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

Twenty-three mutations are now enabled: `/item/change-options`, `/item/apply-options`,
`/item/change-relic-options/v2`, `/item/apply-relic-options`,
`/item/change-lock-options`,
`/item/engrave-weapon`,
`/item/enhance-weapon`,
`/item/limitbreak-weapon/v2`, `/summon/set-select-character`,
`/summon/select-character`, `/preset/set-selected-preset`,
`/preset/set-presets`, `/preset/delete-preset`, `/user/charge-stamina`,
`/user/charge-stamina-by-gem`, `/user/claim-daily-attendance`,
`/lobby-village/harvest-all`, `/lobby-village/harvest-basecamp`,
`/lobby-village/receive-gift`, `/lobby-village/remove-obstacle`,
`/user/guardian-mastery-level-up`, `/user/reset-guardian-mastery-level` and
`/tower-infinity/end-stage`. The summon routes
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
Gem stamina purchases use their existing catalog prices, quota, storage ceiling
and atomic payment/grant receipts for the preserved account as well.
Princess gifts use an explicit no-reward acknowledgment that advances only the
village gift timer/revision and omits the reward notice.
The configured regenerating obstacle also skips rewards/payment while retaining
the building and restarting its regeneration timer.
Equipment enhancement has an explicit free policy for owned hammers and
supported targets: only equipment experience and user revision change, retaining
gold and every material. It requires its own matching public-derived catalog.
Hammer limit breaks use a separate free mock: compatible owned hammers increase
the saved break count up to its configured maximum without consuming materials,
gold or experience.
Equipment option-value proposals and their apply/discard step also have an
explicit free mock, retaining all stones and changing only supported unlocked
option levels when the owner accepts the proposal.
First engraving also has a free mock using a compatible owned hammer and one
matching public attribute tier; gold/materials remain intact.
Ordinary option locking/unlocking shares the free option catalog and retains
all stones, changing only requested lock flags and user revision when necessary.
Relic option changes also use a separate free proposal/decision flow with public
per-slot option pools, changing only the selected main or secondary group.
Orbital non-clear exits change no state; an explicit no-reward completion policy
also permits recording a client-reported victory's highest floor and progress
revision without delivering any reward. Actual APK victory is still unverified.
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
reward grants. At this initial checkpoint, `/tower-infinity/end-stage` and
formation edits remained rejected. The later no-reward completion handler is
described below; loading alone still does not establish a validated battle.

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
result persistence and rewards were outside that initial observation. The later
handler below adds no-reward progress saving; actual APK victory remains pending.

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
unchanged during this check. The subsequent APK claim saved one mocked day with
the expected calendar/date and login-record revisions. After accounting for later
village/base-camp receipt credits, the remaining profile and captured seed matched
their pre-retry hashes; the mocked daily reward was not delivered.

## Imported gem stamina purchases

The next rejected route was `/user/charge-stamina-by-gem`. Its existing handler
already implemented the matching `Count` request, external prices, free-gem
payment, stored stamina, UTC quota and retry receipts for fresh accounts. The
imported mutation guard still rejected it. The route is now enabled for preserved
accounts using that same transaction; no prologue row, reimport or captured-seed
change is needed. The user revision additionally enforces the signed-64-bit
ceiling before a new mutation. Existing receipt replays remain valid at the ceiling.

The prepared catalog grants 50 stored stamina per charge, with its first two
prices at 100 gems, a 3,000 storage ceiling and 20 purchases per UTC day. A saved
expired counter resets before pricing; an unexpired counter continues at its
saved tier. A batch crossing storage, funds or quota limits rejects atomically.
Paid-gem fallback remains unsupported. Replays return current `User` without
another debit/grant or restoring stamina consumed later. Other assets, charged
stamina and its timer, roster, inventory, record and captured seed remain unchanged.

Six new imported-account regressions verify those boundaries through the native
packet route, reopening/reconnect/new login and signed-64-bit revisions. Existing
purchase tests retain rollback and daily-reset coverage. The full Windows suite
has 401 passing tests. A detached actual-account purchase spent exactly the
configured first-tier cost and added its stored stamina amount, preserved all
other fields and verified a no-write delayed replay. The real saved account was
unchanged during the check. The imported APK subsequently saved one purchase
receipt; its gem payment, stored stamina and reset counter matched. This check
covers those purchase fields rather than unrelated subsequent village actions.

## Princess gift without rewards

