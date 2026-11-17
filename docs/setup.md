# Setup and usage

## Requirements

- Python 3.11 or newer, including its standard `ssl` and `sqlite3` modules.
- An OpenSSL executable to generate development certificates once.
- Docker only if you want the optional isolated tests.
- A matching APK and compatible resource set for APK integration; the
  [offline content guide](offline-content.md) covers the project's data release.

Commands below run from the repository root. On Windows, `py -3.11` can replace
`python`. No virtual environment or `pip install` is needed to run from source.

## Generate local TLS files

```sh
python scripts/generate_dev_cert.py
```

This writes `local/tls/localhost-cert.pem` and `localhost-key.pem`. The certificate
lasts 30 days and covers `localhost` and `127.0.0.1`. The script does not overwrite
existing files or install trust in an operating system or emulator. To generate
a replacement in another directory:

```sh
python scripts/generate_dev_cert.py --output local/replacement-tls
```

Use `--openssl PATH` if OpenSSL is not found. Client tests require trust in the
certificate they actually receive; see [client integration](client-integration.md)
for the separate APK certificate requirements.

## Run the synthetic demo

```sh
python -m guardian_tales demo
```

The demo starts listeners on unused local ports, exercises TLS, three Pong
responses, local guest identity, an empty profile, and platform HTTPS, then closes
the server and discards its temporary database. Its JSON result should contain
`"result": "PASS"`. It does not open or test an APK.

## Run the persistent backend

```sh
python -m guardian_tales serve
```

Open `http://127.0.0.1:17657/health`. Stop with Ctrl+C. Restarting with the same
`--data-dir` keeps the UUID, prologue selection, inventory, supported rewards and
diagnostic counters. The default state directory is `local/state`.

```sh
python -m guardian_tales serve --data-dir local/my-save --cert-dir local/tls --reference-dir local/reference
```

| Option | Default | Meaning |
|---|---|---|
| `--data-dir` | `local/state` | Writable SQLite account/state directory |
| `--cert-dir` | `local/tls` | TLS certificate and key directory |
| `--reference-dir` | `local/reference` | Optional externally supplied bootstrap data/catalog |
| `--api-port` | `10100` | Binary game TLS listener |
| `--auth-port` | `10500` | Platform HTTPS listener |
| `--status-port` | `17657` | Plain HTTP health listener |
| `--run-seconds` | `0` | Stop automatically after this many seconds; zero waits for Ctrl+C |

`GT_CERT_DIR` and `GT_REFERENCE_DIR` can set the corresponding default directories.
Explicit command-line paths take precedence. All listeners bind to IPv4 loopback;
there is no public-listen option. Platform configuration advertises the default
health/CDN ports; changing the health listener does not rewrite those web URLs.

Back up the state database **after stopping the backend**. To try a separate new
account, use a different data directory. Do not commit or share the database: it
contains the local signing key and guest token as well as game state.

## Grant free gems

Stop the backend and use its existing data directory:

```sh
python -m guardian_tales admin grant-gems 1000000 --data-dir local/state --operation-id gems-million-001 --reason "Local testing"
```

The same operation ID cannot grant twice. Restart and reconnect to refresh the
game's balance. See [administration](administration.md) for history, limits and
the prepared Android laboratory's separate data-directory requirements.

## Serve preserved resources

After importing the project's content release, start the backend with
`--reference-dir local/client-data/reference` and the CDN in a second terminal:

```sh
python -m guardian_tales assets --resource-root local/client-data/resources/files
```

See the [download and import steps](offline-content.md) for exact file placement.
The imported data and writable account directory `local/state` are separate.

For other preservation copies, supply their roots instead:

```sh
python -m guardian_tales assets --resource-root "/preservation/base/resources/files" --resource-root "/preservation/supplement/resources/files"
```

Each root needs the matching `manifest.json` two directories above it. Later
roots override matching paths from earlier roots. Replace the example paths with
your own copies; these files are not in the repository. See the exact
[manifest format](reference-data.md#preservation-manifest).

The CDN listens on `127.0.0.1:18080`. Use `--port`, `--run-seconds`, and optionally
`--journal local/assets.jsonl`. A journal records URL paths and response status,
not request headers, cookies, or query strings. Stop the CDN separately with Ctrl+C.
The backend's platform response advertises port 18080, so keep that port for the
current original-client configuration.

## Build on-demand resource archives

The client can request group ZIPs such as `AssetBundles/Android/ondemand/<group>.zip`
as well as individual bundles. To assemble these archives from your preserved
resources, run this repository script:

```sh
python scripts/build_ondemand_archives.py --resource-root "/preservation/base/resources/files" --resource-root "/preservation/supplement/resources/files" --output local/ondemand-pack
```

The output directory must be new or empty, outside the source resource roots.
Later inputs override earlier matching files. Use repeated `--group NAME` options
to select specific groups; the default builds every available group. ETag files
and paths outside the on-demand subtree are excluded. Sources are read only.

Add `--resource-root local/ondemand-pack/resources/files` to the CDN command
alongside your original resource roots. The output includes its own preservation
manifest. ZIP members are relative to the on-demand directory, including the
group name, as the native extractor expects. This tool packages available files;
it does not retrieve missing resources or establish regional content completeness.

## Optional package installation

```sh
python -m pip install .
gt-local serve
```

Installation needs setuptools for the build but adds no runtime dependencies.
`gt-local` exposes the same commands as `python -m guardian_tales`. Runtime paths
are relative to your working directory, not the installed package directory.

## Troubleshooting

| Symptom | Check |
|---|---|
| Missing certificate file | Run the certificate generator or pass the correct `--cert-dir` |
| Address already in use | Stop the earlier local process or choose another port |
| Certificate verification fails | Check the received issuer, SAN and expiry; use the matching trusted certificate |
| Windows TLS traffic receives a substituted certificate | The prepared lab uses an Android-local backend; the isolated Docker demo can test the code separately |
| Static-data request disconnects | Required bootstrap file is absent; configure `--reference-dir` |
| Resource request returns 404 | Check the root, manifest entry and actual file; manifest membership alone does not create files |
| Inn disconnects during an unsupported action | First-phase entry works; later campaign contracts are still being implemented |
| Daily attendance disconnects on an item reward | Inventory/random-item rewards are not implemented; no claim is recorded |

Run `python -m guardian_tales COMMAND --help` for each command's options.
