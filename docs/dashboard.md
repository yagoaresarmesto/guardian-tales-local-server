# Using the local dashboard

The dashboard has two sections, **Inventory** and **Game modes**. Both use the same working save and reference catalogs as the backend. On the default ports, the backend dashboard opens on Raid and the standalone dashboard opens on Equipment. The standalone version stays available when you stop the backend to edit the save. [Backend dashboard](http://127.0.0.1:17658/) · [Standalone dashboard](http://127.0.0.1:17661/) · [First-time setup](../README.md#set-up-an-imported-account)

## Inventory

From the repository root, run the following command with your existing working save and matching content installed.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales inventory-panel --open
```

The defaults are `local/state` for the database and `local/client-data/reference` for the catalog. Use `--data-dir` and `--reference-dir` when your backend uses other paths. Running the command again for the same save and port opens the existing dashboard.

1. Browse your roster or inventory and select a hero, item or balance.
2. Before saving, close Guardian Tales. In the **standalone dashboard**, choose **Services → Game backend → Stop**. Saving becomes available once the backend releases the save.
3. Review the change and confirm it. Inventory edits write directly to the working database. **Equipment preview** is available for trying item locks on a temporary copy. **End preview** discards that copy.
4. Choose **Services → Game backend → Restart**, then reopen the game.

### Heroes

Search the roster by name or ID, or filter by element and **Upgrades available**. Each card shows the hero’s current sprite and stars. The bronze, silver-blue and gold bands distinguish ordinary rarities. Green marks Ascended heroes at five or six stars, red marks regular Myth heroes, and violet identifies collaboration heroes.

- **Add hero** opens the missing-hero catalog. Search by name or catalog ID, select a card and confirm to recruit at level 1 in the original form. Owning any evolution of that hero excludes the entire line. Owning either Knight excludes the other Knight, and owning Fei or Mei excludes the other martial artist. The server repeats these checks when it saves.
- **Apply upgrade** changes the selected progression step. **Max hero** applies every eligible step together, including Ascension or Myth where available. Both respect story progress, the Training Room, the hero’s level cap and its awakening tree. They spend no materials.
- **Hero Reset** previews the selected hero at level 1. It clears limit breaks, blessing and awakening. Unique heroes return to their original rarity. Story and Normal heroes keep ordinary evolutions, with Ascended and Myth forms returning to five stars. Equipment stays assigned. Reset is free and grants no material refund. [Hero Reset rules](reference-data.md#hero-reset)

### Equipment and Relics

| To | In the editor |
| --- | --- |
| Add equipment | Choose **Add equipment**. Filter by type or stars (1★–6★), or search by item, exclusive hero or catalog ID. **Collaboration weapons** includes the collaboration weapons and their linked EU evolutions, including Myth where available. **Add to inventory** creates one unequipped level-1 copy with that variant’s native options. |
| Add a relic | Choose **Add relic**, then pick a Scripture, Grail, Candelabrum or Bell and its stars (1★–5★). The new copy rolls its basic options and sub-options for that variant. |
| Improve options | Choose the effects and values, or use **Max selected** under **Basic options** or **Sub-options**. It raises selected, unlocked values to the native limit for each slot. Review the values, then click **Apply**. |
| Upgrade equipment | Set eligible limit breaks, engrave an exclusive weapon that meets its prerequisites, or tick **Raise to max level**. The preview includes story progress, selected limit breaks and engraving. **Apply** grants the necessary equipment XP and saves the changes for free. Under **Enhance**, you can also edit an owned hammer stack. |
| Lock or unlock copies | Use **Lock** or **Unlock** on one copy. For a batch, use **Select items** and optionally **Select page**. The selection carries across pages and filters. Item protection is separate from option locks. |
| Delete copies | **Delete** lists names, stars and copy IDs for review. You can omit individual copies. Ordinary deletion unequips the selected copies. A protected copy, attached jewel, preset or Training Room assignment blocks the batch. **Force delete** removes protection, clears those assignments and returns socketed jewels to inventory. The batch saves together after confirmation. |

Exclusive weapons show the linked hero’s portrait. The book ribbon reports weapon knowledge and collection completion. The engraving ribbon shows the current bonus, with a rainbow star when it reaches its maximum. In the 3.57.0 EU catalog, a base level of 100 and five limit breaks bring shields and accessories to 115. With eligible engraving, a 5★ weapon reaches 130 and a 6★ weapon reaches 150.

### Merch

The star count shows the current evolution. Merch with an original grade of 1★, 2★ or 3★ keeps its silver, blue or copper stars and matching band through every evolution.

Choose **Add merch**, select a catalog variant and press **Add to inventory** for a level-1 copy at the selected rarity. Select an owned copy and choose **Max merch** to apply its full evolution and level in one step. The inspector shows the maximum for that family. Both actions are free. Equipped and locked copies retain their assignments and protection.

Use **Select items** to mark individual merch copies across pages and filters, or **Select page** to mark a whole page. Choose **Lock**, **Unlock** or **Delete** for the selection. Review the copy IDs before confirming deletion. **Force delete** also clears locks and any preset or Training Room assignments on those copies.

### Account, Consumables and Mastery

- **Account** edits nickname, five-character player tag, gems, gold, reserve coffee and materials. Wallet entries add the amount shown. Material entries use **Set total**. Review **After applying** before saving. Free gems, paid gems and gold each have a panel limit of 100,000,000. Reserve coffee follows the catalog cap (3,000 in the EU pack).
- **Materials** can be searched by material, hero, world or season, including rows in collapsed groups. **Hero Evolution Stones** lists stones used by playable heroes. **Hero Myth Stones** has its own hero selector, and **Purple Coins** has a world selector. Choose the corresponding “All” option to scroll the full group. Pending edits are kept as you switch filters.
- **Summoning and material limits** apply per balance. Mileage Ticket, Summon Controller and Selectable Summon Controller can each be set up to 100,000. Experience and Jewel Powder accept up to 1,000,000,000. Other editable material totals accept up to 100,000, subject to a lower catalog limit.
- **Consumables** changes the quantity on an individual owned stack. Select the item to see its allowed range.
- **Mastery** shows Guardian Mastery skills by class. Review skill costs, bonuses and projected points as you redistribute. The panel enforces camp requirements and class limits. A reset of a fully maxed allocation shows any excess refund before you apply it.

## Game modes

Use the same reference directory for the backend, dashboard and CLI selectors. Apply practice changes outside battle and follow the tab’s restart instructions. Reference overrides survive a save restore. Orbital floor progress and Tetis chapter progress, training and loadouts belong to the account database.

### Raid and Dungeon Kingdom Arena

Click a Raid map marker or encounter card to inspect the boss and element. Choose an original season, or configure four pairs and HP per bar in **Custom lineup**. Expand **Active lineup** to compare the draft and saved rotation. In DKA, choose a variant and day to preview the slime and its weakness. The Space-element opponent is displayed as **Void Slime**. Apply the selection and fully reopen the game.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales raid-season list --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales raid-season set 46 --reference-dir local/client-data/reference
.\.venv\Scripts\python.exe -m guardian_tales dka-season set 1 --day 1 --reference-dir local/client-data/reference
```

The installed catalog determines available Raid seasons. The CLI and dashboard share the same selections. [Custom Raid syntax and catalog](custom-raid.md) · [DKA variants and days](reference-data.md#dungeon-kingdom-arena-practice-selector)

### Guild Wars

Select a phase card to see cooperative or fortress practice. **Siege attack** selects Prep Round with no marked target, which allows entry across the castle map. **Castle 21 defense** selects one locally owned castle for defense practice. Choose the round and castle as needed. Every practice phase skips the basic course automatically. Apply the settings and reopen the game. **Disable Guild Wars** restores the parent Raid and DKA calendars. [Guild War presets, commands and prerequisites](guild-war.md#recommended-siege-practice-command)

### Kama-ZONE

Choose an event season and apply or renew its calendar, or enable **Old Kamazone** for the preserved permanent rotations. Restart the backend and reopen the game after changing editions. Enter through the game’s Events card. Each edition keeps its own practice run and benefits. The mode guide covers regular battles, floor advancement, shops, shelters, events and the limits on rewards. [Season and rotation guide](kamazone.md#web-panel)

### Expedition

Use the Solo Expedition district map to select a gate and browse its stages. Drag or swipe to pan, use **+** to zoom and **Fit map** for the overview. Search the directory by stage name or ID to reach unexplored or event stages. **All stages** changes the full catalog even if you have filtered the list. Set a level (1–220 in the matching pack) or restore the original values. Close the game before editing, then restart the backend and reopen it. Practice entry in the game requires the trial and an unlocked stage. [Solo Expedition setup](reference-data.md#solo-expedition-practice) · [Enemy levels](reference-data.md#per-stage-enemy-levels)

### Orbital Lift

- **Explore the tower.** Scroll the Tetis shaft up from floor 1 to 1,000, or follow the Colony shaft down from 1,001 to 1,500. The arrow keys move one cabin while the tower has focus. **Go to floor** jumps to a number. **Current location** recenters on saved progress.
- **Open a formation.** Click a cabin or press Enter to load its **Enemy board**. The board has four columns and five rows. Click a cell to choose an enemy by portrait, name, ID or element. Drag to reposition, or use **Move or swap**. The crown identifies bosses.
- **Edit difficulty.** Apply a global enemy level, or set **Floor enemy level** for an individual floor. An explicit floor level overrides the global setting. The EU editor supports levels 1–200. A blank floor field follows the global or original level. Select an occupied cell to edit an elite modifier offered for that enemy. Moving an enemy carries its modifier.
- **Save a board.** **Save floor** and **Restore original floor** affect the open floor. **Modified floors** lists saved overrides. Reopen the game to load them. Changing the size of the original formation or putting enemies in a record room is experimental.
- **Set next floor.** Close the game and stop the backend from the standalone dashboard. Setting 1,341 records 1,340 as cleared and leaves 1,341 ready to play. You can move backward or forward without awarding floor rewards. Browsing the tower and choosing a cabin only loads the board. [Orbital battle-result coverage](official-save-experiment.md#orbital-stage-closing-and-victory-progress-without-rewards)

### Tetis

Select one of three chapters to edit its highest cleared floor. Seasons 2 and 3 also support Guardian Tactic Level and XP, the specialty skill tree, Guardian spells and seasonal artifacts. The equipped spell and artifacts carry over when playing an archived chapter. Finish any active battle, save the changes and reopen the Tetis lobby. [Chapter limits, training and loadouts](tetis.md#editing-a-test-save)

## Services and artwork

**Services** controls the game backend, content CDN and inventory server individually. After updating the project, restart the inventory server and reload the dashboard. When upgrading from an older version with no service registration, relaunch each service once in its usual terminal.

**Services** shows the expiration dates for the game backend’s server certificate and its signing CA in your local time zone. Starting or restarting the backend renews the server certificate if it has expired or has less than 48 hours left. When the CA itself expires, generate a new CA and restart the bridge so Android trusts it. [Replace the development CA](mumu-client.md#replace-an-expiring-or-expired-ca)

The panel uses sprites, UI atlases and scenery from your imported game resources. The standalone command installs missing readers with its own Python interpreter. If installation fails, it opens with placeholders and retries on the next launch. To install them explicitly, use the checkout’s virtual environment.

```powershell
.\.venv\Scripts\python.exe -m pip install ".[panel-art]"
```

English equipment names come from the catalog’s English name table. For an older pack, place the matching decoded `cache/strings-bin-enUS` export at `local/client-data/reference/strings-bin-enUS`, then restart the panel. A custom header icon belongs at `local/panel-art/brand.png` or in the artwork directory passed with `--art-dir`.

Browsers reuse artwork for 15 minutes. Rendered sprites and scenes are also cached on disk under the user’s `guardian-tales-local/panel-art` cache and rebuilt when their source bundles change. The dashboard fetches account and editor state fresh. In the Android Book of Contents, the CDN also uses local artwork for Recommended cards when available. [Resource pack contents](offline-content.md#what-this-release-preserves)
