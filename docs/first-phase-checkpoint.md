# Inn checkpoint — 2026-11-16

The unmodified Android 3.57.0 Google Play European client completed **Inn's main
clear path** against the local services with emulator Internet egress blocked.
This is the first campaign phase, not the whole first chapter. The prepared
laboratory stopped and restored its configuration after its 50-minute limit.

## Verified flow

| Step | Result observed in the APK |
|---|---|
| Open Inn | Entry screen, level-1 monsters and a 15-stamina unlock cost |
| Unlock and reenter | First unlock charged once; later entry was free after restart |
| Quest 27 | Started and advanced through checkpoints 1–4 |
| Purple coins | 13 collected out of 26 |
| Named pickups and chest | Shield, costume and glove chest accepted; 3/4 item markers |
| Monster reports | Ten known handles saved and deduplicated |
| Clear exit | Returned to world map; “Stage cleared!” displayed |
| First grade reward | 50 free gems saved once; shown after backend/APK restart |
| Knight tutorial | Level 1 → 2 accepted for 37 experience |
| Mission-book help | Tutorial 1007 acknowledged and saved |
| Beginner mission 0 | 300 free gems, 50 reserve stamina, three selectable summon tickets |
| Beginner mission 1 | 20 reserve stamina, 200 low awakening stones; reward notice displayed |

The first-clear grade and the beginner mission are separate rewards. The
existing lab completion was replayed once through the idempotent handler when
the grade reward was introduced. Repeating completion or mission claims does
not grant another reward.

## Saved local test state

These are the synthetic local account's last checked values, not a starting
profile that new repository users receive.

| Field | Last checked value |
|---|---|
| Inn stage ID / flags | `100010001` / `7` (opened, unlocked, cleared) |
| Active story quest | `27`, checkpoint `4`, still active |
| Knight | Level 2 displayed; 37 character experience saved |
| Free gems | 350 |
| Gold | 870 |
| Unspent hero experience | 753 |
| Reserve stamina | 95 |
| Purple coins | 13 |
| Inventory | Two starting weapons, shield, costume, gloves, three summon tickets and 200 low awakening stones |

Gold and experience per defeated monster use a provisional local rule of 87 gold
and 79 experience. Official rates, multipliers, random drops and battle
validation have not been reconstructed.

## Implemented contracts and limits

Campaign entry, early quest checkpoints, coins, known monster handles, three
named item receipts, the glove chest and the clear exit persist in SQLite.
Tutorial acknowledgments currently accept only 200 and 1007. Training accepts
only the starting knight's initial 37-experience upgrade. Beginner reward claims
accept mission 0 or mission 1 in separate batches. Other values and mixed mission
batches are rejected before changing the account.

Transactions and persistent receipts protect balances, inventory IDs, progress
and one-time rewards against retries. The automated suite has **59 passing
tests**, including rejection, restart and write-failure rollback cases. The
latest implementation passed [GitHub Actions](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/runs/43938613922).

## Contract map

These are the implemented limits of the observed requests, not a general game API.
The router requires local sign-in before these operations.

| Route | Main request fields | Current behavior |
|---|---|---|
| `/stage/get-stage-progresses` | `ChapterCode` | Seven first-chapter entries; native empty strings initialize progress |
| `/stage/start-stage` | `StageId` | Inn only; 15 stamina on first unlock, then free reentry |
| `/stage/start-quest` | `StageId`, `QuestId` | Starts quest 27 once |
| `/stage/progress-quest` | `StageId`, `QuestId`, `InnerProgress` | Sequential initial checkpoints; 1–4 exercised in the APK |
| `/stage/pick-stage-coins` | `StageId`, `Items` | Allowlisted purple-coin keys; overlapping batches deduplicated |
| `/stage/beat-monsters` | `StageId`, `MonsterHandleNames` | Known handles, provisional local drops, persistent receipts |
| `/stage/pick-stage-item` | `StageId`, `StageItemKey` | Shield, sword and costume with stable inventory receipts |
| `/stage/open-treasure` | `StageId`, `TreasureBoxKey` | Glove chest only; preserves opened-box progress |
| `/stage/end-stage` | `StageId`, `ExitName`, `IsClearExit`, `StageCustom` | Known clear exit, prerequisite checks and one 50-gem grade claim |
| `/user/mark-tutorial` | `tutorialIds` | IDs 200 and 1007; persistent acknowledgments |
| `/user/add-character-experience` | `Experiences` | Only `{"1":37}` for the initial knight tutorial |
| `/mission/claim-beginner-all` | `missionIds` | ID 0 or 1 in separate batches, with complete saved rewards |

The native stage-progress encoder writes version 2 stores: category IDs,
byte-indexed boolean bitmaps, signed 32-bit integer overrides and a trailing
`StonePieces` byte, currently zero. Implemented stores track coins (2), named
items (4), boxes (5) and monster handles (10). Star pieces and other custom state
are pending. Beginner `GuideClaimed` uses a separate base64 bit array.

## Resume priorities

1. Reopen the same prepared lab and back up its current SQLite account before
   testing more mutations. Keep the saved account; do not repeat account setup.
2. Verify that the level-2 knight, claim flags, inventory and balances reopen in
   the APK. They were saved before shutdown; the final two mission rewards have
   not yet been checked through a subsequent APK restart.
3. Implement the visible beginner **Use 10 Stamina** reward. Its claim button
   was visible at the end; no successful claim was recorded. Determine its
   exact ID, prerequisites and complete reward before adding it.
4. Complete Inn's optional collectibles and custom-state interactions, then
   implement the next story phase. Neither is established by the clear-path test.
5. Expand training, equipment and mission support using observed contracts and
   retry rules. Summoning and the other lobby systems remain unfinished.

This repository contains server source and tests. Game files, recovered metadata,
private captures, certificate keys, the saved database and machine-specific
emulator helpers remain outside Git. See [setup](setup.md),
[client integration](client-integration.md), [architecture](architecture.md) and
the detailed [verification status](status.md).
