# SPDX-License-Identifier: Apache-2.0
"""Supported acknowledgments from the pinned 3.57.0 public tutorial catalog.

The built-in help entries have no actions or conditions. An optional external
catalog allows other known UI acknowledgments after Inn is cleared. Recording
a tutorial flag does not execute its actions, award rewards or advance stages.
"""

# The observed Inn completion and subsequent world-map intro both require Inn's
# saved clear flag. Acknowledging them does not advance stages or grant rewards.
POST_INN_TUTORIALS = (200, 2019)


def catalog_tutorial_ids(references):
    if not (references.directory / "tutorial_catalog.json").is_file():
        return set()
    catalog = references.json("tutorial_catalog.json")
    ids = catalog.get("ids") if isinstance(catalog, dict) else None
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 10000
        or any(type(value) is not int or not 0 <= value <= 0x7FFFFFFF for value in ids)
        or len(ids) != len(set(ids))
    ):
        raise ValueError("Invalid external tutorial catalog")
    return set(ids)


PASSIVE_HELP_TUTORIALS = {
    1000: "Rift",
    1001: "Tower",
    1002: "CoopMain",
    1003: "Gacha",
    1004: "GuildMainPage",
    1005: "LimitBreak",
    1006: "KnowledgeCollection",
    1007: "MissionAchievements",
    1008: "FollowerPage",
    1009: "GuildRaidLobby",
    1010: "TrainingRoom",
    1011: "MasterArenaLobby",
    1013: "GuardianPass",
    1014: "SideStory",
    1015: "RoadmapEvent",
    1016: "BingoEvent",
    1017: "GiantGachaEventMain",
    1018: "LiveEvent",
    1019: "CoopRaidMain",
    1020: "ColosseumLobby",
    1027: "MarbleEventMain",
    1030: "LobbyVillageCommunityCenter",
    1034: "SpeedQuizEventUI",
    1035: "SpeedQuizEventRewardPopup",
    1036: "SingleGuildWarLobby",
    1037: "GuildWarCoopLobby",
    1038: "GuildWarMultiLobby",
    1039: "TurntableEvent",
    1040: "HeroGrowthEvent",
    1041: "SlimeJuiceMainLobby",
    1042: "SlimeJuiceFollowerPage",
    1044: "UnexploredExpeditionEventUI",
}
