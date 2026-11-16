# External reference data and resources

## What the source contains

`guardian_tales/templates/` holds a reconstructed empty local-account template,
empty lobby response shapes, and the small public counter-type mapping needed by
those templates. It contains no saved reference-player inventory or credentials.
An empty announcement list is encoded by the code itself.

Tests include packet/compression regression vectors, a response schema, and a
small explicitly synthetic attendance fixture. Test inputs are not a replacement
for the game content needed by an APK.

## External bootstrap directory

The default external directory is `local/reference/`, ignored by Git. Supply a
compatible set from your own prepared 3.57.0 environment, or pass another folder
with `--reference-dir`. The repository does not retrieve these files.

| Filename | Used for | Stored encoding |
|---|---|---|
| `resource_urls.bin` | `/static-data/resource-url` | Body type 2: raw LZ4 plus trailing decoded length |
| `product_ids.bin` | `/static-data/in-app-product-ids` | Body type 2 |
| `static_data_get.bin` | `/static-data/get` | Body type 2; version/checksum bootstrap body |
| `static_data_check.bin` | `/static-data/check-update` | Body type 1 reference body |
| `attendance_catalog.json` | Daily attendance reward lookup | Parsed public attendance catalog, not account state |

These `.bin` inputs are **response bodies**, not full TLS records, wire frames,
packet headers, APK files, or account responses. Missing files cause a controlled
unsupported-data failure when the corresponding route is requested. They are not
needed for the synthetic demo or the core persistence tests.

An external directory can override a built-in JSON template by filename. Keep
overrides local, compatible and free of official account state.

The attendance reader expects `origin_group`, `active_group`, and `groups`, where
each group maps to rows with `Day` and `Rewards`; a reward has `ItemId` and `Amount`.
`tests/fixtures/reference/attendance_catalog.json` illustrates that structure with
synthetic test rows. It is intentionally not a complete monthly catalog.

## Preservation manifest

Each resource root follows this layout:

```text
preservation-copy/
  manifest.json
  resources/
    files/
      AssetBundles/...
      static_data/...
      GameScript/...
      media/...
```

The resource server reads `manifest.json` two directories above `resources/files`:

```json
{
  "files": [
    {
      "path": "resources/files/media/example.jpg",
      "sha256": "a 64-character SHA-256 hex digest of that file"
    }
  ]
}
```

Paths are relative to the preservation-copy root and use `/`. Only manifest
entries under `resources/files/` that resolve inside the supplied resource root
and exist on disk are indexed. Keep account caches and preferences outside this
content set. The manifest is an allowlist; content hash verification is a separate
preservation task.

Supplements use their own manifests. Pass the base root first, then supplements;
the last matching entry wins. The server keeps the preserved files unchanged.

## Original-client content boundary

The prepared test used the base EN/ES content plus the Japanese voice supplement.
It did not prove every downloaded script, tilemap, language or media item was
complete. Missing resources remain missing; neither this backend nor the CDN
reconstructs or downloads them.
