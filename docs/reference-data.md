# External reference data and resources

For the matching preserved snapshot, follow the
[offline content download/import guide](offline-content.md). It supplies a
versioned Release pack and creates `local/client-data/reference` plus a CDN
resource root. This document describes individual input contracts and other
preservation layouts.

## Free local nickname changes

`/user/change-name` accepts exactly `{"Name":"NewName"}` after sign-in and
prologue completion. Nicknames retain the native 2..10 UTF-16-unit limit and
reject control characters and invalid Unicode. The local server applies no word
list, reserved-name rule, uniqueness check, cooldown or currency charge. Free and
paid gems, tickets and spending counters remain unchanged. This is a local policy,
not a reconstruction of official name-change pricing or moderation.

Only `User.Name` and its `Cas` change. An existing owned `GuildMember` receives
the same name and a revision increment when needed. These updates and an
epoch/sequence receipt commit together; delayed retries return the latest saved
name and cannot restore an earlier choice. Original imports, prologue selections,
captured startup reads, inventory and other account progress are retained.

The matching client checks paid gems before sending this request. The backend
therefore overlays only `constants.ChangeNickCost=0` over its effective static
data, after existing Raid, arena and Guild War overlays. It refreshes the record
revision, content digest and aggregate checksum; static get/check responses share
that checksum. Preserved bootstrap files stay unchanged.

The CDN serves an empty list for manifest-listed
`media/banwords/kakao_<locale>_name.txt` resources with a distinct ETag, refreshing
previously cached lists. The native parser removes empty lines. This client list
is shared by account and guild names; chat lists and other resources retain their
original content. Preserved files, manifests and their ETags are never overwritten.
No APK patch or Android data reset is needed. **After updating, fully close the
game, restart both backend and CDN, and reopen it; the bridge can remain running.**

## Colosseum lobby

The 3.57.0 client sends a Boolean `IsPartial` to `/colosseum/enter`. The server
returns the full lobby resource for both values. The client also reads the season
end time, new-season flag and defense battle records. When the imported profile
lacks a Colosseum resource, the local lobby uses the latest map-backed Global
season in the supplied `colosseum` table.

On opening the lobby the client can also call `/colosseum/get-opponents` and
`/colosseum/get-my-ranking` without parameters. The local responses contain the
configured opponent list and the player's saved `Ranking`. The Refresh button
calls `/colosseum/refresh-opponents` without parameters and returns that list
for free. Entry, list reads and manual refresh use the next local weekly reset
as the refresh time so the client can cache the list.

Colosseum attack teams use the shared `/preset/set-presets` and
`/preset/set-selected-preset` handlers. The matching `PresetCountS3[5]` defines
30 slots with IDs 600 through 629. A new team uses `Order=999` in the request
and is placed after the highest saved Colosseum order. Applying or selecting
the team stores its ID in `User.SelectedPresetId.ColosseumAttack`.

Ranking and Battle Record use parameterless reads and return empty local lists.
Season Stats accepts integer `SeasonId`, integer `Tier`, and Boolean `IsAttack`
and shows an empty list for each filter. The local lobby still shows the saved
personal trophy count and rank. Shop uses the shared empty local shop catalog.
Rewards displays the tier reward schedule supplied by the client data.

Open the Colosseum shield button to edit the practice defense. Saving the team
or its positions stores the defense in the local database. After saving, use
Refresh in the Colosseum lobby to load the updated team and positions in all
three opponent cards. Refresh reads the current defense, so later changes take
effect without restarting the backend.

Apply the team before arranging the defenders. The client's team Apply action
can copy the chosen preset's attack positions into the defense. Confirm the
manual positions in the defense formation popup after applying the team, then
refresh the opponent cards.

Position Settings saves the attacking layout separately for each Colosseum
preset using `/colosseum/save-formation`. During practice, the client uses the
attack preset's saved positions on the player's side and the refreshed defense
positions on the opponent's side.

The defense team takes precedence over the optional `colosseum_practice.json`
seed in the external reference directory. Its `preset_id` identifies a saved,
populated Colosseum attack team to use before the first defense save. The seed
starts at grid positions 12, 3, 19 and 9 in team order. With neither a seed nor
a saved defense, the selected attack team appears in the defense editor and
the opponent list is empty.

The client requires three cards, so each card uses the same defense with a
distinct local ID. The opponent receives the defense heroes and equipped
items, plus the player's current collection, Guardian level and mastery,
Heavenhold, and account buff options.

The practice start and result handlers accept the configured opponent and use
the client's native start and end request fields. The result grants zero trophies
and an empty reward list. The Colosseum requests require sign-in and a
completed prologue. Defense saves update the defense and its retry receipt
together. Practice battles leave the ticket balance intact.

## Backroom entry

`/my-room/enter` accepts exactly Boolean `IsPartial` after sign-in and prologue
completion. Both full and partial entry return native `UserMyRoom` and
`NewGetItems: []`. This is a read-only local default view: the imported account
did not include its separate room settings. No profile section, ownership record,
balance, progress flag, captured startup response or other SQLite row is changed.

The matching `items` table must contain exactly one free `Default` wallpaper and
one free `Default` music item of type `MyRoomMedia`. Their IDs populate `Used`;
only default music is selected. No fixed spec list or extra catalog is required,
and paid/limited media are not granted. Null `Hero` uses the client's current
representative character and costume; position offsets are zero and `Favorites`
is empty. `WallPaper=0` retains the bundled background rather than requesting
standalone wallpaper media absent from the prepared pack. The default music's
bundle is present in that pack.

The native resource has no account ID or revision fields. Entry omits `User` and
other profile resources, so it cannot replace the saved account with room defaults.
Repetition and reopening keep the same default view without database writes.
Room edits, media purchases, favorites and friendship/visitor rewards remain
separate unsupported operations. After updating, close the game and restart only
the backend; CDN and bridge can remain running.

## Training Room entry

`/training-room/enter` accepts no parameters after sign-in and prologue
completion. The native builder sends no body; null and an empty object are
accepted read aliases. The callback opens the scene, which uses the saved
`User.TrainingSlots` map. The response is a compact User resource containing
only `Id`, `Cas` and the complete current `TrainingSlots`.

Entry preserves slot IDs, character/item assignments, all native boost flags,
unknown saved fields and cooldown strings. Past cooldowns are not cleared,
future cooldowns are not advanced and empty slot maps remain empty. No slot is
created/unlocked or reactivated, no item/hero statistics are persisted and no
gems, inventory, profile revision or other account data change. No new catalog
is required for this read. Slot identity, assignment/flag types, saved revision
and explicit timestamp timezones are checked without repairing malformed state.
Placing/removing items or heroes, unlocking slots and paying to reactivate them
remain separate unsupported operations. After updating, close the game and restart
only the backend; CDN and bridge can remain running.

## Inventory item protection

`/item/lock` and `/item/unlock` accept exactly `itemIndexes`: a nonempty array
of 1..256 distinct positive Int32 **inventory IDs**, not item specification IDs.
The native 3.57.0 methods use these routes and this key; the prepared APK's
pending unlock request confirmed the single-item shape. The bounded batch size
and duplicate rejection are local validation policies.

Targets must be unambiguous owned rows in `User.ItemWeapons`, `ItemMiscs` or
`ItemStackables`, with a positive amount and an existing Boolean `Locked` flag.
All targets validate before writing. Only their top-level `Locked` flags and
one `User.Cas` increment change; currencies, quantities, equipment assignments,
levels, stats, engraving and nested option locks remain untouched. No extra
catalog is required. Protection is independent of option rerolls and retains
their pending proposals.

The current `User` response, saved profile and route/epoch/sequence receipt form
one transaction. An already matching batch records only a receipt; a replay
makes no writes and returns current state, preserving later locks, stat changes
or removals. Reordering the same batch retains its identity; changing its IDs
or switching lock/unlock under that identity rejects. Both fresh accounts after
the prologue and imported accounts use this path. Restart only the backend and
fully reopen the game after updating. Sales and equipment extraction use the
separate contracts below.

## No-gold batch item sales

`/item/sell` accepts exactly `SellItems`: a map of 1..256 canonical positive
decimal **inventory IDs** to positive Int32 quantities. Native `SendSellItems`
and an actual eight-item APK request confirm this map, not an array of item
specification IDs. The batch bound is a local validation policy. This explicit
local sale policy grants **no gold, other reward or mission credit** and needs
no extra price catalog; it does not reproduce official prices or eligibility.

Each row must exist unambiguously in `ItemWeapons`, `ItemMiscs` or
`ItemStackables`, have sufficient quantity and be unlocked. Equipment-costume
selections (`EquipCostumes`), current captured/edited party-preset references,
Training Room assignments and items with socketed jewels reject the entire
batch. Remove those protected uses first; teams, training slots and sockets
are not silently cleared. Every target is validated before any write.

Partial stacks retain their row and other fields. Depleted rows are removed;
unselected items and list order stay intact. When a row is fully removed, any
nullable character equipment field pointing to it is explicitly set to null.
Other gear, hero progress and assignments to partially retained stacks stay
unchanged. Only selected quantities/removals, these exact equipment references
and one `User.Cas` increment change. Inventory allocation counters, balances,
spending counters, collections and progression are preserved. Pending weapon or
relic option proposals are discarded only for fully removed item IDs, in the
same transaction as the profile and epoch/sequence receipt. Historical receipts
remain. Old sale retries return current `User` without another debit or an old
inventory snapshot; changing quantities under an existing identity rejects.
A delayed retry preserves equipment assigned after the original removal.

