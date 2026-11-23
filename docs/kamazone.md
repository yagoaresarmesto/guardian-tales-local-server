# Optional Kama-ZONE entry, benefits and challenge practice

`kamazone` selects one preserved Global/EU season so the Android 3.57.0 client
can show its card in **Events**. Without a local run, entry shows a
**read-only idle lobby preview**. Events can select and load a mode automatically
before displaying its drawer, so `/kamazonland/enter` supplies the preview even
without a card tap. Difficulties 1, 2 and 3 use the preserved regular floor layouts. Combat
victories offer seasonal artifacts. Confirming a boss reward opens the next
regular floor and carries the party, HP and inventory forward. Shops sell preserved seasonal artifacts for run-local silver coins. Shelters support resting, reviving and purification. Special nodes
support weighted events, local effects and story continuations.
Reactive battle artifact effects, event battles/bottle caps and season rewards remain
unimplemented. APK combat entry,
accepted victory results, map return, further normal/elite encounters and shop
entry/exit, shelter Rest and the following boss battle are observed. Finish
Challenge can conclude the local run; an accepted finish followed by a fresh
challenge is observed, without separate reopen confirmation.
An additional opt-in practice setting can unlock selected seasonal benefits,
provide a point budget and retain benefit choices outside the saved account.

## Node coverage

Native 3.57.0 type registration identifies all seven real map types below.
`None` (0) is a sentinel, not another encounter. This inventory comes from the
client and retained tables; users do not need to find each type by provoking a
connection error. Packet/model inspection and host tests establish contracts,
while representative APK runs verify scene loading, action feedback and caching.

| Type | Implemented host behavior | Remaining work |
| --- | --- | --- |
| Starting (1) | Initial challenge position and original connections | No separate encounter action |
| Normal (2) | Battle, HP, seasonal artifact choice and connected progression | Coins and reactive battle effects |
| Elite (3) | Same lifecycle with elite enemies and loot weights | Elite affixes and currency |
| Boss (4) | Boss artifact selection and transition to the next regular floor | Final season clear, infinity and season rewards |
| Shelter (5) | Rest, one random revive, one random curse removal, skip and resume; Rest observed in the APK | Artifact-based recovery modifiers; revive/purify APK verification |
| Shop (6) | Buy seasonal normal artifacts with silver, apply artifact discounts, replace at capacity, resume and exit | Curse and effect goods, including shop refresh |
| Special (7) | Weighted seasonal events, conditions, persistent choice/results, local effects, random conclusions and story continuations | Event battles, bottle-cap awards, additional condition/effect kinds and APK validation |

The retained pack contains 328 special events, 779 choices and 135 random
conclusions across its seasons/services. Season 43 references 68 events and
163 choices with twenty nontrivial effect kinds, plus `None`. Its declared
availability does not mean every event can appear on every floor. Effects include
HP changes, artifacts/curses, local coins, conditional progress and battles.
Across all retained choices there are eight condition kinds. Building their
generic condition/effect engine is distinct from merely opening a Special node.
The implementation below covers eighteen of season 43's twenty nontrivial kinds.
Choices requiring unavailable effects are omitted from the outgoing choice list,
rather than displaying a successful reward which was never granted. This is not
complete coverage of every retained event branch.

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
challenge probe, follow the opening-floor section below. The shop section covers
entry, purchases and exit. Other missing actions appear in the route audit.

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
Subsequent regular floors use their own layouts and difficulty rows. Final
season scoring and infinity mode are outside the implemented flow.

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
algorithm. It uses the original floor connections and probabilities,
preserved nonhidden monster groups and preset positions, and guarantees one
reachable opening battle with an originally allowed type. Elite affixes are not
generated yet. Shops and special nodes retain their original probabilities.
Shop, shelter and supported special-event navigation are implemented.
Account currency rewards, scored rankings and
season completion remain unimplemented.
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

For a victory, the client checks the enemy-defeated flag with the node-clear
flag still unset. The backend returns node state 5 and a single group of up to
three distinct IDs in `LootArtifacts`. Only lootable normal artifacts from the
selected season qualify, after applying its exclusions. The local draw weights
each available rarity using `BattleLootWeightsNormal`, `Elite` or `Boss`,
then picks within that rarity. Empty or zero-weight tiers are skipped. This
choice count and weighting policy reconstruct the reward flow locally.

The offer survives reopening. The player can accept one offered artifact or
decline with a null selection. At eight occupied slots they can select a
zero-based replacement index. The client confirms with
`/kamazonland/close-battle` using `NodeId`, `LootArtifactId` and
`DiscardArtifactIndex`. The backend saves the choice once and marks the node
cleared. A boss confirmation also moves the party to the next regular floor's
starting node in the same write. The transition retains HP, formation, run
artifacts, curses, coins and event story progress. The new map uses its own
connections and encounter rolls. The first floor keeps its original seed sequence.

