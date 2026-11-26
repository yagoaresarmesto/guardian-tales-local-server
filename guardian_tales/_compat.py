# SPDX-License-Identifier: Apache-2.0
"""Resolve historical flat module names within the guardian_tales package."""

import os
import sys
from importlib import import_module
from importlib.machinery import ModuleSpec

_TARGETS = {
    f"{__package__}.{name}": f"{__package__}.{group}.{name}"
    for group, names in {
        "accounts": (
            "account account_costs_static account_name my_room portrait_frame "
            "profile_badge profile_card representative_character snapshots"
        ),
        "administration": (
            "admin admin_festival admin_test_items andras_trial andras_trial_growth "
            "andras_trial_labels andras_trial_static andras_trial_training head_hunter "
            "head_hunter_static test_item_static"
        ),
        "campaigns": (
            "campaign campaign_cli campaign_complete completion discovery monsters story "
            "story_data story_handles story_interactions story_loot story_quests "
            "story_rewards story_unlocks story_world_pass tutorials"
        ),
        "content": "assets content_pack reference static_cache",
        "heroes": (
            "awakening_catalog characters hero_awakening hero_blessing hero_catalog "
            "hero_equipment hero_evolution hero_limit_break hero_myth hero_reset "
            "hero_stones imported_training training training_room"
        ),
        "inventory": (
            "cosmetic_items inventory_expansion item_extract item_lock item_sell items "
            "jewel_decompose jewel_socket jewel_upgrade merch_enhance mystery_evolution "
            "relic_options selection_box weapon_engrave weapon_enhance weapon_evolution "
            "weapon_limit_break weapon_option_lock weapon_options"
        ),
        "lobby_ui": (
            "lobby lobby_notice lobby_notice_art lobby_notice_details lobby_settings "
            "play_menu recommended_art"
        ),
        "modes": "classic_coop classic_coop_bundle colosseum",
        "modes.expedition": "expedition expedition_levels",
        "modes.guild": (
            "guild_menu guild_meteor guild_raid guild_war guild_war_static punchking "
            "punchking_static raid_custom raid_panel raid_static"
        ),
        "modes.kamazone": (
            "kamazone kamazone_aids kamazone_banner kamazone_battle "
            "kamazone_event_effects kamazone_events kamazone_legacy kamazone_loot "
            "kamazone_practice kamazone_preview kamazone_run kamazone_shelter "
            "kamazone_shop kamazone_silver kamazone_themes"
        ),
        "modes.orbital": "orbital orbital_boards orbital_levels",
        "modes.tetis": (
            "tetis tetis_art tetis_catalog tetis_map_trial tetis_presets tetis_progress "
            "tetis_sweep"
        ),
        "rewards": (
            "attendance beginner challenge_progress challenges festival_missions "
            "festival_shop hero_knowledge imported_hero_knowledge live_events missions "
            "passes stamina_purchase stamina_regen"
        ),
        "runtime": (
            "android_bridge bootstrap client_cert demo packet_reader platform probe "
            "protocol server service_control state_lock validation"
        ),
        "settlement": (
            "basecamp mastery mastery_reset village village_dispatch village_gift "
            "village_obstacle"
        ),
        "summons": (
            "summon_draw summon_payment summon_pickup summon_selection weapon_selection "
            "weapon_summon"
        ),
        "teams": "multi_presets party_members preset_order presets",
    }.items()
    for name in names.split()
}


class _AliasLoader:
    def __init__(self, target):
        self.target = target

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # Replace importlib's placeholder so both names share globals, classes and caches.
        sys.modules[module.__name__] = import_module(self.target)

    def get_code(self, fullname):
        # python -m uses get_code instead of exec_module. Run relative imports in the
        # target's own package and preserve normal command-line argument handling.
        return compile(
            "from runpy import run_module\n"
            f"globals().update(run_module({self.target!r}, run_name=__name__, alter_sys=True))",
            f"<{fullname}>",
            "exec",
        )


class _AliasFinder:
    def find_spec(self, fullname, target=None):
        canonical = _TARGETS.get(fullname)
        if canonical is not None:
            return ModuleSpec(fullname, _AliasLoader(canonical))
        return None


def install(package_path):
    # An absolute virtual path survives importlib.invalidate_caches(). Only this
    # package searches it, after its ordinary source directory.
    entry = os.path.join(os.path.abspath(package_path[0]), "_legacy_imports")
    sys.path_importer_cache[entry] = _AliasFinder()
    if entry not in package_path:
        package_path.append(entry)
