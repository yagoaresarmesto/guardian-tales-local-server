# Verification and remaining work

Status recorded on **2026-11-16**. The public repository is a source-only
reorganization of the working prototype. Test results and original-client
observations have different scopes.

## Automated checks

The suite has **84 passing tests**, including fourteen first-chapter entry/progress
regressions, four initial knight training regressions, a mission-help tutorial
regression, eight beginner-reward regressions and four first-hero challenge
regressions, an empty event-coupon exchange regression and four initial Guardian
Pass reward regressions and four initial Festival Pass reward regressions.
Eight additional catalog-training regressions cover variable costs, multi-level
targets, batches, story caps, shared balances, request identity, reconnect,
sequence reuse, legacy receipts and rollback. It covers real loopback TLS,
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

Monster gold/experience currently uses one public level-1 `ExpsData` row per new
known monster handle: 79 experience and 87 gold. This is a provisional **local
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

## Prioritized implementation work

1. Continue from the next user-reported unsupported operation. The earlier
   [Inn checkpoint](first-phase-checkpoint.md) remains a historical record.
2. Finish Inn's optional collectible/custom-state contracts and battle validation.
3. Implement later campaign phases and their progression/reward rules.
4. Implement item/random daily rewards and the remaining inventory operations.
5. Add the account's mission progression and the systems it unlocks.
6. Expand content/resource completeness checks where indices can be interpreted.
7. Consider multiplayer/social modes only after the single-player state model works.

No completion date is implied. Several empty read endpoints are compatibility
scaffolding; they are not implementations of the corresponding game systems.
