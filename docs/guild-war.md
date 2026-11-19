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
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase multi-offense --attack-castle 21 --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase coop-offense --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase coop-defense --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase multi-defense --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase multi-defense --defend-castle 1 --reference-dir local/client-data/reference
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
The first Dispute trial used `multi-offense`; the cooperative command above returns to
the previously verified battle path. Dispute now exposes neutral selectable castles;
Multi attack/defense entry and exit are free local trials; persistent result
settlement remains unfinished. Manual navigation to another phase's lobby still
requires selecting that phase first.

The English Fortress tab also opens the Multi lobby. Switching there while
`coop-defense` (2) is selected reproduces the same native switch exception,
this time with CoopDefense, before any API request remains pending. Select
`multi-defense` (4) for that defense menu, or `multi-offense` (3) for its attack
menu, and fully close/reopen the game to recover the blocked transition. The
selector does not automatically follow navigation between Coop and Fortress.
The phase-4 castle list and all 40 details passed repeated wire checks against
read-only source SQLite without profile changes or writes.
After selecting phase 4 and fully restarting the game, the user confirmed the
Fortress tab loads. This verifies its menu, not Multi defense combat or results.

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
adds one local unlock rule, suppresses cooperative and Multi participation rewards,
empties the active season's shop group and optionally waives Single prerequisites.
Other shop groups, tables, modes and calendar services
retain their parent content. Disabling removes only the War selection file, so
the parent Raid/arena bootstrap resumes. The original static source is immutable.

The selection stores checksums, revision, parent digest, selected period and
`overlay_policy: 5`. Existing selections without a policy or at policy 3/4 remain
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

Four meteor and sixty-three War regressions cover native schemas, fresh/imported
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
It initially returned `CastleSimpleInfos: []`, whose native type is
GuildWarCastleSimpleInfo[]. Authentication, enabled trial, season and membership
guards remain in place. The local view has no recovered other-guild captures or
markings. Real-account read-only request/retry checks passed with zero writes;
the user confirmed the castle-list fix passes and reported another error.

## Selectable Dispute castles

The empty list let Dispute load but left its castle buttons inactive. In phases
3/4 the list now contains only the enabled season's native CastleSpecs deployment
group (1001: 40 castles across grades 1..4). Each GuildWarCastleSimpleInfo has
CastleId and neutral local CaptureGuildId, MarkingCount and CaptureDays values of
zero. Cooperative phases retain the empty list. No rival guild or capture is
created, and the underlying static response is unchanged.

`/guild-war/get-castle-detail-info` accepts exactly integer `castleId` from that
deployment, with the same active-trial, membership and preserved-progress guards
and a Dispute-phase requirement. The native callback reads CastleId,
CaptureGuildId, CaptureDays, DefenseBuffIds (Int32[]), TodayBattleStatus
(GuildWarCastleBattleDetail[]), BattleHistory (Int64-keyed dictionary of
GuildWarCastleBattleResult) and NotExistCastleData (Boolean). The local detail is
neutral, with empty buffs/status/history and NotExistCastleData false.

Six regressions cover fresh/imported preservation, native schemas, mismatched
phases/groups, corrupt or ambiguous catalogs and isolated immutable cache rows.
Every request verifies the prepared file digest; a bounded two-entry cache avoids
repeated static decompression. All 40 real-source castle details and list/retries
passed through the wire codec on read-only/query-only account SQLite with zero
writes and an unchanged profile. After backend reload and reentering Dispute,
the user confirmed a castle can be selected and its information opens. This
initially verified map/detail navigation. The free Multi combat trial is described
below; persistent captures remain unfinished. That map/detail fix did not require
a game restart or a new phase command.

## Local Fortress defense selection

`coop-defense` selects the first cooperative lobby. Defense of a castle in the
second Fortress/Dispute tab instead requires `multi-defense` and a locally owned
castle. Selecting phase 4 alone keeps the neutral map and does not select a
defense stage: native OnClickEnter chooses DefenceStageIds only when the selected
castle matches GuildWarInfo.CapturedCastleId. IsCaptureGuild separately compares
the detail's CaptureGuildId with the owned guild ID.

`guild-war enable --phase multi-defense --defend-castle 1` explicitly presents
native castle 1 as owned in the trial response. Keep `--skip-basic` enabled in
the lab as shown above. The selector accepts only a positive ID in the matching
season's deployment, or zero to restore the neutral map. Omission retains the
choice in phase 4, including calendar/parent refresh; choosing another phase
clears it. Legacy selections without the field stay neutral. Bad types, unknown
IDs and an explicit positive selection in another phase reject before publication.

Entry, the castle list and its detail agree on this client-only ownership. Other
castles remain neutral, with empty buffs, battle history and capture days. No
capture, clear, damage, guild points, reward or account revision is persisted.
Prepared static content retains its existing overlay scope. Every owned view
still checks authentication, active season, owned membership and preserved War
progression. Saved War progression cannot be replaced by the trial.

