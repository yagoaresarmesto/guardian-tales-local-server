# Official-account preservation experiment

This research is isolated on `experiment/official-save-import`. It investigates
preserving an owner's existing 3.57.0 European account for this local backend.
**Account import is not implemented yet.** Capturing account data does not show
that this backend can load it or run its unlocked systems.

## Observed sources

A private, read-only observation of the matching Android client captured:

- `/auth/fetch-account`: the seventeen profile sections used by the local account
  model, including the owned inventory, characters and global progress flags.
- `/collection/list-all`: collection, item mastery and their new-entry markers.
- `/preset/get-presets`: the separate party, character-list and other presets.
- `/lobby-village/enter`: the separate village state and associated read response.
- `/pasture/collection-all`: the separate monster collection response.
- `/stage/get-stage-progresses`: nonempty encoded progress for the queried chapter.

These are observations of one owner's session, not a complete server export.
Global stage flags and detailed per-stage progress are different datasets.
Visiting one chapter does not establish preservation of other chapters' detailed
progress. Other systems can require additional reads.

Some subsequent responses contain an empty `User` or another empty profile
section. They are retained separately from the account fetch. Replacing the
complete baseline with such a partial response would lose the captured data;
delta merge behavior must be established before applying updates.

## Private evidence and current checks

The observer reads received application frames without writing into the game or
changing its routing. The owner performs authentication. Request bodies and raw
frames are not persisted. Saved output is limited to recognized account sections
and selected game-state reads; authentication fields are excluded before writing.
The machine-specific observation tools and resulting files stay outside this
repository and are not part of the public installation workflow.

The prepared private capture passed checks for profile-section presence,
consistent account identifiers, unique inventory and character identifiers,
inventory counters, owned party members and resolved equipment references.
Source and prepared-output SHA-256 hashes were recorded privately. These checks
establish integrity of the observed input, not complete game-state preservation
or compatibility with the local mutation handlers.

## Next implementation boundary

An importer must validate the snapshot before writing, target a separate empty
state directory, preserve the captured source and refuse to replace an existing
save. Switching Git branches alone does not separate runtime state.

Before an imported account can be tested, the implementation needs explicit
handling for local sign-in identity, completed-prologue state, separate startup
reads and captured campaign progress. Existing mutation and reward receipts
cannot be inferred merely from an inventory snapshot. Imported progression must
not be reset or awarded again to make an unsupported operation appear to work.

Use synthetic accounts for regression fixtures. Real profiles, captured response
bodies, identifiers, credentials and resource files remain private. The supported
fresh-local-account workflow continues to be described in the
[content guide](offline-content.md) and [verified status](status.md).
