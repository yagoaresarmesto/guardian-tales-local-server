# Project working instructions

- Use English for code, comments, documentation and commit messages.
- Keep this repository updated as the project advances. Finish each verified
  logical change with a focused commit and push to the configured origin, unless
  the user asks to keep that work local or requests a review first.
- Fetch the current remote state before publishing. Preserve other contributors'
  changes and use ordinary fast-forward pushes.
- Update the relevant usage, compatibility or status documentation when behavior
  changes. Separate inferred contracts, automated checks and actual APK results.
- For implementation changes, run the relevant behavioral tests and required
  format/lint checks. For documentation-only changes, check local links and the
  staged diff; additional tests are needed only if behavior is affected.
- Register each new test module exactly once in tests/groups.json. Use
  `python -m guardian_tales validate --list-groups` to inspect available areas.
- Keep game binaries/content, captured bootstrap bodies, credentials, certificate
  keys, account databases and machine-specific lab tools outside the source tree.
- Preserve the saved local account when changing persistence or lab tooling.
- The current compatibility baseline is Android 3.57.0, Google Play, European
  service, with matching external content. Keep backend campaign tests distinct
  from APK playthroughs. All 39 story chapter variants are covered on the host.
  The Inn clear and entry/exit on a completed Normal World 22 save have
  been verified in-game. See the main story section of
  docs/reference-data.md for campaign test-save behavior and coverage.
