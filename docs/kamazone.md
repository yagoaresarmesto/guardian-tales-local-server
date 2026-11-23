# Optional Kama-ZONE entry, benefits and opening-floor practice

`kamazone` selects one preserved Global/EU season so the Android 3.57.0 client
can show its card in **Events**. Without a local run, entry shows a
**read-only idle lobby preview**. Events can select and load a mode automatically
before displaying its drawer, so `/kamazonland/enter` supplies the preview even
without a card tap. Experimental challenge and combat entry now cover the first
floor at difficulties 1, 2 and 3, with local battle results, retained HP and
connected combat-node progression. Shop entry/exit displays preserved seasonal
artifacts. Purchases, loot, shelter/special-event interactions, later floors and
rewards remain unimplemented. APK combat entry, accepted victory results, map
return and further normal/elite encounters are observed; shop navigation is
pending verification.
An additional opt-in practice setting can unlock selected seasonal benefits,
provide a point budget and retain benefit choices outside the saved account.

The matching external pack retains three Global/EU event seasons:

| Season ID | Name |
| --- | --- |
| 41 | Valentine Season |
| 42 | Lifeguard Season |
| 43 | Mecha Harpy Scintilla Season |

Four additional records belong to another service and are excluded from this
selector. The older permanent Kama-ZONE data and Tetis/RogueChess are separate
systems. Installing or updating the code alone activates nothing.

## Commands

Run from the repository root in PowerShell. The default reference directory is
`local/client-data/reference`; append `--reference-dir` when using another one.

List the seasons:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone list
```

For a clean client reload, close Guardian Tales and stop the backend with Ctrl+C
before changing the selection. CDN and bridge can remain running. Select one
season, for example the most recent preserved Global season:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone select --season-id 43
```

Start the backend again with the same state, reference and certificate arguments
as usual. The CDN must also use the same reference directory:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales assets --resource-root .\local\client-data\resources\files --port 18081 --journal .\local\cdn-requests.jsonl --reference-dir .\local\client-data\reference
```

After updating the project, restart the CDN with this command too. The bridge can
remain running. Reopen the game and inspect **Events** for the Kama-ZONE card.
When its historical banner is absent, expect a generated **KAMA-ZONE / SEASON 43 /
MENU PREVIEW** image (with the selected ID). The idle lobby may load automatically.
You can inspect the entry and return to the main lobby. For the experimental
challenge probe, follow the opening-floor section below. Shop entry and exit
have a separate probe below; purchases, gifts, missions and rewards remain
unsupported.

Inspect the selection and whether its visibility window is active:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone status
```

To restore the original calendar, close the game and stop the backend, then run:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone disable
```

Restart the backend and reopen the game afterward. Other enabled experiments
retain their own settings.

## Calendar and preservation

Selection creates a local fourteen-day season window starting at the current
UTC day's midnight, followed by seven days of reward-period visibility. These
are calendar fields for the native menu; this command grants no tickets or
rewards. Selecting the same season during its fourteen-day window is a no-op;
reselecting after that window refreshes the dates. `status` reports the dates and
`menu_active_now`. The server/client clock itself is never changed.

The private `kamazone_selection.json` file is published atomically in the chosen
reference directory and bound to the original static pack's SHA-256. An active
selection rejects a changed content pack until disabled or explicitly selected
again. No account database is opened by the command. Its persistent change is
only the optional selection file; imported progress and trial XP stay intact.

The backend composes the calendar over its other effective static overlays. It
changes the chosen season's Global dates and suppresses any overlapping Global
Kama-ZONE season. Other regions, seasons outside that window and unrelated
events retain their data. Static get/check share the new checksum. Disabling
restores the exact parent calendar content with an advancing revision so the
client can replace cached active dates. A disabled configuration is retained
for that revision history; an installation without a configuration keeps its
original responses byte-for-byte.

The matching pack lacks the three historical Global banner PNGs. With
`--reference-dir`, the CDN can generate an original preview PNG in memory only
for a missing banner URL declared by the selected, currently visible season.
An existing manifest-listed image always takes precedence. Unselected URLs,
disabled configurations and installations without this option retain their
normal manifest behavior. Source binding also applies to the generated preview.
This supplies a recognizable menu image; it does not restore historical artwork.

Preserved reference/resource files, the resource manifest, the APK and shipped
scripts remain unchanged. No banner file is written. Existing Raid, Guild War,
Expedition, Andras and generated-item overlays remain independent.

## Read-only automatic entry

The observed entry request is `{"IsPartial":false}`. Both Boolean values are
accepted after local guest sign-in and the prologue, with an active selected
season bound to the matching pack. The response supplies the native
`UserKamazonLand` singleton and `NewSeason:false`. The mini-season ID comes from
the selected season's preserved group rather than being invented.

Without optional local state the preview has no party or run, a concluded floor zero, empty collections,
nonnull progress/likeability objects and zero preview points/tickets/coins.
Those are temporary display defaults, not changes to saved balances or any
historical Kama-ZONE progress. No `User` inventory delta, reward, operation
receipt or database row is created. Missing/ambiguous mini-season data,
disabled/expired selection and a changed content pack are rejected. This route
itself changes no run or benefit settings. Subsequent challenge requests use
the separate local run described below.

## Optional unlocks and a benefit point budget

For the preserved season 43, **Strong Body** is benefit **174**. It is already
listed by that season, but its normal unlock requires a special-event choice.
Practice can remove that condition in the backend's outgoing static response.
It does not fabricate completed events or change the benefit's effect/levels.

Close Guardian Tales and stop the backend before changing practice settings.
Keep the CDN and bridge running. With season 43 selected, enable the requested
unlock and 4,000 points:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone practice enable --unlock-benefit 174 --points 4000
```

