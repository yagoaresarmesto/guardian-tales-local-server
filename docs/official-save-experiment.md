# Official-account preservation experiment

This research is isolated on `experiment/official-save-import`. It investigates
preserving an owner's existing 3.57.0 European account for this local backend.
An experimental importer now loads a validated private snapshot into a new
SQLite state directory. Account fetch, preserved startup reads and local sign-in
passed a private input check. **The APK now reaches the imported lobby**, following
a village-request compatibility fix. The owner also verified entry into summons
and one- and ten-hero draws using selectable controllers in the APK. Wishlist
changes and the other supported payment types have synthetic coverage only.
Unlocked systems are not automatically implemented by import.

## Observed sources

A private, read-only observation of the matching Android client captured:

- `/auth/fetch-account`: the seventeen profile sections used by the local account
  model, including the owned inventory, characters and global progress flags.
- `/collection/list-all`: collection, item mastery and their new-entry markers.
- `/preset/get-presets`: the separate party, character-list and other presets.
- `/lobby-village/enter`: the separate village state and associated read response.
- `/pasture/collection-all`: the separate monster collection response.
- `/stage/get-stage-progresses`: encoded or null progress entries for the queried
  chapters, retained without replacing null entries with invented empty progress.

These are observations of one owner's session, not a complete server export.
Global stage flags and detailed per-stage progress are different datasets.
Visiting one chapter does not establish preservation of other chapters' detailed
progress. Other systems can require additional reads.

Some subsequent responses contain an empty `User` or another empty profile
section. They are retained separately from the account fetch. Replacing the
complete baseline with such a partial response would lose the captured data;
delta merge behavior must be established before applying updates.

## Private evidence and current checks

The observer reads received application frames without writing into the game or
changing its routing. The owner performs authentication. The original capture
excluded request bodies and raw frames. Saved output is limited to recognized
account sections
and selected game-state reads; authentication fields are excluded before writing.
The machine-specific observation tools and resulting files stay outside this
repository and are not part of the public installation workflow.

The prepared private capture passed checks for profile-section presence,
consistent account identifiers, unique inventory and character identifiers,
inventory counters, owned party members and resolved equipment references.
Source and prepared-output SHA-256 hashes were recorded privately. These checks
establish integrity of the observed input, not complete game-state preservation
or compatibility with the local mutation handlers.

## Inspect and import a snapshot

The input is a private JSON file with `format` equal to
`guardian-tales-account-snapshot`, integer `format_version: 1`, and `client` equal
to `{"version":"3.57.0","version_code":431,"region":"eu"}`. It contains:

- `profile`: every section from a complete account fetch, with credentials
  excluded. Empty or partial update responses are not replacements for this fetch.
- `startup_reads`: all four collection/pasture/village/preset routes above, each
  holding `{"body_type":1,"value":{...}}` with the observed response object.
- `stage_progresses`: a dictionary of stage IDs to their captured Base64 strings
  or null values. Missing progress is not inferred.

The [synthetic tests](../tests/test_snapshots.py) construct a small example without
player data. Machine-specific capture and snapshot preparation are separate from
the importer. There is no automatic official-service login or account downloader.

```sh
python -m guardian_tales snapshot inspect --input /private/account-snapshot.json
python -m guardian_tales snapshot import --input /private/account-snapshot.json --data-dir local/imported-state
```

On Windows/PyCharm, use `.\.venv\Scripts\python.exe` and the full path to your own
input file. The source is read without modification. Validation checks the pinned
client, complete profile sections, excluded credential/contact fields, consistent
IDs, owned party/equipment references, inventory uniqueness/counters, signed
historical spending and the preserved-read format. Reports omit account values.

`--data-dir` is mandatory and must be empty. The same state lock as the backend
protects the directory. A completed database is published without overwriting an
existing file; repeated imports are refused. Switching Git branches alone does
not separate runtime state. Start the backend with that explicit state directory
and the usual compatible content and certificate directories.

The imported account retains its profile ID and is recognized as having completed
the prologue. The local platform issues its own guest UUID and credentials.
Reopening the database preserves the profile. Catalog startup does not unlock
additional stages or rewrite imported progress.

## Current implementation boundary

The imported account uses a protected network mode. Account fetch and known reads
remain available; the four preserved startup responses replace their empty local
counterparts. The preserved collection supplies its own new-entry markers.
Other empty social/catalog scaffolding still has the limitations documented in
[status](status.md). Health exposes `imported_account: true` and lists the enabled
mutation routes in `imported_account_mutation_routes`.

