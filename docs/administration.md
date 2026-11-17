# Local currency administration

The administrative CLI adds **free gems** or **active-season Festival points**
to the existing single local account. Each command updates its saved balance,
increments the corresponding revision and writes an audit
receipt in one SQLite transaction. It does not require an APK modification or
external service. After restarting and reconnecting, the game receives the saved
balance through the normal account response.

## Add one million gems

Stop the backend first. Run from the repository root, using the **same data
directory that the backend uses**:

```sh
python -m guardian_tales admin grant-gems 1000000 --data-dir local/state --operation-id gems-million-001 --reason "Local testing"
```

On Windows, `py -3.11` can replace `python`. An installed package also accepts
`gt-local admin grant-gems ...`. Replace `local/state` when the server runs with
a different `--data-dir`. The account must already exist and have completed the
local prologue, or be marked as a validated snapshot import. Imported accounts
do not need a synthetic local prologue-selection row. A missing database causes
an error; this command does not create a player or migrate an account.

For an imported state directory, use that directory explicitly:

```sh
python -m guardian_tales admin grant-gems 1000000 --data-dir local/imported-state --operation-id gems-million-001 --reason "Local testing"
```

This **adds** one million. A balance of 400 becomes 1,000,400. The JSON result
contains `result: "applied"`, the operation ID, amount, previous/new balances,
reason, UTC timestamp and current balance. Restart the backend with its usual
arguments and reconnect the game to refresh the displayed amount.

The earlier Android-hosted emulator laboratory stored its database **inside
Android**. That setup needs the command in the same Android Python environment
against the backend's `/runtime` directory. A Windows-hosted backend instead needs
the command on Windows against its actual `--data-dir`. These are separate saves;
use the location of the backend being tested. The repository does not include
machine-specific emulator launch/root helpers.

## Retry and history

Repeating exactly the same amount, operation ID and reason returns
`result: "already_applied"` and preserves the current balance. It also preserves
gems spent since the original grant. Reusing an ID with a different amount or
reason is rejected. Use a **new operation ID** for an intentional additional grant.
IDs are scoped to the selected database.

```sh
python -m guardian_tales admin gem-history --data-dir local/state --limit 20
```

History is read-only and works while the updated backend runs. It lists the most
recent receipts first. `balance_before` and `balance_after` describe the original
grant; they do not change when gems are spent later. The grant command's separate
`current_balance` field reports the balance at the time of that invocation.

## Persistence and limits

- Amounts must be positive integers. The resulting free-gem balance must fit
  within the command's conservative limit of 2,147,483,647.
- Gem grants change only asset 70003 and `User.Cas`. Paid currency, spending counters,
  inventory, quests, stage progress and reward receipts remain untouched.
- Imported snapshot metadata, startup seeds and current preset/village state are
  preserved. The user revision supports signed-64-bit values; a new grant rejects
  at its ceiling, while an existing receipt can still replay without incrementing.
- A failed balance update or receipt insert rolls back the entire grant.
- The updated backend and grant command hold the same operating-system file
  lock. Grants and a second backend are refused while that state directory is
  owned. Stop any older backend version before the first use after upgrading.
- The `.state.lock` file can remain after shutdown. Its existence does not mean
  the backend is running; the operating-system lock is released when the owner
  exits. Do not delete it to bypass a running owner's lock.
- Receipts are stored in `admin_gem_grants` inside the existing database. They
  contain the operation details, not credentials or a copied player profile.

The CLI is a local administration tool. It does not expose an administrative
network endpoint. The configured local hero-draw route can spend free gems.
Configured Festival point shop exchanges are implemented separately. General
shop purchases, paid events and weapon draws remain unfinished.

Automated checks cover a million-gem grant, persistence, account responses,
retries after spending, conflicting IDs, invalid input, overflow, rollback,
cross-process locking and backend lock release after startup errors. The new
administrative tests pass on Windows and in the isolated Linux suite.

Four additional regressions cover imported CLI grants without a local prologue
row, exact profile/table/source preservation, reopening, replay after spending,
signed-64-bit revisions and ceiling behavior, plus older completed accounts that
have no import-marker table. All 352 tests pass on Python 3.11 and 3.13 with
external networking disabled. No grant was applied to the current imported
experimental account during this implementation check; its APK display remains
pending the owner's command and reconnect.

The prepared laboratory subsequently applied the command to the existing APK
test account on 2026-11-17, changing 400 free gems to **1,000,400**. The audit
receipt persisted, and the rest of the saved profile matched its previous digest
after excluding the gem amount and user revision. The backend then restarted
with the same database. The user then confirmed that the original game displayed
**1,000,400 gems** after entering the saved account.

## Add Festival points to the active season

Stop the backend and use its existing data directory:

```sh
python -m guardian_tales admin grant-festival-points 1000000 --season-id 41 --data-dir local/state --operation-id festival-million-001 --reason "Local testing"
```

The required season must match saved `UserFestivalPass.SeasonId` and be nonzero.
Claim the initial pass reward to initialize the local season first. The command
does not initialize or rotate a season, migrate a profile or create a database.
As with gems, the prepared Android lab needs the command inside Android against
its actual `/runtime` directory while that backend is stopped.

This **adds** points: three become 1,000,003. Only `UserFestivalPass.Point` and
`UserFestivalPass.Cas` change. Gems, other balances, inventory, purchases,
progress and earned reward receipts remain intact. One transaction records the
grant in `admin_festival_point_grants`. The shared state lock, integer balance
limit and rollback rules apply. Replay with the same season, amount, operation
ID and reason preserves later spending; conflicting arguments or another active
season are rejected. IDs are scoped to the grant type and selected database.

```sh
python -m guardian_tales admin festival-point-history --data-dir local/state --limit 20
```

History is read-only and may run while the backend is active. Restart the backend
after a grant and leave/reenter Festival Pass to refresh the displayed balance.
The initial four-point reward's saved receipt now replays against current points
and purchase history, preserving spent or administratively granted balances.
Granting currency does not implement additional reward-delivery types.

Eight administrative tests pass on Windows and in the isolated Linux suite,
plus a pass-claim retry regression and all existing gem tests. The prepared lab
applied one million points to season 41 on 2026-11-17: **3 -> 1,000,003**. A
normalized full-profile digest confirmed that only point amount/pass revision
changed. The user confirmed seeing the million-point balance in the original APK.
