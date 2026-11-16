# Verification and remaining work

Status recorded on **2026-11-16**. The public repository is a source-only
reorganization of the working prototype. Test results and original-client
observations have different scopes.

## Automated checks

The suite has **36 passing tests**, including the 34 original behavioral/protocol
regressions and two external-reference boundary tests. It covers real loopback TLS,
fragmented and pipelined frames, malformed input, local platform credentials,
account persistence across restart, prologue completion idempotency, restricted
migrations, daily reward retry handling, and manifest-backed resource reads.
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
- The initial campaign chapter stayed locked. No first campaign phase or battle
  completion was demonstrated.

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

1. Determine and implement correct initial chapter unlock state and phase entry.
2. Implement battle start/result contracts, progress validation and stage rewards.
3. Implement remaining inventory mutations, equipment state and item/random daily rewards.
4. Add the account's tutorial/mission progression and the systems it unlocks.
5. Expand content/resource completeness checks where indices can be interpreted.
6. Consider multiplayer/social modes only after the single-player state model works.

No completion date is implied. Several empty read endpoints are compatibility
scaffolding; they are not implementations of the corresponding game systems.
