# Playing Tetis offline

Open **Book of Contents → Recommended → The Tale of the Tetis Hero Beta** with the local backend, CDN and Android bridge running. Tetis opens from the card without an activation command. On a fresh Tetis save, **Elf of the Abandoned Factory** is already selected. If you open the season picker, its grey **Start** button means you are viewing that chapter. Close the picker and use the first floor on the map to start a battle. Use **Old Season** to switch back to a different unlocked chapter.

## Chapters in Android 3.57.0

The CDN uses the original season images when the resource pack contains them.
With the `panel-art` extra installed, it can also recover the factory, train
and fortress backgrounds from the matching Tetis episode bundles and render
the three English chapter titles on transparent backgrounds. Restart the CDN
in its usual terminal after updating the artwork code.

| Season | Adela Kingdom chapter | Playable floors | Guardian Tactic training |
| --- | --- | --- | --- |
| 1 | Elf of the Abandoned Factory | 1–20 | None |
| 2 | The Train’s Uninvited Passenger | 1–20 in the archive | 31 specialty nodes |
| 3 | The Young Lady of the Fortress City | 1–20 for the story, then up to 1,600 | 38 specialty nodes |

The game opens each new chapter after you clear floor 20 of the preceding one. The current season reuses encounter layouts beyond the authored floors and the client applies its floor scaling. The older chapters use the current Tetis battle system. This build contains three seasons under `roguechess3`. An independent playable version of the original Tetis board has yet to be identified.

## Editing a test save

Open the [Tetis editor](http://127.0.0.1:17658/tetis) and select a season. If you configured a different dashboard port, use **Tetis** in the navigation of that dashboard.

| Control | Effect |
| --- | --- |
| Highest cleared floor | Unlocks the following floor. For example, to play season 3 floor 100, set seasons 1 and 2 to 20 and season 3 to 99. Save each season separately. |
| Guardian Tactic Level | Sets that season’s total XP to the start of the selected level. The level applies to all heroes in that season. |
| Guardian Tactic XP | Sets the exact cumulative XP and updates the displayed level. |
| Season specialties | Use the category wheel to choose a branch. Select a diamond to see its description, prerequisites and rank. Use the plus or minus button to assign points. **Reset** clears the season's draft allocations. **Revert** restores its saved ranks. |
| Guardian spell | Select an available spell to equip it. Select it again to unequip. Some spells require a point in a particular specialty in the current season. |
| Season artifacts | Set an artifact's level and choose **Equip**. Level 0 means unowned. Setting an equipped artifact to 0 also unequips it. |

The game shares the equipped spell and artifact across chapters. The loadout editor always shows the current season's collection, including when you select an archived season. Floors, training XP and specialty ranks belong to the selected season.

Finish or leave the current battle before editing. Click **Save changes**, then leave and reopen the Tetis lobby to load the new values. The editor saves progress in the same local account database as the game. Editing the floor changes access directly. Play a floor normally to earn its first-clear rewards.

Use **Services** in the dashboard header to restart the game backend, content CDN or standalone inventory server individually. Each service restarts in its own terminal on its existing ports. Applying a Tetis progression edit only requires reopening the Tetis lobby.

## Offline requests

The game sends the following requests to the local backend. Paths in the first nine rows are relative to `/rogue-chess3/`.

| Request | What it does |
| --- | --- |
| `enter` | Loads the map, cleared floors, team slots, season training, narratives and remaining sweeps. |
| `start-stage` | Opens a playable floor with the chosen artifact and summoner spell. |
| `end-stage` | Records the result, advances the highest floor on a new clear and grants its configured first-clear rewards. |
| `set-ability` | Validates and saves the current season’s specialty points. |
| `set-artifact-spell` | Saves the selected artifact or summoner spell. |
| `mark-narrative` | Marks an unlocked story record as viewed. |
| `reward-narrative` | Grants the reward for a viewed record and marks it claimed. |
| `sweep/v2` | Uses daily sweeps, spends gems for confirmed extra runs and grants items and training XP from the floor’s reward table. The local implementation selects a season artifact uniformly when the configured artifact drop succeeds. |
| `get-rank` | Returns an empty ranking for this single-player server. |
| `/exchange/rogue-chess` | Converts expired season coins to gold at the rate in the client data. |
| Shared `/preset/` requests | Read, save, select, reorder and delete the eight-hero team rosters used by Tetis. |

Gameplay requests and editor writes share SQLite transactions. Retrying a completed battle or reward request cannot grant its rewards twice.

## Verification

On Android 3.57.0, a player entered the first archived chapter from Recommended, cleared floor 1, and returned to the map. The backend recorded the clear and the following map request. Host tests also exercise current-season floors, failed attempts, repeated reward requests, sweeps, loadout selection, and web edits.
