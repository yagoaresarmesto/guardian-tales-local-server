# Optional Kama-ZONE entry in Events

`kamazone` selects one preserved Global/EU season so the Android 3.57.0 client
can show its card in **Events**. This first milestone covers the menu and a
**read-only idle lobby preview**. Events can select and load a mode automatically
before displaying its drawer, so `/kamazonland/enter` supplies the preview even
without a card tap. Challenges, battles, shops and rewards are not implemented
yet. First verify that Events opens, the card appears and you can return to the
main lobby; do not start a challenge.

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
MENU PREVIEW** image (with the selected ID). The idle lobby may load automatically.
You can inspect the entry and return to the main lobby; do not use challenge,
shop, gift, mission or reward buttons yet.

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

## Read-only automatic entry

The observed entry request is `{"IsPartial":false}`. Both Boolean values are
accepted after local guest sign-in and the prologue, with an active selected
season bound to the matching pack. The response supplies the native
`UserKamazonLand` singleton and `NewSeason:false`. The mini-season ID comes from
the selected season's preserved group rather than being invented.

The preview has no party or run, a concluded floor zero, empty collections,
nonnull progress/likeability objects and zero preview points/tickets/coins.
Those are temporary display defaults, not changes to saved balances or any
historical Kama-ZONE progress. No `User` inventory delta, reward, operation
receipt or database row is created. Missing/ambiguous mini-season data,
disabled/expired selection and a changed content pack are rejected. This route
does not enable any gameplay or reward endpoint.

## Local rankings

`/kamazonland/get-rankings` accepts a native request with no body, JSON null or
an empty object. The signed-in guest, prologue, active selection and content-pack
checks are shared with entry. Its JSON response is `{"Rankings":[]}`, matching
the popup callback's named list. Additional parameters are rejected.

The classification is intentionally empty while there are no local scored runs.
No official rankings are requested, and no players, ranks or scores are invented.
Opening it changes no saved state and sends no account or mode-resource delta.
This read does not enable scored runs or ranking rewards.

## Evidence

Native inspection finds Kama-ZONE in `UIEventDrawer.RefreshEventList`, which
requires `KamazonLand2Data.GetCurrentSeasonByRewardUntil`; its predicate checks
the season's reward-period dates. The card routes through `GoKamazonLandMain`.
The preserved Global calendars have all expired, explaining their absence.
`UIEventDrawer.InitEventScene` can call `GoKamazonLandMain` automatically;
`KamazonLandLobby.Load` sends `/kamazonland/enter` before setting the drawer.
The first APK probe reached that request and exposed the missing read response.
The pending request and a fresh unsupported-operation counter delta confirm it.
The next APK probe reached a successful entry response but stalled while loading.
Android's Unity log identifies `JsonSerializationException` at
`UserKamazonLand.Benefits`: the native `List<KamazonLandBenefit>` requires a JSON
array. Read-only native type registration also identifies `Nodes` as
`List<KamazonLandFloorNode>`. Both empty fields are arrays; `Hps` and the two
progress dictionaries remain objects. A field-signature regression checks every
transmitted singleton field and the nested formation/progress/likeability types.

Automated checks cover Global-only selection, calendar restoration/revisions,
get/check consistency, default compatibility, no database access, source
binding, invalid data, atomic publication, overlapping seasons, expiry,
composition with Andras and scoped CDN preview GET/HEAD/range/ETag responses.
The owner confirms that Events loads Kama-ZONE and can return to the main lobby
on Android 3.57.0 EU with season 43 selected. Fresh counters show three successful
entry reads and no new entry rejection; the declared preview banner is served
by the CDN. This verifies loading and return navigation, not playable challenges,
rewards or season 41/42 in the APK. The same probe exposed a separate unsupported
ranking request; the new local empty response is awaiting its own APK check.

The initial entry change passed 271 targeted Windows tests, including static
overlays, CDN, Backroom and Training Room. A coherent file-backed account/XP copy passes selection of all three
seasons and restoration. It retains every main-account table, trial XP, the
other effective overlays and all 52 original reference files. Each missing
historical banner yields a valid generated preview; the source account and
reference directory receive no diagnostic writes or live selection.
A follow-up coherent copy replays the captured automatic entry and both Boolean
partial flags for all three seasons. It records zero database writes during
entry, retains trial XP and all 53 source reference files including the local
selection, and sends no shared account/inventory delta.
The collection-type correction passes 85 focused tests, Black (221 files), Ruff
and repository/link checks. Its coherent copy also validates every transmitted
field against the read-only native type signatures for both partial flags and
all three seasons, retaining all account/XP tables and 53 source reference files
with zero diagnostic source writes. APK loading and return navigation are now
owner verified for season 43.
The native `SendKamazonLandGetRankings` sender has no payload;
`KamazonLandRankingPopup` reads `Rankings` from the JSON resource and accepts an
empty list. Three new regressions cover its native wire shape, parameter
rejection, selection/authentication guards and unchanged saved state. All 88
focused tests pass with Black/Ruff and repository/link checks. The ranking
popup's actual APK open/close check remains pending.
