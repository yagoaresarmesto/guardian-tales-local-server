# External reference data and resources

For the matching preserved snapshot, follow the
[offline content download/import guide](offline-content.md). It supplies a
versioned Release pack and creates `local/client-data/reference` plus a CDN
resource root. This document describes individual input contracts and other
preservation layouts.

## What the source contains

`guardian_tales/templates/` holds a reconstructed empty local-account template,
empty lobby response shapes, and the small public counter-type mapping needed by
those templates. It contains no saved reference-player inventory or credentials.
An empty announcement list is encoded by the code itself.

Tests include packet/compression regression vectors, a response schema, and a
small explicitly synthetic attendance fixture. Test inputs are not a replacement
for the game content needed by an APK.

## External bootstrap directory

The default external directory is `local/reference/`, ignored by Git. Supply a
compatible set from your own prepared 3.57.0 environment, or import the content
release and pass `--reference-dir local/client-data/reference`. The backend does
not fetch missing bootstrap files from an official service.

| Filename | Used for | Stored encoding |
|---|---|---|
| `resource_urls.bin` | `/static-data/resource-url` | Body type 2: raw LZ4 plus trailing decoded length |
| `product_ids.bin` | `/static-data/in-app-product-ids` | Body type 2 |
| `static_data_get.bin` | `/static-data/get` | Body type 2; clean clients require full matching static tables, not only version/checksum data |
| `static_data_check.bin` | `/static-data/check-update` | Body type 1 reference body |
| `attendance_catalog.json` | Daily attendance reward lookup | Parsed public attendance catalog, not account state |
| `training_catalog.json` | Knight experience targets and story caps | Parsed public experience catalog for the matching build |
| `tutorial_catalog.json` | Known UI completion markers after Inn | Parsed public tutorial ID list for the matching build |
| `quest_catalog.json` | Known chapter quest registration in Inn | Parsed mapping of chapter codes to quest IDs |
| `substage_catalog.json` | Side-stage map discovery in Inn | Verified map handles and target stage IDs |
| `story_catalog.json` | Configured story openings and entry | Verified stamina, local clear prerequisites and stage quest IDs |
| `monster_catalog.json` | Defeated-monster reports in additional stages | Stable public handle indices and explicit local experience/gold rules |
| `completion_catalog.json` | Configured clear exits after Inn | Verified exit name and local required defeated-monster indices |
| `summon_selection_catalog.json` | Hero candidates and wishlist registration | Public hero origins and native selection-row fields for a local pool |
| `summon_draw_catalog.json` | Local hero draw costs, pools and duplicate rewards | Explicit local category weights, matching hero definitions and currency identifiers |
| `beginner_mission_catalog.json` | Hero-draw beginner milestones | Public mission IDs, required draw counts and supported asset/stackable rewards |
| `stamina_purchase_catalog.json` | Free-gem purchases of stored stamina | Matching public amount, price tiers, storage ceiling and type-9 daily limit |
| `challenge_mission_catalog.json` | Hero collection/draw and gold collection challenge steps | Public group IDs, supported conditions, increasing thresholds and asset rewards |
| `hero_knowledge_catalog.json` | Initial acquisition knowledge | Matching base-hero origins, public initial knowledge IDs and asset reward lists |
| `festival_shop_catalog.json` | Festival shop availability and simple point redemptions | Matching season, shop IDs, prices, limits, explicit ownership exclusions and typed rewards |
| `orbital_entry_catalog.json` | Experimental Orbital phase loading | Matching client identity and public floor IDs; no outcome or reward rules |
| `stamina_regen_catalog.json` | Natural stamina recharge | Matching client, base charged-stamina maximum and interval in minutes |
| `orbital_preset_catalog.json` | Creating/applying an unused Orbital slot | Matching client and mode slot count |
| `village_harvest_catalog.json` | Inn/facility gold and soul-point collection | Matching production/storage constants, building effects and follower bonuses |
| `basecamp_harvest_catalog.json` | Explicit mastery-reward debugging | Matching client, upgraded camp specs, minimum interval and fixed debug amount |

These `.bin` inputs are **response bodies**, not full TLS records, wire frames,
packet headers, APK files, or account responses. Missing files cause a controlled
unsupported-data failure when the corresponding route is requested. They are not
needed for the synthetic demo or the core persistence tests.