Restart the backend using the same state, certificate and reference arguments
as usual. Reopen Events and the Kama-ZONE benefits screen. Strong Body should
be selectable; choose benefits, save, remove one and reopen the game to verify
the choices and the available/total point display. These checks do not require a run.

Inspect the private practice settings:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone practice status
```

To return to the ordinary preview, close the game, stop the backend and run:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone practice disable
```

Restart the backend and game afterward. The selected season remains visible;
use `kamazone disable` separately to restore its original calendar. Re-enabling
the same practice settings retains its saved test choices.

Practice writes only `kamazone_practice.json` in the external reference directory.
It is bound to the original pack and the selected season. Selecting another
season suspends these settings; an unlock cannot add an absent benefit to that
season. A changed pack is rejected until practice is disabled or explicitly
configured again. Installing the code alone activates nothing.

The configured points are the **total allocation budget**, not a balance that
stays unspent after assigning benefits. `KamazonPointTotal` is 4,000 and
`KamazonPoint` is the remaining budget after the original costs of the selected
levels. Strong Body costs its original 250 points and leaves 3,750 available.
Native `LevelUp` charges `Points[current level]` at each upgrade: a benefit with
prices `[250,500,750]` costs 750 in total to reach level two, and 1,500 to reach
level three. Lowering/removing selections refunds those allocations.

All original prices, effects, maximum levels and the eight-benefit selection
limit remain intact. Only the requested benefits' unlock conditions change in
outgoing static data; unrelated definitions and other effective tables stay
intact. The configured budget must be positive and no higher than the
mini-season's preserved limit (4,000 in this pack).

`/kamazonland/save-benefits` accepts the native `Benefits` dictionary of IDs to
levels. It validates membership, locks, levels, the budget and the eight-benefit
limit, then writes test choices to the optional file. The response returns a
complete idle singleton with an exact list of positive-level selections and the
remaining/total points. Clearing all selections returns an empty benefit list
and the full available budget. Zero-level placeholders must not be supplied:
`Membership.Load` inserts every row into its temporary selected dictionary, and
the native plus button counts its keys toward the eight-benefit cap. The former
all-zero placeholder list incorrectly filled those slots and blocked upgrades.
The last 64 operation IDs prevent recent retries from replacing newer choices.
Saves leave static revisions unchanged; enabling/disabling advances them to
reload the unlock overlay or restore the exact parent mode content. The updated
overlay also advances its revision with an existing configuration, replacing
cached zero-price data from the earlier experiment after a backend/game restart.

The working account, trial XP, APK, shipped scripts, resource manifest and
original reference/resource files are untouched. No gold, gems, tickets,
event rewards or scored runs are added. Combat use of these benefits remains
unverified in the APK.
Fifteen practice regressions cover allocation, original prices, the native slot
limit and the existing configuration/replay/restoration guards. All 290 targeted
Windows tests pass, alongside Black/Ruff and repository/link checks. A coherent
account/XP copy also verifies activation, saving/reopening, clearing, replay
protection and restoration against the actual pack and native field types,
retaining all other effective overlays, saved account/XP tables and 54 source
reference files, including the already enabled practice settings. Diagnostics
never change those live settings themselves.
The owner confirms in the APK that benefit levels can be raised/lowered, points
are deducted correctly and selections persist after reopening. Fresh counters
show three successful benefit saves. Combat use remains unverified; the next
reported request was `/kamazonland/challenge` with difficulty 3; its entry
implementation is described next.

