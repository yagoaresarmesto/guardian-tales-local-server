# SPDX-License-Identifier: Apache-2.0
"""Guild War calendar activation is reversible, composed and account preserving."""

import base64
import copy
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.guild_raid import CATALOG as RAID_CATALOG
from guardian_tales.guild_raid import SELECTION as RAID_SELECTION
from guardian_tales.guild_raid import select_season
from guardian_tales.guild_war import (
    ABANDON,
    CASTLES,
    END_COOP,
    MAX_DAMAGE,
    RECORDS,
    ROUTE,
    START_COOP,
    UNLOCK,
    main,
)
from guardian_tales.guild_war_static import (
    OVERLAY_POLICY,
    SELECTION,
    base_body,
    bootstrap_override,
    cooperative_stage_ids,
    enable,
    load_selection,
)
from guardian_tales.packet_reader import parse_packet
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.raid_static import compress, decode, digest, records
from tests.test_guild_raid import synthetic_catalog, synthetic_static
from tests.test_snapshots import request, synthetic_snapshot


def synthetic_war_static(catalog):
    original = records(decode(synthetic_static(catalog)))[1]
    content = {name: raw for name, (_, raw, _) in original.items()}
    calendar = json.loads(content["seasondate"])
    calendar["EventPeriod"].append(
        {
            "Id": 5500001,
            "From": {"KakaoGlobal": "2099-02-14T00:00:00Z", "KakaoKorea": "2099-02-14T00:00:00Z"},
            "To": {"KakaoGlobal": "2099-02-21T00:00:00Z", "KakaoKorea": "2099-02-21T00:00:00Z"},
        }
    )
    content["seasondate"] = json.dumps(calendar)
    content["guildwar"] = json.dumps(
        {
            "Seasons": [{"Id": 1, "SeasonDateId": 5500001, "CastleStageGroupId": 2001}],
            "SyntheticKeep": [1, 2],
            "Constants": {
                "SingleClearedStageIds": [850020002],
                "SingleStageSetId": 1,
                "PlayCoopCoinReward": 10,
                "SyntheticKeep": 9,
            },
            "CastleStageSet": [
                {
                    "Id": 1,
                    "StageSetType": "Single",
                    "SiegeStageIds": [850010002],
                    "DefenceStageIds": [850020002],
                },
                {
                    "Id": 2,
                    "GroupId": 2001,
                    "StageSetType": "Coop",
                    "SiegeStageIds": [850030005],
                    "DefenceStageIds": [850040001],
                },
                {
                    "Id": 3,
                    "GroupId": 2002,
                    "StageSetType": "Coop",
                    "SiegeStageIds": [850030007],
                    "DefenceStageIds": [],
                },
            ],
        }
    )
    content["unlockfeature"] = json.dumps([{"Id": 1, "Type": "QuestClear", "Rewards": [7]}])
    return compress(
        "".join(
            f"{name}\n{raw}\n1\n{digest(base64.b64decode(raw) if name.endswith('-bin') else raw.encode())}\n"
            for name, raw in content.items()
        ).encode()
    )


class GuildWarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.catalog = synthetic_catalog()
        (self.root / RAID_CATALOG).write_text(json.dumps(self.catalog))
        self.source = self.root / "static_data_get.bin"
        self.original = synthetic_war_static(self.catalog)
        self.source.write_bytes(self.original)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = GuestStore(self.db, self.root)
        self.ref = self.store.references
        self.session = BootstrapSession(self.store)
        self.now = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
        for target in (
            "guardian_tales.guild_war.utc_now",
            "guardian_tales.guild_war_static.utc_now",
        ):
            clock = patch(target, side_effect=lambda: self.now)
            clock.start()
            self.addCleanup(clock.stop)

    def install(self, imported=True):
        profile = synthetic_snapshot()["profile"]
        profile["GuildMember"] = {"UserId": profile["User"]["Id"], "GuildId": 7}
        profile["UserRaid"] = {"Raid": None, "PickAxeCount": 17, "PunchKingCoins": 99}
        reads = {
            "/preset/get-presets": {
                "body_type": 1,
                "value": {
                    "UserPartyPreset2": {
                        "Presets": [
                            {
                                "Id": 701,
                                "Characters": [{"Id": profile["User"]["Characters"][0]["Id"]}],
                            }
                        ]
                    }
                },
            }
        }
        with self.db:
            if imported:
                self.db.execute(
                    "INSERT INTO imported_account VALUES(1,?,?,?,?)",
                    ("0" * 64, "synthetic", json.dumps(reads), "{}"),
                )
            else:
                self.db.execute("INSERT INTO prologue_selection VALUES(1,'synthetic','{}')")
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        self.session.handle(
            request(
                "/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": False}
            )
        )
        return profile

    def call(self, body, route=ROUTE):
        return read_json_body(
            parse_packet(encode_packet(self.session.handle(request(route, body))))
        )

    def test_activation_changes_only_global_war_and_raid_periods_and_disable_restores_parent(self):
        select_season(self.ref, 1)
        parent = base_body(self.ref)
        raid_selection = (self.root / RAID_SELECTION).read_bytes()
        before = records(decode(parent))[1]
        selection = enable(self.ref)
        after = records(decode(bootstrap_override(self.ref, "static_data_get.bin", None)))[1]
        for name in before.keys() - {"seasondate", "unlockfeature", "guildwar", "__checksum__"}:
            self.assertEqual(before[name], after[name])
        expected_war = json.loads(before["guildwar"][1])
        expected_war["Constants"]["PlayCoopCoinReward"] = 0
        self.assertEqual(json.loads(after["guildwar"][1]), expected_war)
        original_features = json.loads(before["unlockfeature"][1])
        features = json.loads(after["unlockfeature"][1])
        self.assertEqual(features[:-1], original_features)
        self.assertEqual(features[-1]["Id"], 126)
        self.assertEqual(features[-1]["Rewards"], [])
        self.assertEqual(features[-1]["VersionFrom"]["KakaoGlobal"], "v3.57")
        self.assertEqual(features[-1]["VersionFrom"]["KakaoKorea"], "v9.99")

        old = json.loads(before["seasondate"][1])["EventPeriod"]
        new = json.loads(after["seasondate"][1])["EventPeriod"]
        raid_ids = {row["SeasonDateId"] for row in json.loads(before["guildraid2"][1])["Seasons"]}
        for was, row in zip(old, new):
            if row["Id"] not in raid_ids | {5500001}:
                self.assertEqual(was, row)
                continue
            for key in ("From", "To"):
                self.assertEqual(
                    {k: v for k, v in was[key].items() if k != "KakaoGlobal"},
                    {k: v for k, v in row[key].items() if k != "KakaoGlobal"},
                )
            end = datetime.fromisoformat(row["To"]["KakaoGlobal"])
            self.assertEqual(end > self.now, row["Id"] == 5500001)
        self.assertEqual(
            datetime.fromisoformat(selection["period"]["to"])
            - datetime.fromisoformat(selection["period"]["from"]),
            timedelta(days=7),
        )
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual((self.root / RAID_SELECTION).read_bytes(), raid_selection)
        (self.root / SELECTION).unlink()
        self.assertIsNone(bootstrap_override(self.ref, "static_data_get.bin", None))
        self.assertEqual(base_body(self.ref), parent)

    def test_single_mode_feature_acknowledgment_changes_only_client_bit_126_without_rewards_or_writes(
        self,
    ):
        original = self.install()
        original["UserClaimedReward"]["UnlockFeature"] = base64.b64encode(b"\x25" * 20).decode()
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(original),))
        enable(self.ref)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for _ in range(2):
            response = self.call({"Feature": 126}, UNLOCK)
            self.assertEqual(response["AddedItems"], [])
            actual = bytearray(base64.b64decode(response["UserClaimedReward"]["UnlockFeature"]))
            expected = bytearray(b"\x25" * 20)
            expected[15] |= 64
            self.assertEqual(actual, expected)
        self.assertEqual(self.store.account.profile(), original)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_single_mode_acknowledgment_rejects_disabled_or_other_reward_requests(self):
        self.install(False)
        with self.assertRaises(PacketError):
            self.call({"Feature": 126}, UNLOCK)
        enable(self.ref)
        response = self.call({"Feature": 126}, UNLOCK)
        self.assertTrue(base64.b64decode(response["UserClaimedReward"]["UnlockFeature"])[15] & 64)
        before = list(self.db.iterdump())
        for body in (
            None,
            {},
            {"Feature": 125},
            {"Feature": True},
            {"Feature": [126]},
            {"Feature": 126, "Rewards": []},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, UNLOCK)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_authenticated_native_entry_is_read_only_and_keeps_every_other_mode_and_asset(self):
        profile = self.install()
        enable(self.ref)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for partial in (False, True, False):
            result = self.call({"isPartial": partial})
            self.assertEqual(set(result["UserRaid"]), {"UserId", "GuildWar"})
            self.assertEqual(result["UserRaid"]["GuildWar"]["PurchaseCounter"], {})
            self.assertEqual(result["UserRaid"]["GuildWar"]["PlayedCharacters"], [])
            info = result["GuildWarInfo"]
            self.assertEqual((info["SeasonId"], info["Phase"]), (1, 1))
            self.assertEqual(info["BattleStatus"], {})
            self.assertEqual(info["CanRewards"], [])
            self.assertEqual(info["BuffIds"], [])
            self.assertEqual(result["AddedItems"], [])
            self.assertGreater(datetime.fromisoformat(info["NextUpdateTime"]), self.now)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_fresh_registered_guest_reopens_without_creating_progress_or_claims(self):
        profile = self.install(False)
        enable(self.ref)
        self.assertEqual(self.call({"isPartial": False})["GuildWarInfo"]["SeasonId"], 1)
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.session.handle(
            request("/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": True})
        )
        self.assertEqual(self.call({"isPartial": True})["GuildWarInfo"]["Phase"], 1)
        self.assertEqual(self.store.account.profile(), profile)

    def test_schema_authentication_disabled_trial_and_preserved_war_state_are_guarded(self):
        with self.assertRaises(PacketError):
            self.call({"isPartial": False})
        original = self.install()
        with self.assertRaises(PacketError):
            self.call({"isPartial": False})
        enable(self.ref)
        for body in (
            None,
            {},
            [],
            {"IsPartial": False},
            {"isPartial": 0},
            {"isPartial": False, "Claim": True},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body)
        for mutate in (
            lambda p: p.update(GuildMember=None),
            lambda p: p["UserRaid"].update(GuildWar={"SeasonId": 1, "GuildWarCoin": 17}),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call({"isPartial": False})
            self.assertEqual(list(self.db.iterdump()), before)
        for route in (
            "/guild-war/claim-rewards",
            "/guild-war/start-coop-stage",
            "/guild-war/buy-items",
        ):
            with self.assertRaises(PacketError):
                self.call({}, route)

    def test_static_bootstrap_cache_hashes_match_the_enabled_compressed_body(self):
        selection = enable(self.ref)
        body = self.session.handle(request("/static-data/get", {"ClientVersions": {}})).body
        self.assertEqual(
            records(decode(body))[1]["__checksum__"][1], selection["static_data_checksum"]
        )
        for checksum, expected in (("old", False), (selection["static_data_checksum"], True)):
            result = self.call({"Checksum": checksum}, "/static-data/check-update")
            self.assertEqual(result["UpToDate"], expected)
            self.assertEqual(result["Checksum"], selection["static_data_checksum"])

    def test_later_raid_selection_and_arena_parent_are_composed_without_resetting_war_period(self):
        select_season(self.ref, 1)
        first = enable(self.ref)
        select_season(self.ref, 2)
        parent = base_body(self.ref)
        with patch("guardian_tales.guild_war_static.arena_override", return_value=parent) as arena:
            bootstrap_override(self.ref, "static_data_get.bin", None)
            self.assertTrue(arena.called)
        second = load_selection(self.ref)
        self.assertNotEqual(first["base_sha256"], second["base_sha256"])
        self.assertGreater(second["static_data_revision"], first["static_data_revision"])
        self.assertEqual(first["period"], second["period"])
        (self.root / SELECTION).unlink()
        self.assertEqual(base_body(self.ref), parent)

    def test_expired_entry_requires_bootstrap_refresh_and_corrupt_data_never_falls_back(self):
        self.install()
        first = enable(self.ref)
        self.now += timedelta(days=8)
        with self.assertRaises(PacketError):
            self.call({"isPartial": False})
        bootstrap_override(self.ref, "static_data_get.bin", None)
        second = load_selection(self.ref)
        self.assertNotEqual(first["period"], second["period"])
        self.assertEqual(self.call({"isPartial": False})["GuildWarInfo"]["SeasonId"], 1)
        body_path = self.root / f"guild_war_static_{second['static_data_sha256']}.bin"
        body_path.write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            bootstrap_override(self.ref, "static_data_get.bin", None)
        (self.root / SELECTION).write_text('{"client":null}')
        with self.assertRaises(ValueError):
            load_selection(self.ref)

    def test_cli_enable_status_disable_and_missing_source_errors(self):
        for action, expected in (
            ("enable", True),
            ("status", True),
            ("disable", False),
            ("disable", False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                main([action, "--reference-dir", str(self.root)])
            self.assertEqual(json.loads(out.getvalue())["enabled"], expected)
        self.source.unlink()
        with self.assertRaises(SystemExit):
            main(["enable", "--reference-dir", str(self.root)])

    def test_optional_skip_basic_waives_only_source_prerequisite_and_is_reversible_without_clears(
        self,
    ):
        profile = self.install()
        before = list(self.db.iterdump())
        original = json.loads(records(decode(self.original))[1]["guildwar"][1])
        out = io.StringIO()
        with redirect_stdout(out):
            main(["enable", "--skip-basic", "--reference-dir", str(self.root)])
        self.assertTrue(json.loads(out.getvalue())["skip_basic_requirement"])
        altered = json.loads(
            records(decode(bootstrap_override(self.ref, "static_data_get.bin", None)))[1][
                "guildwar"
            ][1]
        )
        expected = copy.deepcopy(original)
        expected["Constants"]["PlayCoopCoinReward"] = 0
        expected["CastleStageSet"][0]["SiegeStageIds"] = []
        expected["CastleStageSet"][0]["DefenceStageIds"] = []
        self.assertEqual(altered, expected)
        self.assertTrue(load_selection(self.ref)["skip_basic"])
        enable(self.ref, skip_basic=False)
        restored = json.loads(
            records(decode(bootstrap_override(self.ref, "static_data_get.bin", None)))[1][
                "guildwar"
            ][1]
        )
        expected = copy.deepcopy(original)
        expected["Constants"]["PlayCoopCoinReward"] = 0
        self.assertEqual(restored, expected)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_legacy_overlay_upgrades_reward_decoration_without_resetting_window_waiver_or_account(
        self,
    ):
        profile = self.install()
        before = list(self.db.iterdump())
        previous = enable(self.ref, skip_basic=True)
        path = self.root / f"guild_war_static_{previous['static_data_sha256']}.bin"
        lines, items = records(decode(path.read_bytes()))
        war = json.loads(items["guildwar"][1])
        war["Constants"]["PlayCoopCoinReward"] = 10
        raw = json.dumps(war)
        at = items["guildwar"][0]
        lines[at + 1] = raw + "\n"
        lines[at + 3] = digest(raw.encode()) + "\n"
        old_body = compress("".join(lines).encode())
        previous.pop("overlay_policy")
        previous["static_data_sha256"] = hashlib.sha256(old_body).hexdigest()
        (self.root / f"guild_war_static_{previous['static_data_sha256']}.bin").write_bytes(old_body)
        (self.root / SELECTION).write_text(json.dumps(previous))
        self.assertNotIn("overlay_policy", load_selection(self.ref))
        check = json.loads(bootstrap_override(self.ref, "static_data_check.bin", {}))
        upgraded = load_selection(self.ref)
        self.assertEqual(upgraded["overlay_policy"], OVERLAY_POLICY)
        self.assertEqual(upgraded["period"], previous["period"])
        self.assertTrue(upgraded["skip_basic"])
        self.assertEqual(check["Checksum"], upgraded["static_data_checksum"])
        self.assertGreater(upgraded["static_data_revision"], previous["static_data_revision"])
        new = json.loads(
            records(decode(bootstrap_override(self.ref, "static_data_get.bin", None)))[1][
                "guildwar"
            ][1]
        )
        expected = copy.deepcopy(war)
        expected["Constants"]["PlayCoopCoinReward"] = 0
        self.assertEqual(new, expected)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        for invalid in (False, 2, 4):
            (self.root / SELECTION).write_text(json.dumps(dict(upgraded, overlay_policy=invalid)))
            with self.subTest(policy=invalid), self.assertRaises(ValueError):
                load_selection(self.ref)

    def test_imported_cooperative_help_acknowledgment_only_records_the_seen_help_once(self):
        profile = self.install()
        profile["UserProgress"]["Tutorials"] = [
            v for v in profile["UserProgress"]["Tutorials"] if v != 1037
        ]
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        expected = copy.deepcopy(profile)
        expected["UserProgress"]["Tutorials"].append(1037)
        expected["UserProgress"]["Cas"] += 1
        result = self.call({"tutorialIds": [1037]}, "/user/mark-tutorial")
        self.assertEqual(result, {"UserProgress": expected["UserProgress"]})
        self.assertEqual(self.store.account.profile(), expected)
        writes = self.db.total_changes
        self.assertEqual(self.call({"tutorialIds": [1037]}, "/user/mark-tutorial"), result)
        self.assertEqual(self.db.total_changes, writes)

    def test_imported_gameplay_and_mixed_tutorial_acknowledgments_stay_blocked(self):
        self.install()
        before = list(self.db.iterdump())
        for ids in ([200], [1037, 2019], [1037, 0], [999999]):
            with self.subTest(ids=ids), self.assertRaises(PacketError):
                self.call({"tutorialIds": ids}, "/user/mark-tutorial")
        self.assertEqual(list(self.db.iterdump()), before)

    def test_native_castle_list_returns_empty_array_without_clearing_resources_or_writing(self):
        profile = self.install()
        enable(self.ref)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for _ in range(2):
            self.assertEqual(self.call({"seasonId": 1}, CASTLES), {"CastleSimpleInfos": []})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_castle_list_requires_authentication_enabled_trial_and_exact_known_season(self):
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, CASTLES)
        self.install(False)
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, CASTLES)
        enable(self.ref)
        before = list(self.db.iterdump())
        for body in (
            None,
            {},
            {"SeasonId": 1},
            {"seasonId": True},
            {"seasonId": 2},
            {"seasonId": 1, "GuildId": 7},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, CASTLES)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_cooperative_loading_acknowledges_source_stages_and_owned_team_without_writes(self):
        profile = self.install()
        enable(self.ref, skip_basic=True)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for stage in (850030005, 850040001, 850030005):
            self.assertEqual(self.call({"stageId": stage, "presetId": 701}, START_COOP), {})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        self.db.execute("PRAGMA query_only=OFF")
        self.session = BootstrapSession(self.store)
        self.session.handle(
            request("/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": True})
        )
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"stageId": 850030005, "presetId": 701}, START_COOP), {})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        for route in ("/guild-war/end-coop-stage", "/guild-war/claim-rewards"):
            with self.assertRaises(PacketError):
                self.call({}, route)

    def test_cooperative_entry_rejects_disabled_trial_aliases_foreign_stages_and_unowned_team(self):
        body = {"stageId": 850030005, "presetId": 701}
        with self.assertRaises(PacketError):
            self.call(body, START_COOP)
        self.install()
        with self.assertRaises(PacketError):
            self.call(body, START_COOP)
        enable(self.ref)
        before = list(self.db.iterdump())
        for invalid in (
            None,
            {},
            {"StageId": 850030005, "PresetId": 701},
            dict(body, stageId=True),
            dict(body, presetId=True),
            dict(body, stageId=850010002),
            dict(body, stageId=850030007),
            dict(body, presetId=401),
            dict(body, presetId=799),
            dict(body, Reward=True),
        ):
            with self.subTest(body=invalid), self.assertRaises(PacketError):
                self.call(invalid, START_COOP)
        self.assertEqual(list(self.db.iterdump()), before)
        group = {"Presets": [{"Id": 701, "Characters": [{"Id": 999999}]}]}
        with self.db:
            self.db.execute("INSERT INTO party_preset_state VALUES(1,?)", (json.dumps(group),))
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call(body, START_COOP)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_cooperative_catalog_rejects_tampered_body_and_ambiguous_native_stage_groups(self):
        selection = enable(self.ref)
        path = self.root / f"guild_war_static_{selection['static_data_sha256']}.bin"
        source = path.read_bytes()
        path.write_bytes(source[:-1] + bytes([source[-1] ^ 1]))
        with self.assertRaises(ValueError):
            cooperative_stage_ids(self.ref, selection)
        lines, items = records(decode(source))
        war = json.loads(items["guildwar"][1])
        for alter in (
            lambda w: w["Seasons"][0].pop("CastleStageGroupId"),
            lambda w: w["CastleStageSet"].append(copy.deepcopy(w["CastleStageSet"][1])),
            lambda w: w["CastleStageSet"][1].update(SiegeStageIds=[True]),
            lambda w: w["CastleStageSet"][1].update(DefenceStageIds=[850030005]),
            lambda w: w["CastleStageSet"][1].update(GroupId=999),
        ):
            changed = copy.deepcopy(war)
            alter(changed)
            rows = list(lines)
            rows[items["guildwar"][0] + 1] = json.dumps(changed) + "\n"
            with (
                patch(
                    "guardian_tales.guild_war_static.prepared_body",
                    return_value=compress("".join(rows).encode()),
                ),
                self.assertRaises(ValueError),
            ):
                cooperative_stage_ids(self.ref, selection)

    def test_native_cooperative_result_refreshes_menu_without_score_cost_rewards_or_writes(self):
        profile = self.install()
        enable(self.ref)
        expected = {
            "Cancelled": False,
            "GuildWarInfo": self.call({"isPartial": True})["GuildWarInfo"],
            "AddedItems": [],
        }
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for stage, damages, additional in (
            (850030005, [100, 200, 300, 400], 500),
            (850030005, [100, 200, 300, 400], 500),
            (850040001, [0, 0, 0, 0], 0),
            (850030005, [], 0),
            (850030005, [MAX_DAMAGE - 1], 1),
        ):
            self.assertEqual(
                self.call(
                    {"stageId": stage, "damages": damages, "additionalDamage": additional}, END_COOP
                ),
                expected,
            )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_cooperative_result_rejects_aliases_invalid_damages_and_noncooperative_stages(self):
        body = {"stageId": 850030005, "damages": [10, 20, 0, 0], "additionalDamage": 0}
        with self.assertRaises(PacketError):
            self.call(body, END_COOP)
        self.install()
        with self.assertRaises(PacketError):
            self.call(body, END_COOP)
        enable(self.ref)
        before = list(self.db.iterdump())
        for invalid in (
            None,
            {},
            {"StageId": 850030005, "Damages": [0], "AdditionalDamage": 0},
            dict(body, stageId=True),
            dict(body, stageId=850010002),
            dict(body, stageId=850030007),
            dict(body, damages=None),
            dict(body, damages=[0] * 5),
            dict(body, damages=[True]),
            dict(body, damages=[1.5]),
            dict(body, damages=[-1]),
            dict(body, damages=[MAX_DAMAGE + 1]),
            dict(body, damages=[MAX_DAMAGE, 1]),
            dict(body, additionalDamage=True),
            dict(body, additionalDamage=-1),
            dict(body, additionalDamage=MAX_DAMAGE),
            dict(body, Reward=True),
        ):
            with self.subTest(body=invalid), self.assertRaises(PacketError):
                self.call(invalid, END_COOP)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_result_to_lobby_records_are_three_native_empty_arrays_without_profile_or_database_changes(
        self,
    ):
        profile = self.install()
        enable(self.ref)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for _ in range(2):
            self.assertEqual(
                self.call({"seasonId": 1}, RECORDS),
                {
                    "LatestBattleRecords": [],
                    "CoopDefenseInGuildRanking": [],
                    "DailyBattleStatus": [],
                },
            )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_battle_records_require_authenticated_enabled_trial_and_exact_native_season(self):
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, RECORDS)
        self.install(False)
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, RECORDS)
        enable(self.ref)
        before = list(self.db.iterdump())
        for body in (
            None,
            {},
            {"SeasonId": 1},
            {"seasonId": True},
            {"seasonId": 2},
            {"seasonId": 1, "Claim": True},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, RECORDS)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_native_abandon_acknowledgment_is_empty_and_read_only_across_framing_and_retries(self):
        profile = self.install()
        enable(self.ref)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        native = parse_packet(
            encode_packet(Packet(0, b"", body_type=0, api=ABANDON, sequence_id=15))
        )
        for packet in (native, request(ABANDON), request(ABANDON, {}), native):
            self.assertEqual(
                read_json_body(parse_packet(encode_packet(self.session.handle(packet)))), {}
            )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        self.db.execute("PRAGMA query_only=OFF")
        self.session = BootstrapSession(self.store)
        self.session.handle(
            request("/auth/sign-in", {"AuthKind": 0, "AccessToken": "synthetic", "Reconnect": True})
        )
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(None, ABANDON), {})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_abandon_requires_enabled_authenticated_guild_trial_and_rejects_parameters_or_saved_progress(
        self,
    ):
        with self.assertRaises(PacketError):
            self.call(None, ABANDON)
        original = self.install(False)
        with self.assertRaises(PacketError):
            self.call(None, ABANDON)
        enable(self.ref)
        self.assertEqual(self.call({}, ABANDON), {})
        before = list(self.db.iterdump())
        for body in ([], False, 0, "", {"stageId": 850030005}, {"Claim": True}):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, ABANDON)
        self.assertEqual(list(self.db.iterdump()), before)
        for mutate in (
            lambda p: p.update(GuildMember=None),
            lambda p: p["UserRaid"].update(GuildWar={"SeasonId": 1, "PlayCount": 2}),
        ):
            profile = copy.deepcopy(original)
            mutate(profile)
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
            before = list(self.db.iterdump())
            with self.assertRaises(PacketError):
                self.call(None, ABANDON)
            self.assertEqual(list(self.db.iterdump()), before)