The response uses full current inventory arrays: the native `ParseItems` path
replaces each supplied list and retains missing fields. The success callback
reads no sale-specific response values, but builds its reward notice from a
price calculated locally before sending the request. That notice may still
display gold; the persisted balance is authoritative and receives zero.
This change does not rewrite client content or its displayed price. Restart
only the backend and reopen the game after updating. The distinct merchandise
sale route remains unsupported; equipment extraction has its own contract below.

## Equipment extraction without Magic Metal

`/item/extract` accepts exactly `ItemIds`: a nonempty array of 1..256 distinct
positive Int32 **equipment inventory IDs**. Native `SendExtractItems` and an
actual two-item APK request confirm this shape. Each ID removes one complete
owned equipment row; this is not the sale quantity map. The batch bound is a
local validation policy.

Extraction reuses the sale protection checks and transaction: locked,
equipment-costume selected, preset-referenced, Training Room assigned or
socketed items reject the whole batch before writing. Fully removed equipment
is cleared only from matching nullable character slots, just as in sales.
Targets must belong to `ItemWeapons`, have
amount one and rarity 4 in the existing matching
`weapon_enhance_debug_catalog.json`. This pins eligibility to the preserved
3.57.0 `ExtractableRarity`/`ExtractableMaxRarity` values, both 4. Missing,
malformed or mismatched catalogs disable new extraction, while existing receipt
replays remain available. Sales retain their catalog-free policy.

Only the selected rows, their matching character slots and one `User.Cas`
increment change. **No Magic Metal,
gold, other reward or mission credit is granted**, and all allocation/spending
counters are preserved. Pending weapon/relic proposals are removed only for
depleted targets. Profile, cleanup and `item_extract_requests` receipt commit
atomically; failures roll back the whole batch. Receipts use the canonical
sorted native `ItemIds` body, return current inventory on old retries and reject
reuse for another selection or for a sale. Existing sale receipts retain their
format and history, with no profile or receipt rewrite during initialization.

The response uses the same current `User` and full inventory lists as sales.
The native success popup can show locally predicted Magic Metal; its notice
does not establish a balance credit. Check the actual saved balance. No client
content or displayed reward is rewritten. With the existing matching equipment
catalog in place, only the backend needs restarting; no save/content reimport,
CDN restart or bridge restart is needed. The separate merchandise sale route
remains unfinished.

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
| `attendance_mock_catalog.json` | Explicit no-reward attendance for imported accounts | Matching client, group IDs and 28-day cycle; owner-selected debug policy |
| `training_catalog.json` | Knight experience targets and story caps | Parsed public experience catalog for the matching build |
| `imported_training_catalog.json` | Free leveling of owned imported heroes | Matching public experience thresholds, story caps, hero/myth variant IDs and level modifiers; explicit free-XP policy |
| `tutorial_catalog.json` | Known UI completion markers after Inn | Parsed public tutorial ID list for the matching build |
| `quest_catalog.json` | Known chapter quest registration in Inn | Parsed mapping of chapter codes to quest IDs |
| `substage_catalog.json` | Side-stage map discovery in Inn | Verified map handles and target stage IDs |
| `story_catalog.json` | Configured story openings and entry | Verified stamina, local clear prerequisites and stage quest IDs |
| `monster_catalog.json` | Defeated-monster reports in additional stages | Stable public handle indices and explicit local experience/gold rules |
| `completion_catalog.json` | Configured clear exits after Inn | Verified exit name and local required defeated-monster indices |
| `summon_selection_catalog.json` | Hero candidates and wishlist registration | Public hero origins and native selection-row fields for a local pool |
| `summon_draw_catalog.json` | Local draw costs/weights, hero pools and duplicate rewards | Shared local draw policy, matching hero definitions and currency identifiers |
| `beginner_mission_catalog.json` | Hero-draw beginner milestones | Public mission IDs, required draw counts and supported asset/stackable rewards |
| `stamina_purchase_catalog.json` | Free-gem purchases of stored stamina | Matching public amount, price tiers, storage ceiling and type-9 daily limit |
| `challenge_mission_catalog.json` | Hero collection/draw and gold collection challenge steps | Public group IDs, supported conditions, increasing thresholds and asset rewards |
| `imported_challenge_mission_catalog.json` | Dynamic imported-account achievements | Pinned client, available public challenge groups/steps, verified progress types and explicit reward storage |
| `hero_knowledge_catalog.json` | Initial acquisition knowledge | Matching base-hero origins, public initial knowledge IDs and asset reward lists |
| `imported_hero_knowledge_catalog.json` | Imported hero-book objectives | Pinned client, public spec origins/ranks, XP thresholds, awakening node indices and eight native objective types with gem rewards |
| `festival_shop_catalog.json` | Festival shop availability and simple point redemptions | Matching season, shop IDs, prices, limits, explicit ownership exclusions and typed rewards |
| `orbital_entry_catalog.json` | Experimental Orbital phase loading | Matching client identity and public floor IDs; no outcome or reward rules |
| `guild_meteor_entry_catalog.json` | Fresh guild meteor menu | Pinned client, explicit fresh-local policy and distinct positive season IDs with timezone-aware start dates |
| `orbital_completion_catalog.json` | Opt-in Orbital victory progress without rewards | Matching client and explicit Boolean no-reward policy; uses the separate entry floor catalog |
| `stamina_regen_catalog.json` | Natural stamina recharge | Matching client, base charged-stamina maximum and interval in minutes |
| `orbital_preset_catalog.json` | Creating/applying an unused Orbital slot | Matching client and mode slot count |
| `village_harvest_catalog.json` | Inn/facility gold and soul-point collection | Matching production/storage constants, building effects and follower bonuses |
| `village_gift_mock_catalog.json` | Princess gift acknowledgment without rewards | Matching client and explicit local cooldown; no reward pool is read |
| `village_obstacle_mock_catalog.json` | Regenerating obstacle acknowledgment without rewards/payment | Matching client and explicit regenerating obstacle specs/intervals |
| `weapon_enhance_debug_catalog.json` | Free equipment enhancement and rarity eligibility for no-reward extraction | Matching client, public experience/rarity tables and level coefficients; owner-selected free policy |
| `jewel_decompose_mock_catalog.json` | Jewel powder rewards without losing selected jewels | Matching client, explicit source-retention policy, public jewel spec grades and decomposition powder yields |
| `jewel_upgrade_mock_catalog.json` | Guaranteed jewel upgrades without currency costs | Matching client, explicit free/always-success policy, closed public evolution graph, nominal powder bounds, relic specs and regional socket count |
| `weapon_limit_break_mock_catalog.json` | Free equipment limit breaks using owned hammers | Matching client, eligible target origin rarities, hammer rarities and maximum count; explicit local mock |
| `weapon_option_mock_catalog.json` | Free option-value proposals and ordinary option lock/unlock | Matching client and public per-weapon option ranges; explicit local free policy |
| `relic_option_mock_catalog.json` | Free relic main/subgroup option proposals and apply/discard | Matching client and public per-source, per-slot option IDs/ranges; explicit uniform local rolls |
| `weapon_engrave_mock_catalog.json` | Free first engraving and validation of saved engraving | Matching eligible exclusive specs, origin/hammer rarities, option tiers, experience gate and level coefficient |
| `basecamp_harvest_catalog.json` | Explicit mastery-reward debugging | Matching client, upgraded camp specs, minimum interval and fixed debug amount |
| `guardian_mastery_catalog.json` | Single guardian mastery skill upgrades | Matching skill/class map, ordered next-level costs and upgraded camp specs |
| `guardian_mastery_reset_catalog.json` | Guardian mastery reset | Matching reset resource, cost and cooldown constants |

These `.bin` inputs are **response bodies**, not full TLS records, wire frames,
packet headers, APK files, or account responses. Missing files cause a controlled
unsupported-data failure when the corresponding route is requested. They are not
needed for the synthetic demo or the core persistence tests.

An external directory can override a built-in JSON template by filename. Keep
overrides local, compatible and free of official account state.

`/live-event/enter` needs no new external catalog: it reads current saved
`UserEvent` only. Existing matching static tables determine which event screens
and calendars the client offers. Entry does not initialize missing records or
implement their claims. See [temporal-event families and integration](live-events.md)
for the reviewed source tables, calendar scope and remaining per-family work.

Guild meteor entry uses `guild_meteor_entry_catalog.json`; the
[guild mode guide](guild-war.md) defines its schema and preserved-state boundary.
Guild War activation validates the matching external `guildwar`, `guildraid2`,
`seasondate` and `unlockfeature` records. It creates an immutable derived body,
adds one local no-reward feature-126 rule, and stores a reversible
`guild_war_selection.json`. Overlay policy 4 retains the zero cooperative
participation coin count and empties only the selected season's shop group,
preventing its absent currency spec from aborting result/shop UI rendering.
Other shop groups remain intact; selections without a policy or at policy 3
upgrade at bootstrap while retaining their valid period, phase and waiver.
An optional native `phase` from 1 to 4 controls the matching Coop/Multi lobby;
`guild-war enable --phase ...` persists that choice without account changes.
Omitted phase retains the choice, and legacy selections default to 1.
Optional `--skip-basic` waives only the War course
prerequisite in that response without recording stage clears. It layers above Raid/arena
preparation, retaining their files and source data. These experiment inputs and
selection files are not included in the original 19-reference-file content pack.

