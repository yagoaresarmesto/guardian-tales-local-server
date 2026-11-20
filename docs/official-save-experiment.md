# Official-account preservation experiment

Account snapshot import and local save restoration are available on `main`.
The work began on `experiment/official-save-import`; the observations below
record preserving an owner's existing 3.57.0 European account for this backend.
An experimental importer now loads a validated private snapshot into a new
SQLite state directory. Account fetch, preserved startup reads and local sign-in
passed a private input check. **The APK now reaches the imported lobby**, following
a village-request compatibility fix. The owner also verified entry into summons
and one- and ten-hero draws using selectable controllers in the APK. Wishlist
changes and the other supported payment types have synthetic coverage only.
Unlocked systems are not automatically implemented by import.

## Backroom entry with an imported account

The lobby-to-Backroom transition stopped at unsupported `/my-room/enter`.
Read-only request inspection found exactly `IsPartial: false`; the native builder
always sends that Boolean. Its coroutine consumes `UserMyRoom` and NewGetItems,
and the native room singleton has Used, nullable Avatar Hero, X/Y offsets,
WallPaper, Music and Favorites. That separate resource was not captured among
the imported profile's seventeen sections.

Entry now provides a read-only local default view, with no account or startup
data replacement. The default wallpaper/music IDs come from free Default
MyRoomMedia in the matching items table. Null Hero follows the current owned
representative and costume. Zero wallpaper retains the existing bundled room
background; the standalone default wallpaper image is absent from the prepared
pack. Default music uses the present bgm_lobby_private bundle. NewGetItems and
Favorites are empty. This does not restore uncaptured room customization or add
paid/limited media; room edits, purchases and rewards remain separate contracts.

Twelve synthetic regressions pass. The actual pending request, partial true and
repeated entry passed on an in-memory account backup with SQLite query-only
enabled, an identical database dump and zero diagnostic source writes. After
backend reload, the user confirmed Backroom loads the character and returns to
the lobby. Two entry calls completed with no rejections. The entire raw account
row, imported startup data, current presets and 42 existing receipt/claim tables
matched the pre-fix backup. No room table was created. SQLite integrity passed,
with zero diagnostic source writes. Only the backend needs a restart.

## Training Room entry with saved assignments

The next entry error was unsupported `/training-room/enter`. Its native builder
passes a null body, and the success callback only opens the scene. Training data
was already captured in `User.TrainingSlots`: the real account contains six
records, including occupied weapon/merch slots, empty character slots, all nine
native benefit flags and retained reactivation timestamps.

The new read returns only current User Id/Cas/TrainingSlots. It preserves the
full slot map and does not initialize/unlock slots, place/remove assignments,
reactivate cooldowns, alter benefits, write item statistics or spend gems.
Expired/future timestamps and unknown saved metadata remain verbatim. No new
catalog is required. Placement, removal, unlock and reactivation keep their own
unimplemented mutation contracts.

Twelve regressions pass. Native no-body framing, null/empty-object aliases and
repetition passed against a memory backup of the actual six-slot account with
SQLite query-only enabled. The entire database dump stayed identical, with zero
diagnostic source writes. The user confirmed the APK loads Training Room with
the saved slots intact. Two entry calls completed with no rejections. The entire
raw account row, imported startup data, current presets and 42 receipt/claim
tables matched the pre-fix backup. SQLite integrity passed with zero diagnostic
source writes. Only the backend needs to restart after updating.

## Inventory protection locks

The prepared Android 3.57.0 client stopped at `/item/unlock` with an
`itemIndexes` array containing one owned equipment inventory ID. Native
`SendLockItems` and `SendUnlockItems` confirm `/item/lock`, `/item/unlock` and
the exact lowercase key; their success callbacks read no response fields.
These observations identify the request contract, not an official captured
response.

The local implementation resolves bounded batches dynamically across the three
saved item inventories and persists only selected protection flags plus one
account revision. It returns current `User` through the existing resource
application path. Receipts commit atomically with the profile; old retries
return current state without restoring an old lock or inventory snapshot.
No balance, item quantity, equipment assignment, option value/lock, engraving,
pending reroll proposal or imported startup seed changes. No catalog additions,
save reimport or CDN/bridge restart are required. Equipment selling/extraction
remain outside this change.

Fifteen synthetic regressions cover single unlock, mixed inventory batches,
preservation, canonical and stale retries, reconnect/new login, receipt and
profile rollback, revision limits, fresh-account/prologue guards, malformed or
ambiguous ownership and the 256-item local bound. The captured request and all
2,080 owned inventory IDs passed on an in-memory saved-account backup, with zero
diagnostic source writes. The user then confirmed both protection controls and
persistence after reopening the APK. Four receipts match the final flags, and
the full saved profile matches the pre-fix backup with only the recorded flags
and four user revisions applied. No new lock-route errors appeared; SQLite
integrity passed. See [verification status](status.md).

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

## Restore an existing local account into a clean client

An existing local SQLite backup is different from the original snapshot JSON.
Restore the complete `server.sqlite3` into a separate empty state directory to
retain later equipment changes, presets, currencies, receipts and local identity.
Stop the source backend before preparing the backup, verify SQLite integrity and
keep the original copy private. Refuse an existing destination database rather
than overwriting another save. The `snapshot import` command above accepts the
validated JSON format; it does not restore an SQLite backup.

Use an independent checkout, virtual environment, compatible content, certificates
and [dedicated MuMu instance](mumu-client.md). Select the restored state explicitly
with `serve --data-dir`; the database stays on the host. Install the matching base
APK and split into the new instance without copying Android preferences, SDK
credentials or downloaded game data. The local Guest option supplies local
platform credentials and selects the account already in that state directory.
Local Raid, Dungeon Kingdom Arena and Guild War selectors live in the reference
directory, separately from SQLite. Configure the desired local mode selections
for that directory and fully reopen the game after changing its static tables.
Restoring the account database alone does not activate those practice modes.

The Windows reproduction on `experiment/clean-apk-import` used a backup whose
57 tables matched the stopped source, plus a newly installed 3.57.0/431 APK.
The public content check passed for 15,915 resources and 19 reference files.
An in-memory check passed local guest sign-in, exact profile fetch and the four
preserved startup reads. The clean APK subsequently completed local platform
sign-up, game sign-in, resource downloads and account fetch, then its first
village request was rejected because `lastLobbyShopUpdated` was null. This is a
missing client cache hint. It is now accepted with either Boolean partial flag,
returning the full preserved village with no writes. Invalid non-null timestamps,
wrong types and unexpected fields still reject. A new authenticated-session
regression and the real request on an in-memory backup passed; the snapshot and
bootstrap modules pass 34 tests. After reloading the backend and restarting the
APK, the owner confirmed the lobby loads. That restart reused the local session
created during the first attempt.

A final repeat cleared only the new instance's Android app data, retaining the
matching APK and the restored host database. Before launch, the client had zero
downloaded files and no saved preferences. The client then completed a new local
platform sign-up, game sign-in, account fetch and village entry. The owner
confirmed the imported heroes and equipment in the lobby. No new rejected or
unsupported API counters appeared; SQLite integrity passed and the canonical
saved profile was identical to its pre-reset backup. This verifies fresh local
session creation and restored-profile lobby entry without reusing Android account
caches. It does not establish additional gameplay support.