An external directory can override a built-in JSON template by filename. Keep
overrides local, compatible and free of official account state.

The optional `orbital_entry_catalog.json` contains `client` equal to
`{"version":"3.57.0","version_code":431,"region":"eu"}` and `floors`, a nonempty
list of distinct positive integer floor IDs from the matching `infinitytowerfloors`
table. The file is limited to 128 KiB and 10,000 IDs. The prepared experiment
extracted 1,501 IDs from its already imported static data. This additional catalog
is not included in the previously published 19-reference-file content pack.
Only synthetic subsets belong in tests; keep the prepared catalog external.

This catalog enables only a guarded phase-loading trial with preserved imported
party presets. The local eligibility policy permits configured floors through
the absolute saved floor plus one. The selected preset must contain one to four
distinct owned characters and owned equipment. Entry does not change the saved
floor, selected preset, currency or inventory. Combat results, attempts, rewards
and the separate formation-save route are not implemented by this trial.

The separate `/preset/set-selected-preset` mutation can select an existing saved
Orbital party without editing its definition. It requires no additional public
catalog: the native mode ID range and preserved private preset data provide its
scope. Only the saved selection pointer and account revision change; character
and equipment ownership checks are shared with the phase-loading trial.
`/preset/set-presets` can edit that existing Orbital party's name, members and
gear references. Current definitions are kept in SQLite separately from the
captured startup seed and are used by subsequent preserved reads and entry.
It requires no additional public catalog and does not modify owned inventory.

Creating a missing definition through `/preset/set-presets` additionally requires
`orbital_preset_catalog.json` with the same pinned `client` object and integer
`count` in `[1,100]`. The file is limited to 4 KiB. The inspected `PresetCount`
helper indexes `PresetCountS3` by mode minus one; the matching constants give
Orbital five slots, IDs `[400,405)`. The native list builds missing IDs within
that range and `CreateEmptyPartyPreset` assigns `Order=999`. A populated empty
slot can be saved and selected together by the Apply button.

The handler accepts that native empty order for a new ID and appends its saved
order after the highest existing Orbital order, preserving all other definitions.
That ordering is an explicit local policy; no official creation response was
captured. Creation uses the existing name/member/equipment validation and atomic
group/selection/receipt transaction. Retries use current state, even after delete
and recreation. Missing catalogs disable only new definitions, not existing edits
or known receipt replays. The prepared catalog stays external and is additional
to the previously published 19-reference-file pack.

The optional `stamina_regen_catalog.json` contains `client` with the same pinned
version/code/region object, `base_max` and `interval_minutes`. The prepared
3.57.0 constants supply `MaxStaminaDefault = 63` and `StaminaChargeInterval = 10`.
Native `Asset.GetMaximum` adds the saved charged asset's `MaxAdj` to that base.
Keep this derived catalog external; it is not included in the previously
published 19-reference-file pack. No account values belong in the catalog.
The handler uses only an existing saved `NextCharge` timer; it does not initialize
missing timers, purchase energy or transfer reserve stamina.

The optional `village_harvest_catalog.json` is limited to 2 MiB. It contains the
pinned `client`, `min_seconds`, `inn_factor`, `facility_divisor`, `sp_base_max`,
`rarity_bonus`, `match_bonus` and decimal-ID `buildings`/`followers` objects.
The [synthetic fixture builder](../tests/test_village_harvest.py) shows its shape.
Inn rows contain both rates/storage limits and the maximum manufacture level.
Producer rows contain specialization, follower slots and same-resource effects
with `item_id`, `value`, `period` and `storage`; other building rows explicitly
use `kind: "other"`. Follower rows contain rarity and specialization.

The prepared catalog derives from the matching `lobbyvillage`, `followers` and
`heavenholddata` tables: minimum 600 seconds, inn factor 45, facility divisor 10,
base soul-point capacity 0, rarity bonuses 5/10/15 and matching bonus 10 percent.
The saved asset's `MaxAdj` supplies the account's capacity. Keep all public
definitions external and account values out of this catalog; it is additional
to the older 19-reference-file pack.

