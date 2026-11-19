# Connect a dedicated MuMu test instance

This experimental bridge connects **MuMu Player 12 on Windows, Android 12** to
the backend running on the computer. It supplies temporary hostname routing,
Android certificate trust, ADB reverse mappings and instance network isolation.
It does not modify the APK or copy an existing account into Android.

Use the pinned **3.57.0 Google Play European APK**, including required splits,
and first follow the [content download/import guide](offline-content.md).
Other emulators, Android versions and regions are not supported by this helper.
The bounded setup/cleanup test passed with independent restoration checks.
A fresh APK installation then signed in as a new local guest, downloaded and
extracted the initial content, and completed the prologue through this bridge
using the public Release pack. The selected additional-resource download also
completed after restarting the CDN; its 1,753 installed on-demand files matched
the pack's SHA-256 hashes. Those early transfer cuts were not diagnosed in that
run. A later clean-import reproduction and the CDN adjustment are described below;
gameplay remains subject to the [documented coverage](status.md).

## 1. Prepare the dedicated instance

Create another instance in MuMu's instance manager and name it
`GT357-Install-Test`. Install your matching APK and keep the instance running at
the Android home screen. The bridge requires a non-main instance; it rejects
instance zero and checks the selected name and creation timestamp before ADB
operations.

Find the index by running MuMu's `mumu-cli.exe info --vmindex all` or checking its
instance manager. Examples below use **index 1**; replace it with your actual
index. Python 3.11+, OpenSSL and MuMu's bundled ADB are required. The default CLI
location is under `Program Files/Netease/MuMuPlayerGlobal-12.0/nx_main/`.
Pass `--mumu-cli PATH` to the bridge if your installation uses another location.

Commands run from the repository root. In a PyCharm virtual environment on
Windows, replace `python` with `.\.venv\Scripts\python.exe` if the terminal has
not activated that environment. The [PyCharm walkthrough](pycharm.md) describes
that setup.

## 2. Generate the APK certificate

```sh
python -m guardian_tales client-cert
```

This creates `local/client-tls/`: a private thirty-day development CA, a
seven-day server certificate and key, and the public hashed Android CA file.
The server certificate covers `localhost`, `127.0.0.1`,
`eu-api.live.guardiantales.com` and `eu-auth.live.guardiantales.com`.
The basic quick-start certificate does not cover those game hostnames.

Existing keys are never overwritten. To renew, choose another empty directory
using `--output`, then pass it as `--cert-dir` to both server and bridge. Keep
these files local; only the public CA is sent to Android. This command installs
no certificates in Windows or Android.

## 3. Start the two host services

If a backend is already running, stop it with Ctrl+C before selecting the new
certificate directory. Keep the same state directory to retain your account.

First terminal: **backend**.

```sh
python -m guardian_tales serve --data-dir local/state --cert-dir local/client-tls --reference-dir local/client-data/reference
```

Second terminal: **CDN**.

```sh
python -m guardian_tales assets --resource-root local/client-data/resources/files --port 18080 --journal local/cdn-requests.jsonl
```

