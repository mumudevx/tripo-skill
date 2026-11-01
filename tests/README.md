# Tests

Run the whole suite from the repo root (about 4 minutes; Blender and Godot tests skip when the binary is missing):

```
python3 -m unittest
```

## The tripo CLI in tests

`tests/test_plan.py` `DryRunRules` (17 tests, the B10/B17 plan rules) runs the real `tripo make --dry-run --json`
and `tripo models --json`: zero network, zero credits. The CLI comes from `$TRIPO`, else `tripo` on PATH.

- Without it these tests skip, and the run prints one stderr line:
  `17 dry-run rule tests SKIPPED: tripo not on PATH (set TRIPO=<path>)`. A green run with that line did not check the
  plan rules.
- `TRIPO=<path>` points at the binary when it is not on PATH (a Node version manager such as mise often moves it),
  for example `TRIPO=~/.local/share/mise/installs/node/<version>/bin/tripo python3 -m unittest`.
- `REQUIRE_TRIPO=1` turns the skip into a failure. Use it before a merge or a release:
  `REQUIRE_TRIPO=1 TRIPO=<path> python3 -m unittest`.

## Other binaries

- `BLENDER` (default `/opt/homebrew/bin/blender`) and `GODOT` (default the macOS app bundle) pick the binaries; tests
  that need a missing one skip.
- Fixtures are read-only paths in `tests/fixtures.json`; a test whose fixture is missing on this machine skips.

The end-to-end behaviour check (an agent run, 0 credits) is in `tests/e2e/README.md`.
