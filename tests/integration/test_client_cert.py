# SPDX-License-Identifier: Apache-2.0
"""Exercise startup renewal using temporary certificates and real signatures."""

import shutil
import ssl
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from guardian_tales.runtime.client_cert import HOSTS, generate, openssl_path, prepare_server_tls


class ClientCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.openssl = openssl_path()
        except ValueError as error:
            raise unittest.SkipTest(str(error)) from error
        cls.original = Path(cls.enterClassContext(tempfile.TemporaryDirectory()))
        generate(cls.original, cls.openssl)

    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        shutil.copytree(self.original, self.directory, dirs_exist_ok=True)
        self.cert = self.directory / "localhost-cert.pem"
        self.ca = self.directory / "ca.pem"

    def command(self, *args):
        return subprocess.run(
            [self.openssl, *args], cwd=self.directory, check=True, capture_output=True, timeout=15
        ).stdout

    def expiry(self, certificate):
        end = self.command("x509", "-in", certificate, "-enddate", "-noout")
        return ssl.cert_time_to_seconds(end.decode().strip().removeprefix("notAfter="))

    def shorten_leaf(self, days=1):
        signed = self.command(
            "x509",
            "-req",
            "-in",
            "server.csr",
            "-CA",
            "ca.pem",
            "-CAkey",
            "ca-key.pem",
            "-set_serial",
            "12345",
            "-sha256",
            "-extfile",
            "server.ext",
            "-days",
            str(days),
        )
        self.cert.write_bytes(signed + self.ca.read_bytes())

    def test_exact_threshold_preserves_chain_and_reports_actual_expiries_without_openssl(self):
        end = self.expiry(self.cert)
        ca_end = self.expiry(self.ca)
        original = self.cert.read_bytes()
        for seconds in (48 * 3600 + 1, 48 * 3600):
            with (
                self.subTest(seconds=seconds),
                patch("guardian_tales.runtime.client_cert.time.time", return_value=end - seconds),
                patch(
                    "guardian_tales.runtime.client_cert.subprocess.run", side_effect=AssertionError
                ),
            ):
                context, dates = prepare_server_tls(self.directory)
                self.assertIsInstance(context, ssl.SSLContext)
                self.assertEqual(datetime.fromisoformat(dates["server"]).timestamp(), end)
                self.assertEqual(datetime.fromisoformat(dates["authority"]).timestamp(), ca_end)
                self.assertEqual(self.cert.read_bytes(), original)

    def test_due_or_expired_leaf_renews_once_with_original_trust_and_keys(self):
        for seconds_left in (48 * 3600 - 1, -3600):
            with self.subTest(seconds_left=seconds_left):
                self.shorten_leaf(days=3 if seconds_left > 0 else 1)
                end = self.expiry(self.cert)
                original = self.cert.read_bytes()
                unchanged = {p: p.read_bytes() for p in self.directory.iterdir() if p != self.cert}
                with patch(
                    "guardian_tales.runtime.client_cert.time.time", return_value=end - seconds_left
                ):
                    _, dates = prepare_server_tls(self.directory)
                    renewed = self.cert.read_bytes()
                    self.assertNotEqual(renewed, original)
                    self.assertEqual(prepare_server_tls(self.directory)[1], dates)
                    self.assertEqual(self.cert.read_bytes(), renewed)
                self.assertTrue(renewed.endswith(self.ca.read_bytes()))
                self.assertEqual(
                    self.expiry(self.cert), datetime.fromisoformat(dates["server"]).timestamp()
                )
                for path, content in unchanged.items():
                    self.assertEqual(path.read_bytes(), content, path.name)
                for host in HOSTS:
                    self.command(
                        "verify",
                        "-CAfile",
                        self.ca,
                        "-purpose",
                        "sslserver",
                        "-verify_hostname",
                        host,
                        self.cert,
                    )

    def test_external_certificate_without_signing_material_remains_usable(self):
        # The quick-start generator provisions only a self-signed cert/key pair.
        self.command(
            "req",
            "-new",
            "-x509",
            "-key",
            "localhost-key.pem",
            "-subj",
            "/CN=localhost",
            "-days",
            "1",
            "-out",
            self.cert,
        )
        for path in self.directory.iterdir():
            if path.name not in ("localhost-cert.pem", "localhost-key.pem"):
                path.unlink()
        original = self.cert.read_bytes()
        context, dates = prepare_server_tls(self.directory)
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(
            datetime.fromisoformat(dates["server"]).timestamp(), self.expiry(self.cert)
        )
        self.assertIsNone(dates["authority"])
        self.assertEqual(self.cert.read_bytes(), original)

    def test_invalid_signing_key_preserves_existing_leaf_and_context(self):
        self.shorten_leaf()
        original = self.cert.read_bytes()
        (self.directory / "ca-key.pem").write_bytes(
            (self.directory / "localhost-key.pem").read_bytes()
        )
        with patch("sys.stderr") as stderr:
            context, dates = prepare_server_tls(self.directory)
        self.assertTrue(stderr.write.called)
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(
            datetime.fromisoformat(dates["server"]).timestamp(), self.expiry(self.cert)
        )
        self.assertEqual(self.cert.read_bytes(), original)

    def test_overlapping_startups_report_expiry_of_the_chain_they_actually_serve(self):
        self.shorten_leaf()
        due = self.cert.read_bytes()
        replacement = (self.original / self.cert.name).read_bytes()
        loaded = {}
        load_chain = ssl.SSLContext.load_cert_chain

        def load_while_other_startup_renews(context, certificate, key):
            load_chain(context, certificate, key)
            loaded[context] = Path(certificate).read_bytes()
            if loaded[context] == due:
                self.cert.write_bytes(replacement)

        with patch.object(ssl.SSLContext, "load_cert_chain", load_while_other_startup_renews):
            context, dates = prepare_server_tls(self.directory)
        self.assertTrue(loaded[context] != due, "Listener kept the old certificate")
        self.assertTrue(loaded[context] == self.cert.read_bytes(), "Listener and disk disagree")
        self.assertEqual(
            datetime.fromisoformat(dates["server"]).timestamp(), self.expiry(self.cert)
        )

    def test_ca_expiry_limits_useful_renewal_and_keeps_original_trust(self):
        # Reissue this test CA for one day using its current key and extensions.
        short_ca = self.command("x509", "-in", self.ca, "-signkey", "ca-key.pem", "-days", "1")
        self.ca.write_bytes(short_ca)
        next(self.directory.glob("*.0")).write_bytes(short_ca)
        self.shorten_leaf()
        ca_end = self.expiry(self.ca)
        original = self.cert.read_bytes()
        for now in (ca_end - 3600, ca_end + 1):
            with (
                self.subTest(now=now),
                patch("guardian_tales.runtime.client_cert.time.time", return_value=now),
            ):
                context, dates = prepare_server_tls(self.directory)
                self.assertIsInstance(context, ssl.SSLContext)
                self.assertEqual(datetime.fromisoformat(dates["authority"]).timestamp(), ca_end)
                self.assertEqual(self.cert.read_bytes(), original)
                self.assertEqual(self.ca.read_bytes(), short_ca)
