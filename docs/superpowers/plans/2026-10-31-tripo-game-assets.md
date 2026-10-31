# tripo-game-assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A global Claude Code skill that turns Godot placeholders into game-ready 3D assets through tripo-cli: reviews reference images, plans and prices each paid Tripo step, measures and renders every result in headless Blender, offers free-Blender vs paid-Tripo fixes, places the asset in Godot, and records lessons, with a global hook that sends every paid tripo command through Claude Code's permission window.

**Architecture:** One repo at `~/Desktop/tripo-skill` symlinked to `~/.claude/skills/tripo-game-assets`. A lean `SKILL.md` drives a phase state machine and loads `references/*.md` per phase. Deterministic work lives in zero-install scripts: stdlib Python for CLI/JSON/Godot text work, Blender 5.2's bundled Python (numpy available) for every mesh or pixel operation. Per-project state lives in `<game>/.claude/tripo/`.

**Tech Stack:** Python 3.14 stdlib (`unittest`, no pytest), Blender 5.2.3 LTS headless (`bpy`, `bmesh`, numpy 2.3), Godot 4.x headless, tripo-cli 0.9.0, Claude Code PreToolUse hooks.

**Spec:** `/Users/muhsin/Desktop/tripo-skill/docs/2026-10-31-tripo-game-assets-design.md` (decisions K1–K17, B1–B19). Research it rests on: `/Users/muhsin/Desktop/tripo-skill/_research/`.

## Global Constraints