The owned-castle popup can request `/guild/get-guild-summary` with exact integer
GuildId. Only the trial's own guild is available. Its native GuildSummary holds
the existing local Guild and saved member, with nullable TotalDamage and Rank
left null; foreign guild summaries remain unsupported. This read grants nothing
and makes no database writes.

Five regressions cover fresh/imported state, consistent ownership, native summary
guards, CLI reset, invalid input, atomic rejection and refresh retention. The real
read-only source audit checked entry, all 40 details, list and owned summary
twice, with an unchanged profile and zero writes. After backend reload and full
game restart, the user confirmed the owned castle offers Defense Battle. This
verifies the defense selection UI. The guarded defense entry/exit below extends
this defense trial; the separate phase-3 siege trial is described below.

## Free selected-castle defense entry and exit

The observed `/guild-war/start-multi-stage` request uses integer stageId and
presetId; the actual stage was 850060004. Native StartMultiStageRoutine reads
GuildBuffIds and CastleBuffIds as Int32 arrays before starting the local stage.
Both arrays are empty in the trial. Entry requires phase 4, a selected owned
castle, a matching native stage and an owned captured 700-series preset with
owned characters/equipment. A fresh account without captured presets rejects.
Allowed stages come only from the season's CastleStageGroupId and the unique
MultiGradeN set matching the selected castle's Grade, using DefenceStageIds.
Siege, cooperative, other-grade and foreign stage lists do not qualify.

`/guild-war/end-multi-stage/v2` accepts stageId, up to four nonnegative Int64
damages and nonnegative Int64 additionalDamage, whose combined sum must fit.
The same phase/castle/stage guards apply. Its native callback consumes Cancelled,
GuildWarInfo and AddedItems. The response acknowledges the free local result
with Cancelled false, the unchanged trial view and no AddedItems. No capture,
damage, score, clear, attempt, character lock, resource or reward is persisted.
The existing parameterless abandon handler remains available.

Native completion also appends participation items locally. Policy 5 sets
PlayMultiCoinReward and PlayMultiBattleMedalReward to zero and retains the earlier
PlayCoopCoinReward suppression. A real defeat was accepted by the API but then
failed in GuildWarResult.SetBoss / ItemBox.OnItemUpdate on absent item 21661.
The callback actually reads GetPointPlay at offset 0xc4 for that medal, rather
than the named medal field at 0x68. Policy 5 therefore zeros GetPointPlay too.
Other constants, including PlayCoopBattleMedalReward, retain their source values.
The full source War-table audit matched exactly these overrides, the empty shop
and the optional basic-course waiver. The immutable source and real profile were
unchanged, with zero writes in query-only/read-only start/end/retry checks.
Existing policy-4 selections upgrade while retaining phase, owned castle, valid
window and waiver. Fully restart the game after this update; reconnect retains
the old native participation counts.

Five additional regressions cover grade-bound entry/exit, owned teams, malformed
native bodies, Int64 limits, preserved progress, corrupt or ambiguous catalogs
and policy-4 upgrade. The actual pending start passed the wire codec read-only;
after reload/restart the user confirmed the phase loads. The running API accepted
the real defeat completion before the visual-medal failure. After a full restart
and another battle, the user confirmed the complete result and menu return.
A read-only native probe confirmed all four suppressed counts are zero, with
PlayCoopBattleMedalReward retained at 12. The current process's bounded log had
no missing-21661 or GuildWarResult error frames. The user subsequently confirmed
the remaining listed scenarios, including victory, defense abandonment/reentry,
same-hero repeats, formation/preset changes and the four cooperative attack maps.
This additional coverage is user-reported; no separate native trace was collected
for each scenario.

## Fortress siege combat

`--phase multi-offense` now enables free local Siege Battle entry/exit on the
castle map. Its existing native Multi start/end APIs use the same request and
response schemas as defense. Native OnClickEnter chooses the selected castle
grade's SiegeStageIds in phase 3. The start callback consumes empty Int32 arrays
GuildBuffIds/CastleBuffIds; completion consumes Cancelled, GuildWarInfo and
AddedItems and uses the same policy-5 participation-reward suppression.

The server accepts only SiegeStageIds in the unique season CastleStageGroupId
set for grades present in the active castle deployment. Without a selected target,
the preserved season has 16 allowed stages, four per grade. Selecting a target
restricts combat to its grade's four stages. Missing/ambiguous sets, duplicates,
out-of-range IDs, other-season/group stages, cooperative stages and defense
stages reject. The native request contains stageId/presetId, without a castle ID;
this is a catalog-bound combat trial, not persistent target/capture settlement.
The map remains neutral, with no fabricated rival guild. Phase-4 defense still
requires its explicitly selected owned castle and matching defense stage.

