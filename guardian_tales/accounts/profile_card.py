# SPDX-License-Identifier: Apache-2.0
"""Read the single local user's profile card without changing saved state."""


def _number(value, label, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or not -0x80000000 <= value <= 0x7FFFFFFF:
        raise ValueError("Invalid saved profile-card " + label)
    return value


def read(account, request):
    if (
        not isinstance(request, dict)
        or set(request) != {"UserId"}
        or type(request["UserId"]) is not int
        or not 1 <= request["UserId"] <= 0x7FFFFFFF
    ):
        raise ValueError("Profile cards require one positive integer UserId")
    profile = account.profile()
    user, record, progress = (profile[k] for k in ("User", "UserRecord", "UserProgress"))
    if not isinstance(user, dict) or type(user.get("Id")) is not int:
        raise ValueError("Invalid saved profile-card user")
    if request["UserId"] != user["Id"]:
        raise ValueError("Only the saved local user's profile card is available")
    if not isinstance(record, dict) or not isinstance(progress, dict):
        raise ValueError("Invalid saved profile-card records")
    misc = record.get("Misc", {})
    tower = progress.get("TowerInfinity", {})
    if not isinstance(misc, dict) or not isinstance(tower, dict):
        raise ValueError("Invalid saved profile-card records")
    card = {
        "User": user,
        # The own-profile native callback replaces these with the current
        # representative avatar and device-local badge before rendering.
        "Avatar": None,
        "Badge": None,
        "TowerInfinityFloor": _number(tower.get("Floor"), "floor", nullable=True),
        # These separate social/decorative resources were not captured. This
        # explicit empty local view does not overwrite any profile section.
        "SelectedBoard": None,
        "AttachedStickers": [],
        "GuildName": None,
        "GuildRaidDamage": 0,
        "Scarecrow": [],
        "UnlockFriend": False,
        "PunchKingScore": None,
        "CoopExpeditionLike": None,
        "RogueChessHighScore": None,
    }
    for key in ("ArenaTrophy", "ArenaRank", "ColosseumTrophy", "ColosseumRank"):
        nullable = key.endswith("Rank")
        card[key] = _number(record.get(key, None if nullable else 0), key, nullable)
    for key in (
        "ChampionArenaHighestRank",
        "ChampionArenaHighestTrophy",
        "DeathMatchHighestRank",
        "DeathMatchHighestTrophy",
    ):
        card[key] = _number(misc.get(key), key, nullable=True)
    # Both keys are consumed directly by the native success callback. Empty
    # packs/stickers describe this view only; no ownership record is reset.
    return {"UserProfileCard": card, "UserStickerPacks": []}
