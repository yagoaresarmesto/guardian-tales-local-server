# Custom Raid user guide

Use `raid-season custom` to select four fights for local Guild Raid on the
Guardian Tales 3.57.0 client. Run the command in PowerShell from the project
folder. Keep the backend, CDN, and Android bridge running.

## Activate a lineup

This example puts Light Sandmonster in slot 1 and Water Sandmonster in slot 4.
Each line in the list becomes one slot, in order.

```powershell
$raidRefs = 'local/client-data/reference'
$raidLineup = @(
    'sandmonster light',
    'ancient demon fire',
    'viper clan leader dark',
    'sandmonster water'
) -join ', '

.\.venv\Scripts\python.exe -m guardian_tales raid-season custom $raidLineup --reference-dir $raidRefs
```

The command prints the active season ID and all four choices. Fully close and
reopen Guardian Tales, then open Guild Raid from the lobby. To change the
rotation, edit the four lines, run the command again, and reopen the game.
You can leave the backend running between selections.

If Guild War is enabled, disable it to show Raid in the lobby.

```powershell
.\.venv\Scripts\python.exe -m guardian_tales guild-war disable --reference-dir $raidRefs
```

On a fresh checkout, install the optional dependency before using generated
boss variants, including Sandmonster.

```powershell
.\.venv\Scripts\python.exe -m pip install '.[raid-custom]'
```

## Commands and arguments

Put the subcommand after `-m guardian_tales raid-season`.

| Subcommand | Positional argument | What it does |
| --- | --- | --- |
| `custom` | One string with four comma-separated `boss element` pairs | Applies the lineup to the first season in the list and activates it. |
| `list` | None | Lists season IDs. The asterisk marks the selected season, and `* custom` marks an active custom lineup. |
| `set` | A numeric season ID from `list` | Activates the stock rotation for that season. Stock seasons use their original art, which may be absent from the local pack. |

| Option | Example | What it does |
| --- | --- | --- |
| `--reference-dir` | `--reference-dir local/client-data/reference` | Uses the same reference directory as the running backend. Without it, the command reads `GT_REFERENCE_DIR` or falls back to `local/reference`. |
| `-h` or `--help` | `raid-season custom --help` | Shows the arguments for that subcommand. |

The final word in each pair is the element. Boss names and elements are case
insensitive. Each pair must be unique. Repeating a boss with a different
element is allowed, so these are four valid slots.

```powershell
$raidLineup = 'ancient demon basic, ancient demon fire, ancient demon light, ancient demon dark'
.\.venv\Scripts\python.exe -m guardian_tales raid-season custom $raidLineup --reference-dir $raidRefs
```

| Element argument | Client element |
| --- | --- |
| `basic` | Basic |
| `dark` | Dark |
| `earth` | Earth |
| `fire` | Fire |
| `light` | Light |
| `water` | Water |

## Boss names

Every boss below accepts all six elements. The second column shows which
elements already have a Raid entry in the original 3.57.0 tables. Other
elements use an existing matching Raid monster when available or a generated
variant.

| Boss argument | Elements with original Raid entries |
| --- | --- |
| `altered mad panda mk-3` | Basic, Earth |
| `ancient demon` | Basic, Fire, Light |
| `arachne` | Basic, Dark, Earth, Fire, Light, Water |
| `carmen` | Basic, Light, Water |
| `cyborg erina` | Earth, Light, Water |
| `empire knight` | Basic, Dark, Earth |
| `fairy` | Light, Water |
| `founder elphaba` | Basic, Dark |
| `furious desert bull worm` | Earth |
| `furious minotaur` | Basic, Fire |
| `goblin chief` | Earth, Fire |
| `grand admiral marina` | Basic, Water |
| `invader commander` | Basic, Dark |
| `invader director` | Basic, Dark, Earth, Fire, Light, Water |
| `invader terrorist` | Basic, Dark, Earth, Light, Water |
| `lava slime king` | Fire |
| `little jerry volt` | Basic, Dark, Earth, Light, Water |
| `minister duncan` | Basic, Dark, Earth |
| `nine-tailed fox garam` | Fire, Light, Water |
| `returned harvester` | Basic, Light |
| `sandmonster`, `sand monster`, or `sandy` | Earth |
| `shadow beast` | Basic, Dark |
| `snowman general gast` | Earth, Light, Water |
| `viper clan leader` | Dark, Light |

## How it works

The command uses the lowest season ID in the catalog, normally season 1, and
assigns it a local four-slot boss set. It reuses each boss's arena and loads
the requested element through the boss ID for that slot. If the original
banner or background is missing, custom selection uses art available from the
paired local CDN. The client reloads these tables when the game reopens.

The element applies to the main boss. Its arena, attack patterns, and linked
enemies come from the original encounter. Custom Sandmonster uses the stock
Raid v2 equipment and protection, with fixed Attack **2,000** and fixed
Defense **900**. Invader Director already has that setup in all six native
variants.

The first Sandmonster in a custom lineup appears as **Sandy (jailed for your
crimes)**. With multiple Sandmonsters, the later slots also show their element
in the name.

Custom Raid runs as repeatable local practice. The game displays fight
results, and the server returns an empty reward list. The project has checked
preparation for all 144 boss-and-element pairs. Combat on every pair still
needs an in-game test.
See the [reference data notes](reference-data.md#experimental-local-raid-catalog)
for the underlying files and compatibility details.
