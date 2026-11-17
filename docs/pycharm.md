# Fresh installation in PyCharm on Windows

This walkthrough uses a new clone and the public Release attachments. Keep the
server's existing implementation limits in mind; this is a setup test.

1. Clone the repository into a new folder under your `PycharmProjects` directory.
   Open that folder in PyCharm. If Git reports an issuer-certificate error on a
   Windows machine using HTTPS inspection, this clone command uses the Windows
   certificate store without disabling TLS verification:

   ```sh
   git -c http.sslBackend=schannel clone https://github.com/yagoaresarmesto/guardian-tales-local-server.git
   ```

   From inside that clone, `git config http.sslBackend schannel` retains that
   choice for its future Git operations. This changes only that repository.

2. In PyCharm's terminal, from the repository root, create the local environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe --version
   ```

3. Open Settings, search for **Python Interpreter**, and choose **Add Interpreter
   > Add Local Interpreter > Select existing**. Select
   `<project>\.venv\Scripts\python.exe`. Apply the setting. The executable is
   an existing interpreter, not a directory in which to generate another one.

4. Download the manifest and all three parts from the content Release into the
   included `local/downloads/` folder, following the
   [exact filenames and import command](offline-content.md#2-download-all-four-content-files).
   Use `.\.venv\Scripts\python.exe` for commands if terminal activation is unclear.
   A successful import reports 15,915 resource files and 19 reference files.

5. For a backend-only check, generate the quick-start certificate and start the
   server/CDN as described in the [content guide](offline-content.md#4-start-the-backend-and-resource-server).
   The health page checks plain HTTP; also run the verified TLS probe:

   ```powershell
   .\.venv\Scripts\python.exe -m guardian_tales probe
   ```

6. To connect the matching APK, follow the [dedicated MuMu client guide](mumu-client.md).
   That step generates a certificate for the game hostnames, restarts the backend
   with it and starts a reversible Android bridge in a third terminal.

The backend saves the account in `local/state/`, imported content lives in
`local/client-data/`, and IDE settings/environment stay in `.idea/` and `.venv/`.
These local runtime files are ignored by Git. No `requirements.txt` installation
is needed for the server: it uses the standard library. Optional development
tools are declared separately in `pyproject.toml`.