Eleven mutations are now enabled: `/summon/set-select-character`,
`/summon/select-character`, `/preset/set-selected-preset`,
`/preset/set-presets`, `/preset/delete-preset`, `/user/charge-stamina`,
`/user/claim-daily-attendance` and
`/lobby-village/harvest-all`, `/lobby-village/harvest-basecamp` and
`/user/guardian-mastery-level-up` and `/user/reset-guardian-mastery-level`. The summon routes
use the existing local selection/draw catalogs,
atomic payment/reward transactions and session-scoped retry receipts. Supported
draws are one or ten heroes using free gems, ordinary controllers or selectable
controllers. Preset selection changes only the chosen captured Orbital preset
and the account revision, with its own atomic retry receipts. Editing an existing
Orbital preset saves its definition separately from the captured seed; a matching
slot-count catalog also permits creating a missing definition. Deletion
removes one existing Orbital definition and clears its selection if necessary. Natural stamina
recharge advances the saved timer and charged balance up to its configured cap.
Village harvesting collects configured inn/facility gold and soul points with
balances, clocks and retry receipts stored together.
Base-camp harvesting currently requires an explicit fixed mastery debug reward;
the prepared experiment uses the owner's requested 100 million per collection.
Mastery skill upgrades spend the catalog's next-level cost and persist one skill,
the total mastery level and the corresponding payment with retry protection.
Reset clears the skills/total and refunds their catalog investment, charging the
configured free-gem cost and setting a persisted cooldown with its own receipt.
Daily attendance uses an explicit no-reward mock: it acknowledges the local day
and advances calendar/login counters without delivering or parsing any reward.
Other mutations
remain rejected until validated for imported state. Health's
`imported_account_read_only` is false because these routes can write.

The draw rules remain the explicitly local rules in the
[reference-data guide](reference-data.md), including their local category weights.
Importing an official profile does not recover official rates, promotions, pity,
weapon draws or special payment variants. An imported hero whose origin cannot
be resolved from the configured catalog prevents a new draw without payment.
Owned evolved heroes retain their progression and equipment on duplicate draws.
Only ticket stacks depleted by the current payment are removed; untouched empty
stacks and unrelated inventory stay unchanged.

Existing official mutation/reward receipts cannot be inferred merely from an
inventory snapshot. New draws receive this local server's own operation receipts
without resetting the historical summon counter. Replaying a prologue or issuing
rewards to repair an unsupported response would damage the imported state.
Captured stage strings are retained in SQLite but imported campaign play remains
outside the current scope.

The first attempt to open summons reached `/summon/enter` and then failed at the
automatic `/user/exchange-summon-pickup-ticket` check. The imported account had a
positive event-coupon counter, while the original local handler accepted only
empty coupon maps. No draw occurred and the saved profile remained unchanged.

That check now has an explicit **local preservation policy** for imported
accounts: it validates the saved pickup/collaboration counter maps and returns
the current `UserShop` unchanged with two empty executed-conversion maps. It does
not classify coupons as expired, clear them or grant replacement rewards. Pickup
seasons and their conversion rules are not configured locally, so those counters
remain available for later implementation. This is limited entry compatibility,
not a claim that coupon conversion is implemented. Ordinary/selectable inventory
controllers stay independent and unchanged by this check. Repeated calls return
current shop state; malformed counters or extra request fields reject without
mutation. The owner subsequently opened the summons screen successfully.

The owner then completed one single draw and one ten-hero batch using selectable
controllers (`SummonCostType: 5`). A read-only comparison of SQLite with the
private imported baseline verified two saved receipts containing eleven results,
eleven controllers spent, unchanged free gems and ordinary controllers, and the
matching mileage, duplicate-crystal and historical summon-counter increments.
Existing heroes, equipment, party and unrelated profile sections were unchanged.
Client restart recovery after these draws remains unverified.

Other hero and equipment actions can be enabled in coherent groups with their
own validation, transaction and retry tests. A private protocol-level check already
confirmed profile equality after reopening, local sign-in identity, completed
prologue state and the preserved startup replies. This is distinct from an APK
result or a claim of complete account preservation.

The first imported APK attempt stopped at `/lobby-village/enter`: the preserved
read handler had incorrectly required every startup request to be empty. The
native `SendEnterLobbyVillage` builder and the live pending request both establish
`isPartial` as a Boolean and `lastLobbyShopUpdated` as a timestamp with an offset.
The handler now validates those exact cache hints, including seven-digit .NET
fractional seconds, and returns the preserved full village without refreshing its
shop or changing the account. Other preserved reads still reject unexpected
parameters. Empty bodies remain accepted for existing local probes.

