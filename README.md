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

In the Book of Contents, the Recommended tab uses each card's original PNG from
the installed resource manifest when available. For missing Tetis, Co-op
Expedition and main story cards the CDN can render the corresponding local game
texture with the optional `panel-art` reader. The generic Short Story card
uses Invader Journalist scenery from the pack. This scenery also provides a
fallback when the texture reader is unavailable.

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
| Equipment and relics | Catalog-backed hero equipment changes, local enhancement, limit breaks, engraving, option changes and locks. Prepared free policies retain materials for supported operations; actual APK coverage varies by operation. |
| Jewels, hero experience and collection systems | Additional local handlers and retry-safe persistence are implemented. [Hero Reset](docs/reference-data.md#hero-reset) clears the selected hero's growth for free and returns no items. Several result/claim paths have automated coverage but still need their documented APK checks. |
| Teams and presets | Saved formations plus preset selection, editing, deletion and creation; several Orbital operations were verified in the APK. Other team/preset paths retain their individual limits. |
| Village and mastery | Village resource collection, mastery upgrades and resets. Collecting from the Guardian Base Camp advances its timer and awards zero mastery points. You can manage mastery in the inventory panel. |
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

## Inventory editor

Use **Game modes** and **Inventory** at the top of the dashboard to switch
between Raid, Tetis and the save editors. While the game backend is running,
you can browse [Equipment](http://127.0.0.1:17658/equipment) directly.

To keep the dashboard available when you stop the game backend for inventory
edits, launch it independently from the repository root:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales inventory-panel --open
```

This command opens the same dashboard on [the Equipment page](http://127.0.0.1:17661/). It reads your existing
`local/state/server.sqlite3` and the matching catalog in
`local/client-data/reference`. Use `--data-dir` and `--reference-dir` if your
backend uses other directories. At startup the inventory panel checks for its artwork
and English name readers and uses the same Python interpreter to install missing
dependencies with pip. Later launches reuse them offline. If installation fails, you can still
browse with placeholder icons and rerun the command to retry. The images come from
your imported game resources. The panel also reads the game's UI atlas for
icons such as the Selectable Summon Controller. In each tab, search by name or ID, filter
by type and use the page arrows to browse. Select an item to see its details.

Running the command again for the same save and port opens the existing dashboard.
After updating the project, choose **Services → Inventory server → Restart** and
reload the page to load the new account features.

For English equipment names, the panel looks up the item's shared name key in the
game's English text table. Content packs can include the decoded
`reference/strings-bin-enUS`. With an older pack, copy `cache/strings-bin-enUS`
from a matching English game-data export to `local/client-data/reference/strings-bin-enUS`,
then restart the inventory panel. The file under `files/static_data/` is the
encoded download. Existing catalog-bound English tables also work.

- **Equipment** lets you change basic options, sub-options and their locks on an individual weapon or accessory.
  The grid and detail view size equipment artwork by its original sprite dimensions so that compact items, such as rings and gauntlets, retain their proportions alongside long weapons.
  Exclusive weapons show their hero’s face in the lower-right corner, using the hero’s 6★ portrait when available. Their cards fade from blue to green, or to pink for a 6★ copy.
  The upper-right book ribbon marks completed weapon knowledge and its associated collections. The exclusive ribbon shows the weapon’s current engraving state. A rainbow star means the bonus has reached its maximum, even if the weapon still has engraving attempts left.
  Under **Weapon upgrades**, raise a weapon's limit breaks and engrave eligible exclusive weapons once they meet the experience and limit-break requirements. Choose an engraving count and one of the bonus values offered for that weapon. The editor reads these limits from the imported game catalog. **Apply** saves the selected upgrades and option edits together, without spending hammers or gold.
  Under **Shield upgrades** or **Accessory upgrades**, choose a higher limit break for the selected item. Once all breaks are unlocked, **Raise to max level** stays available until the item reaches its level cap.
  **Raise to max level** previews the highest level that copy can reach with your story progress and selected upgrades. Tick it and click **Apply** to grant exactly the missing equipment XP for free. On a save with base level 100 in 3.57.0, each limit break adds 3 levels, an eligible engraving adds 15 once, and Myth weapon rarity adds 20. With all five breaks, a shield or accessory reaches 115, an engraved 5★ weapon reaches 130 and an engraved 6★ weapon reaches 150.
  Choose **Enhance** below **Accessory** to edit an owned hammer stack. Strengthening Hammers show their level, and Limit Breaking Hammers show their rarity. Enter a quantity, review the change and click **Apply**.
- **Relics** lets you choose the effect and value for each editable basic or bonus slot.
- **Consumables** lets you change the quantity of an owned stack. The grid and detail view scale the original sprites to leave space around tickets, stones and other materials. The panel checks each quantity change against the item's catalog limits.
- **Mastery** groups Guardian Mastery skills by hero class. Select a class to adjust its skill levels and see each stat bonus and the point cost of its next level. Each level control shows the range allowed by the other classes. The − and + buttons stop at those limits, and a typed level is adjusted to the range when you finish editing. You can also reset a fully maxed allocation. Review the projected point balance, then click **Apply** to save the whole allocation at once. The panel enforces the catalog’s skill costs, class caps and upgraded camp requirement. Redistribution in the panel is free of gem charges and cooldowns.
  Refunds can fill the balance up to the cost of maxing every skill plus one final skill level, within the game’s integer limit. The review shows any excess points that will be discarded. With the 3.57.0 EU catalog, the ceiling is 2,032,300,000 points.
- **Account** edits the local nickname and five-character player tag and keeps the player's guild membership in sync. Enter amounts to add to free gems, paid gems, gold or reserve coffee. Review the resulting balances, then click **Apply** with the game closed and the backend stopped. Free gems, paid gems and gold each have a separate panel limit of 100,000,000. Reserve coffee uses the stamina purchase catalog's storage limit (3,000 in the 3.57.0 pack). Natural coffee recharge continues on its existing timer.
  Under **Summoning**, set **Mileage Ticket**, **Summon Controller** and **Selectable Summon Controller** independently from 0 to 100,000 each, subject to a lower item catalog maximum. The limit applies to the total across all stacks of that item. Editing a different field preserves any existing higher balance.
  Under **Materials**, Jewel Powder, Hero Crystal, Magic Metal, Battle Medal, Sprout Knight Coin, Experience, Dream Myth Stone, Dream Evolution Stone and Star Piece each have an editable row. Expand **Hero Myth Stones**, **Purple Coins**, **Tetis Hero Coins** or **Co-op Expedition Coins** to see one row per hero, world or coin balance. You can keep several groups open, enter the desired **Set total** in each row and review **After applying** before pressing **Apply** once. **Experience** and **Jewel Powder** each accept 0–1,000,000,000. Other materials accept 0–100,000 each. A lower item catalog maximum takes precedence. Existing higher balances are preserved until you edit them. World collectible progress is tracked separately.

You can browse while playing. To save inventory changes, open the standalone
dashboard, close Guardian Tales, stop the game backend, then click **Apply**.
The editor writes directly to your working save without creating a backup.
Restart the game backend and reopen
Guardian Tales to use your changes. **Equipment preview** lets you try changes
to item locks in a temporary copy. **End preview** discards that copy and
returns you to Equipment.

## Practice commands

Under **Game modes → Orbital Lift**, choose the floor you want to play (1–1,500).
The panel shows the highest cleared floor before and after the edit. Choosing
floor 1,341, for example, saves 1,340 as cleared and leaves 1,341 ready to play.
To apply, close the game, stop the backend and use the
[standalone dashboard](http://127.0.0.1:17661/orbital-lift). The selector supports
moving forward and backward. Changing progress grants no floor rewards.

In the same tab, **Enemy levels** sets one visible level for floors 1–1,500 and
their enemies, including elite and boss encounters. The 3.57.0 Global panel
offers levels **1–200**, capped at the highest level represented in the original
Orbital Lift table. With Guardian Tales closed, choose a level and click
**Apply to all floors**, or click **Restore original levels** to recover each
floor's own difficulty. The backend can keep running. Reopen the game to load
the new settings. This edit affects the tables served by the backend and is
independent of the saved floor, enemy lineups and elite modifiers.
Under **Enemy board**, enter any floor from **1 to 1,500** and click **Open floor**.
Click a cell to open the enemy portraits. Search by name or ID, or filter by
element. Click a portrait to add or replace the enemy in that cell. Press
**Escape** to close the picker. To reposition an enemy, drag it to another
cell or choose **Move or swap** and click the destination. **Remove enemy**
clears the selected cell. Click **Save floor** when the formation is ready.
The board mirrors the enemy side in the game with four columns and five rows
of square cells. Occupied cells show their element, and a red crown marks a
boss from the Orbital Lift catalog. Hover over or focus a cell to see its
enemy's name. The header and tile artwork come from the installed resource
pack. The enemy picker uses the same square portraits and corner element icons.

To change one enemy's **Elite modifier**, click its cell, then **Edit elite
modifier**. After placing a new enemy, its modifier selector is already on the
board next to its name and cell number. Choose an effect or **None**, then
click **Save floor**. The editor offers only the effects listed for that enemy
in the installed catalog. In 3.57.0 the original floors use at most one
level-1 effect per enemy: Mortar (Shelling), Stat Up (Enlargement), melee
immunity or ranged immunity. An **Elite** label marks affected cells. Moving
or swapping an enemy carries its modifier. A replacement starts with none.

Leave **Floor enemy level** blank to follow the global setting or the original
floor level. An explicit level (1–200) takes precedence for that floor.
**Save floor** and **Restore original floor** affect only the open board.
**Modified floors** lists every saved floor override in numerical order. Click
a floor number to open its board. Restoring a floor removes it from the list.
The global enemy level appears separately when active.
Close and reopen the game after saving. Opening a floor in the editor leaves
your saved progress intact. The roster comes from the enemies actually used
by the installed mode. The stock formations use five to seven enemies.
Larger or smaller formations, previously unused cells and converting a record
room to a normal encounter by placing enemies there are experimental.

Run selectors against the **same reference directory as the backend**, outside
battle. After changing seasons, variants or Guild War settings, **fully close
and reopen the game** to reload its cached static data. Reconnect alone may
retain the previous selection.

Mode selections are stored with the reference data, separately from the account
database; restoring the save alone does not activate them. Guild War overrides
the guild calendars while enabled. Disable its trial before returning to the
parent Raid/DKA configuration, following the [mode guide](docs/guild-war.md).

Open **Services** on any dashboard page to restart the **Game backend**,
**Content CDN** or **Inventory server** individually. Each button restarts a
running service in its existing terminal on its original ports. After updating
from an older version, relaunch each service once in its usual terminal to
register its button. Reopen Guardian Tales after a game or content update.

The backend panel uses the inventory editor's two-column layout. Raid, DKA,
Guild Wars and Kama-ZONE show the saved selection beside the editor. In
Expedition, select a stage from the table to open its level settings.
Open the [Tetis tab](http://127.0.0.1:17658/tetis) to edit each season's highest
cleared floor. Seasons 2 and 3 also have a shared Guardian Tactic Level for
that season's heroes, total experience and a Season Specialty skill tree.
Use the branch wheel and skill diamonds to edit specialty ranks. You can also
equip a Guardian spell and edit the levels and selection of season artifacts.
Spells and artifacts carry over when playing an archived chapter. Select
**Save changes** and reopen the Tetis lobby. Finish any active Tetis
battle before applying an edit. These changes are saved in the backend's
account database. See the [Tetis guide](docs/tetis.md) for the archived
chapters, floor limits and offline requests.

### Raid and Dungeon Kingdom Arena

With the backend running, open the [Guild Raid panel](http://127.0.0.1:17658/)
on the host PC. View the active lineup, select an original season or configure
four boss/element pairs and the HP per bar. Click **Apply rotation**, then fully
close and reopen the game. The [DKA tab](http://127.0.0.1:17658/dka) lists the three
arena variants and their seven daily slimes. Choose a variant and day, then
click **Apply selection** and reopen the game. Both tabs share selections with
their respective CLI commands below.

For original Raid boss portraits, DKA slimes and elemental icons, install the
optional decoder with `python -m pip install ".[panel-art]"`. The panel reads
the imported Android bosses and UI atlases. Raid uses the monster sprite named
by each boss stage in the local catalog. To set the header icon for both tabs,
place your PNG at `local/panel-art/brand.png`
(alongside the working state directory when using a custom data path).

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

The [Guild Wars tab](http://127.0.0.1:17658/guild-war) shows the saved season-1
settings. Choose a cooperative or fortress phase, set the basic-course option
and, for fortress phases, choose the round and a castle from the deployment.
**Siege attack** and **Castle 21 defense** fill in the practice commands below.
Click **Enable Guild Wars** or **Apply settings** to save. **Disable Guild Wars**
restores the parent calendars. Fully close and reopen the game after saving.

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

The optional [Head Hunter command](docs/head-hunter.md) clones one owned original
into a separate level-150 Myth weapon, with a 25% four-crystal bonus selected only
by that copy. It includes private receipts, backups and targeted removal.

The [Expedition tab](http://127.0.0.1:17658/expedition) and
[enemy-level commands](docs/reference-data.md#per-stage-enemy-levels) list
original and configured enemy levels. Set a single stage or all stages to a
visible level from 1 to 220 in the matching pack, or restore their original
levels. Changes apply through external static overlays and preserve the saved account.

The optional [Kama-ZONE selector](docs/kamazone.md) activates one preserved Global
season's calendar for its Events card. The [Kama-ZONE tab](http://127.0.0.1:17658/kamazone)
lists the same seasons as the CLI. View the current calendar, apply a season or
restore the original calendar. Close the game before applying a change, then
restart the backend and reopen the game.
The three retained difficulties support combat, HP retention and artifact
selection after victories. Confirming a regular floor boss's loot opens the
next floor when the selected difficulty has a matching layout and level row.
Shops sell seasonal artifacts for the challenge's silver coins. Run the CDN with `--reference-dir` to supply an
in-memory preview image when the selected season's historical banner is missing.
Selecting a season automatically unlocks its full menu of benefits and gives
it a 4,000-point budget. Upgrading costs the original prices and removing a
level refunds its cost. Each season keeps its own selections outside the working
account.

Shelters support resting, reviving one hero, purifying one curse and leaving
without an action. See the [complete node coverage](docs/kamazone.md#node-coverage)
for each known node type and the remaining mechanics; APK probes validate
representative flows rather than discovering types one at a time.
Special nodes now draw eligible seasonal events, retain choices and follow
story continuations across visits. Local HP, silver coins and confirmed
artifact/curse gifts are supported; event battles and bottle-cap rewards remain
unavailable.
Finish Challenge can also conclude the separate local run and return to the
idle lobby. Cross-challenge artifact retention and season completion rewards remain unavailable.

The optional [Andras Myth trial](docs/reference-data.md#experimental-andras-myth-view)
projects one owned Andras as an experimental Myth variant using her existing
appearance and combat kit, with Eunha's leader effects, Bianca's leader
cinematic, cast/impact visuals and an activated extra
awakening branch. Enable/disable changes the server's view only;
experimental experience is saved separately, while the stored hero, preserved
resources and APK remain unchanged. Disabling shows her original experience.

## Starting a new account

The local backend supports the main story stage and quest requests. For
stage testing, you can open every world and complete all story quests in a
backed-up local save. See [main story and completed campaign testing](docs/reference-data.md#main-story-and-completed-campaign-testing).
A fresh guest starts with the prologue and can exercise first-time scripts.
The complete campaign has yet to be played through in the APK.

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