After this cold start, the owner also completed **Download All**. All 1,738
selected on-demand bundles matched the local content manifest, with no missing
or mismatched bundles. **Check and organize downloaded files** also completed;
all 1,738 hashes still matched afterward. This selected set excludes ZIP staging
files, ETag files and the unselected Japanese voice/dialogue bundles. The lab
content started with the published content package and added French locale
resources, localized banners and DKA menu/interface backgrounds; those supplements
are not yet included in the published package. See the
[download transport verification](mumu-client.md#download-transfers-through-adb-reverse)
for the preceding transfer correction.

The same clean client subsequently switched text from Spanish to English and
French. The owner confirmed the lobby and hero/inventory texts in both languages.
The three cached locale text files matched the local manifest. The first DKA
entry rejected because this reference directory had no arena selector. The real
request passed without writes on an in-memory account copy with variant 1/day 1;
after selecting it in the lab and reopening the client, the owner confirmed the
French DKA menu and combat entry/return. Two start/end cycles completed without
new rejected or unsupported API counters. The
[arena selector guide](reference-data.md#dungeon-kingdom-arena-practice-selector)
describes the required separate configuration.

The owner also verified the French Raid menu, combat and return with local
season 46 in the same clean client. The start and end routes succeeded without
new rejected or unsupported API counters, and the saved profile remained
identical to its pre-reset value. An in-memory preflight also passed the composed
Raid 46 and DKA 1/day 1 static selection without account writes.

## Current implementation boundary

The imported account uses a protected network mode. Account fetch and known reads
remain available; the four preserved startup responses replace their empty local
counterparts. The preserved collection supplies its own new-entry markers.
Other empty social/catalog scaffolding still has the limitations documented in
[status](status.md). Health exposes `imported_account: true` and lists the enabled
mutation routes in `imported_account_mutation_routes`.

Account nickname changes are also enabled through `/user/change-name`, with the
owner-requested free/no-word-filter policy. Only the account name and existing
owned guild-member name, their revisions and the retry receipt change. No paid
or free gems, spending counters, inventory, progress, imported source or preserved
startup reads are modified. The exact pending request passed on an in-memory
backup of the real account with a read-only/query-only source. The static overlay
also passed against the effective real mode tables, retaining other constants
and all other table records. The user then confirmed the APK displays cost zero
and retains the changed nickname after reopening without spending gems. A
read-only live audit confirmed one completed change, only account/guild-member
names and revisions updated, unchanged assets/spending and other profile/startup
data, and valid SQLite integrity. The name list refreshed with HTTP 200 and was
subsequently reused with 304; a previously blocked name was not separately tested.
Restart both backend and CDN, then fully reopen the client to reload the zero
cost and empty localized name list. The existing bridge can remain open. See
[the nickname contract](reference-data.md#free-local-nickname-changes).

Twenty-three mutations are now enabled: `/item/change-options`, `/item/apply-options`,
`/item/change-relic-options/v2`, `/item/apply-relic-options`,
`/item/change-lock-options`,
`/item/engrave-weapon`,
`/item/enhance-weapon`,
`/item/limitbreak-weapon/v2`, `/summon/set-select-character`,
`/summon/select-character`, `/summon/select-weapon`, `/summon/character`,
`/summon/weapon`, `/summon/set-select-weapon`, `/preset/set-selected-preset`,
`/preset/set-presets`, `/preset/delete-preset`, `/user/charge-stamina`,
`/user/charge-stamina-by-gem`, `/user/claim-daily-attendance`,
`/lobby-village/harvest-all`, `/lobby-village/harvest-basecamp`,
`/lobby-village/receive-gift`, `/lobby-village/remove-obstacle`,
`/user/guardian-mastery-level-up`, `/user/reset-guardian-mastery-level` and
`/tower-infinity/end-stage`. The summon routes
use the existing local selection/draw catalogs,
atomic payment/reward transactions and session-scoped retry receipts. Supported
draws are one or ten heroes using free gems, ordinary controllers or selectable
controllers. Preset selection changes only the saved Orbital or shared
Raid/Conquest pointer and account revision, with atomic retry receipts. Editing an existing
Orbital preset saves its definition separately from the captured seed; a matching
slot-count catalog also permits creating a missing definition. Deletion
removes one existing Orbital or Raid/Conquest definition and clears only its
mode's selection if necessary. Natural stamina
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
Importing an official profile does not recover official rates, promotions, pity
or special payment variants. Local weapon draws are described below. An imported hero whose origin cannot
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

## Local weapon draws using the hero-draw flow

The next summons error was `/summon/select-weapon`. The actual pending request
contained `Count=10` and `SummonCostType=0`. Read-only process inspection matched
its builder to the inspected 3.57.0 native code. `Gacha.GetDoGachaPacket` selects
this weapon route, while the same `DoGacha` coroutine parses `Summons` through
`SummonResultData.Parse`. Weapon results use native `Type=0` and the same seven
result fields as hero results.

The local handler follows the existing hero draw's cost/weight configuration,
signed-in epoch/sequence identity and current-resource/frozen-result response
pattern. Weapon pools and initialization come from the matching external client
tables, with the local category mapping documented in
[reference data](reference-data.md#local-weapon-draws). Five saved eligible epic
weapon designs form the Unique pool; repeated designs grant separate weapons.
One/ten draws support free gems and ordinary/selectable controllers. Each result
grants the configured client metal amount and one local mileage. No hero crystal
conversion, pity, promotion reset or paid/discount/free-event behavior is inferred.

One transaction saves payment, new inventory IDs/weapon rows, metal/mileage,
historical weapon-draw count, user/record revisions and the frozen result receipt.
An exact retry returns those results with current state and cannot pay/grant twice
or undo a later weapon edit. Existing gear, hero progression, shop/wishlists and
captured startup data remain intact. Existing saves add receipt storage at normal
backend initialization; no new external catalog or save reimport is required.
Weapon wishlist registration is described below.

Eighteen regressions cover fresh/imported accounts, all supported payments,
single/batch draws, distinct inventory allocation for repeated designs, saved
wishlist/pool guards, malformed requests, invalid definitions, insufficient funds,
numeric limits, rollback/RNG failure, reconnect/reopening and current-state retries
after later edits or catalog removal. The real pending ten-gem draw passed on an
in-memory account copy with every unrelated profile field retained, exact expected
costs/rewards and zero writes through the read-only/query-only source connection.

After reloading only the backend, the owner confirmed weapon draws work and
remain in inventory after reopening the game. A consistent read-only comparison
with the private pre-fix backup observed nine completed requests: one ten-gem draw
and eight single selectable-controller draws. All 18 recorded weapons were
present, with exactly 2,700 gems/eight controllers spent, 180 metal and 18 mileage
credited, and the historical weapon counter increased by 18. All previous weapon
rows, heroes, shop state and hero crystals were retained. SQLite integrity passed;
no weapon-draw requests were rejected and one older unsupported call remains
historical. These totals describe that verification snapshot; further user draws
are independent operations.

## Regular paid-gem banners and daily discounts

The paid-gem error used a different route from wishlist draws: `/summon/weapon`
with `IsPickUp=false`, `PickUpKey=0`, `Count=1` and `SummonCostType=1`. Its native
builder matched the running 3.57.0 code in read-only inspection. The equivalent
hero builder sends the same fields to `/summon/character`. The native enum
distinguishes Normal=0, Discount=1, FreeEvent=2, Ticket=3, PaidGem=4 and
SelectableSummonTicket=5. The captured request was the daily paid discount.

Both regular routes now reuse the existing draw handlers with a shared payment
validator. They use the full local eligible pools, retaining wishlists, rather
than applying wishlist selections to ordinary banners. The daily charges only
paid-gem asset 70002, at the client constant price of 100. Its independent hero or
weapon timestamp under banner key `"0"` and shop revision commit in the same
transaction as payment, grants, counters and the frozen result receipt. Other
timestamps/event fields remain intact. The local UTC clock/StartOfDay contract
sets a UTC-midnight reset. New identities cannot bypass the limit; exact retries
return current state and frozen results without another charge.

Regular full-price paid type 4 supports one/ten draws at the matching 300/2,700
prices without consuming the daily limit. Free gems and controllers remain
separate balances. Pickup/event banners, discount packages and paid wishlist
variants remain guarded, as detailed in
[the regular-banner contract](reference-data.md#regular-banners-and-paid-gems).
No receipt migration or extra external catalog is required.

Twenty regressions and a read-only-source/in-memory protocol check cover both
families, currency isolation, independent/UTC daily limits, full-price payments,
request/state validation, rollback, imported/fresh accounts, duplicate evolved
heroes and current-state retries after reopening or catalog removal. The actual
pending weapon request and equivalent hero request each paid 100 on the detached
copy, with all unrelated fields preserved and zero source writes.

After backend reload, the owner confirmed both daily operations and persistence
after reopening. A consistent read-only verification snapshot found one daily
receipt for each route, exactly 200 paid gems spent and both daily timestamps
saved. Two separate wishlist test pulls spent 600 free gems, matching their own
receipts. Previous heroes/weapon rows and controller inventory were preserved;
shop changes were limited to the expected daily timestamps/revisions. Both
regular API calls completed without rejections, SQLite integrity passed and
diagnostic connections wrote nothing. The older unsupported weapon call remains
historical.

## Weapon wishlist candidates and registration

The weapon wishlist initially offered no choices because `/summon/on-event`
returned an empty `SelectableWeapon` list; the matching registration operation
was also absent. The native `SummonSelectableWeaponSpec` model and
`SendSummonSetSelectWeapon` builder establish candidate item-spec IDs and exactly
`RequestItemIds` for registration. The wishlist coroutine applies the shared
UserShop resource after success.

The catalog now derives 133 eligible epic weapon choices from the same external
definitions used by local weapon draws, with no fixed candidate list or extra
catalog. Rows use the native **ItemSummonCategory.Exclusive**, not the hero
category enum. That distinction matters during JSON model population: an invalid
weapon category can leave later collections null and stop `GetMediaList` before
the lobby loads. A dedicated regression bounds weapon category labels and keeps
the remaining native media collections present.

Entry and event replies share a combined hero/weapon checksum, so existing
installations refresh the former empty weapon catalog. Hero rows remain unchanged.
The authenticated setter accepts zero to five distinct eligible design IDs in
order, supports partial lists and clearing, and returns the current UserShop.
Only its selected-weapon list and revision change; identical current selections
do not write. No resources or inventory are spent/granted, and all hero/draw/daily
state is retained. Existing account files require no migration or reimport.

Fourteen regressions cover native categories and cache shapes, combined cache
refresh, ordered/partial/empty choices, no-op revisions, invalid inputs and saved
state, rollback, persistence/reopening, fresh authentication/prologue guards,
hero-only/weapon-only catalog behavior and use of the new wishlist by subsequent
draws. A private read-only-source/in-memory check exposed all 133 candidates,
retained hero rows, changed only the expected shop fields and recorded zero
source writes. After backend reload with the corrected enum, the owner confirmed
the lobby loads and the wishlist saves across reopening. Six actual registration
calls completed without rejections. A read-only comparison with the private
pre-fix backup found five eligible saved choices and exactly six shop revisions;
only the wishlist/revision changed. User resources, inventory, heroes, records and
captured startup reads were identical, and SQLite integrity passed. No save or
client-data reset was needed.

## Imported client compatibility checks

Other hero and equipment actions can be enabled in coherent groups with their
own validation, transaction and retry tests. A private protocol-level check already
confirmed profile equality after reopening, local sign-in identity, completed
prologue state and the preserved startup replies. This is distinct from an APK
result or a claim of complete account preservation.

The first imported APK attempt stopped at `/lobby-village/enter`: the preserved
read handler had incorrectly required every startup request to be empty. The
native `SendEnterLobbyVillage` builder and the live pending request both establish
`isPartial` as a Boolean and `lastLobbyShopUpdated` as a nullable timestamp. A
cached installation supplies an offset timestamp; a clean installation supplies
null. The handler validates those exact cache hints, including seven-digit .NET
fractional seconds, and returns the preserved full village without refreshing
its shop or changing the account. Other preserved reads still reject unexpected
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

This initial mutation accepted only that mode's already captured party presets;
the later Raid/Conquest selection extension is described below.
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
`/user/charge-stamina` request. Later sections cover Orbital definition mutations
and Raid/Conquest selection; other selection groups and formation/result writes
remain separate contracts.

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

The later Raid deletion report used the same native endpoint and request shape
for the currently selected shared Raid/Conquest team. Its former Orbital-only
guard rejected that valid mode. Deletion now also supports existing definitions
in `[700,800)`, resetting only `GuildRaidAndConquest` when needed. Other teams,
orders, selected modes, inventory, currencies and saved progress remain intact.
Seven regressions cover Raid removal, retries after slot recreation and later
selection, reopening, last-team removal, invalid state, overflow and rollback.
All 53 focused preset tests pass. The exact pending request passed on an in-memory
backup of the real account with zero writes to the read-only/query-only source.
After backend reload, the owner confirmed deletion succeeds, the other teams
remain and the removed team stays absent after reopening. The coherent read-only
save audit found two removals around one explicit recreation/selection of that
slot; its final definition was absent. All surviving definitions/orders, other
mode pointers, owned inventory, assets, progress and imported startup seed matched
the backup. Group/user revisions advanced three times, matching those operations;
SQLite integrity passed. Only the backend needs a restart; the existing save and
CDN/bridge configuration are retained.

## Reordering Raid and Orbital Lift presets

The next report came from `/preset/reorder-preset`, which had no server handler.
Read-only inspection found native `PresetType=7` and a 30-element `Order` array.
The matching popup writes each saved ID's list position at index `Id % 100`;
unsaved slots retain zero. Orbital Lift uses the same builder, with type 4 and
five slots from the matching client constants. Its callback checks request
success; the shared resource handler applies the current preset group.

Both modes now update only their saved definitions' `Order` fields and the group
revision, atomically with an epoch/sequence receipt. The response contains all
current definitions, so the native dictionary replacement retains other modes.
The account profile and selection pointers remain byte-for-byte unchanged.
Replays return the latest group without restoring old order or deleted/recreated
slots. Existing editing, selection and deletion keep using the original IDs.
Other ordering modes remain unsupported, and definition edits still cannot
smuggle an order change through `/preset/set-presets`.

Thirteen regressions cover both modes, native framing, moves, mutation limits,
retries/reopening, slot recreation, no-ops, invalid state, overflow and rollback.
All 31 focused order/deletion/import tests pass. The actual Raid request and an
equivalent Orbital request passed on an in-memory backup of the current account;
a subsequent selected-Orbital deletion also preserved Raid teams/order/selection.
The real SQLite connection was read-only/query-only, with zero diagnostic writes.
The user confirmed both modes work and retain their order after reopening.
Read-only verification found two Raid and one Orbital reorder, plus four explicit
Apply calls and an Orbital deletion during testing. All eight requests replayed
from the backup on a memory copy to exactly match the live account and group.
Each reorder retained raw profile bytes; selection/account-revision changes came
from the explicit Apply/delete calls. Final saved IDs, names, characters, gear and
physical array order matched the backup, as did assets, other profile sections
and imported startup data. SQLite integrity passed with zero source writes.

The later Guild War reorder failure sent type 18 and 30 positions. Native
`GetBasePresetId` explicitly maps type 18 to 700, and `PresetCount` uses the Raid
entry at index 6. Its own static-table entry is zero, and no 1800-ID definitions
were present. The backend now resolves this alias to the existing Raid/Conquest
group, so both menus intentionally share ordering. Five regressions cover alias
resolution, shared/no-op behavior, retry/reopening and original-ID selection and
deletion. All 47 focused preset tests pass. The exact pending request passed on
an in-memory copy of the actual account, preserving raw profile and imported
seed; an equivalent type-7 request retained the same revision. The source stayed
read-only/query-only with zero writes. The user confirmed Guild War reordering
works and remains after reopening. Live read-only verification found one type-18
reorder, two explicit selections and a later deletion across two sessions. Replay
from the backup on a memory clone exactly matched the live profile and group;
the reorder itself retained raw profile bytes. Remaining team definitions and
relative array order, assets, other profile sections and captured startup data
were preserved. SQLite integrity passed with zero source writes.

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
is overwritten. Other-player lookups, boards and stickers remain unsupported.
Owned representative-hero/frame and client-managed badge selection are described
below.

Eight regressions cover authentication/request/identity bounds, full current
user and record preservation, later edits, signed floors, reconnect/reopening,
unknown/invalid records, unsupported writes and successful reads while SQLite
writes are disabled. A private protocol check read the actual account twice
through a read-only SQLite connection, retaining the saved user/floor with zero
writes and unchanged profile. After reload, one APK card request completed, then
the popup's friend refresh failed at `/friend2/enter` before rendering. Opening
the card does not spend resources, change revisions, save a
receipt, grant rewards or migrate the account.

## Selecting an owned profile portrait

Changing the profile picture reached the previously unsupported
`/user/select-representative-character` route. The actual pending request contained
exactly `CharacterId`, a positive signed-32-bit owned **inventory character ID**.
It is not a character-spec ID. Read-only process inspection matched the native
`SendSelectRepresentativeCharacter` builder to the inspected 3.57.0 code. The
profile popup's `LoadRepresentativeCharacter` coroutine reads no response fields;
the shared resource handler applies `User.RepresentativeCharacterId` and refreshes
the portrait from the client's existing owned-character registry.

The authenticated operation now accepts any unambiguous owned character from the
saved roster after the prologue, including imported accounts. It needs no fixed
hero list or extra external catalog. A real change atomically saves only
`User.RepresentativeCharacterId`, `User.Cas` and a request receipt. Selecting the
current character does not rewrite the profile or increment its revision. Invalid
or unknown IDs, spec IDs, Boolean values, unexpected fields, duplicate saved IDs
and exhausted revisions reject without writes. A matching delayed retry returns
the current selection rather than undoing a later choice or other local progress.

Replies contain only `User.Id`, `User.Cas` and `User.RepresentativeCharacterId`.
Inventory, hero state, equipment, presets, currencies, other profile sections and
captured startup reads are retained. Existing saves get the receipt table during
normal backend initialization; updating requires no account reimport or resource
pack change. Frame and badge selection are separate operations below; boards,
stickers and another player's profile remain unsupported.

Twelve regressions cover arbitrary/large rosters, compact replies, fresh/imported
accounts, authentication/prologue guards, malformed and unowned IDs, null/default
saved portraits, atomic rollback, no-op revisions, reconnect/reopening, delayed
retries and existing-database initialization. The real pending request and every
owned character passed against an in-memory copy of the current account, with all
other profile fields retained and zero writes through the read-only source
connection. After reloading only the backend, the owner confirmed that selecting
different owned characters changes the picture and that the last choice persists
after fully closing and reopening the game. The running backend recorded five
completed selection calls and no rejected calls. The old unsupported-call count
remained historical. A read-only check confirmed the saved choice matches the
latest receipt and SQLite integrity passes. This verifies the local profile
portrait path in the prepared APK; other customization remains separate.

## Selecting or removing an owned portrait frame

The next profile customization error reached `/user/set-portrait-frame`. The
actual pending request contained exactly `FrameId`, an owned **inventory misc
item ID**. Read-only inspection matched the running request builder to the
inspected 3.57.0 native code. `SelectPortraitFrameTab.OnSelectItem` sends the
inventory ID for a frame, or null for the no-frame entry. The profile's saved
`User.FrameId` instead contains the **item-spec design ID**: `PortraitBox` looks
it up through `ItemData.GetSpec`. The success callback only redraws the portrait.

The authenticated operation now resolves that inventory ID to its owned design.
Frame eligibility comes from `Type=portraitframe` in the matching external
`static_data_get.bin` items table, with no fixed frame list or additional catalog
to import. Only positive-amount items in `User.ItemMiscs` qualify; costumes,
unknown items, unowned designs and design IDs submitted as inventory IDs reject.
Null removes the selected frame without removing any owned item. The existing
saved zero/default value is also accepted before selecting a frame.

A changed selection atomically saves `User.FrameId`, `User.Cas` and a retry
receipt. Selecting the same design does not rewrite the profile or increment its
revision. Replies contain only `User.Id`, `User.Cas` and `User.FrameId`. A delayed
retry returns the current selection and cannot restore an older frame or undo
later progress. Inventory, representative hero, equipment, currencies, presets,
guild captures and other profile sections remain intact. Existing saves add the
receipt table at normal backend initialization; no save reimport or resource
re-extraction is required. Badges, boards and stickers are separate operations.

Twelve regressions cover inventory/design resolution, dynamic catalog changes,
null removal, ownership/type/amount validation, malformed requests and saved
state, invalid external definitions, atomic rollback, no-op revisions,
authentication/prologue guards, fresh/imported accounts, reconnect/reopening and
delayed retries. The captured request, all 37 owned frames and removal passed on
an in-memory copy of the actual account; all unrelated profile fields were
preserved and the read-only/query-only source connection recorded zero writes.
After reloading only the backend, the owner reported that changing/removing the
frame works and the last choice persists after reopening the game. A separate
read-only check found one completed frame request, no rejected frame calls, a
saved selection matching the latest receipt and passing SQLite integrity. One
unsupported-frame call remains in the historical counter.

## Acknowledging client-managed profile badges

The next error reached `/user/set-profile-badge`. The actual pending request
contained exactly `BadgeId`, a positive signed-32-bit owned **misc inventory ID**,
not an item-spec design ID. Read-only process inspection matched the running
`SendSetProfileBadge` builder to the inspected native code. Closing
`BadgeSelectPopup` resolves the selected design through the owned inventory and
sends its inventory ID, or null when removing the badge. It ignores the response
body. The close callback separately stores the design in `PersistentPlayerPrefs`
under the account-specific `MyBadge_` key, saves preferences and redraws the
profile. No badge selection field was present in the imported account profile.
The original server response/social storage was not captured; the local
acknowledgment follows this observed own-profile client path.

The authenticated local route now validates the request against positive-amount
`User.ItemMiscs` and `Type=profilebadge` in the matching external items table. It
returns an empty JSON acknowledgment, allowing the client's existing preference
flow to finish. Costumes, frames, unowned items, empty stacks, design IDs used as
inventory IDs, malformed requests and invalid item definitions reject. The
shared item-definition reader keeps frame and badge eligibility separate and
refreshes when the external body changes; no fixed badge list or new catalog
import is needed.

The operation writes no account fields, revisions, inventory, receipts or schema.
Repeating an acknowledgment cannot overwrite a later badge choice or other
progress. Persistence of the own-profile badge remains a preference of that
client installation; server-side cross-device badge synchronization and other
players' badge views are not reconstructed. Updating an existing backend needs no
save reimport or resource re-extraction.

Nine regressions cover exact authenticated requests, dynamic ownership/type/amount
validation, null removal, malformed/corrupt inputs, distinct frame/badge caches,
fresh/imported accounts, prologue guards, reopening, retries, maximum user
revision and successful acknowledgments with SQLite writes disabled. The real
pending request and all 13 owned badges passed through the protocol on a detached
account copy with query-only enabled. All profile/database rows were retained;
the source connection was read-only/query-only and recorded zero writes. After
reloading only the backend, the owner confirmed badge changes/removal and
preference persistence after reopening the game. Four actual badge calls
completed without rejections; one older unsupported call remains historical. A
read-only check confirmed SQLite integrity passes.

## Empty friend refresh required by the profile popup

The native profile popup waits for `FriendClient.UpdateFriendDict` before setting
up the visible card. `SendEnterFriend2` sends `/friend2/enter` without a body. Its
success callback consumes `FriendInfos` as a dictionary keyed by integer user ID
and a Boolean `IsMigrated`; the latter can enable a first-entry migration notice.
This was the initial local prerequisite; empty recommendations are covered
below. No official response or peer records were captured.

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

Combat entry/exit has the guarded trial described below; persistent raid results
and reward claims remain unsupported. The native off-season practice loader was inspected,
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

## Empty raid combat log and boss refresh

After reloading the calendar override, the APK requested
`/guild-raid2/get-battle-status` with `SeasonId=1`, matching the new historical
selection. This confirms that its effective-season request now follows the
selection; exact boss rendering and combat remain unverified. The current
failure is a later unsupported log read, rather than a static bootstrap failure.

Native `GuildRaid2Logs.OpenRaidLog` first refreshes rankings, then requests battle
status and latest records before opening the overlay. Its status callback reads
`Records` as `List<GuildRaid2BattleStatus>` and passes it to `SetBattleStatus`.
The local read now returns `{"Records":[]}`. A status entry's nested `Records`
would be `Dictionary<int32,int64[]>`; no such entries or invented fights are
created. The native next request, `/guild-raid2/get-battle-records/latest`, uses
exact integer `SeasonId` and `Count` fields. Its callback reads `BattleRecords`
as `List<BossBattleRecord>`, so the companion response is
`{"BattleRecords":[]}`. This second contract is native inference; the observed
blocked packet was the status request. Count must be a nonnegative signed-32-bit
integer, and season IDs must exist in the matching opt-in catalog.

Telemetry also recorded unsupported `/guild-raid2/update-status`. Its native
builder sends no body; the boss-entry refresh routine consumes integer
`FeverBossIdx` and `Round`, and scalar int64 `RoundExp`. The fresh local response
is `{"FeverBossIdx":0,"Round":1,"RoundExp":0}`, consistent with initial entry.
It does not simulate damage, consume attempts or advance a round. Preserved
non-null saved raid progress rejects this fresh status view instead of resetting
it. Empty history reads leave preserved progress untouched. All three reads
require authentication, completed prologue and owned guild membership; no profile
resources, rewards, receipts or operator selection are returned or changed.

Four regressions cover native parameterless and exact season/count schemas,
ownership/catalog guards, fresh status shapes, preserved-progress protection,
known cached seasons and repeated/reconnect history reads with SQLite writes
disabled. The actual account passed all three protocol reads through a read-only
connection, with zero writes and unchanged full profile and selection. Post-fix
APK log opening and boss refresh remain pending backend reload and reconnect.
Normal completion has the no-reward acknowledgment below. The separate abandon
route, nonempty battle history and persistent raid progress remain unsupported.

## Empty raid history by boss and own member

The general battle-status and latest-record reads each subsequently completed two
actual APK requests. The next unsupported request was
`/guild-raid2/get-battle-records/boss`, with public `SeasonId=1` and
`BossId=1790004`. Native `GuildRaid2MemberRankingTab.RequestRecordData` sends
those exact fields and reads `BattleRecords` as `List<BossBattleRecord>` before
separating normal/fever records. The local response is now `{"BattleRecords":[]}`.
The requested boss must be one of the four IDs in the requested catalog season;
unknown or cross-season boss IDs reject. This read does not invent a cleared
boss, damage or an attempt.

The companion member detail popup uses
`/guild-raid2/get-battle-records/member` with exact native integer `SeasonId`,
`Day` and `UserId` fields. Its callback also consumes
`List<BossBattleRecord>` from `BattleRecords`, so the local response is the same
empty list. Day accepts the native nonnegative signed-32-bit range. Only the
saved local user's ID is supported; other members' private histories were not
captured. This companion contract is native inference, not an observed blocked
member-detail request. Both routes require authentication, completed prologue,
owned membership and the explicit matching catalog, and accept known cached
season IDs independently of the latest operator selection.

Three regressions cover native field validation, season/boss relationships,
own-user restriction, catalog/membership guards and repeated reads across
reconnects with SQLite writes disabled. All boss slots in the synthetic seasons
and day bounds retain saved raid damage/attempts, pending rewards, other-mode
currencies and selection. The actual blocked boss request and an own-member
companion passed through a read-only protocol session with zero writes and the
full profile/selection unchanged. Post-fix APK boss/member history rendering
remains pending reload and reconnect. Nonempty history and combat remain
unsupported.

## Guarded local raid combat-loading trial

The APK advanced through four boss-history queries and two boss-status refreshes
to `/guild-raid2/start-stage`. Read-only inspection of its pending request found
exactly `{"BossIdx":3,"IsFever":false}`. Native `StartStageRoutine` obtains the
boss from its existing set/slot, sends that request for normal combat, and checks
`Cancelled` after network success. False continues to `StartStageInner`, which
resolves the preserved boss detail/stage ID and calls the normal scene transition.
The response is not a stage descriptor, party selection or damage result.

The local handler now accepts exact integer boss slots 1–4 and a Boolean
`IsFever`, using the matching selected four-boss catalog, completed prologue,
owned guild membership and fresh local raid policy. Both Boolean fever settings
are accepted for this experimental loading trial; this does not establish
official fever eligibility/rules. Existing non-null saved raid progress rejects
instead of being reset. The response is `{"Cancelled":false}` with no account
resources, costs, attempt record or reward. The client retains its existing boss,
round and party; the server does not migrate or replace the saved party. Native
off-season practice remains a separate direct loader path.

Three regressions cover authenticated exact request shapes, all configured slots,
both fever flags, reconnect/retry behavior, invalid catalogs/membership and
preserved raid progress. All saved tables and selection remain unchanged with
SQLite writes disabled. The actual pending request passed twice through the
read-only protocol session with false cancellation, zero writes and unchanged
full account/selection. Those checks established the host authorization shape.
The APK subsequently advanced through start to its completion request. The normal
exit acknowledgment is described below; the separate abandon route remains
unverified/unsupported. No result validation or raid progress persistence is
implemented by this trial. Reload the backend and reconnect to retry entry;
another full APK restart is needed only after changing the selected calendar.

## No-reward local raid completion acknowledgment

The APK handled the start request and the user reached the end of combat. The
next unsupported operation was `/guild-raid2/end-stage`. Its pending body
contained only `Damages`, a four-element list of nonnegative int64 values.
Native `EndRoutine` obtains this array from `PartyDamageRecorder`, sends it,
and checks network success. Its success callback reads Boolean `Cancelled` and
the `AddedItems` list. False cancellation continues to `GuildRaid2EndEvent`,
carrying the client's existing result/party damage data and the returned item
list; true instead shows a reset/cancellation notice.

The handler now validates exactly `Damages`: zero to four nonnegative native
int64 values, with the total also within int64 range. It requires authentication,
completed prologue, owned membership and the matching selected fresh local raid
catalog. Preserved non-null saved raid progress rejects rather than being
replaced. The acknowledgment is `{"Cancelled":false,"AddedItems":[]}`. No
account resources, rewards, attempts, history, damage or round progress are
written. There is no persistent attempt to release in this free trial, so retries
and reconnects need no receipt or account reset. The client's existing statistics
remain available for the result flow; damage is not validated as an official
score or persisted raid achievement. The request has no clear/victory field, and
this change does not infer a clear or grant rewards from damage alone.

Three regressions cover authenticated exact native schema, int64 and party-size
bounds, aggregate overflow, saved progress/catalog/membership guards and repeated
entry/exit acknowledgments across reconnects with SQLite writes disabled. Full
account tables, currencies, pending rewards and operator selection remain
unchanged. The actual pending request passed twice through a read-only protocol
session with false cancellation, an empty reward list and zero database writes.
The actual result screen/menu return still needs APK confirmation after backend
reload and reconnect. Separate abandon handling and persistent raid results are
outside this acknowledgment.

## Selecting a saved Raid/Conquest preset

After the completion endpoint handled an actual APK request, switching teams
failed at `/preset/set-selected-preset` with `PresetId=713`. The old handler
allowed only Orbital IDs. Native preset-type helpers use width-100 ranges and
map the shared Raid/Conquest selection to the 700 block. The user model stores
that choice in `User.SelectedPresetId.GuildRaidAndConquest`. The pending target
exists exactly once in the captured/current definitions; its four heroes and
equipment passed the ownership check. No real profile change was applied by
that read-only inspection.

The selector now supports existing owned definitions in `[400,500)` and
`[700,800)`. It derives the stored field from the ID block, validates the existing
pointer as zero or an ID from that same block, and updates only the selected
field plus `User.Cas` when the choice changes. Independent mode selections,
heroes, character equipment, inventory, raid progress and all team definitions
remain unchanged. This is a real saved selection, not an acknowledgment that
ignores the requested choice. The native shared field also applies to its shared
guild contexts; no new per-mode selection field is invented.

Existing epoch/sequence receipts retain atomic update/rollback and current-state
retry behavior across both groups. Repeating a choice does not increment the
revision; a delayed Raid retry cannot undo a later Raid choice or Orbital change.
Unknown groups, missing/ambiguous/empty teams, unowned heroes/gear and invalid
saved pointers/revisions reject without writes. Team creation, editing and
deletion remain limited to the separately implemented Orbital contracts.

Five additional regressions cover zero/default Raid selection, preservation of
the complete profile/definitions, interleaved Orbital/Raid changes, stale retries
after reopening/reconnect, no-op revisions, ownership/scope failures, invalid
saved state and rollback when receipt insertion fails. The actual pending request
was applied only to an in-memory SQLite clone. It changed exactly the shared
Raid pointer and User revision when needed; an exact replay wrote nothing. The
read-only source database remained unchanged. Actual APK team switching remains
pending backend reload and reconnect; the user's retry will persist the choice
through the normal server transaction.

## Empty friend recommendations

The next unsupported request in the friend section was `/friend2/recommend`.
Read-only inspection confirmed a native pending packet with body type zero and
zero body bytes. `SendRecommendFriend` is parameterless; its caller is
`FriendClient.UpdateLatelyFriends`. The success callback reads `RecommendInfos`
as `List<FriendInfo>` into the client's recent/recommendation list and records
the refresh time locally.

The user explicitly chose an empty local view. Authenticated parameterless
requests now return `{"RecommendInfos":[]}`. The response includes no profile
resource or peer data. It leaves saved `UserFriend` settings, friend/request
counts, pending gifts, dates and revision unchanged, and performs no migration,
gift collection, invitation or friendship mutation. The existing friend-entry
response remains `FriendInfos={}` and `IsMigrated=false`. Other-player lookup,
friend requests and gift writes remain unsupported.

Three regressions cover authentication, exact parameterless/native empty bodies,
the required list shape, preserved imported social state and fresh/imported
reconnect sequences with SQLite writes disabled. Repeated friend-entry and
recommendation reads passed against the actual read-only database, including a
native empty packet: zero writes and unchanged full profile. The original
official recommendation response was not captured. Actual empty recommendation
UI rendering still needs verification after backend reload and reconnect.

## Free imported hero experience

The next rejected call was `/user/add-character-experience`. Its native request
contains `Experiences`, mapping owned row IDs to positive XP deltas. The imported
mutation guard had blocked the route, and the existing training implementation
only admitted knights without breaks or blessings. The pending request targets
an owned non-knight with five breaks and blessing level three. The user chose
normal saved hero growth without consuming shared experience.

Native `CharacterInfo.RawMaxLevel` adds story level, limit-break and blessing
coefficients and a myth bonus. `GetAddedCoefLevel` uses public constants 3, 5 and
20; myth specs have rank at least six. Read-only public character-spec references
identify 41 rank-six variants in the 709-entry hero-spec index. The myth-stone
map instead identifies the pre-myth eligible specs, not those rank-six IDs;
`AssignMythMap` and `MythSpec` distinguish these two steps. The matching external
policy combines these IDs with public `exps2` thresholds and story caps. Native
levels are zero-based: threshold N is the XP needed for internal level N, shown
as N+1. The new imported policy uses this index explicitly; legacy fresh-account
paid training retains its existing behavior.

One to 32 owned targets can receive positive XP deltas, including partial levels,
up to their individual current cap. All targets validate before mutation. Only
target XP, User revision, applied-experience record and record revision change.
All assets, equipment, other heroes and progress remain unchanged, even when
the shared XP balance is zero. Profile and epoch/sequence receipt save in one
transaction. Reconnect replays return current resources; identical costs with
new request identities are legitimate new training. Conflicting identities,
unknown heroes, malformed policies/state, over-cap deltas and numeric overflow
reject atomically. A new client epoch cannot infer an ambiguous prior operation
from XP cost alone.

Seven regressions cover advanced/non-knight/myth caps, native threshold indexing,
story unlocks, zero-balance free batches, partial growth, profile preservation,
reopen/reconnect/retry behavior, invalid inputs and transactional rollback. The
actual pending request passed through the protocol against an in-memory clone
of the saved database, including an exact retry. All asset rows matched the
original, and the real read-only source had zero writes and unchanged profile.
The external public policy is installed locally. Actual APK leveling and UI
refresh still require backend reload, reconnect and the user's retry.

## Compact preset responses

The user reported pauses when selecting, editing and deleting presets. Every
mutation and receipt replay returned the complete `User`, even though only the
selected-mode map and revision could change. In the saved account that added
657,376 bytes of hero/inventory JSON to selection responses and approximately
the same amount to definition responses. The transport's uncompressed framing
also encodes/checksums every byte, before the APK parses and reapplies them.

Native `NetResMediator.HasMyResource` routes `User` by `Id`. `User.Apply` uses
existing values as Populate defaults and checks presence before parsing full
hero/item collections. The `SelectedPresetId` map itself is replaced when
provided. Preset mutations now return only `User.Id`, `User.Cas` and the complete
current selected-mode map. Save/create/delete retain the full current
`UserPartyPreset2` group because its dictionary is replaced, including removals.
Retries use current selection/group resources, preserving later changes. No
persistence, ownership, transaction, revision or receipt policy was removed.
The original official preset responses were not captured; partial-resource
compatibility is inferred from the preserved matching native client.

Seven independent in-memory clones per operation/version compared the previous
implementation with the compact responses, including encoding and receipt
replays. The resulting full profiles/groups matched exactly, all omitted User
fields survived a merge, and source writes remained zero. Median host results:

| Operation | Previous JSON bytes | Compact JSON bytes | Previous host work | Compact host work |
| --- | ---: | ---: | ---: | ---: |
| Select | 657,376 | 383 | 85.5 ms | 11.4 ms |
| Save/apply | 676,045 | 19,052 | 87.6 ms | 19.1 ms |
| Delete | 675,525 | 18,532 | 81.9 ms | 7.8 ms |

Host work measures handler plus JSON/wire encoding with in-memory SQLite. It
excludes persistent disk flushes, the bridge/network and APK deserialization/UI
work, so these numbers do not establish total interaction latency. Four added
regressions enforce response size independent of inventory size, complete group
replacement, independent mode preservation, wire decoding, creation/application
and reconnect/stale receipt behavior. Existing ownership/rollback tests remain.
Actual APK response handling and perceived speed require backend reload and a
new select/save/delete trial; no emulator or live account state was changed by
these measurements.

## Dynamic imported achievements

The rejected achievement request was `/mission/claim-challenge-all-step` with
`missionIds: [206]`, the public hero-summon group. The imported mutation guard
rejected it. The fresh-account implementation also expected every saved claim
step to have a local receipt, whereas this imported profile already had official
claim markers and no local challenge receipts. Simply enabling that handler
would therefore still fail, or risk re-awarding old rewards if markers were reset.

The existing next/all-step implementation now accepts imported accounts only
with a matching `imported_challenge_mission_catalog.json`. Public mission enum
values and the native `MissionHelper.GetMissionProgressCount` switch establish
15 progress rules over saved record counters, miscellaneous counters, owned
heroes, gold, stamina spending and Orbital floor. For example, summons read
`SummonCharacterCount`, blessings read `Misc.BlessCharacterCount`, and character
limit-break achievements read only `LimitBreakCharacterCount`. These are not
individual hardcoded target amounts. Public `missions` rows supply ordered
thresholds and rewards; `items.Type` supplies asset/stackable/cosmetic storage.
The prepared regional catalog filters unavailable version-gated rows and has
13 groups with 1,190 contiguous steps. Other native conditions remain guarded;
claiming does not generate unsupported gameplay progress or repair counters
that another local gameplay handler does not yet update.

A first local claim saves each existing official step as a nonpaying baseline.
Only eligible steps above it receive rewards and new contiguous local receipts.
Missing local receipts cannot be silently rebased. One transaction saves all
baseline rows, new asset/stackable/unowned-cosmetic rewards, inventory IDs, claim
markers, revisions and request receipt. A malformed/unearned group or overflow
rejects the batch without writes. No-op completed groups retain their markers.
Exact receipt replays return current resources and frozen reward notices without
granting again; a new operation after real saved counter growth can earn the next
steps. Unique cosmetics already owned are rejected pending a verified duplicate
reward policy, rather than inventing a conversion. Fresh-account behavior and
its existing receipts remain available separately.

Twelve additional regressions exercise these cases, including protocol admission,
authentication, catalog guards, all 15 progress sources, allocator/revision guards,
catalog removal, reconnects and transaction failure. The actual pending request
passed against an in-memory copy of the account database. It awarded one new
step, changed only its expected asset amount and User/UserMission revisions and
claim marker, retained all old steps without replayed rewards, and recorded the
baseline plus only the new local step. An exact retry wrote nothing. The real
SQLite source was read-only and its profile remained unchanged. Original official
claim responses were not captured; APK reward rendering and refresh still require
backend reload, reconnect and the user's retry.

## Dungeon Kingdom Arena rotations and days

The failing guild mode was `/guild-punchking/enter`, not PvP Arena or Conquest.
Read-only native inspection confirmed `IsPartial: bool`. The user requested all
three DKA rotations selectable by command, and an independent choice of day/slime
1–7. The matching public table has 37 historical seasons; its recent seasons
repeat three seven-monster patterns. Native weakness orders begin respectively
Down/Injury/Airborne, Injury/Airborne/Down and Airborne/Down/Injury. All use the
same preserved arena stage and existing assets. Public official notes describe
the original daily slime rotation and 90-second automatic battles with unlimited
challenges; see the [mode introduction](https://www.guardiantales.com/news/4261)
and [a later rotation schedule](https://www.guardiantales.com/news/4747).

Native `GuildPunchKingClient.IsSeasonOff` checks the selected public calendar.
`GetMonsterSpecIdBySeasonId` subtracts content-day start dates and indexes its
seven native monster IDs. `GetTotalDayList` uses the complete calendar interval.
Changing only a server season ID would leave an off-season button or wrong boss.
The new `dka-season set VARIANT --day DAY` command publishes a separate immutable
static body and selection manifest. It activates the matching seven-day global
calendar with the requested day aligned to UTC today and closes other DKA
calendars. The original static source, monster definitions, other modes' dates
and other services' values are retained. It composes over the current Raid
override and refreshes after a later Raid selection or new UTC content date.
The user's server clock and profile are never moved or rewritten. A full client
restart is required after any choice; reconnect retains the cached table objects.

Native entry callback consumes `GuildRaid`; its status is a seven-row dated list
with per-user dictionaries. A partial `UserRaid` season pointer retains other
resources. Ranking callbacks consume empty `Rankings` lists, with nullable
`MyRank` and zero `MyScore` where required. Stage start accepts exactly
`MonsterId` and its callback reads `Messages` before creating the stage. End
accepts nonnegative Int32 `Damage` and Boolean `Abandoned`; its callback reads
`GuildRaid`, `IsRenew` and `Abandoned` before the native result routine. The new
practice response supplies these shapes without rewards, attempt/currency costs,
personal-best persistence or invented official scores. Native DKA preset type
13 maps existing captured teams to `[1300,1400)` and
`User.SelectedPresetId.GuildPunchKing`; selecting those teams is supported.
Current party/equipment, other preset modes and all inventory remain unchanged.

`punchking_active` and `punchking_requests` store only local practice-session
state and epoch/sequence receipts. Start validates the selected day/boss and an
existing nonempty owned DKA team. End requires a matching active selection;
both its completion and abandonment clear that session atomically. Exact retries
do not overwrite a later battle or reward twice; mismatched bodies/selections
reject. Existing nonzero saved arena seasons are guarded rather than reset.
Shop/reward redemption, user comments and score validation remain separate.

Twelve new regressions cover all 21 combinations, native schema/bounds,
authentication, read-only menu views, owned team selection, UTC rollover,
Raid/arena composition in either order, stale-session fences and rollback.
An independent check used the actual public tables and an in-memory copy of the
saved account for all 21 selections, start/end and exact retry. Every profile
section remained equal to the original. Actual pending entry and ranking reads
also passed with the real SQLite connection write-disabled: zero real writes.
The local external catalog is prepared and the initial choice is variant 1,
day 1. These are host/native-contract results. Actual APK scene entry, combat
and result/menu return require backend reload and full client restart; they have
not yet been observed and are not established by passing host checks.

## Dynamic imported hero collection knowledge

The next observed rejection was `/collection/claim-hero-knowledge-all`, with one
owned inventory hero ID. This is the hero knowledge/book claim, rather than item
or custom collection claims. The imported-account route is now enabled with its
own bounded external catalog and persistence tables. The existing fresh-guest
initial-acquisition handler remains unchanged.

Matching native `HeroKnowledgeInfo.GetCurrentValue`, `CheckKnowledgeComplete`
and `HeroKnowledgeSpec.GetMaxValue` establish eight objective types: Get, Evolve,
LevelUp, LimitBreak, AwakeningSkill, Ascend, Blessing and Myth. These are evaluated
from the current owned hero's raw public spec rank, XP, limit breaks, awakening
bits and blessing level. Ascended rank 5 or myth rank 6 satisfies Ascend; Myth
requires rank 6. The native level increment cancels between current and maximum
values, so zero-based total-XP threshold indexing is retained. Saved RankUpgrade
is not substituted for raw evolution rank.

`CharacterInfo.Apply` treats null/empty awakening trees as empty. The native
Base64 decoder reads the second `|` part and constructs nodes from the current
origin's public tree/configuration, using encoded node ID modulo 1000. Only
those bit positions count; padding bits and short bitsets cannot invent progress.
The old encoded spec prefix may survive evolution and does not select the node
map. Invalid nonempty encodings remain guarded.

The prepared external catalog covers 661 playable specs, 175 knowledge origins
and 1,329 objectives. Rewards in those public rows are gems or empty lists.
Saved official claim flags are trusted once as nonpaying baselines, including
flags whose original progress is no longer reconstructible. Later local flags
must agree with objective receipts and their original baseline; missing receipts
cannot be silently rebased. Only requested, owned, unique origins are changed.
Previously claimed and currently unmet objectives give no new reward. Flags,
balances, revisions, baselines and receipts commit or roll back together.
Exact request retries return the frozen notices and current User resource.

Thirteen synthetic regressions cover all eight progress types, XP boundaries,
evolved/ascended/myth specs, sparse awakening bits, old prefixes, null trees,
official baselines, new progress, no-op claims, authentication, reconnect/reopen,
catalog removal, numeric/ownership guards and late transaction rollback. The
actual rejected request passed on an in-memory copy of the saved account: its
acquisition flag, 60 catalog gems and User revision were the only changes. An
exact retry wrote nothing. A batch of every owned hero also passed, retaining
all other profile sections. The real source database had zero writes and its
profile remained unchanged. These are host/native-contract results; actual APK
claim/reward rendering remains pending backend reload, reconnect and retry.

## Jewel decomposition without consuming the jewels

The next unsupported route was `/item/decompose-jewel`. Its captured request had
exactly `Jewels`, mapping three owned stack inventory IDs to selected quantities.
The owner requested that decomposition preserve the jewels, including types
beyond the currently selected ones. The explicit local mock now grants the
matching powder reward while retaining every source stack.

Matching native `ApiConnection.SendDecomposeJewel` establishes the request shape.
`Jewel.get_Grade` and `InlaidData.GetJewelDecompositionDrop` use the public jewel
grade and its decomposition drop. `ForgeJewelDecomposition.SetUI` sums those
drops times the selected amounts. Its `ProcessDecomposition` coroutine awaits
the response, clears the temporary selection, refreshes the inventory and
displays a locally prepared powder reward notice. The native result placeholder
identifies item 70028. Returning current `User` updates the powder balance and
restores selected source quantities under the requested retention policy.

The prepared external catalog uses all 20 matching `items` jewel rows and all
20 `inlaid.JewelGrade` powder yields, rather than a special case for the three
observed grades. Each new batch requires owned, unlocked stack IDs, positive
quantities within saved stock, configured specs and a valid existing powder
asset. Ambiguous inventory IDs and numeric overflows reject without writes.
Only powder amount and User revision change. Jewels, attached sockets, all
other inventory/assets, spending, activity counters and every other profile
section remain equal. The mock does not consume resources or simulate item loss.

The profile and canonical request receipt are one transaction. A retry of the
same epoch/sequence and quantities returns current User without paying twice,
including after reopening, catalog removal or later inventory edits. Different
quantities under that identity reject. A genuinely new operation may reuse the
retained jewels and receive the normal catalog yield again.

Eleven synthetic regressions cover mixed grades, 20 data-driven grade entries,
source/socket/profile preservation, repeated free operations, ownership/locks,
malformed input/catalogs, bounds, atomic rollback, authentication and reconnect.
An independent check used the actual public catalog for all 20 grades on a
synthetic memory account. The actual rejected request also passed on an in-memory
copy of the saved account, adding 798,720 powder and one User revision while
retaining all selected sources and every other profile field. Exact retries
wrote nothing. The real source database remained unchanged with zero writes.
These are native-contract and host results; actual APK result rendering and
retained quantities remain pending backend reload, reconnect and retry.

## Guaranteed jewel upgrades without spending resources

The next unsupported request was `/item/upgrade-jewel-from-relic`, with exactly
`RelicId`, `SlotIndex` and `UseJewelPowder`. It selected an owned locked relic's
socket, with a grade-19 jewel and a nominal powder amount below the native
full-success requirement. The owner requested no resource consumption and
guaranteed success regardless of the selected percentage.

Matching native `ApiConnection.SendUpgradeJewelFromRelic` and
`SendUpgradeJewel` establish the socket and loose-stack request shapes. The
loose route takes an owned inventory `JewelId`. `InlaidData` supplies the grade's
full powder requirement and nominal gold calculation. The forge slider and
`SetProgressLabel` calculate the displayed percentage. Its `ProcessUpgrade`
coroutine reads a Boolean `Succeeded` from the response, refreshes User-backed
inventory/socket data, and chooses the success/failure notice accordingly.
`Utils.IdxBool` takes a default Boolean argument; the success field is a scalar,
rather than an indexed result list.

Both routes now use a separate pinned external catalog with `free: true` and
`always_succeed: true`. All 20 matching public jewel specs and their 19
same-group, consecutive-grade evolution edges are covered, together with the
20 public relic specs and native global capacity of one socket. Positive nominal
powder amounts up to the native full requirement are accepted without charging
powder or gold. The result is always `Succeeded: true` for a valid new operation.
No success RNG or fabricated currency/activity-counter update is involved.

Socket upgrades replace the selected jewel spec ID by its public evolution
target. Loose upgrades promote one unit, merging into an existing next-grade
stack or allocating an inventory ID; the total number of owned jewels is
conserved. Other source units, unrelated sockets, relic options, equipment,
currencies, spending and other profile sections are retained. Maximum-grade,
unknown, empty or unowned targets and numeric/graph inconsistencies reject.
Profile, ID allocation and route-bound canonical request receipt are atomic.
An exact retry returns current User with the prior successful outcome without
advancing another grade, including after later progress or catalog removal.

Thirteen synthetic regressions cover socket/loose targets, locked relics, low
nominal powder and empty currency balances, stack merge/allocation and zero-row
reuse, maximum grade, malformed requests/catalog graphs, numeric bounds,
transaction rollback, authentication and reconnect. The actual rejected request
passed on an in-memory copy of the saved account: only the selected socket's
grade 19 -> 20 and User revision changed. All currencies and every other saved
field remained equal; an exact retry wrote nothing. A separate synthetic memory
check used the actual public graph for all 19 edges through both routes: 38
cases passed with the minimum nominal powder and zero gold/powder balances.
The real source database remained unchanged with zero writes.

These are native-contract/host results. Actual APK success rendering and saved
socket/stack refresh remain pending backend reload and reconnect. The APK's
original cost/percentage preview and its pre-send funds checks are retained;
the server-side policy guarantees success and charges nothing once submitted.

## Saving normal-party members

The next unsupported route was `/user/save-party-member/v2`. The actual pending
body had exactly `CharacterIds`, containing one owned inventory hero ID that
differed from the saved normal party. This route now persists the ordered
normal-party formation, including changing its leader or removing trailing
members, while leaving saved mode presets and all equipment intact.

Matching native `ApiConnection.SendSavePartyMemberV2` establishes the exact
body. `PartyMembers.SaveCurrentPartyMember` serializes each currently selected
member's inventory ID in order and sends it through this API. `PartyInfo.Apply`
resolves numeric IDs using the existing owned-hero registry and clears trailing
slots after a shorter array. Native `User.Apply` tests whether Party is present,
then applies that object; absent hero/inventory/preset fields are preserved.
The normal saved party has ID zero and a physical capacity of four. Existing
client-side feature gates determine which slots its UI offers.

New requests require one to four distinct positive owned IDs, completed
prologue, an unambiguous roster, the normal party and a valid User revision.
Order is significant and the first member is the leader. Only Party.Characters
and User revision change; party metadata, every hero, equipment, relic options,
jewels, currencies, representative avatar, mode selections, preset definitions
and all other profile sections are retained. No mission credit is fabricated.
The response carries only current User Id, Cas and complete Party, avoiding
another large inventory/hero payload for a member change.

Profile and an order-preserving canonical request receipt are one transaction.
An unchanged formation records its identity without rewriting the profile or
increasing the revision. A retry of an older request returns the current party,
including after newer choices, reopening and later gear edits; it cannot undo
those changes. Changed membership or ordering under the same identity rejects.

Nine synthetic regressions cover four-member ordering, leader swaps, shortening,
metadata/profile/preset preservation, compact resources, no-op revisions,
reopen/reconnect/current-state retries, malformed/unknown/duplicate IDs, saved
state guards, numeric bounds, authentication and late rollback. The actual
request passed on an in-memory account clone: only the normal formation and
User revision changed, every other field and preset remained equal, and an
exact retry wrote nothing. Its response was 72 bytes. The real source database
remained unchanged with zero writes. These are native-contract/host results;
actual APK save, displayed leader/slots and reconnect persistence remain pending
backend reload and retry.

## Temporal-event entry and integration review

The next observed pending request was `/live-event/enter`, sent with no body.
Matching native scene loaders await it and use global `UserEvent`; the resource
apply method handles 13 dictionaries and nullable ReturnEvent. Entry now returns
the current saved resource after validating ownership, revision and record IDs.
It does not initialize seasons, repair progress, grant rewards or write state.

Eight synthetic regressions cover native transport, fresh/imported reads, every
event family, malformed requests/state, retained extra fields, authentication
and reconnect. The actual pending packet and retry passed through the session
and wire codec against the real database opened read-only with query-only mode.
Both responses matched saved UserEvent, with zero source writes and no profile
change. APK entry/rendering is pending backend reload and reconnect.

The private account retains Roadmap and Bingo records; its Roadmap record
matches current public event 33. Inspection of the matching external tables
found 14 families and 397 historical/base definition rows, with separate calendar
and eligibility requirements. No additional minigame, season selector or reward
claim is implemented here. The [integration review](live-events.md) lists the
families, current snapshot calendar findings and practical next steps, including
the extra web dependency of Yutnori. Game content and account data remain private.

## Empty guild attendance reward mock

The next unsupported and pending request was
`/guild/claim-guild-daily-attendance`. The user explicitly requested an empty
mock. Matching native `SendClaimGuildDailyAttendance` sends no body, and the
attendance screen and guild-entry coroutines both consume `AddedItems` through
`UserUtil.GetAddedItems` on success. No official response body was captured.

The authenticated handler accepts no body, JSON null or an empty object and
returns exactly `{"AddedItems":[]}`. It does not mark the day claimed, change
attendance dates/counts, grant rewards, clear pending rewards, alter membership,
increment revisions or write a receipt. Repeated calls are naturally no-ops.
Other guild reward claims retain their existing unsupported boundary. This mock
is shared by fresh guest and imported accounts; it requires no additional
catalog, membership initialization or recovered official guild data.

Two regressions cover fresh/imported accounts, native framing and aliases,
reopen/reconnect/retries, exact empty rewards, authentication and malformed
parameters with query-only SQLite enabled. The actual pending route and native
no-body contract also passed against the real database opened read-only and
query-only through the session and response wire codec, including null/object
aliases and a repeat. All saved state remained equal with zero source writes.
These are native-contract and host checks; the actual APK retry and any empty
reward-popup behavior remain pending backend reload and reconnect.

## Meteor menu and opt-in Guild War season trial

The actual pending `/guild-meteor/enter` request now returns fresh native menu
resources: meteor-specific UserRaid fields, a GuildRaid view with a status list
and excavation dictionary, and empty integer excavation/reward arrays. The
external catalog selects the latest started public season without spending
pickaxes or replacing saved progress. The real packet/full-partial-repeat check
passed read-only with zero writes. After backend reload the user confirmed the
APK menu loads, and one completed entry was recorded by the running API.

The user then requested activation commands for Guild War. `guild-war enable`,
`status` and `disable` now control a reversible static-calendar overlay for season
1. Native client inspection establishes its separate castle/shortcut entrances,
the active-season check and Raid's priority in the lobby button. Activation makes
War valid for seven UTC days and Global Raid calendars inactive in the derived
response, preserving parent Raid/arena selection files, other tables/services and
the immutable source. Disable restores the parent bootstrap. The actual composed
source check passed for 47 affected rows without account writes.

The guarded `/guild-war/enter` trial accepts native lowercase `isPartial` and
returns correctly typed fresh UserRaid.GuildWar / GuildWarInfo collections in
phase 1 for the cooperative lobby. It preserves existing account state and
rejects nonempty saved War progress; battles, claims, purchases and other War
APIs remain unfinished. Forty-two new regressions and read-only real-account wire
checks cover these contracts. The first APK trial reached the basic-course
prerequisite popup and redirected to Play > Others, where the entry was absent.
Metadata identifies the missing GuildWarSingle feature as 126. The derived static
data now appends only its Global no-reward unlock rule, and a scoped client-only
acknowledgment retains all saved bits while setting bit 126 in the response.
Neither acknowledgment nor activation writes progression or marks stages clear.
The original source and database remain unchanged; disabling restores the parent
feature table too. The course remained absent after restart, despite its native
checker being present/open in read-only runtime inspection. An explicit optional
`--skip-basic` now waives only the source clear-ID prerequisite in the derived War
table, retaining every saved stage/progress field. Normal enable/disable restores
the source rule; the flag is retained on parent/calendar refresh. This lab trial
uses the flag to attempt War entry. The corrected native stage-list waiver
completed one `/guild-war/enter` and began rendering the cooperative screen.
The next rejected pending packet was `/user/mark-tutorial` with tutorialIds [1037],
the already catalogued passive cooperative-help ID. Imported mutation gating
now permits only built-in passive help acknowledgments through this handler;
gameplay/configured IDs still reject. The actual packet passed on an in-memory
copy with only the seen-help list and its revision changing once, no duplicate
writes, and unchanged real source data. The basic-course UI remains unresolved.
After the help fix the user confirmed
the mode starts; the next Multi-lobby request was
`/guild-war/get-all-castle-simple-infos` with native lowercase seasonId 1.
The guarded read now returns an empty native CastleSimpleInfos array, without
invented other-guild ownership/markings or account writes; its real-account wire
and repeat checks passed read-only. The user confirmed that fix passes. The next
actual pending call, `/guild-war/start-coop-stage`, now acknowledges loading with
an empty object after validating the source season's cooperative stages and an
owned captured Raid/Conquest preset. Native success creates the stage locally
without reading response fields. The real request for public stage 850030005
and a repeat passed with zero source writes or profile differences; it does not
save selections, costs, attempts, locks, battle results or rewards. APK stage
loading passed: the user confirmed the phase opens. The actual pending completion
`/guild-war/end-coop-stage/v2` now validates native stageId/damages/additionalDamage
and acknowledges the free result with Cancelled false, fresh GuildWarInfo and
empty AddedItems. The real packet/retry passed read-only without writes or profile
changes; damage/score/progression, attempts, locks, costs and rewards are not
persisted. Native result display adds a static participation item locally; this
does not grant inventory in the server database. The running API accepted the
end request; the next failure was `/guild-war/get-battle-records` during menu
synchronization. It now returns native empty LatestBattleRecords,
CoopDefenseInGuildRanking and DailyBattleStatus arrays for season 1, without
inventing records/rankings or writing state. The actual request/retry passed
read-only. The API then accepted the follow-up, with no queued request remaining;
the user then reported a frozen result screen. A read-only window capture showed
the incomplete scene, and process-scoped Unity logs identified missing item spec
21644 in ItemBox.OnItemUpdate during GuildWarResult.SetBoss/Begin. Native EndCoop
appends that static participation item locally even when server AddedItems is
empty. The War overlay now zeros only PlayCoopCoinReward (originally 10), so the
native helper skips the append. Policy 3 upgrades legacy selections automatically
without changing their valid period, waiver or account. The additional regression
covers migration, exact derived-table preservation and malformed policies; the
actual table audit/completion/retry checks passed read-only. After full restart,
a read-only native probe confirmed the coin count is zero and the unrelated medal
count remains 12. The replay visibly completed the cooperative attack result,
including per-character damage and Exit control. The user confirmed Exit returns
to the War menu; a fresh window observation verified the lobby with all three
entries available. The current process's bounded log check contained no matching
missing-item/result exception. Persistent progression and other War modes retain
their unfinished boundaries.

The next observed failure occurred when leaving an unfinished battle:
`/guild-war/abandon-stage`. Native SendGuildWarAbandonStage sends no parameters,
and its coroutine does not consume response resources. The guarded local trial
now returns `{}` without recording results, attempts, refunds, rewards, character
locks or profile changes. Two regressions and real-source read-only wire checks
cover empty/null/object bodies, retries/reconnect and rejection of unsupported
parameters or saved progression. The actual backend was reloaded and the user
confirmed the stage can be abandoned after reconnect.

Opening Dispute while the local view remained CoopOffense then froze its Multi
lobby. No API was pending; Unity reported SwitchExpressionException in
GuildWarMultiLobby.Begin. The native switch accepts only phases 3/4. An explicit
`guild-war enable --phase` choice now persists one of the four native phases,
defaulting legacy selections to 1 and retaining valid period, waiver and phase
during recomposition. Existing cooperative battle calls reject a mismatched
Multi phase. Real-account phase-3 entry/castle/abandon/repeat wire checks passed
read-only with zero writes. After full restart the user confirmed Dispute opens.
The next rejected packet marked tutorial 2026 seen. The four native Multi lobby
introductions (2025/2026 for phase 3, 2028/2029 for phase 4) now have scoped trial,
phase and ownership guards; other imported gameplay tutorial IDs stay blocked.
Their source tutorial2 groups contain only presentation/interaction actions.
The actual 2026 request passed on an in-memory account clone with only seen-help
and its revision changing once; retries made no writes and the source stayed
unchanged. After reload/reconnect the user confirmed continuation. The lab now
uses multi-offense; Multi combat and persistent progression remain unfinished.

The guild-information path next requested `/guild-war/get-ranking` and the
separate `/guild-war/get-guild-coin-ranking`, each with native integer seasonId
1. They now return empty native defense/coin ranking views: default rank zero
with an empty RankingGuildEntry array, and an empty GuildWarCoinRewardRecord
array. No other-guild ranks, coin settlement, points, rewards or profile changes
are generated. Four regressions and both actual request/retry wire checks passed
with query-only/read-only source SQLite and zero writes. The user confirmed each
view loads after backend reload/reconnect.

The next freeze occurred at the exchange center, without a pending API. Unity
reported NullReferenceException in GuildWarShopConstantsItem.Set/ItemUpdated/SetUI;
native Set unconditionally resolves absent currency spec 21644 for each offer's
icon. The policy-4 overlay now removes only ShopSet entries in the active season's
ShopGroupId 4001 (five real-source offers), retaining other groups/source data.
The native flat-list filter and zero-item UI path support an empty local shop;
no currency spec, balances, purchases, counters or rewards are manufactured.
Two added regressions and the actual composed-table/read-only account audit
passed, retaining phase, window and waiver with zero source writes. After full
restart a native read-only probe confirmed zero shop rows; the current process's
bounded log check had no matching shop exception. The user confirmed the empty
exchange opens and allows returning without a freeze.

The user then reported inactive Dispute castle buttons. The earlier empty list
now expands in phases 3/4 to the matching season's CastleDeployGroupId 1001:
40 native castle specifications across grades 1..4, each with neutral local owner,
marking count and capture days. Cooperative views stay empty. A new guarded
`/guild-war/get-castle-detail-info` reader accepts native integer castleId from
that deployment and returns neutral identity plus typed empty DefenseBuffIds,
TodayBattleStatus and BattleHistory, with NotExistCastleData false. No account,
static table, rival guild, battle result, resource or reward is changed.
Six regressions and real-source read-only wire checks passed: all 40 details and
repeated map reads preserved the source profile with zero writes. A bounded
immutable cache avoids repeating static decompression while checking the file
digest on every request. The backend was reloaded; after reentering Dispute the
user confirmed selecting a castle opens its information. Multi stage entry and
results remain unfinished.
Bounded Windows sharing-lock retries
also retain atomic selector publication after repeated transient test failures.

The subsequent defense trial clarified that the requested mode was the second
Fortress/Dispute tab. A cooperative phase there throws SwitchExpressionException
with CoopDefense; `coop-defense` only fits the first lobby. Phase 4 loads the map
but neutral castles still select Siege Battle. Native OnClickEnter chooses the
defense stage list when the selected castle matches CapturedCastleId, while
IsCaptureGuild compares its CaptureGuildId with the owned guild ID. The opt-in
`--defend-castle` selector now presents one validated native castle as locally
owned in phase 4, consistently across entry, map and detail, with no saved capture.
Zero resets the mock, another phase clears it, and phase-4 refresh retains it.
Only the matching owned GuildSummary is available, with existing guild/member
data and null rank/damage. Five regressions and repeated real-source read-only
entry/list/all-40-details/summary checks passed without source writes or changes.
After backend reload and full game restart the user confirmed Defense Battle
appears for the owned castle. The guarded defense handlers below extend this
selection; the free Multi siege trial is described below, while persistent
captures remain unfinished.

The next actual packet was `/guild-war/start-multi-stage` for defense 850060004,
with integer stageId/presetId. It now returns native empty GuildBuffIds and
CastleBuffIds arrays after validating the owned captured preset and the selected
castle grade's unique native DefenceStageIds list. The v2 Multi completion uses
the cooperative damage schema and returns Cancelled false, the unchanged trial
GuildWarInfo and empty AddedItems. Neither route writes results, captures,
attempts, resources, locks or rewards. Five regressions cover schemas, Int64
bounds, ownership/grade/catalog guards and legacy-overlay refresh. The actual
start and inferred end/retries passed the wire codec on real read-only SQLite;
the source profile and immutable static body remained unchanged. The user
confirmed the phase loads after reload/restart.

The API accepted the real defeat completion, then its result renderer failed on
missing item 21661. Native Multi completion appends local participation items:
21644 from PlayMultiCoinReward (offset 0x60), and 21661 from GetPointPlay (0xc4),
rather than the named PlayMultiBattleMedalReward field (0x68). Policy 5 suppresses
those counts plus the named Multi medal count, retaining the earlier cooperative
coin suppression. Other source constants stay unchanged. A real War-table audit
confirmed exactly those overrides, the existing shop filter and optional course
waiver, with no profile writes or source replacement. Policy-4 selectors upgrade
while retaining phase, castle, valid period and waiver. A full restart is needed
to discard native cached counts. After full restart/replay the user confirmed
the complete result and menu return. Read-only native inspection confirmed all
four counts zero, with the cooperative medal count retained at 12; the current
process's bounded log had no missing-21661 or GuildWarResult error frames.
The user subsequently confirmed the remaining listed scenarios, including
defense victory, abandonment/reentry, same-hero repeats, formation/preset changes
and all four cooperative attack maps. These are user-reported checks without
separate per-scenario native traces.

Guild Information can still be empty without blocking the game. The process
reported UISceneManager.LoadUIAsset null references and GetLastPhaseInfo cached
date parse errors, with no pending API. Their causal relationship is unresolved;
no client preference was changed while the user continued battle testing.
See [usage and detailed limitations](guild-war.md).

The user later reported cooperative defense works and asked about brief loading
delays. Read-only profiling identified full-static-data decompression on every
cooperative start/end request. Unprofiled source-account handlers took about
1.5-1.8 seconds before a bounded content-and-season-keyed immutable catalog cache
was added. Current file SHA-256 validation still precedes cache lookup; new body
content and season IDs cannot reuse the wrong catalog, and callers receive
isolated sets. Seven-repeat median handlers measured 27.2 ms for start and
21.2 ms for end; session/packet processing measured 27.8/21.8 ms. The source profile
was unchanged with zero writes. The first catalog lookup after backend restart
still took 1.48 seconds. These are host-side timings; after backend reload the
user confirmed repeated cooperative entry/exit feels faster. APK latency and
combat frame rate remain unmeasured. Two regressions cover repeat loading and
cache isolation/refresh, and the existing tampering case now checks a warm cache.

The next focus is `multi-offense` Siege Battle. Native phase-3 castle entry uses
SiegeStageIds and the existing Multi start/end schemas. The guarded free trial
now accepts only the active season's unique stage-group sets for deployed castle
grades, yielding 16 native source stages. It validates the owned captured team
and returns empty buff arrays, then acknowledges bounded Int64 results with
unchanged trial info and no items. It persists no captures, damage, attempts,
locks, costs or rewards and retains policy-5 client reward suppression. Five
regressions cover repeated loading/results, reconnect, phase/catalog/team guards,
saved progression, corruption and immutable caching. All 16 native-inferred
source-stage start/end/retry/abandon sequences passed on real read-only SQLite
without writes or profile/source/selection changes. After reload/full restart
the user confirmed the menu loads, but stage entry may be unavailable. A native
read-only probe found phase 3, IsBattleRound true and no pending request; actual
APK combat and result/menu return remain unverified.

The user clarified that the blue-castle popup has only one blank bottom button,
which closes it. A read-only native probe identified castle 21 in phase 3 with
combat active, MarkedCastleId zero, isMarked false and no cooperative/season-end
block. Native SetBattleUI uses the `not_marked` button layout. The explicit
`--attack-castle` selector now provides a local marked siege target, without
invented rival ownership, capture, resources or saved guild progress. The map
marks only that target and combat is restricted to its native grade's four siege
stages. Phase-3 omission/refresh retains it, zero resets it, and another phase
clears it; legacy selectors remain unmarked. Four regressions and real-source
read-only target-21 entry/map/detail/start/end/retry checks passed, with another
grade rejected and no writes or source/profile/selection changes. The backend
was reloaded and target 21 selected. After full restart the user confirmed the
entry button opens the stage selection, then an attack stage loads and is
playable. The user then confirmed the result and return to the castle menu;
the particular victory/defeat outcome was not separately identified.
The existing empty labels remain a separate unresolved UI issue.

The user next requested a command for preparation-round practice. Native code
has a separate StartMultiPracticeStageRoutine path, reached with the practice
flag rather than the ordinary Multi start API. The new `--round prep|combat|auto`
selector prepares policy-6 static data: only MultiBattleRoundStartTime is changed
to 24/0 for prep/combat, with the source value 12 restored by auto. The server
clock and season window stay unchanged. Multi phase changes/refresh retain the
choice; cooperative phases reset it to auto, and old selectors upgrade to auto
while preserving valid state. Four regressions passed for scoped changes,
restoration, checksums, upgrade/refresh, validation, atomic rejection and CLI use.
A private real-source preparation verified hours 24/0/12 and unchanged other War
data. Read-only entry/all-40-map/details checks had zero writes and unchanged
profile/source/active selector. The supplied prep command clears the siege target
to test unmarked-castle practice. After full restart the user reported it works
well and prefers it for testing attacks. Read-only native inspection confirmed
phase 3, start hour 24, IsBattleRound false, no marked/captured target and zero
participation counts, with no pending API. Individual castle results were not
separately enumerated.

At the user's request, the unmarked Prep Round attack command is highlighted as
important/recommended in the README and War guide. The equivalent
`multi-defense --round prep --defend-castle 21` command was supplied for defense
practice testing; unlike the attack browse path, it selects an owned trial
castle. The user confirmed it works after restart and asked for the same important
marking. Both commands now have important callouts in the README and War guide;
individual defense-practice results for every castle were not separately listed.

## French interface text in the Windows lab

Changing text language to French saved `frFR` and restarted the client, which
requested `media/staticdata/strings-bin-frFR`. The local CDN returned 404 because
the preserved content contained EN/ES strings. Backend counters showed no new
rejected or unsupported API calls during this failure.

The matching public `live/global/0491` CDN still supplied the French file. The
English resource's remote size and ETag matched the local file, whose MD5 also
matched that ETag. The 8,018,592-byte French download passed its length and MD5
checks before being saved with its ETag and SHA-256 manifest entry. Four further
requested French resources were preserved: the chat/name word lists and the
Roadmap 3.57 and Meteor banners. These remain external lab files, outside Git;
the published content release still contains EN/ES text. The existing manifest
entries were retained, following the [resource layout](reference-data.md#preservation-manifest).

After the CDN reload, the APK downloaded the French strings with HTTP 200,
fetched its account and entered the lobby. The user confirmed the lobby displays
French text. Read-only inspection verified saved language `frFR` and a downloaded
French cache file whose SHA-256 matches the local CDN copy. All five added
resources passed local HTTP/hash checks, and no new rejected or unsupported API
calls appeared. Other screens and their localized assets need separate APK checks.

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
