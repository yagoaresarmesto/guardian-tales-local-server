# Local gem administration

The administrative CLI adds **free gems** to the existing single local account.
It updates the saved balance, increments the user revision and writes an audit
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
prologue. A missing database causes an error; this command does not create a
player or migrate an account.

This **adds** one million. A balance of 400 becomes 1,000,400. The JSON result
contains `result: "applied"`, the operation ID, amount, previous/new balances,
reason, UTC timestamp and current balance. Restart the backend with its usual
arguments and reopen the game to refresh the displayed amount.

The prepared emulator laboratory stores its active database **inside Android**.
For that setup, run the command in the same Android Python environment against
the backend's `/runtime` directory after stopping the backend. A Windows folder
with the same name is a different save. The repository does not include the
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
- Only asset 70003 and `User.Cas` change. Paid currency, spending counters,
  inventory, quests, stage progress and reward receipts remain untouched.
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
network endpoint. Having gems does not implement spending routes that are still
missing, such as summons or unimplemented shop operations.

Automated checks cover a million-gem grant, persistence, account responses,
retries after spending, conflicting IDs, invalid input, overflow, rollback,
cross-process locking and backend lock release after startup errors. The new
administrative tests pass on Windows and in the isolated Linux suite. No grant
has been applied to the preserved APK test account during this implementation.
