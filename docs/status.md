# Verification and remaining work

Status recorded on **2026-11-18**. The public source tree reorganizes the working
prototype; preserved game data is distributed separately as versioned Release
attachments. Test results and original-client observations have different scopes.

## Automated checks

The suite has **658 passing tests on Windows Python 3.11**. Nine normal-party
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
reload, one actual APK friend-entry request completed. Visible profile rendering
remains unconfirmed; the later guild-notice failure is tracked separately.
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