The next unsupported request was `/lobby-village/receive-gift`. The owner explicitly
preferred no reward. The matching native builder sends no parameters. Its success
callback checks for `AddedItems`; when the key is absent it skips reward parsing
and the reward notice, then invokes the completion action. The saved village uses
`NextGiftTime` to gate the present. No original official gift response was captured.

An explicit external `village_gift_mock_catalog.json` pins the client and local
cooldown. The prepared 21,600-second delay is a debug policy, not a claimed official
interval. A due gift updates only `UserLobbyVillage.NextGiftTime` and its revision.
Null/future timers are retained. The response contains the current village and
omits `AddedItems`, rather than manufacturing a zero-value item. The entire user
profile, all balances/inventory, other village fields and the captured startup seed
remain unchanged; the gift is skipped rather than deferred.

The village overlay and operation receipt commit together. Replays return current
village state without resetting a later timer or overwriting subsequent village
collection, including after reopening or catalog removal. Missing/invalid
configuration, malformed timers, wrong ownership, invalid request/authentication
and revision/time overflow reject without writes.

Nine regressions verify these boundaries, replay/interleaving and rollback. A
detached actual-account acknowledgment verified the exact timer/revision changes,
unchanged entire user profile, omitted reward notice and no-write old retry after
a second gift. The real saved account was unchanged. The full Windows suite has
410 passing tests. The subsequent APK acknowledgment saved its expected timer
and single village revision increment. Other village fields and the captured
seed hashes matched. Subsequent natural stamina changes are outside that profile
comparison.

## Regenerating vending machine without rewards

The next unsupported request was `/lobby-village/remove-obstacle`, and the owner
again preferred an empty reward. Its native builder sends lower-case `buildingId`.
The removal coroutine checks optional `AddedItems`/`AddedCharacters`; absent keys
skip reward branches while the normal removal/refresh path continues. The matching
public table identifies the saved obstacle as the regenerating vending machine,
with a positive regeneration interval. No original official response was captured.

The explicit external mock catalog permits only configured regenerating obstacle
specs, with the prepared machine interval of 57,600 seconds. A request must identify
one owned instance in available/completed-regeneration state. It retains the row,
position and all other fields, sets status 3 with a new regeneration `EndTime` and
increments the village revision. An active future regeneration is retained. The
response contains only current `UserLobbyVillage`, with no item or hero reward
keys. No soul points or other currency are spent, and no rewards are delivered or
deferred. This is a local mock, not an implementation of the official exchange.
Permanent removal, hero-unlock obstacles and general demolition remain unsupported.

The overlay and a building-specific operation receipt commit atomically. A replay
returns the current village without extending a later timer or overwriting other
village work, including after reopening or catalog removal. Reusing the same
request identity for a different building rejects. Wrong ownership/spec/status,
malformed requests/configuration, clock/revision overflow and unauthenticated
requests reject without writes.

Eight regressions and the 418-test Windows suite pass. A detached actual-account
check preserved the entire user profile, restarted only the selected machine's
regeneration and village revision, retained the building/position and verified a
no-write old replay after a later regeneration. The real saved account was
unchanged during the check. The APK obstacle mock retry is pending backend reload
and reconnect.

## Free equipment experience from owned hammers

The next APK failure was the unsupported `/item/enhance-weapon` route. The owner
requested an actual improvement without spending anything. The matching native
`SendEnhanceWeapon` builder sends exactly `TargetWeaponId`, `SourceItems` and
`discountBuff`. Its success callback consumes the global account update and
requests the existing training-mission check; no special reward payload was
identified. The matching native hammer calculation selects experience by the
material's declared public level and rarity. No original official response was
captured, and the free behavior is an explicit local policy.

The separate opt-in catalog supplies matching weapon rarities, hammer experience,
experience thresholds and limit-break/myth coefficients. The handler validates
one owned target and sufficient unlocked owned hammers, then changes only target
experience and user revision. Gold and selected materials are retained. Locked
targets are supported; validated engraving now adds its separately configured
level coefficient. Sacrificing equipment as material remains unsupported.
The local cap uses the preserved weapon maximum plus matching
limit-break/myth coefficients; it does not reconstruct the native stage-opening
eligibility calculation. Excess experience is clipped at the supported cap.
Account buffs and mission/progression credit are unchanged.

The profile and canonical operation receipt commit atomically. Reconnect replays
return current state, preserving later improvements without applying experience
twice. A different body under the same identity rejects. A genuinely new operation
can reuse the retained hammers. These receipts retain the existing session-epoch
limitations described for other mutations; they do not identify arbitrary stale
requests across a new login.

