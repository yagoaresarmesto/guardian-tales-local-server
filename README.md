# Guardian Tales Local Server

An experimental Python server for the **Guardian Tales 3.57.0 Android client**.
It implements the observed game transport, local guest identity, prologue account
creation, persistent character storage, the first campaign phase's clear path,
initial lobby queries, and a read-only resource server.

**This is not a complete offline version of the game.** In the prepared test
environment, the original APK completed the prologue, recovered the saved
character after restart, displayed the lobby and world map, and received its
first daily reward with Internet access blocked. The user also played the first
campaign phase, **Inn**, through its clear exit and returned to the world map.
Optional collectibles, later phases, equipment changes, battle validation and
most other game systems remain unfinished.

## Quick start

Clone the repository and run these commands with **Python 3.11 or newer**:

```sh
git clone https://github.com/yagoaresarmesto/guardian-tales-local-server.git
cd guardian-tales-local-server
python scripts/generate_dev_cert.py
python -m guardian_tales demo
python -m guardian_tales serve
```

Certificate generation requires an installed **OpenSSL CLI**. On Windows the
script also checks the usual Git for Windows OpenSSL location. Use `py -3.11`
instead of `python` if that is how Python is installed on your computer.
There are no third-party Python runtime dependencies and installation is optional.

The demo uses synthetic requests and a temporary database, then stops. The server
command runs until **Ctrl+C** and keeps the local account in
`local/state/server.sqlite3`. Check [http://127.0.0.1:17657/health](http://127.0.0.1:17657/health)
after starting it.

| Address | Purpose |
|---|---|
| `127.0.0.1:10100` | Binary game protocol over TLS |
| `127.0.0.1:10500` | Platform configuration and local guest APIs over HTTPS |
| `127.0.0.1:17657` | HTTP health/status endpoint |
| `127.0.0.1:18080` | Optional, separately started resource CDN |

Starting the backend does **not** install the game, configure an emulator, supply
game resources, or make the official APK connect to it automatically. An APK test
also needs compatible external bootstrap data, preserved resources, routing and
TLS trust in a dedicated test environment. See [setup](docs/setup.md) and
[client integration](docs/client-integration.md).

The pinned client baseline is **Android 3.57.0, Google Play, European service**,
with compatible bootstrap data and preserved resources from the same content
snapshot. Other versions and distributions have not been validated. See the
[compatibility details](docs/client-integration.md#client-version-and-content-compatibility).

## Current scope

| Component | State |
|---|---|
| TLS handshake, framing, checksum, LZ4, Ping/Pong | Implemented; protocol regression fixtures included |
| Platform configuration and local guest credentials | Implemented for one local guest |
| New account, prologue name/avatar/weapon selection | Persistent in SQLite; repeated completion is idempotent |
| Lobby, collection, inbox and catalog reads | Initial empty responses; no social or purchase functionality |
| World map and story entry | Catalog prerequisites, one-time stamina and free reentry; prepared entry catalog covers Inn and the second story phase |
| Daily attendance | External catalog required; supported asset rewards once per UTC day |
| Resource delivery | Read-only manifest allowlist; ETags, HEAD and single byte ranges |
| Quest registration | Known chapter quests can be registered in Inn with an external catalog; early main-quest checkpoints persist; other progression pending |
| Side-stage map discovery | Verified map targets persist as discovered; entering or playing those side stages remains pending |
| First-phase collectibles | Purple coins, star pieces, three named items and glove-chest receipts persist without duplicate grants; mixed currency batches are atomic |
| First-phase monster reports | Known handles persist; provisional level-1 gold/experience rule, no battle validation |
| Inn clear exit and first grade reward | Persistent completion, 50 free gems once, completion tutorial acknowledgment |
| Knight leveling | External catalog supplies level targets and story caps; single/multiple-level spending and reconnect receipts; limit breaks/blessings pending |
| Mission book | Help acknowledgment and beginner rewards for Inn, knight level 2 and spending 10 stamina persist; other missions pending |
| First hero collection challenge | Group 200, step 1: 50 free gems once for the saved starting knight |
| Ad inbox initialization | Returns saved local ad state; ad playback and reward claims remain pending |
| Summons screen entry | Empty local catalog checksum and event state; summoning remains pending |
| Pickup-ticket exchange check | Returns empty results when both event-coupon maps are empty; inventory tickets stay unchanged |
| Tutorial acknowledgments | Built-in help plus optional known-ID catalog; other UI markers require Inn cleared; no gameplay actions or rewards |
| Guardian Pass | Entry returns saved state; season 58's free level-1 reward grants 30 reserve stamina once; other progression and claims pending |
| Festival Pass | Entry returns saved state; season 41's free level-1 reward grants four festival points once; other progression and purchases pending |
| Guild lists | Empty local recommendations and invitations, no pending application; guild creation and membership remain pending |
| Later phase gameplay and remaining rewards | Unfinished; entry support alone does not implement a phase's interactions or clear rules |
| Multiplayer, guild systems and purchases | Not implemented |

All connections share the same local account. Incoming provider tokens are not
validated against an official service or retained. This is a loopback development
server, not a service for public hosting.

## Documentation

- [Setup and server commands](docs/setup.md)
- [How the components work](docs/architecture.md)
- [External reference data and resources](docs/reference-data.md)
- [Connecting a test client](docs/client-integration.md)
- [Observed packet protocol](docs/protocol.md)
- [Verified behavior and limitations](docs/status.md)
- [Inn checkpoint and next steps](docs/first-phase-checkpoint.md)
- [Development, tests, CI and GitHub preparation](docs/development.md)

Hosted test results are available in [GitHub Actions](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/workflows/ci.yml).

## Repository contents

```text
guardian_tales/        Server package and command-line tools
  templates/          Reconstructed empty-account and lobby templates
tests/                Behavioral regressions and protocol/synthetic fixtures
scripts/              Certificate generation and source-package checks
docs/                 Setup, architecture, protocol and current status
.github/workflows/    CI configuration
local/                Your runtime inputs and state; ignored by Git
```

The repository excludes account databases, certificate keys, game archives,
downloaded assets, captured bootstrap payloads, and tools tied to a particular
computer. The full attendance catalog is also external input. The built-in
templates contain empty local state, not a reference player's account.

## License

Original project code and documentation are licensed under [Apache 2.0](LICENSE).
See [NOTICE](NOTICE). This independent project is not affiliated with the game's
operators; externally supplied game files are outside the project license.
