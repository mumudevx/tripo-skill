# Keeping tripo-cli current (K13)

When to read this: phase 0 (session start) when `cli_watch.py check` reports a new version, a changelog gap or a golden drift; and after the first paid run of any step listed in section 5.

## 1. Session start check (spec 15)

```
python3 scripts/cli_watch.py check --update
```

- Runs at most once per day (date in `<skill>/.state.json`); `--force` runs it again. A skipped run prints `{"ok", "skipped": true, "installed", "golden_ok_for", ...}` and needs no CLI at all.
- `--update` runs `tripo update --yes` when `tripo update --check` reports a newer version: the user granted this permanently (spec 15.1). Without `--update` the watcher only looks.
- Output: `installed`, `latest`, `updated`, `update_available`, `from`, `changelog` (`[{"version", "items"}]`, sections newer than the last seen version up to the installed one, oldest first), `changelog_missing`, `changelog_gaps`, `relevant`, `golden` (`{"passed", "failed": [{"name", "diff"}]}`), `golden_ok_for`.
- Exit 0 ok, 4 tripo CLI missing or broken, 5 at least one golden drifted.
- State in `<skill>/.state.json` (git-ignored, read-modify-write, other keys kept): `last_check`, `cli_version`, `golden_ok_for`, and the `projects` list that `lessons.py` uses.

## 2. What to tell the user

Nothing when nothing changed. Otherwise 3 to 5 Turkish lines, only about what affects the skill:

- new version installed (`from` -> `installed`);
- `relevant`: changelog bullets that mention a priced parameter (from `prices.json`) or a keyword: model, default, pbr, texture, rig, decimate, segment, dry-run, estimate, validation, reject, exit, retire, price, credit, face_limit;
- golden drift: which golden commands now behave differently (`golden.failed[].name` with the first diff line);
- `changelog_missing` / `changelog_gaps`: say "changelog eksik" and name the versions (the 0.9.0 package `CHANGELOG.md` lists 0.8.0, 0.8.1 and 0.9.0 only; the GitHub repo `vast-enterprise/Tripo-API-CLI` returned 404 when last checked).

Changelog sources, in order: the installed package's `CHANGELOG.md` (`npm root -g`/tripo-cli, then the package that holds the `tripo` binary), then the GitHub raw `CHANGELOG.md` (no auth; skipped when `CLI_WATCH_OFFLINE=1`). The Tripo API changelog page (`https://developers.tripo3d.ai/en/docs/changelog`) covers API-side changes (models, prices, endpoints) that the CLI changelog does not.

## 3. After a version change or a golden drift

1. Run `lessons.py stale --cli <installed> --model <wire id> ...` with the wire ids the skill uses (generation, texture, rig; see `lessons-system.md` section 6). Lessons tied to the old version become warnings.
2. For each drifted golden, read its diff: a changed default (for example 0.9.0 made `pbr` opt-in), a new rejection, a moved price, a renamed model. Run the same command with `--dry-run --json` to see the new behaviour.
3. Mark the affected part of `references/tripo-cli.md` as "re-verify" in a proposal, not by editing it in place: write `~/Desktop/tripo-skill/docs/proposals/<YYYY-MM-DD>-cli-<version>.md` with the changelog bullets, the golden diffs, and the diff for `references/tripo-cli.md`, `tests/golden_dryruns.json` and, when a price moved, `scripts/data/prices.json` (new `as_of`). The user decides; the commit is the user's (spec 17.3).
4. Until the proposal is applied, plan with the new behaviour shown by the dry-run, not with the reference text. `tripo_plan.py` always validates against the installed CLI, so a rejected step stops there.

## 4. The golden contract (`tests/golden_dryruns.json`)

- About 40 `tripo make` commands with the expected payload, warnings, errors and estimate, recorded on tripo-cli 0.9.0. Entry shape: `{"name", "argv": ["tripo", "make", ...], "expect": {"valid", "payload_subset", "warnings_contains", "errors_contains", "estimate", "warnings_count", "errors_count"}}`.
- The runner appends `--dry-run --json` and nothing else, ever: `argv` must be a `tripo make` command. Placeholders `{png}`, `{png2}`, `{png3}`, `{glb}` and `{task}` become throw-away files and ids. `payload_subset` maps a step name (`text-to-model`, `image-to-model`, `decimate`, `rig`, ...) to a subset of that step's payload.
- A new golden is added only through a proposal, recorded by running the command with `--dry-run --json` on the installed CLI. Never a real run.
- `tests/test_references.py` checks that every fenced `tripo` command in `references/` matches a golden's shape (subcommand, `--model`, `--for`, the set of `-p` keys, the `--then` steps and their argument keys) or carries `<!-- unverified -->`.

## 5. First paid runs: measure and record

These cannot be checked without spending credits. Each one is measured on the first real run of that step (through the lock, with the user's approval of that step), written as a project lesson (`lessons-system.md`), and, when it changes a reference or a price, proposed as a skill patch.

| question | how to measure | where it goes |
|---|---|---|
| import task price (any local file input to `tripo make`) | `credits_breakdown` in the run's JSON, or `tripo usage` | `prices.json` `import`, lesson |
| P-series `detailed`/`extreme` texture price | `credits_consumed` of a P1/P2 run with that quality | `prices.json` |
| P2 `quad=true` surcharge | `credits_consumed` of a P2 quad run | `prices.json` |
| `texture_version=v3.5` surcharge | compare `credits_consumed` with the dry-run estimate | `prices.json`, lesson |
| `delight=true` effect on baked light | `qa.py` `BAKED_LIGHT` and the light-sweep row vs a non-delight control | lesson |
| `face_limit` overshoot on v3.1 without `smart_low_poly` | `glbstat.py` tris vs the requested limit | lesson, `generation-planning.md` table |
| A-pose vs T-pose on rig-check and rig | rig-check verdict and rig quality for both poses | lesson, `rigging.md` |
| `spec` for Godot (`mixamo` assumed) | `godot_place.py rig_accept` + the editor BoneMap (red bones) | lesson, `profile.json` |
| `decimate -> uv` and `rig -> convert` from non-generation task ids | whether the server accepts the chained step | lesson, `tripo-cli.md` |
| retarget clip names, packaging, frame rate | `glbstat.py` `animations` on the first retarget output | lesson, `rigging.md` |
| rig output bone count, influences, scale (v3.0) | `rig_accept`, `qa.py` | lesson |

## 6. Known 0.6.1 -> 0.9.0 changes the references already reflect

- 0.8.0: `generation_credits_estimate` in dry-run JSON (H3.1 and P2 only; `null` for P1, legacy models, imports and chain steps); unknown 3D models rejected; H3.1 the official default; chain preflight before uploads; strict pipes; a successful task whose download fails exits 7.
- 0.8.1: `tripo models` lists the accepted model ids and aliases offline.
- 0.9.0: PBR opt-in (`pbr=false` when omitted); short texture model names (`v3.5`) and rig names (`v3.0`) accepted; `decimate` `smart_uv` needs an explicit `model=v3.0`; `generate_parts` + `smart_low_poly` rejected; v2.5 strips unsupported parameters with warnings; `tripo mcp --toolset full` (the MCP server stays outside the credit lock and is never used by the skill).