## Experimental opening-floor combat entry

The preserved Global season defines exactly **three difficulties**, numbered
**1, 2 and 3**, each with eight original difficulty/floor rows. The backend accepts
each retained difficulty, without rewriting their enemy levels. For season 43,
floor one's normal/elite/boss levels are 59/62/64, 85/88/90 and 116/116/118.
This implementation generates only the opening floor; it does not claim eight
playable floors or a complete run.

After updating, close the game and restart only the backend using the usual
working state, certificate and reference arguments. Keep CDN and bridge open.
Open Kama-ZONE, select difficulty 3, choose an owned party and try a connected
normal battle node (the crossed-swords icon). For this probe, verify map and
combat loading, then complete the first normal battle and check that its node
is cleared on return to the map. Reopen the game to check retained node/HP state.
If another connection error appears, leave it open to identify its request.
There is no additional enabling command beyond the existing season selection.

The native request chain is `/kamazonland/challenge` (`Difficulty`),
`/kamazonland/start-stage` (`NodeId`),
`/kamazonland/select-characters` (`CharacterIds`), and `/kamazonland/start-battle`
(`NodeId`, `Formation`). Responses
project a complete `UserKamazonLand` singleton, with the preserved mini-season,
benefits and remaining allocation budget. The APK opens the encounter panel
before initializing its party: a node can be opened with an empty selection.
Its native `PartyInfo` initialization then sends the owned party, and combat
loading sends the formation handshake. Party selection may also precede the
challenge. Owned, distinct heroes are required for combat, while node opening
requires a connected generated battle node. Normal, elite and boss entry use
each node's actual type and monster preset. Opening an encounter and loading
combat have separate flags, so the party remains editable on the encounter
screen and is locked only once combat starts. The battle handshake must match
the entered node and contain a valid formation.
HP uses the client's 10,000-unit scale. Native character generation resolves
each battle monster's ID through the mode's monster table before loading its
character spec; these IDs are not interchangeable.

The observed battle request sends positions directly, for example
`{"NodeId":111,"Formation":[12,3,19,9]}`. This input is a four-position array even
with a two-hero party. It must contain distinct integer cells from 0 through 24.
`BeforeLoad` passes the current formation's `Positions` to the sender, not its
complete model. The server wraps the accepted list in the response/local-state
model `{"Id":0,"Positions":[12,3,19,9]}`, retaining an existing formation ID.
Object-shaped inputs, wrong lengths, duplicate/out-of-range cells and noninteger
positions are rejected without changing the run. Reopening restores the model;
recent retries return the current formation without reverting newer positions.

The private `kamazone_run.json` holds the selected difficulty, party, formation,
seed, current node, encounter/combat flags, node states and the last 64 request
receipts, plus reported hero/monster HP, a pending outcome, the last result hash
and a completed-battle counter. Files predating these fields remain readable without being rewritten
by entry; their next successful action publishes the added field. It is published
atomically outside the account database, bound to the content SHA-256, season
and local user. Reopening retains the same generated map; recent request retries
do not reroll it or replace newer progress. A new challenge explicitly replaces
that local run, retaining its party. Selecting another season suspends it.

Map generation is a **local reconstruction**, not a recovered official server
algorithm. It uses the original opening-floor connections and probabilities,
preserved nonhidden monster groups and preset positions, and guarantees one
reachable opening battle with an originally allowed type. Elite affixes are not
generated yet. Shops and special nodes retain their original probabilities.
Shop navigation is implemented, while shelter/special-event interactions remain
unsupported. Loot, conclusion, currency rewards,
scored rankings, further floors and season progression are also unimplemented.
Only reported wins in an active matching battle clear a local combat node;
reward balances and season-wide clears are not fabricated.

The reported difficulty-3 challenge request is APK observed. Its APK retry reached
the generated map, then sent `/kamazonland/start-stage` with `NodeId:111` for a
normal encounter while the party was still empty. The initial party guard
rejected that valid native order. The follow-up moves the party requirement to
combat loading and keeps party changes available after node opening.
Fourteen run regressions
cover all three tiers, deterministic resume, request replay, party ownership,
formation/connection guards, the actual node-before-party flow, normal/elite/boss
dispatch, native formation arrays and model responses, legacy run files,
source/season/user isolation and unchanged account,
benefit and effective static data. Automated client-contract checks and actual
APK combat observations are recorded separately in [status](status.md).

