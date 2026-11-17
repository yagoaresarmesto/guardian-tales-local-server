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

Three mutations are now enabled: `/summon/set-select-character`,
`/summon/select-character` and `/preset/set-selected-preset`. The summon routes
use the existing local selection/draw catalogs,
atomic payment/reward transactions and session-scoped retry receipts. Supported
draws are one or ten heroes using free gems, ordinary controllers or selectable
controllers. Preset selection changes only the chosen captured Orbital preset
and the account revision, with its own atomic retry receipts. Other mutations
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
applied to the real account by those checks. Backend reload and the APK selection
retry remain pending. Creating, editing, deleting and reordering presets, other
modes' selections and Orbital formation/result writes remain unsupported.

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
