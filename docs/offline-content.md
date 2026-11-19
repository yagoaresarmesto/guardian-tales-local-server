# Offline content: download, file placement and startup

Use this guide to prepare the server and its local content without contacting
the official game services. The project hosts the preserved content as
[GitHub Release attachments](https://github.com/yagoaresarmesto/guardian-tales-local-server/releases/tag/content-3.57.0-eu-20261117).
An ordinary source clone or GitHub's automatic **Source code (zip)** download
does not include those attachments.

The required game installation is **Guardian Tales 3.57.0 for Android, Google
Play, European service**, package `com.kakaogames.gdts`. Supply your own matching
base APK and required splits. No APK or existing player's account is included.
Other versions and regional clients have not been validated.

This prepares the data and backend. Connecting an unmodified APK still requires
Android hostname routing and TLS trust in a dedicated test environment, as
explained in step 5. An automatic emulator installer is not supplied.

## 1. Get the source and tools

Install **Python 3.11 or newer** and an **OpenSSL CLI** for certificate generation.
Git is needed for the clone command; alternatively extract the source download.
No `pip install` or third-party Python runtime dependencies are required.

```sh
git clone https://github.com/yagoaresarmesto/guardian-tales-local-server.git
cd guardian-tales-local-server
```

Run all following commands from this repository folder. On Windows, use
`py -3.11` instead of `python` if needed. OpenSSL from Git for Windows is detected
automatically. Keep at least **20 GB free on the computer** for the downloads,
imported data and working space, plus separate emulator storage.

## 2. Download all four content files

From the [3.57.0 European content release](https://github.com/yagoaresarmesto/guardian-tales-local-server/releases/tag/content-3.57.0-eu-20261117),
download these four attachments and place them together in the included
[`local/downloads/` folder](../local/downloads/README.md) inside the repository:

```text
guardian-tales-local-server/
  guardian_tales/
  docs/
  local/
    downloads/
      README.md
      content-manifest.json
      gt357-eu-20261116-part01.zip
      gt357-eu-20261116-part02.zip
      gt357-eu-20261116-part03.zip
```

The three ZIPs total **5,049,412,576 bytes** (about 5.05 GB). Download all three;
they are separate containers read by the importer. Keep their original names.
Do not join them or manually extract them. The optional `SHA256SUMS.txt` and
`CONTENT-NOTICE.txt` attachments document checksums and content provenance.

For a computer that will never have Internet access, transfer the source, these
four files, Python/OpenSSL and the matching APK from another machine first.
Importing and serving the content require no GitHub or official-server access.

## 3. Import the files

```sh
python -m guardian_tales content import --manifest local/downloads/content-manifest.json --output local/client-data
```

The importer verifies every release part's SHA-256, expands the initial and
on-demand archives, verifies the resulting files, and writes the CDN allowlist.
Expect several minutes and disk activity. Successful output includes
`"result": "PASS"`, `"resource_files": 15915` and `"reference_files": 19`.

The result is approximately **9.94 GB** and has this layout:

```text
local/
  downloads/                       Downloaded release attachments
  client-data/
    content-manifest.json           Content hashes and compatibility metadata
    import-report.json              Import verification result
    manifest.json                   Resource-server allowlist
    reference/                      Bootstrap responses and gameplay catalogs
      static_data_get.bin
      resource_urls.bin
      ...
    resources/
      files/                        Resource root supplied to the CDN
        master-global-v3.57.0.Android.zip
        Android.index
        AssetBundles/
        GameScript/
        Tilemaps/
        static_data/
        media/
        ...
  tls/                             Certificates generated locally in step 4
  state/                           Your account, created when the backend starts
    server.sqlite3
```

Do not copy the ZIP parts into Android manually. The local CDN serves the
individual files and download archives that the game requests. Do not put
`server.sqlite3` inside `client-data/` or `downloads/`.

The output directory must be new or empty. Existing content or saves are never
overwritten. After a failed import, retain the error message and use a different
empty output directory on retry; do not delete your `local/state/` folder.
To check an existing import later:

```sh
python -m guardian_tales content check --data-dir local/client-data
```

This verifies the imported data, not APK routing or gameplay. Once the import
passes, `downloads/` is not needed at runtime; keep a copy elsewhere for recovery.

## 4. Start the backend and resource server

Generate development TLS files once:

```sh
python scripts/generate_dev_cert.py
```

In the first terminal, start the persistent backend with the imported reference
directory:

```sh
python -m guardian_tales serve --data-dir local/state --cert-dir local/tls --reference-dir local/client-data/reference
```

In a second terminal, from the same repository folder, start the resource CDN:

```sh
python -m guardian_tales assets --resource-root local/client-data/resources/files
```

Both processes must remain running. They wait until **Ctrl+C** by default; there
is no 50-minute timeout. Close the game before stopping them to avoid interrupted
downloads. Restarting with the same `--data-dir local/state` keeps your account.

The backend health endpoint is
[http://127.0.0.1:17657/health](http://127.0.0.1:17657/health).
This resource URL should be downloadable from the same computer:
[http://127.0.0.1:18080/master-global-v3.57.0/Android.index](http://127.0.0.1:18080/master-global-v3.57.0/Android.index).
Use a browser or `curl`; a working health endpoint alone does not test the CDN.

| Service | Computer's loopback address |
|---|---|
| Binary game protocol over TLS | `127.0.0.1:10100` |
| Platform and local guest HTTPS | `127.0.0.1:10500` |
| Backend health | `127.0.0.1:17657` |
| Resource CDN over HTTP | `127.0.0.1:18080` |

These listeners serve a local experiment. They are not configured for public
hosting. See [setup](setup.md) for options and [administration](administration.md)
for controlled local currency changes.

## 5. Connect the Android client

For the supported Windows/MuMu Android 12 experiment, continue with the
[certificate and reversible bridge guide](mumu-client.md). It uses the imported
data and the same host state directory. The [PyCharm walkthrough](pycharm.md)
also records interpreter setup and the fresh-clone checks.

Install your matching APK/splits in a dedicated test emulator. Starting these
two computer processes does not redirect the APK automatically. Its requests to
the European API/auth hostnames must reach ports 10100/10500, its advertised
local CDN must reach 18080, and Android must trust a lab certificate for the
actual game hostnames. Inside Android, `127.0.0.1` means Android itself, so an
explicit bridge or Android-local service is needed.

The certificate from step 4 covers only `localhost` and `127.0.0.1` for backend
probes. It does not establish the game's hostname trust. ADB reverse mappings
alone do not solve hostname routing or trust either. Follow the separate
[client integration requirements and tested MuMu arrangement](client-integration.md#requirements-for-an-apk-experiment).
The earlier prepared laboratory's launcher remains machine-specific. The new
public bridge is a separate experimental implementation; its documented scope
and verification do not imply that every Android environment is supported.

Once that integration is configured, choose **Login as Guest**. The backend
creates a new local guest, not a copy of the developer's account. The game can
request its initial download/tutorial and later additional files from the local
CDN. For a verified offline test, block external traffic in that test environment
while keeping its management channel and local services available. Do not use
your normal online account for the experiment.

## What this release preserves

Content ID: `gt357-eu-20261116`; APK baseline: Android 3.57.0 Google Play Europe.
The pack contains **15,915 resource files** and **19 reference files**, including
the initial archive, 92 on-demand archives, full matching initial static-table
responses, local gameplay catalogs, EN/ES text, preserved media and the Japanese
voice supplement. It includes two newline-only Spanish word-filter files as
explicit local placeholders; they are not recovered official dictionaries.

The prepared clean laboratory passed initial download, guest access, prologue,
additional resource download, and the client's downloaded-file organization
check. The content pack was independently built, imported into a new computer
directory and verified by SHA-256. The imported directory has not yet been used
for a separate end-to-end APK run on another computer.

This is the preserved test snapshot, not a claim that every regional resource
exists: some unselectable regional voices, fonts, illustrations, tilemaps and
movie variants were not available. Only EN/ES interface text was preserved.
Missing original files are not reconstructed by the importer.

Having these resources removes reliance on the official CDN for the covered
content. It does not implement the remaining backend. Prologue and the observed
early campaign paths are supported; later systems and unsupported actions may
still produce a connection error. See [verified scope](status.md).

The source is Apache 2.0. Original game content remains subject to its owners'
rights and is not relicensed by this project. See [content notice](content-notice.md).

## Troubleshooting

| Problem | Action |
|---|---|
| A release part is missing | Put all three ZIP parts next to `content-manifest.json`, with unchanged names |
| SHA-256 verification fails | Re-download the named release part from the same release; do not edit the manifest |
| Output directory is not empty | Choose a new content output folder; retain your separate state folder |
| Download dialog fails or CDN returns 404 | Check both processes, the resource root and import result; the health URL tests only the backend |
| Download fails with Curl error 18 despite HTTP 200 | Reload the current CDN for persistent HTTP/1.1 transfers, then retry; see the [ADB reverse transfer check](mumu-client.md#download-transfers-through-adb-reverse) |
| Clean client cannot load static tables | Use `--reference-dir local/client-data/reference`; the source-only default is not this content directory |
| APK cannot connect but health works | Check the Android bridge, game hostname routing, received TLS certificate and trust |
| Another APK/region requests missing files | Return to the pinned compatible baseline; this pack is not a universal version converter |
| A later game action disconnects | Check the implementation status; available files do not imply an implemented route |

## Maintainers: build a new content pack

The builder takes four mandatory bootstrap response files and the optional
allowlisted catalogs from a reference directory, plus one or more preservation
roots with their manifests. Include a prepared initial ZIP in a root; create
available on-demand ZIPs with [the archive builder](setup.md#build-on-demand-resource-archives)
before packing. All raw members must also be indexed by the source manifests.

```sh
python -m guardian_tales content build --reference-dir local/reference --resource-root local/preserved/resources/files --resource-root local/ondemand-pack/resources/files --output local/new-release --content-id example-snapshot
```

Use a new output directory outside the inputs. The builder reads inputs only,
omits duplicate raw members already carried in nested archives, and splits the
payload into assets below 2 GiB. Its fixed allowlist excludes account templates,
databases, SDK caches, APKs and private keys. Inspect the selected inputs before
publishing; path checks are not a substitute for provenance review. Always
import into a separate directory and verify before publishing a new immutable
release. Keep old manifests with their matching parts and client baseline.