The optional `orbital_entry_catalog.json` contains `client` equal to
`{"version":"3.57.0","version_code":431,"region":"eu"}` and `floors`, a nonempty
list of distinct positive integer floor IDs from the matching `infinitytowerfloors`
table. The file is limited to 128 KiB and 10,000 IDs. The prepared experiment
extracted 1,501 IDs from its already imported static data. This additional catalog
is not included in the previously published 19-reference-file content pack.
Only synthetic subsets belong in tests; keep the prepared catalog external.

This catalog enables a guarded phase-loading trial with preserved imported
party presets. The local eligibility policy permits configured floors through
the absolute saved floor plus one. The selected preset must contain one to four
distinct owned characters and owned equipment. Entry does not change the saved
floor, selected preset, currency or inventory. Stage closing uses the separate
handler below. Attempt records, combat validation, rewards and formation saving
are outside this loading trial.

`/tower-infinity/end-stage` accepts exactly positive integer `floor`, Boolean
`isCleared` and `damages`, a list of 0..4 nonnegative signed-32-bit integers in
party order. It requires sign-in, a completed prologue and a configured floor no
higher than the absolute saved floor plus one. This includes earlier floors.
With `isCleared: false`, it returns `{}` and changes no saved table, profile,
floor, revision or resource. No attempt/damage record is reconstructed. The native
callback can exit while skipping absent `AddedItems`/`TowerInfinity` payloads.

Victories additionally require `orbital_completion_catalog.json`, limited to
4 KiB with exactly the matching `client` and Boolean `no_rewards: true`. The
explicit local policy accepts the authenticated client's clear report; it does
not validate the battle simulation. A clear higher than the absolute saved floor
stores that new highest floor positively and increments only `UserProgress.Cas`.
Earlier/equal clears retain the existing signed floor and revision. Other tower
fields, including legacy formation, remain intact. The progress revision must
be a nonnegative signed-64-bit integer; advancement at its ceiling rejects.

The victory response contains current `UserProgress` and top-level `TowerInfinity`
without reward keys. Assets, inventory, user revision, mission counters and every
other profile/village field stay unchanged. No reward is granted, queued or
claimed. Profile advancement and the canonical victory receipt commit atomically.
Old victory retries return current progress, preserving later floors even after
catalog/policy removal; changed parameters under the same operation ID reject.
New clears of older floors save a receipt without resetting progress or giving
rewards. These receipts use the existing session epoch/sequence identity and
its limits across new logins. Non-clear exits remain read-only and create no
completion receipt. The explicit policy file is additional to the content pack.
Actual APK victory behavior remains unverified; its constructed native request
and state boundaries are covered by automated/detached checks.

`/tower-infinity/save-formation` accepts exactly `Positions`, an ordered array of
four distinct integer deployment cells in `[1,20]`. These are party-slot grid
positions, not character inventory IDs or preset ordering. The pinned native
deployment UI keeps four positions even for a shorter party and numbers its
20 cells from one. No extra reference catalog or reward policy is needed.

After sign-in and a completed/imported account, one transaction changes only
`UserProgress.TowerInfinity.Formation.Positions`, one `UserProgress.Cas` when the
layout changes, and an `orbital_formation_requests` receipt. If the legacy
formation is absent/null, it creates `{Id:0,Positions:[...]}` as the native
fallback does. Existing formation IDs/metadata, signed floor, the separate
`Formations`/`SelectedParty`, presets, normal party, heroes, equipment, currencies
and every unrelated resource stay intact. New changes reject at the signed-64
revision ceiling; unchanged layouts can still record a receipt there.

Retries with the same session epoch/sequence and positions return current
`UserProgress` without writes, preserving later deployments and floor changes.
Conflicting payloads under the same identity reject. The native confirmation
callback copies its submitted positions locally after success; the response
also supplies the current progress resource/revision. Restarting the game reads
the saved layout normally. Changing positions spends nothing and authorizes no
clear/reward. Floor entry/exit and preset edits retain their separate guards.

The separate `/preset/set-selected-preset` mutation can select an existing saved
Orbital party without editing its definition. It requires no additional public
catalog: the native mode ID range and preserved private preset data provide its
scope. Only the saved selection pointer and account revision change; character
and equipment ownership checks are shared with the phase-loading trial.
`/preset/set-presets` can edit that existing Orbital party's name, members and
gear references. Current definitions are kept in SQLite separately from the
captured startup seed and are used by subsequent preserved reads and entry.
It requires no additional public catalog and does not modify owned inventory.

`/preset/delete-preset` accepts exactly integer `PresetId` for an existing,
unambiguous Orbital `[400,500)` or shared Raid/Conquest `[700,800)` definition.
No additional catalog or save import is required. It removes only that definition,
retains the order and data of every other team and increments `UserPartyPreset2.Cas`.
Deleting the selected team resets only its mode's pointer to zero and increments
`User.Cas`; choosing another team remains an explicit client action. Other mode
pointers, owned heroes, equipment, currencies and progress remain unchanged.
The current group, optional selection change and epoch/sequence receipt commit
together. Replays return current state, preserving later edits, selections and
explicitly recreated slots. Other preset modes remain outside deletion support.
After updating this backend behavior, close the game, restart the backend and
reopen the game; CDN and bridge can remain running.

`/preset/reorder-preset` uses the same handler for Orbital Lift (`PresetType=4`),
Raid/Conquest (`PresetType=7`) and Guild War (`PresetType=18`). Guild War shares
the existing `[700,730)` Raid slots and their order; it has no separate 1800-ID
definitions. Native `GetBasePresetId` returns 700 for type 18, and `PresetCount`
reads the Raid count, 30, instead of the zero at `PresetCountS3[17]`.
The native request contains exactly `PresetType` and `Order`: integer arrays of
5 entries for Orbital or 30 for Raid/Guild War. **The array contains positions,
not preset IDs**:
`Order[PresetId % 100]` gives the saved team's new zero-based position. Saved
teams must occupy distinct positions `0..N-1`; unsaved slots remain zero.
Unknown modes, invalid lengths/positions, ambiguous saved IDs and stale slot
references reject without writes. No additional catalog is required.

Only existing teams' `Order` fields and `UserPartyPreset2.Cas` change. Team IDs,
names, members, equipment, the physical definition-array order, other modes and
the complete account profile/selection map are preserved. The response contains
the full current `UserPartyPreset2`, retaining all other teams during the native
dictionary replacement. Order changes and an epoch/sequence receipt commit
together. Unchanged order records only a receipt; a repeated receipt makes no
writes and returns the latest group after later moves, deletion or recreation.
Selecting, editing and deleting teams continues to use their original IDs in
both modes. Fully close the game and restart the backend after this update;
CDN and bridge can remain running.

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

`/lobby-village/receive-gift` supports an explicit no-reward mock. Its external
`village_gift_mock_catalog.json`, limited to 4 KiB, contains exactly the pinned
`client` and positive integer `cooldown_seconds` in 1..31,536,000. The prepared
local cooldown is 21,600 seconds. This is a local debugging policy, not a verified
official gift interval; no official reward response was captured.

The parameterless request requires an owned preserved village. If its nullable
`NextGiftTime` is due, only that timer and `UserLobbyVillage.Cas` advance. A future
or null timer is retained. The response contains only the current village model;
`AddedItems` is omitted because the native success callback skips its reward
notice when that key is absent. No user profile, balance, inventory, account
revision, gift pool or original captured seed changes. The skipped gift is not
queued or delivered later. The village overlay and receipt commit atomically;
replays return the current village without postponing a later timer or overwriting
other village work. Catalog removal does not prevent receipt replay.

`/lobby-village/remove-obstacle` accepts exactly one positive integer `buildingId`.
Its explicit mock catalog `village_obstacle_mock_catalog.json` is limited to
64 KiB and contains exactly the pinned `client` and `regenerating_specs`, a map
of canonical positive decimal spec IDs to positive integer regeneration seconds
in 1..31,536,000. Include only matching `LobbyBuildings` rows of type `Obstacle`
with positive `RegenTime` and item rewards. The prepared catalog covers the
regenerating vending machine (spec 321002, 57,600 seconds). Permanent obstacles,
hero unlocks and normal building demolition are outside this mock.

The request must identify one owned configured obstacle in status 0 (available)
or 3 (regenerating). An available obstacle, or a completed regeneration, is
acknowledged by retaining the building/position and setting status 3 with its
next `EndTime`. Only those fields and the village revision change. A future
regeneration is retained. The response contains current `UserLobbyVillage`,
omitting `AddedItems` and `AddedCharacters` so the native reward branches are
skipped. No currency is charged and no reward is delivered or deferred: this is
an explicit local mock, not the official obstacle exchange. The entire user
profile stays unchanged. The village overlay and receipt commit together;
replays preserve later timers and other village actions, including after catalog
removal. A different building under an existing operation identity rejects.

