# Optional Head Hunter Myth copy

The opt-in `head-hunter` command adds a separate, locked **Head Hunter Myth
(6-star) at visible level 150**. It copies the rolls and engraving of one owned,
fully limit-broken and engraved original Head Hunter. The original inventory
row and equipment assignments remain unchanged. Pulling the repository creates
no items. This experiment targets the matching Android 3.57.0 EU content pack.

Only the new copy selects the **25% four-ice-crystal bonus** when equipped by
Andras. The original weapon keeps 20%. This adds five percentage points to that
specific crystal modifier; it does not grant 25% to all damage. The copy reuses
the existing appearance, localized name, weapon skill and shipped combat scripts.
The separate [Andras Myth trial](reference-data.md#experimental-andras-myth-view)
is optional and remains independently switchable.

## Commands

Run these in PowerShell from the repository root. The default directories are
`local/state` and `local/client-data/reference`; use `--data-dir` and
`--reference-dir` when your installation uses others. Install the optional
dependencies once if they are missing:

```powershell
.\.venv\Scripts\python.exe -m pip install ".[hero-trials]"
```

Close Guardian Tales and stop the backend with Ctrl+C before granting or
retiring an item. The backend's state lock rejects concurrent administration.
CDN and bridge can remain running during the offline command. Grant one copy:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales head-hunter grant --operation-id head-hunter-test-01
```

If several original Head Hunters are owned, supply the desired **inventory ID**
with `--source-item-id`. The command requires five limit breaks, valid existing
engraving and no socketed jewels. The matching enhancement/engraving catalogs
and story cap must permit level 150. Its new copy retains those limit breaks and
engraving, receives the level-150 experience threshold and starts locked.
No currency, materials, original weapon or hero development is changed.

Restart the backend with its usual arguments and reopen the game to fetch the
new server tables. Equip the new Myth weapon manually. There is no automatic
equip or change to the saved Andras spec.

List the private grant receipts, including inventory IDs and `present` status:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales head-hunter list
```

To remove only the generated copy, close the game and stop the backend again:

```powershell
.\.venv\Scripts\python.exe -m guardian_tales head-hunter remove --operation-id head-hunter-test-01
```

Removal works while locked and clears ordinary hero slots holding that copy.
Remove its preset/Training Room assignments and socketed jewels first. Later
progress and the original weapon remain intact; the command never restores an
old account database. Restart the backend and game afterward.

Each new grant or removal first creates a coherent SQLite backup plus SHA-256
file inside the selected state directory's `backups` folder. Profile changes
and the private grant receipt commit together. Repeating the same operation ID
and reason returns `already_applied`, including after sale/removal; it never
duplicates or resurrects a weapon. A deliberately additional copy needs a new
operation ID. The registry retains at most 32 receipts. Optional `--reason`
records a private audit note; changing an already-used operation's parameters
is rejected.

## Scope and compatibility

Definitions are generated in backend responses only, with coherent JSON/native
battle-action tables and static check/update checksums. No APK, shipped script,
preserved reference file or original CDN resource is edited. New item spec
9060605 has native Myth rarity 5, a separate exclusive option and an exclusive
weapon number of 2. The client's existing alternate-exclusive-weapon mechanism
selects an Andras override and a role-action alias only for that equipped copy.
Original item/option/action/style records remain intact. Removing the last
owned trial copy restores the exact parent static response, including other
enabled experiments.

The existing optional English Andras title response also includes the new
weapon class's leader-title key. If that private title input is configured,
restart the CDN after updating this code; it generates the English response in
memory, preserving its original file. No new private key or resource input is
required. The title remains unresolved without the existing optional input.

Equipping, clearing, targeted retirement and the backend's unlock/zero-gold sale
routes support the copy. General enhancement, rerolling, new engraving, further
evolution and extraction are outside this experiment. Client sell-button
availability is unverified; the terminal retirement command is the tested undo.
Keep this backend version while a generated copy exists, and retire copies
before using code without their definitions. Account databases, backups,
receipts and generated items remain private.

## Evidence

Native inspection supports the visible-level conversion, Myth and engraving
caps, alternate exclusive hero/style selection, action alias loading and the
existing script's `1 + AddModifierMultiplier` crystal calculation. The original
option stays at 0.20; the separate option uses 0.25 and the same four-crystal
condition. The existing manual actions retain their original parameter option.

Automated tests cover exact grant deltas, backups, retries, allocation, source
ambiguity, owner/content binding, state locking, transaction rollback, equipment,
sale, protected removal, checksum/native table consistency and composition with
Andras Myth and test pins. A coherent copy of the working account and its trial
XP passes grant/equip/original/copy/remove, preserves all original inventory and
52 reference files, restores the exact parent static response, and passes SQLite
integrity with zero diagnostic writes to the source. **The actual APK's weapon
display, combat behavior and measured damage remain pending.**
