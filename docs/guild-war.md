# Guild meteor entry and experimental Guild War activation

The pinned Android 3.57.0 client contains separate meteor and Guild War screens.
Meteor entry now loads a fresh local guild view. Guild War has an opt-in calendar
and menu-entry trial, with guarded cooperative entry and result acknowledgments.
Persistent damage/progression, rankings, castle writes, purchases and rewards
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
chosen policy. The lab currently uses this flag to try the cooperative entry
while the basic-course button is unavailable.

Activation prepares season 1 / calendar 5500001 as a seven-day UTC period. The
initial lab activation covers 2026-11-18 through 2026-11-25, with an exclusive end.
Native GuildWarSeason.IsValid checks that window. The source Global season was
dated in 2099. Native LobbyMain.SetGuildContentButton tries active Raid first;
the overlay makes all Global Raid periods inactive while Guild War is enabled.
It preserves their selection files and composes above the existing Raid and
Dungeon Kingdom Arena calendar preparation. Apart from the calendar and one
local unlock rule and optional prerequisite waiver described below, tables,
modes and calendar services retain their parent
content. Disabling removes only the War selection file, so
the parent Raid/arena bootstrap resumes. The original static source is immutable.

The selection stores checksums, revision, parent digest and the selected period.
Bootstrap re-prepares the overlay if the parent changes or the period expires;
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
The trial provides typed empty progress collections and native phase 1, which
selects the cooperative lobby. Existing saved Guild War progression rejects;
the fresh menu cannot overwrite it. Account state, assets, other-mode currencies,
clears, teams and revisions are retained without database writes. This trial
retains stage prerequisites by default and never claims completed combat. The phase, empty
progress and next-update/end values are local trial values, not captured official
state. The user confirmed the War menu starts after the passive-help fix below.

Four meteor and twenty-two War regressions cover native schemas, fresh/imported
accounts, membership/progress guards, retries/reconnect, rollover, reversible
calendar changes, parent composition, cache hashes, corrupt inputs and CLI use.
The actual meteor packet and both War cache hints passed through the session and
wire codec with the real source database opened read-only/query-only. No source
writes or profile differences occurred. The real composed War calendar check
covered 47 affected rows; all Raid periods were inactive, War was valid, and all
other parent rows/services/tables plus the original source were preserved, apart
from appending the single explicit no-reward feature rule and the optional War
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
The native client appends its static participation reward to the result's display
list; that client-side decoration does not grant inventory in server SQLite.
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
inspection found no queued request. Visual confirmation of complete result/menu
return remains pending. Single and Multi combat/result handlers remain unsupported.

Two additional atomic-file regressions cover transient Windows sharing locks,
bounded retries, preserved old output and immediate propagation of access denial.