Harvesting uses saved inn clocks and ready facilities' `EndTime`; it does not
initialize zero/future anchors. The explicit local policy credits up to free
capacity, consumes eligible clocks only for credited resources and discards
capped excess. Full resources retain their clocks. Only gold and soul points
are supported; mixed-resource facility effects and unfinished inns reject.
Airships, visitors, guardian-base-camp points, dispatches, shops and construction
require their own operations. Native arithmetic is evidence for the local
calculation, not a captured official reward contract.

`/lobby-village/harvest-basecamp` currently supports an explicit fixed mastery
reward for debugging. It requires a separate `basecamp_harvest_catalog.json`,
limited to 4 KiB, with exactly `client`, `portal_specs`, `min_seconds` and
`debug_mastery_points`. The client object is pinned as above; specs are a nonempty
list of distinct positive IDs, the interval is 1..86,400 seconds, and the reward
is a positive signed-32-bit amount. The prepared experiment uses the matching
upgraded portal spec, 60 seconds and **100,000,000 mastery points**, explicitly
requested by the owner. This catalog is not part of the published content pack.

The reward goes to the existing asset 70033. It requires a positive saved mastery
level and one configured camp in producing status, using that camp's `EndTime`.
Future/zero anchors are retained. Each eligible new request grants the fixed
amount and advances the clock; retries cannot grant it again. Normal guardian
points (70013), mastery/guardian levels, gold, tickets, parties and equipment
remain unchanged. Overflow rejects the whole reward. Without the explicit catalog,
the operation rejects; ordinary production/scoring, conversion, quick-harvest
tickets, party changes and mastery upgrades remain unfinished.

The attendance reader expects `origin_group`, `active_group`, and `groups`, where
each group maps to rows with `Day` and `Rewards`; a reward has `ItemId` and `Amount`.
`tests/fixtures/reference/attendance_catalog.json` illustrates that structure with
synthetic test rows. It is intentionally not a complete monthly catalog.

The optional training catalog contains `experience_by_level`, an increasing
integer array whose index 0 is level 1's zero experience, and `caps`, ordered
objects containing `opened_stage_id` and `max_level`. The first cap is the default;
later rows apply when their stage has its opened flag. Resolve build-specific
values before supplying this file. The synthetic fixture illustrates the schema
with test thresholds; it must not be used with an APK. Without this file, only
the original one-time knight tutorial is supported.

The optional tutorial catalog contains `ids`, a list of distinct nonnegative
integer tutorial IDs from the matching client's catalog. Built-in passive help
remains available without it. Other configured markers require Inn's saved
clear flag and only record UI completion; they do not run tutorial actions or
grant gameplay rewards. The test fixture is a synthetic subset.

The optional quest catalog contains `chapters`, mapping string chapter codes to
lists of distinct positive quest IDs. Registration currently requires an active
Inn session and preserves any existing quest state. It does not supply quest
scripts, implement later checkpoints/rewards or open linked stages. Without the
catalog, registration is limited to the original main quest 27.

The optional side-stage catalog contains `stages`, mapping string source stage
IDs to objects whose keys are map handles and whose values are target stage IDs.
Resolve these from matching client map objects and stage definitions, rather
than assuming a naming pattern. Discovery requires an active Inn session and
sets only the target's opened flag; it does not spend entry stamina, complete
the target or implement its gameplay. No targets are built into the source.

The optional story catalog contains `stages`, mapping string stage IDs to
`stamina` (a nonnegative integer), `requires_cleared` (stage IDs) and `quest_ids`.
Optional `requires_discovery: true` also requires the saved opened flag and
prevents automatic opening from clear prerequisites. It defaults to false.
Use only stages whose requirements have been reviewed. The prepared Chapter 1
catalog includes Inn, passage 110011001 (`passage_1_1`, 10 stamina) and main stage
100010002 (`easy_forest_1_2`, 15 stamina). The loaded world-map state identifies
the passage as the immediate destination after Inn. These two later story entries
require Inn's saved clear flag as a local rule; this does not reconstruct the
complete official route graph. The catalog also includes discovered side stage
110010005 (`substage_1_5`, 10 stamina, quest 57) with `requires_discovery: true`.
Its entry requires finding the map; adding its definition does not reveal it.
Adding a
catalog materializes earned openings in an existing save when the account store
opens, without resetting it. Clear events also refresh these openings.
Chapter-progress reads include an initialized progress entry for every configured
stage and every stage in the save's `StageStates`, including discovered side
stages without an entry definition. They preserve each stage's own progress.
With an entry catalog they also return the latest `UserProgress` to synchronize
the map. The chapter-read endpoint currently supports Chapter 1 only; keep this
catalog limited to that chapter.
Without this catalog, only the original Inn entry remains available. These data
do not implement the new stage's collectibles, battles, exits or rewards.

