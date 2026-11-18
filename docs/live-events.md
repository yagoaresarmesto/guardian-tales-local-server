# Temporal events and offline integration

The observed failure was `/live-event/enter`, rather than a pass claim. Entry now
returns the account's saved `UserEvent`. This is a read: it does not initialize a
season, change a revision, spend currency or grant rewards. Opening an event does
not yet implement its gameplay or claims. APK rendering remains to be checked
after reloading the backend and reconnecting.

## Entry contract and saved state

Matching Android 3.57.0 native `ApiConnection.SendEnterLiveEvent` sends a packet
with no body. The handler accepts that transport form, JSON null or an empty
object. Scene loaders await the request and then read global `UserEvent`, whose
native apply method consumes 13 event dictionaries and nullable `ReturnEvent`.
The handler checks the saved owner, revision and dictionary record identities,
retains additional fields, and leaves absent collections absent. It uses the
ordinary authenticated account dispatch for fresh and imported accounts.

The private test account has one Roadmap record and one Bingo record; its other
event dictionaries are empty and `ReturnEvent` is null. The saved Roadmap record
matches public event ID 33. No private account payload or player identifier is
included in the source tree.

Eight synthetic regressions cover fresh/imported state, the native no-body
packet, all dictionary families, retained metadata, repeated reads, reconnect,
authentication, malformed input/state and the boundary with unsupported claims.
A real-account check used a read-only, query-only SQLite connection and sent the
entry packet through the session and wire codec twice. Both responses matched
the saved resource exactly; the source profile was unchanged with zero writes.
These are native-contract and host checks, not an APK gameplay result.

## Families present in the matching content snapshot

Inspection of the matching external static tables found **14 families and 397
base definition rows**. Counts describe the unsuffixed base collections, not a
list of currently active or independently playable events. Historical rows,
regional overrides, eligibility and missing account progress must be considered
before selecting a season. The content itself remains external.

| Family | Source table / collection | Base rows | Main additional work |
|---|---|---:|---|
| Point/story live events | `s3liveevents.LiveEvents` | 38 | Point rules, claims; stage support for story/rift variants |
| Roadmap reward paths | `s3roadmapevents.RoadmapEvents` | 34 | Node prerequisites, point deductions, selected and remaining reward claims |
| Bingo | `s3bingoevents.BingoEvents` | 23 | Board state, ordinary/fixed draws, coins, round transitions and rewards |
| Giant gachapon | `s3gachaevents.GiantGachaMachineEvents` | 18 | Draw pool, costs, counters and giveaway claims |
| Marble/dice boards | `s3marbleevents.MarbleEvents` | 19 | Rolls, positions, laps, fixed draws and monopoly rewards |
| Roulette | `turntable.TurntableEvents` | 2 | Weighted draws, costs, progress and rewards |
| Event attendance | `liveevent.AttendanceEvents` | 227 | Eligibility, per-day claims and reward storage |
| Returning players | `s3returnevents.ReturnEvents` | 22 | Return eligibility, missions, days and point claims |
| Quiz | `quizevents.QuizEvents` | 5 | Board setup, answers, progress and claims |
| Hero growth | `s3herogrowthevent.Seasons` | 3 | Objective evaluation, clear/claim state and rewards |
| Slime juice shop | `s3slimejuiceevents.SlimeJuiceEvents` | 2 | Run results, upgrades, coin/social claims and persistence |
| Summon festival | `s3summonfestivalevents.SummonFestivalEvents` | 2 | Summon counters and milestone claims |
| Visitor | `visitorevents.VisitorEvents` | 1 | Gift eligibility, saved state and delivery |
| Web / Yutnori | `webevents.WebEvents` | 1 | Web component, local backend integration and point/cash claims |

The web definition has type `Yutnori` and a configured external event URL. Its
presence in static data does not preserve that website. Fully offline play would
require compatible web assets and services, or a local replacement. Native entry
support alone cannot establish that this event works.

The snapshot also contains boost, short-story and collaboration definitions,
plus separate single-raid and unexplored-expedition seasons. These use other
rules or stage systems and are not additional implementations of this entry API.
Guardian, Festival and World Pass catalogs likewise have separate routes/state.
Existing limited [pass support](../README.md#current-scope) remains separate from
the temporal-event work.

## Calendar and account eligibility

The source calendar is `seasondate.EventPeriod`; the prepared snapshot has 6,634
period rows. Matching Global period checks for 2026-11-18 UTC identified Roadmap
33 (season 3000127), returning-player event 22 (season 10000022), and new-player
attendance 231 (season 6000228) among these families. Source timestamps with no
offset were treated as UTC for this inspection. This is a snapshot observation,
not a query of the live service or proof of account eligibility.

Only Roadmap 33 already has a matching saved record in the private account.
Returning-player and new-player schedules do not make an existing imported
account eligible. Native current-event lookup can return no event when its
calendar or account record is missing. Entry deliberately leaves that situation
unchanged instead of inventing an entitlement or resetting old progress.

## Practical integration stages

1. **Preserved menus (implemented entry).** Return current event state and test
   the actual client screen. A later unsupported action needs its own contract.
2. **Roadmap, then Bingo.** These already have saved records in the test account.
   Roadmap is the best first target because its current scheduled record exists.
   Implement one observed action at a time with catalog rules and saved progress.
3. **Points, attendance and milestones.** Connect only verified activity counters
   to event conditions. Reward claims need explicit asset/item mappings and
   atomic progress plus durable receipts so retries cannot pay twice. A no-reward
   mock can be a separate explicit policy when requested.
4. **Minigames.** Gachapon, roulette, marble, quiz and juice each need their own
   draw/turn/result state, timers, validation and rewards. Client assets and an
   entry response do not supply these server rules.
5. **Web and combat content.** Preserve or replace the web component separately;
   story/rift/combat events also depend on the unfinished stage engine.

A historical-event selector, similar to the existing Raid/Dungeon Kingdom Arena
commands, is feasible but **not implemented by this change**. It should select a
known family/season, override only that season's calendar, and compose with the
existing Raid and arena overrides. It also needs explicit initialization and
per-season progress storage, validated eligible records and assets, and a policy
for keeping imported progress when switching. Moving the global server clock
would affect unrelated daily timers and is unsuitable for this selector. As with
the existing static-calendar selectors, client-cached tables require a full game
restart after changing the selected event.

Offline reward claims can ultimately deliver compatible local rewards without
contacting the official service. Purchases, social verification and unfinished
combat do not become implemented by enabling a season. Keep menu, host-rule and
actual APK results separate when extending this guide.
