# Contributing

This prototype currently targets one local guest and the 3.57.0 Android client.
Start with [architecture](docs/architecture.md), [status](docs/status.md), and
[development](docs/development.md).

## Keeping the repository current

Publish each verified logical advance with a focused commit and the corresponding
documentation/status updates. Implementation changes should include relevant
behavioral tests; documentation-only changes need link and diff checks. Keep
experimental captures and unfinished local trials outside published source.
Check GitHub Actions for the result of each pushed commit. Preserve the client's
pinned compatibility baseline until another version has been explicitly tested.

Keep changes focused on observed behavior. Distinguish a response shape inferred
from native code, a captured contract, a synthetic test, and behavior actually
accepted by the original client. Do not mark unfinished mutations successful.

For changes to persistence or rewards, preserve existing account state, make
retries safe, and test both successful completion and rejected input. Run the
regression suite, synthetic demo, formatter and linter before submitting changes.

Use English for code, comments, documentation, issues and pull requests.
Report the client version, relevant route, expected/actual behavior and a minimal
sanitized reproduction. Keep account identifiers, provider tokens, certificates,
databases, memory dumps and game files out of issues and pull requests.

Contributions to original project code and documentation use Apache 2.0 as
described in [LICENSE](LICENSE). Externally supplied game content is not part of
the contribution or source package.