The optional monster catalog contains `stages`, mapping string stage IDs to
objects keyed by public monster handle. Each handle has exactly `index`,
`experience` and `gold`: an index from 1 through 254, unique within the stage,
and nonnegative integer rewards up to 1,000,000. Preserve the tilemap name-table
indices once a save contains progress; renumbering would change defeat receipts.
Inn retains its built-in handle definitions and provisional local rates.
Additional stages require an explicit catalog and a matching active session.
Only newly saved category-10 markers grant rewards; mixed batches, duplicate
handles, overlap and retries use one transaction with the balances.

The prepared catalog covers all nine named monsters in passage 110011001. It
reuses the existing **local** rule of 79 experience and 87 gold per new handle.
Those values come from the public level-1 experience table; applying them here
does not establish official monster levels, multipliers or server reward rates.
The catalog does not implement random drops, combat validation, respawn rewards
or stage completion. The repository includes only a synthetic test catalog.

The optional completion catalog contains `stages`, mapping string stage IDs to
`exit_name` and `required_monsters` (distinct category-10 indices, 1 through 254).
The prepared passage definition uses exit `easy_forest_1_2` and indices
`[2, 4, 5, 6, 7, 8, 9]`, matching the seven reported enemies on the observed path.
These encounter prerequisites are a local rule, not recovered server logic.
The first completion requires an active unlocked stage and all listed markers.
One transaction saves its clear flag, hit/no-damage telemetry, completion receipt
and earned catalog openings, then removes the active session. A retry preserves
any later active stage and does not spend resources or change quest progress.

Configured completion currently grants no extra items or grade gems and creates
no grade-claim receipt. The passage's public `Rewards` and `FailRewards` are null;
its separate grade reward has not been verified. Previously earned monster
rewards remain saved. Inn keeps its existing verified 50-gem claim behavior.

The optional summon-selection catalog contains a `characters` list. Each row has
distinct positive `Id` and `CharacterOriginId`, `SummonCategory: "Unique"`,
`SummonEventType: "Character"` and boolean `IsNew`. Optional `VersionFrom` and
`SelectableFrom` map service names to version/date strings. The prepared local
pool contains 122 playable Unique-category origin definitions from the client's
already-decoded hero cache, retaining those service fields. It is not a recovered
official promotion or probability table.

Entry and catalog reads derive the same checksum from these rows to refresh
cached data. `/summon/on-event` returns them in `SelectableCharacter`; promotion
state stays empty. Without the catalog, the empty fallback remains available.
`/summon/set-select-character` accepts exactly `RequestOriginIds`: zero through
five distinct known origins. An empty list clears the wishlist. It requires a
signed-in account with the prologue complete and saves only
`UserShop.SelectedSummonCharacters`/`UserShop.Cas`, returning `UserShop`. Identical
retries do not write another revision. Negative placeholders and unknown or
duplicate IDs are rejected before saving. No currency, inventory or hero is
granted or spent. Weapon selection remains pending. Hero draws use the separate
optional draw catalog described below.

The draw catalog's exact shape is shown by the [synthetic fixture](../tests/fixtures/summon_draw_catalog.json).
`heroes` maps origin IDs to native `rank` and `category` (`Normal`, `Story`,
`Unique`); `origin_by_spec` maps evolved spec IDs back to those origins.
`category_weights` and `duplicate_crystals` contain positive integers for all
three categories. `gem_costs` contains keys `1` and `10`. The remaining fields
identify ordinary/selectable tickets, hero crystals and mileage. No game catalog
or official probabilities are included in the repository.