Reopening an older active run stranded on a defeated first-floor boss presents
the outstanding offer. Reading the map leaves the run file intact. Confirm the
reward to continue to floor 2 without restarting the challenge. Previously
passed nodes stay complete. The original APK still needs to be checked for the
loot popup and floor-change animation. Automated packet tests and a copy of the
stranded run cover both ends of the transition.

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
shop discounts come from the artifacts the player holds. This is local stock generation,
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

Buying sends `/kamazonland/buy-shop-item` with `NodeId`,
`ChoiceArtifactOrCurseId` and an optional nullable `DiscardArtifactOrCurseIndex`.
A purchase charges the displayed artifact's silver price, adds it to the run
inventory and marks its stock entry sold in one write. The price includes
`MallShopDiscount` from each held artifact before replacement, capped at 100%.
At eight artifacts the player must choose an occupied, zero-based replacement
slot. Insufficient funds, unavailable stock and an invalid slot leave the run
intact. A repeated request receipt cannot charge twice. The 4,000-point benefit
budget is a separate balance.

Eight shop regressions cover seasonal/exclusion rules, native Boolean stock,
entry/resume/exit, adjacency and combat guards, legacy files, invalid saved stock,
authentication, failed publication and unchanged account/static data. The actual
pack copy replays node 143, populates three seasonal artifacts at original base prices, closes
it and checks reopen/retry without changing the existing combat map, HP, party,
benefits, balances, battle count, account/XP tables or 55 source reference files.
The observed follow-up reaches a Shelter from the completed shop, establishing
shop entry/exit and retained progression in the APK. A copy of the season 43
floor 2 shop had 90 silver. Independent purchases at 40 and 60 silver retained
the artifact and sold flag on reopen. The 100-silver item stayed on sale after
the insufficient-funds check. Purchase feedback in the APK awaits confirmation.

## Mode route audit for Android 3.57.0 EU

The [client route inventory](reference/client-api-inventory.json) lists 23 direct
`/kamazonland/` routes. Adding the separately identified ranking read gives 24.
The current backend registers 16. The following eight have no handler.

| Player action | Missing routes under `/kamazonland/` |
| --- | --- |
| Apply a preset or set preset | `apply-preset`, `apply-set-preset` |
| Open the gacha reward list (excluded item specs) | `get-except-item-spec-ids` |
| Enter infinite mode or sweep | `infinitize`, `sweep` |
| Buy a random box or gacha draw | `buy-random-box`, `buy-gacha` |
| Claim a likeability reward | `claim-likeability-reward` |

A related exchange operation, `/exchange/kamazon-land`, also lacks a handler
outside that namespace. A registered route can have partial behavior. Rankings
return an empty list. The final regular floor has no season scoring or payout. Normal shops do
not yet offer curses, effect goods or stock refresh. Special-event combat and
bottle-cap award branches remain unavailable. Combat silver income, elite
affixes, reactive artifact effects and artifact-based shelter recovery also
remain incomplete. This audit covers known requests and code paths. A complete
Android playthrough has yet to be verified.

## Shelters

The captured `start-stage` for node 152 targets Shelter (5). The same type-based
entry works for any connected shelter, preserving the existing seed and monster
rolls. A visit is marked cleared (3), with one unused choice. Back/Confirm closes
the native overlay without a dedicated close API; leaving for a connected node
forfeits an unused action without healing. The next successful action stores its
chosen state (11). Retrying an unused entry does not create another visit.

`/kamazonland/take-shelter` accepts `NodeId` and the native integer `ChoiceType`:

| ChoiceType | Action | Local result |
| --- | --- | --- |
| 0 | None | Leave without changing HP or curses |
| 1 | Rest | Add the original recovery percentage to living heroes, capped at full HP; do not revive defeated heroes |
| 2 | Revive | Restore exactly one random defeated hero |
| 3 | Purify | Remove exactly one random seasonal curse |

The preserved `ShelterHpRecover` is 0.4. Native `ShelterHpRecover` converts that
fraction to an integer percentage; rest therefore adds 4,000 to the 10,000-unit
HP scale before clamping. Original English descriptions independently establish
living-hero recovery, one random revival and one random curse removal. The
revival amount itself is not specified in those retained inputs: this local
trial uses full HP, an explicit local policy rather than a recovered server rule.
Artifact recovery modifiers remain unimplemented.

One action consumes the visit. Identical retries return the current state
without another heal, revival or purification; a different second choice is
rejected. No-dead-hero and no-curse actions reject without consuming it. Separate
deterministic targeting leaves the original map/combat random stream untouched.
The external run records visits, HP and curses; the shared singleton supplies
those values and its shelter counter. Older files default missing fields in
memory without read-time writes. There are no account, XP, inventory or balance
changes and no gamefile edits.