An owned captured 700-series preset and its owned members/equipment are required.
The active trial, authentication, prologue, membership and preserved War-progress
guards apply. Start returns empty buff arrays. The bounded Int64 completion
returns Cancelled false, unchanged trial GuildWarInfo and empty AddedItems.
Neither call saves damage, captures, attempts, hero locks, resources or rewards;
the shared abandon handler remains available.

Five regressions cover all four siege choices for each synthetic deployed grade,
repeat/reconnect, wrong phases/stages/teams, preserved progress, corruption,
catalog ambiguity and bounded immutable caching. All 16 native source stages
passed repeated start/end/abandon wire checks on real read-only/query-only
SQLite, including zero damage and the Int64 boundary. No writes occurred; the
profile, immutable source static body and persisted selection were unchanged by
that check. Requests were inferred from the native contract. After reload/full
restart the user confirmed the menu opens but reported stage entry may be
unavailable. A read-only native probe found phase 3, IsBattleRound true and no
pending request. The user then confirmed the only visible blank bottom button
returns to the map, and that the window was opened from a blue castle.

### Selecting a local siege target

Read-only native inspection identified castle 21 in phase 3 with the combat round
active, no selected target (MarkedCastleId zero), isMarked false, no cooperative
prerequisite block and no season-end block. Native SetBattleUI selects the
`not_marked` button state in that case. `--attack-castle ID` now explicitly marks
one native castle as the local siege target, without fabricating a rival guild,
capturing a castle or saving guild/account progress. Entry supplies MarkedCastleId
and only that map row has MarkingCount 1. CaptureGuildId and CapturedCastleId stay
zero. The selected target's native grade restricts start/end to its SiegeStageIds.

For example, enable `multi-offense --attack-castle 21` using the full command
above. Fully close/reopen the game and select the marked castle. IDs 1/2/4/8 are
examples of the four source grades; 21 shares grade 1 with castle 1. Use
`--attack-castle 0` for the unmarked map. Omitting the flag in phase 3 retains the
target, including parent/calendar refresh; choosing another phase clears it.
A positive target in another phase, bad types or IDs outside the deployment
reject before publishing. Legacy selections without the key stay unmarked.
The defense selector remains independent and phase-4-only.

Four additional regressions cover consistent entry/map views, selected-grade
battle guards, no writes, refresh/reset/phase/legacy behavior, invalid input,
atomic rejection and CLI status. Repeated real-source read-only entry/map/detail
and all four target-21 stage start/end wire checks passed; another-grade stage
rejected. The profile, immutable source and persisted selection were unchanged
by the check. The backend was reloaded and target 21 selected for the APK trial.
After full restart the user confirmed the entry button appears and opens the
four-stage selection, then confirmed an attack stage loads and is playable.
The user then confirmed the result and return to the castle menu. The particular
victory/defeat outcome was not separately identified. The existing empty labels
in the castle popup remain unresolved.

## Remaining guild-information UI issues

The user reported an empty Guild Information view without a full game freeze.
No API request was pending. Unity reported NullReferenceException in
UISceneManager.LoadUIAsset while OpenGuildWarLogsRoutine was opening the window.
The same process also reported DateTime FormatException in GetLastPhaseInfo;
native code parses a cached LastGuildWarPhase date with DateTimeOffset.Parse.
The cache contained a date in month/day/year form after selecting English.
Their causal relationship is not established. No client preference was changed,
and the empty view remains unresolved while battle testing continues.

## Cooperative loading performance

After testing the defense variants, the user reported that cooperative defense
works but entering stages can pause briefly. A read-only source-account profile
identified repeated full-static-data decompression in cooperative stage
validation. Before the change, unprofiled start calls took 1,504-1,706 ms and end
calls took 1,490-1,770 ms on the prepared Windows host. That synchronous work also
delays other requests handled by the backend event loop.

Cooperative validation now keeps at most two immutable stage-ID sets, keyed by
the exact compressed body and season ID. Every request still reads the current
file and checks its SHA-256 digest before consulting the cache. A changed body
gets a new catalog; a different season still validates against that body. Public
callers receive separate mutable sets. No account-derived or result data is cached.

Seven-repeat read-only measurements against native defense stage 850040001 gave
median start/end handler times of 27.2/21.2 ms; session/packet round trips measured
27.8/21.8 ms. Source writes were zero and the profile was unchanged. These are
host-side measurements, excluding TLS, bridge transport and client asset loading.
The first catalog lookup after backend restart still took 1,478 ms; later lookups
had a 9.7 ms median. Repeated start/end calls, result isolation, content/season
changes and file tampering after cache warming have regression coverage. After
backend reload the user confirmed repeated cooperative entry/exit feels faster.
This is a qualitative APK observation, not a measured end-to-end loading time or
an in-combat frame-rate measurement. Castle-map and selected-castle defense
validation already use their own bounded caches; this change targets cooperative
attack/defense start and end calls.

## Cooperative stage entry and results

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
screen: the user reported a freeze. Single combat and persistent result settlement remain
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
This verifies this cooperative attack result path; separate Multi checks are
documented above. It does not establish Single combat or
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