- Zero install: no pip/npm packages. Stdlib Python for non-Blender scripts; numpy only inside Blender.
- tripo-cli ≥ 0.9.0. Every generation command passes `--model` explicitly; never `-p model=` (B10).
- Never submit a paid Tripo task during build or tests. Allowed: `--dry-run --json`, `--help`, `docs`, `models`, `balance`, `usage`, `whoami`, `doctor`, `task get`, `update --check`.
- One paid step per command; a command holding more than one paid step is refused (B17).
- Never write inside a game project during tests. Tests copy what they need into a temp dir (`tempfile.mkdtemp()` under the scratchpad when available).
- Higgsfield is never referenced in skill files or code (K11). Test fixtures use only direct-Tripo models (K17): no `model_h31*.glb`, no dirs containing `job3d.json`. Reference *images* from those dirs may still be used for preflight tests.
- Every script prints exactly one JSON line on stdout; logs go to stderr. Exit codes: `0` ok, `2` usage, `3` input not found, `4` internal error, `5` check failed (QA/guard style "ran fine, result is negative").
- Blender scripts run via `scripts/bl.py` with `--factory-startup --python-exit-code 4`; they write their JSON to `--out <file>` (Blender's stdout is noisy) and `bl.py` echoes it.
- Tripo normals are never recomputed globally; edits restore custom normals on untouched faces (B7).
- Skill files, scripts, lessons: English. User-facing reports: Turkish (B13).
- No AI attribution in files, commits or docs.
- Commits: local to the `tripo-skill` repo only, no push.

## Review Focus

1. **Command forms the guard must see through:** `rtk tripo …`, `env X=1 tripo …`, `cd dir && tripo …`, `tripo … | jq`, `npx tripo-cli …`, absolute path to the binary. A paid call hidden in any of these must still reach the permission window. → tests in Task 5.
2. **Blender exits 0 on a Python exception:** every Blender script must fail with a non-zero exit and no stale `--out` file. → tests in Task 2.
3. **Non-GLB inputs:** quad and some rig outputs arrive as FBX; QA, normalize and render must accept FBX/OBJ, not just GLB. → tests in Task 7.
4. **Unwelded Tripo meshes:** island/hole/boundary metrics on an unwelded mesh are garbage (every UV seam is a boundary). Weld must run first and be bbox-relative. → tests in Task 7.
5. **Missing or stale project state:** no `profile.json`, a deleted raw GLB, an asset JSON from an older schema, `@last` from another session. Scripts must say what is missing, never silently fall back. → tests in Tasks 11 and 12.

---

## File Structure

```
tripo-skill/
  SKILL.md                         Task 14
  .gitignore                       Task 1
  references/                      Task 13 (tripo-cli.md, generation-planning.md, image-preflight.md,
                                   qa-checklist.md, fix-tradeoffs.md, rigging.md, godot.md,
                                   lessons-system.md, cli-updates.md, profile-schema.md)
  scripts/
    common.py                      Task 1   emit/fail/exit codes, project + profile lookup
    glbstat.py                     Task 1   stdlib GLB/glTF stats
    bl.py                          Task 2   Blender runner
    tripo_plan.py                  Task 4   single-step command builder + dry-run validator + pricing
    cli_watch.py                   Task 6   version check, changelog summary, golden re-run
    hooks/tripo_guard.py           Task 5   PreToolUse credit lock
    data/prices.json               Task 4   dated price table
    data/qa_thresholds.json        Task 7 (initial) / Task 15 (calibrated)
    data/budgets.json              Task 11  default tri budgets per class × platform
    blender/_io.py                 Task 2   import any format, write JSON, fail cleanly
    blender/skill_io.py            Task 2   importable shim for _io.py (import skill_io as sio)
    blender/qa.py                  Task 7
    blender/render_sheet.py        Task 8
    blender/fixkit/normals.py      Task 9   NormalKeeper
    blender/fixkit/ops.py          Task 10  parametric operators
    blender/normalize.py           Task 9
    blender/apply_recipe.py        Task 10
    blender/export.py              Task 10
    preflight_ref.py               Task 3   stdlib driver; pixel work in blender/preflight_img.py
    blender/preflight_img.py       Task 3
    profile.py                     Task 11  detect + init profile.json
    asset_state.py                 Task 11  <game>/.claude/tripo/assets/<id>.json + ledger.jsonl
    log_asset.py                   Task 12  provenance.json + project asset_log row
    godot_place.py                 Task 12  placeholder AABB, .import params, swap diff/apply
    godot/aabb.gd                  Task 12  headless helper: print node global AABB as JSON
    godot/rig_accept.gd            Task 12  headless rig acceptance check
    lessons.py                     Task 12  add / list / promote / mark-stale
  lessons/general.example.md       Task 12
  tests/
    fixtures.json                  Task 1
    golden_dryruns.json            Task 6
    godot_min/                     Task 12  tiny Godot project fixture
    test_*.py                      per task
```

---

### Task 1: Repo scaffold, common helpers, glbstat, fixture registry

**Files:**
- Create: `.gitignore`, `scripts/common.py`, `scripts/glbstat.py`, `tests/fixtures.json`, `tests/test_glbstat.py`, `tests/util.py`

**Interfaces:**
- Produces: `common.emit(obj: dict) -> None` (one JSON line, stdout); `common.fail(code: int, msg: str, **extra) -> NoReturn` (emits `{"ok": false, "error": msg, ...}` then exits `code`); constants `EXIT_OK=0, EXIT_USAGE=2, EXIT_NOT_FOUND=3, EXIT_INTERNAL=4, EXIT_CHECK=5`; `common.find_project_root(start: Path) -> Path | None` (nearest dir with `project.godot`); `common.tripo_dir(project: Path) -> Path` (`<project>/.claude/tripo`).
- Produces: `glbstat.stat(path: Path) -> dict` with keys `format` (`"glb"|"gltf"|"fbx"|"obj"|"unknown"`, from magic bytes, not extension), `tris`, `meshes`, `primitives`, `materials`, `images: [{name, mime, width, height, bytes}]`, `skins`, `joints`, `animations`, `bytes`. Non-glTF formats return `format` and `bytes` only, plus `"note": "use blender/qa.py"`.
- Produces: `tests/util.fixture(name: str) -> Path` reading `tests/fixtures.json`; `tests/util.skip_if_missing(path)`.

- [ ] **Step 1:** `git init` in `~/Desktop/tripo-skill`. `.gitignore`: `lessons/general.md`, `.state.json`, `__pycache__/`, `*.blend1`, `tests/_out/`, `_research/*.glb`.
- [ ] **Step 2:** Write `tests/fixtures.json` with these direct-Tripo entries (absolute paths from `_research/prior-testset.md` §1): `pedal_car_raw` (T2 raw, 12367 tris), `tool_chest_g1` (17430), `tool_chest_g3` (9327), `tool_chest_final`, `pickup_g2` (9625), `crew_rigged` (T5 rigged, 1 skin, 27 joints), `crew_apose_raw` (7884), `jerry_can_g2` (10710, three handles), `jerry_can_g3` (10567), `bicycle_v1` (7990), `bicycle_v2` (10907), `back_panel_v1_12k`, `back_panel_v2_20k` (29943), `top_plate_full` (1,391,172), `top_plate_reduced` (2443), `mailbox_letter_dec2000` (2000), `engine_block_g1` (10274); images `R1`…`R12` from §2 of the same note.
- [ ] **Step 3: Write failing tests** `tests/test_glbstat.py`: `test_pedal_car_tris` (`tris == 12367`, `format == "glb"`), `test_crew_rigged_skin` (`skins == 1`, `joints == 27`, `animations == 0`), `test_tool_chest_g1_tris` (`17430`), `test_fbx_passthrough` (a renamed copy `x.glb` of an FBX in a temp dir → `format == "fbx"`; create the FBX in the test via Blender only if no FBX fixture exists, else skip), `test_missing_file_exit_3` (CLI exit code 3).
- [ ] **Step 4:** Run `python3 -m unittest tests.test_glbstat -v` → FAIL (module missing).
- [ ] **Step 5:** Implement `glbstat.py`: parse GLB header + JSON chunk; tris = Σ primitive index count / 3 (mode 4) or vertex count / 3 when non-indexed; image size from PNG IHDR / JPEG SOF / WebP VP8 headers inside the BIN chunk via bufferViews. CLI: `glbstat.py <file> [--json]`.
- [ ] **Step 6:** Run tests → PASS. **Step 7:** Commit `feat: scaffold, glbstat and fixtures`.

### Task 2: Blender runner and safe IO

**Files:**
- Create: `scripts/bl.py`, `scripts/blender/_io.py`, `tests/test_bl.py`

**Interfaces:**
- Produces: `bl.run(script: str, args: list[str], timeout: int = 600) -> dict` — runs `blender -b --factory-startup --python-exit-code 4 --python scripts/blender/<script> -- --out <tmp.json> <args>`, deletes `<tmp.json>` before the run, raises `BlenderError(code, stderr_tail)` if exit ≠ 0 or the file is missing. CLI: `bl.py <script> -- <args>` echoes the JSON. Blender binary: `$BLENDER` or `blender` on PATH.
- Produces (inside Blender): `_io.args() -> argparse.Namespace` (parses after `--`), `_io.load_model(path) -> list[bpy.types.Object]` (GLB/GLTF/FBX/OBJ by magic bytes; clears the scene first), `_io.write(out: str, obj: dict) -> None`, `_io.main(fn)` (wraps `fn`, on exception writes nothing and `sys.exit(4)`). Blender scripts reach these as `import skill_io as sio` (`import _io` returns CPython's built-in C module). Signatures: `sio.main(fn, configure=None)` where `fn(ns) -> dict` and `configure(parser)` adds options; `sio.load_model` returns every imported object, so callers filter `o.type == "MESH"`; `sio.write` rejects NaN/inf.

- [ ] **Step 1: Failing tests:** `test_roundtrip_json` (a tiny test script returning `{"x": 1}` → `{"x": 1}`), `test_python_error_nonzero` (script raising → `BlenderError` with code 4 and no out file), `test_stale_out_removed` (pre-create the out file, run a raising script → file gone), `test_load_fbx_and_glb` (load `pedal_car_raw` and an FBX made in-test → mesh count ≥ 1).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: blender runner with hard failure`.

### Task 3: Reference image preflight

**Files:**
- Create: `scripts/preflight_ref.py`, `scripts/blender/preflight_img.py`, `tests/test_preflight.py`

**Interfaces:**
- Consumes: `bl.run(script, args) -> dict` from Task 2.
- Produces: `preflight_ref.py <image>... [--views auto|single|sheet] [--bg auto|#RRGGBB]` → `{"ok": true, "views": [{"index", "bbox_px", "width", "height"}], "checks": [{"code", "level": "fail"|"warn"|"info", "message", "evidence"}]}`. Exit `5` when any check is `fail`.
- Check codes (automatic only; the agent-eye checks live in `references/image-preflight.md`): `LOW_RES` (any view's object bbox < 1024 px on its long side → fail; 512-px views produced a jumbled model, R12), `FAKE_FORMAT` (extension ≠ magic bytes → warn), `MULTI_OBJECT` (more connected foreground blobs than declared views → fail, R4), `TWO_ROWS` (view bboxes on > 1 row → warn, R9), `LR_COPY` (left vs right: IoU of silhouettes ≥ 0.97 without mirroring → fail; ≥ 0.97 only after mirroring is the expected case), `BACK_COPY` (front vs back silhouette+pixel similarity ≥ 0.97 un-mirrored → fail, R11), `CHROMA_INSIDE` (background colour found in enclosed interior regions → warn "transparent part shows background", R9), `GROUND_LINE` (horizontal line/slab under all views → warn), `NON_PLAIN_BG` (background variance high → warn).

- [ ] **Step 1: Failing tests:** `test_good_sheets_pass` (R1, R2, R3: no `fail`), `test_multi_object` (R4 → `MULTI_OBJECT` fail), `test_back_copy` (R11 → `BACK_COPY` fail), `test_two_rows_and_chroma` (R9 → `TWO_ROWS` and `CHROMA_INSIDE` warn), `test_low_res` (an R12 512-px view → `LOW_RES` fail), `test_exit_code_on_fail` (R4 → exit 5).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: background = mode colour of the border pixels (or `--bg`); foreground mask by colour distance; blobs via numpy flood labelling (`scipy` absent: implement two-pass union-find on a downscaled ≤ 1024-px mask); views = blobs sorted left→right, row grouping by vertical bbox overlap; similarity on silhouettes resampled to 128×128.
- [ ] **Step 4:** Run → PASS. Thresholds that fail on the fixtures go to `scripts/data/qa_thresholds.json` under `"preflight"`, not hard-coded. **Step 5:** Commit `feat: reference image preflight`.

### Task 4: Single-step planner, dry-run validation, pricing

**Files:**
- Create: `scripts/tripo_plan.py`, `scripts/data/prices.json`, `tests/test_plan.py`

**Interfaces:**
- Produces: `tripo_plan.build(step: dict) -> list[str]` (argv). `step` keys: `kind` (`generate|texture|decimate|uv|segment|smartsegment|complete|convert|rig_check|rig|retarget|image_to_multiview|edit_multiview`), `label` (required, `<asset>-<kind>-vNN`), `input` (`{"images": [paths]} | {"task": "<task_id|@label>"} | {"file": path}`), `model` (required for `generate`, `decimate`, `rig`, `texture`), `params` (dict → `-p k=v`), `name` override.
- Produces: `tripo_plan.check(step: dict) -> dict` → `{"argv", "dry_run": <CLI JSON or null>, "estimate": {"credits": int|null, "source": "dry-run"|"table"|"none"}, "warnings": [...], "errors": [...], "paid": bool}`. Exit 5 if `errors`.
- Rules enforced by `check` (each is a test): payload `model` equals the requested wire id (alias → wire via `tripo models --json`); `-p model=` in params → error; `generate_parts=true` forces `texture=false, pbr=false` explicitly and errors with `smart_low_poly=true`; `quad=true` then a later step requesting GLB/GLTF → error (cross-step check uses the asset state chain passed as `--chain <asset.json>`); `rig_type` ∈ {biped, quadruped, hexapod, octopod, avian, serpentine, aquatic, others}; `spec` ∈ {tripo, mixamo, actorcore, unity, unreal, vrm} and only with `biped`; `orientation`, `export_orientation`, `auto_size` in a generate step → warning "set locally instead" and removed; `-n` > 1 → error (one paid task per approval); `rig_check` is the only kind with `paid: false`.
- Dry-run: steps with a task/@label input are validated through `tripo make <input> --then <single step> --dry-run --json` (direct `generate/model/mesh/anim` have no dry-run); the emitted argv for execution is that same single-step `make` form.
- Pricing: `generation_credits_estimate` from the dry-run when non-null; else `prices.json` (dated `"as_of": "2026-10-31"`, values from `_research/tripo-generation.md` §2 and `tripo-processing.md` §0.4: H text 10/20, image/multiview 20/30, add-ons detailed +10, extreme +20, geometry detailed +20, quad +5, smart_low_poly +10, generate_parts +20; P1 text 30/40, image 40/50; P2 100/110; texture 10/10/20/30; convert 5 basic / 10 advanced; decimate v1 10, v2 30, v3 35 tri / 40 quad; uv 20; segment 40; complete 50; smartsegment 55 model / 85 image; rig_check 0; rig 25; retarget 10 per animation; image_to_multiview 10; edit_multiview 5 per view; import `null`). Unknown → `credits: null`, never 0.

- [ ] **Step 1: Failing tests** (all dry-run, 0 credits): `test_delight_generate` (images=[patina mailbox `front.png`], model `tripo-v3.1`, params `texture_version=v3.5, delight=true, texture_quality=detailed` → no errors, payload `model == "v3.1-20260211"`, `pbr is False`, estimate `{"credits": 40, "source": "dry-run"}`); `test_parts_forces_texture_off`; `test_parts_with_slp_errors`; `test_model_param_rejected`; `test_multi_candidate_rejected`; `test_quad_then_glb_errors`; `test_rig_spec_needs_biped`; `test_decimate_price_from_table` (model v3.0 → 35, source `table`); `test_import_price_unknown` (`{"file": x.glb}` rig → `credits: null`); `test_rig_check_free` (`paid: false`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: single-step tripo planner`.

### Task 5: Credit lock hook

**Files:**
- Create: `scripts/hooks/tripo_guard.py`, `tests/test_guard.py`

**Interfaces:**
- Consumes: `tripo_plan` pricing table (`scripts/data/prices.json`) and its dry-run helper for `make` commands.
- Produces: hook reading Claude Code PreToolUse JSON on stdin (`tool_name`, `tool_input.command`). Output on stdout:
  - not a tripo command, or a free one → exit 0, no output (let other hooks/permissions decide);
  - paid single step → `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "<TR text: adım, tahmini kredi or 'tahmin yok', bakiye, label>"}}`;
  - more than one paid step in one command (several `--then` paid steps, or two paid tripo calls joined by `&&`/`;`/`|`) → `permissionDecision: "deny"` with reason "Her ücretli adım ayrı komut olmalı (B17)".
- Classification: tokenise with `shlex`; split on `&&`, `||`, `;`, `|`; strip leading `env VAR=…`, `rtk`, `npx tripo-cli`/`npx -y tripo-cli`, absolute paths ending in `/tripo`. Free: `--dry-run`, `--help`/`-h`, `docs`, `models`, `balance`, `usage`, `whoami`, `doctor`, `history`, `view`, `config`, `update`, `completion`, `login`, `logout`, `use`, `task get|list|watch`, `files upload`, `mcp` (server start). Paid: `make` (without `--dry-run`; `--then` steps other than `rig-check` each count), `generate *`, `redo`, `model *`, `mesh *`, `anim rig|retarget`, `batch run`, `ai` (plans then runs). `anim check` is free.
- Balance in the reason: `tripo balance --json` with a 5 s timeout; on failure write "bakiye okunamadı".
- Estimate for `make`: run the same argv + `--dry-run --json` (timeout 20 s); others from the price table; none → "tahmin yok".

- [ ] **Step 1: Failing tests** (pure classification; dry-run and balance calls mocked through an env var `TRIPO_GUARD_OFFLINE=1`): `test_free_commands_silent` (each free form → no stdout), `test_paid_make_asks`, `test_rtk_prefix`, `test_env_prefix`, `test_cd_and_chain` (`cd a && tripo make x.png --model tripo-v3.1` → ask), `test_pipe_two_paid_denied` (`tripo make a.png --json | tripo anim rig --json` → deny), `test_then_two_paid_denied` (`--then texture,rig` → deny), `test_then_rig_check_plus_one_paid_asks` (`--then rig-check,rig` → ask), `test_redo_asks`, `test_npx_form`, `test_non_tripo_silent` (`echo tripo make` inside quotes → silent: only argv[0]-position tokens count), `test_reason_contains_estimate_and_balance`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: credit lock hook` (installation happens in Task 16).

### Task 6: CLI version watch and golden dry-runs

**Files:**
- Create: `scripts/cli_watch.py`, `tests/golden_dryruns.json`, `tests/test_cli_watch.py`

**Interfaces:**
- Produces: `cli_watch.py check [--update] [--force]` → `{"installed", "latest", "updated": bool, "changelog": [{"version", "items": [str]}], "relevant": [str], "golden": {"passed", "failed": [{"name", "diff"}]}, "skipped": bool}`. Runs at most once per day unless `--force` (state in `<skill>/.state.json`: `{"last_check", "cli_version", "golden_ok_for"}`).
- Changelog sources in order: installed package `CHANGELOG.md` (path from `npm root -g`/`tripo-cli/CHANGELOG.md`), then GitHub `vast-enterprise/Tripo-API-CLI` raw `CHANGELOG.md` via `curl -fsSL` (no auth), then report `"changelog_missing": true` for versions not found (0.7.x is missing locally today).
- `relevant`: changelog bullets matching any of: parameter names in `prices.json`, `model`, `default`, `pbr`, `texture`, `rig`, `decimate`, `segment`, `dry-run`, `estimate`, `validation`, `reject`, `exit`, `retire`, `price`, `credit`. The skill turns these into a 3–5 line Turkish summary.
- Golden file format: `[{"name", "argv": [...], "expect": {"valid": bool, "payload_subset": {...}, "warnings_contains": [str], "errors_contains": [str], "estimate": int|null}}]`. 25–40 entries drawn from the commands marked verified in `_research/tripo-*.md` §"Verified via dry-run", re-recorded on 0.9.0. Mandatory entries: the Task 4 delight case; `face_limit=8000` without `--model` (records whether the CLI still auto-selects P1 and strips params); `generate_parts` + `smart_low_poly` (error); `decimate --smart-uv` without `--model v3.0` (0.9.0 behaviour); `pbr` omitted → `false`; `rig` with `spec=unity` on v3.0; `quad=true` + `convert:gltf`.

- [ ] **Step 1: Failing tests:** `test_changelog_slice` (fixture changelog text → sections strictly newer than `0.6.1` up to `0.9.0`, in order), `test_relevant_filter` (the 0.9.0 PBR bullet is relevant; the MCP analytics bullet is not), `test_daily_skip` (state with today's date → `skipped: true`), `test_goldens_pass_on_installed` (runs every golden against the installed CLI; all pass).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Record goldens by running each argv on 0.9.0 and writing the observed values; implement `cli_watch.py`. **Step 4:** Run → PASS. **Step 5:** Commit `feat: cli version watch and golden dry-runs`.

### Task 7: QA metrics

**Files:**
- Create: `scripts/blender/qa.py`, `scripts/data/qa_thresholds.json`, `tests/test_qa.py`

**Interfaces:**
- Consumes: `skill_io.load_model` (`import skill_io as sio`), `bl.run`.
- Produces: `bl.py qa.py -- <model> [--budget N] [--symmetric x|none] [--ref-palette <png>] [--class <class>] [--thresholds <json>]` → report `{"schema": "qa/1", "file", "format", "metrics": {...}, "findings": [...]}`.
- `metrics`: `tris`, `verts`, `verts_welded`, `meshes`, `materials`, `images: [{name, w, h}]`, `bbox: {min, max, size}`, `weld_eps` (= `1e-5 × bbox diagonal`), `boundary_edges`, `nonmanifold_edges`, `islands: [{tris, bbox_pct}]` (largest first, after weld), `flipped_pct`, `sliver_pct` (triangles with min angle < 5°), `ground: {min_z, low_band_tris_pct, slab}` (`slab`: a thin connected sheet within the bottom 3 % of height spanning ≥ 60 % of the footprint), `asymmetry: {axis, mean_dist_pct}` (mean nearest-surface distance of mirrored vertices over bbox diagonal, KD-free grid hash), `back_relief` (front vs back depth-map similarity along the declared front axis, 0–1), `uv: {overlap_pct, oob_pct}`, `texel_density` (px/m, median), `palette: {delta_e_mean}` (when `--ref-palette`), `baked_light: {score}` (albedo luminance gradient correlation with up-axis normal), `skin: {joints, max_influences}`.
- `findings[]`: `{"id": "F1", "code", "severity": "S0"|"S1"|"S2"|"info", "message", "value", "threshold", "fix_options": [op codes]}`. Codes: `OVER_BUDGET` (S1 when > 1.10 × budget, S0 when > 2 ×), `NON_MANIFOLD`, `HOLES`, `LOOSE_PARTS`, `FLIPPED_NORMALS`, `SLIVERS`, `GROUND_SLAB`, `NOT_GROUNDED`, `ASYMMETRY`, `BACK_COPY`, `UV_OVERLAP`, `LOW_TEXEL`, `PALETTE_DRIFT`, `BAKED_LIGHT`, `TOO_MANY_INFLUENCES` (> 4), `MULTI_MATERIAL`, `TEXTURE_OVERSIZE`. Thresholds read from `qa_thresholds.json`; metrics without a calibrated threshold emit `info` only (spec §12).

- [ ] **Step 1: Failing tests:** `test_budget_overshoot` (`tool_chest_g1`, `--budget 8000` → `OVER_BUDGET` S0), `test_pedal_car_budget` (`pedal_car_raw`, `--budget 10000` → S1), `test_weld_first` (`pedal_car_raw`: `boundary_edges` after weld < 5 % of the unwelded count), `test_asymmetry_tool_chest` (`tool_chest_g1 --symmetric x` → `ASYMMETRY`; `tool_chest_final` → none), `test_slivers_bicycle` (`bicycle_v1.sliver_pct > bicycle_v2.sliver_pct`), `test_influences` (`crew_rigged` → `skin.max_influences ≤ 4`, no finding), `test_fbx_input` (FBX copy of `jerry_can_g3` → same `tris` as GLB ± 0), `test_schema` (keys above present).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with bmesh + numpy; weld on a copy, never on the loaded data used for normals. **Step 4:** Run → PASS. **Step 5:** Commit `feat: blender qa metrics`.

### Task 8: Render sheet

**Files:**
- Create: `scripts/blender/render_sheet.py`, `tests/test_render.py`

**Interfaces:**
- Produces: `bl.py render_sheet.py -- <model> --png <out.png> [--front +x|-x|+y|-y] [--game-cam "<yaw>,<pitch>,<fov>"] [--light-sweep]` → `{"png", "width", "height", "panels": [{"name", "pass", "view"}]}`.
- Layout: rows = passes `lit` (studio light, normal maps on), `lit_no_normalmap`, `albedo` (emission-only), `wire` (wireframe over flat grey); columns = views `front, back, left, right, top, iso` plus `game_cam` when given. Overlay: front-axis arrow, 1 m grid on the ground, tri count label. Long side ≤ 1500 px. EEVEE Next; Workbench fallback for `wire`.
- `--light-sweep` adds one row of 4 lit renders with the key light at 0/90/180/270°.

- [ ] **Step 1: Failing tests:** `test_sheet_size` (`jerry_can_g3` → png exists, max(width, height) ≤ 1500), `test_panels_complete` (24 panels for 4 passes × 6 views; 28 with `--game-cam`), `test_bad_input_fails` (missing file → exit 3, no png).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; open one sheet and look at it (the agent must be able to read it). **Step 5:** Commit `feat: qa render sheet`.

### Task 9: NormalKeeper and normalize

**Files:**
- Create: `scripts/blender/fixkit/__init__.py`, `scripts/blender/fixkit/normals.py`, `scripts/blender/normalize.py`, `tests/test_normalize.py`

**Interfaces:**
- Produces: `normals.NormalKeeper(obj)` context manager: on enter stores custom split normals keyed by triangle (sorted welded vertex positions rounded to `weld_eps`); on exit re-applies stored normals to triangles whose key still exists and writes analytic flat/smooth-by-angle (30°) normals only on new or changed triangles. One implementation; replaces both prior mechanisms (`keep_normals.py`, `fix_common.save_keeping`).
- Produces: `bl.py normalize.py -- <in> --out-model <out.glb> [--yaw DEG] [--target-size X,Y,Z | --target-height H] [--pivot bottom_center|center] [--name <asset>]` → `{"out_model", "bbox", "scale_applied", "yaw", "pivot", "renamed": {...}}`. Order: weld (bbox-relative eps) → yaw → uniform scale to fit target (largest axis ratio, never non-uniform) → pivot → apply transforms → rename root/mesh/material/image to `<asset>` → export. All inside `NormalKeeper`.

- [ ] **Step 1: Failing tests:** `test_target_height` (`jerry_can_g3 --target-height 0.5` → bbox z = 0.5 ± 0.5 %), `test_pivot_bottom_center` (min z = 0 ± 1e-4, x/y centre = 0 ± 1e-4), `test_yaw_90` (bbox x/y swap within 1 %), `test_normals_preserved` (angle between input and output custom normals on untouched triangles: max < 0.5°), `test_names` (`--name jerry_can` → root, mesh, material and first image named `jerry_can*`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: normal keeper and normalize`.

### Task 10: Fix operators, recipes, export package

**Files:**
- Create: `scripts/blender/fixkit/ops.py`, `scripts/blender/apply_recipe.py`, `scripts/blender/export.py`, `tests/test_fixkit.py`

**Interfaces:**
- Consumes: `NormalKeeper`, `normalize` behaviour (a recipe's first step may be `normalize`).
- Produces: recipe file `{"schema": "recipe/1", "asset", "source": "<raw model path>", "steps": [{"op", "params"}]}`; all lengths/regions in params are fractions of the bbox (`box: [x0,y0,z0,x1,y1,z1]` in 0–1 bbox space), never metres.
- Produces ops (first set; each a function `op(ctx, **params) -> dict` registered in `OPS`): `normalize` (Task 9 params), `weld_boundary(eps_pct)`, `remove_loose(min_tris_pct)` (refuses to run before weld), `remove_ground_slab(max_height_pct=3)`, `delete_region(box)`, `fill_holes(max_edges)` (loop walker; does not use `bmesh.ops.holes_fill`), `mirror_half(axis, keep: "+"|"-")`, `flatten_region(box, axis)` (press back relief flat), `clone_part(src_box, dst_offsets)` (copy one clean wheel onto others), `hard_edges(angle=30)` (per edge, sets sharp + split normals), `separate_parts(by: "loose"|"material")` (sets per-part pivot to part bbox bottom centre, names `<asset>_part_NN`), `recolour(hsv_shift | ref_palette)` (texture pixels via numpy, saturation restore against reference).
- Produces: `bl.py apply_recipe.py -- <recipe.json> --work <dir>` → writes `<dir>/vNN.blend` and `<dir>/vNN.glb`, returns `{"version", "blend", "glb", "steps": [{"op", "result"}]}`; re-running on the same raw gives identical tri counts.
- Produces: `bl.py export.py -- <vNN.blend> --out-model <file.glb> [--engine godot]` (Godot adapter: GLB, `+Y` up, images as PNG/JPEG unchanged, Triangulate applied last) and writes `<dir>/export.sh` (one-command re-export, B12).

- [ ] **Step 1: Failing tests:** `test_mirror_half_fixes_asymmetry` (`tool_chest_g3` recipe `[normalize{name}, mirror_half{axis:x, keep:"+"}]` → QA `asymmetry.mean_dist_pct` drops below the `ASYMMETRY` threshold), `test_remove_ground_slab` (synthetic: cube + thin plate under it in-test → plate gone, cube tris unchanged), `test_remove_loose_needs_weld` (call before weld → error), `test_clone_part` (synthetic 4 cylinders, one clean → all four identical tri counts), `test_recipe_reproducible` (apply twice → same tris and bbox), `test_export_roundtrip` (`vNN.blend` → glb → glbstat tris equal to the blend's triangulated count), `test_normals_kept_through_recipe` (untouched-triangle normal deviation < 0.5°).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: fixkit operators, recipes and export`.

### Task 11: Project profile and asset state

**Files:**
- Create: `scripts/profile.py`, `scripts/asset_state.py`, `scripts/data/budgets.json`, `references/profile-schema.md`, `tests/test_profile.py`

**Interfaces:**
- Produces `profile.json` schema v1: `{"schema": "profile/1", "engine": {"name": "godot", "version", "binary"}, "renderer", "platforms": [..], "art_style", "pbr": bool, "game_camera": {"yaw","pitch","fov"}|null, "texel_density": number|null, "budgets": {"<class>": int}, "naming": {"model_pattern", "root"}, "paths": {"art_source", "models", "asset_log"}, "asset_log_format": "grime"|"patina"|"none", "placement_mode": "scene_swap"|"generator_script", "pinned": {"cli", "gen_model", "texture_model", "rig_model"}, "check_commands": [..]}`.
- Produces: `profile.py detect <project>` → proposed profile + `"unknown": [keys]` (engine version from `project.godot` `config/features`; binary from `scripts/godot_bin.sh` if present; `art_source` = existing `art_src/`|`art_source/` with `.gdignore`; `asset_log` = `docs/asset_log.md`; format by header columns; `placement_mode` = `generator_script` when `scripts/dev/generate_*_models.gd` exist; check commands from `scripts/check_import.sh` and `.gutconfig.json`). `profile.py init <project> --answers <json>` writes `<project>/.claude/tripo/profile.json` (refuses to overwrite without `--force`).
- `budgets.json` defaults (triangles, LOD0) from `_research/game-polycount-lod.md` §2a, keyed `class × platform`: small_prop mobile 800 / pc 3000; large_prop 3000 / 15000; env_piece 2000 / 10000; weapon_held 3000 / 10000; npc 5000 / 20000; hero 10000 / 50000; vehicle 15000 / 30000.
- Produces: `asset_state.py new|get|update|ledger` over `<project>/.claude/tripo/assets/<id>.json` (`{"schema": "asset/1", "id", "class", "phase", "placeholder": {"scene", "node"}|null, "brief": {...}, "refs": [..], "chain": [{"label", "task_id", "kind", "model", "credits", "status"}], "qa": [..], "recipe", "decisions": [..]}`) and `ledger.jsonl` (`{"ts", "asset", "label", "kind", "estimate", "consumed", "task_id"}`). `get` on an older schema → exit 5 with `"migrate": true`; never auto-migrates silently.

- [ ] **Step 1: Failing tests:** `test_detect_grime` (on a temp copy of only `project.godot`, `scripts/godot_bin.sh`, `docs/asset_log.md`, `.gutconfig.json`, empty `art_src/.gdignore` from grime → `asset_log_format == "grime"`, `art_source == "art_src"`, `placement_mode == "scene_swap"`), `test_detect_patina` (same for patina → `"patina"`, `"art_source"`, `"generator_script"`), `test_init_no_overwrite`, `test_asset_roundtrip`, `test_old_schema_flagged`, `test_missing_profile_message` (`asset_state.py new` with no profile → exit 3, message names `profile.py init`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: project profile and asset state`.

### Task 12: Godot placement, provenance log, lessons

**Files:**
- Create: `scripts/godot_place.py`, `scripts/godot/aabb.gd`, `scripts/godot/rig_accept.gd`, `scripts/log_asset.py`, `scripts/lessons.py`, `lessons/general.example.md`, `tests/godot_min/` (project.godot, `main.tscn` with a `Node3D` root and a `MeshInstance3D` placeholder `Crate` using `BoxMesh` size `(1, 0.5, 0.8)` at `(2, 0, -1)` rotated 90° yaw), `tests/test_godot.py`, `tests/test_log_lessons.py`

**Interfaces:**
- Produces: `godot_place.py aabb <project> <scene> <node>` → `{"size", "center", "bottom_center", "yaw_deg"}` (runs `godot --headless --path <project> --script scripts/godot/aabb.gd -- <scene> <node>`).
- Produces: `godot_place.py plan <project> <asset.json> <glb>` → `{"copy_to", "import_params": {...}, "scene_diff": "<unified diff>", "before_after": {"size", "position", "yaw"}}` without writing; `godot_place.py apply …` performs exactly the planned change, then runs `godot --headless --import` and each `check_commands` entry; any failure → exit 5 with output tail. Scene swap: keep root name, node path, `unique_id`s, scripts, collision and child sockets; insert the model as a child scene instance named `Model`; set placeholder mesh `visible = false` and rename to `<name>_placeholder` (never deleted). `generator_script` mode: `plan` returns `"generator_hint": {"file", "symbols"}` and no scene diff; the agent edits the script and shows the diff (spec B19).
- Produces: `godot_place.py rig_accept <project> <glb>` (spec §14.5) → `{"skeletons": int, "bones", "single_root": bool, "max_influences", "animations": [..], "bonemap_auto": {"mapped", "unmapped": [..]}, "verdict": "pass"|"fail"}` via a headless helper `scripts/godot/rig_accept.gd` that imports the GLB, finds the `Skeleton3D`, and tries `SkeletonProfileHumanoid` auto-mapping. `fail` when skeletons ≠ 1, no single root, or max influences > 4; `bonemap_auto` is reported, not judged, until the first paid rig run settles the Godot `spec` (deferred list).
- `.import` params written: `gltf/embedded_image_handling=1` (extract), `meshes/ensure_tangents=true`, `meshes/generate_lods=true`, `nodes/apply_root_scale=true`.
- Produces: `log_asset.py <project> <asset.json>` → writes `<art_source>/<kind>/<id>/provenance.json` (`tools`, CLI version, wire model ids, task ids with credits, input file sha256, human edits = recipe ops, licence field from profile) and appends one row to `asset_log` in its detected format and section (grime columns `id | class | tool | date | prompt or source | license | notes`; patina columns `asset_path | source_tool | plan/license | generation_date | prompt_ref | human_edited | notes`); `none` → creates `docs/asset_log.md` with the patina columns only after `--create` (the skill asks first).
- Produces: `lessons.py add --project <p> --title --rule --evidence --cli <v> --model <wire>` (project file, no approval needed); `lessons.py candidates --project <p>` (lessons with no game-specific terms from profile `naming`/`art_style`/asset ids, or matching a lesson in another project's file listed in `<skill>/.state.json:"projects"`); `lessons.py promote --project <p> --id <n> --approved` (refuses without `--approved`; appends to `<skill>/lessons/general.md`, marks the project copy `promoted`); `lessons.py stale --cli <v> --model <wire>` (marks lessons tied to other versions `needs_reverify`). Lesson block format in `references/lessons-system.md`.
- `lessons/general.example.md`: empty template. On install (Task 16), `general.md` is created with one seed lesson, user-sourced (K16): "Multi-part objects: generate through Tripo (`generate_parts` or one piece + segment/smartsegment). Generating each part separately from its own images made parts that did not fit together or look like one family (patina, 2026-10)."

- [ ] **Step 1: Failing tests:** `test_aabb_min_project` (Crate → size `(1, 0.5, 0.8)` ± 1e-3, yaw 90), `test_plan_writes_nothing` (hash of the fixture dir unchanged after `plan`), `test_apply_keeps_identity` (on a temp copy: root name, node path and every `unique_id` unchanged; placeholder hidden and renamed; `Model` child present), `test_import_params`, `test_rig_accept_crew` (`crew_rigged` → `skeletons == 1`, `single_root`, `max_influences ≤ 4`, `verdict == "pass"`), `test_rig_accept_static_fails` (`jerry_can_g3` → `verdict == "fail"`), `test_check_failure_exit5` (profile with `check_commands: ["false"]`), `test_log_grime_format` / `test_log_patina_format` (temp copies of each `asset_log.md` → one new row with the right column count in the right section), `test_promote_requires_flag`, `test_candidates_exclude_game_terms`, `test_stale_marking`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: godot placement, provenance and lessons`.

### Task 13: References

**Files:**
- Create: `references/tripo-cli.md`, `generation-planning.md`, `image-preflight.md`, `qa-checklist.md`, `fix-tradeoffs.md`, `rigging.md`, `godot.md`, `lessons-system.md`, `cli-updates.md`; Test: `tests/test_references.py`

**Interfaces:**
- Consumes: `_research/*.md`, goldens (Task 6), thresholds (Task 7), ops (Task 10), schemas (Tasks 11–12).
- Content rules: each file ≤ 400 lines, opens with "When to read this" (phase). Facts only from `_research` or 0.9.0 observation. Where research notes disagree, the spec's decision wins: normals never recomputed globally (B7); `face_limit` is a hint, hard-surface → full-res then `decimate --model v3.0 --smart-uv` (B9); rig default A-pose + rig v3.0 (B6), `spec` for Godot = `mixamo` marked "to verify on first paid run"; bundled `examples/game-asset.md` LOD recipe is wrong (decimates the previous LOD) — LODs are made locally or by Godot.
- `image-preflight.md`: the agent-eye checklist (true ortho vs 3/4 side views, back = mirror not copy, unseen cavities, thin parts, glass, held props, A-pose, baked lighting words, movable parts → K7 question) with a Gemini fix prompt per item, and R1–R12 as examples.
- `fix-tradeoffs.md`: one row per QA code: Blender op(s), Tripo route + credits, regenerate condition, keeps rig/UV/scale yes/no, and the ladder from spec §13.
- `rigging.md`: rig-check → rig → retarget; Tripo bone names (`tripo::…`, Godot renames `::` → `__`); Godot BoneMap retarget path; animation question wording (K9, B16).

- [ ] **Step 1: Failing tests:** `test_no_higgsfield` (no file under `SKILL.md`, `references/`, `scripts/` contains "higgsfield", case-insensitive), `test_line_caps` (each reference ≤ 400 lines), `test_commands_are_golden` (every fenced `tripo …` command in `references/` either matches a golden argv shape or carries `<!-- unverified -->`), `test_every_qa_code_has_tradeoff` (each code from Task 7 appears in `fix-tradeoffs.md`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Write the references. **Step 4:** Run → PASS. **Step 5:** Commit `docs: skill references`.

### Task 14: SKILL.md

**Files:**
- Create: `SKILL.md`; Test: `tests/test_skill_md.py`

**Interfaces:**
- Consumes: every script interface above, `references/*`.
- Frontmatter: `name: tripo-game-assets`; `description` (≤ 1024 chars, third person) naming the triggers: converting a Godot placeholder into a 3D asset, generating a game asset with Tripo, checking/fixing a GLB/FBX from Tripo, rigging a model for Godot, Tripo credits/CLI updates.
- Body ≤ 250 lines: (1) session start: `cli_watch.py check`, `tripo balance`, load profile + both lesson files; (2) phase table = spec §9 with the script per phase and the reference to read; (3) approval rules = spec §18 verbatim in short form, including "with the lock installed, never ask separately before a paid step: run the single-step command, the permission window is the approval (K14)"; without the lock (`~/.claude/settings.json` has no `tripo_guard`), ask once per paid step; (4) report format: 2–3 Turkish lines + one table, details to `qa/vNN/report.md`, one batched question ("1A, 2B, 3 geç"); (5) state: update `assets/<id>.json` after every phase, resume from it; (6) hard rules: explicit `--model`, one paid step per command, `--name <asset>-<kind>-vNN`, run tripo from the asset's `raw/` dir, no `@last` across sessions, re-roll cap 2 (B11), front axis confirmed in the first QA report line, exit-code policy (spec §16.2); (7) end of task: `lessons.py add` for what was learned, then one message with promotion candidates; skill-logic proposals go to `~/Desktop/tripo-skill/docs/proposals/`.

- [ ] **Step 1: Failing tests:** `test_frontmatter` (name, description length), `test_line_cap` (≤ 250), `test_mentions_every_script` (each script in File Structure is named), `test_no_higgsfield` (reuse).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Write. **Step 4:** Run → PASS. **Step 5:** Commit `feat: SKILL.md`.

### Task 15: QA calibration on the local corpus

**Files:**
- Create: `scripts/calibrate.py`, `tests/calibration_labels.json`; Modify: `scripts/data/qa_thresholds.json`, `tests/test_qa.py`

**Interfaces:**
- Consumes: `qa.py`.
- `calibrate.py --corpus <dir>... --labels tests/calibration_labels.json` → per code: true/false positives on labelled cases, distribution percentiles over the unlabelled corpus, suggested threshold. Corpus = every `tripo-out/*/model.glb` under grime `art_src/` and patina `art_source/`, skipping any path containing `model_h31` or a sibling `job3d.json`. Skip files > 100 MB (log them, no silent cap).
- Labels from `_research/prior-testset.md` (direct-Tripo cases only): `tool_chest_g1` ASYMMETRY+BACK_COPY+OVER_BUDGET(8000); `pedal_car_raw` OVER_BUDGET(10000)+GROUND_SLAB-like discs; `pickup_g2` (cavity closed: info only — no automatic code, documented as agent-eye); `jerry_can_g2` LOOSE_PARTS or extra parts (agent-eye if metric misses); `bicycle_v1` SLIVERS; `bicycle_v2` clean; `back_panel_v2_20k` OVER_BUDGET(20000); `engine_block_g1` BACK_COPY; `bellows`/`winding_knob`/`shutter_release` (patina, "fine") clean.
- Rule: a code ships with `severity ≥ S2` only if it catches its labelled positives and stays silent on the labelled clean cases; otherwise it stays `info` and `references/qa-checklist.md` says "agent-eye".

- [ ] **Step 1: Failing test:** `test_calibrated_labels` (every label with a shipping code is caught; every clean label has no S0/S1).
- [ ] **Step 2:** Run → FAIL with initial thresholds. **Step 3:** Run `calibrate.py`, update thresholds, record the run summary in `docs/calibration-2026-10-31.md`. **Step 4:** Run → PASS. **Step 5:** Commit `feat: calibrated qa thresholds`.

### Task 16: Install skill and lock

**Files:**
- Modify: `~/.claude/settings.json` (backup to `~/.claude/settings.json.bak-tripo-guard` first); Create: symlink `~/.claude/skills/tripo-game-assets`, `lessons/general.md` (seed lesson, Task 12 text)

**Interfaces:**
- Hook entry appended to the existing `PreToolUse` → `matcher: "Bash"` group, after `rtk hook claude`: `{"type": "command", "command": "python3 ~/.claude/skills/tripo-game-assets/scripts/hooks/tripo_guard.py"}`. Existing entries untouched.

- [ ] **Step 1:** Show the user the exact settings.json diff before writing (the edit is outward-facing config; consent was given in the conversation, the diff is shown for confirmation of form).
- [ ] **Step 2:** Back up, write, validate JSON (`python3 -m json.tool`).
- [ ] **Step 3: Verify the lock live:** in this session run `tripo make "a crate" --model tripo-v3.1` → the permission window must appear; **deny it**. Run the same with `--dry-run --json` → no window. Run `tripo balance` → no window.
- [ ] **Step 4:** Create symlink; confirm the skill appears in the skill list.
- [ ] **Step 5:** Commit `chore: install notes` (repo files only; settings.json is not in the repo).

### Task 17: End-to-end skill behaviour test (0 credits)

**Files:**
- Create: `tests/e2e/README.md`, `docs/e2e-2026-10-31.md` (result)

- [ ] **Step 1:** Make a scratch Godot project: copy `tests/godot_min/` + patina mailbox `concept/` images + `tool_chest_g3` raw GLB into the scratchpad.
- [ ] **Step 2:** Dispatch a fresh subagent with only: "Use the tripo-game-assets skill. In <scratch project>, turn the `Crate` placeholder into a tool chest using these reference images; the Tripo raw result already exists at <path> (treat it as the generation output, do not generate)." The paid steps it attempts must stop at the permission window (the subagent cannot approve).
- [ ] **Step 3: Check and record:** preflight ran before any paid command; every paid command was single-step with explicit `--model` and `--name`; QA + render sheet produced; the fix report is ≤ 6 lines + one table and asks one batched question; no question about free actions; front axis confirmed inside the QA report; placement shown as a diff and not applied without approval; a project lesson written; no write outside the scratch project and the skill's own state.
- [ ] **Step 4:** Fix whatever failed (each fix is its own commit), re-run until all checks pass. **Step 5:** Commit `test: e2e behaviour run`.

### Deferred until credits are topped up (each paid step through the lock)

Not part of this plan's completion; listed so the gap is visible (spec §19.7): A-pose vs T-pose rig-check/rig, `spec` compatibility with Godot BoneMap, delight's effect on baked lighting vs a non-delight control, `face_limit` overshoot on v3.1 without `smart_low_poly`, whether `decimate → uv` and `rig → convert` chains accept non-generation task ids, import task price. Each result becomes a lesson and, when it changes a reference, a proposal.