## Local battle results and closing

The APK reports `/kamazonland/end-battle` with `NodeId`, `Result`, `CharacterHps`
and `MonsterHps`. The native result enum is Victory=1, Draw=2, Defeated=3 and
Timeout=4. Hero HP is an ID-to-integer map restricted to the selected owned party;
monster HP is a list in generated encounter order, including repeated monster
specs. Both use 0..10,000. Monster count must match the entered encounter, and a
reported victory requires all generated enemies at zero HP. No result is accepted
for a different node or a battle that was never started.

A victory marks the node Started|Cleared (3), retains the reported HP and
increments the local completed-battle counter once. The response includes the
native callback's `ArtifactEffectResults` array, empty while artifact effects
are unsupported. When the node has no artifact, curse or effect choices, the
same result transaction finalizes it as Started|Cleared|Chosen (11). The observed
client can return to the map and request the next node without `close-battle`;
requiring that extra request left a valid victory stuck in a pending state.
Finalization uses the actual generated node and applies to normal, elite and
boss encounters. The next entry must still follow the original map connections.

An optional `/kamazonland/close-battle` with `NodeId` and nullable
`LootArtifactId`/`DiscardArtifactIndex` remains compatible and idempotent;
omitted null fields are also accepted. Its response supplies empty
`ChoiceEffectResults` and `AddedItems` lists. Genuine unresolved choices retain
the pending win and block party changes/another battle; they are not discarded
by automatic finalization. Artifact choice handling is still unimplemented.

Draw, defeat and timeout retain hero/enemy HP without clearing the node or
unlocking its successors. The encounter can be retried with surviving heroes,
directly or after closing; reopening never heals a reported zero-HP hero.
Recent request receipts and the last result fingerprint prevent double counting
or reapplying an outcome, including identical reconnects with a new sequence.
Old retries cannot replace a newer encounter. Legacy run files receive missing
HP/outcome defaults in memory; the next successful action publishes them
atomically. Failed publication changes neither HP nor the clear state.
Earlier pending victories without choices are normalized in the read-only view,
retaining their seed, HP, party, benefits and battle count. The next successful
action publishes that correction with its ordinary run update; invalid requests
and reads alone leave the stored file untouched. No run reset is required.

This is separate local run progress. Benefit allocations, main account tables,
trial XP, gold, gems, season clears/rankings and the preserved game files remain
unchanged. The twelve completion regressions cover victory/closing/advancement,
losses, dead heroes, malformed/foreign results, retries, old files, authentication
and failed publication. A coherent actual-account copy replays the captured
node-111 victory, closes it, reopens it and starts connected node 123 while
retaining all account/XP tables, effective static responses and 55 live reference
files. An additional coherent copy replays the actual next-node-123 request from
the owner's stuck pending win, without issuing a close request or resetting the
run. It enters the second battle and immediately finalizes another empty victory.
The APK has accepted the first result and returned to the map, exposing this
missing transition. The next-node retry after automatic finalization remains
pending verification.

## Shop entry and exit

The reported `/kamazonland/start-stage` request for node 143 targets a **Shop**,
following already completed normal and elite encounters. Shop entry now uses
the generated node type and original map connections, with the same source,
season, owner and replay guards as combat entry. It opens the shop rather than
loading a battle. Combat-only requests are rejected for a shop node.

On first entry, a separate deterministic sampler chooses up to three distinct
normal, lootable, positive-price artifacts from the selected season's `Artifacts`,
excluding its `ArtifactsException` IDs. `ShopArtifacts` is an ID-to-Boolean map:
false means available and is passed directly to the native sold-out widget.
`ShopCurses` and `ShopEffectArtifacts` remain empty. Names, icons, descriptions
and prices come from the preserved client tables; original definitions and
benefit-based price calculations are unchanged. This is local stock generation,
not a recovered official shop algorithm.

The separate sampler does not consume the map/monster random stream. Existing
node types, enemy IDs/positions and map seed stay intact. Stock is saved per
node in the external run's `shops` map; entry retries and reopening preserve it.
Older run files default that map in memory without read-time writes.

The native Exit button sends `/kamazonland/close-shop` with `NodeId`. Closing
marks the shop complete/chosen (11), clears its open flag and allows a connected
next node. The response supplies empty `ChoiceEffectResults` and `AddedItems`
lists for the native finish routine. A shop cannot be left for another node
while still open. Recent retries do not reopen stock or overwrite a later battle.