Twelve regressions cover exact free mutation bounds, locked targets, myth and
limit-break caps, discount flags, retained materials, current-state retries,
reopening/reconnect/new login, catalog and ownership guards, strict request/auth
validation, revision/experience overflow and transaction rollback. A detached
actual-account check of the pending request computed 422,750 experience from
19 hammers, changing only target experience from 1,335,460 to 1,758,210 and user
revision. Gold, hammer quantities, all unrelated profile fields and captured seeds
were preserved; same-operation and delayed retries made no writes. The actual
saved account was unchanged. Three subsequent APK enhancement receipts were
saved; their continuous experience changes match the current target and the
first gain matches the detached prediction. All saved hammer stacks match their
pre-enhancement hash. This live comparison establishes experience and retained
hammer inventory; complete profile/currency bounds were checked in detached and
synthetic tests.

## Free equipment limit breaks using hammers

The next unsupported route was `/item/limitbreak-weapon/v2`. The owner requested
a mock retaining the hammers. Its matching native `SendLimitBreakWeapon` builder
sends `TargetWeaponId`, `SourceItems` and `discountBuff`. Native
`ForgeLimitBreak.GetAddLimitBreakCount` adds stack quantities, while its hammer
filter compares material rarity with the target weapon's origin rarity. The
success callback logs analytics and requests the existing training-mission check;
no extra reward response fields were identified. No official response was
captured.

The separate matching catalog explicitly enables the free mock for eligible
unengraved weapons and owned, unlocked limit-break hammers. A locked target is
supported. Each hammer contributes one limit break, clipped at the matching
maximum of 5; both hammer quantities and gold are retained. Only target
`LimitBreaks` and user revision change. Experience, options, account buffs,
mission/progression counters, other inventory, village and captured seeds remain
unchanged. This does not implement duplicate-weapon sacrifice or engraving.

The profile and canonical operation receipt commit atomically. Old replays
return current state without reapplying a break, including after later upgrades,
catalog/material removal or reaching the maximum. A changed body under the same
identity rejects; new operations can reuse retained hammers up to the maximum.
The existing session-epoch retry limitation still applies across new logins.

Thirteen regressions cover exact mutation/resource bounds, compatible origin
rarity, multiple stacks and clipping, discount flags, persistent current-state
retries, ownership/schema/configuration/authentication guards, malformed target
and material state, revision/count overflow and transaction rollback. A detached
actual-account check of the pending one-hammer request increased the saved break
count from 2 to 3 and preserved all other fields apart from user revision. It
also verified reuse up to 5, no-write replay at that maximum and rejection of a
new capped operation. The actual saved account was unchanged during these checks.
Two subsequent APK limit-break receipts reached the saved maximum of 5. Their
continuous changes match the target, and the first matches the detached
prediction. Gold, all hammer stacks, experience and every other profile field
apart from user revision match the private pre-mock baseline.

## Free equipment option-value proposals

The next unsupported APK request was `/item/change-options`, and the owner asked
to retain option stones. Native `SendChangeItemOptions` sends exactly `ItemId`;
the forge and retry callbacks read `NewOptions` as `OptionId`/`Level` pairs. The
popup separately calls `SendApplyItemOptions` with `ItemId` and Boolean `Apply`,
using false for keeping old values and true for applying new values. No original
official response was captured.

The explicit matching external catalog supplies public per-weapon option ranges.
This local mock keeps existing option identities, count, order, locks and source,
rolling unlocked levels uniformly within those ranges. It does not reconstruct
official option-presence probabilities or add/remove optional attributes. Only
owned weapons with supported ordinary option rows and validated saved engraving,
if present, are accepted. A
locked target is supported, existing locked option values remain fixed, and
option-lock creation/removal now uses the separate free operation described below.

Generation persists a proposal and its original spec/options/ranges without
changing the profile or revision. Applying changes only target `Options` and
user revision; discarding leaves the profile unchanged. No stones, currency,
buffs, progression credit or other inventory are consumed. A new reroll replaces
the latest proposal for that item. Resolving requires unchanged original options
and spec, while preserving later experience/limit-break changes; saved ranges
remain checked after external catalog removal.

Proposal writes/resolution and receipts commit atomically. Change retries show
the latest proposal or current applied options without drawing or resurrecting an
older proposal. Apply/discard retries retain newer pending work and current
profile state. Different parameters or routes under the same identity reject.
The native body has no proposal ID, so a new resolution targets that item's
latest pending proposal. Existing session-epoch limitations still apply across
new logins.

