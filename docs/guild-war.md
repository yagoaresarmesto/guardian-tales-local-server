# Guild meteor entry and experimental Guild War activation

The pinned Android 3.57.0 client contains separate meteor and Guild War screens.
Meteor entry now loads a fresh local guild view. Guild War has an opt-in calendar
and menu-entry trial, with guarded cooperative entry and result acknowledgments.
Persistent damage/progression, competitive rankings, castle writes, purchases and rewards
remain unfinished.

## Meteor entry

`/guild-meteor/enter` accepts exactly Boolean `IsPartial`, including its native
capitalization. The success coroutine reads `GuildRaid`, integer array
`MeteorExcavation` and `AddedItems`; the shared resource handler applies UserRaid.
Native field types establish a list of MeteorStatus and a dictionary of user
excavation statuses. Empty collections use the client's untouched meteor defaults.

The external `guild_meteor_entry_catalog.json` has `client` equal to the pinned
snapshot identity, `fresh_local: true`, and `seasons`, each with positive `id`
and timezone-aware ISO `from`. IDs and dates must be distinct. The handler chooses
the latest started season, so a reconnect on the next season's opening changes
the fresh menu view. The private prepared catalog contains 91 matching public
seasons. Offsetless source calendar timestamps were normalized as UTC during
that external preparation; the server catalog requires explicit offsets.

Completed prologue and owned guild membership are required for fresh and imported
accounts. Existing saved meteor progression rejects instead of being reset.
The response supplies only the meteor-related UserRaid fields, a fresh GuildRaid
view and empty excavation/reward arrays. Pickaxes, other-mode state, inventory,
balances and the database remain unchanged. Excavation/refresh/pickaxe claims
remain unsupported. After a backend reload the user confirmed the APK menu loads;
the health counter also recorded a completed entry.

## Guild War commands