`/item/enhance-weapon` requires a separate, explicit free debug catalog, limited
to 1 MiB. Its exact keys are `client`, `free`, `level_total_exps`, `weapons`,
`hammer_exp`, `limit_break_coef`, `max_limit_breaks` and `myth_coef`. The client
must match the pinned build and `free` must be Boolean true. The experience table
contains 1..1,000 strictly increasing positive signed-32-bit totals. Each spec
map contains 1..30,000 canonical positive decimal IDs: weapon values are rarities
0..5, and hammer values are positive signed-32-bit experience amounts. The maps
must be disjoint; coefficients and the maximum limit-break count are integers
0..100. The prepared catalog derives totals and hammer experience from the
matching default `weaponenhance.LevelExps`, using each public hammer's declared
level and rarity. Weapon rarities come from `items`; the matching limit-break
coefficient, maximum count and myth coefficient are 3, 5 and 20. This opt-in file
is additional to the published content pack.

The request has exactly `TargetWeaponId`, `SourceItems` and `discountBuff`.
The target is one owned equipment item; a locked target is supported. A saved
engraving matching the separate engraving catalog below is also supported.
`SourceItems` identifies 1..256 owned, unlocked hammer stacks and positive counts
within their saved quantities. Weapon sacrifice materials are unsupported. Each
hammer contributes its configured experience without being removed or consumed.
The explicit local cap policy uses saved `User.Unlocked.MaxLevel.Weapon`, plus
limit-break count times its coefficient, plus the myth coefficient for rarity
above 4, plus the engraving coefficient for a validated engraved target. Total
experience is clipped at that level's table threshold. It uses the preserved
saved cap rather than implementing the original stage-gated cap
calculation. Already capped targets reject new enhancements.

Only the target's `Experience` and user revision change. Gold, all materials,
options, account buffs, missions and all unrelated profile/village state remain
unchanged. `discountBuff` is validated but consumes no buff under this free
policy. The response contains current `User`. Profile and retry receipt commit
atomically; a replay returns current state, preserving later improvements even
after catalog removal. Different parameters under the same request identity
reject. A new operation can reuse the retained hammers until the cap is reached.
Evolution and weapon-sacrifice enhancement remain outside this handler. Hammer
limit breaks and first engraving use the separate mocks below.

## Source-preserving jewel decomposition

`/item/decompose-jewel` accepts exactly `Jewels`: a map of 1..256 canonical
positive inventory ID strings to positive Int32 quantities. Keys identify owned
stack rows, not public jewel spec IDs. Selected rows must be unambiguous across
the inventory, belong to `User.ItemStackables`, be unlocked, and hold at least
the requested quantity. Mixed grades are supported in one operation.

The external `jewel_decompose_mock_catalog.json` is required, limited to 1 MiB,
and has exactly:

- `client`: the matching pinned client identity.
- `preserve_sources`: Boolean `true`, explicitly selecting the local free policy.
- `powder_asset_id`: native jewel powder asset 70028.
- `jewels`: canonical public jewel spec IDs mapped to integer grades 1..100.
- `grade_yields`: canonical grade strings mapped to positive Int32 powder yields.
  Every configured jewel grade must have a yield.

Build the maps from matching `items` rows whose `Type` is `jewel` and
`inlaid.JewelGrade[].DecompositionDrop`. The prepared matching catalog contains
all 20 jewel specs/grades available in those tables. The handler looks up the
actual selected spec, rather than deriving eligibility or reward from an ID
range. Each quantity multiplies its grade's yield; the total selected quantity,
reward, resulting balance and User revision are checked for native overflow.

Only the existing powder asset's `Amount` and `User.Cas` change. Source stacks
keep their IDs, quantities, locks and metadata. Equipment sockets, gold, other
assets, spending counters and all other profile sections are retained. This mock
does not invent decomposition activity-counter credit. A new operation can reuse
the retained jewels and earn powder again.

The response contains current `User`. The matching native forge builds its
reward notice from the selected quantities and grade yields; it does not need
`AddedItems` from this route. Profile and canonical request receipt commit or
roll back together. Epoch/sequence retries return current User without granting
again, including after catalog removal or later source/reward edits. A changed
batch under an already-used identity rejects. New requests still require their
matching catalog, ownership, unlocked stock and sufficient saved quantities.

## Guaranteed free jewel upgrades

The two native routes are supported under a separate explicit local policy:

- `/item/upgrade-jewel`: exactly positive integer `JewelId` and `UseJewelPowder`.
  The jewel ID identifies one owned stack inventory row.
- `/item/upgrade-jewel-from-relic`: exactly positive integer `RelicId`, zero-based
  nonnegative integer `SlotIndex`, and positive integer `UseJewelPowder`.
  The relic ID identifies one owned unique relic row in `User.ItemMiscs`.

The required external `jewel_upgrade_mock_catalog.json` is limited to 1 MiB.
It has exactly `client`, `free: true`, `always_succeed: true`, `slot_count`,
`relic_ids` and `jewels`. The regional socket count is in 1..16. Public relic IDs
are distinct positive integers; `jewels` maps canonical public spec ID strings
to `{grade, group_id, evolve_to, powder_full}`. Grades are in 1..100; group IDs
are positive. Every nonzero evolution target must be present, in the same group,
and exactly one grade higher. A terminal spec has both evolution target and full
powder amount zero; other rows require a positive full powder amount.

Build the graph from matching `items` jewel rows (`Grade`, `GroupId`, `EvolveTo`),
the relic IDs from `Type: relic`, and nominal full powder amounts from
`inlaid.JewelGrade[].UpgradeNeeded`. The regional capacity is
`inlaid.constants.InlaidCount.KakaoGlobal`. The prepared catalog contains 20
jewel specs, 19 upgrade edges, 20 relic specs and one regional socket.

A new operation validates ownership, unambiguous inventory IDs, positive stock,
boolean saved lock state, the selected socket and the saved target spec. Locked
upgrade targets are retained. The selected nominal powder amount may be any
positive Int32 up to that grade's native full-success amount. The handler does
not charge it or gold, and returns Boolean `Succeeded: true` with current `User`.
It draws no success probability. Maximum-grade or empty/unknown socket targets
reject new operations.

A socket upgrade changes only the selected public jewel spec ID and User
revision. A loose upgrade promotes exactly one owned unit: decrease its old
stack by one and merge one unit into the next-grade stack, or allocate a new
inventory ID when absent. Total jewel quantity is conserved. Empty old rows
remain in the resource so the client can clear their old quantity. Existing
destination metadata is retained; a new stack inherits the source's lock.
Currencies, spending, other sockets, equipment references, relic options,
activity counters and all other profile sections remain unchanged.

Profile, any inventory-ID allocation and the route-bound canonical request
receipt commit or roll back together. An exact epoch/sequence retry returns
current User and the saved successful outcome without promoting again, even
after later upgrades, catalog removal or a maximum-grade result. A changed
route, target, slot or nominal powder amount under that identity rejects.

The original client still calculates and displays the normal percentage from
its slider, and can require nominal funds before sending the request. The local
server guarantees the submitted operation's result and retains currency; this
policy does not modify the APK's preview or its client-side funds checks.

## Free equipment limit breaks

`/item/limitbreak-weapon/v2` also accepts exactly `TargetWeaponId`, `SourceItems`
and Boolean `discountBuff`, but uses `weapon_limit_break_mock_catalog.json`.
The catalog is limited to 1 MiB and has exactly `client`, `free`, `weapons`,
`hammers` and `max_limit_breaks`. It requires the matching pinned client,
Boolean `free: true`, a maximum count in 1..100, and disjoint canonical positive
decimal spec maps. `weapons` contains 1..30,000 eligible spec IDs mapped to origin
rarity 3 or 4; `hammers` contains 1..64 limit-break hammer specs mapped to rarity
3 or 4. The prepared catalog uses matching public weapons with current rarity
4 or 5 and origin rarity 3 or 4, both public `limitbreakhammer` specs and the
matching maximum count of 5. It is additional to the published content pack.

A new request must identify one owned, unengraved target below that maximum,
and 1..256 unlocked owned hammer stacks with positive counts within their saved
quantities. A locked target is supported. Each hammer's rarity must equal the
target's **origin rarity**, including evolved/myth weapons. Each selected hammer
adds one limit break, clipped at the configured maximum. No hammer, gold or
account buff is consumed. Only target `LimitBreaks` and user revision change;
experience, item options, mission counters, all other inventory and village state
are retained. This is an explicit free local mock, not the official exchange.
Sacrificing duplicate weapons and engraved targets are outside its scope.

Profile and canonical retry receipt commit atomically. The response contains
current `User`; old replays retain later experience/breaks and require neither
the original hammers nor catalog to remain present. A changed body under the same
operation identity rejects. A new operation can reuse retained hammers until the
maximum, where new requests reject without writes.

`/item/change-options` accepts exactly a positive integer `ItemId`, identifying
the owned inventory instance, and returns current `User` plus `NewOptions` pairs
containing `OptionId` and `Level`. Its opt-in `weapon_option_mock_catalog.json`
contains exactly matching `client`, Boolean `free: true` and `weapons`. The file
is limited to 1 MiB. `weapons` maps 1..30,000 canonical positive decimal spec IDs
to 1..32 canonical option IDs, each with `[minimum, maximum]` integer levels in
0..1,000. The prepared catalog derives those ranges from matching public
`items.Options` rows and is additional to the published content pack.

