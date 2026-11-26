# Guardian Tales Local Server

Run a private Guardian Tales save on your PC, open it in the Android client, and use a browser dashboard to manage your roster or set up a practice battle. The supported build is **Guardian Tales 3.57.0, Google Play, European service (version code 431)**. Each backend serves one local account.

- **Setting up for the first time?** Start with the [imported-account setup](#set-up-an-imported-account).
- **Already playing locally?** Jump to the [inventory editor](#inventory-editor) or the [seven game-mode tabs](#game-modes).
- **Checking whether something works in-game?** See [current scope](#current-scope) for the difference between Android observations and host tests.

## Inventory editor

Use the standalone dashboard for save edits. Run this from the repository root after restoring your save and importing the matching content.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales inventory-panel --open
```

You can browse while playing. To save changes, close Guardian Tales, choose **Services → Game backend → Stop** in the standalone dashboard, and confirm the edit. Choose **Restart** for the game backend and reopen the game when finished. The editor writes to your working SQLite database. Keep a separate backup before making changes you may want to undo. [Open the standalone dashboard](http://127.0.0.1:17661/)

| Inventory tab | What you can do |
| --- | --- |
| **Heroes** | Browse owned heroes by sprite, form and stars. Level, evolve, awaken or bless a hero for free. **Max hero** applies all eligible upgrades, including Ascension or Myth where supported. **Hero Reset** previews a return to level 1. |
| **Equipment** | Browse standard weapons, shields and accessories by type or stars (1★–6★), including a dedicated collaboration weapon filter. Add an exact variant, raise its level, limit break it or engrave an eligible exclusive weapon. |
| **Relics** | Choose a family and rarity (1★–5★), add a relic, or edit the basic options and sub-options on an owned copy. Both equipment and relics support **Max selected** within each slot’s catalog limits, plus individual or bulk lock, unlock and deletion. |
| **Merch** | Browse each owned copy by its game sprite, stars and level. Select a copy to see who has it equipped and whether it is locked. |
| **Consumables** | Find an owned stack and change its quantity within the item limit. |
| **Mastery** | Allocate Guardian Mastery points by class, preview the resulting bonuses and save the allocation. |
| **Account** | Edit player identity, wallet and materials. Pick a hero for Evolution or Myth Stones, or a world for Purple Coins. Review pending balances before applying them together. |

**Add hero** lists the collectible heroes missing from the save, including collaborations. Each recruit starts at level 1 in its original form. Evolved, Ascended and Myth forms count as owned. The two Knights share one story choice, as do Fei and Mei. Saving checks ownership again, including when two tabs try to recruit the same hero. [Inventory controls and bulk actions](docs/dashboard.md#inventory)

## Game modes

Open **Game modes** in the standalone dashboard, or use the dashboard served by the running backend. [Open the backend dashboard](http://127.0.0.1:17658/)

| Tab | What you can set up |
| --- | --- |
| **Raid** | Inspect four bosses on the encounter map. Select an original season or build a custom rotation with a boss and element per slot and a shared HP-per-bar setting. |
| **DKA** | Preview the slime and its weakness for any day in the three seven-day Dungeon Kingdom Arena rotations. |
| **Guild Wars** | Preview cooperative attack, cooperative defense, fortress siege and castle defense. Use the siege and Castle 21 presets for practice. |
| **Kama-ZONE** | Choose an event season or switch to **Old Kamazone** for one of the 40 preserved permanent rotations in the matching pack. |
| **Expedition** | Pan and zoom the reconstructed ten-district Solo Expedition map. Select a gate and stage to edit enemy levels, or apply one level to every stage. |
| **Orbital Lift** | Browse the ascending Tetis shaft (1–1,000) and descending Colony shaft (1,001–1,500). Select a cabin to load its enemy board. Edit formations, enemy levels and eligible elite modifiers, or set the next playable floor. |
| **Tetis** | Edit cleared floors across the three chapters. Manage Guardian Tactic training and specialties in seasons 2 and 3, along with the spell and artifact loadout. |

Season and enemy-table settings live alongside the reference data. Orbital Lift progression and Tetis account edits use the working save. Each tab gives the reload steps for its changes. [Practice controls, CLI commands and mode guides](docs/dashboard.md#game-modes)

## Set up an imported account

The documented setup uses Windows, Python 3.11+, Git, OpenSSL and a dedicated MuMu Player 12 instance running Android 12. The source checkout contains the server and dashboard. Supply the matching APK and splits, common content pack, and your own private save separately. The backend uses the Python standard library. The standalone dashboard installs its optional artwork and name readers on first use when needed. [Windows and PyCharm setup](docs/pycharm.md)

### 1. Prepare the checkout and content

In PowerShell, clone the project and create a virtual environment. Run the remaining commands from this repository root.

```powershell
git clone https://github.com/yagoaresarmesto/guardian-tales-local-server.git
cd guardian-tales-local-server
py -3.11 -m venv .venv
```

Place `content-manifest.json` and all ZIP parts from the same pack in `local/downloads/`. Leave the parts compressed. Import into a new or empty output directory, then check the result.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales content import --manifest local/downloads/content-manifest.json --output local/client-data
.\.venv\Scripts\python.exe -m guardian_tales content check --data-dir local/client-data
```

The published EU pack provides the English/Spanish baseline. Additional languages, artwork and practice catalogs depend on the pack you import. [3.57.0 EU content release](https://github.com/yagoaresarmesto/guardian-tales-local-server/releases/tag/content-3.57.0-eu-20261117) · [File placement and verification](docs/offline-content.md)

### 2. Restore the account before the first backend start

Keep your original backup. An empty state directory starts a new account. Choose the instructions for your save format.

**SQLite backup.** With the backend stopped, extract your save ZIP or place the complete `server.sqlite3` in `import/`. Copy it into the working state directory. This command refuses to overwrite an existing save.

```powershell
New-Item -ItemType Directory -Path .\local\state -Force | Out-Null
[System.IO.File]::Copy((Resolve-Path -LiteralPath '.\import\server.sqlite3').Path, (Join-Path $PWD.Path 'local\state\server.sqlite3'), $false)
```

**Account-snapshot JSON.** Inspect the snapshot and import it into an empty state directory.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales snapshot inspect --input .\import\account-snapshot.json
.\.venv\Scripts\python.exe -m guardian_tales snapshot import --input .\import\account-snapshot.json --data-dir .\local\state
```

The working database stays on the PC. If you choose a different state or reference directory, pass the same paths to the backend and standalone dashboard. [SQLite restore](docs/official-save-experiment.md#restore-an-existing-local-account-into-a-clean-client) · [JSON snapshot import](docs/official-save-experiment.md#inspect-and-import-a-snapshot)

### 3. Start the local game

Generate the client certificates once from the checkout.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales client-cert
```

Start the **game backend** and **resource CDN** in separate PowerShell terminals. Keep both running during play.

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m guardian_tales serve --data-dir local/state --cert-dir local/client-tls --reference-dir local/client-data/reference
```

```powershell
# Terminal 2
.\.venv\Scripts\python.exe -m guardian_tales assets --resource-root local/client-data/resources/files --reference-dir local/client-data/reference --port 18081 --journal local/cdn-requests.jsonl
```

Check the [backend health response](http://127.0.0.1:17657/health) and the [CDN resource index](http://127.0.0.1:18081/master-global-v3.57.0/Android.index). In a third terminal, follow the MuMu guide’s short routing check and play-session command using your dedicated instance’s index and name. Wait for **BRIDGE READY**, open Guardian Tales, and choose **Login as Guest** to load the restored account. Verify that the lobby shows the roster you expected. [MuMu play-session guide](docs/mumu-client.md#4-run-a-short-routing-check-then-the-play-session)

To finish, stop the bridge first with **Ctrl+C** and wait for **BRIDGE INACTIVE**. Then stop the other services. Stop the backend before making a plain file copy of `local/state/server.sqlite3`. [Shutdown and restoration](docs/mumu-client.md#5-stop-and-restore)

## Current scope

| Evidence | What it covers |
| --- | --- |
| **Observed in the Android client** | A clean client loaded a restored account and displayed its heroes and equipment. Resource download and file checks completed. Tests also exercised hero summons, Raid and DKA combat, selected Guild War practice paths, and a battle in Old Kamazone rotation 40. |
| **Campaign** | Host checks covered 39 chapter variants and entry and return for all 412 stages. A simulated guest completed 463 campaign quests. Android observations include the Inn clear and entering and leaving a stage on a completed Normal World 22 save. A full fresh Android playthrough remains unverified. |
| **Backend and save tools** | Supported operations include hero and equipment progression, free merch upgrades using mixed materials, presets, eligible hero costumes and weapon skins, and free equipment inventory expansion through the installed catalog’s steps. [Merch forge rules](docs/reference-data.md#free-merch-enhancement) |
| **Practice and online services** | Raid, DKA, Guild War and Solo Expedition practice grant no battle rewards. Orbital Lift defeat and return were observed on Android. Its optional victory path saves progress without rewards and has host coverage. Some social and event screens show empty local data. Real multiplayer, purchases and official competitive settlement remain outside the local server. |

For repeatable campaign testing, `campaign preview` shows the changes in memory and `campaign complete` backs up and prepares a local test save. Use a separate empty state directory for a fresh guest. [Campaign coverage and commands](docs/reference-data.md#main-story-and-completed-campaign-testing) · [Clean-client observations](docs/official-save-experiment.md#restore-an-existing-local-account-into-a-clean-client) · [Verification log](docs/status.md)

## Further reading

- **Playing and administration** — [Dashboard guide](docs/dashboard.md), [server options](docs/setup.md), [reference data and game mechanics](docs/reference-data.md), [local administration](docs/administration.md).
- **Optional experiments** — [Andras Myth trial](docs/reference-data.md#experimental-andras-myth-view), [Classic Co-op Defense](docs/reference-data.md#classic-co-op-defense-trial), [Head Hunter](docs/head-hunter.md), [fixed-stat test items](docs/test-items.md).
- **Development** — [Source-only demo](docs/setup.md#run-the-synthetic-demo), [architecture](docs/architecture.md), [protocol](docs/protocol.md), [test groups](tests/README.md), [development checks](docs/development.md) and [CI](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/workflows/ci.yml).

## License

The project’s original code and documentation use the Apache 2.0 license. Guardian Tales and its assets belong to their respective rights holders. This is an independent project. [License](LICENSE) · [Notice](NOTICE) · [Game content notice](docs/content-notice.md)
