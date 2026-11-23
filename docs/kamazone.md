# Optional Kama-ZONE entry in Events

`kamazone` selects one preserved Global/EU season so the Android 3.57.0 client
can show its card in **Events**. This first milestone covers **menu visibility
only**. Opening the card, entering the mode, challenges, battles, shops and
rewards are not implemented yet. Do not use the card to test gameplay at this
stage; first verify that it appears after reopening the game.

The matching external pack retains three Global/EU event seasons:

| Season ID | Name |
| --- | --- |
| 41 | Valentine Season |
| 42 | Lifeguard Season |
| 43 | Mecha Harpy Scintilla Season |

Four additional records belong to another service and are excluded from this
selector. The older permanent Kama-ZONE data and Tetis/RogueChess are separate
systems. Installing or updating the code alone activates nothing.

## Commands

Run from the repository root in PowerShell. The default reference directory is
`local/client-data/reference`; append `--reference-dir` when using another one.

List the seasons:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone list
```

For a clean client reload, close Guardian Tales and stop the backend with Ctrl+C
before changing the selection. CDN and bridge can remain running. Select one
season, for example the most recent preserved Global season:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone select --season-id 43
```

Start the backend again with the same state, reference and certificate arguments
as usual. The CDN must also use the same reference directory:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales assets --resource-root .\local\client-data\resources\files --port 18081 --journal .\local\cdn-requests.jsonl --reference-dir .\local\client-data\reference
```

After updating the project, restart the CDN with this command too. The bridge can
remain running. Reopen the game and inspect **Events** for the Kama-ZONE card.
When its historical banner is absent, expect a generated **KAMA-ZONE / SEASON 43 /
MENU PREVIEW** image (with the selected ID). Do not open the card yet:
`/kamazonland/enter` is intentionally still unsupported.

Inspect the selection and whether its visibility window is active:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone status
```

To restore the original calendar, close the game and stop the backend, then run:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales kamazone disable
```

Restart the backend and reopen the game afterward. Other enabled experiments
retain their own settings.

## Calendar and preservation

Selection creates a local fourteen-day season window starting at the current
UTC day's midnight, followed by seven days of reward-period visibility. These
are calendar fields for the native menu; this command grants no tickets or
rewards. Selecting the same season during its fourteen-day window is a no-op;
reselecting after that window refreshes the dates. `status` reports the dates and
`menu_active_now`. The server/client clock itself is never changed.

The private `kamazone_selection.json` file is published atomically in the chosen
reference directory and bound to the original static pack's SHA-256. An active
selection rejects a changed content pack until disabled or explicitly selected
again. No account database is opened by the command. Its persistent change is
only the optional selection file; imported progress and trial XP stay intact.

The backend composes the calendar over its other effective static overlays. It
changes the chosen season's Global dates and suppresses any overlapping Global
Kama-ZONE season. Other regions, seasons outside that window and unrelated
events retain their data. Static get/check share the new checksum. Disabling
restores the exact parent calendar content with an advancing revision so the
client can replace cached active dates. A disabled configuration is retained
for that revision history; an installation without a configuration keeps its
original responses byte-for-byte.

The matching pack lacks the three historical Global banner PNGs. With
`--reference-dir`, the CDN can generate an original preview PNG in memory only
for a missing banner URL declared by the selected, currently visible season.
An existing manifest-listed image always takes precedence. Unselected URLs,
disabled configurations and installations without this option retain their
normal manifest behavior. Source binding also applies to the generated preview.
This supplies a recognizable menu image; it does not restore historical artwork.

Preserved reference/resource files, the resource manifest, the APK and shipped
scripts remain unchanged. No banner file is written. Existing Raid, Guild War,
Expedition, Andras and generated-item overlays remain independent.

## Evidence

Native inspection finds Kama-ZONE in `UIEventDrawer.RefreshEventList`, which
requires `KamazonLand2Data.GetCurrentSeasonByRewardUntil`; its predicate checks
the season's reward-period dates. The card routes through `GoKamazonLandMain`.
The preserved Global calendars have all expired, explaining their absence.

Automated checks cover Global-only selection, calendar restoration/revisions,
get/check consistency, default compatibility, no database access, source
binding, invalid data, atomic publication, overlapping seasons, expiry,
composition with Andras and scoped CDN preview GET/HEAD/range/ETag responses.
The actual APK card-visibility check remains pending.
Seeing a card does not establish a playable Kama-ZONE mode.

All 240 targeted Windows tests pass, including existing static-overlay and CDN
tests. A coherent file-backed account/XP copy passes selection of all three
seasons and restoration. It retains every main-account table, trial XP, the
other effective overlays and all 52 original reference files. Each missing
historical banner yields a valid generated preview; the source account and
reference directory receive no diagnostic writes or live selection.
