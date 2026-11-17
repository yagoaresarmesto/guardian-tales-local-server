# Put the offline content downloads here

Download these four attachments from the
[3.57.0 European content release](https://github.com/yagoaresarmesto/guardian-tales-local-server/releases/tag/content-3.57.0-eu-20261117)
and place them together in this folder, keeping their original names:

```text
local/downloads/
  README.md
  content-manifest.json
  gt357-eu-20261116-part01.zip
  gt357-eu-20261116-part02.zip
  gt357-eu-20261116-part03.zip
```

Download all three ZIP parts. Do not join or extract them manually.
From the repository root, run:

```sh
python -m guardian_tales content import --manifest local/downloads/content-manifest.json --output local/client-data
```

On Windows, `py -3.11` can replace `python`. The importer verifies the hashes and
prepares `local/client-data/`. Your account is stored separately in `local/state/`.

Follow the [complete offline setup guide](../../docs/offline-content.md) for
requirements, server/CDN startup and Android connection setup.

This README keeps the folder present in Git clones and source ZIPs. Downloaded
files, imported content and account state stay ignored by Git.