Eighteen regressions cover generation/accept/discard bounds, free resources,
locked values, repeated rolls, current-state retries, reopening/reconnect/new
login, persisted range guards, later experience/break changes, stale/corrupt
proposals, ownership/configuration/schema/authentication, revision ceilings and
transaction rollback. A detached actual-account check generated all five current
option values, applied a proposal and discarded a later proposal while retaining
all stones, currency, inventory quantities and other fields. Same and delayed
retries made no writes; captured seeds and the actual saved profile remained
unchanged. Seven subsequent APK rolls and one accepted proposal were saved.
The equipped options match that accepted proposal; all currencies, stackables,
misc inventory and other profile fields apart from user revision match the
private pre-mock baseline. Known engraving attributes are now validated and
retained by this handler as described below.

## Free first engraving with a retained hammer

The next unsupported APK route was `/item/engrave-weapon`; the owner explicitly
requested retaining the hammer. Native `SendEngraveWeapon` sends exactly
`TargetWeaponId` and `MaterialWeaponId`. The matching `Weapon.Apply` reads
`EngraveOptions` as option-ID/level pairs and derives fixed engraving options from
the public weapon spec. Its success callback can read optional returned items;
the later refund coroutine skips a null/empty list. No official response was
captured.

The explicit free first-engraving catalog supplies matching eligible exclusive
weapons, public random-option tiers, compatible hammer origin rarities, the
experience gate and engraving coefficient. The target must have five limit
breaks, sufficient experience and no prior engraving. One unlocked owned
compatible hammer stack is required but retained. The local mock uniformly
chooses one public tier, stores one engraving pair and sets the initial ceiling
counter to 1. This is an explicit local initial-roll policy, not an implementation
of official rates or subsequent ceiling/pity progression. Only engraving options,
the ceiling and user revision change; gold, hammers, experience, ordinary options
and every unrelated field remain intact. No refund reward is fabricated.

The profile and retry receipt commit atomically. Reconnect replays return current
state without rolling again or overwriting later changes, including after catalog
or material removal. Changed request parameters under one identity reject. A new
first-engraving request on an already engraved target rejects. Duplicate weapons
as materials, engraving rerolls and their separate apply/discard routes remain
outside this handler.

Existing ordinary option changes now validate and retain supported saved engraving.
Experience enhancement also includes the matching additional level coefficient
of 15. Neither operation requires an engraving catalog for unengraved targets.
This avoids making the newly engraved weapon unusable by those existing handlers.

Fourteen regressions cover exact free mutation bounds, valid tiers, ownership,
origin-rarity compatibility, eligibility/schema/configuration/authentication,
persistent current-state retries, revision limits, rollback and coexistence with
ordinary options/experience after engraving. A detached actual-account check
confirmed the pending first engraving, retained all resources and other fields,
then verified ordinary option acceptance and experience enhancement preserved the
attribute. Same and delayed retries made no writes; captured seeds and the actual
saved account remained unchanged. One subsequent APK engraving receipt matches
the saved attribute and initial ceiling of 1. Assets, hammer inventory, target
experience and limit breaks match the pre-mock baseline. Later ordinary option
edits and other profile fields are outside this live comparison.

## Free ordinary option locking and unlocking

The next unsupported APK route was `/item/change-lock-options`; the owner
requested retaining its stones. Matching native `SendChangeLockItemOptions`
sends `ItemId`, `OptionIds` and Boolean `DoLock`. Separate native lock/unlock
coroutines use that route and refresh their UI from the updated user state;
no additional response payload was identified. The pending request selected one
existing option on an owned accessory. No official response was captured.

The handler shares the explicit free option catalog. It validates owned equipment,
its ordinary option IDs/ranges and any supported saved engraving, then changes
only the requested `Locked` flags. Other flags, every value, engraving, currency,
stone/material quantities and unrelated state remain intact. A real change
increments user revision once; a request already in the desired state saves a
no-op receipt without a profile/revision change. No stones or other payment are
consumed or required by the server's free policy.

Changing a lock discards only that item's pending option-value proposal, in the
same transaction as profile and receipt. This prevents an old proposal from
undoing the newly selected locks; other items' pending work is retained. No-op
requests retain their existing pending work. Retries treat selected ID order as
insignificant and return current state without reapplying older flags after a
later unlock or option change, including after catalog removal. Changed request
parameters under one identity reject. Existing session-epoch retry limits apply.

