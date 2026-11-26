# SPDX-License-Identifier: Apache-2.0
"""Test-pin grants isolate definitions, preserve accounts and support targeted undo."""

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from guardian_tales.accounts.snapshots import import_snapshot
from guardian_tales.administration.admin import MAX_USER_REVISION
from guardian_tales.administration.admin_test_items import (
    grant_test_pin,
    remove_test_pin,
    test_pin_history,
)
from guardian_tales.administration.test_item_static import (
    PIN_ID,
    PIN_NAME,
    TABLE,
    pin_spec,
    prepare,
)
from guardian_tales.inventory.items import inventory_item
from guardian_tales.modes.guild.raid_static import compress, decode, digest, records
from guardian_tales.runtime.bootstrap import BootstrapSession, GuestStore
from guardian_tales.runtime.state_lock import StateLock
from tests.account.test_snapshots import request, synthetic_snapshot


def source_body(extra=()):
    pin = dict(
        Id=PIN_ID,
        Name=PIN_NAME,
        Type="weapon",
        Rarity=3,
        Defense=18.88,
        Limited=True,
        Composable=False,
        Summonable=False,
        MinOptions=0,
        MaxOptions=0,
        WeaponType="accessory",
        OriginRarity=3,
        StatGrowthRate=1.02,
        NameWithoutRarity="aprilfool_2025_accessory",
        SpriteName={"default": "april_fool_2025_accessory"},
        StaticOptions=[dict(OptionId=i, Level=41) for i in (36, 37, 38)],
    )
    tables = {
        "items": json.dumps([pin, *extra]),
        "options": '[{"Id":10,"Class":"TotalAttackScale","AttackScaleAdd":0.01,"AttackScaleBase":0}]',
        "constants": '{"ChangeNickCost":1200}',
        "unchanged": '{"data":[1,2]}',
        "__checksum__": "source-checksum",
    }
    return compress(
        "".join(
            f"{name}\n{value}\n31\n{digest(value.encode())}\n" for name, value in tables.items()
        ).encode()
    )


class TestPinAdministrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.references = self.root / "reference"
        self.references.mkdir()
        self.source = self.references / "static_data_get.bin"
        self.source.write_bytes(source_body())
        (self.references / "static_data_check.bin").write_bytes(b'{"Checksum":"source-checksum"}')
        snapshot = synthetic_snapshot()
        user = snapshot["profile"]["User"]
        user["Cas"] = 0x80000008
        user["ItemIdCounter"] += 1
        original = inventory_item(user["ItemIdCounter"], PIN_ID)
        original.update(Locked=True, Experience=2077400, LimitBreaks=5)
        user["ItemWeapons"].append(original)
        self.original_id = original["Id"]
        self.snapshot = self.root / "synthetic.json"
        self.snapshot.write_text(json.dumps(snapshot))
        self.state = self.root / "state"
        import_snapshot(self.snapshot, self.state)
        self.database = self.state / "server.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self):
        with closing(sqlite3.connect(self.database)) as db:
            return json.loads(
                db.execute("SELECT profile FROM local_account WHERE id=1").fetchone()[0]
            )

    def save(self, profile):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))

    def dump(self):
        with closing(sqlite3.connect(self.database)) as db:
            return list(db.iterdump())

    def grant(self, **kwargs):
        return grant_test_pin(
            self.state,
            self.references,
            kwargs.pop("operation_id", "pin-01"),
            kwargs.pop("reason", "Local testing"),
            **kwargs,
        )

    def session(self, db):
        session = BootstrapSession(GuestStore(db, self.references))
        session.signed_in = True
        return session

    def test_default_grant_adds_one_locked_item_and_preserves_entire_original_account(self):
        before = self.profile()
        source, snapshot = self.source.read_bytes(), self.snapshot.read_bytes()
        receipt = self.grant()
        expected = copy.deepcopy(before)
        row = inventory_item(before["User"]["ItemIdCounter"] + 1, receipt["spec_id"])
        row["Locked"] = True
        expected["User"]["ItemWeapons"].append(row)
        expected["User"]["ItemIdCounter"] += 1
        expected["User"]["Cas"] += 1
        self.assertEqual(self.profile(), expected)
        self.assertEqual(
            (receipt["result"], receipt["defense"], receipt["attack_percent"]),
            ("applied", 10000, 0),
        )
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.snapshot.read_bytes(), snapshot)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(
                GuestStore(db, self.references).account.read("/auth/fetch-account"), expected
            )
        with closing(sqlite3.connect(receipt["backup_path"])) as db:
            self.assertEqual(
                json.loads(db.execute("SELECT profile FROM local_account").fetchone()[0]), before
            )
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        path = Path(receipt["backup_path"])
        self.assertEqual(
            path.with_suffix(".sqlite3.sha256").read_text().strip(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def test_optional_attack_is_an_ordinary_fixed_range_suboption_not_global_item_edits(self):
        receipt = self.grant(attack_percent=1000)
        row = self.profile()["User"]["ItemWeapons"][-1]
        self.assertEqual(
            row["Options"], [dict(OptionId=10, Level=1000, Locked=True, OptionSource=0)]
        )
        with closing(sqlite3.connect(self.database)) as db:
            body = self.session(db).handle(request("/static-data/get", {})).body
        items = json.loads(records(decode(body))[1]["items"][1])
        original, custom = items
        self.assertEqual(
            original, json.loads(records(decode(self.source.read_bytes()))[1]["items"][1])[0]
        )
        self.assertEqual(custom["Id"], receipt["spec_id"])
        self.assertNotEqual(custom["Name"], original["Name"])
        for key in ("SpriteName", "NameWithoutRarity", "WeaponType", "Rarity"):
            self.assertEqual(custom[key], original[key])
        self.assertEqual((custom["Defense"], custom["StatGrowthRate"]), (10000, 1.0))
        self.assertEqual(
            custom["Options"], [dict(OptionId=10, MinLevel=1000, MaxLevel=1000, Probability=1)]
        )
        self.assertEqual(custom["StaticOptions"], [dict(OptionId=i, Level=41) for i in (37, 38)])

    def test_retry_does_not_duplicate_restore_sold_items_or_overwrite_later_progress(self):
        receipt = self.grant()
        current = self.profile()
        current["User"]["Assets"][0]["Amount"] += 9
        current["User"]["ItemWeapons"].pop()
        self.save(current)
        before, backups = self.dump(), list((self.state / "backups").iterdir())
        retry = self.grant()
        self.assertEqual(retry["result"], "already_applied")
        self.assertFalse(retry["present"])
        self.assertEqual(retry["inventory_id"], receipt["inventory_id"])
        self.assertEqual(self.dump(), before)
        self.assertEqual(list((self.state / "backups").iterdir()), backups)
        for change in ({"defense": 9999}, {"attack_percent": 1000}, {"reason": "Other reason"}):
            with self.assertRaises(ValueError):
                self.grant(**change)
        self.assertEqual(self.dump(), before)

    def test_new_operation_allocates_distinct_inventory_and_spec_ids_without_stacking(self):
        first = self.grant()
        second = self.grant(operation_id="pin-02", attack_percent=1000)
        self.assertEqual(second["inventory_id"], first["inventory_id"] + 1)
        self.assertNotEqual(second["spec_id"], first["spec_id"])
        self.assertEqual(len(test_pin_history(self.state)), 2)
        self.assertTrue(all(r["present"] for r in test_pin_history(self.state)))

    def test_invalid_input_missing_source_counter_and_revision_overflows_make_no_writes(self):
        before = self.dump()
        for change in (
            {"defense": 0},
            {"defense": True},
            {"defense": 10001},
            {"attack_percent": -1},
            {"attack_percent": True},
            {"attack_percent": 1001},
            {"attack_percent": 1.5},
            {"operation_id": "bad\nID"},
            {"reason": " "},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.grant(**change)
        self.assertEqual(self.dump(), before)
        for change in (
            {"ItemIdCounter": 0},
            {"ItemIdCounter": 0x7FFFFFFF},
            {"Cas": MAX_USER_REVISION},
        ):
            profile = self.profile()
            profile["User"].update(change)
            self.save(profile)
            before = self.dump()
            with self.assertRaises(ValueError):
                self.grant()
            self.assertEqual(self.dump(), before)

    def test_backend_lock_prevents_both_grant_and_removal(self):
        self.grant()
        before = self.dump()
        with StateLock(self.state):
            for action in (
                lambda: self.grant(operation_id="pin-02"),
                lambda: remove_test_pin(self.state, "pin-01"),
            ):
                with self.assertRaisesRegex(RuntimeError, "in use"):
                    action()
            self.assertEqual(len(test_pin_history(self.state)), 1)
        self.assertEqual(self.dump(), before)

    def test_failed_receipt_rolls_back_profile_counter_and_definition_together(self):
        self.grant()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                f"CREATE TRIGGER fail_grant BEFORE INSERT ON {TABLE} BEGIN SELECT RAISE(ABORT,'test failure'); END"
            )
        before = self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            self.grant(operation_id="pin-02")
        self.assertEqual(self.dump(), before)

    def test_no_opt_in_retains_parent_bytes_and_creates_no_tables(self):
        with closing(sqlite3.connect(self.database)) as db:
            session = self.session(db)
            before, changes = list(db.iterdump()), db.total_changes
            db.execute("PRAGMA query_only=ON")
            first = session.handle(request("/static-data/get", {})).body
            second = session.handle(request("/static-data/get", {})).body
            self.assertEqual(first, second)
            self.assertEqual(len(json.loads(records(decode(first))[1]["items"][1])), 1)
            self.assertEqual(list(db.iterdump()), before)
            self.assertEqual(db.total_changes, changes)

    def test_overlay_get_check_refresh_and_removal_compose_with_effective_parent(self):
        with closing(sqlite3.connect(self.database)) as db:
            original = self.session(db).handle(request("/static-data/get", {})).body
        self.grant()
        with closing(sqlite3.connect(self.database)) as db:
            session = self.session(db)
            before, changes = list(db.iterdump()), db.total_changes
            db.execute("PRAGMA query_only=ON")
            overlay = session.handle(request("/static-data/get", {})).body
            a, b = records(decode(original))[1], records(decode(overlay))[1]
            for key in a.keys() - {"items", "__checksum__"}:
                self.assertEqual(a[key], b[key])
            checksum = b["__checksum__"][1]
            self.assertNotEqual(checksum, a["__checksum__"][1])
            for candidate, expected in ((checksum, True), (a["__checksum__"][1], False)):
                check = json.loads(
                    session.handle(
                        request("/static-data/check-update", {"Checksum": candidate})
                    ).body
                )
                self.assertEqual(
                    check,
                    dict(
                        UpToDate=expected,
                        Checksum=checksum,
                        QuitGameWhenStaticDataUpdateNeeded=False,
                    ),
                )
            self.assertEqual(list(db.iterdump()), before)
            self.assertEqual(db.total_changes, changes)
        remove_test_pin(self.state, "pin-01")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(
                self.session(db).handle(request("/static-data/get", {})).body, original
            )

    def test_changed_mode_parent_is_preserved_and_yields_a_new_checksum(self):
        self.grant()
        with closing(sqlite3.connect(self.database)) as db:
            session = self.session(db)
            first = session.handle(request("/static-data/get", {})).body
            extra = dict(Id=222, Name="mode-added", Type="misc")
            parent = source_body((extra,))
            with patch(
                "guardian_tales.runtime.bootstrap.guild_war_bootstrap_override", return_value=parent
            ):
                second = session.handle(request("/static-data/get", {})).body
        before, after = records(decode(first))[1], records(decode(second))[1]
        self.assertNotEqual(before["__checksum__"][1], after["__checksum__"][1])
        self.assertIn(extra, json.loads(after["items"][1]))
        self.assertEqual(json.loads(after["constants"][1])["ChangeNickCost"], 0)

    def test_removal_detaches_only_generated_equipment_preserves_progress_and_is_idempotent(self):
        receipt = self.grant(attack_percent=1000)
        current = self.profile()
        current["User"]["Characters"][0]["Accessory1"] = receipt["inventory_id"]
        current["User"]["Assets"][0]["Amount"] += 23
        self.save(current)
        expected = copy.deepcopy(current)
        expected["User"]["ItemWeapons"].pop()
        expected["User"]["Characters"][0]["Accessory1"] = None
        expected["User"]["Cas"] += 1
        removed = remove_test_pin(self.state, "pin-01")
        self.assertEqual(removed["result"], "removed")
        self.assertFalse(removed["present"])
        self.assertEqual(self.profile(), expected)
        before = self.dump()
        self.assertEqual(remove_test_pin(self.state, "pin-01")["result"], "already_removed")
        self.assertEqual(self.grant(attack_percent=1000)["result"], "already_applied")
        self.assertEqual(self.dump(), before)
        with self.assertRaises(ValueError):
            remove_test_pin(self.state, str(self.original_id))
        self.assertEqual(self.dump(), before)

    def test_removal_guards_training_socketed_jewels_and_mismatched_inventory(self):
        receipt = self.grant()
        original = self.profile()
        for change in ("training", "jewel", "spec"):
            current = copy.deepcopy(original)
            if change == "training":
                current["User"]["TrainingSlots"] = {"4": {"ItemId": receipt["inventory_id"]}}
            elif change == "jewel":
                current["User"]["ItemWeapons"][-1]["JewelSlots"] = [123]
            else:
                current["User"]["ItemWeapons"][-1]["ItemId"] = PIN_ID
            self.save(current)
            before = self.dump()
            with self.assertRaises(ValueError):
                remove_test_pin(self.state, "pin-01")
            self.assertEqual(self.dump(), before)

    def test_failed_removal_audit_rolls_back_detachment_and_item(self):
        receipt = self.grant()
        current = self.profile()
        current["User"]["Characters"][0]["Accessory1"] = receipt["inventory_id"]
        self.save(current)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                f"CREATE TRIGGER fail_remove BEFORE UPDATE ON {TABLE} BEGIN SELECT RAISE(ABORT,'test failure'); END"
            )
        before = self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            remove_test_pin(self.state, "pin-01")
        self.assertEqual(self.dump(), before)

    def test_retiring_an_already_sold_pin_does_not_rewrite_the_profile(self):
        self.grant()
        current = self.profile()
        current["User"]["ItemWeapons"].pop()
        self.save(current)
        self.assertEqual(remove_test_pin(self.state, "pin-01")["result"], "removed")
        self.assertEqual(self.profile(), current)

    def test_source_collisions_bad_identity_missing_tables_and_revision_overflow_reject(self):
        collision = dict(Id=9990003, Name="existing", Type="misc")
        spec = pin_spec(source_body((collision,)), [], 10000, 0)
        self.assertEqual(spec["Id"], 9990013)
        for body in (
            compress(b"[]"),
            source_body((json.loads(records(decode(source_body()))[1]["items"][1])[0],)),
        ):
            with self.assertRaises(ValueError):
                pin_spec(body, [], 10000, 0)
        with self.assertRaises(ValueError):
            prepare(source_body(), (json.dumps(collision), json.dumps(collision)))

    def test_wrong_pin_or_attack_definition_and_revision_overflow_reject_before_grant(self):
        original = self.source.read_bytes()
        lines, tables = records(decode(original))
        for name, value in (
            ("items", tables["items"][1].replace(PIN_NAME, "wrong_item")),
            ("options", "[]"),
        ):
            changed = lines.copy()
            at = tables[name][0]
            changed[at : at + 4] = [
                name + "\n",
                value + "\n",
                "31\n",
                digest(value.encode()) + "\n",
            ]
            self.source.write_bytes(compress("".join(changed).encode()))
            before = self.dump()
            with self.assertRaises(ValueError):
                self.grant(attack_percent=1000)
            self.assertEqual(self.dump(), before)
        changed = lines.copy()
        changed[tables["items"][0] + 2] = str(0x7FFFFFFF) + "\n"
        self.source.write_bytes(compress("".join(changed).encode()))
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(self.dump(), before)

    def test_missing_account_incomplete_prologue_and_wrong_schema_reject(self):
        with self.assertRaises(ValueError):
            grant_test_pin(self.root / "missing", self.references, "x", "Local testing")
        self.assertFalse((self.root / "missing").exists())
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("DELETE FROM imported_account")
        before = self.dump()
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE local_account SET schema_version=999")
        before = self.dump()
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(self.dump(), before)

    def test_backup_failure_and_registry_capacity_prevent_account_changes(self):
        before = self.dump()
        with patch(
            "guardian_tales.administration.admin_test_items.backup_and_begin",
            side_effect=OSError("backup failed"),
        ):
            with self.assertRaises(OSError):
                self.grant()
        self.assertEqual(self.dump(), before)
        self.grant()
        before = self.dump()
        with patch("guardian_tales.administration.admin_test_items.MAX_GRANTS", 1):
            with self.assertRaises(ValueError):
                self.grant(operation_id="pin-02")
        self.assertEqual(self.dump(), before)

    def test_generated_pin_can_be_unlocked_and_sold_through_existing_native_routes(self):
        receipt = self.grant(attack_percent=1000)
        with closing(sqlite3.connect(self.database)) as db:
            session = self.session(db)
            session.handle(request("/item/unlock", {"itemIndexes": [receipt["inventory_id"]]}))
            session.handle(request("/item/sell", {"SellItems": {str(receipt["inventory_id"]): 1}}))
            profile = session.store.account.profile()
            self.assertFalse(
                any(row["Id"] == receipt["inventory_id"] for row in profile["User"]["ItemWeapons"])
            )
            body = session.handle(request("/static-data/get", {})).body
            self.assertEqual(len(json.loads(records(decode(body))[1]["items"][1])), 1)
        before = self.dump()
        self.assertFalse(self.grant(attack_percent=1000)["present"])
        self.assertEqual(self.dump(), before)

    def test_cli_grant_history_and_remove_use_the_same_audited_path(self):
        base = [sys.executable, "-m", "guardian_tales", "admin"]
        state = ["--data-dir", str(self.state)]
        for args, result in (
            (
                [
                    "grant-test-pin",
                    *state,
                    "--reference-dir",
                    str(self.references),
                    "--operation-id",
                    "cli-01",
                    "--reason",
                    "CLI testing",
                    "--attack-percent",
                    "1000",
                ],
                "applied",
            ),
            (["remove-test-pin", *state, "--operation-id", "cli-01"], "removed"),
        ):
            run = subprocess.run(
                [*base, *args], capture_output=True, text=True, check=True, timeout=15
            )
            self.assertEqual(json.loads(run.stdout)["result"], result)
        run = subprocess.run(
            [*base, "test-pin-history", *state],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        self.assertFalse(json.loads(run.stdout)[0]["present"])