This is a local **option-value mock**: it preserves each existing option ID,
count, order, lock flag and source, rolling only unlocked levels uniformly within
their configured inclusive ranges. It does not reproduce official probabilities
or add/remove optional attributes. The target must be owned equipment
with distinct supported ordinary (`OptionSource: 0`) options in range and at least
one unlocked option. Locked equipment itself is supported. Existing option locks
are retained; creating/removing locks uses the separate free operation below.
Saved engraving matching the separate engraving catalog is validated and retained.
No option stones, lock stones, other inventory or currency are consumed or required
by this server policy. Client UI resource checks are outside this handler.

Generating a proposal leaves the entire profile and user revision unchanged.
The latest proposal for each item is stored separately with its original option
set and validated range data. `/item/apply-options` accepts exactly `ItemId`
and Boolean `Apply`: true applies the latest proposal and increments user revision;
false discards it without changing the profile. Both return current `User`.
Experience, limit breaks, buffs, missions and all other fields are retained.
The saved spec and original options must still match when resolving a proposal;
later experience/limit-break changes are retained. Persisted range checks remain
available if the external catalog is removed.

Proposal replacement/resolution and canonical receipts commit atomically. Old
change retries display the latest pending proposal, or current applied options,
without drawing again or restoring an old proposal. Old apply/discard retries
return current profile without consuming a newer proposal. A changed body or
route under one request identity rejects. The wire carries no proposal ID:
new apply/discard requests resolve the latest pending proposal for that item.
Session-epoch retry limits across new logins remain the same as other mutations.

`/item/change-lock-options` accepts exactly positive integer `ItemId`, a list
`OptionIds` of 1..32 distinct positive integer option IDs and Boolean `DoLock`.
It shares the explicit matching `weapon_option_mock_catalog.json` free policy.
The item must be owned equipment with supported ordinary options matching its
public ranges; every requested ID must already be present. Known saved engraving
is validated and retained. True locks only the selected IDs; false unlocks only
those IDs. Existing option values, identities, order, metadata and other locks
are preserved. The response contains current `User`.

A real flag change increments user revision once and discards only that item's
unapplied option-value proposal, so a stale proposal cannot overwrite the new
locks. Other items' pending proposals remain intact. A new request already in
the desired state saves its receipt without rewriting the profile, incrementing
revision or discarding pending work. No lock stones, option stones, other
materials, currency, buffs or mission credit are consumed or required by this
server policy. It does not enforce the original service's payment/quota rules.
Client UI resource checks are outside this handler.

Profile changes, same-item pending-proposal removal and canonical retry receipt
commit atomically. Option ID order is insignificant; changed IDs, target or
direction under the same identity reject. Old retries return current `User`
without reinstating a lock after a later unlock or undoing subsequent option
values, including after catalog removal. Later value rolls preserve the newly
locked values; all-locked equipment requires an unlock before a new roll.

`/item/engrave-weapon` accepts exactly positive integer `TargetWeaponId` and
`MaterialWeaponId`, identifying different owned inventory instances. The opt-in
`weapon_engrave_mock_catalog.json` is limited to 1 MiB, with exactly matching
`client`, Boolean `free: true`, `min_experience`, `required_limit_breaks`,
`engrave_coef`, `max_ceiling`, `weapons` and `hammers`. The experience gate is a
positive signed-32-bit value, required breaks and maximum ceiling are in 1..100,
and the coefficient is in 0..100. The disjoint canonical spec maps contain
1..30,000 weapons and 1..64 hammers. Each weapon has exactly `origin_rarity`
(3 or 4) and `options`, 1..32 distinct positive `OptionId`/`Level` pairs sharing
one option ID, with levels in 1..1,000. Hammer values are rarity 3 or 4.

The prepared catalog uses matching exclusive weapons with rarity at least 4,
origin rarity 3 or 4 and nonempty public static/random engraving options. It
derives the minimum experience from `WeaponLevelToExp`'s public threshold for
the configured engraving requirement: 1,462,850 experience. Required limit breaks
are 5, the added level coefficient is 15, and the configured ceiling is 5. This
optional catalog is additional to the published content pack.

This handler supports **first engraving only**: the owned target must meet the
experience gate, have exactly the required limit breaks, no engraving options
and zero engraving ceiling. A locked target is supported. The material must be
one unlocked, nonempty owned limit-break hammer stack whose rarity matches the
target's origin rarity. Duplicate-weapon sacrifice is unsupported. The local
mock chooses one public random-option tier uniformly, stores one `EngraveOptions`
pair, sets `EngraveCeiling` to 1 and increments user revision. This uniform roll
and initial counter are explicit local policy, not verified official response
behavior or rates. The native client derives fixed engraving options from its
matching weapon spec. The response contains current `User`, omitting returned
`AddedItems`; no refund/reward is fabricated.

No hammer or gold is consumed. Experience, limit breaks, ordinary options,
inventory quantities, buffs, missions, village and all unrelated fields remain
unchanged. Profile and canonical receipt commit together. Old retries return
current state without rolling or overwriting later work, including after catalog
or material removal; changed parameters under the same identity reject. New
first-engraving requests on an already engraved target reject. Engraving rerolls,
their apply/discard routes and repeated ceiling progression remain unsupported.

Subsequent ordinary option changes validate and preserve the saved engraving.
Subsequent experience enhancement includes its configured level coefficient.
These operations require the matching engraving catalog for a saved engraved
target, accepting one public tier with ceiling in 1..`max_ceiling`. Malformed or
unknown engraving data rejects before writes; unengraved accounts need no new
catalog for the existing operations.

`/item/change-relic-options/v2` accepts exactly positive inventory-instance
`ItemId` and integer `OptionType` 1 (main/base) or 2 (secondary/change). The
response contains current `User` plus `NewRelicOptions`, with `OptionId`, `Level`
and `OptionSource` for every proposed row. `/item/apply-relic-options` accepts
exactly `ItemId` and Boolean `Apply`: true accepts the latest proposal, false
discards it. Both return current `User`.

The opt-in `relic_option_mock_catalog.json` is limited to 1 MiB and has exactly
matching `client`, Boolean `free: true` and `relics`. This map contains 1..4,096
canonical positive decimal spec IDs. Each relic has exactly source keys `1` and
`2`, each holding 0..16 slot pools, with at least one slot overall. A pool maps
1..256 canonical positive option IDs to `[minimum, maximum]` integer levels in
0..1,000,000. The prepared catalog derives those ordered pools from matching
public `items.BaseOptions` and `items.ChangeOptions`, omitting unused empty public
slots. It is additional to the published content pack.

The target must be an owned single relic in `User.ItemMiscs` with valid
`RelicOptions` and a configured spec. Locked relics are supported. Saved rows
retain their order and must match each source's slot count and public pools;
**repeated option IDs in different slots are valid**. The selected group requires
at least one unlocked slot. Each unlocked selected slot chooses an allowed
option ID uniformly, then an integer level uniformly within that ID's inclusive
range. The ID and value can both change; the same result can also repeat. A slot
with only one allowed ID varies only its level. These are explicit local uniform
rolls, not reconstructed official presence/value probabilities. Locked rows and
the entire unselected group are retained. Set effects and jewel mutation are
outside these routes.

Generation stores a separate proposal with original options/spec and validated
slot pools, leaving the entire profile/revision unchanged. Acceptance replaces
only `RelicOptions` with the validated selected-group result and increments user
revision; discard leaves the profile unchanged. No currency, relic tickets,
materials or other item quantities are consumed or required by the server's
free policy. Existing jewel slots, unrelated equipment/progress and all other
fields are retained. Client UI resource checks remain outside this handler.

Proposal replacement/resolution and canonical receipts commit atomically. Old
generation retries return the latest pending proposal or current applied options
without drawing or resurrecting old work. Old acceptance/discard retries retain
newer pending work and current state. A changed body/route under one identity
rejects. Resolution validates the original spec/options and persisted slot pools,
including after external catalog removal, while retaining later jewel-slot or
unrelated item changes. New resolutions target the item's latest pending
proposal; the native apply body has no proposal ID/type. Session-epoch retry
limitations across new logins still apply.

`/lobby-village/harvest-basecamp` currently supports an explicit fixed mastery
reward for debugging. It requires a separate `basecamp_harvest_catalog.json`,
limited to 4 KiB, with exactly `client`, `portal_specs`, `min_seconds` and
`debug_mastery_points`. The client object is pinned as above; specs are a nonempty
list of distinct positive IDs, the interval is 1..86,400 seconds, and the reward
is a positive signed-32-bit amount. The prepared experiment uses the matching
upgraded portal spec, 60 seconds and **100,000,000 mastery points**, explicitly
requested by the owner. This catalog is not part of the published content pack.