The prepared pool contains 175 matching base definitions. Its **local** category
weights are Normal 75, Story 20 and Unique 5; heroes within a category are uniform,
and Unique results use the five saved wishlist origins. These are explicit local
testing rules, not verified official rates or guarantees. Public client constants
provide costs of 300/2,700 free gems and duplicate rewards of 1/8/50 hero crystals.
Ordinary controllers are item 110007, selectable controllers 110015, hero crystals
asset 70009 and mileage asset 70014. Supported cost types are 0 (free gems),
3 (ordinary controllers) and 5 (selectable controllers), for one or ten draws.
Controllers cost one per result; the local rule credits one mileage per result.

One transaction saves the payment, newly owned level-one heroes, duplicate
crystals, mileage, summon counter and frozen result receipt. A repeated request
in the same client epoch returns those results with the current player state;
it does not charge again or recreate heroes. Reconnect keeps the epoch; a fresh
login starts a new one. Identical stale deltas across a fresh login remain
ambiguous without an independent client operation ID. Pity, official promotions,
paid/discount/free-event currencies, weapon draws and general hero training remain
unfinished. The local draw route is `/summon/select-character`.

Imported accounts can use these same local hero draws and wishlist operations.
Each owned imported hero spec must have a known origin mapping before a new draw
can proceed; unknown forms reject without payment rather than risking a second
copy of an evolved hero. Existing hero progression/equipment and historical draw
counts are retained. Ticket payment removes only stacks depleted by that draw,
preserving other zero-amount stacks. Imported-account regressions also cover
reopening, reconnect receipts, legitimate new-session draws and rollback.

## Beginner reward batches

The optional `beginner_mission_catalog.json` extends the built-in Inn, initial
knight-training and stamina missions with hero-draw milestones. For example,
this is a **synthetic** row, not a game-content distribution:

```json
{
  "missions": {
    "5": {
      "summon_count": 7,
      "rewards": [{"item_id": 110007, "amount": 4, "storage": "stackable"}]
    }
  }
}
```

Mission keys must be canonical decimal IDs from 1 through 8191 and cannot
override built-in IDs 0, 1 or 9. `summon_count` is a positive threshold checked
against saved `UserRecord.SummonCharacterCount`. Rewards have positive integer
`item_id` and `amount`, with `storage` either `asset` or `stackable`. Asset rewards
must already exist in the account's asset list. Equipment and other reward kinds
are unsupported. Supply only verified matching definitions.

`/mission/claim-beginner-all` accepts a `missionIds` array with up to 512 entries.
It deduplicates IDs, validates every requested mission's eligibility and saved
receipt/claim bit, then saves all new rewards, receipts and flags in one SQLite
transaction. Shared stacks merge and unrelated profile state remains intact.
Already claimed IDs replay their frozen reward notices with current player state;
they do not replenish spent rewards. A mixed old/new batch grants only new IDs.
Unknown or incomplete missions reject the whole batch. Without the external
catalog, only the three built-in missions are supported.

The prepared private catalog has 11 hero-draw milestones from the matching
client's public mission data, with thresholds between 1 and 50. This covers one
mission type; other beginner conditions remain unfinished.

## Challenge reward steps

The optional `challenge_mission_catalog.json` contains a `groups` object keyed
by positive decimal group ID. Each group has a `condition` and ordered `steps`;
each step has an increasing positive `threshold` and a `rewards` list containing
positive `item_id`/`amount` pairs. List position determines step number, starting
at one. See the [synthetic fixture](../tests/fixtures/challenge_mission_catalog.json).
Only existing account asset rewards are supported.

Conditions currently supported are `owned_heroes`, which counts saved
`User.Characters` entries as the native mission helper does; `hero_draws`, which
reads saved `UserRecord.SummonCharacterCount`; and `collected_gold`, which adds
gold asset 70001's current `Amount` and lifetime `Spent`, capped at 2,147,483,647.
This matches native mission type 32, so spending gold does not remove collection
progress. Other condition types need their own evaluation rules. The prepared
catalog has 100 steps each for public groups 200, 202 and 206; the repository
does not embed those full game tables in the source tree. The separate content
release supplies the matching prepared catalog.

Both routes accept exactly `{"missionIds": [group_ids]}`. With the external
catalog, `/mission/claim-challenge-all` awards at most one new eligible step per
group; `/mission/claim-challenge-all-step` awards every consecutively earned
remaining step. IDs are deduplicated. An unknown group or a never-started group
with no completed step rejects the entire batch. Already claimed groups can
contribute no new reward. Saved claim markers must match contiguous per-step
receipts, including the old group-200 first-step receipt.