Fourteen regressions cover exact lock/unlock/resource bounds, no-op semantics,
reopening/reconnect/new login, canonical delayed retries, same-item pending
invalidation, later rolls respecting locks, all-locked eligibility, supported
engraving, ownership/configuration/schema/authentication, revision ceilings and
rollback. A detached actual-account check locked the requested accessory option,
verified a later value roll retained its level, accepted that roll and unlocked
the option, preserving all resources and other fields. Old retries retained the
later unlock without writes. Captured seeds and the actual saved profile were
unchanged. Three subsequent APK lock receipts saved the requested flags, and
their selected values remained fixed through later ordinary value rolls.
Assets, stackables and miscellaneous inventory match the private pre-lock
baseline. Other later equipment changes are outside this live comparison.

## Free relic option changes by source group

The next unsupported APK request was `/item/change-relic-options/v2`; the owner
asked to retain its different payment resource. Native `SendChangeRelicOptions`
sends `ItemId` and `OptionType`; its callbacks read `NewRelicOptions` rows with
`OptionId`, `Level` and `OptionSource`. Native main/sub accessors filter sources
1 and 2 respectively, and separate callers request those option types. Native
`SendApplyRelicOptions` sends `ItemId` and Boolean `Apply`. No official response
was captured.

The pending owned relic has three main rows, including repeated IDs, and two
secondary rows. Its public spec supplies separate ordered pools per group/slot.
The explicit free mock rolls only the requested group's unlocked slots: it
chooses an allowed ID uniformly, then a level uniformly within that ID's public
range. Types and values can change or repeat; a single-ID slot only varies its
level. These are local uniform rules, not reconstructed official rates. Slot
count/order/source, locked rows and the other group remain intact. Repeated main
option IDs are legitimate and are not deduplicated. Jewel slots and set effects
are retained.

Generation stores a proposal without changing profile/revision. Acceptance
changes only the validated selected-group result in `RelicOptions` and user
revision; discard leaves the profile unchanged. No payment resource, ticket,
currency or inventory quantity is consumed or required by the server's free
policy. The matching external catalog is additional to the content pack.

Proposal changes and canonical receipts commit atomically. Old generation retries
display current pending/applied options without drawing or restoring older rolls;
old resolution retries preserve newer proposals and current state. Different
parameters/routes under one identity reject. Resolving requires the original
spec/options and saved public slot pools to remain valid, including after catalog
removal, while preserving later jewel-slot and other unrelated item edits. The
apply body has no proposal ID/type, so a new decision resolves the latest pending
proposal for that item. Existing session-epoch retry limits still apply.

Eighteen regressions cover exact free generation/accept/discard bounds, both
groups, repeated IDs, slot-pool validity, locked/unselected rows, latest-state
retries, reopening/reconnect/new login, catalog removal, later jewel edits,
ownership/configuration/schema/authentication, revision ceilings and rollback.
A detached actual-account check generated and accepted the pending secondary
proposal, generated/discarded a main-group proposal, and verified no-write same
and delayed retries. All currencies, tickets, materials, jewel slots and unrelated
fields were preserved. Captured seeds and the actual saved profile remained
unchanged. Two subsequent APK rolls and two discard decisions were saved, with
no accepted proposal observed. The current relic matches the latest resolution;
stackable payment/material inventory, jewel slots and the unselected group match
the private pre-mock baseline. Other assets and later profile actions are outside
this live comparison. APK acceptance remains unverified.

## Orbital stage closing and victory progress without rewards

The next unsupported request was `/tower-infinity/end-stage`. Its observed
`isCleared` was false, with four integer damage totals; this was not an APK
victory. Native `SendTowerInfinityEndStage` sends exactly `floor`, `isCleared`
and `damages`. `Tower1000Client.SendTower1000End` copies one signed-32-bit damage
value per party member. Its success callback checks optional `AddedItems` and
`TowerInfinity`, then can exit/restart without those payloads. No official end
response was captured.

The authenticated handler accepts configured floors through the absolute saved
floor plus one, including lower floors. Non-clear exits acknowledge with `{}`
without changing any table, profile field, attempt record or reward. Victory
requests require a separate explicit no-reward policy. The owner requested that
victories save their cleared floor while delivering no rewards. The local policy
trusts the authenticated client report, records only a newly highest floor and
increments `UserProgress.Cas`; it does not validate combat outcomes. Older/equal
clears preserve the existing signed floor/revision. A new highest floor is stored
positively; legacy formation and all other tower fields remain intact.

No asset, inventory, user revision, mission counter, reward notice or unrelated
profile/village field changes. No reward is deferred. The victory response
contains current `UserProgress` and top-level `TowerInfinity`. Profile advancement
and canonical receipt commit atomically. Old victory retries preserve later
progress without writes, including after catalog/policy removal. Changed request
parameters under the same identity reject. Repeating a lower floor under a new
identity records a receipt without resetting progress or giving anything.
Existing session-epoch retry limits still apply. No missing attempt is invented
for a phase already open before backend reload.