The reward goes to the existing asset 70033. It requires a nonnegative saved mastery
level and one configured camp in producing status, using that camp's `EndTime`.
Zero allocated skill levels remain valid after a mastery reset; the upgraded
camp specification supplies the activation boundary.
Future/zero anchors are retained. Each eligible new request grants the fixed
amount and advances the clock; retries cannot grant it again. Normal guardian
points (70013), mastery/guardian levels, gold, tickets, parties and equipment
remain unchanged. Overflow rejects the whole reward. Without the explicit catalog,
the operation rejects; ordinary production/scoring, conversion, quick-harvest
tickets and party changes remain unfinished. Skill upgrades use their own catalog.

`/user/guardian-mastery-level-up` accepts exactly one integer `SkillId`. Its
external `guardian_mastery_catalog.json` is limited to 64 KiB and contains exactly
`client`, `portal_specs`, `skills` and `level_costs`. The client is pinned as above;
portal specs are distinct positive IDs for upgraded camps. `skills` maps canonical
positive decimal skill IDs to integer class IDs 1..4, with all four classes
present. `level_costs` is a nonempty list of positive signed-32-bit costs, indexed
by the selected skill's current level: index zero buys level one. Derive these
from the matching `guardianlevel` table's `GuardianSkill` (`SkillId`,
`SkillCategoryId`) and ordered `GuardianSkillLevel` (`SkillLevel`, `LevelUpExp`)
rows. Keep the extracted data external; it is not in the published content pack.

The prepared catalog contains 16 skills and 64 levels. The lowest sum of skill
levels among the four classes controls the next ten-level class cap; the native
maximum is the largest class's skill count times the individual level count.
The selected skill also has its own maximum. The saved skill map and total must
agree. An owned producing upgraded camp is the local activation gate. A single
transaction spends mastery asset 70033, adds the cost to its signed `Spent`
counter, increments the selected skill, synchronizes the total and increments
the account revision. Historical spending treatment is a local policy; the
official response was not captured. Retries return current user state without
another debit.

`/user/reset-guardian-mastery-level` accepts no parameters or an empty object.
It uses the same mastery catalog plus `guardian_mastery_reset_catalog.json`,
limited to 4 KiB, containing exactly `client`, `resource_id`, `cost` and
`cooldown_seconds`. Match the pinned client; `resource_id` must be integer 70003,
`cost` a positive signed-32-bit integer, and cooldown an integer in 1..31,536,000.
Extract `SkillResetResource`, `SkillResetCost` and `SkillResetCoolTime` from the
matching guardian constants. The prepared values are 70003, 300 and 86,400.
The client checks total gems; this local implementation charges free gems only
and rejects insufficient free gems without falling back to paid gems.

Reset requires the same upgraded camp and consistent skill map, with at least one
allocated level and at least one skill below its maximum. A nullable
`SkillNextResetTime` gates requests using the native whole-second comparison;
equality is eligible. The new time is current server time plus the configured
cooldown, serialized in UTC. The **local refund policy** returns the sum of all
configured level costs invested in the current skill map, clears the map and
sets total mastery to zero. It adds that refund to asset 70033 and subtracts the
same amount from its signed `Spent` counter, preserving any historical offset.
It spends the configured gem cost and increments gem spending and user revision.
All changes and the receipt commit together. No official reset response was
captured, so the refund/counter policy is not claimed as a verified official
contract. Overflow, malformed state or active cooldown reject without writes.
The response carries current `User`; replay cannot repeat payment/refund or
erase newer skills. An older upgrade replay cannot restore reset skills. Catalogs
are unnecessary for an existing receipt. Ordinary camp production remains outside
these operations.

The fresh-account attendance reader expects `origin_group`, `active_group`, and `groups`, where
each group maps to rows with `Day` and `Rewards`; a reward has `ItemId` and `Amount`.
`tests/fixtures/reference/attendance_catalog.json` illustrates that structure with
synthetic test rows. It is intentionally not a complete monthly catalog.

Imported accounts instead require an explicit `attendance_mock_catalog.json` to
skip an eligible daily reward. The file is limited to 4 KiB and contains exactly
`client`, `origin_group`, `active_group` and `days`. Match the pinned client and
its monthly group constants; positive group IDs must fit the encoded signed-32-bit
counter. `days` must be integer 28. The prepared experiment uses origin group 1
and active group 3. This is an opt-in debug policy requested by the owner; without
the catalog an eligible imported claim rejects before changing state.

The parameterless `/user/claim-daily-attendance` response contains current `User`,
current `UserRecord` and `AddedItems: []`. The mock never loads reward rows or
interprets item types. It advances the calendar count/date, login-day record and
both model revisions once per UTC day. Existing assets, inventory and item counters
remain unchanged. A completed 28-day cycle restarts at day one of the active group;
this rollover is a local policy. A same-day official capture or existing daily
receipt is already claimed. Future/malformed dates, invalid counters/ownership
and revision overflow reject without writes.

The calendar changes, daily fence and request receipt commit together. A reconnect
replay returns current state without advancing again, even on a later day or after
catalog removal. A different request on an already claimed day also leaves the
profile unchanged. A skipped reward is not deferred or placed in an inbox: that
local day's reward is deliberately omitted. Fresh-account asset rewards retain
their existing implementation; this mock does not add inventory/random rewards.

The optional training catalog contains `experience_by_level`, an increasing
integer array whose index 0 is level 1's zero experience, and `caps`, ordered
objects containing `opened_stage_id` and `max_level`. The first cap is the default;
later rows apply when their stage has its opened flag. Resolve build-specific
values before supplying this file. The synthetic fixture illustrates the schema
with test thresholds; it must not be used with an APK. Without this file, only
the original one-time knight tutorial is supported for fresh accounts.

Imported accounts instead require `imported_training_catalog.json`. This explicit
local policy includes `client` (the pinned version/code/region),
`free_experience: true`, `experience_by_level`, `caps`, `character_ids`, `myth_ids`,
`limit_break_coefficient`, `blessing_coefficient`, `myth_coefficient`,
`max_limit_breaks` and `max_bless_level`. Thresholds are `[0]` followed by public
`exps2.LevelExps[].TotalExps`; caps retain the ordered public story rows. For this
policy, a native internal level N uses threshold index N (displayed level N+1).
The limit is the opened-story cap plus saved breaks times their coefficient,
saved blessings times their coefficient and the myth coefficient for a myth
variant. Resolve IDs and modifiers from matching public client data, never a
player's current level. The observed build has coefficients 3, 5 and 20, maximum
five breaks and three blessings. Myth variant IDs are public character specs
whose rank is at least the public `MythCharacterRank` constant (six); hero IDs
come from the public hero-spec index. `MythStoneCharacterMap` identifies eligible
pre-myth heroes and must not be used as the list of already-mythic variants.
These game tables remain external.

Positive XP deltas may stop between thresholds but cannot exceed the computed
cap. The handler changes only requested heroes' experience, `User.Cas`, the
record of total experience applied and `UserRecord.Cas`. Every asset, including
shared experience amount/spending, remains unchanged; an empty XP balance is
valid. One transaction saves targets and an epoch/sequence receipt. Reconnect
replays return current resources without training again. The same delta with a
new request identity is a new operation. A full fresh client launch has a new
epoch and cannot identify an old request solely from an ambiguous XP delta.
Missing policy, unknown/unowned heroes, invalid state, cap/record overflow or a
failed batch rejects without profile or receipt changes. The older paid knight
training and its receipts remain separate.

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
granted or spent. Weapon wishlist candidates and registration follow below.
Hero draws use the separate optional draw catalog described below.

Weapon candidates for `/summon/on-event` are derived from the matching external
`static_data_get.bin`, using the same eligible non-limited base rank-4 definitions
as local weapon draws. No additional selection catalog or fixed ID list is
required. Local native rows contain stable design IDs in both `Id` and `ItemId`,
`SummonEventType=Weapon`, `IsNew=false` and **`SummonCategory=Exclusive`**. Weapons
use the native `ItemSummonCategory` enum, which differs from the hero category
enum. A hero category label in this field can abort catalog population and block
startup media preparation. Contract regressions verify the weapon enum and retain
the remaining media/event list fields.

When weapon data is available, `/summon/enter` and `/summon/on-event` share a
checksum covering both hero and weapon candidates. Changes to either list refresh
the client cache. Hero-only installations retain their existing checksum behavior;
valid weapon candidates can also be served without the optional hero selection
file. Catalog reads do not write account state or enable events.

`/summon/set-select-weapon` accepts exactly `RequestItemIds`: zero to five distinct
positive Int32 **design IDs** from those candidates, preserving their order. Owned
inventory row IDs and hero origins do not identify wishlist weapons. Selection
does not require owning the requested weapon. Partial lists and an empty clear
are supported; a subsequent wishlist draw still requires five valid entries.
Only `UserShop.SelectedSummonWeapons` and its `Cas` change, returning `UserShop` as
for hero selection. An unchanged list writes nothing, including at the maximum
revision. Invalid requests, shop ownership/revision, duplicate choices or failed
storage retain the previous state. Existing positive stale choices may be replaced
with eligible designs. No currency, inventory, hero, event counter or draw receipt
is granted, spent or reset; existing saves need no migration or reimport.

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
event currencies and general hero training remain unfinished. Regular paid-gem
banners are described below. The local wishlist hero route is
`/summon/select-character`; weapon draws follow below.