Regressions cover both partial flags, timestamp bounds/types, invalid parameters,
unchanged profile data and rejection without mutation. Known API validation
failures now increment `rejected_api:<route>` health counters without storing
request bodies. The subsequent APK retry reached the lobby, as reported by the
owner. Backend counters confirm village entry and the later preset/shop/content
reads; the saved profile still matched the imported baseline before draw testing.
IPv4/IPv6 rejection rules, game-host loopback routing and the expected ADB reverse
mappings were also verified while the local game connection was active. Some
localized promotional banners returned HTTP 404 without preventing that reported
lobby. This is not verification of every menu, asset or gameplay operation.

## Play-menu prerequisite experiment

The owner next reported a failure while opening Play. Health recorded the
unsupported `/coop-expedition/enter` request before a mode was started. Static
inspection of `ContentsBook` confirms that loading the menu sends this request
and then `/rift/enter`. The native builders supply `IsPartial` as a Boolean for
cooperative entry and no body for rift entry. Native model fields establish the
cooperative object's structure; no official response to these reads was captured.

The new handlers require sign-in and reject extra or malformed parameters. Rift
entry returns current `UserProgress` without resetting reward selections or
refreshing bonuses. Cooperative entry returns an explicitly empty local view,
including the already captured cooperative presets where present. Its stage
states, narratives and reward counters are placeholders, not recovered official
progress. The full object is returned for either cache hint without saving it
into the imported profile. Matching, battles, clears and rewards remain blocked.

Four synthetic regressions cover authentication, both cache flags, strict request
shapes, captured presets, current rift settings, unchanged complete database state
and rejection of unsupported actions. All 266 tests pass on Python 3.11 and 3.13
without external networking. Private read-only checks also verified the captured
presets, current rift selections and unchanged account/draw receipts. After the
owner reloaded the backend, the running service exposed both routes and recorded
one successful APK read for each. The owner reported recovery using Reconnect
without closing the game. The local connection was active and both saved draw
receipts still contained their original one and ten results. Earlier failure
counters had not increased. This verifies the prerequisite exchange and reported
reconnect recovery, not every tab, mode gameplay or a full client restart.

## Infinite-tower entry

The owner's next error produced an unsupported `/tower-infinity/enter` request.
The native builder supplies no body, and the entry callback reads a top-level
`TowerInfinity` object before transitioning to `Tower1000`. Returning only a
`UserProgress` wrapper would not satisfy that callback. The profile capture
already contains the saved floor and legacy formation, and the native client
retains a fallback for that legacy formation.

The authenticated read now returns current `UserProgress.TowerInfinity` under
the required top-level key. It preserves the captured object, including signed
floor values, without filling in new formation presets or resetting progress.
Unexpected request fields and invalid saved floor data reject without writes.
Three new regressions cover the legacy shape, signed/current imported progress
and malformed-state rejection; existing guard tests now also cover this entry
and unsupported tower mutations. All 269 tests pass on Python 3.11 and 3.13 with
external networking disabled. A private read-only check matched the captured
tower object and retained the complete profile and existing draw receipts.

The original entry response was not captured. After the backend reload, health
recorded a successful entry, and the owner proceeded to the ranking screen. A
private full-profile and draw-receipt comparison still matched the pre-deployment
state. Formation edits, battles, floor advancement and rewards are not implemented
by this read.

## Empty local tower ranking

Opening the ranking screen next failed at `/tower-infinity/get-rankings`. The
native builder sends no body; `Tower1000Client` reads the response's `Rankings`
list, and the ranking overlay uses its count. The new authenticated read returns
`{"Rankings":[]}` as an explicit empty local leaderboard. It does not copy official
ranking entries, infer a personal rank from the saved floor or grant rewards.
Null and empty request bodies are accepted; other parameters reject.

One new regression verifies repeated empty-list reads and unchanged complete
database state for both fresh and imported accounts. Existing authentication and
malformed-request checks also cover the route. All 270 tests pass on Python 3.11
and 3.13 without external networking. A private read-only check confirmed the
empty response and unchanged account/draw receipts. After reload, health recorded
a successful APK ranking query, and the owner proceeded to phase entry. The full
profile and draw receipts still matched the private pre-deployment check. The
original ranking response was not captured.
The separate `/tower-infinity/get-my-ranking` route is still unsupported.

## Orbital phase-loading trial

The next failure was `/tower-infinity/start-stage`. Its native builder sends
integer `floor` and `presetId`, and the success callback ignores the response
body while constructing the client's existing floor stage. The related end
builder sends `floor`, `isCleared` and `damages`; its callback can apply rewards
and tower progress. Entry and result handling therefore have separate boundaries.