Eight regressions cover all four choices, living/dead HP, limits, single-use
retries, skipping without an API, legacy data, invalid curses, authentication
and failed publication. A coherent actual-account copy replays node 152 and the
native Rest request: HP 7,650/9,121 becomes 10,000/10,000, with three battles and
one shelter visit. It reopens/retries and loads connected boss node 160 while
retaining the complete original map, party, benefits, budget, shop stock,
effective static data, account/XP tables and 55 source reference files. APK
shelter entry, Rest and return navigation are now observed: the stored visit
records choice 1, followed by a successfully entered and completed boss node 160.
Reopening persistence and revive/purify actions lack separate owner confirmation.

## Special events and story threads

The captured node-123 `start-stage` targets Special (7). Entry uses the selected
season's original event list, base/additional weights, conditions, floor and
difficulty gates. A separate seeded stream leaves all existing map/monster rolls
unchanged. The event and its offered choices are stored per node, so reopening
and retries never redraw them. Hidden continuation events require an active
story link. Original event names, descriptions, actors and art stay unchanged.

Generation is a local reconstruction, not the recovered official algorithm.
At the current run floor, positive `AppearFloor` values are treated as
earliest floors and negative values as latest floors. Artifact/curse ownership,
coin/count and event-choice conditions gate the available branch. Hero-spec and
bounty conditions remain unavailable; owned instance IDs are not mistaken for
hero catalog IDs. Completed choices affect conditional weights, including the
original negative additions that suppress completed story entries.

The native requests are:

- `/kamazonland/choice-special-event`: `NodeId` and `ChoiceId`.
- `/kamazonland/close-special-event`: `NodeId`, `LootArtifactIds`,
  `DiscardArtifactIndices`, `LootCurseIds` and `DiscardCurseIndices`.

In `SpecialEventChoices`, **true means chosen**, as confirmed by native
`EnterNode`; it does not indicate availability. Entry supplies false flags,
choosing marks exactly one true and state Chosen (9), and confirmation marks
Cleared|Chosen (11). The unconfirmed result blocks onward movement and can be
resumed. Nullable loot/discard arrays align with each offered gift: accept its
exact ID, replace an existing zero-based slot or decline it with null. Both
artifact and curse inventories respect the native eight-slot limit. Validation
rejects fabricated IDs, bad lengths/indices and changing an already confirmed
reward. Empty omitted/null/list forms are equivalent on retries.

Supported local effects include silver-coin gain/cost, living-hero healing and
damage, random single-hero effects, counted revival, artifact gain by ID/rarity,
all-ID gifts, specified/random artifact removal and seasonal curses. All-hero
results use one native description; random/revive effects use character rows.
Gifts remain pending until confirmation. Revived HP follows the existing full-HP
trial policy; event damage can defeat a hero. Those are explicit local policies
where authoritative server rules are unavailable. Artifact battle/shelter/removal
counters are retained; reactive battle artifact-effect handling is still pending.
Silver coins are run currency, separate from the 4,000 benefit allocation.

Random conclusions use their original group, conditions, highest eligible
priority and weights, and retain the selected conclusion ID for native text.
Story links keep a root, next event and choice history. Challenge links reset on
an explicit new challenge; season links and learned events/choices/conclusions
survive it. A link can migrate from challenge to season scope without losing its
history. The outgoing native progress dictionaries contain the recorded choices.
These policies are outside the working account, bound to source, season and user.

`Battle` and `GetCap` branches are not offered yet: nested battles and bottle-cap
account rewards need separate implementations. Unknown condition/effect kinds
also reject eligibility. The engine does not substitute another outcome for an
unsupported random conclusion. At the reported season-43 state, 36 initial
events with 65 choices are eligible; hidden chapters require later progress.

Fifteen regressions cover variety, source gates, native flags, entry/choice/close,
season/challenge continuations, weighted conclusions, HP/coins, deferred gifts,
capacity/replacements, counters, reopen/retry and atomic rejection. The coherent
actual-account copy opens the exact node as event 402 with choices
40202/40203/40204, then exercises all 65 eligible initial choices through entry,
choice and confirmation. Account/XP tables, effective static data, existing
map/enemy rolls and all 55 original reference files remain unchanged. APK event
display, choice feedback and confirmation remain pending verification.

## Finish Challenge

The captured button sends `/kamazonland/conclude` with
`{"keepingArtifactId":null}`. The field uses lower camel case, as independently
confirmed by the native sender. Its success coroutine checks the response,
closes the popup and returns to the idle Kama-ZONE lobby. It does not itself
request the next floor or select a battle reward.