Imported accounts can use these same local hero draws and wishlist operations.
Each owned imported hero spec must have a known origin mapping before a new draw
can proceed; unknown forms reject without payment rather than risking a second
copy of an evolved hero. Existing hero progression/equipment and historical draw
counts are retained. Ticket payment removes only stacks depleted by that draw,
preserving other zero-amount stacks. Imported-account regressions also cover
reopening, reconnect receipts, legitimate new-session draws and rollback.

## Local weapon draws

`/summon/select-weapon` accepts exactly `Count` (1 or 10) and `SummonCostType`
(0 free gems, 3 ordinary controllers or 5 selectable controllers), matching the
hero draw's authenticated request/epoch/sequence flow. It reuses costs, ticket
identifiers, mileage and explicit local `category_weights` from
`summon_draw_catalog.json`; no additional draw catalog is required.

Weapon definitions, initial level/experience and magic-metal rewards come from
`items`, `constants` and `weaponenhance` in the matching external
`static_data_get.bin`. Eligible base weapons have `Summonable=true`,
`Limited=false` and equal `Rarity`/`OriginRarity`; evolved forms, limited items
and mythic rank 5 are excluded. The local Normal pool contains ranks 0/1, Story
contains ranks 2/3 and Unique uses exactly the five distinct eligible rank-4
designs saved in `UserShop.SelectedSummonWeapons`. Those category names and the
prepared 75/20/5 weights are reused local testing rules; they do not establish
official weapon probabilities. Members of each pool are uniform.

Each result grants a separate inventory weapon, including repeated designs;
weapons are not converted into hero crystals. New rows use the shared inventory
defaults. The prepared constants give native level index 19 (displayed level 20),
17,350 initial experience and ten magic metal per weapon. The existing local
mileage rule grants one per result. One/ten gem costs are 300/2,700; supported
controllers cost one per weapon and only stacks depleted by payment are removed.
Insufficient balances, ambiguous inventory IDs, exhausted allocators/revisions,
missing/invalid definitions or an invalid five-weapon wishlist reject before
rolling or saving.

Payment, appended weapons, allocator, metal/mileage, historical weapon-draw count,
user/record revisions and a frozen result receipt commit atomically. Replies use
the same current User/UserShop/UserRecord plus `Summons` envelope as hero draws,
with native result `Type=0`. Reconnect retains the request epoch. Exact retries
return the frozen results with current state, including after catalog removal or
later weapon edits; they do not pay again, recreate consumed weapons or roll
again. A conflicting body under one identity rejects. Existing saves initialize
the receipt table without reimport. Existing gear/options/engraving, heroes,
wishlists, other progress and captured startup reads are preserved.

Wishlist paid-gem modes, free-event draws, official pity/promotions and official
option-generation probabilities remain outside this draw route.
Regular paid-gem banners are described below.
The prepared APK has verified a ten-gem draw and single selectable-controller
draws, with weapons retained after reopening; ordinary-controller payment has
automated coverage.

## Regular banners and paid gems

`/summon/character` and `/summon/weapon` accept exactly `IsPickUp`, `PickUpKey`,
`Count` and `SummonCostType`. The bounded local regular-banner contract requires
`IsPickUp=false` and integer `PickUpKey=0`. These routes use all eligible local
Unique candidates instead of the five wishlist entries; empty wishlists remain
unchanged. They reuse the existing hero/weapon generation, rewards and atomic
receipt flow. Pickup/event banners remain unsupported.

Both draw families share the payment handler. Native cost type 1 is the daily
discount: one result, paid exclusively from asset 70002 at the matching
`GemsForSummonDiscount` price (100). The character and weapon limits are separate.
The operation updates only its `UserShop.LastDiscountSummonCharacter["0"]` or
`LastDiscountSummonWeapon["0"]` timestamp and increments `UserShop.Cas`, atomically
with payment, inventory/rewards and the frozen receipt. Other banner timestamps,
wishlists, event counters and the unrelated currency remain intact.

The local API advertises UTC server time and `StartOfDay=00:00:00`; the native
`ContentToday` predicate therefore resets the limit at UTC midnight. Saved offset
timestamps are converted to UTC before comparison. A second new request or fresh
login cannot bypass the persisted daily limit. An exact retry returns its saved
results/current state without another debit or timestamp/revision change.

Native cost type 4 pays full price from asset 70002, using `GemsForSummon` for one
result and `PaidGemforSummonTen` for ten (300/2,700 in the prepared data), without
using the daily discount. Insufficient paid gems never fall back to free gems or
controllers. Ordinary free-gem type 0 and ordinary-controller type 3 also work on
regular banners with the existing local rules. Selectable controllers and paid
modes on wishlist routes, free-event type 2, active discount packages, pickup
keys and promotional guarantees remain outside this bounded contract.

Existing receipt tables are reused; no save migration, reimport or extra external
catalog is needed. Twenty additional regressions cover both families, paid and
free currency isolation, independent limits, UTC boundaries/offsets, new-login
limits, full-price one/ten draws, malformed state and requests, rollback,
fresh/imported accounts and persistent retries after price-data removal. Both
100-paid-gem daily operations have now passed in the prepared APK, with the owner
confirming persistence after reopening. Full-price type 4 has automated coverage.

## Normal party members

`/user/save-party-member/v2` accepts exactly `CharacterIds`: an ordered list of
one to four distinct positive Int32 owned inventory hero IDs. It uses the saved
roster directly and needs no additional external catalog. Public character spec
IDs, zero/null holes, repeated IDs and empty formations are rejected. The first
ID remains the leader; the array is never sorted or deduplicated. This route
saves the normal `User.Party` with ID zero, rather than selecting or editing a
mode preset. The client retains its feature-based slot availability checks;
the server bounds the formation to the four physical native slots.

The current normal-party object and owned hero registry must be unambiguous,
with a valid revision. Only `User.Party.Characters` and, when the formation
changes, `User.Cas` are updated. All other party metadata is retained. A shorter
array replaces the complete roster: native `PartyInfo.Apply` clears the old
trailing slots. Character equipment/progression, representative avatar, assets,
relic options/jewels, selected mode pointers, preset definitions and every other
profile section remain equal. No rewards or mission progress are invented.

The response contains only `User.Id`, `User.Cas` and the complete current
`User.Party`. Matching native `User.Apply` preserves omitted inventory, character
and preset fields, and `PartyInfo.Apply` resolves member IDs against the owned
character registry. Profile and ordered canonical request receipt commit or
roll back together. An unchanged formation records its identity without a
revision increase or profile rewrite. Exact epoch/sequence retries return the
current party without undoing newer choices or later equipment edits. Changing
members or their order under an already-used identity rejects.

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

For fresh accounts, optional `challenge_mission_catalog.json` contains a `groups` object keyed
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

Imported accounts use `imported_challenge_mission_catalog.json`, with a pinned
`client` object and the same `groups`/ordered `steps` structure. Its `condition`
uses a verified native mission type rather than the legacy aliases. Every reward
also specifies `storage`: `asset`, `stackable` or `misc`. Assets must already
exist; stackables merge into the existing active stack or allocate a new inventory
ID. A `misc` reward is one previously unowned cosmetic, with amount exactly one.
Already owned unique cosmetics reject until their duplicate/conversion policy is
known. The prepared public data classifies these from `items.Type`; random,
hero, weapon-stat or unknown reward types are not inferred.

The progress evaluators read saved state as follows:

| Native condition | Saved source |
| --- | --- |
| `SummonCharacter`, `SummonEquip` | `UserRecord.SummonCharacterCount`, `SummonWeaponCount` |
| `Attendance`, `EvolveCharacters` | `UserRecord.LoginDayCount`, `EvolveCharacterCount` |
| `LimitBreak`, `CraftMerch` | `UserRecord.LimitBreakCharacterCount`, `CraftMerchCount` |
| `BlessCharacters`, `EngraveWeapons`, `MythCharacters` | Matching `UserRecord.Misc` character/weapon counters |
| `DecomposeJewel`, `LobbyComplaintClear` | `UserRecord.Misc.DecomposeJewelCount`, `ComplaintClear` |
| `CollectHero` | Saved owned-character row count |
| `TowerInfinityClear` | `UserProgress.TowerInfinity.Floor` |
| `CollectGold` | Gold amount plus lifetime spending, capped at Int32 maximum |
| `UseStamina` | Charged/reserve stamina lifetime spending; reject native Int32 overflow |

Matching `MissionHelper.GetMissionProgressCount` branches establish these rules;
in particular, `LimitBreak` counts character breaks, not weapon breaks. The
prepared 3.57.0 KakaoGlobal catalog has 13 available groups and 1,190 contiguous
steps. Version/date gates must be resolved before preparing the file; two other
verified evaluator types have no available steps in this regional catalog.
Other native condition types still require verified evaluators. A saved counter
only advances when a corresponding local gameplay handler maintains it; these
claims do not invent battle results or new activity counts.

On a group's first local claim, its current imported `ChallengeClaimed` step is
saved in `imported_challenge_baselines`. Those old official steps receive no
local reward and need no fabricated local reward receipts. Only later steps
require contiguous `challenge_mission_claims` rows. The baseline cannot be
silently recreated when local receipts already exist, and cannot exceed the
saved claim marker. Baseline, new rewards, inventory IDs, claim markers and
request receipts commit together. Failed batches save none of them. Replays
retain frozen reward notices with current resources, even after catalog removal.
This extends the two challenge claim routes; beginner, daily and event claims
remain separate contracts.

