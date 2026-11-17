# Development and GitHub preparation

## Run tests

Generate local TLS files once, then run from the repository root:

```sh
python scripts/generate_dev_cert.py
python -m guardian_tales validate
python -m guardian_tales demo
```

The validation runner prints test details on stderr and a JSON result on stdout.
The tests use temporary account state. Set `GT_TEST_TMP` to an existing writable
temporary directory and `GT_CERT_DIR` to a different certificate directory if
needed. No full game content or captured bootstrap data is needed.

## Verify without external networking

Prepare Docker's Python image while networking is available:

```sh
docker pull python:3.11-alpine
```

After generating `local/tls`, these commands run in Bash or PowerShell from the
repository root. They mount source/certificates read-only and give tests writable
temporary space:

```sh
docker run --pull=never --rm --network none --read-only --mount "type=bind,source=${PWD},target=/app,readonly" --tmpfs /tmp:rw --workdir /app -e GT_TEST_TMP=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e GT_EXPECT_NO_NETWORK=1 python:3.11-alpine python -m guardian_tales validate
docker run --pull=never --rm --network none --read-only --mount "type=bind,source=${PWD},target=/app,readonly" --tmpfs /tmp:rw --workdir /app -e GT_TEST_TMP=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e GT_EXPECT_NO_NETWORK=1 python:3.11-alpine python -m guardian_tales demo
```

The `external_network_disabled` field is true only when the expected isolated
environment is requested and only the loopback interface is present. A normal
native test run reports false even though the application makes no outbound
requests. Preparing Docker, Python and CI dependencies is a separate networked step.

## Formatting and lint

Optional development tools are versioned in `pyproject.toml`:

```sh
python -m pip install -e ".[dev]"
python -m black guardian_tales tests scripts
python -m ruff check guardian_tales tests scripts
```

Runtime code uses only the standard library. Keep local paths and client inputs
in command-line arguments or the documented environment variables. Preserve
packet body kinds, transaction semantics and existing database state when
changing handlers. Add behavior tests for new mutations and failure recovery.

## Repository checks and source ZIP

The repository's default branch is `main`. A normal Git clone already has an
index and remote. In an extracted source ZIP, initialize Git first:

```sh
git init -b main
git add .
python scripts/check_repository.py
python scripts/package_source.py
```

The check reads Git's indexed file list, rejects private/runtime artifact paths
and private-key content, and checks local Markdown links. It is a targeted
repository check, not a guarantee that arbitrary files are safe to publish.
The packager includes only indexed source files, excludes runtime artifacts,
verifies the ZIP, and writes a sibling `.zip.sha256` checksum file. It uses current working-tree
bytes for those indexed paths, so stage all intended additions before packaging.

Game bootstrap `.bin` bodies, full catalogs, captured account responses, emulator
credentials, local keys and SQLite saves are external inputs, not source files.
The `.gitignore` also excludes APKs, native libraries, recovered metadata,
generated caches, build output and runtime files under `local/`. The sole tracked
exception is `local/downloads/README.md`, which preserves the content drop folder
in clones and source archives. Repository checks still reject other files under
`local/`, even if force-added.

## Contribute changes on GitHub

The repository is hosted at
[yagoaresarmesto/guardian-tales-local-server](https://github.com/yagoaresarmesto/guardian-tales-local-server).
Create a branch for a focused change, run the checks, and review the staged diff
before committing with your configured Git identity:

```sh
git switch -c describe-your-change
git add .
python scripts/check_repository.py
git diff --cached --stat
git commit -m "Describe the resulting behavior"
git push -u origin describe-your-change
```

Use a fork as your remote if you do not have write access to the repository.

## CI

The workflow runs the regression suite and demo on Linux with Python 3.11 and
3.13, plus formatting/repository checks on Python 3.11. It provisions temporary
TLS files and does not need game data or secrets. The Actions configuration uses
the official [checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) usage. Check the
[hosted workflow runs](https://github.com/yagoaresarmesto/guardian-tales-local-server/actions/workflows/ci.yml)
for the result associated with a particular commit; local verification records
are separate snapshots.

Each job has a ten-minute limit. A newer run cancels an older run of the same
workflow/ref, so obsolete branch runs do not accumulate. Branch and tag refs
remain independent.

Shutdown tests bound the close operation itself. Close accepted clients and
finish their handlers before awaiting a listener's `wait_closed()`:
[Python 3.12 and newer wait for active connections too](https://docs.python.org/3.13/library/asyncio-eventloop.html#asyncio.Server.wait_closed).
Waiting on the listener first deadlocks when a game connection is idle. Timer
regressions accelerate the `wait_for` API rather than patching the event loop's
internal scheduler, which differs across supported Python versions. Reproduce
transport changes on both CI versions; a Python 3.11-only pass is insufficient.
