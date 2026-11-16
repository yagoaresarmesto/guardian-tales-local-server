# Verification and remaining work

Status recorded on **2026-11-16**. The public repository is a source-only
reorganization of the working prototype. Test results and original-client
observations have different scopes.

## Automated checks

The suite has **47 passing tests**, including eleven first-chapter entry/progress
regressions. It covers real loopback TLS,
fragmented and pipelined frames, malformed input, local platform credentials,
account persistence across restart, prologue completion idempotency, restricted
migrations, daily reward retry handling, manifest-backed resource reads, empty
chapter progress objects, atomic stamina spending, free stage retries, and initial
quest persistence without duplicates, native stage-progress bytes, overlapping
coin batches, monster reward retries and stable item receipts.
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

The APK subsequently accepted the first two quest checkpoints, a five-purple-coin
batch, the two initial goblin reports and the shield pickup. The database retained
those records after another laboratory restart. The APK then reopened Inn with populated native stage progress showing 5/26 coins
and 1/4 item markers; no completed campaign phase is claimed.

Monster gold/experience currently uses one public level-1 `ExpsData` row per new
known monster handle: 79 experience and 87 gold. This is a provisional **local
rule**, not a verified reconstruction of official server rates, multipliers or
random drops. Reports are allowlisted and deduplicated but battles are not
validated by the server. The remaining named items are covered by automated
receipt tests and their public runtime configuration; only the shield has been
picked up in the initial APK test. A subsequent test also accepted the costume
pickup and glove chest, showing 3/4 item markers, and advanced quest checkpoints
3 and 4. The chest grants the public tilemap's single item 30017 and records the
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

1. Finish the first phase's battle, collectible, custom-state and exit contracts.
2. Implement stage progress validation, completion and rewards.
3. Implement remaining inventory mutations, equipment state and item/random daily rewards.
4. Add the account's tutorial/mission progression and the systems it unlocks.
5. Expand content/resource completeness checks where indices can be interpreted.
6. Consider multiplayer/social modes only after the single-player state model works.

No completion date is implied. Several empty read endpoints are compatibility
scaffolding; they are not implementations of the corresponding game systems.