The authenticated entry trial now checks completed-prologue state, a matching
external floor catalog and a preserved party preset. Its explicit local policy
allows configured floors through the absolute saved floor plus one. The party
must have one to four distinct owned characters, with every referenced equipment
item owned. Invalid requests, missing/ambiguous presets, unknown references and
unsupported floors reject without writes. Valid entry returns `{}` and performs
no selected-party migration, payment, attempt recording, floor advancement or
reward grants. `/tower-infinity/end-stage` and formation edits remain rejected.
The trial is for loading a phase; winning it does not save progression or rewards.

The prepared lab extracted 1,501 public floor IDs from its matching imported
static table into the optional external entry catalog. The existing Release pack
does not include this additional catalog. Six synthetic regressions cover
authentication, strict request fields, configured/saved limits, preset ambiguity,
owned character/equipment references, invalid catalogs, repeated entry,
reopening/reconnect and rejected result operations. All 276 tests pass on Python
3.11 and 3.13 without external networking. A private read-only check accepted the
account's next configured floor and saved Orbital preset, retaining the complete
profile and earlier draw receipts. No actual combat was started by that check.

The original start response was not captured. After reload, the APK completed the
start request and loaded the phase. The owner confirmed that the battle ended in
defeat and returned to the Orbital menu. The local connection remained active;
no successful, rejected or unsupported `/tower-infinity/end-stage` request was
observed in that trial. A private full-profile and draw-receipt comparison still
matched the pre-deployment state. This establishes loading and the reported
defeat return, not a persisted battle result. Victory, battle-result validation,
result persistence and rewards require their own implementation before claiming
playable saved Orbital progress.

## Selecting a captured Orbital preset

The next reported failure was `/preset/set-selected-preset` while changing the
team inside Orbital. The native builder sends exactly integer `PresetId`.
Static enum and ID helpers establish `InfiniteTower = 4` and a preset-type width
of 100, placing that mode's IDs in `[400,500)`. The popup success callback uses
the selected ID; the saved choice belongs to `User.SelectedPresetId.InfiniteTower`.
The original selection response was not captured.

The enabled mutation accepts only that mode's already captured party presets.
It shares the phase-entry ownership checks for distinct characters and equipment.
Selection updates only the mode's pointer and `User.Cas`; all other profile data
and preserved preset definitions remain unchanged. Repeating the same choice
does not increment the revision. Session-epoch/sequence receipts are committed
with the profile update; replays return current `User` without reverting a later
choice. Reusing an operation ID with different data rejects. A fresh login can
make a new choice, while reconnect/reopening retains prior request identities.

Seven synthetic regressions cover selection and phase entry, exact mutation
boundaries, current-state retries, no-op choices, request identity conflicts,
reopening/reconnect, scope/authentication, invalid or unowned presets, revision
overflow and rollback on receipt failure. All 283 tests pass on Python 3.11 and
3.13 without external networking. Private read-only checks resolved the captured
Orbital options and retained the real profile and draw receipts; no selection was
applied to the real account by those checks. After reload, the APK selection
request succeeded and one receipt was saved. A private check matched the selected
pointer and revision to that receipt; all unrelated profile data and preserved
preset definitions were unchanged. The subsequent failure was a separate
`/user/charge-stamina` request. Creating and reordering presets, other
modes' selections and Orbital formation/result writes remain unsupported.

## Natural stamina recharge

The automatic `/user/charge-stamina` request has no parameters. Static inspection
of `ChargeStaminaLocal`, `Asset.GetMaximum` and native field offsets establishes
the charged asset, saved `NextCharge` anchor, `MaxStaminaDefault + MaxAdj` cap and
`StaminaChargeInterval` in minutes. Matching public constants are 63 and 10 minutes;
the account's adjustment stays private. The original official response was not
captured. The implementation mirrors the inspected client calculation as its
explicit local recharge policy.

While below the cap with a due saved anchor, the handler credits one unit per
elapsed tick, starting at the anchor, and advances that anchor by the same number
of intervals. It clamps the balance and increments `User.Cas` once. The amount
and anchor are committed together, so retries or reopening cannot credit an old
tick twice. Future/null anchors and balances already at or above the cap remain
unchanged; entry does not invent a new anchor or reduce over-cap balances.
Seven-digit .NET fractional seconds retain their final digit without charging
early at a microsecond boundary. Reserve stamina, historical spending, gems,
purchase counters and all other state remain untouched.

Eight new regressions cover exact tick boundaries, timezone/fractional precision,
cap adjustments, catch-up/reopening, no-op states, malformed assets/timers/clocks,
authentication/parameters, invalid catalogs and rollback on failed writes.
All 291 tests pass on Python 3.11 and 3.13 without external networking. A private
calculation on detached account data accepted the saved timer and changed only
the intended fields; it did not write to the real account. The optional recharge
catalog was extracted from the matching imported constants and is additional to
the older Release pack. After reload, the APK recharge request succeeded. Its
saved balance and timer matched elapsed ticks and the adjusted cap. Later preset
selection receipts explained the additional revision changes; the observed choice,
unrelated profile data, summon receipts and captured reads remained consistent.
Gem purchases and reserve-stamina transfers are separate operations.