For this probe, restart only the backend, then enter the shop, inspect its list
and press Exit. Reopen the game to check that its completed state persists.
**Do not buy during this probe:** purchases, curse/effect goods and shop effects
are not implemented. The current local `SilverCoin` balance remains zero; this
entry/exit milestone grants no currency. The benefit allocation's 4,000 Kamazon
Points are separate from shop silver coins.

Eight shop regressions cover seasonal/exclusion rules, native Boolean stock,
entry/resume/exit, adjacency and combat guards, legacy files, invalid saved stock,
authentication, failed publication and unchanged account/static data. The actual
pack copy replays node 143, populates three seasonal artifacts at original base prices, closes
it and checks reopen/retry without changing the existing combat map, HP, party,
benefits, balances, battle count, account/XP tables or 55 source reference files.
APK shop opening and exit remain pending verification.

## Local rankings

`/kamazonland/get-rankings` accepts a native request with no body, JSON null or
an empty object. The signed-in guest, prologue, active selection and content-pack
checks are shared with entry. Its JSON response is `{"Rankings":[]}`, matching
the popup callback's named list. Additional parameters are rejected.

The classification is intentionally empty while there are no local scored runs.
No official rankings are requested, and no players, ranks or scores are invented.
Opening it changes no saved state and sends no account or mode-resource delta.
This read does not enable scored runs or ranking rewards.

## Evidence

Native inspection finds Kama-ZONE in `UIEventDrawer.RefreshEventList`, which
requires `KamazonLand2Data.GetCurrentSeasonByRewardUntil`; its predicate checks
the season's reward-period dates. The card routes through `GoKamazonLandMain`.
The preserved Global calendars have all expired, explaining their absence.
`UIEventDrawer.InitEventScene` can call `GoKamazonLandMain` automatically;
`KamazonLandLobby.Load` sends `/kamazonland/enter` before setting the drawer.
The first APK probe reached that request and exposed the missing read response.
The pending request and a fresh unsupported-operation counter delta confirm it.
The next APK probe reached a successful entry response but stalled while loading.
Android's Unity log identifies `JsonSerializationException` at
`UserKamazonLand.Benefits`: the native `List<KamazonLandBenefit>` requires a JSON
array. Read-only native type registration also identifies `Nodes` as
`List<KamazonLandFloorNode>`. Both empty fields are arrays; `Hps` and the two
progress dictionaries remain objects. A field-signature regression checks every
transmitted singleton field and the nested formation/progress/likeability types.

Automated checks cover Global-only selection, calendar restoration/revisions,
get/check consistency, default compatibility, no database access, source
binding, invalid data, atomic publication, overlapping seasons, expiry,
composition with Andras and scoped CDN preview GET/HEAD/range/ETag responses.
The owner confirms that Events loads Kama-ZONE and can return to the main lobby
on Android 3.57.0 EU with season 43 selected. Fresh counters show three successful
entry reads and no new entry rejection; the declared preview banner is served
by the CDN. This verifies loading and return navigation, not playable challenges,
rewards or season 41/42 in the APK. The same probe exposed a separate unsupported
ranking request; its local empty response is now owner verified too.

The initial entry change passed 271 targeted Windows tests, including static
overlays, CDN, Backroom and Training Room. A coherent file-backed account/XP copy passes selection of all three
seasons and restoration. It retains every main-account table, trial XP, the
other effective overlays and all 52 original reference files. Each missing
historical banner yields a valid generated preview; the source account and
reference directory receive no diagnostic writes or live selection.
A follow-up coherent copy replays the captured automatic entry and both Boolean
partial flags for all three seasons. It records zero database writes during
entry, retains trial XP and all 53 source reference files including the local
selection, and sends no shared account/inventory delta.
The collection-type correction passes 85 focused tests, Black (221 files), Ruff
and repository/link checks. Its coherent copy also validates every transmitted
field against the read-only native type signatures for both partial flags and
all three seasons, retaining all account/XP tables and 53 source reference files
with zero diagnostic source writes. APK loading and return navigation are now
owner verified for season 43.
The native `SendKamazonLandGetRankings` sender has no payload;
`KamazonLandRankingPopup` reads `Rankings` from the JSON resource and accepts an
empty list. Three new regressions cover its native wire shape, parameter
rejection, selection/authentication guards and unchanged saved state. All 88
focused tests pass with Black/Ruff and repository/link checks. The owner
confirms that the ranking popup opens and returns to the Kama-ZONE lobby with
season 43 selected. A fresh successful ranking-read counter increments once,
with no new rejected or unsupported operation in that verification interval.