The backend marks the separate local run inactive and returns its complete
singleton with `Progress.Concluded=true`. The ended floor snapshot retains
its node, map seed, party/formation, HP, counters, shop stock and shelter visits.
Reads/reopening do not rewrite it. Benefit selections, allocated points, main
account inventory/balances and trial XP are unchanged. Finishing awards no season
clear, score or currency. With Artifact Keep selected, the same field accepts an
owned artifact ID. The native picker disables rarities 4 and 5. The ended run
records the choice in `Progress.KeepingArtifactId`. With the benefit still
selected at the next start, one copy carries over with fresh counters, even if
the old run held duplicates. A null choice carries nothing.

Finishing requires a run that has left its starting position. Active combat and
unresolved victory loot block it; a reported loss or an encounter panel without
active combat can be concluded. Repeating a completed finish is harmless.
Recent request receipts also prevent a stale finish from closing a subsequent
challenge. New stage/battle/result requests reject a concluded run until an
explicit new challenge starts; the new challenge retains the party and benefits
and resets only local run HP/map/counters.

Eight finish regressions cover open encounters, defeated/boss-completed runs,
reopen/retry, a subsequent challenge, malformed/artifact IDs, phase guards,
authentication, source/season/owner isolation and failed atomic publication.
The coherent actual-account copy replays the captured null-keep request from
cleared boss 160, retaining four battles and one shelter visit, and verifies
reopen/retry and a fresh challenge without changing account/XP tables, effective
static data or 55 original reference files. Follow-up counters and run state
show an accepted finish followed by a fresh challenge; a separate owner check
of popup closing/reopening remains absent. Battle artifact selection and regular floor advancement are described under
[local battle results and closing](#local-battle-results-and-closing).

## Starting aids and regular-floor checks

Starting a fresh challenge applies the selected seasonal benefits. Artifact Aid
offers an original lootable normal artifact of rarity 0-2. Curse Aid offers a
seasonal curse. Both respect seasonal exclusions. Silver Coin Aid grants the
amount listed for the selected level. A player can take either aid separately
or both; leaving the starting position expires any outstanding choice.
Reopening the same start or resending a confirmed pick preserves the existing
inventory. A conflicting second choice is rejected. Older runs can finish with
a retained artifact without resetting their current floor.

The optional host regression plays one seeded route through all eight regular
floors at each difficulty for seasons 41-43, including all seven node types,
boss loot and a manual finish. It uses a temporary run and a synthetic party.
From the repository root on Windows, supply the matching external static data:

```powershell
$env:GT_KAMAZONE_TEST_STATIC = (Resolve-Path '.\local\client-data\reference\static_data_get.bin').Path
.\.venv\Scripts\python.exe -m unittest tests.test_kamazone_playthrough
```

This exercises the backend. Retention and starting aids still need an APK
confirmation. A separate replay on a copy of the owner's floor-two run covered
a null choice and each of its three distinct owned artifact IDs, a lobby
reopen, a new difficulty, a starting aid and retries.

## Response latency

Every run action projects a complete Kama-ZONE singleton. Previously its
mini-season lookup decompressed and verified the entire static pack again on
every response, even after the run and benefit catalogs were warm. An isolated
actual-account profile identified that decode as the dominant repeated work.

The lookup now retains only the validated mini-season integer in a bounded
two-entry in-memory cache, keyed by the complete original source bytes and
selected season. Authentication, expiry and content-binding checks still run on
each request. Benefits, HP, party, nodes and run state are read/projected afresh;
no account snapshot, mutable response or game resource is cached by this lookup.
A changed pack/season requires a new lookup, and a backend restart clears it.

On the same Windows account copy and inputs, three warm baseline reads had a
median of 922.65 ms; five optimized reads had a median of 29.28 ms (31.5x for
this host response path). All 10,750 response bytes matched exactly, with
unchanged account/XP tables and all 55 original reference files. Two regressions
verify one static decode for repeated entries, independent mutable responses,
source/season invalidation and unchanged content guards. Existing run/benefit
tests verify that warmed responses still reflect changes.

These measurements cover server response generation, not complete scene loading
or emulator FPS. The first request after restart still prepares the static
lookup. The reported apparent infinite loading eventually completed; no queued
request or new API rejection was observed at the diagnostic snapshot. The
longest scene delay has not been attributed to this single bottleneck. The owner
later estimated another return at roughly fifteen seconds, then reported that
the next observed return was fast. Fresh counters show an accepted finish, new
challenge and completed first-node battle with no new Kama-ZONE rejection.
This is a qualitative APK improvement report, not a timed end-to-end benchmark
or proof of the earlier delay's cause. Read-only coroutine sampling was partial
and does not identify a specific cleanup/resource step as the culprit.

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