Keep both running. Check [backend health](http://127.0.0.1:17657/health).
If another local experiment occupies 18080, use `--port 18081` for this CDN and
`--cdn-port 18081` for the bridge. Android still receives its CDN on 18080.
The bridge verifies the backend's hostname certificates and the CDN before
changing the emulator. It does not turn off TLS verification.
The CDN terminal prints `Local CDN: manifest-listed resource files: ...`.
Its local journal records requested paths, availability and HTTP response codes.

### Download transfers through ADB reverse

Use the current CDN before a large additional-resource download. It serves
HTTP/1.1 with explicit response lengths, supporting persistent connections and
byte ranges. Idle connections have a 30-second socket timeout. Response journal
entries are written after each request, including requests on a reused connection;
query strings, cookies and authentication headers are excluded.

In the clean-import Windows lab, the APK reported Curl error 18 despite HTTP 200
responses. A cached ZIP contained 2,872,320 of the server's 2,873,569 bytes. An
Android curl comparison through a temporary reverse mapping reproduced the same
1,249-byte tail loss with the HTTP/1.0 handler: seven of eight downloads matched.
All eight HTTP/1.1 downloads matched their SHA-256. This is evidence for that
transport case, not a diagnosis of every earlier interrupted download.

After restarting the updated CDN, the owner reported the additional download
finished. A read-only comparison verified all 1,738 selected English-voice
on-demand content files against the local manifests. ZIP staging files and ETag
metadata are counted separately. The owner then completed the downloaded-file
check/organization. All 1,738 content hashes still matched afterward, and the
incomplete ZIP staging file had been removed. Persistent full/HEAD/conditional/range
requests and one-response-per-request journaling have automated regression coverage.

If an already running CDN predates an update, reload that CDN before retrying the
download. The backend and bridge can remain active while an idle CDN is reloaded.

## 4. Run a short routing check, then the play session

In a third terminal (**bridge**), first run a thirty-second session:

```sh
python -m guardian_tales android-bridge run --index 1 --name GT357-Install-Test --minutes 0.5
```

For a CDN on 18081, append `--cdn-port 18081`. Expect `BRIDGE READY`, followed
by `BRIDGE INACTIVE` after the limit and restoration. This first check tests
setup/cleanup; keep the game closed during it. The local session report is
`local/android-bridge/session.json`. A successful cleanup records `active: false`
and an empty `restoration_errors` list.

Then run the regular session:

```sh
python -m guardian_tales android-bridge run --index 1 --name GT357-Install-Test --minutes 500
```

After `BRIDGE READY`, open the game and choose **Login as Guest**. The host
backend creates and retains this installation's own local account. Initial and
additional downloads come from the imported resource set.

Keep all three terminals running if you use the game's downloaded-file
check/organization afterward. That operation also passed in the fresh-install
test; all 1,753 selected on-demand files retained their expected SHA-256 hashes.

The bridge temporarily enables the selected instance's root support, overlays
its hosts/trust files and blocks external IPv4/IPv6 traffic while retaining
loopback and MuMu's ADB management connection. It is limited to MuMu's default
management topology (`10.0.2.2`, Android ADB port 5555).

| Android loopback port | Host loopback port | Purpose |
|---|---|---|
| 10100 | 10100 | Binary game TLS |
| 10500 | 10500 | Platform HTTPS |
| 17657 | 17657 | Local status/web URLs |
| 18080 | `--cdn-port`, default 18080 | Resource HTTP |

## 5. Stop and restore

Press **Ctrl+C in the bridge terminal** before stopping the backend/CDN. The
bridge stops the game, removes its mappings and firewall chains, unmounts its
hosts/trust overlays, checks the original hashes and restores the initial root
setting. The account stays in `local/state/server.sqlite3` on the computer;
game downloads stay in the dedicated Android instance. It does not stop the
host services or close another emulator.

The initial root setting is read from MuMu's `root_permission` configuration.
Availability of `su` to ADB is not used to infer that setting. In the first
short test, root access was already available and remained available afterward;
the original hosts, trust listing, IPv4/IPv6 rules, reverse mappings and staging
directory were independently checked after restoration.

Closing the actual emulator process also ends the bridge. Its transient mounts
and network rules disappear with Android shutdown; the helper restores the root
configuration and records that cleanup happened through shutdown. Minimizing a
window is not shutdown. A normal session ends automatically after 500 minutes.

If the controller was interrupted without finishing cleanup, run:

```sh
python -m guardian_tales android-bridge restore --index 1 --name GT357-Install-Test
```

Use the same session directory. A running bridge owns a local lock; stop it
before invoking a separate restore command. Failed restoration keeps the session
marked active and reports the error. Do not delete its session record to hide
an incomplete cleanup.

If startup reports `A previous bridge needs restoration`, run the restore action
with the same instance index/name and session directory, then repeat the original
`run` command. When Android is running, restoration reconnects ADB using the
selected instance's current loopback port before changing root or cleaning up.
This also handles a restarted ADB daemon that has forgotten its emulator
connection. A failed reconnect leaves the active record available for another
restore attempt. If Android is stopped, the existing shutdown cleanup path
restores its root configuration without connecting ADB. Backend/CDN processes
and the saved account remain separate from bridge restoration.

## Additional download errors

Keep the CDN journal enabled when testing downloads. A missing resource returns
HTTP 404; Unity's `Curl error 18` means the response ended before the advertised
body was complete. HTTP 200 in the journal alone does not prove that the client
received or installed the entire file.

In the fresh-install test, several transfers were truncated and the in-game
retry failed again. While the download was paused at its error prompt, the user
stopped only the CDN with Ctrl+C and reran its command with the same resource
root and port, adding the journal. The next in-game retry installed the remaining
five files. All 1,753 installed on-demand files then matched the public pack's
SHA-256 hashes. The backend, bridge and account stayed in place.

This records a successful recovery, not a permanent correction. The cause of
the transfer cuts is still unresolved. Preserve the journal if the failure
recurs; avoid deleting the account or downloaded content to troubleshoot it.

## TLS inspection on Windows

During the fresh-install test, Norton Web/Mail Shield replaced the development
certificate with its own. The plain HTTP health page worked while the TLS probe
failed. The user temporarily disabled **HTTPS scanning** in Norton; the normal
verified probe then passed TLS 1.3 with three Pong responses, and the received
certificate's SHA-256 matched the generated certificate. The website-exclusion
form rejected `https://localhost`; a working local exclusion was not established.

This is a machine-specific finding, not a requirement to disable antivirus.
If local TLS inspection interferes, resolve it in your environment or use an
Android-local backend as in the earlier prepared lab. This bridge expects a
working, verified host TLS connection. Turning inspection back on can make the
same native-host connection fail again. Restore any temporary protection change
when your test is finished.

The bridge's guard tests and a server health page do not establish a complete
offline game. See [current gameplay coverage](status.md).
