# SPDX-License-Identifier: Apache-2.0
"""Inventory resources shared by the local dashboard's HTTP entry points."""

import sqlite3
from contextlib import closing
from functools import partial
from threading import Lock

from guardian_tales.raid_static import decode, records

from .account_details import AccountEditor
from .catalog import InventoryCatalog
from .equipment_grants import EquipmentGrants
from .equipment_options import EquipmentOptionEditor
from .hero_portraits import HeroPortraits
from .mastery import MasteryEditor
from .owned_copies import CopyProtection, CopyRemoval
from .preview import Sandbox
from .relic_grants import RelicGrants
from .relics import RelicEditor
from .stack_quantities import CONSUMABLES, StackQuantityEditor
from .weapon_progression import WeaponProgression


class InventoryApplication:
    def __init__(self, database, references):
        database = database.resolve()
        self.database = database
        self._sandbox = None
        self._sandbox_guard = Lock()
        body = references.read_bytes("static_data_get.bin")
        tables = records(decode(body))[1]
        self.hero_portraits = HeroPortraits(tables)
        progression = WeaponProgression(tables)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            self.catalog = InventoryCatalog(
                source,
                references,
                body,
                progression.thresholds,
                self.hero_portraits.name_keys,
                tables,
            )
        self.mastery = MasteryEditor(database, references)
        self.account_editor = AccountEditor(database, references, self.catalog, tables)
        self.relics = RelicEditor(database, self.catalog, tables)
        self.relic_grants = RelicGrants(database, self.catalog, self.relics.specs, tables)
        self.equipment = EquipmentOptionEditor(database, self.catalog, tables, progression)
        self.equipment_grants = EquipmentGrants(
            database, self.catalog, body, tables, self.equipment.specs
        )
        self.consumables = StackQuantityEditor(database, self.catalog, CONSUMABLES)
        self.listings = {
            "/api/inventory": self.preview_listing,
            "/api/game/account": self.account_editor.info,
            "/api/game/consumables": self.consumables.info,
            "/api/game/equipment": self.equipment.info,
            "/api/game/equipment/catalog": self.equipment_grants.info,
            "/api/game/mastery": self.mastery.info,
            "/api/game/relics": self.relics.info,
            "/api/game/relics/catalog": self.relic_grants.info,
        }
        self.edits = {
            "/api/lock": self.preview_change,
            "/api/game/account": self.account_editor.write,
            "/api/game/consumables": self.consumables.write,
            "/api/game/equipment": self.equipment.request,
            "/api/game/equipment/add": self.equipment_grants.write,
            "/api/game/equipment/delete": CopyRemoval(database, "ItemWeapons").write,
            "/api/game/equipment/lock": CopyProtection(database, "ItemWeapons", locked=True).write,
            "/api/game/equipment/unlock": CopyProtection(
                database, "ItemWeapons", locked=False
            ).write,
            "/api/game/equipment/roll": partial(self.equipment.request, roll=True),
            "/api/game/equipment/hammers": self.equipment.hammers.write,
            "/api/game/mastery": self.mastery.write,
            "/api/game/mastery/preview": self.mastery.preview,
            "/api/game/relics": self.relics.apply,
            "/api/game/relics/add": self.relic_grants.write,
            "/api/game/relics/lock": CopyProtection(
                database, "ItemMiscs", self.relics.specs, locked=True
            ).write,
            "/api/game/relics/unlock": CopyProtection(
                database, "ItemMiscs", self.relics.specs, locked=False
            ).write,
            "/api/game/relics/delete": CopyRemoval(database, "ItemMiscs", self.relics.specs).write,
        }

    def _preview(self):
        if self._sandbox is None:
            db = sqlite3.connect(":memory:", check_same_thread=False)
            try:
                with closing(
                    sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
                ) as source:
                    source.backup(db)
                self._sandbox = Sandbox(db, self.catalog.refs, self.catalog)
            except BaseException:
                db.close()
                raise
        return self._sandbox

    def preview_listing(self):
        with self._sandbox_guard:
            return self._preview().listing()

    def preview_change(self, payload):
        with self._sandbox_guard:
            return self._preview().change(payload)

    def close_preview(self):
        with self._sandbox_guard:
            if self._sandbox is not None:
                self._sandbox.db.close()
                self._sandbox = None
