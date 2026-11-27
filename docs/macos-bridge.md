# Test a Mac emulator against the local backend

Use this procedure on an Apple Silicon Mac with a dedicated ARM64 Android instance. The Mac adapter connects the instance's loopback ports to the services on your Mac. It checks the installed 3.57.0/431 build and, during a run, verifies the backend's health response from Android. The stock game also needs its fixed service names to resolve locally and trust the server certificate. Stock APK lobby access on macOS remains pending.

## Select the instance

1. In MuMuPlayer Pro, start your test instance. Use **Developer → Open ADB** or **Tools → Open ADB** to find its ADB port. Return to the Mac terminal for the commands below. [MuMu developer tools](https://www.mumuplayer.com/help/mac/developer-support-function.html) · [MuMu ADB menu](https://www.mumuplayer.com/help/mac/connect-adb.html)
2. If using BlueStacks Air instead, select a dedicated instance with ADB enabled if the installed version offers it. Use the local endpoint shown by that version or the device serial listed by your Mac ADB. Support depends on the instance exposing ADB with reverse forwarding and Android's Toybox netcat. [BlueStacks Air support](https://support.bluestacks.com/hc/en-us/categories/32272865984397-BlueStacks-Air-for-Mac)
3. From the repository root, enter the device serial when prompted. For a port shown by MuMu, enter `127.0.0.1:` followed by that port. An existing local `emulator-N` serial from `adb devices -l` is also accepted. The CLI searches PATH, the Android SDK and MuMu's bundled ADB. If needed, append `--adb "/actual/path/to/adb"` to each command. [Google SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)

```zsh
read "GT_SERIAL?Dedicated instance ADB serial: "
./.venv/bin/python -m guardian_tales android-bridge mac check --serial "$GT_SERIAL"
```

Expect **ADB CHECK PASSED** with the Android release and game version. You can run this before starting the host services. If the device is offline or unauthorized, check the emulator's ADB settings and serial.

## Test the connection

Start the backend with your restored state and `local/client-tls`. Start the CDN on host port 18081. Use the same Mac terminal and device serial as above:

```zsh
./.venv/bin/python -m guardian_tales android-bridge mac run --serial "$GT_SERIAL" --cert-dir local/client-tls --cdn-port 18081 --minutes 0.5
```

Expect **LOCAL PORTS READY** after a TLS and CDN check on the host and an HTTP health check from Android. After 30 seconds, expect **LOCAL PORTS INACTIVE**. While active, clients configured for localhost can reach ports 10100, 10500 and 17657 at the same host ports, and port 18080 at the chosen host CDN port. The command requires ordinary ADB access. Android root settings, system trust, DNS and firewall settings stay as configured by the user. The emulator retains its normal network access.

To end a longer session, press **Ctrl+C** before closing the emulator. If the device disconnects or the controller is killed, restart the same instance with the same serial and run:

```zsh
./.venv/bin/python -m guardian_tales android-bridge mac restore --serial "$GT_SERIAL"
```

The recovery record is stored in `local/mac-android-bridge/mac-forward.json`. Use the same session directory if you supplied `--session-dir`. Existing mappings are preserved. Cleanup checks the device identity and each target before removing a mapping.

Automated tests use simulated ADB responses. Physical Apple Silicon testing, including a run on an M4 Pro and BlueStacks Air compatibility, remains pending.
