# SPDX-License-Identifier: Apache-2.0
"""Native slot-position arrays reorder Orbital/Raid teams without changing identities."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from guardian_tales.bootstrap import BootstrapSession, GuestStore, read_json_body
from guardian_tales.packet_reader import parse_packet
from guardian_tales.preset_order import ROUTE, SLOT_COUNTS
from guardian_tales.presets import MAX_REVISION, current_group
from guardian_tales.protocol import Packet, PacketError, encode_packet
from guardian_tales.snapshots import import_snapshot, preserved_read
from tests.test_snapshots import synthetic_snapshot


class PresetReorderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("GT_TEST_TMP"))
        self.root = Path(self.temporary.name)
        snapshot = synthetic_snapshot()
        snapshot["profile"]["User"]["SelectedPresetId"] = {
            "InfiniteTower": 404,
            "GuildRaidAndConquest": 705,
            "Rift": 101,
            "GuildPunchKing": 1302,
        }
        self.initial_group = {
            "Cas": 8,
            "Presets": [
                {
                    "Id": ident,
                    "Name": "Synthetic team",
                    "Order": order,
                    "Characters": [{"Id": 1, "Weapon1": 1}],
                    "Retained": {"value": ident},
                }
                for ident, order in (
                    (101, 3),
                    (400, 10),
                    (401, 11),
                    (403, 8),
                    (404, 4),
                    (700, 0),
                    (705, 5),
                    (729, 9),
                    (1302, 6),
                )
            ],
        }
        snapshot["startup_reads"]["/preset/get-presets"]["value"][
            "UserPartyPreset2"
        ] = self.initial_group
        snapshot["startup_reads"]["/preset/get-presets"]["value"].update(
            UserCharacterListPreset={"Cas": 4, "Presets": []},
            UserMultiPartyPreset={"Cas": 3, "Presets": []},
            CoopExpeditionSlots=[],
        )
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(snapshot))
        self.source_bytes = self.source.read_bytes()
        self.state = self.root / "state"
        import_snapshot(self.source, self.state)
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session()

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def open_session(self, reconnect=False):
        self.store = GuestStore(self.db, self.root)
        self.session = BootstrapSession(self.store)
        self.call(
            {"AuthKind": 0, "AccessToken": "synthetic-only", "Reconnect": reconnect},
            "/auth/sign-in",
            1,
        )

    def call(self, body, route=ROUTE, sequence=70):
        packet = parse_packet(
            encode_packet(
                Packet(0, json.dumps(body).encode(), body_type=1, api=route, sequence_id=sequence)
            )
        )
        reply = self.session.handle(packet)
        self.assertEqual(reply.sequence_id, sequence)
        return read_json_body(parse_packet(encode_packet(reply)))

    def orders(self, mode, ids):
        values = [0] * SLOT_COUNTS[mode]
        base = 700 if mode == 18 else mode * 100
        for position, ident in enumerate(ids):
            values[ident - base] = position
        return {"PresetType": mode, "Order": values}

    def save_group(self, group):
        with self.db:
            self.db.execute(
                "INSERT INTO party_preset_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(group),),
            )

    def reject(self, body, sequence=70):
        before, changes = list(self.db.iterdump()), self.db.total_changes
        with self.assertRaises(PacketError):
            self.call(body, sequence=sequence)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_both_native_modes_change_only_target_order_and_group_revision(self):
        self.assertEqual(SLOT_COUNTS, {4: 5, 7: 30, 13: 7, 17: 15, 18: 30})
        raw = self.db.execute("SELECT profile FROM local_account").fetchone()[0]
        seed = self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0]
        original_read = preserved_read(self.db, "/preset/get-presets")
        for sequence, mode, ids in ((70, 7, [729, 700, 705]), (71, 4, [403, 401, 400, 404])):
            expected = current_group(self.db)
            for row in expected["Presets"]:
                if row["Id"] in ids:
                    row["Order"] = ids.index(row["Id"])
            expected["Cas"] += 1
            self.assertEqual(
                self.call(self.orders(mode, ids), sequence=sequence), {"UserPartyPreset2": expected}
            )
            self.assertEqual(current_group(self.db), expected)
            self.assertEqual(
                self.db.execute("SELECT profile FROM local_account").fetchone()[0], raw
            )
            reads = preserved_read(self.db, "/preset/get-presets")
            self.assertEqual(reads, dict(original_read, UserPartyPreset2=expected))
        self.assertEqual(
            self.db.execute("SELECT startup_reads FROM imported_account").fetchone()[0], seed
        )
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_tetis_roster_lifecycle_uses_its_own_resource_and_fifteen_slots(self):
        route = "/preset/set-character-list-preset"
        character = self.initial_group["Presets"][0]["Characters"][0]

        def save(slot, seq):
            payload = {
                "CharacterListPreset": {
                    "Id": slot,
                    "Name": "Tetis",
                    "Order": 999,
                    "Characters": [character],
                },
                "SetSelected": True,
            }
            return self.call(payload, route, seq)

        group = save(1700, 80)["UserCharacterListPreset"]
        self.assertEqual((group["Cas"], group["Presets"][0]["Id"]), (5, 1700))
        second = save(1714, 81)
        self.assertEqual(second["User"]["SelectedPresetId"]["RogueChess"], 1714)
        roster = self.call(self.orders(17, [1714, 1700]), sequence=82)["UserCharacterListPreset"]
        self.assertEqual([(p["Id"], p["Order"]) for p in roster["Presets"]], [(1700, 1), (1714, 0)])
        self.assertEqual(
            self.call({"PresetId": 1700}, "/preset/set-selected-preset", 83)["User"][
                "SelectedPresetId"
            ]["RogueChess"],
            1700,
        )
        self.open_session(reconnect=True)
        reads = self.call({}, "/preset/get-presets", 84)
        self.assertEqual(reads["UserCharacterListPreset"], roster)
        self.assertEqual(reads["UserPartyPreset2"], self.initial_group)
        deleted = self.call({"PresetId": 1700}, "/preset/delete-character-list-preset", 85)
        self.assertEqual(deleted["User"]["SelectedPresetId"]["RogueChess"], 0)
        self.assertEqual(deleted["UserCharacterListPreset"]["Presets"][0]["Id"], 1714)
        with self.assertRaises(PacketError):
            save(1715, 86)

    def test_top_bottom_up_down_permutations_keep_slot_ids_and_physical_array_order(self):
        sequence = 70
        for mode, ids in ((4, [400, 401, 403, 404]), (7, [700, 705, 729])):
            for ordered in (ids[::-1], ids[1:] + ids[:1], [ids[1], ids[0], *ids[2:]], ids):
                self.call(self.orders(mode, ordered), sequence=sequence)
                sequence += 1
                group = current_group(self.db)
                self.assertEqual(
                    [p["Id"] for p in group["Presets"]],
                    [p["Id"] for p in self.initial_group["Presets"]],
                )
                self.assertEqual(
                    [
                        p["Id"]
                        for p in sorted(
                            (p for p in group["Presets"] if p["Id"] in ids),
                            key=lambda p: p["Order"],
                        )
                    ],
                    ordered,
                )

    def test_retry_after_other_mode_recreation_selection_and_reopen_returns_latest_group(self):
        first = self.orders(7, [729, 700, 705])
        self.call(first)
        self.call(self.orders(4, [404, 403, 401, 400]), sequence=71)
        self.call({"PresetId": 705}, "/preset/delete-preset", 72)
        self.call(
            {
                "PartyPreset": {
                    "Id": 705,
                    "Name": "Recreated",
                    "Order": 999,
                    "Characters": [{"Id": 1}],
                },
                "SetSelected": True,
            },
            "/preset/set-presets",
            73,
        )
        self.call(self.orders(7, [705, 729, 700]), sequence=74)
        self.call({"PresetId": 700}, "/preset/set-selected-preset", 75)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        group = current_group(self.db)
        profile = self.store.account.profile()
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(first), {"UserPartyPreset2": group})
        self.assertEqual(self.store.account.profile(), profile)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_delete_and_select_after_reorder_use_original_ids_in_both_modes(self):
        for sequence, mode, ids, field in (
            (70, 4, [404, 403, 401, 400], "InfiniteTower"),
            (80, 7, [705, 729, 700], "GuildRaidAndConquest"),
        ):
            self.call(self.orders(mode, ids), sequence=sequence)
            self.call({"PresetId": ids[0]}, "/preset/set-selected-preset", sequence + 1)
            self.call({"PresetId": ids[0]}, "/preset/delete-preset", sequence + 2)
            group = current_group(self.db)
            self.assertNotIn(ids[0], [row["Id"] for row in group["Presets"]])
            self.assertEqual(self.store.account.profile()["User"]["SelectedPresetId"][field], 0)
            self.assertEqual(
                [row["Order"] for row in group["Presets"] if row["Id"] in ids[1:]],
                [ids.index(row["Id"]) for row in group["Presets"] if row["Id"] in ids[1:]],
            )

    def test_new_epoch_can_reuse_sequence_but_conflicting_receipt_cannot(self):
        self.call(self.orders(7, [729, 700, 705]))
        self.reject(self.orders(7, [705, 729, 700]))
        self.reject(self.orders(4, [400, 401, 403, 404]))
        self.open_session(False)
        self.call(self.orders(7, [705, 729, 700]))

    def test_identical_order_at_revision_ceiling_only_records_receipt_once(self):
        body = self.orders(7, [729, 700, 705])
        self.call(body)
        group = current_group(self.db)
        group["Cas"] = MAX_REVISION
        self.save_group(group)
        changes = self.db.total_changes
        self.call(body, sequence=71)
        self.assertEqual(self.db.total_changes, changes + 1)
        self.call(dict(reversed(list(body.items()))), sequence=71)
        self.assertEqual(self.db.total_changes, changes + 1)
        self.reject(self.orders(7, [700, 705, 729]), sequence=72)

    def test_invalid_envelope_modes_lengths_and_position_types_reject_without_writes(self):
        valid = self.orders(7, [729, 700, 705])
        for body in (
            None,
            {},
            [],
            True,
            {"PresetType": 7},
            {"Order": valid["Order"]},
            dict(valid, User={}),
            {"presetType": 7, "Order": valid["Order"]},
        ):
            self.reject(body)
        for mode in (None, True, 4.0, "7", 0, -1, 6, 8, 14, 0x80000000):
            self.reject(dict(valid, PresetType=mode))
        for values in (None, {}, "0", [], [0] * 5, [0] * 29, [0] * 31):
            self.reject(dict(valid, Order=values))
        for value in (None, True, -1, 1.5, "0", 30, 0x80000000):
            values = list(valid["Order"])
            values[5] = value
            self.reject(dict(valid, Order=values))
        for identity in (None, True, "", "x" * 201):
            before = list(self.db.iterdump())
            with self.assertRaises(ValueError):
                self.store.account.reorder_party_presets(valid, identity)
            self.assertEqual(list(self.db.iterdump()), before)

    def test_duplicate_missing_gapped_or_unknown_slot_positions_reject(self):
        for mode, ids in ((4, [404, 403, 401, 400]), (7, [705, 729, 700])):
            valid = self.orders(mode, ids)
            for slot, value in (
                (ids[0] - mode * 100, 1),
                (ids[-1] - mode * 100, 0),
                (2 if mode == 4 else 2, 1),
            ):
                body = copy.deepcopy(valid)
                body["Order"][slot] = value
                self.reject(body)

    def test_invalid_saved_ids_slots_orders_or_revision_do_not_get_repaired(self):
        for mutate in (
            lambda g: g.update(Cas=True),
            lambda g: g.update(Cas=-1),
            lambda g: g.update(Cas=MAX_REVISION + 1),
            lambda g: g["Presets"].append(copy.deepcopy(g["Presets"][6])),
            lambda g: g["Presets"][6].update(Id=730),
            lambda g: g["Presets"][6].update(Order=True),
            lambda g: g["Presets"][6].update(Order=-1),
            lambda g: g["Presets"][6].update(Order=999),
            lambda g: g["Presets"].append(None),
        ):
            group = copy.deepcopy(self.initial_group)
            mutate(group)
            self.save_group(group)
            self.reject(self.orders(7, [729, 700, 705]))

    def test_empty_mode_rejects_but_old_receipt_does_not_resurrect_deleted_teams(self):
        first = self.orders(7, [729, 700, 705])
        self.call(first)
        for sequence, ident in enumerate((700, 705, 729), 71):
            self.call({"PresetId": ident}, "/preset/delete-preset", sequence)
        group = current_group(self.db)
        changes = self.db.total_changes
        self.assertEqual(self.call(first), {"UserPartyPreset2": group})
        self.assertEqual(self.db.total_changes, changes)
        self.reject({"PresetType": 7, "Order": [0] * 30}, sequence=74)

    def test_receipt_failure_rolls_back_all_positions_and_group_revision(self):
        self.db.execute(
            "CREATE TEMP TRIGGER refuse_reorder BEFORE INSERT ON preset_reorder_requests BEGIN SELECT RAISE(ABORT,'synthetic refusal'); END"
        )
        before = list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):
            self.call(self.orders(7, [729, 700, 705]))
        self.assertEqual(list(self.db.iterdump()), before)

    def test_raw_profile_including_maximum_user_revision_is_never_written(self):
        profile = self.store.account.profile()
        profile["User"]["Cas"] = MAX_REVISION
        with self.db:
            self.db.execute("UPDATE local_account SET profile=?", (json.dumps(profile),))
        raw = self.db.execute("SELECT profile FROM local_account").fetchone()[0]
        self.call(self.orders(7, [729, 700, 705]))
        self.call(self.orders(4, [403, 404, 401, 400]), sequence=71)
        self.assertEqual(self.db.execute("SELECT profile FROM local_account").fetchone()[0], raw)

    def test_signin_and_completed_prologue_are_required(self):
        body = self.orders(7, [729, 700, 705])
        self.session.signed_in = False
        self.reject(body)
        with sqlite3.connect(":memory:") as db:
            account = GuestStore(db).account
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                account.reorder_party_presets(body, "unfinished")
            self.assertEqual(list(db.iterdump()), before)

    def test_guild_war_alias_updates_raid_orders_and_keeps_1800_block_untouched(self):
        group = current_group(self.db)
        group["Presets"].append({"Id": 1800, "Order": 17, "Characters": [], "Name": "Unrelated"})
        self.save_group(group)
        expected = copy.deepcopy(group)
        ordered = [729, 705, 700]
        for row in expected["Presets"]:
            if row["Id"] in ordered:
                row["Order"] = ordered.index(row["Id"])
        expected["Cas"] += 1
        raw = self.db.execute("SELECT profile FROM local_account").fetchone()[0]
        reply = self.call(self.orders(18, ordered))
        self.assertEqual(reply, {"UserPartyPreset2": expected})
        self.assertEqual(current_group(self.db), expected)
        self.assertEqual(self.db.execute("SELECT profile FROM local_account").fetchone()[0], raw)

    def test_guild_war_and_raid_share_current_order_with_no_duplicate_revision(self):
        ordered = [729, 705, 700]
        first = self.call(self.orders(7, ordered))
        revision = current_group(self.db)["Cas"]
        changes = self.db.total_changes
        self.assertEqual(self.call(self.orders(18, ordered), sequence=71), first)
        self.assertEqual(current_group(self.db)["Cas"], revision)
        self.assertEqual(self.db.total_changes, changes + 1)
        self.reject(self.orders(18, ordered))

    def test_guild_war_retry_after_raid_and_orbital_moves_survives_reopening(self):
        first = self.orders(18, [729, 705, 700])
        self.call(first)
        self.call(self.orders(7, [700, 729, 705]), sequence=71)
        self.call(self.orders(4, [404, 400, 403, 401]), sequence=72)
        self.db.close()
        self.db = sqlite3.connect(self.state / "server.sqlite3")
        self.open_session(True)
        group = current_group(self.db)
        before, changes = list(self.db.iterdump()), self.db.total_changes
        self.assertEqual(self.call(first), {"UserPartyPreset2": group})
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_guild_war_requires_30_raid_slots_instead_of_zero_or_1800_definitions(self):
        body = self.orders(18, [729, 705, 700])
        for values in ([], [0] * 5, [0] * 29, [0] * 31):
            self.reject(dict(body, Order=values))
        group = current_group(self.db)
        group["Presets"] = [row for row in group["Presets"] if not 700 <= row["Id"] < 800]
        group["Presets"].append({"Id": 1800, "Order": 0, "Characters": []})
        self.save_group(group)
        self.reject({"PresetType": 18, "Order": [0] * 30})

    def test_guild_war_move_keeps_selection_and_deletion_using_original_raid_ids(self):
        self.call(self.orders(18, [729, 705, 700]))
        self.call({"PresetId": 700}, "/preset/set-selected-preset", 71)
        self.call({"PresetId": 705}, "/preset/delete-preset", 72)
        group = current_group(self.db)
        self.assertEqual([p["Id"] for p in group["Presets"] if 700 <= p["Id"] < 800], [700, 729])
        selected = self.store.account.profile()["User"]["SelectedPresetId"]
        self.assertEqual(selected["GuildRaidAndConquest"], 700)
        self.assertEqual(selected["InfiniteTower"], 404)
