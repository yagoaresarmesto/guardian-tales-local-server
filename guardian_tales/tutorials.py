# SPDX-License-Identifier: Apache-2.0
"""Supported acknowledgments from the pinned 3.57.0 public tutorial catalog.

Each entry has a popup, no start/move scene, no actions, and no start/end
conditions. Recording a seen popup does not implement or unlock its game system.
"""

# The observed Inn completion and subsequent world-map intro both require Inn's
# saved clear flag. Acknowledging them does not advance stages or grant rewards.
POST_INN_TUTORIALS = (200, 2019)

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