## Imported hero collection knowledge

Imported accounts use a separate `imported_hero_knowledge_catalog.json` for
`/collection/claim-hero-knowledge-all`. The request is exactly `CharacterIds`, a
list of 1-512 positive inventory IDs. It never accepts public spec IDs as ownership.
The external catalog is required, limited to 2 MiB and pinned to the matching
`client`. Its fields are:

- `experience_by_level`: strictly increasing native total-XP thresholds, starting
  at zero; internal level is `bisect_right(thresholds, Experience) - 1`.
- `heroes`: public spec IDs mapped to `origin_id` and raw `rank` (0-6).
- `origins`: origin IDs mapped to sorted unique `nodes` indices and `objectives`.
  Each objective has a globally unique `id`, native `type`, `value` and `rewards`.
  Rewards are `{item_id, amount}`; only the verified gem asset 70003 is supported.
  Empty rewards are valid. Bits use `id % 100 - 1`, preserving sequence gaps.

The prepared matching public catalog contains 661 playable specs, 175 knowledge
origins and 1,329 objectives. Build it from `heroes`, `knowledgecollection`,
`exps2`, `charactertreeconfig`, `awakeningtreenodes` and `awakeningnodelayout`.
The native conditions compare acquisition/ownership; raw evolution rank; internal
level; saved limit breaks; opened awakening nodes; ascended-or-myth state; blessing
level; and myth state. Ascend uses a boolean current value, with public target 5
minus normal maximum rank 4. Myth also uses a boolean, with threshold 1; public
value 6 identifies its rank rather than requiring six myth upgrades.

Awakening null/empty means no opened nodes, matching `CharacterInfo.Apply`.
Nonempty trees use two Base64 parts separated by `|`; the first is a four-byte
spec prefix that can predate evolution. Only configured node bits in the second
part count, least-significant bit first within each byte. Derive node indices as
encoded tree node IDs modulo 1000 and bound them by the selected layout. Padding
and absent bytes cannot increase progress. Malformed encodings are guarded.

On the first local claim, existing official `Knowledge` flags become a nonpaying
baseline for that unique owned origin. Each newly earned objective then requires
its own local receipt. Missing baselines/receipts cannot be silently reconstructed
from current flags. Unknown original bits are preserved. New growth can earn later
objectives under a new request identity, without paying old objectives again.
Baselines, new gem balances, flags, User revision and request receipts commit in
one transaction. Exact retries return frozen notices with current User state,
even after catalog removal; they never restore an old profile or grant twice.
Other hero fields, spending counters and all other profile sections are retained.
This support is specific to hero knowledge; item/custom/mastery collection claims
have separate contracts.

The existing fresh-guest acquisition path below is unchanged.

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
The route is enabled for both completed fresh accounts and preserved imported
accounts. The same catalog and transaction apply, without creating a local
prologue row or modifying the captured seed. Account revisions use the client's
signed-64-bit range; an exhausted revision rejects a new purchase, while a saved
receipt still returns current state without writing.
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

## Experimental local raid catalog

`guild_raid_entry_catalog.json` is an optional external opt-in catalog, limited
to 256 KiB. It is not included in the existing 19-reference-file content release.
Keep it in the backend's reference directory. The exact top-level fields are:

- `client`: the matching version/version-code/region object.
- `fresh_local`: `true`, explicitly enabling the fresh, non-persistent view.
- `default_season_id`: an ID present in `seasons`.
- `daily_entries`, `max_retry`, `play_time_ms`: native public constants.
- `seasons`: unique entries containing `season_id`, `boss_set`, `round_set`,
  `period`, `bosses` and `first_round`.

Each period has aware ISO timestamps `from` and `to`, in increasing order.
Each season has four distinct boss and stage IDs, with slots 1–4; each boss has
only `slot`, `id`, `stage_id`. Its first-round object contains `number` (1),
positive `score`, nonnegative `buff_level` and positive `boss_hp_bar`. IDs and
numeric fields use bounded native integers. See the account-free synthetic
[catalog example](../tests/test_guild_raid.py) and the
[season command and limitations](official-save-experiment.md#fresh-local-raid-entry-and-season-selection).
Do not substitute guessed IDs or another client's catalog.

`guild_raid_selection.json` contains `client`, `season_id` and the generated
`static_data_sha256`, `static_data_checksum`, `static_data_revision` manifest.
The older two-field setting remains readable but cannot activate expired seasons;
run `raid-season set ID` again to upgrade it. Missing selection uses the catalog
default. Invalid/unknown selection rejects instead of silently choosing another.

`set` validates matching external `static_data_get.bin`, including the selected
season's boss/stage identities and unique global raid calendar ID. It creates
an immutable `guild_raid_static_<sha256>.bin` before atomically publishing the
selection. Source files, the catalog's original dates and SQLite remain unchanged.
The prepared body changes only the selected raid's `KakaoGlobal` period and any
existing reward-until timestamp, plus static revision/checksum records. Other
calendar rows, service variants, bosses and tables retain their values. No reward
route is enabled. Bootstrap checks the artifact hash before serving it; update
checks compare the client's checksum with the generated one.

Preparation accepts at most 64 MiB of decompressed local static text and uses
bounded LZ4 encoding to remain within the existing packet limit. The network
reader's default 16 MiB limit is unchanged. Binary static records retain their
original bytes and use checksums of their decoded binary content. Both the
original and prepared bodies remain private external data, excluded from the
content-pack allowlist. Unpublished artifacts left by an interrupted selection
do not become active; the atomic setting selects the complete body.

After every selection **fully close and reopen the game** to reload its static
calendar. Reconnect alone does not apply it. The backend rereads the setting,
but the client's loaded tables persist until restart. Selection changes neither
global server time nor the saved account. Historical boss rendering and combat
must still be checked in the APK.

## Dungeon Kingdom Arena practice selector

The optional `guild_punchking_catalog.json` contains pinned `client`,
`practice_only: true` and exactly three `variants`. Each variant has `id` (1–3),
`season_id` (native season row ID), `calendar_id` and seven ordered `days`.
Each day has `id` (native arena monster row ID), `monster_id` (character spec ID),
`stage_id`, `weak_point` and `element`. Prepare these from matching public
`guildpunchking.Seasons`/`Monsters`, not a player's score or a guessed boss ID.
All catalog values are checked against the preserved static tables before a
selection is published. The local prepared rotations use season rows 36, 37
and 35; the historical beta rows remain unchanged.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales dka-season list
.\.venv\Scripts\python.exe -m guardian_tales dka-season set 1 --day 1
.\.venv\Scripts\python.exe -m guardian_tales dka-season set 2 --day 5
.\.venv\Scripts\python.exe -m guardian_tales dka-season set 3 --day 7
```

The default reference directory for this command is `local/client-data/reference`;
override it with `--reference-dir`. Days 1–7 are the basic, light, dark, fire,
water, earth and space slimes. Native weakness names rotate through `Down`,
`Poison` and `Aerial`; the latter two represent the injury/airborne weaknesses.
The seven slimes keep their original stats, assets and stage. The command only
selects a matching existing rotation and aligns its native calendar.

`guild_punchking_selection.json` stores the variant/day, UTC content date,
seven-day period, composed Raid body digest and generated static manifest. Its
immutable `guild_punchking_static_<sha256>.bin` is published before the selection
pointer is replaced atomically. The selected arena's KakaoGlobal period starts
at today's UTC midnight minus day-1 and ends seven days later, minus one second.
Other arena periods close in the past so they cannot override that choice.
Other modes' calendar rows and other services' timestamps remain unchanged.
The client is told `StartOfDay=00:00:00`; its native day calculation therefore
selects exactly the requested slot without changing global server time.

If Raid has its own override, the arena body composes over it. A later Raid
change or later UTC content date rebuilds the arena calendar during the next
static check/get. The requested day remains fixed on that later login. An open
client crossing midnight must reload its tables; stage requests reject stale
day/boss data. **Fully close and reopen the game after each selector change**;
Reconnect alone retains its old static objects. The first code update also
requires restarting the backend. No CDN or bridge reconfiguration is needed.

The six implemented routes cover native entry, guild/member/user rankings,
start and completion. This is a free practice policy: no official ranking data,
rewards, coins, attempts, personal bests or imported profile state are written.
The native result screen still receives the client battle result. Entry returns
a seven-day `GuildRaid` status and partial `UserRaid` season pointer, preserving
unrelated cached currencies. Saved DKA teams in the native `[1300,1400)` block
can be selected with the normal preset selector; editing those definitions is
still a separate unsupported contract. Start requires the chosen catalog boss
and an existing nonempty owned team. Start/end store only local practice-session
and epoch/sequence receipts, commit atomically and fence variant/day changes.
Replays do not clear a later active battle. Unknown preserved arena progress is
guarded rather than reset. Reward/shop/message operations remain separate.

## Original-client content boundary

The prepared test used the base EN/ES content plus the Japanese voice supplement.
It did not prove every downloaded script, tilemap, language or media item was
complete. Missing resources remain missing; neither this backend nor the CDN
reconstructs or downloads them.