Five non-clear exit regressions cover native damage/schema/authentication bounds,
earlier/signed floors, matching catalog/prologue guards, repeat requests and
reopening/reconnect/new login without writes. Ten completion regressions cover
next-floor-only advancement, exact profile/resource boundaries, lower-floor
repetition, ordered progression/current-state retries, explicit no-reward policy,
revision ceilings, rollback and catalog removal. The observed actual-account
non-clear request leaves every saved table unchanged in a detached check. Separate
**constructed** victory requests advance only the highest floor/progress revision,
retain progress on earlier floors and preserve later progress on old retries.
Captured seeds and the real saved account remained unchanged. The APK non-clear
retry requires backend reload; an actual APK victory still needs to be tested.

## Read-only own profile card

Opening the owner's profile failed at `/user/get-user-profile-card`. The pending
native request contained only an integer `UserId` matching the saved local user.
`SendGetUserProfileCard` confirms that request key. The profile popup's success
callback reads `UserProfileCard` and `UserStickerPacks` directly; their native
types require a card object and an integer-array pack list. Attached stickers
are a list, while scarecrow scores are a signed-64-bit array. No official card
response or separate sticker collection was captured during import.

The authenticated read accepts only the saved local user's positive signed-32-bit
ID. It returns the current saved user, arena/Colosseum records, captured champion/
death-match records and signed Orbital floor. The native own-profile callback
replaces its user/avatar/badge and locally available records with current client
resources before rendering. Uncaptured sticker ownership, attached stickers,
selected board and social records are explicitly empty/unknown in this view;
they are not recovered official state. No account field or ownership collection
is overwritten. Other-player lookups and profile customization remain unsupported.

Eight regressions cover authentication/request/identity bounds, full current
user and record preservation, later edits, signed floors, reconnect/reopening,
unknown/invalid records, unsupported writes and successful reads while SQLite
writes are disabled. A private protocol check read the actual account twice
through a read-only SQLite connection, retaining the saved user/floor with zero
writes and unchanged profile. After reload, one APK card request completed, then
the popup's friend refresh failed at `/friend2/enter` before rendering. Opening
the card does not spend resources, change revisions, save a
receipt, grant rewards or migrate the account.

## Empty friend refresh required by the profile popup

The native profile popup waits for `FriendClient.UpdateFriendDict` before setting
up the visible card. `SendEnterFriend2` sends `/friend2/enter` without a body. Its
success callback consumes `FriendInfos` as a dictionary keyed by integer user ID
and a Boolean `IsMigrated`; the latter can enable a first-entry migration notice.
Only this local prerequisite is implemented. No official response or peer
records were captured.

Authenticated parameterless entry now returns `FriendInfos={}` and
`IsMigrated=false`. This explicit empty local view does not claim restored
official friends or an executed migration. The saved `UserFriend`, including
friend/request counts, settings, gift dates/counters and revision, remains
unchanged and is not sent back as a replacement. No resources, requests,
receipts, rewards or migration state are saved. Friend mutations and other-player
lookup remain unsupported.

Three regressions verify sign-in/native empty-body/exact-schema handling,
imported-count/settings/gift preservation, social-write rejection and the
profile-then-friend sequence across reconnects while SQLite writes are disabled.
The same sequence passed twice against the actual database opened read-only with
zero writes and unchanged full profile. After reload, one APK friend-entry request
completed. Visible profile rendering and the complete friend UI remain unconfirmed;
successful API calls alone do not establish working social features.

## Guild menu notification indicators

The next unsupported APK request was `/guild/red-dot` while entering the guild
area. `SendGuildRedDot` sends no body. The guild-entry success callback reads four
top-level Boolean fields: `Raid`, `Meteor`, `PunchKing` and `GuildWar`. Closing the
Punch King and guild-war reward shop overlays reuses the same endpoint and their
respective flags. No official response was captured.

The authenticated parameterless read now returns all four flags as false. These
are explicit inactive local-mode indicators, not recovered official notification
state. The response does not replace membership, clear pending rewards, mark
attendance, grant anything or change profile revisions. Guild gameplay,
membership mutations and reward claims remain unsupported.

Two regressions cover authentication/request bounds, native empty-body framing,
all four Boolean flags, fresh/imported accounts, reconnects and no-write reads
with positive synthetic membership/pending-reward state retained. Three request
variants passed against the actual account opened read-only with zero writes
and unchanged full profile. One subsequent APK notice query completed, then
stopped at `/guild-raid2/reset`. Visible menu entry/shop return remain unverified.