Use the same reference directory as the backend:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase multi-offense --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase coop-offense --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war status --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war disable --reference-dir local/client-data/reference
```

**Fully close and reopen the game after enabling or disabling.** Reconnect alone
retains cached static objects. Reload the backend once when installing the new
handlers. Keep the ordinary bridge and resource CDN running.

`--skip-basic` is an explicit optional trial policy: it empties only
`SiegeStageIds` and `DefenceStageIds` in the Single CastleStageSet referenced by
`Constants.SingleStageSetId`, in the derived response. Native IsSingleModeCleared
checks these two lists; it does not use the similarly named
`Constants.SingleClearedStageIds`. Empty trial lists waive those prerequisites. It
does not add stage clears or change UserProgress, and normal `enable` without
the flag restores the source prerequisite. Automatic recomposition retains the
chosen policy. The lab keeps this flag enabled while the basic-course button
is unavailable, including when switching trial phases.

`--phase` on `enable` selects a local native phase:

| Choice | Value | Lobby |
|---|---|---|
| `coop-offense` | 1 | Cooperative attack |
| `coop-defense` | 2 | Cooperative defense |
| `multi-offense` | 3 | Dispute attack |
| `multi-defense` | 4 | Dispute defense |

The choice persists in the selection and survives parent/calendar refresh. Omit
the flag to retain it; legacy selections without a phase use 1. Status reports
both its native value and command name. Change phases outside a battle and fully
reopen the game before entering the corresponding lobby. Cooperative start/end
calls from an old cached lobby reject when a Multi phase is selected, while safe
reads and abandonment remain available. This is an explicit trial selection, not
automatic season scheduling or a grant of completed phases.

Opening Dispute while the trial reported phase 1 caused an infinite transition
with no pending API request. Unity logged a SwitchExpressionException in
GuildWarMultiLobby.Begin, with unmatched value CoopOffense. Its native phase
switch accepts only 3 or 4; entry selects Coop for 1/2 and Multi for 3/4. After
phase 3, backend reload and a full game restart, the user confirmed Dispute opens.
The lab currently uses `multi-offense`; the cooperative command above returns to
the previously verified battle path. Castle lists remain empty and Multi combat
and results remain unfinished. Manual navigation to another phase's lobby still
requires selecting that phase first.

The next actual request acknowledged guide 2026 through `/user/mark-tutorial`.
Native MultiLobby.Begin selects guides 2025/2026 in phase 3 and 2028/2029 in phase
4 for guild-role-specific introductions. Matching tutorial2 groups 2025 and 2026
contain 145 and 95 presentation steps: narration, focus, illustrations, dimming,
blocking, waits and interaction. These do not grant rewards or complete battles.
Only these four additional guide IDs are accepted, with enabled/valid trial,
matching phase and owned-membership guards. Their acknowledgment saves only seen
flags and one UserProgress revision, with no retry writes. Gameplay and other
configured tutorial IDs remain blocked for imported accounts. The actual 2026
packet passed on an in-memory source-account clone with exactly those changes
and unchanged real source data. After backend reload and reconnect the user
confirmed the introduction completes without that error.

Activation prepares season 1 / calendar 5500001 as a seven-day UTC period. The
initial lab activation covers 2026-11-18 through 2026-11-25, with an exclusive end.
Native GuildWarSeason.IsValid checks that window. The source Global season was
dated in 2099. Native LobbyMain.SetGuildContentButton tries active Raid first;
the overlay makes all Global Raid periods inactive while Guild War is enabled.
It preserves their selection files and composes above the existing Raid and
Dungeon Kingdom Arena calendar preparation. The overlay changes Global calendars,
adds one local unlock rule, zeros the cooperative participation coin count,
empties the active season's shop group and optionally waives Single prerequisites.
Other shop groups, tables, modes and calendar services
retain their parent content. Disabling removes only the War selection file, so
the parent Raid/arena bootstrap resumes. The original static source is immutable.

The selection stores checksums, revision, parent digest, selected period and
`overlay_policy: 4`. Existing selections without a policy or at policy 3 remain
readable and are re-prepared at bootstrap, retaining their valid window, phase
and skip-basic choice.
Bootstrap also re-prepares the overlay if the parent changes or the period expires;
a parent change within the window retains the window. Prepared bodies are
immutable and digest checked. Static get/check responses share one checksum.
These commands do not open or migrate the account database or move global time.
Atomic publication retries only brief Windows sharing/lock violations, up to six
attempts over 0.75 seconds. Other permission errors fail immediately, and a
failed publication retains the prior complete file.

## Entry scope and evidence

The existing castle handler `EnterGuildWarLobby` calls `OpenGuildWarLobby`, checks
the season and invokes the War lobby coroutine. SingleGuildWarShortCut also
exists. No meteor or Raid endpoint is redirected, and no APK patch is installed.

The first APK trial displayed the localized fortress-assault prerequisite: finish
the basic course first. Confirm moved to Play > Others, but the course was absent.
Native metadata identifies `Oak.Feature.GuildWarSingle` as **126** and the Others
button as `SingleGuildWar`, dispatched through shortcut 54. The source
`unlockfeature` table has 125 rows and no rule 126. Activation now appends exactly
that local `Type: None` rule, with no rewards and Global version v3.57; other
services stay gated at v9.99. Existing feature rows remain equal. It does not mark
the basic stage or any other combat complete.

The optional `/user/claim-unlock-feature-rewards` request accepts only
`{"Feature":126}` while the trial is enabled. It returns a client-only copy of
the native Base64 unlock bitmap with bit 126 set and empty AddedItems. Every other
bit is retained, and the database is untouched. A full restart can therefore
require acknowledging the basic-course button again. Other unlock/reward IDs
remain unsupported. The actual source-profile check confirmed exactly that bit
change in the response and zero database writes. A second APK restart still did
not show the course. Read-only runtime inspection confirmed 126 registered
features and a feature-126 checker with open state 2, so missing calendar/data
alone no longer explains the absent button. The Others page visibly showed
Farm and Pasture plus empty slots. The prerequisite waiver is a separate route
for testing War entry; the individual course UI remains unresolved.

`/guild-war/enter` accepts exactly Boolean **`isPartial`**, with a lowercase i.
The native callback consumes GuildWarInfo and the shared UserRaid resource.
The trial provides typed empty progress collections and the selected native phase
(default 1, selecting the cooperative lobby). Saved Guild War progression rejects;
the fresh menu cannot overwrite it. Account state, assets, other-mode currencies,
clears, teams and revisions are retained without database writes. This trial
retains stage prerequisites by default and never claims completed combat. The phase, empty
progress and next-update/end values are local trial values, not captured official
state. The user confirmed the War menu starts after the passive-help fix below.

Four meteor and thirty-six War regressions cover native schemas, fresh/imported
accounts, membership/progress guards, retries/reconnect, rollover, reversible
calendar changes, parent composition, cache hashes, corrupt inputs and CLI use.
The actual meteor packet and both War cache hints passed through the session and
wire codec with the real source database opened read-only/query-only. No source
writes or profile differences occurred. The real composed War calendar check
covered 47 affected rows; all Raid periods were inactive, War was valid, and all
other parent rows/services/tables plus the original source were preserved, apart
from appending the single explicit no-reward feature rule, zeroing cooperative
participation coins, emptying the active shop group and the optional War
prerequisite waiver. The basic-course
button remains unresolved. With the corrected prerequisite waiver the APK
completed `/guild-war/enter` and began loading the cooperative screen, then
requested passive help acknowledgment 1037. Imported-account protection had
blocked that operation. Imported tutorial acknowledgment now permits only the
built-in passive help IDs, retaining blocks on gameplay/configured tutorial IDs.
It records the seen help and its UserProgress revision once; it does not clear
stages or deliver rewards. The real request passed on an in-memory source-account
clone with only those two changes and zero retry writes. Final APK help/menu
completion passed after reload: the user confirmed the mode starts. The next
observed request came from the Multi lobby:
`/guild-war/get-all-castle-simple-infos` with native integer `seasonId: 1`.
It now returns exactly `CastleSimpleInfos: []`, whose native type is
GuildWarCastleSimpleInfo[]. Authentication, enabled trial, season and membership
guards remain in place. The local view has no recovered other-guild captures or
markings. Real-account read-only request/retry checks passed with zero writes;
the user confirmed the castle-list fix passes and reported another error.

The next actual pending call was `/guild-war/start-coop-stage`, with integer
`stageId` and `presetId`. Native SendGuildWarStartCoopStage supplies those exact
keys. Its success callback directly invokes the local GuildWarStage creation
and LobbyToStage transition without reading response fields. The local handler
therefore acknowledges with `{}` after checking the active trial, membership,
preserved-progress guard, digest-verified prepared static data and the owned
700-series Raid/Conquest preset, including its characters/equipment. Allowed
stage IDs come only from the matching season's cooperative CastleStageSet group;
Single, Multi and other-season sets do not qualify. Existing captured presets
are required. It does not save a preset selection, consume an attempt or resource,
lock characters, record a battle or deliver rewards. Retries and reconnects make
no writes. The real request for public stage 850030005 passed with its owned
preset through the wire codec twice on read-only/query-only source SQLite,
with zero writes and an unchanged profile. The API then recorded a completed
start, and the user confirmed the APK loads the phase.

The observed completion request `/guild-war/end-coop-stage/v2` contains exactly
integer `stageId`, a list `damages` of up to four nonnegative Int64 values, and
nonnegative Int64 `additionalDamage`; their combined sum must fit Int64. It uses
the same active-season, membership, saved-progress and cooperative-stage guards.
The native cooperative result callback refreshes GuildWarInfo and consumes
AddedItems and Cancelled. The local response supplies the unchanged fresh
GuildWarInfo, `Cancelled: false` and `AddedItems: []`. This acknowledges a free
trial result without damage validation, score/progression storage, attempts,
clears, character locks, resource consumption or rewards. Repetition is a no-op.
The native client can append its static participation reward to the result's
display list. The overlay now disables that decoration as described below.
The real pending completion and a repeat passed through the session/wire codec
with read-only/query-only source SQLite, zero writes and an unchanged profile.
The running API then completed that end request. The next failure was the
result-to-lobby refresh `/guild-war/get-battle-records`, accepting exactly native
integer `seasonId: 1`. Its SyncBattleRecordsInfo callback consumes three arrays:
`LatestBattleRecords` (GuildWarBattleRecord[]), `CoopDefenseInGuildRanking`
(RankingEntry[]) and `DailyBattleStatus` (GuildWarBattleStatus[]). The guarded
local handler returns all three empty without inventing a battle history or
rankings. The real request and repeat passed read-only with zero writes/profile
changes. The API also accepted this follow-up after reload, and read-only pending
inspection found no queued request. That alone did not establish a working result
screen: the user reported a freeze. Single and Multi combat/result handlers remain
unsupported.

## Cooperative result freeze

On 2026-11-19 a read-only window capture confirmed an incomplete result screen,
despite completed API calls and no queued request. Process-scoped Unity logs
reported `Cannot found a item spec by id: 21644` in ItemBox.OnItemUpdate,
GuildWarResult.SetBoss and its scene Begin. Native EndCoop appends item 21644 with
`Constants.PlayCoopCoinReward` (field offset 0x5c), originally 10. AddPlayReward
skips the append only when the count is below one. SetBoss renders that list, and
the missing spec aborts the scene before its result controls are initialized.
An empty server AddedItems list alone therefore does not avoid this exception.

The local overlay now changes only PlayCoopCoinReward to zero, preserving other
War constants and the immutable source. No substitute item spec, icon, reward or
profile mutation is introduced. One added regression exercises legacy-overlay
upgrade and malformed policy rejection; existing composition and reversal checks
also verify the exact constant change and source restoration on disable. The real
composed-table audit and read-only completion/retry checks passed with zero source
writes. The initial reward-fix overlay was prepared at policy 3, with its original period and
skip-basic choice. A backend reload and full game restart are required to replace
the cached static data and abandoned scene coroutine; reconnect cannot repair
that scene. After restart a read-only native probe confirmed PlayCoopCoinReward
loaded as zero while PlayCoopBattleMedalReward remained 12. The actual cooperative
attack replay displayed the complete result, per-character damage and Exit button.
The user confirmed Exit returns to the War menu, and a fresh window observation
verified that lobby with all three entries still available. The current process's
bounded log check contained no missing-21644 or GuildWarResult exception frames.
This verifies this cooperative attack result path, not Single/Multi combat or
persistent War score/progression/rewards.

## Empty exchange menu

The next exchange-center freeze had no pending API request. Unity logged a
NullReferenceException in GuildWarShopConstantsItem.Set, ItemUpdated and SetUI.
Native item rendering unconditionally calls ItemSpec.GetById(21644) to retrieve
the purchase-currency icon and throws if the spec is null. That spec was already
confirmed missing in this pinned snapshot's result screen.

The opt-in policy-4 overlay therefore removes only ShopSet rows whose GroupId
matches the selected season's ShopGroupId (4001). The real source has five such
offers. Other shop groups and the immutable parent source remain intact. Native
GetShopListBySeasonId filters the flat list, and SetUI explicitly handles zero
items, so an empty local catalog skips the invalid item renderer. No replacement
spec/icon, coin balance, purchase counter, account migration or reward is created.
Purchases and real exchange inventory remain unsupported.

Two regressions cover policy-3 upgrade with old offers, matching checksum refresh,
retained phase/window/waiver, unrelated-row preservation and malformed source
rejection without replacing the prior selection. The actual composed-table audit
and real read-only account entry/read/retry checks passed with zero source writes;
the prepared active group contains zero offers and keeps phase 3. Backend reload
and full game restart are required to discard the cached static list and frozen
scene. After restart a read-only native probe confirmed zero loaded shop rows,
and the current process's bounded log check contained no matching shop exception.
The user confirmed the empty shop opens and allows returning without a freeze.

## Empty ranking views

The observed `/guild-war/get-ranking` request accepts exactly integer `seasonId:
1`. Native SyncRankingInfo consumes CoopDefenseMyGuildRank (Int32) and
CoopDefenseTopRanking (RankingGuildEntry[]). The local response keeps the native
untouched rank value zero and returns an empty top list. No ranked defense result
or other guild placement is invented. The user confirmed the preceding screen
opens after reload/reconnect, then encountered the separate coin ranking request.

`/guild-war/get-guild-coin-ranking` accepts the same season schema. Native
SendGuildWarGetGuildCoinRanking consumes `GuildCoinRanking`, a
GuildWarCoinRewardRecord array. The local response supplies an empty array, with
no settlement records, generated points or reward/currency grant. After reload
and reconnect the user confirmed that view loads too.

Both reads share the enabled/valid trial, prologue, membership and preserved-war
guards. Four regressions cover fresh/imported authentication, exact native
capitalization/types, unsupported seasons, retries and query-only preservation.
Each actual pending request and repeat passed through the session/wire codec on
real read-only/query-only SQLite with zero writes or profile changes.

## Abandoning an unfinished stage

`/guild-war/abandon-stage` handles leaving a battle before its result. Native
SendGuildWarAbandonStage creates a parameterless packet; its coroutine yields
the request without reading response fields. The local handler accepts the native
empty body and null/empty-object aliases, returning `{}` after the enabled-season,
completed-prologue, owned-membership and preserved-progress checks used by entry.
The trial has no persisted active battle to refund or delete. Abandoning does not
record a clear, damage, attempt, cost, reward, character lock or profile revision.

Two regressions exercise native wire framing, fresh/imported account guards,
malformed parameters, repetition and reconnect with query-only SQLite. The real
source database also passed empty/null/object/repeat requests through the wire
codec with zero writes or profile changes. The running backend was reloaded;
after reconnect the user confirmed leaving the battle succeeds. No full game
restart or change to the saved Guild War activation is required for this handler.

Two additional atomic-file regressions cover transient Windows sharing locks,
bounded retries, preserved old output and immediate propagation of access denial.