All new asset rewards, step markers, per-step receipts and a request receipt
commit in one transaction. A reconnect retry returns frozen reward notices with
current `User`/`UserMission`, without granting again or restoring spent rewards.
Changing the groups or next/all-step mode under an existing operation ID fails.
Fresh logins use a new epoch; the existing ambiguity around stale requests
across fresh logins also applies here. Receipted retries survive catalog removal.

Without the external catalog, the original first-knight/group-200 step-1
fallback remains available on the next-step route. It does not extend to later
steps or a larger roster. The all-step route requires an explicit catalog.

## Initial hero acquisition knowledge

`/collection/claim-hero-knowledge-all` accepts exactly `CharacterIds`: a list of
owned character **inventory IDs**, not hero spec/origin IDs. The external
`hero_knowledge_catalog.json` contains a `heroes` object keyed by base spec ID.
Each row has `origin_id` matching that key, a unique positive `knowledge_id`
ending in `01`, and a `rewards` list of positive `item_id`/`amount` pairs. Empty
reward lists are valid. See the [synthetic fixture](../tests/fixtures/hero_knowledge_catalog.json).

The supported condition is initial acquisition of a directly owned, untrained
base hero. Experience, rank upgrades, limit breaks and blessings must be zero,
and the awakening tree empty. Evolved forms and later rank, level, awakening,
ascension, blessing and myth objectives need additional rules. A request outside
that scope rejects the whole batch without marking those other objectives done.

The matching native sequence rule is `max(knowledge_id % 100 - 1, 0)`; supported
initial rows therefore use bit zero of the owned character's `Knowledge` value.
The batch checks inventory ownership and marker/receipt agreement, deduplicates
IDs and preserves other bits. Initial-knowledge IDs are unique across receipts
to prevent a duplicated origin from awarding acquisition twice.

One SQLite transaction commits acquisition flags, configured asset rewards,
per-hero receipts and a frozen request receipt. The response includes current
`User` and `AddedItems`, including an empty list when no currency is awarded.
Reconnect retries preserve notices without granting again; mixed old/new batches
grant only new acquisitions. Existing request receipts remain usable after
catalog removal or subsequent hero progression. Fresh-login request ambiguity
has the same limits as other epoch-based operations.

The prepared public catalog has 173 initial acquisition rows. Fifteen contain
60-gem rewards; the others have no asset reward. The observed 25-character
request contains only the latter. Initial knowledge can therefore be saved
without awarding gems. Book bonuses are evaluated by the client from its public
knowledge data and saved flags; server-side battle/stat validation is unfinished.

## Gem stamina purchases

`/user/charge-stamina-by-gem` requires an external
`stamina_purchase_catalog.json` with exactly four fields. The
[synthetic fixture](../tests/fixtures/stamina_purchase_catalog.json) illustrates
the shape: positive integer `amount_per_charge`, `max_storage` and `daily_limit`,
plus a nonempty `gem_prices` list of positive integers. These inputs are public
configuration, not account state.

The request is exactly `{"Count": positive_integer}`. Prices start at the saved
type-9 `User.StaminaGemChargeTicket.PlayCount`; a batch sums consecutive price
tiers and repeats the last price if the configured limit exceeds the price list.
The saved counter resets at the next UTC midnight. This matches this local
server's `StartOfDay` configuration; other service reset schedules are unsupported.

One transaction deducts free gems (asset 70003), increments their `Spent` total,
adds stored stamina (70032), advances the daily counter and saves an operation
receipt. The reply contains the current `User`; the native success consumer
constructs its reward notice from the requested count and public charge amount.
Other profile sections and stamina `Spent` remain unchanged.

Reconnect retries in the same request epoch reuse the receipt and current user
state. They do not recharge gems or restore stamina consumed after purchase.
The same receipt also remains stable after a daily reset or catalog removal.
A changed count under an existing operation ID is rejected. A fresh login starts
a new epoch; ambiguous stale requests across fresh logins have the same limitation
as existing draw/training receipts.