## Preserved membership and non-mutating raid menu preparation

The next unsupported request was `/guild-raid2/reset` with `IsPartial=false`.
`SendResetGuildRaid2` derives that Boolean from whether `UserRaid` was fetched,
unless its caller forces a full refresh. The guild-menu and castle entry routines
read the response's `ClaimRaidSeasonReward` flag before requesting season rewards.
This is menu preparation, not a player command to delete saved account data.
The local handler accepts exactly a Boolean `IsPartial` and returns
`ClaimRaidSeasonReward=false` for full/partial requests. It does not report a
completed season reset, mark rewards claimed, send `AddedItems` or replace
`UserRaid`, which was not captured separately. No attempt/receipt is saved.

Read-only inspection found that the saved account has a guild membership but
the client's `GuildClient.Guild` was null. The old empty `/guild/get-my-guild`
response was inconsistent with that membership; the raid entry routine would
dereference the guild after receiving its preparation response. Fixing only
the unsupported route would leave that client-side failure in place.

`/guild/get-my-guild` now validates the native nullable signed-32-bit `Hash` hint
and the saved member's ownership and guild ID. Accounts without membership retain
the empty guest view. Registered accounts receive an explicitly named **Local
guild** using the preserved guild ID and complete own-member row only. The
displayed member count is one, not the official roster size. The guild achievement
view uses only that member's saved achievement ID/points; their reward flags remain
unchanged. The original guild name, other members, applicants, leader, emblem,
creation time and notices were not captured. The local name, ancient date/zero
emblem, empty leader/introduction and empty notices/applicants are placeholders,
not restored official details. Guild creation/membership changes remain unsupported.

Native `RefreshMyGuild` consumes `Guild`, `GuildMembers`, `Applicants`, `Hash`
and `DismissedMasterName`; its callback skips replacement when the hash matches.
The local response supplies non-null lists, an empty dismissal name and a stable
nonzero content hash, distinct from the previous empty view's zero. Later saved
member changes produce a new hash. Native notices use a `GuildNotice` object with
an empty `Notice` list and zero `RepresentativeNotice`, not an empty list in place
of the object. No guild view or cache hash is persisted in SQLite.

Four regressions cover authentication/cache schema, full/partial/reconnect
preparation, no-write preservation of membership/raid currencies/pending rewards,
unsupported battle/claim operations, the own-member-only view and stable/updating
hashes, and malformed ownership/identity/achievement/cache inputs. The actual
account's own-guild read and both raid cache-hint variants passed through a
read-only connection with zero writes and unchanged full profile. This does not
establish actual raid gameplay or a successful rendered guild menu.

After backend reload, restart the APK once so the startup own-guild query can
populate this local view. Reconnect alone can resume the pending preparation
request while retaining the older null guild cache. Leave the existing bridge
and CDN running. Original guild recovery and cache-independent raid gameplay
remain outside this change.

## Fresh local raid entry and season selection

After the membership/preparation fix, the APK reached `/guild-raid2/enter`.
The native builder sends the Boolean `IsPartial` resource-cache hint. Its success
callback reads `GuildRaidStatus`, nullable integer `GuildRanking`, integer
`FeverBossIdx` and `Round`, a scalar signed-64-bit `RoundExp`, and `AddedItems`.
The local opt-in response initializes a fresh personal raid for the selected
season, round one and zero damage, with no ranking or added items. Entry requires
completed prologue and owned guild membership. Preserved non-null raid progress
rejects rather than being replaced. Re-entry resets this experimental view;
there is no persistent raid damage, round progression or battle-result handling.

The resource update includes only `UserRaid.UserId` and `UserRaid.Raid`. Native
inspection of the registered `UserRaid` handler establishes that it populates
the existing object and replaces supplied properties; omitted properties remain.
Other-mode currencies, flags and guild-war state are deliberately omitted.
The SQLite profile, including any saved other-mode fields, remains unchanged.

An external matching catalog supplies public season/boss/stage/first-round IDs
and global periods. The private Windows lab catalog has 46 default/global season
definitions from the preserved client. These IDs are client catalog IDs, not a
claim to reconstruct every official raid ever held. Public data and operator
selection stay outside Git. No official raid response, historical damage,
rankings, attempts or rewards were captured.

