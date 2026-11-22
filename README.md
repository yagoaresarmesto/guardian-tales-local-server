# Guardian Tales Local Server

An experimental local Python server for the **Guardian Tales 3.57.0 Android
client, Google Play European service, version code 431**.

The main workflow is **loading an existing, privately preserved account into a
clean local installation**, then testing its heroes, equipment and supported
game modes. Account import and the local practice tools are available on
**`main`**; an old experimental branch is not required.

The prepared Windows/MuMu lab has restored the imported account into a clean
client, verified its heroes and equipment, completed resource downloads and the
downloaded-file check, and tested supported local combat paths. English and
French text were also checked with the expanded content pack. See the
[clean-client restore observations](docs/official-save-experiment.md#restore-an-existing-local-account-into-a-clean-client).

**This is not a complete offline recreation of the official game.** Available
assets do not implement an unsupported API or recover uncaptured account data.
Some screens use empty responses, and several local practice modes deliberately
grant no rewards or save no battle results. Full campaign progression, real
multiplayer and the remaining official systems are unfinished.

## What you need

- **Windows, Python 3.11+, Git and an OpenSSL CLI** for the documented PyCharm
  setup. There are no third-party Python runtime dependencies.
- **MuMu Player 12 / Android 12**, a dedicated non-main test instance with root
  support, and your own matching APK with any required splits. Other client
  versions, regions and emulator arrangements have not been validated.
- **Compatible game files and reference catalogs**, supplied separately from
  the source. Keep every content ZIP part with its matching manifest.
- **Your private save**, either a complete local `server.sqlite3` backup or a
  validated account-snapshot JSON. These are different input formats.

The repository contains no player's save, APK or generated certificate keys.
Obtain compatible common content through the maintainer's supplied links and
supply your private account backup separately. The [published content release](https://github.com/yagoaresarmesto/guardian-tales-local-server/releases/tag/content-3.57.0-eu-20261117)
is an older EN/ES baseline; newer supplied packs can include additional languages
and mode catalogs. Use the manifest belonging to your pack, and do not mix parts
from different releases or assume they cover the same features.

## Set up an imported account

These examples use **PowerShell in PyCharm**, from the repository root. Use the
same paths in every terminal. The [PyCharm guide](docs/pycharm.md),
[content guide](docs/offline-content.md) and [MuMu guide](docs/mumu-client.md)
cover the individual tools; their fresh-guest examples do not replace the save
restoration step below.

### 1. Clone `main` and select Python

```powershell
git clone --branch main https://github.com/yagoaresarmesto/guardian-tales-local-server.git
cd guardian-tales-local-server
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe --version
```

Select `.venv` as the PyCharm interpreter. If the Windows `py` launcher is not
installed, create the environment using your installed Python executable.
Certificate generation needs OpenSSL; the tools also check the usual Git for
Windows OpenSSL location. No `pip install` is needed to run from the checkout.

### 2. Import the common game content

Place `content-manifest.json` and **all of its original ZIP parts** together in
[`local/downloads/`](local/downloads/README.md). Keep those ZIPs compressed; the
content importer handles extraction and integrity checks.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales content import --manifest local/downloads/content-manifest.json --output local/client-data
.\.venv\Scripts\python.exe -m guardian_tales content check --data-dir local/client-data
```

Use a new or empty output directory. The resulting resource files go under
`local/client-data/resources/files/`; bootstrap responses and mode catalogs go
under `local/client-data/reference/`. These are common game data, separate from
the writable account database. See [file placement and content verification](docs/offline-content.md).

### 3. Restore the save before starting the backend

> [!IMPORTANT]
> **Restore or import the account before the first backend start.** Starting the
> server against an empty state directory can create a new starter account.
> Keep the original backup untouched and use a separate working copy.

For a **save ZIP containing `server.sqlite3`**, extract the save ZIP into the
repository's `import/` folder. This ZIP is extracted manually, unlike the common
content ZIPs. Verify the supplied checksum when one is provided. For a plain
SQLite backup, place that complete file there directly.

```text
import/
  server.sqlite3
  server.sqlite3.sha256    Optional supplied checksum
```

With the backend stopped, copy the database into the working state directory:

```powershell
New-Item -ItemType Directory -Path .\local\state -Force | Out-Null
[System.IO.File]::Copy((Resolve-Path -LiteralPath '.\import\server.sqlite3').Path, (Join-Path $PWD.Path 'local\state\server.sqlite3'), $false)
```

The copy refuses to overwrite an existing database. If one already exists,
preserve it and choose a separate state directory rather than replacing it.
Use that directory consistently with every later `--data-dir` argument.
The database belongs on the **computer**, not inside Android's game folders.

If your input is instead a **validated account-snapshot JSON**, use these
commands **instead of copying an SQLite file**. The destination must be empty:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales snapshot inspect --input .\import\account-snapshot.json
.\.venv\Scripts\python.exe -m guardian_tales snapshot import --input .\import\account-snapshot.json --data-dir .\local\state
```

The snapshot importer does not accept SQLite backups. It also does not log in to
the official service or download an account. Preserving a still-accessible
official account is a separate observation workflow; its original capture tools
are not part of a public source clone. See [snapshot format and account preservation](docs/official-save-experiment.md#inspect-and-import-a-snapshot).

### 4. Generate certificates and start the three services

Generate your own APK-compatible certificates once:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales client-cert
```

This creates `local/client-tls/`. Existing keys are not overwritten. Both the
backend and bridge must use the same certificate directory. The basic
`generate_dev_cert.py` certificate is for backend probes; use `client-cert` for
the game's hostnames. See [certificate setup and renewal](docs/mumu-client.md#2-generate-the-apk-certificate).

**Terminal 1 — backend:**

```powershell
.\.venv\Scripts\python.exe -m guardian_tales serve --data-dir local/state --cert-dir local/client-tls --reference-dir local/client-data/reference
```

**Terminal 2 — resource CDN:**

```powershell
.\.venv\Scripts\python.exe -m guardian_tales assets --resource-root local/client-data/resources/files --port 18081 --journal local/cdn-requests.jsonl
```

Check [backend health](http://127.0.0.1:17657/health). A snapshot-derived save
should report `imported_account: true`; compare the loaded account with the
intended backup. The CDN should also serve the
[Android resource index](http://127.0.0.1:18081/master-global-v3.57.0/Android.index).
A healthy backend alone does not verify resource downloads or Android routing.

**Terminal 3 — Android bridge:** first follow the
[short setup/restoration check](docs/mumu-client.md#4-run-a-short-routing-check-then-the-play-session)
with the game closed. For the regular session, replace the example index/name
below with **your actual dedicated instance**:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales android-bridge run --index 1 --name GT357-Import-Test --cdn-port 18081 --minutes 500
```

Wait for **`BRIDGE READY`**, then open the game. Choose **Login as Guest** if a
sign-in choice appears: the local server loads the restored PC database and uses
its own local guest credentials. An official-account login is not required for
this local test.

Keep all three terminals running. Verify your expected heroes, equipment and
inventory. If the game shows a starter profile or asks you to replay the
prologue, stop and check the state path before changing anything. Copying files
into `import/` alone does not make the backend load them.

### 5. Stop safely and keep the save

Press **Ctrl+C in the bridge terminal first** and wait for restoration /
`BRIDGE INACTIVE`. Then stop the backend and CDN with Ctrl+C, and close the
dedicated emulator. If the bridge reports that a previous session needs
restoration, use the [documented restore action](docs/mumu-client.md#5-stop-and-restore)
for the same instance; keep its session record until cleanup succeeds.

The working save remains at `local/state/server.sqlite3`. Stop its backend
before making a plain file backup, or use a coherent SQLite backup procedure.
Keep the full database and verify its integrity/checksum. Changing a Git branch
does not isolate or back up this runtime state.

## Current scope

The table summarizes the imported-account workflow. Detailed evidence and
per-operation limits are recorded in the [status notes](docs/status.md) and
[account experiment log](docs/official-save-experiment.md); an automated check
and an actual APK observation are different forms of verification.

| Area | Current behavior and limits |
|---|---|
| Account and clean-client restore | Preserved profile, owned heroes/equipment and startup reads load locally; only observed account data is preserved, and detailed campaign coverage varies. |
| Summons | One- and ten-hero local draws worked in the APK. Rates, payment variants and catalogs are local rules; importing a profile does not recover official summon logic or history. |
| Equipment and relics | Catalog-backed local enhancement, limit breaks, engraving, option changes and locks. Prepared free policies retain materials for supported operations; actual APK coverage varies by operation. |
| Jewels, hero experience and collection systems | Additional local handlers and retry-safe persistence are implemented. Several result/claim paths have automated coverage but still need their documented APK checks. |
| Teams and presets | Saved formations plus preset selection, editing, deletion and creation; several Orbital operations were verified in the APK. Other team/preset paths retain their individual limits. |
| Village and mastery | Resource collection, mastery upgrades/reset and selected no-reward mocks; fixed base-camp mastery rewards require an explicit debug policy. |
| Raid | Local season selection, menu, combat and return were verified with the prepared account, including season 46 in French. Empty rankings/history and no-reward battle acknowledgments; no official raid settlement. |
| Dungeon Kingdom Arena | Three rotations and days 1–7 selectable by command. A configured menu/combat/return path was verified in French; every variant/day combination has not been separately verified in the APK. No saved scores or rewards. |
| Guild War | Cooperative attack/defense, marked-target siege and selected-castle defense trials, plus Prep Round practice. Confirmed entry/result/menu paths depend on phase and selection; no saved captures, competitive results or battle rewards. |
| Orbital Lift | Entry, defeat and menu return observed. The opt-in victory path saves progress without rewards; actual APK victory remains unverified. |
| Social, passes and events | Partial reads, local placeholders and selected reward/no-reward policies. Empty views are intentional in some areas; real peers, purchases and full event progression are unavailable. |
| Resources and languages | Local manifest-checked downloads; clean-client download/organization and EN/FR changes were verified with expanded content. Available languages and mode assets depend on the supplied pack. |

Configured free/no-reward behavior is part of the local experiment, not a claim
to reproduce official economy rules. Use the matching reference catalogs and
read each mode's prerequisites before enabling it. All connections to one
backend share **one local account**; this is a loopback development server,
not a public multiplayer service.

## Practice commands

Run selectors against the **same reference directory as the backend**, outside
battle. After changing seasons, variants or Guild War settings, **fully close
and reopen the game** to reload its cached static data. Reconnect alone may
retain the previous selection.

Mode selections are stored with the reference data, separately from the account
database; restoring the save alone does not activate them. Guild War overrides
the guild calendars while enabled. Disable its trial before returning to the
parent Raid/DKA configuration, following the [mode guide](docs/guild-war.md).

### Raid and Dungeon Kingdom Arena

```powershell
.\.venv\Scripts\python.exe -m guardian_tales raid-season list --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales raid-season set 46 --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales raid-season custom "sandmonster light, ancient demon fire, viper clan leader dark, sandmonster water" --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales dka-season list --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales dka-season set 1 --day 1 --reference-dir local/client-data/reference
```

Raid seasons available depend on the supplied catalog. `custom` selects the
first listed season and applies the four choices in slot order. `set ID`
selects a stock season again. DKA accepts variants 1–3 and days 1–7.
See the [Custom Raid user guide](docs/custom-raid.md)
and [DKA selector](docs/reference-data.md#dungeon-kingdom-arena-practice-selector)
for catalog requirements, composition and limits.

### Guild War: recommended siege practice

> [!IMPORTANT]
> **Recommended attack practice:** Prep Round with no marked target allows
> practice entry across the castle map without marking each castle by command.
> This path worked in the prepared APK test.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase multi-offense --round prep --attack-castle 0 --reference-dir local/client-data/reference
```

> [!IMPORTANT]
> **Recommended defense practice:** select one local owned castle in Prep
> Round. Castle 21 is a displayed-level-150 example confirmed in the APK.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales guild-war enable --skip-basic --phase multi-defense --round prep --defend-castle 21 --reference-dir local/client-data/reference
```

Restart the game after either command. Defense retains the selected-castle
requirement. These are local trials requiring the prepared catalogs and owned
guild membership; they do not grant persistent castle ownership. All four
phases, status/disable commands and other variants are documented in the
[Guild War guide](docs/guild-war.md).

For controlled gem/Festival-point grants, use the
[administration guide](docs/administration.md) with the same account state
directory. Writes require stopping the backend first.
The opt-in [test-pin commands](docs/test-items.md) add new equipment with
configurable base DEF and an optional ATK-percent suboption only when explicitly
run against a stopped account.

The optional [Expedition enemy-level commands](docs/reference-data.md#per-stage-enemy-levels)
list stages, set a per-stage level and restore original levels. They configure
external static overlays without editing the saved account.

## Starting a new account

Creating a fresh local guest remains an **experimental secondary path**. Its
prologue, persistence and early campaign clear paths were previously exercised,
but a full playthrough from zero is not the project's main workflow. Later
campaign interactions and general progression remain incomplete.

Use a separate empty state directory for that experiment. See the
[early campaign checkpoint](docs/first-phase-checkpoint.md) and
[verified limitations](docs/status.md). For a source-only synthetic demonstration
without an APK or real save, run `python -m guardian_tales demo`.

## Documentation and source layout

- [Restore a complete SQLite save into a clean client](docs/official-save-experiment.md#restore-an-existing-local-account-into-a-clean-client)
- [Private JSON snapshot validation/import](docs/official-save-experiment.md#inspect-and-import-a-snapshot)
- [PyCharm setup](docs/pycharm.md), [common content](docs/offline-content.md) and [MuMu bridge](docs/mumu-client.md)
- [All server options](docs/setup.md), [reference catalogs](docs/reference-data.md) and [local administration](docs/administration.md)
- [Guild War](docs/guild-war.md) and [temporal-event integration](docs/live-events.md)
- [Architecture](docs/architecture.md), [protocol](docs/protocol.md) and [client integration](docs/client-integration.md)
- [Verified status](docs/status.md), [implementation inventory](docs/implementation-plan.md) and [development checks](docs/development.md)
- [Organized test groups](tests/README.md) and [GitHub Actions](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/workflows/ci.yml)

```text
guardian_tales/        Server package and command-line tools
docs/                 Setup, mode guides and verification records
tests/                Synthetic fixtures and regression tests
scripts/              Certificate helpers and source checks
import/               Private save inputs; initially an empty tracked marker
local/downloads/      Common content ZIP parts and their manifest
local/client-data/    Imported common resources and reference catalogs
local/state/          Working server.sqlite3 account database
local/client-tls/     Locally generated certificate keys
```

`import/` and runtime files under `local/` are excluded from source distribution.
Keep account backups private: they contain player identifiers and can include
local guest credentials. Git ignores are a convenience, not access control.
The source contains reconstructed empty templates, not a reference player's save.

## License

Original project code and documentation are licensed under [Apache 2.0](LICENSE).
See [NOTICE](NOTICE). This independent project is not affiliated with the game's
operators; externally supplied game files are outside the project license.
