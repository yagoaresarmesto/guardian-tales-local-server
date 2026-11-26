# Regression test groups

The suite uses standard-library `unittest`. Each group has a package under
`tests/`, and [groups.json](groups.json) lists the modules in each package.
CI and local validation run the full suite by default.

Run these commands from the repository root, with the project's Python environment:

```sh
python -m guardian_tales validate --list-groups
python -m guardian_tales validate --group inventory
python -m guardian_tales validate --group teams --group guild
python -m guardian_tales validate
```

`--list-groups` discovers and counts tests without executing them. Repeated
`--group` options select a union, so each selected test runs once in discovery
order. Omit `--group` or use `--group all` to run the full suite sequentially.

| Group | Area |
|---|---|
| [core](core/) | Bootstrap packets, LZ4 and validation-runner checks |
| [account](account/) | Snapshot import, profile reads, portraits, frames, badges, nicknames, Backroom entry and local administration |
| [content](content/) | Content packs, references, archives, static nickname policy and catalog contracts |
| [campaign](campaign/) | Story entry, stage progress/completion and play menus |
| [heroes](heroes/) | Hero experience, evolution, official Myth, individual and auto awakening, limit breaks, free Hero Reset, blessings, equipment, training caps and Training Room slots |
| [inventory](inventory/) | Weapons, relic options and jewel operations |
| [teams](teams/) | Normal parties, presets, Orbital/Raid ordering and compact response payloads |
| [rewards](rewards/) | Missions, challenges, knowledge, passes, temporal events, stamina and attendance |
| [summons](summons/) | Saved wishlists, hero/weapon draws and imported summon state |
| [village](village/) | Harvest, gifts, obstacles, basecamp and guardian mastery |
| [guild](guild/) | Guild reads, Raid, Meteor, Dungeon Kingdom Arena and Guild War |
| [tetis](tetis/) | Offline battles, archived seasons, tactics progression, sweeps and the web editor |
| [orbital](orbital/) | Orbital entry, progress and completion |
| [android](android/) | Temporary Android bridge configuration and restoration |
| [integration](integration/) | Loopback TLS/transport, packet codec and resource serving |

Grouping is by module responsibility. Some modules contain both small contract
tests and integration checks; the labels do not replace their individual test
descriptions. Counts are calculated from discovery rather than pinned in the
catalog. To run just the jewel upgrade tests, use the module's import path:

```sh
python -m unittest tests.inventory.test_jewel_upgrade
```

Prepare loopback TLS certificates for the complete/integration suite as described
in [development](../docs/development.md#run-tests). Tests use synthetic or temporary
state. Group selection does not access the saved game account or live emulator.
The supported validation entry point checks every group against discovered files
and cases before executing a selection. Unknown groups, unassigned/stale files,
undiscovered modules, duplicate module assignments and duplicate test identities
fail rather than silently narrowing coverage.

Shared fixture data lives in [fixtures/](fixtures/). Tests also import Python
helpers from modules such as [test_snapshots.py](account/test_snapshots.py),
[test_village_harvest.py](village/test_village_harvest.py),
[test_guild_raid.py](guild/test_guild_raid.py),
[test_guardian_mastery.py](village/test_guardian_mastery.py) and
[test_preset_edit.py](teams/test_preset_edit.py). The Orbital panel tests use
`prepare_inventory` from [test_inventory_panel.py](inventory/test_inventory_panel.py).

Place each new `test_*.py` module in its group's directory and register its
dotted name (e.g. `inventory.test_jewel_upgrade`) exactly once in `groups.json`.
Imports of shared fixtures do not require assigning their modules to a second
group. Run the relevant groups during iteration and the complete suite before
publishing a verified change.