## Editing an existing Orbital preset

The owner next edited/saved a team and reached `/preset/set-presets`, which was
unsupported. Native builders and serializers establish a single `PartyPreset`
object containing `Id`, `Name`, `Order` and `Characters`, plus Boolean
`SetSelected`. Character rows contain an owned ID and optional equipment IDs;
the native serializer omits nullable gear slots. Those omitted slots therefore
mean unequipped, rather than preserving a previous slot. The save callback reads
the refreshed party model before marking the editor saved. No official save
response was captured.

The mutation now updates one existing Orbital preset in `[400,500)`. It accepts
up to four distinct owned characters and owned equipment, retaining the existing
order and all other teams. Names are bounded to 64 UTF-16 units with control and
invalid surrogate characters rejected. A nonselected team can be saved empty;
empty teams cannot be selected or used for entry. Unsupported fields, other
modes, reordering and invalid references reject without partial changes. New IDs
require the separate creation contract described below.

Current preset definitions are stored separately from the immutable captured
startup reads. `/preset/get-presets`, selection and phase entry use this current
group, including after restart. A changed definition increments only its group
revision. If `SetSelected` changes the chosen team, the selection pointer and
`User.Cas` also change. One transaction stores the group, any selection change and
the edit receipt. Replays return current definitions and selection without undoing
later edits; exact no-ops do not increment revisions. The owned hero roster,
inventory and equipped character progression remain unchanged.

Ten new regressions cover edit/save and entry, optional selection, omitted gear,
no-op serialization, current-state retries, reopening/new epochs, authentication,
scope/schema/ownership checks, empty teams, revision limits and transaction
rollback. All 301 tests pass on Python 3.11 and 3.13 without external networking.
A private read-only check confirmed that the captured Orbital teams round-trip
through the native serialized shape without changes. No real team was edited by
that check. After reload, one APK save succeeded and its receipt reproduced the
current group and optional selection/revision changes. Unrelated profile fields,
the captured seed, summon receipts and earlier selection receipts were unchanged.
The next error was the separate delete endpoint. Reordering, other
modes and Orbital battle results remain unsupported.

## Deleting an existing Orbital preset

The owner reported an error while deleting a preset. The backend rejected
`/preset/delete-preset`; its native builder sends exactly integer `PresetId`.
The native success callback refreshes the preset list and editor. The model's
`Presets` array application clears its dictionary before adding the supplied
definitions, so a full current group can remove a deleted definition. No original
official delete response was captured.

The handler removes exactly one existing Orbital definition in `[400,500)`,
increments the group's revision and returns current `UserPartyPreset2` and `User`.
Other definitions, including their order, remain unchanged. If that team was
selected, the explicit local policy resets only the Orbital pointer to zero and
increments `User.Cas`; choosing another team remains a client action. Removing
the last saved Orbital team is allowed. Owned heroes, equipment, inventory and
the immutable captured seed are retained.

The current group, optional selection change and session/sequence deletion receipt
commit together. Replays return current state without restoring deleted presets
or reverting later edits and choices. A new request for a missing or ambiguous ID
rejects. Current reads and reconnects retain the deletion; selection and stage
entry cannot use it until the slot is explicitly recreated.

Ten new regressions cover selected/nonselected deletion, preserved unrelated
data and seeds, dependent-operation rejection, retries after edits/selections,
reopening/new epochs, the last team, strict schema/authentication/scope, empty
teams, ambiguous IDs, revision limits and rollback. All 311 isolated tests pass
on Python 3.11 and 3.13 without external networking. Private pre-delete hashes
were recorded without changing the account. After reload, one APK deletion
succeeded. Remaining definitions and their order matched the pre-delete hashes;
group revision, optional selection/account revision and the receipt matched the
removal. Unrelated profile data, captured seed and earlier selection/edit/summon
receipts were unchanged. The next error came while applying an unsaved slot.

## Applying or creating an unused Orbital slot

The rejected request was `/preset/set-presets`, rather than a separate Apply
endpoint. Read-only inspection of the pending request found a missing definition,
native empty `Order=999`, four members and `SetSelected=true`. The existing-only
handler rejected creation. Native `SetPresetList` builds empty IDs from the mode
base and slot count; `CreateEmptyPartyPreset` sets order 999. `PresetCount` indexes
the matching `PresetCountS3` constants by mode minus one, giving five Orbital
slots. The Apply builder sends the edited party and true selection flag, and its
success callback exits the editor. No official creation response was captured.

