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
    CASTLE_DETAIL,
    CASTLES,
    COIN_RANKING,
    END_COOP,
    END_MULTI,
    GUILD_SUMMARY,
    MAX_DAMAGE,
    RANKING,
    RECORDS,
    ROUTE,
    START_COOP,
    START_MULTI,
    UNLOCK,
    main,
)
from guardian_tales.guild_war_static import (
    OVERLAY_POLICY,
    PHASES,
    SELECTION,
    base_body,
    bootstrap_override,
    castle_specs,
    cooperative_stage_ids,
    defense_stage_ids,
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
            "Seasons": [
                {
                    "Id": 1,
                    "SeasonDateId": 5500001,
                    "CastleStageGroupId": 2001,
                    "CastleDeployGroupId": 1001,
                    "ShopGroupId": 4001,
                }
            ],
            "CastleSpecs": [
                {"Id": 1, "GroupId": 1001, "Grade": 1, "SpotId": 1},
                {"Id": 2, "GroupId": 1001, "Grade": 4, "SpotId": 2},
                {"Id": 101, "GroupId": 1002, "Grade": 2, "SpotId": 1},
            ],
            "CastleDeploySpots": [
                {"SpotId": 1, "Coordinate": [0.2, 0.2], "SectionNumber": 1},
                {"SpotId": 2, "Coordinate": [3.1, 0.4], "SectionNumber": 1},
            ],
            "ShopSet": [
                {"Id": 1, "GroupId": 4001, "Coins": 10, "Rewards": [{"ItemId": 101, "Amount": 1}]},
                {"Id": 2, "GroupId": 9999, "Coins": 20, "Rewards": [{"ItemId": 102, "Amount": 2}]},
            ],
            "SyntheticKeep": [1, 2],
            "Constants": {
                "SingleClearedStageIds": [850020002],
                "SingleStageSetId": 1,
                "PlayCoopCoinReward": 10,
                "PlayMultiCoinReward": 10,
                "PlayMultiBattleMedalReward": 12,
                "GetPointPlay": 10,
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
                {
                    "Id": 4,
                    "GroupId": 2001,
                    "StageSetType": "MultiGrade1",
                    "SiegeStageIds": [850050077],
                    "DefenceStageIds": [850060004],
                },
                {
                    "Id": 5,
                    "GroupId": 2001,
                    "StageSetType": "MultiGrade4",
                    "SiegeStageIds": [850050005],
                    "DefenceStageIds": [850060001],
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
        expected_war["Constants"].update(
            PlayCoopCoinReward=0,
            PlayMultiCoinReward=0,
            PlayMultiBattleMedalReward=0,
            GetPointPlay=0,
        )
        expected_war["ShopSet"] = [row for row in expected_war["ShopSet"] if row["GroupId"] != 4001]
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

    def test_policy_three_shop_upgrades_to_empty_active_group_retaining_phase_window_and_account(
        self,
    ):
        profile = self.install()
        before = list(self.db.iterdump())
        selection = enable(self.ref, skip_basic=True, phase=3)
        prepared = bootstrap_override(self.ref, "static_data_get.bin", None)
        lines, items = records(decode(prepared))
        war = json.loads(items["guildwar"][1])
        war["ShopSet"] = json.loads(records(decode(self.original))[1]["guildwar"][1])["ShopSet"]
        raw = json.dumps(war)
        at = items["guildwar"][0]
        lines[at + 1], lines[at + 3] = raw + "\n", digest(raw.encode()) + "\n"
        old_checksum = digest(b"synthetic-before-empty-shop")
        at = items["__checksum__"][0]
        lines[at + 1] = old_checksum + "\n"
        lines[at + 3] = digest(old_checksum.encode()) + "\n"
        old_body = compress("".join(lines).encode())
        legacy = dict(
            selection,
            overlay_policy=3,
            static_data_sha256=hashlib.sha256(old_body).hexdigest(),
            static_data_checksum=old_checksum,
        )
        (self.root / f"guild_war_static_{legacy['static_data_sha256']}.bin").write_bytes(old_body)
        (self.root / SELECTION).write_text(json.dumps(legacy))
        self.assertEqual(load_selection(self.ref)["overlay_policy"], 3)
        update = json.loads(
            bootstrap_override(self.ref, "static_data_check.bin", {"Checksum": old_checksum})
        )
        self.assertFalse(update["UpToDate"])
        current = load_selection(self.ref)
        self.assertEqual(current["overlay_policy"], OVERLAY_POLICY)
        self.assertEqual(current["phase"], 3)
        self.assertTrue(current["skip_basic"])
        self.assertEqual(current["period"], selection["period"])
        actual = json.loads(
            records(decode(bootstrap_override(self.ref, "static_data_get.bin", None)))[1][
                "guildwar"
            ][1]
        )
        expected = copy.deepcopy(war)
        expected["ShopSet"] = [row for row in expected["ShopSet"] if row["GroupId"] != 4001]
        self.assertEqual(actual, expected)
        self.assertEqual(actual["ShopSet"], [war["ShopSet"][1]])
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_empty_shop_policy_rejects_malformed_source_groups_without_replacing_selection(self):
        enable(self.ref)
        before = (self.root / SELECTION).read_bytes()
        lines, items = records(decode(self.original))
        war = json.loads(items["guildwar"][1])
        for mutate in (
            lambda w: w["Seasons"][0].update(ShopGroupId=0),
            lambda w: w["Seasons"][0].update(ShopGroupId=True),
            lambda w: w["Seasons"][0].pop("ShopGroupId"),
            lambda w: w.update(ShopSet=None),
            lambda w: w["ShopSet"][0].update(GroupId="4001"),
        ):
            changed = copy.deepcopy(war)
            mutate(changed)
            rows = list(lines)
            raw = json.dumps(changed)
            at = items["guildwar"][0]
            rows[at + 1], rows[at + 3] = raw + "\n", digest(raw.encode()) + "\n"
            with self.assertRaises(ValueError):
                enable(self.ref, source=compress("".join(rows).encode()))
            self.assertEqual((self.root / SELECTION).read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), self.original)

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
        expected["Constants"].update(
            PlayCoopCoinReward=0,
            PlayMultiCoinReward=0,
            PlayMultiBattleMedalReward=0,
            GetPointPlay=0,
        )
        expected["ShopSet"] = [row for row in expected["ShopSet"] if row["GroupId"] != 4001]
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
        expected["Constants"].update(
            PlayCoopCoinReward=0,
            PlayMultiCoinReward=0,
            PlayMultiBattleMedalReward=0,
            GetPointPlay=0,
        )
        expected["ShopSet"] = [row for row in expected["ShopSet"] if row["GroupId"] != 4001]
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
        expected["Constants"].update(
            PlayCoopCoinReward=0,
            PlayMultiCoinReward=0,
            PlayMultiBattleMedalReward=0,
            GetPointPlay=0,
        )
        self.assertEqual(new, expected)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        for invalid in (False, 2, 6):
            (self.root / SELECTION).write_text(json.dumps(dict(upgraded, overlay_policy=invalid)))
            with self.subTest(policy=invalid), self.assertRaises(ValueError):
                load_selection(self.ref)

    def test_fortress_defense_start_end_and_retries_follow_selected_grade_without_writes(self):
        profile = self.install()
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for castle, stage in ((1, 850060004), (2, 850060001)):
            selection = enable(self.ref, phase=4, defend_castle=castle)
            self.assertEqual(defense_stage_ids(self.ref, selection), {stage})
            expected = {
                "Cancelled": False,
                "GuildWarInfo": self.call({"isPartial": True})["GuildWarInfo"],
                "AddedItems": [],
            }
            for _ in range(2):
                self.assertEqual(
                    self.call({"stageId": stage, "presetId": 701}, START_MULTI),
                    {"GuildBuffIds": [], "CastleBuffIds": []},
                )
                self.assertEqual(
                    self.call(
                        {"stageId": stage, "damages": [MAX_DAMAGE], "additionalDamage": 0},
                        END_MULTI,
                    ),
                    expected,
                )
            self.assertEqual(self.call(None, ABANDON), {})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_fortress_defense_requires_active_owned_castle_matching_stage_and_owned_preset(self):
        body = {"stageId": 850060004, "presetId": 701}
        with self.assertRaises(PacketError):
            self.call(body, START_MULTI)
        self.install(False)
        with self.assertRaises(PacketError):
            self.call(body, START_MULTI)
        enable(self.ref, phase=4, defend_castle=1)
        before, writes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, START_MULTI)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        self.install()
        for phase in (1, 2, 3, 4):
            enable(self.ref, phase=phase)
            with self.subTest(phase=phase), self.assertRaises(PacketError):
                self.call(body, START_MULTI)
        enable(self.ref, phase=4, defend_castle=1)
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for invalid in (
            None,
            {},
            {"StageId": 850060004, "presetId": 701},
            dict(body, stageId=True),
            dict(body, presetId=True),
            dict(body, presetId=601),
            dict(body, presetId=702),
            dict(body, stageId=850030005),
            dict(body, stageId=850050077),
            dict(body, stageId=850060001),
            dict(body, castleId=2),
        ):
            with self.subTest(body=invalid), self.assertRaises(PacketError):
                self.call(invalid, START_MULTI)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        with self.db:
            self.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?)",
                (json.dumps({"Presets": [{"Id": 701, "Characters": [{"Id": 999999}]}]}),),
            )
        before, writes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, START_MULTI)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_fortress_result_rejects_bad_damages_wrong_stages_and_saved_progress(self):
        profile = self.install()
        enable(self.ref, phase=4, defend_castle=1)
        body = {"stageId": 850060004, "damages": [0], "additionalDamage": 0}
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for invalid in (
            None,
            {},
            dict(body, damages=[True]),
            dict(body, damages=[-1]),
            dict(body, damages=[0] * 5),
            dict(body, damages=[MAX_DAMAGE], additionalDamage=1),
            dict(body, additionalDamage=True),
            dict(body, additionalDamage=-1),
            dict(body, stageId=850060001),
            dict(body, stageId=850050077),
            dict(body, Rewards=[]),
        ):
            with self.subTest(body=invalid), self.assertRaises(PacketError):
                self.call(invalid, END_MULTI)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        changed = copy.deepcopy(profile)
        changed["UserRaid"]["GuildWar"] = {"SeasonId": 1, "PlayCount": 2}
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(changed),))
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for route, request_body in (
            (START_MULTI, {"stageId": 850060004, "presetId": 701}),
            (END_MULTI, body),
        ):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(request_body, route)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_fortress_defense_catalog_rejects_corrupt_ambiguous_or_foreign_stage_sets(self):
        selection = enable(self.ref, phase=4, defend_castle=1)
        path = self.root / f"guild_war_static_{selection['static_data_sha256']}.bin"
        source = path.read_bytes()
        self.assertEqual(defense_stage_ids(self.ref, selection), {850060004})
        path.write_bytes(source[:-1] + bytes([source[-1] ^ 1]))
        with self.assertRaises(ValueError):
            defense_stage_ids(self.ref, selection)
        lines, items = records(decode(source))
        war = json.loads(items["guildwar"][1])
        for alter in (
            lambda w: w["Seasons"][0].pop("CastleStageGroupId"),
            lambda w: w["CastleStageSet"].append(copy.deepcopy(w["CastleStageSet"][3])),
            lambda w: w["CastleStageSet"][3].update(GroupId=999),
            lambda w: w["CastleStageSet"][3].update(DefenceStageIds=[]),
            lambda w: w["CastleStageSet"][3].update(DefenceStageIds=[True]),
            lambda w: w["CastleStageSet"][3].update(DefenceStageIds=[850060004, 850060004]),
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
                defense_stage_ids(self.ref, selection)

    def test_policy4_upgrade_suppresses_multi_coins_and_medals_and_retains_owned_castle(self):
        profile = self.install()
        previous = enable(self.ref, phase=4, defend_castle=1, skip_basic=True)
        path = self.root / f"guild_war_static_{previous['static_data_sha256']}.bin"
        lines, items = records(decode(path.read_bytes()))
        war = json.loads(items["guildwar"][1])
        war["Constants"].update(
            PlayMultiCoinReward=10, PlayMultiBattleMedalReward=12, GetPointPlay=10
        )
        raw = json.dumps(war)
        lines[items["guildwar"][0] + 1] = raw + "\n"
        lines[items["guildwar"][0] + 3] = digest(raw.encode()) + "\n"
        legacy_body = compress("".join(lines).encode())
        previous["static_data_sha256"] = hashlib.sha256(legacy_body).hexdigest()
        (self.root / f"guild_war_static_{previous['static_data_sha256']}.bin").write_bytes(
            legacy_body
        )
        previous["overlay_policy"] = 4
        previous["static_data_checksum"] = digest(b"synthetic-policy4")
        (self.root / SELECTION).write_text(json.dumps(previous))
        before, writes = list(self.db.iterdump()), self.db.total_changes
        checked = json.loads(
            bootstrap_override(
                self.ref, "static_data_check.bin", {"Checksum": previous["static_data_checksum"]}
            )
        )
        selection = load_selection(self.ref)
        self.assertFalse(checked["UpToDate"])
        self.assertEqual(selection["overlay_policy"], 5)
        self.assertEqual(
            (selection["phase"], selection["defend_castle"], selection["period"]),
            (4, 1, previous["period"]),
        )
        self.assertTrue(selection["skip_basic"])
        war = json.loads(
            records(decode(bootstrap_override(self.ref, "static_data_get.bin", None)))[1][
                "guildwar"
            ][1]
        )
        self.assertEqual(
            [
                war["Constants"][key]
                for key in (
                    "PlayCoopCoinReward",
                    "PlayMultiCoinReward",
                    "PlayMultiBattleMedalReward",
                    "GetPointPlay",
                )
            ],
            [0, 0, 0, 0],
        )
        self.assertEqual(war["Constants"]["SyntheticKeep"], 9)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

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

    def test_dispute_castles_use_only_active_deployment_and_keep_neutral_state_without_writes(self):
        for imported in (False, True):
            profile = self.install(imported)
            for phase in (3, 4):
                enable(self.ref, phase=phase)
                self.db.execute("PRAGMA query_only=ON")
                before, writes = list(self.db.iterdump()), self.db.total_changes
                expected = {
                    "CastleSimpleInfos": [
                        {
                            "CastleId": value,
                            "CaptureGuildId": 0,
                            "MarkingCount": 0,
                            "CaptureDays": 0,
                        }
                        for value in (1, 2)
                    ]
                }
                for _ in range(2):
                    self.assertEqual(self.call({"seasonId": 1}, CASTLES), expected)
                self.assertEqual(self.store.account.profile(), profile)
                self.assertEqual(list(self.db.iterdump()), before)
                self.assertEqual(self.db.total_changes, writes)
                self.db.execute("PRAGMA query_only=OFF")

    def test_native_castle_detail_returns_typed_neutral_history_for_each_dispute_castle(self):
        profile = self.install()
        for phase in (3, 4):
            enable(self.ref, phase=phase)
            self.db.execute("PRAGMA query_only=ON")
            before, writes = list(self.db.iterdump()), self.db.total_changes
            for value in (1, 2, 1):
                self.assertEqual(
                    self.call({"castleId": value}, CASTLE_DETAIL),
                    {
                        "CastleId": value,
                        "CaptureGuildId": 0,
                        "CaptureDays": 0,
                        "DefenseBuffIds": [],
                        "TodayBattleStatus": [],
                        "BattleHistory": {},
                        "NotExistCastleData": False,
                    },
                )
            self.assertEqual(self.store.account.profile(), profile)
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, writes)
            self.db.execute("PRAGMA query_only=OFF")

    def test_castle_details_reject_unknown_deployment_native_schema_and_non_dispute_phase(self):
        body = {"castleId": 1}
        with self.assertRaises(PacketError):
            self.call(body, CASTLE_DETAIL)
        self.install()
        with self.assertRaises(PacketError):
            self.call(body, CASTLE_DETAIL)
        for phase in (1, 2):
            enable(self.ref, phase=phase)
            with self.assertRaises(PacketError):
                self.call(body, CASTLE_DETAIL)
        enable(self.ref, phase=3)
        before = list(self.db.iterdump())
        for invalid in (
            None,
            {},
            {"CastleId": 1},
            {"castleId": True},
            {"castleId": 1.0},
            {"castleId": 0},
            {"castleId": -1},
            {"castleId": 101},
            {"castleId": 1, "seasonId": 1},
        ):
            with self.subTest(body=invalid), self.assertRaises(PacketError):
                self.call(invalid, CASTLE_DETAIL)
        self.now += timedelta(days=8)
        with self.assertRaises(PacketError):
            self.call(body, CASTLE_DETAIL)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_castle_reads_preserve_saved_war_progress_and_require_owned_guild(self):
        profile = self.install()
        enable(self.ref, phase=3)
        for alter in (
            lambda p: p.update(GuildMember=None),
            lambda p: p["UserRaid"].update(GuildWar={"SeasonId": 99, "GuildWarCoin": 100}),
        ):
            changed = copy.deepcopy(profile)
            alter(changed)
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(changed),))
            before, writes = list(self.db.iterdump()), self.db.total_changes
            for route, body in ((CASTLES, {"seasonId": 1}), (CASTLE_DETAIL, {"castleId": 1})):
                with self.subTest(route=route), self.assertRaises(PacketError):
                    self.call(body, route)
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, writes)

    def test_castle_catalog_rejects_digest_mismatch_missing_groups_and_ambiguous_spots(self):
        selection = enable(self.ref, phase=3)
        self.assertEqual(set(castle_specs(self.ref, selection)), {1, 2})
        path = self.root / f"guild_war_static_{selection['static_data_sha256']}.bin"
        source = path.read_bytes()
        path.write_bytes(source[:-1] + bytes([source[-1] ^ 1]))
        with self.assertRaises(ValueError):
            castle_specs(self.ref, selection)
        lines, items = records(decode(source))
        war = json.loads(items["guildwar"][1])
        for alter in (
            lambda w: w["Seasons"][0].pop("CastleDeployGroupId"),
            lambda w: w["Seasons"][0].update(CastleDeployGroupId=True),
            lambda w: w.update(CastleSpecs=[]),
            lambda w: w["CastleSpecs"].append(copy.deepcopy(w["CastleSpecs"][0])),
            lambda w: w["CastleSpecs"][0].update(Id=True),
            lambda w: w["CastleSpecs"][0].update(Grade=5),
            lambda w: w["CastleSpecs"][0].update(SpotId=99),
            lambda w: w["CastleSpecs"][1].update(SpotId=1),
            lambda w: w["CastleDeploySpots"].append(copy.deepcopy(w["CastleDeploySpots"][0])),
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
                castle_specs(self.ref, selection)

    def test_castle_catalog_cache_keeps_responses_isolated_and_decodes_matching_body_once(self):
        selection = enable(self.ref, phase=3)
        from guardian_tales import guild_war_static

        guild_war_static._castle_specs.cache_clear()
        with patch("guardian_tales.guild_war_static.decode", wraps=decode) as decoder:
            first = castle_specs(self.ref, selection)
            first[1]["Grade"] = 99
            first.pop(2)
            second = castle_specs(self.ref, selection)
            self.assertEqual(set(second), {1, 2})
            self.assertEqual(second[1]["Grade"], 1)
            self.assertEqual(decoder.call_count, 1)

    def test_selected_defense_castle_consistently_uses_owned_guild_without_persisting_a_capture(
        self,
    ):
        for imported in (False, True):
            profile = self.install(imported)
            enable(self.ref, phase=4, defend_castle=2)
            self.db.execute("PRAGMA query_only=ON")
            before, writes = list(self.db.iterdump()), self.db.total_changes
            for _ in range(2):
                self.assertEqual(
                    self.call({"isPartial": False})["GuildWarInfo"]["CapturedCastleId"], 2
                )
                rows = self.call({"seasonId": 1}, CASTLES)["CastleSimpleInfos"]
                self.assertEqual([v["CaptureGuildId"] for v in rows], [0, 7])
                self.assertTrue(all(v["CaptureDays"] == v["MarkingCount"] == 0 for v in rows))
                self.assertEqual(self.call({"castleId": 1}, CASTLE_DETAIL)["CaptureGuildId"], 0)
                detail = self.call({"castleId": 2}, CASTLE_DETAIL)
                self.assertEqual(detail["CaptureGuildId"], 7)
                self.assertEqual(detail["TodayBattleStatus"], [])
                self.assertEqual(detail["BattleHistory"], {})
                self.assertEqual(detail["DefenseBuffIds"], [])
                summary = self.call({"GuildId": 7}, GUILD_SUMMARY)["GuildSummary"]
                self.assertEqual(summary["Guild"]["Id"], 7)
                self.assertEqual(summary["GuildMembers"], [profile["GuildMember"]])
                self.assertIsNone(summary["Rank"])
                self.assertIsNone(summary["TotalDamage"])
            self.assertEqual(self.store.account.profile(), profile)
            self.assertEqual(list(self.db.iterdump()), before)
            self.assertEqual(self.db.total_changes, writes)
            self.db.execute("PRAGMA query_only=OFF")

    def test_defense_castle_selection_is_retained_on_refresh_and_cleared_explicitly_or_on_phase_change(
        self,
    ):
        selection = enable(self.ref, phase=4, defend_castle=1)
        self.assertEqual(enable(self.ref)["defend_castle"], 1)
        self.assertEqual(enable(self.ref)["period"], selection["period"])
        self.now += timedelta(days=8)
        refreshed = bootstrap_override(self.ref, "static_data_check.bin", {})
        self.assertFalse(json.loads(refreshed)["UpToDate"])
        self.assertEqual(load_selection(self.ref)["defend_castle"], 1)
        self.assertEqual(enable(self.ref, defend_castle=0)["defend_castle"], 0)
        enable(self.ref, defend_castle=1)
        self.assertEqual(enable(self.ref, phase=3)["defend_castle"], 0)
        self.assertEqual(enable(self.ref, phase=4)["defend_castle"], 0)

    def test_defense_castle_selector_rejects_wrong_phase_unknown_castles_and_bad_types_atomically(
        self,
    ):
        enable(self.ref, phase=4, defend_castle=1)
        saved = (self.root / SELECTION).read_bytes()
        for value in (True, 1.0, "1", -1, 0x80000000, 101, 999):
            with self.subTest(value=value), self.assertRaises(ValueError):
                enable(self.ref, defend_castle=value)
            self.assertEqual((self.root / SELECTION).read_bytes(), saved)
        for phase in (1, 2, 3):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                enable(self.ref, phase=phase, defend_castle=1)
            self.assertEqual((self.root / SELECTION).read_bytes(), saved)
        original = json.loads(saved)
        for changes in ({"defend_castle": True}, {"defend_castle": -1}, {"phase": 2}):
            (self.root / SELECTION).write_text(json.dumps(original | changes))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                load_selection(self.ref)

    def test_owned_castle_summary_rejects_foreign_guilds_disabled_trial_and_bad_native_parameters(
        self,
    ):
        with self.assertRaises(PacketError):
            self.call({"GuildId": 7}, GUILD_SUMMARY)
        profile = self.install()
        enable(self.ref, phase=4)
        with self.assertRaises(PacketError):
            self.call({"GuildId": 7}, GUILD_SUMMARY)
        enable(self.ref, defend_castle=1)
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for body in (
            None,
            {},
            {"guildId": 7},
            {"GuildId": True},
            {"GuildId": 8},
            {"GuildId": 7, "SeasonId": 1},
        ):
            with self.subTest(body=body), self.assertRaises(PacketError):
                self.call(body, GUILD_SUMMARY)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
        for alter in (
            lambda p: p.update(GuildMember=None),
            lambda p: p["UserRaid"].update(GuildWar={"SeasonId": 1, "CapturedCastleId": 2}),
        ):
            changed = copy.deepcopy(profile)
            alter(changed)
            with self.db:
                self.db.execute("UPDATE local_account SET profile=?", (json.dumps(changed),))
            saved, writes = list(self.db.iterdump()), self.db.total_changes
            with self.assertRaises(PacketError):
                self.call({"GuildId": 7}, GUILD_SUMMARY)
            self.assertEqual(list(self.db.iterdump()), saved)
            self.assertEqual(self.db.total_changes, writes)

    def test_defense_castle_command_reports_explicit_mock_and_neutral_reset(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main(
                [
                    "enable",
                    "--phase",
                    "multi-defense",
                    "--defend-castle",
                    "2",
                    "--reference-dir",
                    str(self.root),
                ]
            )
        result = json.loads(output.getvalue())
        self.assertEqual(result["local_defense_castle"], 2)
        self.assertEqual(result["phase"], 4)
        output = io.StringIO()
        with redirect_stdout(output):
            main(["enable", "--defend-castle", "0", "--reference-dir", str(self.root)])
        self.assertEqual(json.loads(output.getvalue())["local_defense_castle"], 0)

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
        self.assertEqual(cooperative_stage_ids(self.ref, selection), {850030005, 850040001})
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

    def test_cooperative_catalog_reuses_decoding_across_battles_without_sharing_mutable_results(
        self,
    ):
        from guardian_tales import guild_war_static

        profile = self.install()
        selection = enable(self.ref, phase=2)
        guild_war_static._cooperative_stage_ids.cache_clear()
        self.addCleanup(guild_war_static._cooperative_stage_ids.cache_clear)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        with patch("guardian_tales.guild_war_static.decode", wraps=decode) as decoder:
            stages = cooperative_stage_ids(self.ref, selection)
            stages.clear()
            stages.add(850010002)
            for _ in range(3):
                self.assertEqual(self.call({"stageId": 850040001, "presetId": 701}, START_COOP), {})
                self.assertFalse(
                    self.call(
                        {"stageId": 850040001, "damages": [0], "additionalDamage": 0}, END_COOP
                    )["Cancelled"]
                )
            self.assertEqual(cooperative_stage_ids(self.ref, selection), {850030005, 850040001})
            with self.assertRaises(PacketError):
                self.call({"stageId": 850010002, "presetId": 701}, START_COOP)
            self.assertEqual(decoder.call_count, 1)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_cooperative_catalog_refreshes_for_new_content_and_validates_season_on_cache_hits(self):
        from guardian_tales import guild_war_static

        selection = enable(self.ref)
        guild_war_static._cooperative_stage_ids.cache_clear()
        self.addCleanup(guild_war_static._cooperative_stage_ids.cache_clear)
        expected = {850030005, 850040001}
        self.assertEqual(cooperative_stage_ids(self.ref, selection), expected)
        with self.assertRaises(ValueError):
            cooperative_stage_ids(self.ref, dict(selection, season_id=2))
        path = self.root / f"guild_war_static_{selection['static_data_sha256']}.bin"
        lines, items = records(decode(path.read_bytes()))
        war = json.loads(items["guildwar"][1])
        war["CastleStageSet"][1]["DefenceStageIds"] = [850040002]
        raw = json.dumps(war)
        at = items["guildwar"][0]
        lines[at + 1], lines[at + 3] = raw + "\n", digest(raw.encode()) + "\n"
        body = compress("".join(lines).encode())
        changed = dict(selection, static_data_sha256=hashlib.sha256(body).hexdigest())
        (self.root / f"guild_war_static_{changed['static_data_sha256']}.bin").write_bytes(body)
        self.assertEqual(cooperative_stage_ids(self.ref, changed), {850030005, 850040002})
        self.assertEqual(cooperative_stage_ids(self.ref, selection), expected)

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

    def test_native_defense_ranking_view_is_empty_without_guild_progress_rewards_or_database_writes(
        self,
    ):
        profile = self.install()
        enable(self.ref, phase=3)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for _ in range(2):
            self.assertEqual(
                self.call({"seasonId": 1}, RANKING),
                {"CoopDefenseMyGuildRank": 0, "CoopDefenseTopRanking": []},
            )
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_ranking_requires_authenticated_enabled_trial_and_exact_known_native_season(self):
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, RANKING)
        self.install(False)
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, RANKING)
        enable(self.ref)
        self.assertEqual(
            self.call({"seasonId": 1}, RANKING),
            {"CoopDefenseMyGuildRank": 0, "CoopDefenseTopRanking": []},
        )
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
                self.call(body, RANKING)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_native_guild_coin_ranking_is_an_empty_array_without_settlement_rewards_or_profile_writes(
        self,
    ):
        profile = self.install()
        enable(self.ref, phase=3)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        for _ in range(2):
            self.assertEqual(self.call({"seasonId": 1}, COIN_RANKING), {"GuildCoinRanking": []})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)

    def test_coin_ranking_requires_authenticated_enabled_trial_and_exact_native_season(self):
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, COIN_RANKING)
        self.install(False)
        with self.assertRaises(PacketError):
            self.call({"seasonId": 1}, COIN_RANKING)
        enable(self.ref)
        self.assertEqual(self.call({"seasonId": 1}, COIN_RANKING), {"GuildCoinRanking": []})
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
                self.call(body, COIN_RANKING)
        self.assertEqual(list(self.db.iterdump()), before)

    def test_cli_phase_choice_uses_native_values_and_survives_recomposition_without_account_changes(
        self,
    ):
        profile = self.install()
        before = list(self.db.iterdump())
        first_period = None
        for name, phase in PHASES.items():
            out = io.StringIO()
            with redirect_stdout(out):
                main(["enable", "--skip-basic", "--phase", name, "--reference-dir", str(self.root)])
            status = json.loads(out.getvalue())
            self.assertEqual((status["phase"], status["phase_name"]), (phase, name))
            self.assertEqual(self.call({"isPartial": False})["GuildWarInfo"]["Phase"], phase)
            self.assertTrue(load_selection(self.ref)["skip_basic"])
            first_period = first_period or status["period"]
            self.assertEqual(status["period"], first_period)
        select_season(self.ref, 2)
        bootstrap_override(self.ref, "static_data_get.bin", None)
        current = load_selection(self.ref)
        self.assertEqual(current["phase"], 4)
        self.assertEqual(current["period"], first_period)
        self.assertTrue(current["skip_basic"])
        enable(self.ref)
        self.assertEqual(load_selection(self.ref)["phase"], 4)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_phase_selection_rejects_invalid_native_values_and_legacy_defaults_to_cooperative_offense(
        self,
    ):
        self.install()
        selection = enable(self.ref)
        path = self.root / SELECTION
        before = path.read_bytes()
        for phase in (False, True, 0, 5, "3", 1.5):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                enable(self.ref, phase=phase)
            self.assertEqual(path.read_bytes(), before)
            path.write_text(json.dumps(dict(selection, phase=phase)))
            with self.assertRaises(ValueError):
                load_selection(self.ref)
            path.write_bytes(before)
        selection.pop("phase")
        path.write_text(json.dumps(selection))
        self.assertEqual(self.call({"isPartial": True})["GuildWarInfo"]["Phase"], 1)
        self.assertEqual(enable(self.ref)["phase"], 1)

    def test_imported_multi_lobby_guide_acknowledgments_only_save_seen_flags_and_revision_once(
        self,
    ):
        profile = self.install()
        expected = copy.deepcopy(profile)
        for phase, ids in ((3, [2025, 2026]), (4, [2028, 2029])):
            enable(self.ref, phase=phase)
            expected["UserProgress"]["Tutorials"].extend(ids)
            expected["UserProgress"]["Cas"] += 1
            result = self.call({"tutorialIds": ids}, "/user/mark-tutorial")
            self.assertEqual(result, {"UserProgress": expected["UserProgress"]})
            self.assertEqual(self.store.account.profile(), expected)
            writes = self.db.total_changes
            self.assertEqual(self.call({"tutorialIds": ids}, "/user/mark-tutorial"), result)
            self.assertEqual(self.db.total_changes, writes)

    def test_multi_lobby_guides_require_matching_active_trial_and_keep_gameplay_ids_blocked(self):
        self.install()
        before = list(self.db.iterdump())
        with self.assertRaises(PacketError):
            self.call({"tutorialIds": [2026]}, "/user/mark-tutorial")
        enable(self.ref)
        with self.assertRaises(PacketError):
            self.call({"tutorialIds": [2026]}, "/user/mark-tutorial")
        enable(self.ref, phase=3)
        for ids in ([2029], [2026, 2028], [2026, 2019], [2026, 200], [2027], [2026, True]):
            with self.subTest(ids=ids), self.assertRaises(PacketError):
                self.call({"tutorialIds": ids}, "/user/mark-tutorial")
        self.assertEqual(list(self.db.iterdump()), before)

    def test_multi_phase_keeps_safe_reads_and_abandonment_but_rejects_cached_cooperative_battle_calls(
        self,
    ):
        profile = self.install()
        enable(self.ref, phase=3)
        self.db.execute("PRAGMA query_only=ON")
        before, writes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call({"isPartial": False})["GuildWarInfo"]["Phase"], 3)
        self.assertEqual(len(self.call({"seasonId": 1}, CASTLES)["CastleSimpleInfos"]), 2)
        self.assertEqual(self.call(None, ABANDON), {})
        for route, body in (
            (START_COOP, {"stageId": 850030005, "presetId": 701}),
            (END_COOP, {"stageId": 850030005, "damages": [0], "additionalDamage": 0}),
        ):
            with self.subTest(route=route), self.assertRaises(PacketError):
                self.call(body, route)
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, writes)
