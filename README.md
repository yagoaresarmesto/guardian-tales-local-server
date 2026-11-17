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
The first connecting passage's entry, observed encounters and clear exit also
passed with the same saved account.
Optional collectibles, later phases, equipment changes, battle validation and
most other game systems remain unfinished.

## Use the matching APK with preserved offline content

Start with the [offline content guide](docs/offline-content.md). It explains
which Release attachments to download, exactly where to put them, how to import
and verify them, and how to start both the backend and resource CDN. The
[3.57.0 European content release](https://github.com/yagoaresarmesto/guardian-tales-local-server/releases/tag/content-3.57.0-eu-20261117)
contains the preserved resource packages and matching bootstrap/catalog data.
Supply your own compatible APK. A new installation creates its own local guest;
no existing player's save is distributed.

Android hostname routing and TLS trust still need a dedicated test setup. The
guide distinguishes those integration requirements from importing the content.
The remaining backend limitations below continue to apply.

## Quick backend test

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

Starting the backend does **not** install the game, configure an emulator, import
game resources, or make the official APK connect to it automatically. Use the
[content guide](docs/offline-content.md) to obtain and import the separate data
release, and [client integration](docs/client-integration.md) for routing and TLS
trust requirements.

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
| World map and stage entry | Catalog prerequisites, one-time stamina and free reentry; prepared catalog covers Inn, the first passage, the second main phase and one discovered side stage |
| Daily attendance | External catalog required; supported asset rewards once per UTC day |
| Resource delivery | Read-only manifest allowlist; ETags, HEAD and single byte ranges |
| Quest registration | Known chapter quests can be registered in Inn with an external catalog; early main-quest checkpoints persist; other progression pending |
| Side-stage map discovery | Verified map targets persist as discovered; configured entry can require finding the map; side-stage gameplay remains pending |
| First-phase collectibles | Purple coins, star pieces, three named items and glove-chest receipts persist without duplicate grants; mixed currency batches are atomic |
| Monster reports | Inn handles plus external stage catalogs; atomic rewards once per stage/handle, provisional local rates, no battle validation |
| Inn clear exit and first grade reward | Persistent completion, 50 free gems once, completion tutorial acknowledgment |
| Configured later clear exits | External exit/encounter prerequisites, saved completion and earned openings; additional clear rewards pending |
| Local currency administration | Audited gem and season-bound Festival point grants, idempotent operation IDs and exclusive offline writes |
| Gem stamina purchases | External price tiers, atomic free-gem costs and stored stamina, UTC daily quota and persistent retry receipts |
| Knight leveling | External catalog supplies level targets and story caps; single/multiple-level spending and reconnect receipts; limit breaks/blessings pending |
| Mission book | Inn, knight level 2, stamina and configured hero-draw milestones; atomic batches and persistent reward receipts; other missions pending |
| Hero collection/draw challenges | Configured thresholds, next-step or all-earned-step batches, atomic asset rewards and persistent step/request receipts |
| Hero acquisition knowledge | Catalog-backed initial knowledge for batches of untrained base heroes, saved character flags and retry receipts; advanced objectives pending |
| Ad inbox initialization | Returns saved local ad state; ad playback and reward claims remain pending |
| Summons screen entry | Optional local hero candidate catalog with matching checksums; empty fallback without external data |
| Hero wishlist | Up to five distinct catalog heroes persist without spending currency or granting inventory |
| Local hero draws | One/ten draws with configured probabilities, free gems or either controller type; new heroes, duplicate crystals, mileage and persistent retry receipts |
| Pickup-ticket exchange check | Preserves imported event-coupon counters without conversion; empty fresh guests supported; redemption/expiration pending |
| Play-menu prerequisites | Read-only cooperative placeholder with captured presets and saved rift settings; APK retry pending; mode gameplay unfinished |
| Tutorial acknowledgments | Built-in help plus optional known-ID catalog; other UI markers require Inn cleared; no gameplay actions or rewards |
| Guardian Pass | Entry returns saved state; season 58's free level-1 reward grants 30 reserve stamina once; other progression and claims pending |
| Festival Pass | Initial free points, local shop availability and configured asset/stackable/individual item redemptions; sticker packs and other progression pending |
| Guild lists | Empty local recommendations and invitations, no pending application; guild creation and membership remain pending |
| Later phase gameplay and remaining rewards | Unfinished; entry support alone does not implement a phase's interactions or clear rules |
| Multiplayer, guild systems and purchases | Not implemented |

All connections share the same local account. Incoming provider tokens are not
validated against an official service or retained. This is a loopback development
server, not a service for public hosting.

## Documentation

- [Fresh installation in PyCharm on Windows](docs/pycharm.md)
- [Connect a dedicated MuMu Android 12 instance](docs/mumu-client.md)
- [Offline content: downloads, exact file placement and startup](docs/offline-content.md)
- [Setup and server commands](docs/setup.md)
- [Grant gems/Festival points and inspect administrative history](docs/administration.md)
- [How the components work](docs/architecture.md)
- [External reference data and resources](docs/reference-data.md)
- [Connecting a test client](docs/client-integration.md)
- [Observed packet protocol](docs/protocol.md)
- [Verified behavior and limitations](docs/status.md)
- [Experimental private-account snapshot import](docs/official-save-experiment.md)
- [API inventory and implementation plan](docs/implementation-plan.md)
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
local/                Runtime inputs and state; download instructions included
```

The source tree excludes account databases, certificate keys, game archives,
downloaded assets, captured bootstrap payloads, and tools tied to a particular
computer. Preserved resources and matching reference data are distributed
separately as Release attachments with a [content notice](docs/content-notice.md).
The built-in templates contain empty local state, not a reference player's account.
The tracked [download folder instructions](local/downloads/README.md) keep
`local/downloads/` present after cloning; its downloaded files remain ignored.

## License

Original project code and documentation are licensed under [Apache 2.0](LICENSE).
See [NOTICE](NOTICE). This independent project is not affiliated with the game's
operators; externally supplied game files are outside the project license.