New definitions now require the matching external slot-count catalog, an unused
configured ID and the native empty order. Existing edits retain their order.
The local creation policy assigns the next order after the highest saved Orbital
order, leaving other teams untouched. Names, distinct owned heroes and gear have
the same validation as edits. Empty definitions can be saved without selection;
applying or entering an empty team still rejects. Group, optional selection and
the existing edit receipt commit together. Old save/delete retries return current
state across removal/recreation rather than affecting a later incarnation.

Ten new regressions cover creation/application and entry, empty teams, optional
catalogs and replay after catalog removal, invalid catalogs/IDs/orders, ownership,
retries across deletion/recreation, reopening/new logins, authentication, revision
limits and rollback. All 321 tests pass on Python 3.11 and 3.13 without external
networking. The actual pending request passed against a temporary in-memory DB
copy, changing only the intended group and selection fields. The real account
was unchanged; only structural evidence and pre-apply hashes were recorded.
The optional five-slot catalog was derived from the already imported static data.
After reload, two APK creations and two subsequent deletions succeeded. Replaying
the saved definition history reproduced the current group, selected pointer and
revisions; unrelated profile data, captured reads and earlier selection/summon
receipts remained unchanged. Reordering, other modes and saved Orbital battle
progression remain unsupported.

## Collecting village production

The next reported failure was the parameterless `/lobby-village/harvest-all`
request. Native builders and the harvest coroutine establish that request and
its `AddedItems` response. Resolving the coroutine's generic conversion gives
`List<ItemPlaceholder>`, so notices use item/amount objects. Native production
helpers and field offsets establish separate inn soul-point/gold Unix-second
anchors, facility `EndTime` anchors, manufacture types, production periods,
per-building storage and follower rarity/specialization bonuses. `Harvest` status
is 2. Soul points use asset 70012, gold 70001; the soul-point capacity is the
matching `DefaultMaxSP` plus the saved asset adjustment. No official harvest
response was captured.

The local policy requires a matching external production catalog and a preserved
village. An eligible inn uses its saved manufacture levels; ready facilities use
their owned deployed followers. Production is bounded by each building's storage
and available asset capacity. Facility percentage arithmetic retains the native
float32 conversion before double production, cap and truncation. The local minimum
interval applies separately to each producer. Future/zero anchors are not
initialized or backfilled. Unfinished facilities are skipped; unfinished inns
and mixed-resource facility clocks reject until supported.

A credited resource consumes its eligible source clocks, with capped excess
discarded. A full resource retains its clocks and balance, so a full soul-point
balance does not prevent gold collection. One transaction stores the profile,
current village, both revisions and a session/sequence receipt. No-op collections
retain their revisions and store an empty receipt. Replays return frozen notices
with current profile/village without another grant. `/lobby-village/enter` overlays
the current village after reopening; the original captured startup seed is
immutable. Airships, visitors, base-camp points, dispatches, shops, complaints,
construction, heroes, equipment and historical spending remain separate.

Fifteen regressions cover exact mutation bounds and seeds, minimum/period gates,
bonuses/storage, full and partial capacities, future/zero clocks, current-state
replays without a catalog, reopening/new login, authentication/parameters,
malformed catalogs/state, ownership, revisions, unfinished facilities and atomic
rollback. All 336 tests pass on Python 3.11 and 3.13 with external networking
disabled. A detached check of the actual account credited only eligible gold,
retaining its full soul-point asset and corresponding clocks. Unrelated account
and village fields were unchanged and replay did not write. The real account
was unchanged; private pre-collection hashes were recorded. After reload, one APK
collection succeeded. Its receipt matched the gold balance and both revisions;
the gold clock advanced and full soul-point clocks were retained. Unrelated
profile/village data, captured seed and earlier summon/preset receipts remained
unchanged. The following error was the separate base-camp collection request.

## Administrative gem grants