From the repository root, using the backend's reference directory:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales raid-season list --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales raid-season set 12 --reference-dir local/client-data/reference
```

`list` marks the selection with `*`, shows original periods/boss sets and reports
whether its local calendar has been prepared. `set` accepts only catalogued IDs,
requires matching `static_data_get.bin` and prepares an immutable static body
before atomically replacing `guild_raid_selection.json`. It does not open SQLite
or change the server clock. After **each selection, fully close and reopen the
game** so its static tables reload; leaving the menu or reconnecting is
insufficient. The first code update also requires a backend reload.

The initial ID-only implementation was incomplete. Read-only inspection showed
that the running client actually held personal raid season 27 while the same
bosses remained visible. Native `UserRaid.get_GuildRaid2SeasonId` checks
`IsVaildSeasonId`: an expired selection falls back to `GetPrevSeasonId` before
the boss/background widgets use it. The previous inference that those widgets
would directly display any supplied historical ID was incorrect.

`raid-season set` now prepares a copy of the original static response with only
the selected raid's `seasondate` global-service row activated locally from
2000-01-01 through 2099-12-24. An existing global reward-until date is adjusted
to 2099-12-31 for ordering consistency; no reward handler is enabled. Other dates,
service variants, seasons, bosses and tables retain their original values.
The original external body is never overwritten. The selected calendar and
`__checksum__` records receive correct SHA-256 hashes and increasing native
revisions; bootstrap serves the prepared body and a consistent update checksum.
The native date guard then sees an active period without a global clock change.

Normal battle authorization, results and reward claims remain unsupported;
test these incrementally. The native off-season practice loader was inspected,
but it does not bypass the effective-season getter used by the boss menu.
Ranking reads use the empty local view described below. The corrected historic
boss display and combat still require an actual APK check after full restart.

Eight regressions cover authenticated entry, exact cache schema, membership,
native reply shapes, omitted unrelated resources/rewards, read-only repeated
entry/reconnect, live selection, malformed/missing catalogs, preserved-progress
guards, unknown operations and atomic-write failure. The real saved account
passed both entry variants through a read-only protocol session: zero SQLite
writes, selected season 46, no added items and unchanged full profile. This was
a host check. Subsequently the user reported that raids loaded at least
partially, and the actual entry request completed before the classification
refresh failed. This does not establish successful combat or complete menu UI.

Six additional calendar regressions cover historical activation, preservation
of other table rows/service dates/binary records, cache checksums, successive
selection revisions, legacy settings, missing/corrupt source/artifact guards,
LZ4 match/literal/window boundaries and failed atomic publication. Expanded
selector tests require restart guidance and preserve the old selection when
publication fails. The private full-table preparation changed exactly one
calendar row and the two containing/checksum records, preserving all bosses and
other records. The actual source body and saved account remain unchanged.

## Empty local raid classifications

The next unsupported APK request was `/guild-raid2/get-guild-rankings`.
Read-only inspection of the pending packet confirmed `{"SeasonId":45}`.
The native builder wraps the integer season ID; the timed ranking refresher
reads the personal raid's current client-cached season. This can differ from the
operator's latest selection while a scene/refresh is in flight. Ranking reads
therefore accept any season present in the explicit matching catalog, without
changing that selection. Authentication, completed prologue and owned guild
membership are required; missing/foreign catalogs, unknown seasons, non-integers
and extra request fields reject.

The guild-ranking callback consumes `Rankings` as a list of guild ranking
entries and `CutOff` as `Dictionary<int32,int64>`. The cut-off widget converts
that dictionary to a list, so an object is required even when empty. The local
response is `{"Rankings":[],"CutOff":{}}`. The callback derives its update
timestamp from client server-time; no timestamp, score or reward is invented.

Native `GuildRaid2RankingResources.StartTracking` also creates the member-ranking
refresher. Its builder uses the same season request shape and its callback reads
`Rankings`, reprocesses member rows and has a native fallback for its own empty
ranking entry. The companion `/guild-raid2/get-member-rankings` read therefore
returns `{"Rankings":[]}`. This companion contract is inferred from native code;
it was not the observed failing APK packet. Neither response includes profile
resources, rewards, attempts or progress updates. Saved raid progress is not
read as an official classification or replaced by these reads.

Three additional regressions cover authentication/schema/ownership checks,
known-season reads across selection changes and reconnects, missing/foreign
catalogs and preservation of all saved tables, pending rewards, other-mode
currencies and operator selection with SQLite writes disabled. Both routes
passed read-only checks against the actual profile for the pending and newly
selected seasons: zero database writes and unchanged full profile/selection.
Post-fix APK ranking refresh and subsequent combat remain unverified.

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