The prepared catalog provides 50 stored stamina per charge, a storage ceiling of
3,000 and 20 purchases per day. Prices are 100 for each of the first two charges,
then 200, 300 and 400 for successive pairs, followed by 500 for the remaining
charges. These values come from the matching client's constants and type-9
counter specification. The local handler rejects a batch that would exceed the
storage ceiling rather than truncating it. Exact official overflow behavior is
unverified. Paid gems, automatic stamina regeneration and counter upgrades are
outside this operation's scope.

## Festival shop availability and point redemption

The external `festival_shop_catalog.json` contains `season_id` and an `items`
object keyed by positive decimal shop IDs. Each item has `price`, `limit`,
`owned_misc_ids` and `rewards`; the [synthetic fixture](../tests/fixtures/festival_shop_catalog.json)
shows the shape. A zero limit means unlimited redemptions. Each reward has
positive `item_id`/`amount` and `storage` equal to `asset`, `stackable`, `misc` or
`unsupported`. Unsupported delivery types can remain in the availability catalog
but cannot be redeemed by this implementation.

`/festival-pass/check-not-redeemable` accepts no parameters (or an empty object)
and returns `{"NotRedeemable": [shop_ids]}`. The client loads these integers into
its shop exclusion set. The **local policy** excludes items whose saved purchase
count reaches their configured limit or whose configured persistent reward is
already present in `User.ItemMiscs`. Point affordability is a separate UI/payment
check. This query changes no profile, points, inventory or receipts. A completely
empty season-zero state can use the catalog for this read without initialization;
other season mismatches or unknown history fail rather than silently resetting.

The prepared season-41 catalog contains shop set 2's 42 items. Ownership rules
cover its 22 costumes, one portrait frame and two blueprints. Complete official server exclusion
rules, including other cosmetic subsystems, are unverified; these are explicit
local rules derived from matching public item types and the local inventory model.

`/festival-pass/redeem-point-rewards` accepts exactly `shopItemId` and `amount`,
where amount is the number of exchanges. One transaction spends
`price * amount` Festival points, updates `UserFestivalPass.Purchase`, grants the
multiplied rewards and records a request receipt. Asset rewards require an
existing asset; stackable rewards merge or receive a new inventory ID. Individual
`misc` rewards create one `User.ItemMiscs` row per unit with distinct inventory
IDs. A request can create at most 1,000 individual rows. The
response contains `User`, `UserFestivalPass` and `AddedItems`, as consumed by the
native purchase routine. Other asset spending counters are unchanged.

The prepared deliveries cover 40 of the 42 shop entries: costumes, portrait
frames, blueprints, merch, materials, hammers, tickets and supported assets.
Item 304 costs one point for three item-110009 relic-option change tickets.
Hammers use stackable storage, as observed in the matching inventory model.
Sticker packs (shop IDs 102 and 104) remain unsupported and reject without
point spending. Delivery support does not establish equip/use/upgrade behavior.
Missing data, ownership/limit
conflicts, insufficient points and overflow reject the entire purchase.

Reconnect retries return frozen reward notices with current player/pass state
without another charge or grant. Changing the request under a saved operation
ID fails; existing receipts survive catalog removal. Fresh-login stale-request
ambiguity has the same limits as other epoch-based mutating operations. The
catalog does not initialize, rotate or migrate a progressed season.

## Preservation manifest

Each resource root follows this layout:

```text
preservation-copy/
  manifest.json
  resources/
    files/
      AssetBundles/...
      static_data/...
      GameScript/...
      media/...
```

The resource server reads `manifest.json` two directories above `resources/files`:

```json
{
  "files": [
    {
      "path": "resources/files/media/example.jpg",
      "sha256": "a 64-character SHA-256 hex digest of that file"
    }
  ]
}
```

Paths are relative to the preservation-copy root and use `/`. Only manifest
entries under `resources/files/` that resolve inside the supplied resource root
and exist on disk are indexed. Keep account caches and preferences outside this
content set. The manifest is an allowlist; content hash verification is a separate
preservation task.

Supplements use their own manifests. Pass the base root first, then supplements;
the last matching entry wins. The server keeps the preserved files unchanged.

## Original-client content boundary

The prepared test used the base EN/ES content plus the Japanese voice supplement.
It did not prove every downloaded script, tilemap, language or media item was
complete. Missing resources remain missing; neither this backend nor the CDN
reconstructs or downloads them.