The separate [administrative gem command](administration.md#add-one-million-gems)
also supports a validated imported account without creating a local prologue row.
Run it while the backend is stopped against its existing state directory. It adds
only free-gem asset 70003 and increments `User.Cas`, with an atomic audit receipt;
import metadata, startup seeds and current preset/village state are preserved.
This command is an offline administrative action, separate from the network
mutation allowlist. Imported CLI persistence/replay has synthetic coverage;
the current imported account has not received a grant during implementation.

## Fixed mastery rewards in the guardian base camp

The combined village collection then reached the parameterless
`/lobby-village/harvest-basecamp` request, which was unsupported. Native inspection
established its builder, separate portal `EndTime`, 60-second minimum, and the
distinction between normal guardian-point asset 70013 and mastery asset 70033.
The response uses current `User`, current `UserLobbyVillage` and `AddedItems`
notices. No original official base-camp response was captured.

During investigation the owner explicitly requested 100 million points in each
collection, then selected **mastery points** after clarifying the two balances.
The implemented contract is therefore an opt-in fixed debug reward, not ordinary
camp production. A separate external catalog selects upgraded camp specs, the
minimum interval and the fixed mastery amount. The prepared policy grants exactly
100,000,000 to existing asset 70033 for each eligible new collection.

The handler requires a preserved village, a nonnegative saved mastery level and one
configured producing camp. It retains future/zero clocks. A credited collection
updates only mastery balance, camp `EndTime` and account/village revisions, with
its receipt in the same transaction. Replays return frozen notices and current
models without another grant, including after reopening or catalog removal.
Normal guardian points, levels, gold, tickets, owned heroes/gear and other village
systems remain unchanged. If the full reward would exceed the signed-32-bit
balance, the request rejects atomically. No fallback debug reward exists without
the catalog. Ordinary camp rates/scoring, gold conversion, ticket collection,
party management remain unfinished. Zero allocated mastery levels remain valid
for the upgraded camp after a reset.

Twelve regressions cover exact rewards and preserved state/seeds, interval/future/
zero-clock boundaries, current-state retries, reopening/new login, explicit catalog
validation, authentication/parameters, inactive mastery, missing/ambiguous/unready
camps, overflow/revisions, rollback, interleaving regular village collection and
changed debug configuration. All 348 tests pass on Python 3.11 and 3.13 with
external networking disabled. A detached actual-account check granted exactly
100 million mastery points, preserving all other fields except the intended camp
clock and revisions; replay did not write. The real account was unchanged and
private pre-retry hashes were recorded. Subsequently, four APK collections
produced saved receipts totaling 400 million mastery points. The saved balance
matches the pre-retry balance plus these receipts. Unrelated live village and
console operations are outside that balance-only comparison.

## Guardian mastery skill upgrades

The owner's attempt to add a mastery skill point reached the unsupported
`/user/guardian-mastery-level-up`. The matching native builder sends exactly one
integer `SkillId`; its coroutine consumes success and refreshes the mastery UI.
Native mastery helpers establish the skill map, next-level cost and class cap.
These are inferred client contracts; no original official response was captured.

An external `guardian_mastery_catalog.json` supplies matching skill/class IDs,
ordered level costs and upgraded camp specs. The prepared 3.57.0 table has 16
skills across four classes and 64 individual levels. The handler requires an
owned, producing upgraded camp; this is the local activation gate rather than a
complete implementation of every lobby feature-unlock rule.

Each accepted request spends the selected skill's next-level cost from asset
70033 and increments that asset's historical `Spent` counter. It preserves any
existing signed counter value rather than resetting it. It increases one entry
in `User.Options.GuardianMastery.GuardianMasterySkill`, synchronizes the derived
`User.GuardianMasteryLevel` total and increments `User.Cas`. The local spending
counter policy is not verified against an official level-up response. Reset time,
normal guardian points, all other assets, heroes/gear, village and captured seed
remain unchanged. The response carries the current `User` model.

The native class cap is the next multiple of ten above the lowest class total,
clamped to the largest class skill count times the number of individual levels.
The selected class must remain below that cap before the upgrade, and the skill
must have another configured level. Missing or malformed state, inconsistent
totals, unknown skills, insufficient funds and overflow reject without writes.
Profile and request receipt commit together. A reconnect replay returns current
state without another debit, even after another upgrade or catalog removal;
changing its skill under the same request identity rejects. Fresh-login request
identity has the same limits as the other epoch-based mutations.

Thirteen regressions exercise these boundaries, persistence and rollback. All
365 tests pass on Python 3.11 and 3.13 without external networking. A detached
in-memory actual-account upgrade verified its exact next cost, narrow mutation
bounds, unchanged village and no-write retry; it did not mutate the saved account.
Subsequently, 34 APK upgrades matched their saved skill map, total, mastery
balance and spending counter. Village and captured seed hashes were unchanged.
This comparison does not assert whole-profile equality across unrelated player
actions. Ordinary camp production remains unfinished.

## Guardian mastery reset

The owner next reported an error while resetting mastery. The unsupported route
was `/user/reset-guardian-mastery-level`. Its matching native builder is
parameterless, and its coroutine checks success, refreshes mastery and shows the
completion popup. Native UI guards reject fully maximized/empty mastery and a
future `SkillNextResetTime`, comparing whole Unix seconds. The matching guardian
constants specify resource 70003, cost 300 and cooldown 86,400 seconds. These
client contracts were inspected; no original official reset response was captured.

The handler uses the existing mastery catalog and a separate matching reset
catalog. It requires consistent saved mastery and an owned producing upgraded
camp. It clears the skill map and serialized total, refunds the sum of configured
costs invested in those current skills, subtracts that refund from mastery
`Spent`, charges the configured free gems and increments gem spending and user
revision. Refund/counter treatment is an explicit local policy, preserving signed
historical offsets rather than refunding a historical counter wholesale. The
client displays total gems; paid-gem fallback is outside this implementation.
The reset time becomes server time plus cooldown, in UTC. Profile and receipt
commit together, and the response contains the current `User`.

Replay returns current state without charging/refunding again or clearing newer
skills. An older skill-upgrade replay likewise cannot restore cleared skills.
Receipts survive reopening and catalog removal; fresh login retains the shared
epoch-identity limitations. Empty/maximized skills, malformed state, insufficient
free gems, active cooldown or currency/revision overflow reject without writes.
The camp's debug collection now accepts zero allocated mastery levels after reset;
the upgraded producing camp remains its activation guard.

Fourteen regressions exercise these boundaries, timestamps, persistence, rollback,
retry interleaving and zero-level camp collection. All 379 tests pass on isolated
Python 3.11/3.13. A detached actual-account reset verified exact refund/payment,
cooldown and narrow mutation bounds, then verified an old upgrade retry and a
reset retry after a new skill purchase. The real saved account was unchanged.
A subsequent APK reset produced one saved receipt. The cleared skills/total,
mastery refund and reversed spending, gem payment/spending, next-reset time and
single revision increment matched that receipt. Unrelated profile, village and
captured seed hashes were unchanged, and SQLite quick-check returned ok.

## Explicit daily attendance mock

The imported account's `/user/claim-daily-attendance` request was rejected by its
mutation guard. Its next catalog reward was an inventory material, beyond the
existing fresh-account asset-only delivery. The owner explicitly selected a
no-reward mock for imported attendance. The matching native builder is
parameterless; both calendar callbacks consume `AddedItems` and the updated
global models. Native group/day helpers establish the encoded calendar counter.
No original official claim response was captured.

An external `attendance_mock_catalog.json` explicitly enables the policy and pins
the client, origin/active group IDs and 28-day cycle. The handler returns current
`User`, current `UserRecord` and an empty `AddedItems` list. It never reads the
normal reward catalog, so unsupported inventory or random reward types cannot
cause delivery errors. An eligible new UTC day advances only the saved calendar
count/date, login-day count and their two revisions. Every skipped reward is
deliberately omitted rather than queued for future delivery. All assets, owned
heroes/gear, inventory counters, other profile fields and captured seed remain
unchanged. Cycle rollover to the active group is a local policy.

A saved same-day official claim is already complete. Invalid/future dates,
invalid counters/owner and revision overflow reject without writes. Calendar
changes, the daily fence and an epoch-based request receipt commit together.
Retries return current models without advancing, including after another day,
reopening or catalog removal. A new request on the same day is also a no-op;
fresh login retains the existing request-epoch limitations. Fresh-account asset
rewards use their prior implementation.

Fourteen regressions cover exact mutation bounds and empty notices, absent or
malformed reward catalogs, cross-day retries, same-day/official/daily guards,
reopening/new login, group/28-day rollover, UTC and .NET timestamp handling,
invalid state, authentication/schema/identity, explicit catalog and rollback.
A detached actual-account check advanced one day with no reward, preserved all
other profile fields and verified a no-write delayed retry. The saved account was
unchanged during this check. Actual APK mock verification is pending backend
reload and reconnect.

## Host readiness before the APK check

The fresh Windows clone imported the public Release content successfully: all
15,915 resources and 19 reference files passed the importer checks. The saved
download manifest matched the manifest fetched from the published Release.
Client hostname certificates were generated locally. A temporary host-only run
verified the API/auth hostname certificates, the CDN index response and three
TLS 1.3 Pongs while retaining the imported profile unchanged. The host services
were then stopped; emulator routing was not changed by this check.

A Windows Proactor connection-close callback logged `WinError 10054` during that
preliminary check. The certificate checks, keepalives and cleanup completed; this
warning is not evidence of a failed APK session. This preliminary check did not
exercise the APK.

Use synthetic accounts for regression fixtures. Real profiles, captured response
bodies, identifiers, credentials and resource files remain private. The supported
fresh-local-account workflow continues to be described in the
[content guide](offline-content.md) and [verified status](status.md).
