# Verification and remaining work

Status recorded on **2026-11-23**. The public source tree reorganizes the working
prototype; preserved game data is distributed separately as versioned Release
attachments. Test results and original-client observations have different scopes.

## Automated checks

The optional [Kama-ZONE selector](kamazone.md) lists/selects the three preserved
Global/EU seasons and restores their original calendar. Native inspection locates
the entry in the Events drawer and its reward-period visibility predicate.
Twenty-nine regressions cover scoped dates, expiry, content binding, no account
access, revision-safe restoration, atomic publication, Andras composition,
the optional CDN preview, read-only automatic entry and empty local rankings. The pack lacks its
historical banner PNGs; the CDN
can generate an original menu image in memory for the selected declared URL
when started with `--reference-dir`, without changing preserved files.
The first APK probe failed because Events can automatically load Kamazone before
showing the drawer. Its pending `/kamazonland/enter` request and native scene
loader establish the missing read contract. A follow-up supplies a read-only
idle lobby for the selected season, with a real mini-season ID and no saved
progress, inventory or balance changes. Challenges and gameplay remain
unsupported. The owner has now verified that Events loads Kama-ZONE and can
return to the main lobby with season 43 selected. Diagnostics never activate a
live season themselves.
The initial entry change passed 271 targeted Windows tests, Black (221 files), Ruff and
repository/link checks (281 files). A coherent account/XP copy passes all three
selections and restoration, retaining every main-account table, trial XP,
existing overlays and 52 original reference files, with zero source writes.
A follow-up coherent copy passes the captured entry request and both partial
flags for every Global season with zero database writes during entry, unchanged
trial XP and all 53 reference files (including the local selection) retained.
The entry response now reaches the APK, but its first load stalled on a
`JsonSerializationException`: `Benefits` must be an array. Resolving all native
field signatures also identifies `Nodes` as a list. The follow-up corrects both
JSON shapes and adds a complete outgoing field-type regression; 85 focused tests
pass alongside Black/Ruff and repository/link checks. A coherent account/XP copy
matches all outgoing fields to those signatures for six entry requests, with
zero entry/source writes and 53 unchanged source reference files. The successful
APK retry shows three successful entry reads and the declared banner served by
the CDN. That probe also exposed `/kamazonland/get-rankings`; a new read returns
the native JSON `Rankings` list empty, without account deltas, fake users/scores
or official-server access. It shares the entry authentication, prologue,
selection and content-binding guards. All 88 focused tests pass. The owner
confirms that the ranking popup opens and returns to the Kama-ZONE lobby for
season 43. A fresh successful ranking read appears with no new rejected or
unsupported operation during that check. Entry and empty ranking navigation
are APK verified; challenges, scored runs and rewards remain unimplemented.
All changes remain backend response data; game files are untouched.

Optional Kama-ZONE benefit practice adds a separate, content/season-bound local
settings file. Season 43's Strong Body (174) can be unlocked in outgoing data;
seasonal benefit prices become zero and points stay pinned at 4,000, including
during client-side edits. Native inspection confirms the Id-to-level save map,
Id/Level response list and local point subtraction. Choosing, clearing and
recent retry handling write no account/trial-XP data. Default previews remain
unchanged; disabling restores the parent static mode with a newer revision.
Actual APK benefit selection and pinned-point checks are pending.
All 287 targeted Windows tests pass, including twelve new practice regressions.
A coherent account/XP copy verifies the real seasonal definitions, free prices,
Strong Body's unchanged effects, native request/response types, saved selection,
clearing, recent replay protection and restoration. All other effective static
tables, main-account tables, trial XP and 53 original reference files remain
unchanged, with zero diagnostic source writes or live practice activation.

The main campaign backend was exercised against the preserved 3.57.0 tables.
A test guest reached all 412 stages and completed all 463 campaign quests using
simulated stage and checkpoint requests. Separate runs covered the 224 named
pickups, 205 chests, repeat clear requests and imported-account stage entry.
The completed-save command was verified on a SQLite copy and across all 39
chapter reads. In the Android client, Normal World 22 showed 100% and a
stage could be entered and exited. An in-game playthrough of every world
remains unverified.
See [main story and completed campaign testing](reference-data.md#main-story-and-completed-campaign-testing).

The Andras presentation follow-up selects Bianca's existing leader movie and
shared cast animation, retaining Eunha's gameplay controller, hit timing, damage,
ATK buffs and cooldowns. An Andras-only option/action alias leaves original Eunha
and Bianca actions intact. Its native index uses the alias and its payload keeps
the original Lua dispatch name, avoiding a request for a nonexistent script.
Three new regressions cover exact visual-only changes, native alias dispatch and
conflicting/missing content. All 143 targeted Windows tests pass; Black (205
files), Ruff and repository/link checks (264 files) pass. Discovery lists 1,140
tests. A coherent account/XP copy passes the new leader definitions, original
Eunha/Bianca record preservation, existing-script dispatch and Head Hunter/test-pin
composition, with unchanged main account/trial XP during projection, 52 unchanged
reference files, three unchanged checked resources and valid SQLite integrity.
Diagnostics write nothing to the source account. The matching preserved Bianca graph was inspected
read-only to identify its animation; no graph or original resource is edited.
The owner confirms Bianca's movie appears, but reports a missing hit animation.
The follow-up identifies a separate animated impact prefab in Bianca's preserved
graph and redirects the private action's explosion binding to it. The source
pool entry and prefab are checked read-only; the ATK-buff visual, damage,
cooldowns and hit sequence remain intact. Two additional tests cover the visual
binding/catalog preservation and missing/misbound prefab rejection. The hit
follow-up passes all 145 targeted Windows tests, Black/Ruff and repository/link
checks; discovery lists 1,142 tests. The coherent account/XP copy also passes,
retaining the pool catalog and ATK-buff visual, all 52 source reference files and
four checked original resources with zero diagnostic source writes. The hit
prefab still uses Eunha's target-position spawn and controller timing, so this
does not claim a full Bianca graph transplant. Actual APK hit verification is
pending. See the
[presentation and native dispatch contract](reference-data.md#activated-experimental-growth).

The optional [Head Hunter Myth command](head-hunter.md) adds a separate locked
level-150 copy with its own four-crystal 25% option, backed-up receipts and
targeted retirement. Original weapon, option, role and style definitions remain
intact at 20%. Native inspection supports the alternate exclusive weapon/hero
selection and existing role script's parameter lookup; an action alias selects
the separate option without replacing scripts. The optional English title
response also defines the alternate class's leader key in memory. Automated
checks and a coherent account/XP copy cover grant, retries, equip/original/copy,
removal and restoration of the exact parent static response. All 140 targeted
Windows tests pass, including 16 new weapon cases and existing Andras, test-pin,
equipment, asset, bootstrap, validation and import tests. Discovery lists 1,137
tests; Black (205 files), Ruff and indexed repository/link checks (264 files)
pass. All original
inventory and 52 reference files remain intact; SQLite integrity passes with
zero diagnostic writes to the source. Actual APK display, combat selection and
damage measurement are pending. No generated item has been granted to the
working account by these diagnostics.

The Hero-screen equipment follow-up implements five native individual routes:
weapons, accessories, cards, merch and relics. The captured failing request used
`/user/change-weapons`; native send methods and the card UI confirm the other
payloads and card slot numbering. Fourteen new equipment regressions cover
holder transfers, both card slots, clearing, type/ownership checks, atomic
rollback, no-ops, stale retries and registered test pins. An additional Andras
case verifies that equipping retains the saved base hero while projecting the
active Myth variant. These targeted cases pass. A coherent real account/XP copy
passes the captured request, all five routes, both card slots and active Andras
equipment projection. Only the profile and equipment receipt tables change;
inventory, assets, presets and development remain intact. All 52 source reference
files are unchanged, integrity passes and diagnostics write nothing to the source
account. The broader 520-case core/account/heroes/inventory/teams run found one
stale expected import-summary route list; the other 519 cases passed. Updating
that explicit expected list for the five newly enabled routes is followed by all
14 snapshot/import tests passing. Discovery lists 1,121 tests. Black (202 files),
Ruff and indexed repository/link checks (260 files) pass.
The owner confirms equipment changes and persistence after reopening. Read-only
inspection finds 14 successful equipment receipts across all five routes,
including six card changes, and 12 final slot differences from the backup. The
inventories, currencies, hero development, other user/profile fields, presets and
separate Andras trial XP remain intact. Integrity passes with no diagnostic
source writes or new API errors. See the
[request and persistence contract](reference-data.md#hero-equipment-changes).

The preceding full Windows regression run passed **1,090 tests**, including 26
regressions for the experimental Andras Myth view and isolated training, disabled
compatibility, owner/content binding, full and partial replies, other-owner
isolation, source/binary agreement, native block boundaries, no-op choices,
restoration and failed atomic publication. A coherent
account copy passed enable/project/disable with all 74 database tables unchanged.
Only the target hero's outgoing spec changed; all saved fields, original combat
and visual definitions, other hero records and 49 original reference files
stayed intact. Disabling restored the full original profile and static contents,
with matching get/check checksums and advancing revisions. Integrity passed with
zero diagnostic source writes. After activation and backend restart, the owner
confirmed that the lobby loads and Andras appears as Myth with her original
appearance, portrait, equipment and skills. A read-only audit found the stored
hero and all 71 gameplay tables unchanged; only login/epoch/counter metadata
changed and integrity passed. Two experience requests exposed the initial
deliberate training guard. The follow-up now permits free trial training in a
separate SQLite sidecar, with atomic XP/retry receipts and consistent virtual
user revisions. All 26 trial regressions pass, including cap enforcement,
retries/replays, transaction rollback, malformed/unsigned packets, partial
replies, restoration and isolation from later saved growth. Replaying the
captured 6,600,000-XP request on a coherent account copy reaches visible level
150 from 130, with all 74 main database tables and 50 reference files unchanged.
Retry, restoration and SQLite integrity pass with zero diagnostic source writes.
The owner confirms level 150 and persistence after reopening. Read-only inspection
finds two trial training receipts totaling 6,600,000 XP in the sidecar; the original
hero, XP, currencies and saved training counters remain intact. Ordinary preset
selection/edit and login metadata changes were retained. No new API errors were
observed and integrity passed. The owner reports a missing leader skill in the
variant; that and combat checks remain open. Black (198 files), Ruff
and indexed repository/link checks (256 source files) pass.
See the [Andras trial](reference-data.md#experimental-andras-myth-view).

A read-only [Myth compatibility review](reference-data.md#myth-compatibility-review)
found a matching existing snowflake Myth layout with 300 nodes versus Andras's
248: 46 extra statistical nodes and six special centers. Original circle
coordinates match; the six original connection changes attach the extra branch.
The layout/statistical pattern can be reused, but five special centers depend on
their template hero's ability implementation. Leader actions also require
compatible existing client scripts/graphs and localization, beyond Myth rank.
Neither the extra tree nor a leader action has been implemented by the review.

The follow-up activated-growth prototype now supplies Eunha's stock leader,
the 300-node snowflake tree and 52 projected open nodes. Its party center follows
Eunha's +50 per-mille (+5 percentage points) ranged-party increase. Normal/role
and weapon coefficients gain 10%; the chain gains 20% (300 to 360% DPS), and
Bitter Cold gains five percentage points of ATK/DEF and one second of duration.
All 34 trial regressions pass, including exact tuning, original-bit retention,
partial replies, all-table restoration, unchanged unrelated binary bytes, native
resource reuse and malformed/colliding contracts. A coherent real account/XP
copy passes complete projected-profile comparison, 248 original flags retained,
52 new flags open, get/check consistency, disable and re-enable. All 74 main
database tables, 50 original reference files and the XP sidecar remain unchanged;
integrity passes with zero diagnostic source writes. The full Windows growth
checkpoint passes **1,098 tests** in 614.945 seconds with no failures/errors.
The final cost/label refinements additionally pass all 34 targeted cases. Black
(199 files), Ruff and indexed repository/link checks (257 files) pass.
The owner's screenshot confirms level 150, original appearance, Myth state and
55% ranged-party bonus. Its `???` chain label led to a native-verified missing
`MythOptionId` UI link, now supplied. A numeric-suffix variant name also reuses
the original name localization. All 34 targeted cases pass after those changes
and the addition of stock cost definitions for inspecting open special centers.
The copy check still passes. The owner confirms the corrected chain label and
launching Eunha's leader while continuing to play. A read-only audit finds the
original hero development/mask, currencies, saved counters and XP sidecar intact;
integrity passes and no new API errors were observed. The numeric hero-name
correction is implemented without separate owner confirmation. The original
class's leader-title key remains untranslated; no controlled numerical combat
benchmark was recorded.
See the [growth scope and limitations](reference-data.md#activated-experimental-growth).

The custom English title follow-up initially passed static/copy tests but failed
the owner's APK check: the raw leader key still appeared after reopening.
Further native inspection located an explicit `strings-` exclusion in the API's
static-item iterator. Read-only client inspection found the original English
resource and decoded cache unchanged, explaining why the API-only table was
ignored. That ineffective API layer and compression dependency were removed.

The replacement generates an optional English CDN response in memory, retaining
all 171,554 original strings and adding only **Sovereign of Eternal Slaughter**.
It uses a private external content-bound key and the optional cryptography
dependency; no game key, resource or account is included in source. Forty-eight
Andras/CDN tests pass, covering native envelope round trips, original-record
preservation, pack/language/opt-in gates, unchanged database/resource files,
GET/HEAD, ETags, conditional requests, ranges, invalid-input 503s and exact
disable/re-enable restoration. An isolated HTTP server over the real resource
pack passes download/cache checks with a 5,877,216-byte response, while retaining
the original resource exactly. All **232 core/content/account tests** pass,
including 42 Andras cases; total discovery is 1,106. Black (200 files), Ruff and
indexed repository/link checks (258 files) pass. After restarting backend and CDN
with the explicit reference directory, the owner confirms the requested title
appears and other texts remain correct. Read-only inspection finds the exact
generated resource and decoded 171,555-entry table in the selected client's
normal caches. The original server resource still matches its manifest; the
original saved hero/awakening, currencies, counters and separate trial XP remain
intact. SQLite integrity passes with zero diagnostic source writes and no new
API errors. A fresh read-only client screenshot also confirms the corrected
Andras name and Cold Death label.
See the [private inputs and restoration scope](reference-data.md#optional-english-leader-title).

The enemy-level CLI now supports `set-level --all`, covering all 44 solo
Expedition stage definitions in the matching pack, including hidden, boss,
unexplored and archived event variants. It accepts visible levels 1 through 220
and translates them to zero-based standard levels. Six additional regressions
cover all-stage isolation, all 220 native experience-lookup round trips,
individual changes after a global setting, restoration to distinct originals,
atomic failure and compatibility with previous raw version-1 files. All
**138 campaign/core/content tests** pass; discovery lists 1,064 cases, without a
new full-suite run. The owner's earlier raw-130 trial displayed 131 and completed
the phase/map return; original-level restoration is now confirmed too.
A coherent source-account copy passed all 44 stages at the visible maximum
220 and full restoration. The entire original stage table and all other
effective table contents were preserved, all 74 account tables stayed intact,
and all 49 original reference files remained unchanged. Get/check checksums
matched, stage revisions advanced and integrity passed with zero diagnostic
source writes. Updated global/exact-visible-level APK checks are pending.

The initial fourteen regressions covered the per-stage Expedition enemy-level CLI,
level 130, source-table bounds, independent overrides, partial/full restoration,
advancing cache revisions, current get/check checksums, composition with existing
nickname/feature/test-pin overlays, malformed inputs and atomic-write failure.
All **132 campaign/core/content cases** passed at that checkpoint, with 1,058
discovered tests. No new full-suite run was performed. The native monster
preparation reads the stage's standard level and corresponding experience; the
preserved Global experience table has 220 rows, including level 130. On a
coherent account copy with the actual reference pack, setting level 130 changed
only the chosen stage's Global level. Restoration recovered the entire original
stage table, get/check checksums matched, and revisions advanced. All other
effective table contents stayed intact, including active test-pin definitions;
their outer overlay only advanced its expected revision. All 74 account tables
and all 48 source reference files remained unchanged, with zero diagnostic
source writes and valid SQLite integrity. The owner's original single-stage
APK trial and restoration are recorded above. See the
[enemy-level commands](reference-data.md#per-stage-enemy-levels).

The Expedition preset full Windows regression run passed **1,040 tests**, including 22 new
Expedition preset cases. The teams/Orbital union passes 137 cases. The actual
delete request and create/copy, rename, party edits, ordering and selection also
passed on a coherent copy of the current imported account. Deletion preserved
all 71 other preexisting tables, the imported seed, other preset resources and
all owned inventory/heroes; only the multi-party group and selected slot's user
revision changed. Delayed retries made no writes and did not delete a recreated
slot. The retained backup passed integrity checks with zero diagnostic source
writes. After restart, the owner confirmed deletion, saving, copying, naming,
member/gear edits, ordering and persistence across reopening, including a
separate two-slot copy/name/order check. The read-only snapshot recorded four
deletions and two saves across two request epochs, with no new preset errors.
Replaying those requests against the backup reproduced the full current profile
and both preset resources exactly. All 68 other gameplay tables stayed intact;
only normal login/epoch/counter metadata also changed. Old replay checks made
no writes and integrity passed. A separate type-9 reorder packet was not present
in that snapshot; its contract has automated/native/clone coverage alongside
the owner's UI report. See the
[multi-party preset contract](reference-data.md#expedition-multi-party-presets).

The separate Expedition result failure was reproduced approximately 20 seconds
before the countdown ended. Its native `/expedition/clear-stage/v2` request sent
`PlayTime` as an invariant TimeSpan string, while the handler required integer
ticks. The duration parser now accepts both forms with exact tick precision and
native range checks. Four new regressions cover early results, fractional
boundaries, malformed/overflowing inputs, existing result guards and zero writes.
All **91 campaign/core tests** passed after that change; its discovery listed
1,044 tests, without a new full-suite run. The actual result, equivalent ticks, repeated
result, start and exit passed on a query-only account copy with all 74 tables
intact, no source writes and valid SQLite integrity. After backend restart,
the live APK completed two clear-result requests without new Expedition errors.
A read-only audit found the full profile and all 71 gameplay tables unchanged;
only login/epoch/counter metadata changed. The owner confirmed that results
appear, returning to the map works and the account remains intact after
reopening. New stage unlocks and reward claims remain outside practice scope.

The Solo Expedition trial opens feature rules 31 and 110 for the Android 3.57.0
Global client. The archived data includes four areas, ten districts, the wave
tables, and the on-demand assets. A read-only copy of the imported save
passed map entry, stage start, kill reporting, scoring, ranking, and exit
requests using existing district progression.

After restarting the local backend, the user confirmed that the map, a stage,
and the timeout or defeat result opened in the APK. The live backend recorded
Expedition entry, district score, stage start, and stage exit. The separate
clear-result and leaderboard paths were exercised by packet tests.

Five Colosseum lobby tests cover the native `IsPartial` entry hint, opponent list,
personal ranking, parameterless manual refresh, and sign-in enforcement. The
menu requests also passed against a query-only copy of the imported save.
The user confirmed that the lobby opened and Refresh completed in the APK.
The running server recorded two successful refresh requests with the game still
connected. The opponent list is empty.

The optional Colosseum practice configuration projects a saved attack team into
three opponent cards. Native inspection found that the lobby expects at least
three opponents and three challenge counts before updating those cards. A
query-only copy of the imported save returned the three cards with all equipped
items and acknowledged two practice starts and results without writes.
The user confirmed the cards appeared. The live backend completed a practice
start and result. Each opponent receives the player's account-wide stat options,
including the assigned Guardian Mastery skills. The user confirmed that the
displayed DPS and Toughness matched with the same preset on both sides.

The defense editor uses separate requests for the team and grid positions.
The live client sent a full preset with calculated stats and saved both team
and formation. The handler retains the owned roster and gear references.
A detached account test verified that a refresh in the same backend session
returned the new team and positions for each practice opponent.
Attack position saves use a separate per-preset table. The live client saved
different attack and defense layouts while using the same team on both sides.

Defense Apply now expires the opponent cache. Native inspection found the lobby
checks this deadline once a second and requests a new list when it expires.
Replay on a read-only source save copy covered a start against the old card
before the automatic fetch and a start against the updated defense afterward.
The live backend recorded a defense save, a new opponent list request and a
completed battle with the manual Refresh count unchanged. The user confirmed
the newly applied team appeared in the fight.

Colosseum Ranking, Battle Record and Season Stats now have read-only empty
responses. Query-only packet checks passed against a copy of the imported save
for all three menus and the existing shop routes. The installed Colosseum table
defines 22 reward tiers, and all reward items have matching item definitions.
The user confirmed that Ranking, Battle Record, Season Stats, Shop and Rewards
all opened in the APK after reloading the backend.

Before the Colosseum changes, **993 tests passed on Windows Python 3.11**.
Tests are cataloged into 14 logical groups. `validate --list-groups` reports
discovered counts; repeated `--group` arguments select a union in original
discovery order. Existing files, shared fixture imports, direct unittest paths
and the default full CI run remain unchanged. An independent discovery audit
retained all 658 previous case IDs and their relative order, with six new runner
regressions. Group membership partitions every case exactly once; inventory plus
teams selects 246 unique cases. Catalog omissions, duplicates and undiscovered
modules fail explicitly. See [group usage and maintenance](../tests/README.md).

Fourteen Orbital deployment regressions cover `/tower-infinity/save-formation`,
exact four-slot/20-cell validation, original-account preservation, current-state
retry replies, unchanged layouts, signed-64 revision limits, null/missing legacy
formation, rollback, restart/reconnect and entry/exit/victory coexistence. The
actual request passed on an in-memory coherent account backup: only the legacy
positions and progress revision changed, all 66 other tables stayed intact,
retries made no writes, and current/next-floor entry remained authorized.
Native inspection confirmed the request and success callback, and read-only
inspection of the prepared UI found 20 deployment cells. The source account had
zero diagnostic writes and the retained backup passed SQLite integrity. After
backend restart, the owner confirmed repositioning, phase entry and formation
persistence after reopening. A read-only verification snapshot matched the full
profile to only the recorded deployment changes and progress revisions. Assets,
heroes and equipment remained intact. Three formation receipts, four new stage
starts and three exits were observed. One independent preset edit was replayed
on the backup and matched the current preset group exactly; other gameplay
tables stayed intact. Normal login/epoch/counter metadata also changed. No new
formation rejections or unsupported calls appeared, and integrity passed. See the
[formation contract](reference-data.md).

Twenty additional administration regressions cover the opt-in test-pin CLI,
coherent backups, idempotent grants/removal, original-account preservation,
ordinary sale, rollback, locking and static get/check composition with existing
mode/nickname overlays. A separate isolated copy of the current account passed
grant and targeted retirement, preserving all 65 other tables and the original
inventory with zero source writes. Native inspection supports the fixed base
DEF and optional ATK suboption. Actual APK appearance, equipping, combat effect
and persistence remain pending; no pin was added to the working account during
implementation. See the [test-pin guide](test-items.md).

Fifteen inventory-protection regressions cover `/item/lock` and `/item/unlock`,
whose native request uses `itemIndexes` inventory IDs. Only selected top-level
protection flags and one user revision change, with atomic receipts and current
state on delayed retries. Single/mixed/full batches, ownership guards, fresh and
imported accounts, restart persistence, independent option locks/proposals and
transaction rollback are covered. The actual captured unlock/reverse-lock and
all 2,080 owned item IDs passed on an in-memory source-account backup with zero
diagnostic source writes. After backend restart, the user confirmed locking,
unlocking and persistence across reopening the APK. Four saved receipts match
the final flags; the full current profile equals the pre-fix backup with only
those recorded protection changes and four user revisions. No new lock-route
rejections appeared and SQLite integrity passed. Extraction uses its separate
guarded removal path below. See the
[request and persistence contract](reference-data.md#inventory-item-protection).

Twenty-three no-gold sale regressions cover native `/item/sell` batches, partial
stacks, full removal, resource preservation, protected/in-use targets,
reconnect, canonical/delayed retries, proposal cleanup and atomic rollback.
The actual eight-item request passed on a saved-account memory backup with only
the requested removals and one user revision changed. All balances and other
items remained intact; retries made no writes and a new resale of removed IDs
rejected. The source connection was write-disabled and a coherent pre-sale
backup passed integrity checking. After backend restart, the user confirmed
multi-item sales, zero gold credit and removal persisting across APK reopening.
At the verification snapshot, eight sales removed 145 inventory rows, including
25-item batches. The full profile matches only those recorded sales and eight
user revisions applied to the backup. All assets, gold spending counters and
the inventory allocation counter are unchanged. Proposal cleanup matches only
depleted targets; no new sale-route errors appeared and SQLite integrity
passed. The client can still display a locally predicted gold notice; the
explicit server policy credits zero. The separate merchandise sale route remains
unfinished. See the [sale contract](reference-data.md#no-gold-batch-item-sales).

Fifteen equipment-extraction regressions cover native `/item/extract` batches,
zero Magic Metal/rewards, single-row rarity-4 eligibility, protected/in-use items,
atomic cleanup/receipts, canonical/stale/cross-route retries and preservation of
legacy sale records. The real two-item request passed on a saved-account memory
backup: only its selected removals and one revision changed, all assets and the
imported seed were preserved, and both its retry and all eight existing sale
receipts returned current inventory with no writes. New extraction of removed
IDs rejected without changes. A coherent pre-extraction backup passed integrity
checking with zero diagnostic source writes. After backend restart, the user
confirmed multi-item extraction, zero Magic Metal credit and removal persisting
after reopening the APK. At the verification snapshot, two batches removed four
equipment rows. The complete profile matches only those removals and two user
revisions applied to the backup; all assets, Magic Metal spending counters and
the allocation counter are unchanged. Existing sale receipts remain intact,
proposal cleanup matches only depleted targets, no new extraction-route errors
appeared and SQLite integrity passed. The existing matching enhancement catalog
supplies eligibility; no new content or
save import is needed. Its native notice may display predicted Magic Metal,
while the persisted balance receives zero. See the
[extraction contract](reference-data.md#equipment-extraction-without-magic-metal).

Equipped-item removal now clears only nullable character fields pointing to
fully removed inventory IDs. Partial stacks retain their assignments; unrelated
gear/progress and later replacements on a delayed retry are preserved. Presets,
Training Room slots, `EquipCostumes`, locked and socketed items remain protected.
Five additional regressions and updated sale/extraction tests cover atomic slot
cleanup and rejection/rollback. The native 25-item sale batch, including one
equipped weapon, passed on an in-memory source-account backup with exactly its
selected removals, one cleared slot and one revision; other profile data stayed
unchanged with zero source writes. A verified coherent backup was retained.
The user confirmed equipped-item sale, an empty slot, zero gold and persistence
after reopening the APK. A read-only verification snapshot recorded eight new
removal operations affecting 94 rows and two equipment slots, with three
independent unlock requests; it included an actual equipped-item extraction and
25-item sales. The entire profile matched exactly those operations. All assets,
allocation counters and historical receipts remained intact; proposal cleanup
matched only removed items, no new sale-route errors appeared, and SQLite
integrity passed. Extraction's equipped-slot result was observed through the
saved request/profile; its UI restart was not separately reported. See the
[equipped-item contract and evidence](official-save-experiment.md#removing-equipped-items-through-sale-or-extraction).

Four guild meteor and sixty-seven Guild War regressions cover native entry schemas,
fresh/imported account preservation, membership/progress guards, season rollover,
reconnect, reversible calendar activation, parent composition, cache consistency,
corrupt inputs and CLI commands. Meteor entry passed on the actual APK after
backend reload; the user confirmed its menu loads. The War season-1 trial is
enabled for a valid seven-day period and exposes enable/status/disable commands.
It retains Raid/arena selections while overriding Global War/Raid calendars and
appending one explicit no-reward Global rule for the missing basic-course feature
126. Its acknowledgment changes only bit 126 in a client-only response bitmap.
The actual composed-table audit checked 47 affected rows; other tables, services
and modes retained their parent content, apart from the documented War trial overrides. Both entry
sequences passed against the real write-disabled source database without profile
changes. The first APK War access reached the basic-course prerequisite popup
and redirected to Play > Others; the missing feature rule was then identified
and added. A further APK restart still showed no course; read-only runtime
inspection confirmed its feature checker was loaded/open. Optional `--skip-basic`
now waives only the source prerequisite without writing clears; the lab trial is
enabled with this flag. The corrected waiver reached a completed War entry and
partial cooperative screen load in the APK, then stopped at passive help 1037.
Imported accounts now accept only built-in passive help acknowledgments; gameplay
tutorials stay blocked. The actual packet passed on an in-memory source-account
clone, changing only seen help and UserProgress revision once, with zero retry
writes and no real source writes. Two file-publication regressions cover bounded
Windows sharing-lock retries and preserved output on failure. The user then
confirmed War starts; its next Multi-lobby call now returns a typed empty
CastleSimpleInfos array for native seasonId 1 without resources or writes.
The user confirmed that fix passes. The next cooperative start request now gets
an empty acknowledgment after validating the source season's cooperative stages
and an owned captured Raid/Conquest preset. Actual stage 850030005 passed with
its owned team on read-only source SQLite twice without profile changes or writes.
The user confirmed the APK loads the cooperative phase. Its actual completion
request now returns Cancelled false, fresh GuildWarInfo and no AddedItems after
validating native damage fields and the source stage. The actual request/retry
passed read-only without writes; no score, progress, costs or rewards are saved.
The running API accepted the end request, then the client requested battle-record
synchronization. That follow-up now returns three typed empty arrays for records,
guild defense rankings and daily status; the real request/retry passed without
writes. The API accepted the follow-up after reload with no pending request,
but the result screen froze. A read-only window observation and process-scoped
Unity log identified missing item spec 21644, appended locally from the static
cooperative participation reward. Overlay policy 3 now sets only
PlayCoopCoinReward to zero, retaining other constants and source data. Existing
selections auto-upgrade with their valid window and prerequisite waiver unchanged.
The real source-table/read-only request checks passed without writes. After full
restart the runtime count was zero with other reward constants retained; the APK
displayed the complete cooperative attack result and Exit control. The user
confirmed menu return, also verified by a fresh window observation with all three
entries retained. No matching result exception appeared in the current process's
bounded log check. Single combat, persistent result settlement
and the basic-course UI remain unfinished. See
[commands, contracts and boundaries](guild-war.md).

Leaving an unfinished War stage now acknowledges native parameterless
`/guild-war/abandon-stage` with `{}`. The enabled local trial, membership and
preserved-progress guards remain active. It records no battle result, attempt,
cost, reward or account change. Native empty/null/object framing and repeats
passed against real read-only source SQLite with zero writes. After backend
reload and reconnect the user confirmed abandonment succeeds; two regressions
cover framing, fresh/imported guards, invalid parameters and reconnect.

The Dispute transition threw a native SwitchExpressionException because its Multi
lobby received cooperative phase 1; it accepts only 3/4. The new explicit
`guild-war enable --phase` selector supports four native choices and preserves
the selection across restarts and calendar/parent refresh, retaining legacy
default 1. Cooperative battle calls reject stale Multi-phase views. Phase-3 entry,
castle reads and abandonment passed against real read-only source SQLite with
zero writes. After reload/full restart the user confirmed Dispute opens. Its
next UI guide acknowledgment, 2026, is now allowed along with the three matching
Multi lobby guides, gated by active trial, phase and owned guild. A source-account
memory-clone check changed only the seen-help flag and revision once, without
real source writes. The user confirmed continuation after reload/reconnect.
The first Dispute trial selected `multi-offense`; `coop-offense` restores the verified
cooperative attack path. Multi battle entry/exit now have free local trials;
persistent results remain unfinished. Three phase
and two scoped-guide regressions cover persistence, validation and state retention.

Guild War's defense and coin ranking reads now return native empty views for
season 1: zero/default CoopDefenseMyGuildRank with an empty CoopDefenseTopRanking,
and an empty GuildCoinRanking array. They do not create ranks, settle battles or
grant currency/rewards. The actual packets and repeats passed against real
read-only source SQLite without writes or profile changes. The user confirmed
both screens load after backend reload/reconnect. Four regressions cover native
schemas, fresh/imported guards, retries and query-only state retention.

The exchange center froze in native GuildWarShopConstantsItem.Set, with no queued
API. Its row renderer resolves the same absent currency spec 21644. Overlay policy
4 removes only the active season's five shop offers, preserving other groups and
parent data; native filtering and UI initialization support an empty catalog.
Two regressions cover legacy policy-3 upgrade, scope/cache/state preservation and
malformed source rejection. The real table/read-only account audit passed, with
zero active offers, retained phase 3 and no source writes. After full restart a
native read-only probe confirmed zero loaded rows, with no matching exception in
the process's bounded log check. The user confirmed shop entry/return succeeds;
real purchases remain unfinished.

Dispute's empty castle list previously left its map buttons inactive. Phases 3/4
now expose the selected native deployment's 40 castles with neutral ownership,
marking counts and capture days. The guarded native castle-detail read returns
empty typed status/history/buff collections for those IDs, without writes or
invented rival guilds. All 40 details and repeated lists passed through the wire
codec against real read-only SQLite with an unchanged profile and zero writes.
Six regressions cover fresh/imported state, schemas, phase/membership/progression
guards, corrupt catalogs and bounded immutable caching. After backend reload and
reentering Dispute the user confirmed castle selection opens its information.
The Multi combat trials below do not implement persistent captures.

Fortress defense selection now has an explicit phase-4 `--defend-castle` option.
Entry, map and detail present only the selected native castle as owned by the
local guild, without recording a capture or changing saved progress. The guarded
owned GuildSummary read uses the existing local guild/member and null rank/damage.
Five regressions and repeated real-source read-only entry/list/all-40-details/
summary checks passed without writes or profile changes. After backend reload and
full game restart the user confirmed Defense Battle appears for the owned castle.
This initially established its selection UI; the guarded defense handlers below
extend the trial to local battle entry/exit.

Fortress defense entry now returns native empty GuildBuffIds/CastleBuffIds arrays
after validating an owned captured preset and the selected castle grade's native
DefenceStageIds. Its native v2 exit validates bounded nonnegative Int64 damage
fields and acknowledges the result without saved score, captures, costs or rewards.
Five regressions and real-source read-only request/retry checks passed with zero
writes. The actual stage-850060004 start loaded in the APK after reload/restart.
The API accepted its real defeat completion, then the result renderer failed on
absent medal 21661. Policy 5 suppresses Multi coin/medal decoration and GetPointPlay,
the count the callback actually uses for that medal, retaining other source data.
The source War-table audit passed. After full restart/replay the user confirmed
the result and menu return; native counts were zero and the bounded current log
had no missing-medal/result error frames. The user subsequently confirmed all
remaining listed tests: defense victory, defense abandonment/reentry, repeated
same-hero combat, formation/preset changes and the four cooperative attack maps.
These later checks are user-reported without separate per-scenario native traces.
Guild Information can still be empty; native UI-load
and cached-date parse exceptions were observed with no pending request, and no
client preference was changed during the user's battle tests.

The user subsequently reported cooperative defense works, with occasional stage
loading delay. Read-only profiling found that each cooperative start/end decoded
the full static body, taking approximately 1.5-1.8 seconds per handler. A bounded
content-and-season-keyed immutable stage cache now reuses this validation, while
checking the current file digest on every request and isolating returned sets.
Seven-repeat source-account medians fell to 27.2 ms for start and 21.2 ms for end;
session/packet measurements were 27.8/21.8 ms, with zero writes and an unchanged
profile. The first lookup after backend restart still prepares the catalog in
about 1.48 seconds. Two regressions cover repeated battles, result isolation and
content/season changes; the corruption regression also warms the cache first.
After backend reload the user confirmed less waiting during repeated cooperative
entry/exit. This is qualitative APK confirmation; end-to-end loading latency and
in-combat frame-rate improvement remain unmeasured.

Fortress Siege Battle now has a phase-3 free combat trial using the native Multi
start/end schemas and existing participation-reward suppression. The allowed
catalog is restricted to the unique season stage-group SiegeStageIds for grades
present in the native castle deployment: 16 source stages. The owned captured
preset, authentication, membership, season and saved-progress guards remain;
phase-4 defense retains its selected-castle restriction. Five regressions cover
entry/end/retry/reconnect, grade lists, invalid phases/stages/teams/progress,
corruption and immutable caching. Native-inferred requests for all 16 source
stages passed repeated wire checks on real read-only SQLite with zero writes,
an unchanged profile/source body and unchanged persisted selection. No target
capture, score, attempt, lock, resource cost or reward is saved. After reload/full
restart the user confirmed the menu loads but reported stage entry may be
unavailable. A read-only native probe found phase 3, IsBattleRound true and no
pending API. The following target-selection check identified the blocked control.

The user then confirmed that the blue-castle popup only offers a blank bottom
button that returns to the map. Read-only native fields showed castle 21,
phase 3, combat round active, MarkedCastleId zero and isMarked false, with no
cooperative/season-end block. Native button setup selects `not_marked` there.
The new phase-3 `--attack-castle` selector supplies one explicit local target and
one map marking, retaining zero ownership and no saved progress. Its grade's
four siege stages are accepted; other grades reject. Zero clears the target,
phase-3 omission/refresh retains it, and another phase clears it. Legacy sidecars
stay unmarked. Four regressions and repeated real-source read-only wire checks
passed without profile/source/selection changes or writes. The backend is
reloaded with target 21. After full restart the user confirmed the entry button
opens the stage selection, then confirmed an attack stage loads and is playable.
The user then confirmed the result and return to the castle menu. The particular
victory/defeat outcome was not separately identified.
The pre-existing empty castle-popup labels also remain unresolved.

Guild War now has a Multi `--round prep|combat|auto` selector, separate from phase
and target selection. Native round timing uses ContentToday plus a source hour;
policy 6 overrides only MultiBattleRoundStartTime to 24/0 for preparation/combat,
or preserves the source value 12 in auto. Server time and calendar windows stay
unchanged. Legacy policy-5 selectors upgrade with auto timing and preserve their
phase, castles, valid window and waiver. Multi omission/refresh retains the mode;
cooperative phases reset to auto. Four regressions cover exact table changes,
restoration, checksums, upgrade/retention, invalid input and CLI status. Real-source
private preparations verified hours 24/0/12 with only the expected War constant
change, and all 40 unmarked map/detail reads passed on read-only SQLite with zero
writes and unchanged profile/source/active selector. Native inspection found a
separate local Multi practice entry path. After the prep/unmarked command and
full restart the user reported it works well and prefers it for testing attacks.
Read-only native inspection confirmed phase 3, start hour 24, IsBattleRound false,
no marked/captured castle and retained zero participation counts, with no pending
API. Individual practice outcomes for all 40 castles were not separately recorded.
The user requested this attack command be marked important; the README and War
guide now highlight it as the recommended siege-practice path. The user also
confirmed `multi-defense --round prep --defend-castle 21` works in practice after
restart, and requested it be highlighted too. Both commands now have important
callouts in the README and guide. Defense retains the selected-castle requirement;
individual practice outcomes for every defense castle were not separately listed.

Two guild-attendance regressions cover the explicitly requested empty-reward
mock for `/guild/claim-guild-daily-attendance`: native no-body/null/empty-object
requests, fresh and imported accounts, reopen/reconnect/retries, authentication
and malformed bodies, with SQLite writes disabled. It returns `AddedItems: []`
without changing attendance, membership, balances, inventory, rewards or profile
revisions. The pending route was confirmed in the client; the native request
builder sends no body and both attendance callbacks consume AddedItems. Four
request/retry variants passed through the session and wire codec against the
real database opened read-only/query-only, with zero writes and unchanged full
profile. APK retry is pending backend reload. See
[mock contract](official-save-experiment.md#empty-guild-attendance-reward-mock).

Eight temporal-event entry regressions cover the native no-body packet, fresh
and imported state, all 13 dictionary families plus nullable ReturnEvent,
malformed requests/state, authentication, reconnect and read-only retries. The
observed `/live-event/enter` now returns current saved `UserEvent` without new
seasons, rewards or writes. The actual packet passed twice against a query-only
real database; the resource matched exactly and the source profile was unchanged
with zero writes. APK rendering is pending reload and reconnect. The matching
catalog contains 14 families/397 base rows; Roadmap and Bingo have saved records,
while minigames, historical selection and rewards need additional handlers. See
[event contracts and integration scope](live-events.md).

Nine earlier normal-party
regressions cover ordered owned members, leader changes, trailing-slot removal,
metadata/equipment/preset preservation, compact responses, no-op revisions,
current-state retries, authentication, numeric guards and rollback. The actual
pending `/user/save-party-member/v2` request passed on an in-memory account
clone, changing only the normal formation and User revision. Every other field
and saved preset remained equal, the response was 72 bytes and its exact retry
wrote nothing. The real database remained unchanged. APK formation/leader
refresh and reconnect persistence are pending reload and retry. See
[contract and evidence](official-save-experiment.md#saving-normal-party-members).

Thirteen earlier jewel-upgrade
regressions cover guaranteed low-powder success without costs, socket and loose
targets, stack merge/allocation, locks, maximum grade, malformed requests/graphs,
numeric bounds, atomic rollback, authentication and reconnect. The actual
rejected socket request passed on an in-memory clone, changing only the selected
jewel from grade 19 to 20 and User revision. All currency and other profile
fields remained equal; its exact retry wrote nothing. The actual public graph
passed all 19 edges through both routes on synthetic memory state, 38 cases in
total. The real database remained unchanged. APK success rendering and inventory
refresh are pending reload/reconnect; the original preview percentage remains
client-controlled. See
[contract and evidence](official-save-experiment.md#guaranteed-jewel-upgrades-without-spending-resources).

Eleven earlier jewel
decomposition regressions cover mixed grades, catalog-driven rewards, source
and socket retention, new free operations, exact retries, authentication,
ownership/locks, bounds and atomic rollback. The actual rejected
`/item/decompose-jewel` request passed on an in-memory account clone: only
798,720 powder and the User revision changed. All source jewels and other
profile fields remained equal; the exact retry wrote nothing. The actual
public catalog also passed all 20 grades on synthetic memory state. The real
source database was unchanged. APK result rendering and jewel retention are
pending backend reload/reconnect. See
[contract and evidence](official-save-experiment.md#jewel-decomposition-without-consuming-the-jewels).

Thirteen earlier imported
hero-book regressions cover all eight native objective types, XP thresholds,
evolution/ascension/myth variants, awakening node masks, official nonpaying
baselines, incremental growth, exact retries and transaction rollback. The
matching external catalog has 661 playable specs, 175 origins and 1,329
objectives. The actual rejected `/collection/claim-hero-knowledge-all` request
passed on an in-memory account clone, changing only its acquisition flag,
60 catalog gems and User revision. The exact retry wrote nothing, and an
all-owned-hero batch also passed. The real database remained unchanged.
APK claim/reward rendering is pending backend reload and reconnect. See
[contract and evidence](official-save-experiment.md#dynamic-imported-hero-collection-knowledge).

Twelve earlier Dungeon
Kingdom Arena regressions cover all three rotations and seven days, consistent
native seven-day calendars, unrelated-table/service preservation, composition
with later Raid changes, UTC daily refresh, exact authenticated route schemas,
owned arena-team selection, start/end/abandon receipts, stale selections and
transaction rollback. The public real catalog and an in-memory copy of the
actual account also passed all 21 combinations through start/end/retry, with all
profile sections unchanged. The actual pending entry and empty ranking routes
passed against the read-only real database with zero writes. The initial local
choice is variant 1, day 1; runtime schemas and calendar behavior are inferred
from matching native methods. APK lobby, combat and result/menu return remain
pending backend reload and a full game restart. See
[selector and evidence](official-save-experiment.md#dungeon-kingdom-arena-rotations-and-days).

Twelve earlier imported
challenge regressions cover official baselines, saved native counter rules,
next/all-step batches, dynamic new progress, asset/stackable/cosmetic rewards,
reopen/reconnect/current-state retries, malformed inputs, numeric guards and
atomic rollback. The rejected `/mission/claim-challenge-all-step` request named
the hero-summon achievement group. The actual request passed on an in-memory
clone, awarding one newly earned step while retaining the old official steps;
an exact retry wrote nothing. The matching external catalog contains 13
available groups and 1,190 steps, driven by 15 verified progress evaluators.
The real profile remained unchanged; APK claim/refresh verification is pending
backend reload and reconnect. See [contract and evidence](official-save-experiment.md#dynamic-imported-achievements).

Four earlier preset response
regressions cover large inventories, compact current selections, full definition
replacement on save/create/delete, independent mode pointers, wire round trips
and stale/reconnect retries. Preset responses now send only owner ID, revision
and the complete selected-mode map in `User`, preserving absent hero/inventory
fields under the native partial-resource contract. The actual-account clone
benchmark reduced selection JSON from 657,376 to 383 bytes and edit/delete JSON
from roughly 676 KB to 19 KB. Median host handler/JSON/wire work dropped from
82–88 ms to 8–19 ms; these timings exclude disk flush, network and APK rendering.
Resulting saved profiles/groups and retries matched the previous implementation;
the real database was read-only. APK responsiveness remains pending reload and
reconnect. See [contract and measurements](official-save-experiment.md#compact-preset-responses).

Seven earlier imported-hero
training regressions cover free XP with an empty balance, non-knights, break/
blessing/myth caps, native threshold indexing, partial growth, story unlocks,
atomic batches/rollback, saved-state guards and request/reconnect receipts.
The actual pending `/user/add-character-experience` request passed on an
in-memory clone with only target XP, revisions and applied-XP record changed;
all assets and the real source profile remained unchanged. The matching external
free-XP policy is installed locally. APK leveling remains pending backend reload
and reconnect. See [contract and evidence](official-save-experiment.md#free-imported-hero-experience).

Three earlier friend
recommendation regressions cover authenticated parameterless/native empty bodies,
the native `RecommendInfos` list, social-state preservation and fresh/imported
reconnect reads without writes. The unsupported `/friend2/recommend` request was
confirmed as body type zero with no payload. It now returns `RecommendInfos: []`,
matching `FriendClient.UpdateLatelyFriends`, while retaining saved settings,
friend/request counts, gifts and revisions. Existing friend entry remains empty;
social mutations and peer lookup are unavailable. Repeated actual-account reads
passed with SQLite writes disabled and the full profile unchanged. APK
recommendation rendering remains pending reload/reconnect. See
[contract and evidence](official-save-experiment.md#empty-friend-recommendations).

Five earlier Raid selection
regressions cover the native 700-ID block, the shared `GuildRaidAndConquest`
pointer, owned team validation, independent mode preservation, cross-mode
retries/reconnects, revision guards and atomic rollback. The rejected actual
request was `/preset/set-selected-preset` with `PresetId=713`; the previous
handler admitted only Orbital. Selection now supports existing owned teams in
both Orbital and Raid/Conquest groups, updating only the selected pointer and
User revision with the existing receipt transaction. The pending request passed
against an in-memory clone of the real account; exact replay wrote nothing and
the read-only source remained unchanged. Post-fix APK switching remains pending.
See [scope and evidence](official-save-experiment.md#selecting-a-saved-raidconquest-preset).

Three earlier completion
regressions cover the exact `Damages` array, nonnegative int64 values, four-member
and aggregate bounds, ownership/catalog/progress guards and no-write retries
across reconnects. The APK reached `/guild-raid2/end-stage` after start succeeded.
The local acknowledgment now returns `Cancelled: false` and `AddedItems: []`,
matching the native success callback/result event. It leaves attempts, profile,
rewards, damage, round progress, history and operator selection unchanged. The
actual pending request passed twice through a read-only protocol session with
zero writes. Result rendering/menu return remain pending APK verification;
persistent raid results and the separate abandon endpoint are unsupported. See
[completion contract and scope](official-save-experiment.md#no-reward-local-raid-completion-acknowledgment).

Three earlier combat-entry
regressions cover exact boss-slot/Boolean requests, four configured slots,
both experimental fever flags, reconnects, membership/catalog guards and saved
raid-progress protection without writes or selection changes. The actual blocked
request was `/guild-raid2/start-stage` with `BossIdx=3`, `IsFever=false`. Native
success checks `Cancelled`; false invokes the existing boss/stage scene loader.
The guarded local loading trial now returns that false flag without resources,
costs, attempt records, rewards or party migration. The actual request passed
twice in a read-only session with full profile and selection unchanged. The APK
subsequently advanced to the completion request; completion acknowledgment is
described above. Separate abandon handling and result persistence are pending. See
[contract and scope](official-save-experiment.md#guarded-local-raid-combat-loading-trial).

Three earlier raid
history regressions cover boss/season relationships, the native day/user schema,
owned-user restriction and read-only reconnects without progress, reward or
selection changes. General battle-status/latest reads each completed two actual
APK requests; the next blocked route was `/guild-raid2/get-battle-records/boss`
for season 1 and public boss ID 1790004. It now returns `BattleRecords: []` only
for a boss present in the requested catalog season. The native companion member
detail read returns the same empty list for the saved local user. Both passed
read-only actual-account protocol checks. The boss-history route later completed
four APK queries and boss refresh completed two, advancing to combat entry;
member-detail rendering and combat remain unverified. See
[contracts and evidence](official-save-experiment.md#empty-raid-history-by-boss-and-own-member).

Four earlier raid
menu regressions cover authenticated status/history reads, exact season/count
schemas, native empty lists and fresh boss-state shapes, catalog/ownership
guards and no-write reconnects. The observed blocked request was
`/guild-raid2/get-battle-status` with the selected historical `SeasonId=1`; it now
returns `Records: []`. Its native follow-up latest-record read returns
`BattleRecords: []`. The previously observed parameterless boss refresh returns
fever index zero, round one and scalar round score zero, without consuming
attempts or replacing preserved raid progress. Actual-account read-only checks
passed all three routes with profile and selection unchanged. The APK later
advanced through the two general history reads to the boss-specific request;
boss refresh and combat/result handlers remain unverified or unsupported.
See [contracts and evidence](official-save-experiment.md#empty-raid-combat-log-and-boss-refresh).

Six earlier calendar
regressions address the historical raid selector's missing client date handling.
The client held season 27 correctly, but its effective-season getter rejected
the expired period and substituted the previous season before choosing bosses.
`raid-season set` now prepares an immutable static response activating only that
raid's global calendar row, with matching checksums/revisions and an atomic
selection manifest. Original tables, other service dates, all bosses, global time
and saved account remain unchanged. Private full-table preparation verified that
exactly one calendar row and its containing/checksum records changed. The client
must fully restart after each selection; reconnect is insufficient. The client
subsequently requested historical season 1 as selected, confirming effective
season selection. Exact boss rendering and combat remain unverified. See
[corrected selector behavior](official-save-experiment.md#fresh-local-raid-entry-and-season-selection).

Three earlier raid
ranking regressions cover exact authenticated season requests, catalog/membership
validation and read-only reconnects without changing saved progress, rewards or
operator selection. The raid-entry API completed and the user reported partially
loaded raids; the next unsupported request was `/guild-raid2/get-guild-rankings`
with `SeasonId=45`. It now returns `Rankings: []` and `CutOff: {}`, matching the
native list and integer-to-int64 dictionary. The companion automatic member
ranking refresh returns `Rankings: []`, based on its native builder/callback.
Known catalog seasons are accepted independently of the latest operator choice
because timed refreshes can carry an older client cache. Both routes passed
read-only actual-account checks with full profile and selection unchanged.
Both ranking routes subsequently completed four actual APK requests each; visible
classification UI and combat remain unverified. See
[contracts and evidence](official-save-experiment.md#empty-local-raid-classifications).

Eight earlier raid
regressions cover opt-in fresh entry, resource shapes, preserved state, live
season selection and atomic-write failure. The actual APK advanced through the
membership/preparation path to `/guild-raid2/enter`; that read now offers a
catalog-selected local season with four client-defined bosses, round one, zero
damage and no rewards. `raid-season list` and `raid-season set ID` use the same
external reference directory as the backend. The private lab has 46 default/global
definitions, initially selecting 46. No catalog or operator setting is published
with the source. Selection changes neither SQLite nor global time; existing
non-null saved raid progress rejects. Historical selection now requires the
calendar preparation and full restart described above. Both entry variants passed
against the actual profile with SQLite writes disabled. Post-fix APK rendering
and combat remain unverified; battle/result/reward APIs are unsupported. See
[commands and evidence](official-save-experiment.md#fresh-local-raid-entry-and-season-selection).

Four earlier guild-menu
regressions cover authenticated Boolean raid cache hints, omitted raid-resource/
reward updates, own-member local guild views, native cache hashes, saved
membership/achievement validation and full/partial/reconnect reads without writes.
The APK's next unsupported request was `/guild-raid2/reset` with `IsPartial=false`.
It now returns `ClaimRaidSeasonReward=false` without resetting any raid state.
Read-only inspection also confirmed saved membership but a null client guild
object. The older `/guild/get-my-guild` reply always returned null; it now offers
a view named `Local guild` with only the saved member, membership ID and that
member's achievement. Other guild details use explicit placeholders; no peer
roster or original guild name is recovered. A stable nonzero content hash replaces
the old empty cache. The actual-account sequence passed read-only with unchanged
full profile. After backend reload, restart the APK once to refresh its guild
cache before testing; raid gameplay/rewards and visible menu success remain
unverified or unsupported.
Two guild-notice-read
regressions cover authentication, exact empty/native request bodies, Boolean
notice types, repeated fresh/imported reads, reconnects and saved membership/
pending-reward preservation while SQLite writes are disabled. The unsupported
`/guild/red-dot` menu query now returns `Raid`, `Meteor`, `PunchKing` and `GuildWar`
as false for unavailable local-mode notices. It does not claim rewards or reset
saved guild state. Native scene/shop callbacks establish these response keys;
no official response was captured. Three actual-account request variants passed
through a read-only connection with zero writes and unchanged full profile.
One actual APK notice request subsequently completed, then stopped at the raid
preparation request. This does not establish a rendered guild menu.
Three empty-friend-entry
regressions cover authenticated native empty requests, current imported friend
settings/count/gift preservation, unsupported social mutations and the profile/
friend sequence across reconnects with SQLite writes disabled. The APK completed
one profile-card request, then stopped at the unsupported `/friend2/enter`
prerequisite before rendering. That follow-up now returns an empty `FriendInfos`
dictionary and `IsMigrated=false` without replacing the saved `UserFriend` record.
The actual-account read-only protocol check passed twice with no writes. After
reload, one actual APK friend-entry request completed. The later representative-
portrait test confirmed visible own-profile portrait updates and persistence
after reopening; uncaptured social/decorative fields remain unverified.
Eight own-profile-card
regressions cover sign-in, exact own-user requests, current saved user/records,
signed tower floors, reconnect/reopening, absent or invalid optional records,
unsupported customization/other users and reads with SQLite writes disabled.
The pending APK request's sole `UserId` matched the saved account. A protocol
read against the actual database opened in read-only mode passed twice with
zero writes and unchanged saved profile. Native callbacks require top-level
`UserProfileCard` and `UserStickerPacks`; uncaptured decorations/social fields
are explicitly empty/unknown in this local view. The own-user native callback
uses the current representative avatar and device-local badge. No original
profile-card response was captured; completing the card request alone does not
establish a rendered popup.
Twenty-one new nickname regressions cover the account mutation, composed static
cost/cache contract and CDN name lists. `/user/change-name` accepts one structurally
valid Name, updates only the user and owned guild-member names/revisions, and
commits an atomic retry receipt. The requested local policy is free, with no word
filter, cooldown or uniqueness check. Zero balances are supported; no assets,
spending counters, inventory, progress or captured startup reads are altered.
The native popup checks `ChangeNickCost` against paid gems and loads a localized
name word list before sending. The final static overlay sets only that cost to
zero over the effective mode tables, with consistent revisions/checksums. The CDN
returns an empty name list under a new ETag, retaining chat lists and preserved
resource bytes. Its name list also serves guild-name validation. The actual
pending request passed on an in-memory account backup with zero source writes;
the actual composed static data retained every other constant and table. After
backend/CDN reload, the user confirmed cost zero and name persistence after
reopening without spending gems. A read-only audit found one completed rename,
matching account/guild-member names, unchanged assets/spending and unchanged
other profile sections/startup reads. SQLite integrity passed. The CDN refreshed
the English name list with HTTP 200, then reused it with 304; a previously blocked
name was not separately reported as tested.
See [usage and restart requirements](reference-data.md#free-local-nickname-changes).

Twelve Backroom-entry regressions cover `/my-room/enter` with native Boolean
`IsPartial`. Its separate `UserMyRoom` singleton was not part of the imported
profile, so entry supplies an explicit local default view and empty NewGetItems.
Only free Default MyRoomMedia from the matching items table are made available;
null Hero uses the current representative/costume, zero wallpaper keeps the
bundled background and default music uses its existing bundle. Paid/limited
media, purchases, edits and rewards are outside this entry operation. The entire
account, startup data, presets and receipts remain unchanged, including with
SQLite query-only enforcement. Tests cover framing/authentication, fresh/imported
accounts, dynamic defaults and characters, reopen/repetition, invalid state and
invalid catalogs. The exact pending request and partial/repeated entry passed
on a write-disabled memory account backup with zero source writes. The user then
confirmed the APK loads the character in Backroom and returns to the lobby. Two
entry calls completed without rejections. Read-only verification found the entire
raw account row, imported startup data, current presets and all 42 existing
receipt/claim tables identical to the backup. No room storage was created and
SQLite integrity passed, with zero diagnostic source writes. See
[the entry contract](reference-data.md#backroom-entry).

Twelve Training Room regressions cover parameterless `/training-room/enter`.
The native scene callback reads no response fields; the shared compact User
resource refreshes Id/Cas/TrainingSlots from current saved data. No assignments,
benefits, cooldowns, slot availability, profile revisions, inventory or balances
change. Empty maps and unknown saved slot metadata are retained. Tests cover
fresh/imported state, native no-body/null/empty-object framing, strict guards,
query-only SQLite, reopening, timestamp preservation and bounded response size.
The actual six saved slots passed through native packet framing on a write-disabled
memory backup with an identical full database dump and zero diagnostic source
writes. The user then confirmed Training Room loads and retains its slots. Two
entry calls completed without rejections. Read-only verification found the
entire raw account row, imported startup data, current presets and 42 existing
receipt/claim tables unchanged from the backup. SQLite integrity passed with
zero diagnostic source writes. See
[the entry contract](reference-data.md#training-room-entry).

Twelve representative-portrait regressions now cover
`/user/select-representative-character`: any owned inventory hero can be selected
with no fixed character list or extra catalog. Only the chosen ID and user
revision change, together with an atomic retry receipt; later choices, inventory,
equipment, presets and other progress are retained on delayed retries. Responses
use a compact three-field User resource. Fresh/imported accounts and reopening
an existing database are covered. The actual pending CharacterId and every owned
hero passed on an in-memory account copy with a read-only/query-only source and
zero source writes. After backend reload, the user confirmed changing the picture
between owned heroes and preserving the last choice across a full client restart.
Five actual calls completed without rejections; the saved selection matched the
latest receipt and SQLite integrity passed in a read-only check. Frame selection
is a separate operation below; badges, boards, stickers and other-user lookups
remain outside this operation.
Twelve frame-selection regressions cover `/user/set-portrait-frame`: a positive-
amount owned misc inventory ID resolves to its `portraitframe` design in the
matching external items table, while null removes the selection. No fixed frame
list or extra catalog is needed. Only `User.FrameId`, `User.Cas` and an atomic
receipt change; compact replies and delayed retries retain later selections and
all other progress. Invalid ownership/types, corrupt definitions, rollback,
no-op revisions, fresh/imported accounts and reopening are covered. The actual
pending request and all 37 owned frames passed against an in-memory account copy
with zero source writes. After backend reload, the owner reported successful
changes/removal and persistence across a full client restart. One APK frame call
completed without rejections; a read-only check matched the saved selection to
the latest receipt and confirmed SQLite integrity. The earlier unsupported call
remains historical.
Nine badge regressions cover `/user/set-profile-badge`. The native popup sends an
owned misc inventory ID or null and ignores the reply body; its close callback
saves the design in account-specific persistent client preferences. The local
route validates positive-amount owned `profilebadge` items using the matching
external items table, then returns an empty acknowledgment. Frames and other
misc items cannot be submitted as badges. No account fields, revisions, inventory,
receipts or schema change. Dynamic definitions, null removal, invalid inputs,
fresh/imported accounts, reopening, retries and query-only operation are covered.
The actual pending request and all 13 owned badges passed through the protocol
on a detached account copy with zero writes and every database row preserved.
Own-profile badge persistence is client-local; server-side cross-device/social
badge synchronization is not implemented. After backend reload, the owner
confirmed changes/removal and persistence after reopening. Four actual badge
calls completed without rejections; the older unsupported call is historical.
SQLite integrity passed in a read-only check.
Five Orbital non-clear
exit regressions cover read-only exits, native schema/damage bounds, floor/catalog/
prologue/authentication guards and reconnection. Ten no-reward completion
regressions cover highest-floor-only progress, exact resource/profile bounds,
earlier floors, retries/reopening/new login, explicit policy, revision limits,
rollback and catalog removal. The observed non-clear request and separately
constructed victories passed against a detached actual account. The real save
was unchanged. APK exit retry needs backend reload; actual APK victory remains
unverified. The owner selected progress saving without rewards.
Eighteen relic-option
regressions cover free generation/accept/discard, selected main/secondary groups,
valid slot pools, repeated IDs, locked/unselected rows, persistent current-state
retries, reopening/reconnect/new login, catalog removal, later jewel edits,
ownership/authentication/schema/configuration, revision ceilings and rollback.
The explicit local mock uniformly rolls allowed option IDs and inclusive values
for selected unlocked slots. The detached actual-account check passed without
changing the real save. Two APK rolls and two discards were subsequently saved;
no accepted proposal was observed. Stackable payment/material inventory, jewels
and the unselected group match the pre-mock baseline. Other assets and later
profile actions are outside this live comparison; APK acceptance remains unverified.
Fourteen option-lock
regressions cover free lock/unlock, exact flag/revision/resource bounds, no-op
requests, canonical current-state retries, reopening/reconnect/new login,
same-item pending-proposal invalidation, later value rolls, saved engraving,
ownership/authentication/schema/configuration, revision ceilings and rollback.
The detached actual-accessory check passed without changing the real save.
Three APK locks subsequently persisted, with selected values fixed through later
rolls and all assets, stackables and miscellaneous inventory equal to their
private pre-lock baseline. Other later equipment changes are outside this comparison.
Fourteen first-engraving
regressions cover free hammer/gold preservation, valid public tiers, eligibility,
origin rarity, ownership/authentication/schema/configuration, persistent retries,
revision limits, rollback and follow-up ordinary option/experience changes. The
explicit first-engraving mock retains materials, uses a local uniform tier roll
and sets the initial counter to 1. The detached actual-account check passed;
the real save was unchanged. One APK engraving subsequently saved the expected
attribute/ceiling while assets, hammers, experience and limit breaks matched the
pre-mock baseline. Later ordinary option edits are outside that live comparison.
Eighteen equipment
option-value regressions cover free generation/apply/discard, locked values,
later rerolls/upgrades, persistent current-state retries, original option/range
guards, catalog removal, ownership/authentication/schema/configuration, revision
ceilings and rollback. The explicit local mock preserves option identities/count
and rolls only unlocked values within matching public ranges. A detached
actual-account check passed without changing the real save. Seven APK rolls and
one accepted proposal subsequently persisted with all resources and other profile
fields apart from user revision equal to their private pre-mock baseline.
Thirteen free hammer
limit-break regressions cover exact break/revision mutation bounds, retained
resources and experience, origin-rarity compatibility, maximum clipping,
persistent current-state retries, ownership/authentication/schema/configuration
guards, malformed saved items, overflow and rollback. The detached actual-account
check passed without changing the real save. Two APK operations subsequently
reached 5 saved breaks with gold, hammer stacks, experience and all other profile
fields apart from user revision equal to their private pre-mock baseline.
Twelve free equipment
enhancement regressions cover exact target experience/revision changes, retained
gold and hammers, locked targets, level caps, discount flags, retry persistence,
ownership/configuration/authentication/schema guards, overflow and rollback.
The owner selected a free local policy; the detached actual-account check gained
the expected experience while preserving every resource and unrelated field.
Known saved engraving is now validated and its cap coefficient supported through
the separate first-engraving catalog; weapon sacrifice remains unsupported. Three APK
enhancements subsequently saved continuous experience changes matching the
current target, with all hammer stacks equal to their pre-enhancement hash.
Eight regenerating
obstacle mock regressions cover exact profile/village preservation, available
and future regeneration, old retries after later collection/regeneration,
reopening/reconnect/new login, ownership/spec/status/clock/revision bounds,
explicit configuration, request identity/schema/authentication and rollback.
The owner selected an empty reward. The configured vending-machine mock keeps
the building and position, restarts regeneration and charges/grants nothing.
Its detached actual-account check passed; the APK retry requires backend reload
and reconnect.
Nine princess-gift
mock regressions cover omitted reward notices, exact timer/revision mutation
bounds, null/future/.NET fraction boundaries, current-state retries across later
gifts and village collection, reopening/new login, malformed state, ownership,
revision/time overflow, explicit catalog/schema/authentication and rollback.
The owner selected no reward. A detached actual-account gift acknowledgment
preserved the entire user profile and changed only its village gift timer/revision;
one subsequent APK acknowledgment saved the expected gift timer and single
village revision increment. Other village fields and captured seed hashes matched.
Six imported stamina
purchase regressions cover exact profile/seed preservation, saved/expired price
tiers and batches, current-state retries after consumption/catalog removal,
reopening/reconnect/new login, storage/funds/quota/schema/authentication guards
and signed-64-bit revision limits. The existing purchase handler is now enabled
for imported accounts. A detached actual-account purchase verified its exact
gem cost, stored stamina grant and no-write delayed replay; the APK purchase
retry subsequently saved one receipt with the expected gem payment, stored
stamina and reset counter. This verification covers those purchase fields, not
unrelated later village actions.
Fourteen daily
attendance mock regressions cover no-reward mutation bounds, ignored reward
catalogs, day/request retry fences, official same-day state, reopening/new login,
calendar rollover, UTC/.NET timestamps, invalid state, schema/authentication,
explicit configuration and rollback. The owner selected skipped daily rewards
for the imported account. Its detached check advanced one calendar day with empty
notices, preserved assets/inventory and verified a no-write delayed retry. The
APK subsequently saved one mocked day with the expected calendar/date and login
record revisions. Accounting for later village/base-camp receipt credits, the
remaining profile and captured seed matched their pre-retry hashes; no daily
reward was delivered.
Two new bridge
regressions cover restoration after ADB loses its connection, dynamic loopback
ports and failed reconnect without root/device changes. The latest isolated
Python 3.11/3.13 matrix contains the preceding 379 tests; Docker was unavailable
for the reconnect change, so its full suite ran on the Windows host instead.
The interrupted prepared bridge was restored, its initial root setting matched,
backend/CDN preflight passed and the saved database quick-check returned ok.
Fourteen mastery-reset regressions cover
exact refund/payment and mutation bounds, upgrade/reset retry interleaving,
reopening/new login, cooldown/null/ancient/.NET timestamp boundaries,
authentication/schema/catalog guards, empty/maximized skills, currency/revision
limits, rollback and camp collection after reset. A detached actual-account reset
passed. One subsequent APK reset matched its saved refund, payment and timer.
Thirteen guardian-mastery regressions cover
single-skill spending, exact costs, class/skill limits, preserved state, retries,
reopening/new login, schema/authentication/catalog guards, invalid saved state,
revision/spending limits and transaction rollback. A detached actual-account
upgrade passed. Subsequently, 34 APK upgrades matched saved skills and costs.
Four additional gem-administration regressions
cover imported accounts without a local prologue row, exact state preservation,
CLI/reopening/replay, signed-64-bit revisions and older databases without an import
table. The owner subsequently ran the million-gem command; its saved audit receipt
confirms the grant. The exact APK gem display was not independently verified.
Twelve base-camp mastery-debug regressions
cover exact rewards and mutation bounds, interval gates, retries/reopening,
catalog/authentication guards, camp/mastery state, overflow, revisions, rollback,
interleaving regular collection and changed configuration.
Fifteen village-harvest regressions cover
mutation bounds, seeds, interval/period gates, follower bonuses, storage/capacity,
future/zero clocks, retries, reopening/new login, malformed data, ownership,
authentication, unfinished facilities, revision limits and atomic rollback.
Ten Orbital preset-creation regressions cover
applying a new team, empty definitions, catalogs/slot bounds/native order,
ownership, retries across deletion/recreation and catalog removal, reopening,
authentication, revisions and rollback.
Ten Orbital preset-delete regressions cover
selected/nonselected and last-team removal, preserved data/seeds, dependent
operation rejection, retries/reopening, strict schema/authentication/scope,
ambiguous IDs, empty teams, revisions and atomic rollback.
Seven additional Raid/Conquest deletion regressions extend the same endpoint to
the native 700-ID block. Selected removal clears only `GuildRaidAndConquest`;
nonselected removal retains the complete raw account profile. Other team
definitions/orders and other mode pointers remain unchanged. Last-team removal,
strict mode/state guards, revision overflow, atomic rollback and replay after
recreation/new selection/reopening are covered. All 53 focused preset tests pass.
The actual selected-team request passed through the packet codec on an in-memory
copy of the current account, changing only its definition/group revision and
Raid pointer/account revision, with zero diagnostic source writes. No migration,
new catalog or reimport is needed. After backend reload, the user confirmed
deletion, retained other teams and persistence after reopening. The read-only
save audit found two deletions around an explicit recreation/selection of the
same slot, with the final definition absent. Every surviving team/order and
other mode pointer, inventory, assets, progress and captured seed stayed intact.
The group/user revision deltas matched those changes; SQLite integrity passed.
Thirteen preset-order regressions cover the shared Orbital Lift/Raid handler at
`/preset/reorder-preset`. Native mode 4/7 requests contain slot-indexed position
arrays of length 5/30, with zero for unsaved slots and a complete permutation for
saved teams. Only target `Order` fields and group revision change; account bytes,
selected IDs, team members/gear, other modes and captured startup data remain
unchanged. Validation, no-ops, revision ceilings, atomic rollback, reconnect and
old retries after edits/deletion/recreation are covered. Integration checks also
select/delete reordered teams by their original IDs in both modes. All 31 focused
order/deletion/import checks pass. The actual pending Raid array and equivalent
Orbital array passed on a memory backup of the real account, followed by deleting
its selected Orbital team while retaining Raid order/selection. Diagnostic source
writes were zero. The user then confirmed order persists after reopening in
both modes. The APK completed two Raid reorders and one Orbital reorder. Its
four additional Apply operations and one Orbital deletion also replayed from
the backup to exactly match the live account/group. Each reorder left the raw
profile unchanged; the other operations explain the selection/revision changes.
Final IDs, names, members, equipment and definition-array order were preserved,
as were assets, other profile sections and the captured seed. SQLite integrity
passed, with zero diagnostic source writes.
Five later regressions cover Guild War's native type-18 alias. Its
`GetBasePresetId` maps to 700, while `PresetCount` reads the Raid's 30 slots
instead of the zero in its direct static-table entry. The same order handler
therefore updates the existing Raid/Conquest definitions, preserving account
bytes and other modes; both menus share that order. Tests cover the shared state,
no duplicate revision for an identical Raid order, retry/reopening, strict slot
validation and selection/deletion by original Raid IDs. All 47 focused preset
checks pass. The exact type-18 request passed on a memory account backup, followed
by an equivalent type-7 no-op, with zero source writes. The user then confirmed
Guild War ordering and reopening persistence. One type-18 reorder, two explicit
selection calls and one subsequent deletion across two sessions replayed from
the backup to exactly match the live account/group. The reorder retained profile
bytes; the selections/delete account for later pointer/revision changes. Surviving
team definitions and their relative array order, assets, other profile sections
and startup data were retained. SQLite integrity passed with zero source writes.
Ten Orbital preset-edit regressions cover
exact mutation bounds, optional selection, omitted gear fields, no-ops, retries,
reopening, schema/scope/ownership checks, empty teams and rollback/revision limits.
Eight natural-stamina regressions cover
tick/precision/timezone boundaries, adjusted caps, catch-up and reopening,
no-op states, invalid data/clocks/catalogs, authentication and atomic rollback.
Seven Orbital preset-selection regressions
cover exact mutation boundaries, retries and identities, reopening/reconnect,
scope/authentication, ownership, invalid state, overflow and atomic rollback.
Six Orbital loading regressions cover
authentication, requests, configured/saved floor limits, preserved presets,
ownership, invalid inputs, retries/reconnect and unchanged state. The later
no-reward completion handler covers client-reported progress; battle validation
and rewards remain unsupported. An empty tower-ranking regression covers
repeated fresh/imported reads and unchanged database state; authentication and
request-shape guards also cover the ranking read. Three infinite-tower entry
regressions cover
legacy formations, signed/current imported progress and invalid-state rejection;
authentication, parameter and mutation guards also cover the tower entry.
Four contents-book prerequisite regressions
cover authentication, exact request shapes, imported presets and rift selections,
unchanged database state and unsupported action rejection. Both prerequisite
reads subsequently succeeded in the APK after a backend reload and reconnect.
Thirteen snapshot-import regressions cover
private-input validation, unchanged source/profile data, local sign-in identity,
preserved startup reads, restart, mutation/prologue rejection, catalog isolation,
existing-save protection, directory locking, failed-publication cleanup and valid
or malformed village cache hints. A TLS integration regression checks that a
rejected registered API records its route without retaining its private body.
Imported coupon checks additionally cover positive historical counters, regular
and collaboration maps, zero counts, unchanged inventory/balances/revisions,
repeated reads, reopening, current-shop replies and malformed-state rejection.
Seven imported-summon regressions cover existing evolved heroes, equipment and
historical-state preservation, wishlist changes, one/ten draws, unused zero
stacks, current-state retries, restart/reconnect, new request epochs, unknown
hero origins and atomic rejection/receipt failure.
Eighteen weapon-draw regressions now cover `/summon/select-weapon`, using the
hero draw's local costs/weights, transaction and frozen retry pattern. Matching
external definitions supply 459 eligible non-limited base weapons and the initial
level/experience/metal reward. Rank-4 results use five saved weapon wishlist
designs; every result receives its own inventory ID. Fresh/imported accounts,
one/ten draws, free gems and ordinary/selectable controllers, invalid inputs and
funds, allocator/reward limits, rollback and current-state retries after later
edits/catalog removal are covered. The actual ten-gem request passed on a detached
account copy with only expected fields changed and zero source writes. The owner
then confirmed draws and weapon persistence after reopening. A read-only snapshot
observed nine completed requests/18 new weapons, 2,700 gems and eight selectable
controllers spent, 180 metal/18 mileage credited, unchanged old weapons/heroes/
shop/hero crystals and passing SQLite integrity. No calls were rejected; the old
unsupported request is historical. Regular paid-gem banners are described below;
promotion/pity behavior remains separate; weapon wishlist editing follows below.
Twenty paid-summon regressions cover `/summon/character` and `/summon/weapon`
regular banners (`IsPickUp=false`, `PickUpKey=0`). A shared payment handler debits
only paid-gem asset 70002 for daily type 1 (100) and full-price type 4 (300/2,700).
Daily hero/weapon timestamps and shop revision commit with grants and receipts;
UTC-midnight limits survive new logins, and exact retries cannot charge again.
Full eligible local pools retain the saved wishlists. Currency isolation, UTC
offsets, independent limits, rollback, fresh/imported accounts and persistent
current-state retries are covered. Both daily operations passed on a detached
account copy with zero source writes. The owner confirmed both in the APK and
persistence after reopening. A read-only snapshot matched two daily receipts to
200 paid gems and both saved timestamps; separate wishlist tests accounted for
600 free gems. Old heroes/gear/controllers remained intact, shop changes matched
the daily fields/revisions and SQLite integrity passed. Full-price type 4 has
automated coverage; pickup/events, paid wishlist variants and packages remain
outside the bounded contract.
The existing 241 tests include eighteen first-chapter entry/progress
regressions, four initial knight training regressions, a mission-help tutorial
regression, eight beginner-reward regressions and four first-hero challenge
regressions, an empty event-coupon exchange regression and four initial Guardian
Pass reward regressions and four initial Festival Pass reward regressions.
Eight additional beginner-batch regressions cover shared stacks, high claim-bit
indices, mixed old/new receipts, spent-reward retries, eligibility, invalid
catalogs, authentication, overflow and transaction rollback.
Twelve stamina-purchase regressions cover tiered batches, free-gem spending,
storage/quota limits, UTC resets, receipt persistence after reopening/spending,
catalog validation, authentication/reconnect and failed-write rollback.
Thirteen challenge-batch regressions cover legacy claim preservation, next/all
steps, distinct request identity, persisted retries, malformed/incomplete groups,
catalogs, balance overflow, contiguous receipts and transaction rollback.
Three gold-collection regressions cover current balance plus lifetime spending,
integer clamping, next/all steps, spent-reward retries and invalid mixed batches.
Thirteen initial hero-knowledge regressions cover owned inventory IDs, batches
with/without rewards, preserved flags, mixed old/new claims, persisted retries,
unsupported progression, catalog/receipt validation, authentication and rollback.
Six Festival shop checks cover read-only availability, purchase limits, owned
persistent items, empty-season reads, data validation and authentication. Eight
redemption regressions cover point costs, quantities, assets/stacks, limits,
receipt/reconnect behavior, invalid requests, overflow and atomic rollback.
Four individual-item delivery regressions cover persistent costumes, separate
merch inventory IDs, spent-state retries, row/counter bounds and rollback.
Eight Festival administration regressions cover a season-bound million-point
grant, persistence, spent-balance retries, conflicting arguments, validation,
rollback and cross-process locking. A pass-claim retry regression preserves
points after spending or an administrative grant.
Eight additional catalog-training regressions cover variable costs, multi-level
targets, batches, story caps, shared balances, request identity, reconnect,
sequence reuse, legacy receipts and rollback. Three catalog-tutorial regressions
check persistent flags, the Inn prerequisite, atomic batches and invalid data.
Three quest-catalog regressions check registration, retained progress, retries,
active-stage/catalog validation and rollback.
Three map-discovery regressions check preserved state, request/authentication
validation, persistence across retries/reopening and failed-write rollback.
Mixed currency tests distinguish identical numeric keys across pickup kinds,
check native progress bytes, retries/overlap, all 29 pickups in one batch and
rollback of both balances and markers.
Twelve story-entry regressions cover earned openings, prerequisites, split stamina,
free reentry, session rollback, separate progress stores, catalog validation and
active-stage main-quest handling. Passage checks cover reserve-only entry with
zero charged stamina, insufficient total stamina and initialized chapter progress
for configured stage IDs outside the seven main phases.
Discovered-stage checks preserve independent progress without an entry catalog,
require the saved map flag before entry, prevent clear-based automatic discovery,
deduplicate the entry cost and restrict quest registration to the stage catalog.
Five monster-catalog regressions check mixed reward rows, duplicates/overlap,
restart, stage-local receipts, active-stage and handle validation, invalid
catalogs, native index boundaries and rollback of rewards with defeat markers.
Five completion-catalog regressions check clear prerequisites, exact custom-state
validation, retained balances/quests, earned openings, persistent retry receipts,
later active sessions, invalid catalogs and rollback of the whole completion.
Eight administrative regressions check persistent million-gem grants, exact
profile preservation, idempotent IDs, retries after spending, audit history,
invalid input/overflow, transactional rollback, real CLI use, cross-process
state locks and cleanup after backend startup failures. These eight also pass
on Windows with its native file-lock implementation.
Fourteen weapon-wishlist regressions cover `/summon/set-select-weapon`, dynamic
rank-4 candidates and native category/media-field contracts. The prepared external
definitions expose 133 choices, with a combined hero/weapon checksum refreshing
the old empty weapon cache. Native weapon rows require ItemSummonCategory.Exclusive;
using the hero enum can prevent startup media initialization. Saving preserves
order and supports zero to five choices, returning UserShop and changing only
its weapon selection/revision. No currencies, inventory or draws change; no
migration is needed. Cache refresh, invalid requests/state, no-op revisions,
rollback, reopening and subsequent draw-pool use are covered. All candidates and
replacement/reordering/clearing passed on an in-memory account copy with zero
source writes. After correcting the enum and reloading the backend, the owner
confirmed lobby recovery and saved choices after reopening. Six registration calls
completed without rejection. A read-only backup comparison confirmed five eligible
saved choices, only six shop revisions/the wishlist changed, unchanged user
resources/inventory/heroes/records/startup reads and passing SQLite integrity.
Five hero-wishlist regressions cover catalog checksum refresh, selection,
replacement/clearing, persistence/retries, authentication, invalid placeholders,
catalog validation and failed-write rollback with the remaining profile retained.
Ten draw regressions check one/ten costs, both controller kinds, split stacks,
new heroes, evolved-origin duplicate conversion, crystals/mileage, frozen retry
results, current-state preservation, reconnect/fresh epochs, authentication,
invalid catalogs/balances, overflow and rollback of payment with the receipt.
It covers real loopback TLS,
fragmented and pipelined frames, malformed input, local platform credentials,
account persistence across restart, prologue completion idempotency, restricted
migrations, daily reward retry handling, manifest-backed resource reads, empty
chapter progress objects, atomic stamina spending, free stage retries, and initial
quest persistence without duplicates, native stage-progress bytes, overlapping
coin batches, monster reward retries, stable item receipts, clear-exit validation,
first-clear gem deduplication, completion tutorial acknowledgments, training cost
validation, persistent retry receipts and transaction rollback on a failed write.
The full suite passed on Python 3.11.18 in a container with networking disabled.

The suite and synthetic demo can run in a read-only Docker container with
`--network none`. The runtime has no third-party Python dependencies. A local
development certificate must be generated before running TLS tests.

## Original APK observations

With compatible private inputs in a dedicated, isolated test clone:

- The unmodified 3.57.0 APK accepted local platform configuration and guest access.
- The user completed the full prologue while emulator egress was blocked.
- `/auth/sign-up/v2` saved one selected knight and the starting weapon slots.
- Restarting the backend/client recovered that character without repeating the prologue.
- The lobby and Adventure/world map were displayed.
- The first attendance reward added 40 reserve stamina; the saved amount remained
  40 after reopening the account.
- The first phase's entry screen displayed Inn, monster level 1 and a 15-stamina
  unlock cost. Empty per-stage progress entries fixed the earlier map transition.
- Unlocking loaded Inn and its opening conversation and saved quest 27. The
  displayed reserve stamina changed from 40 to 25.
- After a backend/client restart, the same quest and 25 stamina were recovered;
  Inn could be entered again without another charge.

The APK subsequently accepted quest checkpoints 1 through 4, thirteen purple
coins, ten known monster reports, the shield and costume pickups, and the glove
chest. An intermediate restart reopened Inn with 5/26 coins and 1/4 item markers.
The tested path later reached 13/26 coins and 3/4 item markers, then accepted
`exit_forest_1_2` as a clear exit. The world map displayed **Stage cleared!** and
the 50-gem stage-grade reward. The completion tutorial acknowledgment was also
accepted. This verifies Inn's clear path, not all optional interactions or the
rest of Chapter 1.

Completion saves the cleared flag and one receipt for the 50 free gems. The
existing lab save was credited by replaying its captured local completion through
that same idempotent handler after the reward was added. Restarting the backend
and APK then displayed 50 gems, 870 gold and 25 reserve stamina in the lobby.
The saved inventory still contained the shield, costume and gloves. The next
lobby tutorial directed the player to hero level-up. Its captured request spends
37 experience on the starting knight. The APK accepted the implemented response
and displayed **Lv.1 → Lv.2**; the saved experience balance changed from 790 to
753. This initial tutorial remains the fallback when the external training
catalog is absent. Its receipt preserves older saves without charging again.

The subsequent 74-point request exposed that tutorial-only limit. Training now
uses the matching external experience catalog and story caps, with atomic batch
validation and request receipts independent of the amount spent. The native
popup computes a target's total experience minus the current character total.
The APK accepted 74, 111 and 559 points in succession, taking the knight from 37
to 781 accumulated experience and the unspent balance from 753 to 9. The last
request crossed several levels. The observed reconnect used `Reconnect: true`
and retained pending request sequence 105 while sign-in used sequence 108.
The supplied normal-build catalog has 220 thresholds and a base cap of 99.
Support covers owned knights without limit breaks/blessings; other hero types
and advanced level-cap modifiers remain pending. Request identity relies on the
client's reconnect flag and sequence IDs; arbitrary identical requests replayed
after a fresh application login can be ambiguous. No original-client replay of
a completed training request was forced during this playtest.

Opening the mission book then requested tutorial 1007, whose public configuration
names the `MissionAchievements` help popup. Its acknowledgment is now saved and
the APK's retry passed. It is independent of training.

The mission book's beginner claims for Inn (ID 0) and knight level 2 (ID 1) now
work. The pinned public catalog gives mission 0 three selectable summon tickets,
300 free gems and 50 reserve stamina; mission 1 gives 20 reserve stamina and
200 low awakening stones. The APK accepted both requests, displayed the second
reward notice, and showed 350 gems and 95 reserve stamina. Claim flags and frozen
reward receipts persist together with balances and shared inventory stacks.
Retries grant nothing further. Only these two missions in separate batches are
implemented; other missions and mixed claim batches are rejected atomically.

## Subsequent stamina-mission fix

The resumed client reported `/mission/claim-beginner-all` with `missionIds: [9]`
from the **Use 10 Stamina** reward. Its public catalog requires ten spent stamina
and grants 20 summon tickets (110007) and one selectable summon ticket (110015).
The native `UsedStamina` getter sums the charged and reserve assets' `Spent`
fields; the server now checks those saved counters before granting this reward.

Missions 0, 1 and 9 share the same transactional handler and existing receipt
table. Mission 9 sets bit 9 of `GuideClaimed`, extending the byte array while
preserving the prior claims. Shared ticket stacks and frozen reward notices
retain their inventory IDs across retries. Tests cover the spending threshold,
split charged/reserve spending, malformed/mixed batches, restart and rollback.
The APK retry succeeded. The saved inventory now contains 20 summon tickets and
four selectable summon tickets; the prior gem/stamina balances were preserved.

The next request was `/mission/claim-challenge-all` for group 200, **Collect 1
Heroes**. Its first public step grants 50 free gems for collecting one hero.
The server now supports that first step for the one-knight local account,
records `ChallengeClaimed["200"] = 1` and saves a separate challenge receipt.
The APK retry succeeded and the saved gem balance became 400. Other challenge
groups, later steps and the all-step claim route remain unsupported. Tests cover
duplicates/restart, malformed batches, eligibility, receipt mismatch and rollback.

The next reported boundary was `/ad/init-inbox` when opening the inbox. Its
parameterless native request and success callbacks need the saved `UserRecord`
ad state. The route now returns that record without changing balances, claim
state or ad counters. This is inbox initialization only; ad playback and rewarded
ad claims remain unsupported. The existing 66-test suite still passes. The APK
accepted this read and subsequently reached the summons entry request.

The next missing route was the parameterless `/summon/enter`. The native scene
loader reads `Checksum` and `IsActiveEvent`, then compares them with its loaded
pickup catalog. Entry now returns the same checksum as the existing empty
`/summon/on-event` catalog with inactive events. The lobby regression checks that
the two checksums agree and that reads leave the account unchanged. This adds
entry compatibility only; it implements no summon, exchange, selection or
currency/ticket mutation. The APK accepted entry and then called
`/user/exchange-summon-pickup-ticket` during scene loading.

That parameterless check now returns two empty exchange dictionaries and the
saved `UserShop` when its regular/collaboration event-coupon maps are both empty.
It preserves regular and selectable inventory tickets, balances and counters.
Nonempty event-coupon maps are rejected unchanged because their conversion rules
remain unimplemented. The new regression covers preserved ticket stacks,
restart and refusal to process existing event coupons. The APK retry
succeeded; the loaded summons screen showed the preserved 20
summon tickets, four selectable tickets and 400 free gems. The next reported
error was help tutorial acknowledgment 1003.

The summons help request exposed a general missing class of acknowledgments.
The pinned tutorial catalog contains 32 passive help popups with no start/move
scene, actions or start/end conditions. Those exact IDs are now allowlisted in
`tutorials.py`; unspecified IDs and progression tutorials remain rejected.
The APK accepted help 1003 and later requested world-map acknowledgment 2019.
That individual acknowledgment is now supported after Inn's saved clear flag,
using the same prerequisite as 200. Tests reject premature/mixed batches, retain
all unrelated progress and inventory, and verify retries across restart.
Acknowledgment does not grant rewards, unlock another stage or implement the
systems described by the help. The saved account confirms the 2019 retry.

After catalog-based leveling, the APK requested tutorial 205. The optional
tutorial catalog now allows all 91 known IDs from the matching client to be
recorded after Inn is cleared, while built-in passive help keeps its existing
eligibility. Completion markers only change `UserProgress.Tutorials` and its
revision. They do not execute the tutorial's UI actions, advance quests/stages,
spend resources or grant rewards. This separates UI acknowledgments from the
gameplay operations that need independent server rules. Unknown IDs, malformed
catalogs and premature/mixed batches are rejected unchanged. The APK retry saved
205, preserving 781 character experience, nine unspent experience, all other
balances, quest/stage progress and inventory.

On reentering Inn, the client collected two more purple coins and requested
`/stage/start-quest` for quest 57, `dragon_knight`. Registration now accepts known
chapter quests from an external catalog, currently containing 11 Chapter 1 IDs.
An active Inn session is required. New entries start with grade -1, progress 0
and empty custom state; retries preserve existing entries and the main quest's
checkpoints. The response remains `OpenedStages: []`. This implements registration
only: linked-stage openings, NPC interaction validation, side-quest progression
and rewards remain pending. The APK accepted quest 57 registration and then
requested `/stage/interact-substage-item` for `substage_1_5`.

The public map object and stage definition confirm target 110010005. Native
map visibility checks `UserProgress.IsStageOpened` for that target; after a
successful interaction its coroutine hides the map and shows the discovery
presentation. The server now resolves handles through an external map catalog,
requires an active Inn session and saves the target's opened bit while retaining
all existing flags and account state. Retrying causes no further write or cost.
The response supplies current `UserProgress` to the client's resource handler.
The APK accepted the interaction and saved target 110010005 with opened state 1,
preserving all balances, quest progress and character experience.
Target-stage entry, its gameplay and NPC/location validation remain unfinished.

The next collection request mixed purple keys 13 and 14 with star-piece key 1
(asset 70005). The public Inn tilemap names three star pieces; the native
`HasStarPiece` overloads read progress store 3, separate from purple store 2.
The pickup handler now validates each item against its kind's complete key range
and saves all new markers and currency balances in one transaction. Each unique
kind/key grants one unit once. Invalid mixed batches save nothing; overlapping
retries credit only new pickups. Star-piece markers use the existing v2 progress
encoding. The trailing `StonePieces` puzzle byte is a separate feature and stays
unchanged. The APK accepted the mixed pickup and subsequent collections; the
latest save contains 22 purple coins and two star pieces.

The initial next-stage catalog prepared main stage 100010002 (`easy_forest_1_2`),
with tilemap `alt_forest_1_2_2`, stamina cost 15 and quest IDs 27/34. This did not
resolve the reported map blockage. A read of the loaded public world-map state
identified the immediate destination as **`passage_1_1`**, stage **110011001**,
tilemap `alt_forest_3_1`, costing **10 stamina** and declaring no quests or entry
equipment/level requirements. The private catalog now includes this passage.
Both later entries require Inn's saved clear as a local rule; a complete official
route graph has not been reconstructed. Existing saves receive earned opened
flags without resetting balances, collectibles, quests or unlocked flags.

The first entry saves the unlocked flag, active session and charged/reserve
stamina changes in one transaction; retries/reentry cost nothing further. Chapter
reads keep each stage's own saved stores, initialize every configured stage ID
(including the passage) and return current user progress to refresh the map.
Missing progress entries otherwise produce null client objects. Native total
stamina sums charged and reserve amounts; zero charged stamina does not block
entry when the reserve covers the cost. No stamina transfer or grant is needed.
Registration uses the active stage's catalog quest IDs;
the existing sequential main-quest checkpoints can run in the active configured
stage. The entry update passed 106 tests and preserved the existing account.
The APK subsequently entered the passage and reached its first monster report,
as recorded below. Second-main-stage entry and later clear paths remain pending;
entry support alone does not establish a playable clear.

The next reported error occurred before any new `/stage/start-stage` request.
Logcat identified `NullReferenceException` in `EnterStage`'s load coroutine.
Read-only inspection of the selected entry state showed stage **110010005**
(`substage_1_5`) with **null `SelectedStageProgress`**. This attempt selected the
previously discovered side stage. Its public definition is tilemap
`substage_dragon_knight`, cost 10, quest 57, standard monster level 29 and zero
level/equipment entry requirements. The map response had omitted this ID because
it was neither a main phase nor a configured story entry.

Chapter reads now include every stage already recorded in saved `StageStates`,
as well as configured entries, without changing flags or awarding progress.
The optional catalog flag `requires_discovery` prevents clear prerequisites from
revealing a map and requires its saved opened bit at entry. The prepared side
stage uses this flag and the ordinary one-time entry transaction. No clear
prerequisite is added for this side stage. All 109 tests pass; deployment kept the
selected saved state unchanged. Original-client entry-screen recovery and side
stage entry are pending. Its gameplay, quest completion and rewards are unfinished.

The APK then entered **passage 110011001** with `/stage/start-stage`, saved state
3 (opened/unlocked), and reduced reserve stamina from 125 to **115**. The next
failed request was `/stage/beat-monsters`, containing `battle_1_slime_big`,
`battle_1_slime_1` and `battle_1_slime_2`. The original handler accepted only Inn.
A read of the loaded public tilemap confirmed all **nine** named passage
monsters and their stable indices; the passage has no named currencies/items or
chests in those tables. This does not establish its complete runtime behavior.

Monster reporting now uses an optional external stage catalog with explicit
handle indices and local reward rows. It validates the whole batch and active
stage before writing, then records defeat markers and credits only new handles
in one transaction. Inn retains its existing defaults. The prepared passage
catalog applies the existing provisional local 79-experience/87-gold rule to each
new handle; official levels, rates, multipliers, random drops and battle
validation remain unknown. All 114 tests, format/lint checks pass. Deployment
preserved the selected saved state, including the active passage and 115 reserve
stamina. The APK accepted the retry and two further encounters, recording seven
distinct defeats: gold is now 1,479 and unspent experience 562. The next unsupported
operation is the passage's clear exit `/stage/end-stage`, exit `easy_forest_1_2`.
The passage's clear exit is implemented in the following update; the discovered
side stage's gameplay remains unfinished.

The reported passage clear request uses exit `easy_forest_1_2`, `IsClearExit:true`
and nullable custom fields with HitCount 13/NoDamage false. Its public exit table
agrees with that name; `StageSpec.Rewards` and `FailRewards` are null. The optional
completion catalog now gates this exit on the active unlocked stage and the seven
defeated indices on the observed path. A transaction saves the clear flag,
telemetry, receipt and earned openings and removes the active session. Retries
preserve later sessions and do not grant or spend assets or alter quests.
No additional grade gems or items are granted until their rule is verified;
no grade-claim receipt is created for this path. Inn's existing 50-gem behavior
is unchanged. All 119 tests and format/lint checks pass. The APK accepted the
clear retry: passage state is now **7**, with 1,479 gold, 562 unspent experience,
400 gems, 115 reserve stamina, 22 purple coins and two star pieces preserved.
Existing quests remain unchanged. The observed passage path is now cleared;
second-main-stage gameplay, additional grade rewards and optional paths remain
unfinished.

The next missing entry was the parameterless `/guardian-pass/enter`. Native
scene callbacks refresh from global `UserGuardianPass` state; entry now returns
that saved record without initializing a season or changing experience, pass
type, claims, missions or balances. The account-read regression checks that
nonempty saved progress survives entry, invalid parameters and reopening the
store. The APK accepted entry and acknowledged Guardian Pass help 1013. Its
next unsupported request was `/guardian-pass/claim-all`.

That parameterless claim now supports only the free level-1 reward of pinned
season 58. The client's displayed season and public reward catalog confirm 30
reserve stamina (70032); the native level getter returns level 1 for zero
experience. The first claim assigns season 58 to an empty pass, sets `Claimed.Free`
to 1 and saves the stamina, pass state and frozen reward receipt in one SQLite
transaction. Retrying after reopening the store returns the same notice without
granting again. Other seasons, paid passes, later progress, inconsistent receipts
and request parameters are rejected unchanged. A failed profile write rolls back
the receipt and reward together. The APK accepted the claim: reserve stamina
increased from 95 to 125, with 400 gems and all inventory stacks preserved.
The next missing entry was `/festival-pass/enter`. Seasonal rollover, pass
missions, later rewards, purchases and level skipping remain unimplemented.

The parameterless `/festival-pass/enter` now returns the saved `UserFestivalPass`
record. Its native scene loader and refresh callbacks consume the global record;
the handler preserves experience, points, pass type, claims, missions, purchases
and balances. The existing pass-read regression now checks two distinct nonempty
pass records to catch resets or returning the wrong pass. All 72 tests pass.
The APK accepted entry and next requested `/festival-pass/claim-all`.

That parameterless claim now supports only season 41's free level-1 reward.
The displayed season selects reward set 1: four festival points, no free inventory
items. Native UI code selects `CoinRewards[0]` for the free lane and consumes
`AddedPoint` separately from `AddedItems`. The points are stored in
`UserFestivalPass.Point`; coin item 21484 is used for their reward notice, without
adding an inventory stack. The first claim assigns season 41 to an empty pass,
sets `Claimed.Free` to 1, and saves the points and receipt atomically. Other passes,
balances and inventory remain unchanged. Tests cover retry/reopening, strict
scope validation, independent pass receipts, corrupt receipts and write rollback.
The APK accepted the claim and saved four points, free claim level 1 and its
receipt, preserving all inventory stacks and balances. Later Festival rewards,
missions, point redemption, purchases and automatic seasonal rollover remain
unimplemented.

The next unsupported request was `/guild/get-join-suggestion-list/v2`. The native
request sends `SuggestBy`; its callback reads `Guilds` as a list and
`GuildApplyTo` as a nullable guild. The local read now returns `Guilds: []` and
`GuildApplyTo: null`, consistent with the single account's empty guild state.
It adds no guild, application or membership and does not change the account.
The existing lobby regression exercises the new response's body kind and
unchanged saved profile. The APK accepted the read twice before reaching
`/guild/get-invite-list`. That parameterless read now returns `Guilds: []`, which
its native refresh callback stores in the invitation list before updating the
guild notification indicator. It does not create or accept an invitation or
change guild membership. All 76 tests still pass, and the APK accepted the
invitation-list read twice. Guild creation, applications and multiplayer remain
unimplemented.

## Economy and preservation limits

An unsupported `/summon/set-select-character` request contained
`RequestOriginIds: [-1]`. The empty local candidate list left the native hero
popup without a valid selection; preview/event-button handlers also logged null
references. An optional external pool now supplies 122 playable Unique-category
origin definitions from the matching client's already-decoded cache, retaining
service version/date fields. Matching checksums refresh cached catalog data.
This is a local pool, not a recovered official promotion or probability table.

The new endpoint validates up to five distinct known origins and saves only the
hero wishlist and shop revision. The game was reopened to discard the invalid
pending request. The APK loaded the list and sent five valid updates, finishing
with five saved heroes; the user confirmed selection worked. Normalizing only
the wishlist and `UserShop.Cas` reproduces the pre-fix profile digest. Gems remain
1,000,400, with all other balances, inventory, quests and clears retained.
The wishlist update passed 132 tests. Its next boundary was the ten-draw
`/summon/select-character` request with cost type 3.

Local hero draws now use an explicit external catalog and stable client
epoch/sequence receipts. Supported requests are one or ten results with cost
types 0 (free gems), 3 (ordinary controllers) and 5 (selectable controllers).
Matching public constants supply the 300/2,700 gem costs and duplicate conversion
values 1/8/50. The prepared pool has 175 base definitions with **local** category
weights 75/20/5 for Normal/Story/Unique; Unique draws use the five saved wishlist
origins. These rates, mileage credit and pool rules do not reconstruct official
server probabilities, guarantees, promotions or pity.

Payment, new owned heroes, duplicate crystals, mileage, summon count and frozen
results commit together. Reconnect returns the existing results and current
profile without another payment. A fresh login starts a new request epoch;
cross-login stale replay ambiguity remains. Party/equipment, prior hero progress,
quests and stage clears are preserved. New heroes start at level one without
equipment; general hero training is still pending.

The APK completed three ten-draw batches: 20 ordinary controllers and 2,700 gems
were spent, leaving 997,700 gems, 24 owned heroes, 105 hero crystals and 30 mileage.
The subsequent single-draw request used type 5, which now consumes its separate
110015 controller stack. Four single draws succeeded: the saved total is now
34 with seven receipts, 107 hero crystals and 34 mileage; gems remain 997,700.
The subsequent seven-mission beginner claim exposed the old handler's
single-mission limit. The replacement checks all requested conditions before
granting any rewards, deduplicates IDs, preserves earlier receipts and commits
the whole batch atomically. An optional external catalog supplies the matching
hero-draw milestones; the prepared catalog contains 11 public rows with required
counts from 1 through 50. No mission is marked complete just to dismiss an error.

The original APK retried IDs 10, 418, 173, 419, 175, 420 and 181 with 34 saved
draws. All seven receipts and claim bits persisted, awarding 20 ordinary
controllers and 12 selectable controllers. The three older beginner receipts
remain intact. Gems stayed at 997,700, draws at 34 and hero crystals/mileage at
107/34; reported stage, quest, equipment, pass and tutorial state was preserved.
The profile was also unchanged across backend deployment before that retry.
All 150 tests and Black/Ruff checks pass. Other beginner condition types, weapon
draws, paid/discount/free-event currencies, official pity and remaining game
systems are unfinished.

The next unsupported request was `/user/charge-stamina-by-gem` with `Count: 1`.
The handler now uses a matching external price/limit catalog, saves free-gem
spending and stored stamina with the type-9 daily purchase count, and writes a
receipt in the same transaction. The native price routine sums successive tiers
from the used count; the public counter permits 20 charges daily. The prepared
values are 50 stamina per charge, prices beginning at 100 gems and a 3,000 storage
ceiling. UTC midnight is an explicit local reset rule; cap-crossing batches are
rejected, and paid-gem payment is unsupported.

All 162 tests, Black and Ruff pass. Deployment preserved the complete saved
profile before the pending APK retry: 997,700 gems and 115 stored stamina.
The APK then submitted four purchases with counts 1, 1, 2 and 16. All four
receipts saved, spending 8,000 gems for 1,000 stored stamina and reaching the
20-charge daily quota. Gems became 989,700 and stored stamina 1,115; other
reported balances, heroes, inventory, quests, stages, passes and prior receipts
were preserved. The client proceeded to `/mission/claim-challenge-all-step`
for groups 200 and 206, which is the next unsupported operation.

That challenge request exposed the first-step-only handler's scope. The new
catalog engine evaluates owned heroes and saved hero draws, grants either the
next eligible step or all consecutively earned steps, and preserves existing
per-step receipts. The all-step route and next-step route now share batch
validation, atomic rewards and frozen request receipts. Without an external
catalog the original first-knight fallback retains its earlier behavior.

The matching public data has 100 steps in each requested group. With 26 owned
heroes and 34 draws, the saved account has earned hero-collection steps 2 through
26 and hero-draw steps 1 through 3. Step 1 of collection was already claimed.
The pending batch therefore qualifies for 1,250 gems and 30,000 experience.
All 175 tests, Black and Ruff passed for that change. Deployment preserved the
complete profile. The original APK retried the batch: collection advanced to
26, hero draws to 3, and 28 new step receipts plus one batch receipt persisted.
Gems became 990,950 and experience 230,562, matching the expected awards; the
previous collection receipt remained intact. Other challenge conditions, inventory rewards,
daily/event missions and compass rules remain unfinished.

The next failure was `/collection/claim-hero-knowledge-all` for 25 owned inventory
characters. Their pending condition is initial acquisition; the matching rows
award no assets. The new handler validates the whole batch, marks acquisition
bit zero, preserves other knowledge bits and writes per-hero/request receipts
atomically. Matching external definitions cover 173 initial hero origins. This
scope requires untrained base heroes and does not claim later knowledge
objectives are implemented.

All 188 tests, Black and Ruff pass. Deployment again preserved the complete
saved profile before retry. The APK retried successfully: all 25 acquisition
flags and per-hero receipts plus one batch receipt persisted. Gems stayed at
990,950 and experience at 230,562. The previously owned characters retained
their other reported fields. The user also made 20 further draws before the
state inspection, adding six heroes and changing controller/crystal/mileage
state, so this was not an isolated full-profile comparison of the knowledge
operation. Unrelated profile preservation is covered by the automated tests.

Opening the Festival shop next required `/festival-pass/check-not-redeemable`.
Static inspection established a parameterless request and a `NotRedeemable`
integer list consumed by the popup's exclusion set. A matching external catalog
now computes **local** exclusions from purchase limits and configured owned
persistent rewards. Its prepared 42-item set has 23 costume/frame ownership
rules. Complete official exclusion behavior is unverified. The APK accepted the
availability reply; the complete saved profile remained unchanged across that
read and the next unsupported purchase attempt.

That purchase was `/festival-pass/redeem-point-rewards` with
`shopItemId: 304, amount: 1`: one point for three relic-option change tickets
(110009). The new handler commits point spending, purchase count, asset/stackable
delivery and a frozen request receipt together. Other delivery kinds remain
unsupported. All 202 tests and Black/Ruff checks pass; deployment preserved the
complete profile with four Festival points. The APK retried successfully: one
receipt saved, points became three and three item-110009 tickets were delivered.

The user then requested one million Festival points. The new season-bound
administrative command changed season 41 from 3 to 1,000,003 points while the
backend was stopped. A normalized full-profile digest verified that only
`UserFestivalPass.Point` and its revision changed. The user confirmed the million
balance in the APK. The first free pass reward now replays its original receipt
against current points/purchases instead of requiring the old balance of four.
All 215 tests, Black and Ruff pass; the eight new administration tests also pass
on Windows. Individual delivery now covers costumes, portrait frames, blueprints
and merch; matching hammer items use stackable storage. The prepared catalog
supports 40 of 42 entries, with two sticker packs still unsupported. APK requests
and persisted receipts confirm all 22 costume purchases, nine merch types and
repeated material/ticket/currency batches. Equip/use/upgrade behavior is separate.

Those purchases then unlocked gold collection challenge group 202. Its matching
public catalog contains 100 steps; native mission type 32 counts current gold
plus spent gold, capped at a signed 32-bit maximum. The catalog handler now uses
that condition with the existing atomic batch and per-step receipts. Deployment
preserved the complete saved profile. All 218 tests and formatting/lint checks
pass. The APK retry persisted the first three steps and their 150-gem reward.

The next missing request was `/chat/listen-channel`, with `Listen: true` and a
null `Since`. Its native callback requires a `History` array. The local handler
returns an empty array for authenticated listen/unlisten requests with a null
cursor, without storing a subscription or changing account state. Non-null
cursors and message sending remain unsupported. The complete saved profile was
unchanged at deployment. All 219 tests, Black and Ruff pass; original-client
chat retry confirmation is pending.

The local administrative CLI can add free gems with a persistent receipt and
operation ID. It requires the backend to be stopped, updates only the free-gem
balance/user revision and rolls back on failure. The updated backend and command
share an operating-system lock to prevent overlapping owners. History can be read
without stopping the server. See [administration](administration.md).
After the synthetic checks, the prepared lab applied the million-gem command to
its existing saved account: **400 -> 1,000,400**. The audit receipt persisted, and
the remaining profile matched its previous digest with gem amount/User.Cas
excluded. The backend restarted on the same database with stage clears, quests,
inventory and other balances retained. The user confirmed that the original APK
displayed **1,000,400 gems** after login. This is a user-reported display check;
no automated screenshot or game-input control was used.

The prepared Inn and passage monster rewards use one public level-1 `ExpsData`
row per new known monster handle: 79 experience and 87 gold. This is a provisional **local
rule**, not a verified reconstruction of official server rates, multipliers or
random drops. Reports are allowlisted and deduplicated but battles are not
validated by the server. The optional sword pickup is covered by automated
receipt tests and its public runtime configuration; it was not collected on the
tested clear path. The chest grants the public tilemap's single item 30017 and records the
opened box separately from named pickups. Its retry returns the same inventory
item; it does not grant another pair of gloves.

The prepared laboratory's restoration checks verified its original hosts,
preferences, SDK cache, trust listing and OUTPUT rules. The clone was stopped and
root disabled; the normal emulator instance stayed stopped. The preserved base
and Japanese supplement had no missing files or hash mismatches in their last
full audit.

After the source reorganization, the prepared launcher deployed the new package,
the APK reopened the same saved character in the lobby with its 40 reserve
stamina, and automatic restoration passed again. A clean wheel build, installed
demo, console entry point, Black check and Ruff check also passed. See the
machine-readable [local verification record](verification.json) and the
[GitHub Actions runs](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/workflows/ci.yml)
for hosted results associated with each published commit.

These observations do not mean an arbitrary fresh clone of this repository can
boot an APK without its own content, reference bodies, routing and certificates.

## Clean installation experiment

A separate new Android instance has the exact matching base and ARM64 split
APKs, verified by SHA-256, with no prior app launch, downloaded resources or guest
cache. Its backend has a separate empty database; the established saved account
and its emulator remain stopped. Internet egress is blocked for the experiment.

The first new request was `/static-data/device-specific-settings`. Native audio
initialization consumes an LZ4-compressed static-item text stream. The local
handler now returns a blank stream with no hardware overrides, leaving the
client's built-in DSP fallback. It accepts no parameters and requires no sign-in
or external file. A regression verifies binary response framing, decoded empty
text, invalid requests and absence of account/SQL writes. All 220 tests, Black
and Ruff pass. The APK accepted this response and continued bootstrap.

The local CDN served the media index and Spanish strings. Two requested Spanish
banword lists are absent from the preservation set. The prior captured
`static_data_get.bin` was only a checksum response for an already populated
client: it is insufficient for an empty `ClientVersions` request. A private
complete-table bootstrap now supplies 129 matching text/binary tables, with
binary data encoded as base64 in the static-item stream. They remain external
game data. The client persisted these tables and advanced to requesting its
initial resource ZIP, also absent from the earlier prepared environment.

A private 1.66 GB test ZIP has been generated from 11,874 preserved indexed
files and version/index metadata, excluding on-demand content. It is served
through an additional manifest root without editing the preservation copies.
Two generated empty Spanish filters are an explicit local policy, not recovered
official dictionaries. A fresh local SDK guest was issued through `/kong/sign-up`
and the game accepted `/auth/sign-in`, without importing the earlier guest cache.
The user selected tutorial play with background downloads and reached the
tutorial. The native client downloaded and extracted the package: all 11,874
entries are present with matching sizes, and three selected bundle/script/tilemap
files also match their preserved SHA-256 hashes. These generated inputs and
machine-specific preparation tools are not distributed by the repository. The
user subsequently completed the clean account's prologue without further errors.
The backend confirms the prologue selection is saved and one persistent character
exists; no campaign stage has yet been entered on this new account. Subsequent
gameplay and restart recovery for this specific installation remain unverified.

The user reached the choice between playing the tutorial with or without
background downloads, then reported a connection error. The server had a
90-second next-frame timeout even when the client was simply waiting in a menu.
A real TLS regression with accelerated long deadlines reproduced that disconnect.
The server now waits for a frame's first byte without an idle deadline, then
bounds header/body completion to ten seconds each. Three regressions cover an
authenticated idle/resume, shutdown of an idle game connection and incomplete
header expiry. All 223 tests, Black and Ruff pass. Deployment preserved the
complete new profile. The original-client retry reached the tutorial and
extracted the initial resource package.

The next tutorial disconnect was traced to the clean laboratory's private
diagnostic wrapper: it attempted to parse binary keepalives as JSON. The wrapper
now observes API requests only and passes keepalives unchanged. A direct check
reproduced the old failure; the corrected wrapper and three live TLS Ping/Pong
exchanges passed. This is a laboratory-tool correction, separate from the public
idle timeout change. The client retry passed, subsequent client keepalives were
observed, and the user completed the prologue. No player state or downloaded
content was reset.

## Additional resource downloads

The clean-client user started the in-game additional resource download. Many
individual bundles returned HTTP 200, but `ondemand/ancient_darkness.zip` was
absent and the overall download later reported failure. An individual-bundle
fallback therefore did not establish successful completion of the full operation.

The repository now provides `scripts/build_ondemand_archives.py` to build group
ZIPs from external preservation manifests and produce another CDN manifest root.
Its group-relative paths match the native extractor's destination. Four synthetic
tests cover source overrides, archive contents and manifest delivery, group
selection, source/output preservation and path traversal rejection. All 227 tests,
Black and Ruff pass. Usage is in [setup](setup.md#build-on-demand-resource-archives).

The prepared lab generated 92 group archives containing 1,919 available files.
The previously missing archive now returns HTTP 200 and passes ZIP CRC validation.
All 1,919 preserved indexed on-demand files match their index SHA-1 values. This
does not establish that unpreserved regional resources are available. A cached
330-byte HTTP error body was moved out of the client's ZIP cache for inspection.

A later retry coincided with a CDN process reload and logged five truncated
HTTP responses. The user retried with the CDN left running and reported no
further download error. All 1,524 requested individual on-demand paths are
present with matching indexed sizes. All 1,753 installed indexed on-demand files
also match their SHA-1 values; no ZIP files remain pending. This verifies the
selected client's additional-resource download, not every regional/language
resource. Use of the generated group ZIP by the APK remains unverified because
individual files were already cached. The saved player account and original
preservation files were not changed.

The user next completed the in-game downloaded-file check/organization function.
It requested the media index, received HTTP 304 and made no new resource download.
The file inventory changed from 16,442 to 16,440: one summon video and its ETag
sidecar were removed, with no added files or other size changes. All 1,753 indexed
on-demand files still pass SHA-1 checks. The full saved profile digest remained
identical, including the completed prologue. This observation did not require a
backend restart or any agent change to the client's files.

## Python 3.13 CI shutdown fix

Seven workflow runs across six commits remained in the Python 3.13 validation
step after idle game connections were allowed to remain open. Python 3.11 and
style jobs completed. The standalone idle-connection shutdown test reproduced
the hang locally on Python 3.13. The server awaited listener shutdown before
closing accepted clients; newer asyncio versions wait for those clients too.

Shutdown now closes clients and finishes their handlers before awaiting the
listeners. Existing shutdown regressions bound the close operation itself,
and timer regressions now accelerate `wait_for` rather than a version-specific
internal scheduler. The workflow has ten-minute job limits and cancels older
runs for the same ref. The seven obsolete stuck runs were cancelled.

Both Python 3.11.18 and 3.13.18 pass all 234 tests and the synthetic TLS demo
with external networking disabled. This is a transport/CI correction; no player
save or resource content was changed. Hosted results remain recorded per commit
in [GitHub Actions](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/workflows/ci.yml).

## Fresh PyCharm setup and public client bridge

A new clone under PyCharm used a project-local Python 3.11.9 environment and
the user's fresh public Release downloads. Import passed for 15,915 resource
files and 19 references. The host backend health and the separate CDN's index
delivery passed. Norton initially substituted its own TLS certificate; after
the user temporarily disabled HTTPS scanning, the normal verified protocol
probe passed with TLS 1.3 and three Pongs. The received certificate then matched
the generated certificate exactly. The local website-exclusion form rejected
`https://localhost`, so no working Norton local exclusion is claimed.

The source now includes a separate client-hostname certificate generator and an
experimental reversible MuMu Android 12 bridge, documented in the
[PyCharm walkthrough](pycharm.md) and [MuMu setup](mumu-client.md). Seven additional
regressions guard the instance identity, loopback serial, conflicting hosts,
staging paths, existing keys, root configuration and corrupted-session restoration. The full suite
and synthetic demo pass offline on Python 3.11 and 3.13. The user completed the
first thirty-second bridge test. Independent checks confirmed the original
hosts/trust hashes, IPv4/IPv6 OUTPUT rules, removed firewall chains, empty reverse
mappings and removed staging directory. Root access matched its observed initial
availability. The bridge now queries MuMu's root configuration directly for
future sessions. The existing player accounts were not migrated.

The fresh APK subsequently created its own local SDK guest and completed game
sign-in through the public bridge. It downloaded and extracted the initial
archive from the imported Release pack: all 11,874 entries were present with
their expected sizes, and three sample SHA-256 checks matched the pack's
manifest (the AssetBundle manifest, one script and one tilemap). This was not a
full hash check of every installed file. The user completed the prologue, and
the backend confirmed that its character selection was saved.

The additional download initially failed with truncated responses (`Curl error
18`), including an 88,040,061-byte archive that stopped 25,213 bytes short.
An immediate in-game retry also failed. A Windows probe reproduced incomplete
transfers from the active CDN, while separate diagnostic servers delivered the
same file successfully under both HTTP/1.0 and HTTP/1.1. These observations do
not isolate the cause or establish a protocol fix.

The user restarted only the CDN with its request journal enabled. The next
in-game retry completed: the journal recorded an unchanged index (HTTP 304) and
five successful resource responses (HTTP 200). All 1,753 installed on-demand
files matched the public pack's SHA-256 hashes, including those five files.
The temporary checksum disappeared. A partial group ZIP remained on disk and
was excluded from that installed-content verification. This validates the
selected English voice resource set; Japanese-only resources, other media and
other interface languages are outside that result. The backend and bridge
continued running with the same account. The transfer failure is recovered for
this session; its root cause and a permanent correction remain unresolved.

The user then completed the game's downloaded-file check/organization without
an error. The journal added one media-index request (HTTP 304), with no further
resource downloads. A fresh SHA-256 check still matched all 1,753 selected
on-demand files. Afterward, the previously observed partial group ZIP was no
longer present; no ZIP, `.mkdownload` or temporary checksum files were found.
The backend continued to report the prologue selection as saved. This confirms
the completed organization result for this installation, not the cause of the
earlier transfer cuts or a permanent correction for them.

## Reproducible content import

The [offline content guide](offline-content.md) documents the matching APK
baseline, four required downloads, exact placement, import/check commands,
backend/CDN startup and separate Android routing/trust requirements. The source
tree remains free of game binaries, content and account state. The separate
content snapshot is identified as `gt357-eu-20261116` and carries its own notice.

The release was built from the preserved base, Japanese voice supplement,
prepared initial archive, 92 on-demand archives and 19 allowlisted reference
files. Three ZIP parts total 5,049,412,576 bytes. A full import into a new
directory passed SHA-256 checks for 15,915 resource files and all 19 reference
files, producing the CDN allowlist. The import does not overwrite existing data
or a saved account. Game resources retain their original rights; Apache 2.0
applies to the project's source and documentation.

The imported directory also passed HEAD/range delivery checks for its index,
initial archive and one on-demand archive. With external networking disabled,
the imported reference files passed local TLS Ping/Pong, persistent guest and
platform probes; all 129 initial static tables passed their own data hashes.
These are synthetic server/data checks, not another APK session.

Seven synthetic regressions cover multipart import, nested archive expansion,
content tampering, unsafe/private paths, duplicate part names, existing-directory
protection, missing bootstrap inputs and later file changes. All 234 tests pass
with external networking disabled; Black and Ruff pass. This data-distribution
work does not establish another end-to-end APK run or implement pending routes.

## Prioritized implementation work

Use the [API inventory and implementation plan](implementation-plan.md) to
implement coherent systems independently of manual failures. The initial static
scan found 710 distinct route literals across 62 systems; at source commit
`d248371` the server registered 58 game routes, of which 57 appeared in that scan.
Registration includes partial
handlers and empty reads and does not measure game completion. Eight send
methods require further route resolution. This documentation-only planning
update itself did not change the tested server or saved account. Subsequent
features are recorded above; the inventory's dispatch fields remain a snapshot.

1. Review unresolved routes and request/response contracts; extend automated
   cross-system scenarios using synthetic guests and temporary databases.
2. Finish early-campaign quest completion and custom-state contracts, then the
   remaining configured interactions. Battle validation remains separate work.
3. Implement ordinary party/equipment operations, followed by additional verified
   mission conditions and basic item management.
4. Expand hero development and remaining single-player systems with explicit
   catalog dependencies and persistent retry behavior.
5. Implement later campaign phases and their progression/reward rules.
6. Expand content/resource completeness checks where indices can be interpreted.
7. Consider multiplayer/social modes only after the single-player state model works.

The earlier [Inn checkpoint](first-phase-checkpoint.md) remains a historical record.

No completion date is implied. Several empty read endpoints are compatibility
scaffolding; they are not implementations of the corresponding game systems.

## Experimental official-account preservation

On 2026-11-17, the separate `experiment/official-save-import` branch recorded a
private observation of an owner's matching 3.57.0 client. The account fetch,
separate collection/preset/village/pasture reads and queried chapters' encoded or
null stage progress were retained with authentication fields excluded. Input
integrity and inventory-reference checks passed. The experimental importer now
preserves that profile and the selected startup reads in a separate empty state
directory. Private protocol-level checks passed for local identity,
completed-prologue state, startup replies and unchanged profile after reopening.
The first APK attempt reached account fetch and then stalled at village entry:
the preserved read validator rejected the native request's cache hints. Those
parameters are now validated and covered by regressions. The owner confirmed that
the follow-up APK retry reached the imported lobby, with the matching startup
routes observed and the saved profile unchanged before mutation testing. Host
routing, reverse mappings and IPv4/IPv6 isolation were verified. Some localized
promotional banners were missing; this did not prevent the reported lobby.
Configured hero wishlist/draw mutations are now enabled with imported-account
regressions. Opening summons then failed at its automatic event-coupon check,
before any draw: the previous handler rejected positive imported counters.
An explicit local preservation policy now returns those counters unchanged and
reports no executed conversion. The owner subsequently opened summons and
completed one single draw and one ten-hero batch with selectable controllers.
Read-only SQLite checks verified two receipts, eleven results and controllers
spent, matching reward/history increments, and unchanged existing heroes,
equipment, party and unrelated profile sections. Client restart recovery and
other payment types are not yet APK-verified. Coupon conversion/expiration remains
unimplemented. Other mutations remain guarded. Opening Play next failed at the
unimplemented cooperative-expedition prerequisite. Read-only handlers now cover
that request and the loader's following rift read. Rift selections and captured
cooperative presets are retained; separate cooperative progress was not captured,
so its menu view is explicitly empty. Mode gameplay and rewards remain unfinished.
After the backend reload, both prerequisite reads succeeded. The owner reported
recovery using Reconnect without closing the game; the connection remained active
and the saved one/ten draw receipts were retained. Individual tabs and mode
gameplay remain outside this verification. The next error was the unimplemented
`/tower-infinity/enter` read. Its handler now returns the captured floor and legacy
formation under the native callback's top-level `TowerInfinity` key without
changing progress. The APK subsequently completed entry and reached the ranking
query; a private check confirmed unchanged full profile and draw receipts.
Opening rankings then failed at `/tower-infinity/get-rankings`. It now returns an
empty local `Rankings` list without inferring official entries or a personal rank.
The APK subsequently completed the ranking query and reached
`/tower-infinity/start-stage`. A guarded loading trial now validates the configured
floor against saved progress and resolves the captured preset's owned characters
and equipment before returning success. It performs no profile writes, payments,
attempt recording or rewards. All 276 isolated tests and a private read-only check
of the actual next floor/preset pass. After reload, the APK loaded the phase, and
the owner confirmed defeat followed by return to the Orbital menu. No end-stage
request was observed; the full profile and draw receipts remained unchanged.
That initial trial did not establish saved Orbital progression. The later
no-reward handler is covered by constructed victory checks; actual APK victory,
formation edits, battle validation and reward delivery remain unverified or unsupported.
Changing the preset inside Orbital next failed at
`/preset/set-selected-preset`. That initial fix selected existing captured Orbital
parties, updating the selection pointer and revision with atomic request receipts.
Replays preserve later choices; team definitions, heroes, equipment and other
profile data remain unchanged. The later Raid/Conquest extension is described
above. The APK Orbital selection succeeded and its saved receipt,
pointer and revision matched, with unrelated data preserved. The following failure
was the parameterless `/user/charge-stamina` request. Natural recharge now uses
the saved timer, matching interval and adjusted maximum, committing only the
charged balance, next anchor and revision. Already credited ticks are not granted
twice; reserve/gems, spending, purchase counters and presets remain intact.
The APK recharge succeeded; its saved balance/anchor and later selection revisions
matched their expected changes, preserving unrelated profile data and captured
reads. The following error came after editing/saving a preset at
`/preset/set-presets`. It now saves one existing Orbital team's definition and
optional selection atomically with a retry receipt, retaining other teams and
the original captured seed. Current reads, selection and entry use the saved
definitions. Hero progression, equipped character data and inventory are preserved.
The APK save succeeded. Its receipt matched the current definitions and optional
selection/revision changes, with unrelated profile fields, captured seed, summon
receipts and earlier selection receipts intact. The next error was deletion at
`/preset/delete-preset`. It now removes one existing Orbital definition atomically
with a retry receipt, clearing only that mode's selection if necessary. Current
reads retain removal across reconnects; deleted teams cannot be selected or used
for entry until explicitly recreated. Full responses refresh the client's preset
dictionary. The APK deletion succeeded: remaining definitions, expected revisions,
selection and receipt matched the removal, with unrelated profile data and prior
receipts intact. The next error was Apply using `/preset/set-presets` for a missing
ID with native empty order 999 and `SetSelected=true`. Creation now requires the
matching optional slot-count catalog and validates owned heroes/gear before
atomically saving and selecting the team. New order is appended locally; other
teams retain their order. Old save/delete retries preserve later recreations.
The APK subsequently saved two creations and two deletions. Their receipt history
reproduced current definitions, selection and revisions with unrelated profile,
captured reads and previous selection/summon receipts intact. Reordering, other
modes and saved Orbital progression are unfinished.

The next failure was `/lobby-village/harvest-all`, collecting village production.
It now uses a matching optional catalog, saved inn/facility clocks and owned
follower bonuses to collect gold and soul points within storage/capacity limits.
Balances, source clocks, revisions and retry receipts commit together; current
village reads retain the clocks after reconnect. Full resources preserve their
clocks, while other resources remain collectible. The captured seed and unrelated
village systems remain unchanged. All 336 isolated tests pass. Detached actual
account validation credited only eligible gold, retained full soul points and
their clocks, and left unrelated fields intact without writing the saved account.
The APK collection succeeded; saved gold and both revisions matched its receipt,
the gold clock advanced, full soul-point clocks were retained, and unrelated
profile/village data and prior receipts were unchanged. The next error was
`/lobby-village/harvest-basecamp`. The owner then requested a fixed reward and
selected **100 million mastery points per eligible collection**.

That separate request now uses an explicit debug catalog and the producing
upgraded camp's own clock, with the native 60-second minimum. The mastery balance,
camp clock, revisions and receipt commit together; retries do not grant again.
Normal guardian points, levels, gold, tickets, parties, heroes and equipment remain
unchanged. Ordinary camp scoring/rates and conversion are unfinished. All 348
isolated tests pass. The exact reward and mutation bounds passed against a
temporary in-memory copy of the actual account, without changing its saved state.
Four subsequent APK camp collections have saved receipts totaling 400 million
mastery points; the saved balance equals the pre-retry balance plus those rewards.
This comparison covers the mastery balance and receipts, not unrelated concurrent
village or console operations.

The next mastery failure was `/user/guardian-mastery-level-up`, which accepts one
`SkillId`. It now spends the matching next-level cost from asset 70033, updates
one skill in `User.Options.GuardianMastery`, synchronizes the total mastery level,
increments the user revision and saves a receipt atomically. Native class caps
advance in tens according to the lowest class total, with a separate per-skill
maximum. An upgraded producing camp and a matching external catalog are required.
Reconnect retries return current user state without a second debit. Thirteen
new regressions and the full 365-test matrix pass on Python 3.11/3.13 without
external networking. A detached real-account check verified the exact cost,
mutation bounds and replay without changing the saved account. Subsequently,
34 APK upgrades matched the saved skill map, total, mastery balance and spending
counter. Village and captured seed hashes were unchanged; this comparison does
not assert whole-profile equality across unrelated player actions.

The next failure was the parameterless `/user/reset-guardian-mastery-level`.
It now clears the current skill map/total, refunds that map's catalog investment,
reverses the same mastery spending, charges configured free gems and saves a new
reset time with one atomic receipt. The matching constants specify 300 gems and
86,400 seconds. Native UI guards reject empty/maximized mastery and active cooldown.
Refund and signed counter treatment are explicit local policies; an official reset
response was not captured. Paid-gem fallback is unsupported. Old reset/upgrade
retries preserve subsequent work, and the upgraded camp can collect with zero
skills after a reset. Fourteen new regressions and all 379 tests pass on isolated
Python 3.11/3.13. A detached actual-account reset verified the refund, payment,
cooldown, narrow mutation bounds and both retry directions without changing the
saved account. One subsequent APK reset saved the exact refund, gem cost and
cooldown, cleared the skill map/total and incremented the revision once. Unrelated
profile, village and captured seed hashes matched; SQLite quick-check returned ok. Other village
actions and ordinary camp production remain unfinished.
See the
[experiment boundaries and remaining work](official-save-experiment.md).
