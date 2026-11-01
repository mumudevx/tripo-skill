# tripo-cli 0.9.0: commands, parameters, prices

When to read this: phase 4 (generation plan) and before any paid step in phases 6 and 7; also when a tripo command exits non-zero.

Every fact here was checked against tripo-cli 0.9.0 (`tests/golden_dryruns.json`, recorded with `--dry-run --json`, and the 0.9.0 `CHANGELOG.md`) or comes from `_research/tripo-*.md`. A fenced command marked `<!-- unverified -->` has no golden dry-run of the same shape: `tripo_plan.py` still dry-runs it before use, but the golden set does not pin its behaviour across CLI updates.

## 1. How the skill calls Tripo

The skill never types a paid tripo command by hand. It writes one step as JSON and lets `scripts/tripo_plan.py` build, validate and price it:

```
python3 scripts/tripo_plan.py '{"kind": "generate", "label": "crate-generate-v01",
  "input": {"images": ["refs/front.png", "refs/left.png", "refs/back.png"]},
  "model": "tripo-v3.1",
  "params": {"texture_version": "v3.5", "delight": true, "texture_quality": "detailed"}}'
```

- Output: `{"ok", "argv", "ref", "dry_run", "estimate": {"credits", "source"}, "warnings", "errors", "paid"}`. Exit 5 = the step breaks a rule (`errors` non-empty); 2 = malformed step; 3 = input file missing; 4 = tripo CLI missing or broken.
- `--build` returns only `argv` and `ref` and runs nothing (no CLI call).
- `--chain <assets/<id>.json>` adds cross-step checks against the asset's earlier steps (for example a quad step followed by a GLTF convert).
- Then run `argv` exactly as printed, from the asset's `raw/` folder. With the credit lock installed (section 7) the permission window is the approval; the skill asks nothing extra.
- `kind`: `generate`, `texture`, `decimate`, `uv`, `segment`, `smartsegment`, `complete`, `convert`, `rig_check`, `rig`, `retarget`, `image_to_multiview`, `edit_multiview`.
- `input`: `{"images": [...]}`, `{"prompt": "..."}`, `{"task": "<task_id|@label>"}` or `{"file": path}`.
- `model` is required for `generate`, `decimate`, `rig` and `texture` (B10).
- `label` must be `<asset>-<kind>-vNN` (for example `crate-rig_check-v01`; the kind keeps its underscore). It becomes `--name`.
- `ref` is the `@reference` of the task the step produces. A generation is `@<label>`; a `--then` step is `@<label>-<step>` (for example `@crate-decimate-v01-decimate`). Use that `ref` as the next step's `{"task": ...}`.
- `orientation`, `export_orientation` and `auto_size` are dropped from `params`: direction and scale are set locally (`normalize.py`), never by Tripo.
- `candidates` must be 1. `-n` multiplies the cost and `-n` with `--then` needs a TTY.

Record every paid step in the ledger before and after it runs: `asset_state.py ledger <project> --add '{"asset", "label", "kind", "estimate", "consumed": null, "task_id": null}'`, then append the full row again (same `asset`, `label`, `kind` and `estimate`) with the real `consumed` and `task_id`; every row needs `kind` and a numeric `estimate`, and the latest row per asset/label replaces the earlier one in the totals.

## 2. Hard rules (each one cost credits before)

1. **Always `--model`, never `-p model=`** (B10). Without `--model`, 0.9.0 picks the model itself: `-p face_limit=8000` alone selects P2 (estimate 110, golden `auto_model_face_limit_8000_*`). In 0.6.1 `-p model=` overrode `--model` and skipped the model checks; 0.9.0 keeps `--model` (golden `model_param_cannot_override_flag`), but the rule stays.
2. **One paid step per command** (B17). `tripo_plan.py` builds single steps; the lock refuses a command that holds two paid steps. The free `rig-check` runs on its own command too.
3. **Only `tripo make` has `--dry-run`.** `generate`, `model`, `mesh`, `anim`, `redo`, `batch`, `ai` and the MCP tools have none. `tripo_plan.py` routes every kind it can through `tripo make <src> --then <step>`; only `image_to_multiview`, `edit_multiview` and `smartsegment` become direct commands (no dry-run, priced from the table).
4. **`-p` reaches only the generation step**, never a `--then` step. `--then` takes scalars only: no lists, no objects (a list makes `tripo_plan.py` refuse the step).
5. **A local file input adds an `import` task** (`tripo make model.glb --then ...`). Its price is not published and it normalizes scale. Chain from the `@label` of a Tripo task when the model has not been edited locally; use the file only when it has (for example rig after Blender fixes, B18).
6. **Name every task** (`--name`, from `label`) and run from the asset's `raw/` folder. A real run writes `.tripo/context.json` into the working directory: check that `.tripo/` is git-ignored. `@last` is the last successful task and, after a chain, its last step: never use `@last` across sessions. `@name` falls back to a fuzzy substring match, so labels must be unique.
7. **Measure, never trust the request.** `face_limit` is a hint (B8): see `generation-planning.md` section 3.
8. **Never `tripo redo`, `tripo ai` or `tripo batch run`.** Each submits immediately with no plan card, no dry-run and no confirmation.

## 3. Generation (`kind: generate`)

Input decides the endpoint: text = text-to-model, one image = image-to-model, 2 to 4 images = multiview-to-model (file names `front`/`left`/`back`/`right` give the roles, else that order; front is required).

Default image or multiview generation (golden `delight_generate_v31`, estimate 40 for one image):

```bash
tripo make refs/front.png --model tripo-v3.1 -p texture_version=v3.5 -p delight=true -p texture_quality=detailed --name crate-generate-v01
```

H-series low poly with hand-made-style topology (golden `smart_low_poly_v31_explicit`, estimate 30 from text):

```bash
tripo make refs/front.png --model tripo-v3.1 -p smart_low_poly=true -p face_limit=5000 --name crate-generate-v01
```

Separate parts, untextured (golden `parts_explicit_texture_off`, estimate 30 from text; texture it afterwards):

```bash
tripo make refs/front.png --model tripo-v3.1 -p texture=false -p pbr=false -p generate_parts=true --name crate-generate-v01
```

Native quads on P2 (golden `p2_quad_8000`, estimate 110; output is FBX):

```bash
tripo make refs/front.png --model tripo-p2 -p quad=true -p face_limit=8000 --name crate-generate-v01
```

Parameter facts (0.9.0):

| parameter | effect | checked by |
|---|---|---|
| `--model tripo-v3.1` | H3.1, wire `v3.1-20260211`, the official default | golden |
| `--model tripo-p1` | P1 `P1-20260311`: clean low-poly triangles, `face_limit` 50 to 20000; no `quad`, `smart_low_poly`, `generate_parts`, `geometry_quality` (removed with a warning) | golden `p1_*` |
| `--model tripo-p2` | P2 `P2-20260801`: `face_limit` 48 to 50000 tris, 48 to 25000 with `quad=true`; no `smart_low_poly` (removed) | golden `p2_*` |
| `--model tripo-v2.5` | legacy: `geometry_quality`, `quad`, `smart_low_poly`, `generate_parts`, `auto_size`, `compress` removed | golden, changelog |
| `face_limit` | target face count; a hint, not a cap (B8) | measured |
| `smart_low_poly=true` | H only, +10; needs `face_limit` 500 to 20000 (error below) | golden |
| `generate_parts=true` | H only, +20; 0.9.0 turns texture and pbr off with a warning, still pass `texture=false pbr=false`; rejected together with `smart_low_poly` | golden |
| `quad=true` | +5 on H; output is forced to FBX (quads cannot live in GLB) | golden |
| `texture_version=v3.5` | newest texture model (`v3.5-20260815`); enables `delight` and `texture_quality=fast` | golden |
| `delight=true` | removes lighting baked into the reference from the albedo (v3.5 only); `false` keeps painted shading | changelog, golden |
| `texture_quality` | `fast` (selects v3.5 by itself) / `standard` / `detailed` (+10) / `extreme` (8K, +20) | golden |
| `pbr` | opt-in since 0.9.0: omitted means `pbr=false`; `pbr=true` forces `texture=true` | golden |
| `geometry_quality=detailed` | +20, H3.x only; not used for game assets (doubles cost, turns printed detail into lumps) | research |
| `-n N` | N parallel candidates, N times the price, at most 4 | golden |

## 4. Processing steps (`kind` other than generate)

All of these run as `tripo make <@label|file> --then <one step>`.

Decimate with UV unwrap (golden `decimate_smart_uv_v3`; 35 credits from the table, the dry-run gives no estimate):

```bash
tripo make @crate-generate-v01 --then "decimate:model=v3.0;face_limit=5000;smart_uv=true" --name crate-decimate-v01
```

- `smart_uv` needs an explicit `model=v3.0` (0.9.0 rejects it otherwise). `face_limit` 500 to 20000 (500 to 10000 with `quad=true`). `model=v1.0` requires `face_limit`.
- Measured: v3.0 + smart_uv lands at 0.69 to 1.02 x the target; v1.0 hits the target within 2 faces but has no bake and keeps a mismatched normal map; v2.0 (the server default) overshot 20000 to 29943. Never use v2.0 when the budget matters.

Retexture on the same mesh (0.9.0 dry-run accepts texture model v3.5 with `delight`; 0.6.1 rejected it):

<!-- unverified -->
```bash
tripo make @crate-generate-v01 --then "texture:model=v3.5;delight=true;texture_quality=detailed" --name crate-texture-v01
```

Other single steps (prices from section 6):

<!-- unverified -->
```bash
tripo make @crate-decimate-v01-decimate --then uv --name crate-uv-v01
tripo make @crate-generate-v01 --then segment --name crate-segment-v01
```

Convert with a texture size (golden `convert_complex_tier_warning`: any non-default option bills the advanced tier, 10):

```bash
tripo make @crate-generate-v01 --then "convert:format=FBX;texture_size=2048" --name crate-convert-v01
```

- `convert:glb` is an error: GLB is the native output, not a convert target (golden).
- A quad mesh cannot be converted to GLTF. The CLI only warns; `tripo_plan.py --chain` refuses it.
- `uv` (Smart UV, 20) re-unwraps and remaps existing textures, rig and animation; input at most 80000 triangles (decimate first).
- `segment` (40) splits parts; `complete` (50, or 30 with `completion_mode=quick_cap`) accepts only a segment task.
- `smartsegment` (55 model, 85 image) takes a file only and runs as a direct `tripo mesh smartsegment` command (no dry-run).
- Rig steps are in `rigging.md`.

## 5. Image pre-steps (paid, optional)

`image_to_multiview` (10) makes four views from one image; `edit_multiview` (5 per edited view) repairs a view of such a task. Both are direct `tripo generate ...` commands with no dry-run. A fix in the user's image tool costs nothing, so offer that first (`image-preflight.md`).

## 6. Prices (credits, 1 credit = 0.01 USD; `scripts/data/prices.json`, as of 2026-10-31)

The dry-run's `generation_credits_estimate` wins for generation steps (H3.1 and P2 only). Chain steps, P1, legacy models and imports have no dry-run estimate; the table below is used, and an unknown price is "tahmin yok", never 0.

| step | credits |
|---|---|
| H3.x text-to-model, no texture / textured | 10 / 20 |
| H3.x image or multiview, no texture / textured | 20 / 30 |
| H add-ons | `texture_quality=detailed` +10, `extreme` +20, `geometry_quality=detailed` +20, `quad` +5, `smart_low_poly` +10, `generate_parts` +20 |
| P1 text / image or multiview (no texture / textured) | 30/40 / 40/50 |
| P2 any input (no texture / textured) | 100 / 110 |
| texture step fast / standard / detailed / extreme | 10 / 10 / 20 / 30 |
| decimate v1.0 / v2.0 / v3.0 tri / v3.0 quad | 10 / 30 / 35 / 40 |
| uv | 20 |
| segment | 40 |
| complete ai_completion / quick_cap | 50 / 30 |
| smartsegment model / image | 55 / 85 |
| convert basic / advanced | 5 / 10 |
| rig-check | 0 on a task; a file input adds an import task (price unknown) |
| rig | 25 |
| retarget | 10 per animation |
| image_to_multiview | 10 |
| edit_multiview | 5 per view |
| import (any local file input) | unknown |
| P-series detailed/extreme texture, P2 quad surcharge | unknown |

Golden estimates (0.9.0): v3.1 image + v3.5 + detailed = 40; v3.1 text = 20; v3.1 text + smart_low_poly = 30; v3.1 text + parts = 30; v3.1 multiview = 30; P2 = 110. Failed and cancelled tasks are refunded.

## 7. Credit lock (`scripts/hooks/tripo_guard.py`)

- A global PreToolUse hook on Bash. It finds tripo calls behind `rtk`, `env`, `VAR=...`, `cd ... &&`, pipes, `bash -c`, `eval`, `$(...)` and backticks, heredocs fed to a shell, `npx tripo-cli`, a path to the binary (names case-folded), and in a shell script that `bash`/`sh`/`source` runs. Comments, quoted text and quoted heredoc bodies are text.
- **Is the lock on?** Only the functional check of SKILL.md section 1 step 4 decides: it pipes a synthetic paid event into the installed hook and expects `"permissionDecision": "ask"` (`LOCK OK`). A grep for `tripo_guard` in `~/.claude/settings.json` proves nothing. With the lock the window is the approval (K14); without it the skill asks in chat once before every paid step (SKILL.md section 3).
- Free, no output (other hooks decide): `--dry-run`, `--help`, `--version`, `docs`, `models`, `balance`, `usage`, `whoami`, `doctor`, `history`, `view`, `config`, `update`, `completion`, `login`, `logout`, `use`, `mcp` with no stdin (starting the server), `task get|list|watch`, `files upload`, `anim check`, `--then rig-check` on a task.
- The guard's decisions:

| command | decision |
|---|---|
| exactly one paid step | `ask`: a window with the step, the estimate (make dry-run, else the price table, else "tahmin yok"), the balance and the label, in Turkish. A local file's leading import belongs to that step |
| a loop body (`for`/`while`/`until`/`select`, zsh `repeat`), a repeater (`xargs`, `parallel`, `find -exec`, `fd -x`, `watch`), a function called more than once, `tripo batch run`, `tripo ai <request>` | `deny` (B17): one approval would start many paid tasks |
| two or more paid steps in one command (chain steps, a scenario chain, candidates, two calls, or a make dry-run that plans more than one paid task) | `deny` (B17) |
| an unknown tripo subcommand | counts as one paid step |
| an unknown runner (`mise exec`, `npm exec`, `caffeinate`, ...) that is not a read-only tool | read from its first tripo word: classified like a bare call |
| an opaque program in a command that mentions tripo (`$VAR`, `$(...)`), or a shell script file that calls tripo | `ask`, marked "görülemeyen çağrı" |
| `tripo mcp` with stdin from a pipe, file, heredoc or here-string | `ask`: JSON-RPC can call `tripo_make` |
| a command the guard cannot parse | `ask` when it mentions tripo |
| an error inside the guard | `ask` |
| the hook cannot start (its `tripo_plan` import fails) | `ask` on every command that mentions tripo |

- Hard rule 3 still applies: run tripo as a bare `tripo …` or the absolute path, one paid step per command, never through a wrapper, script, loop, function or `$VAR`. A "görülemeyen çağrı" window means the command breaks that rule: rewrite it as a bare call instead of approving it.
- **The lock does not cover the MCP tools.** A `tripo_make` MCP tool call is not a Bash command, so the hook never sees it, and `tripo_make` has no dry-run or confirmation. The skill never registers or uses `tripo mcp` (hard rule 9).

## 8. Exit codes and what to do (spec 16.2)

| exit | meaning | action |
|---|---|---|
| 0 | success | read the stdout JSON (`task_id`, `credits_consumed`, `output_dir`, `files`) |
| 1 | unexpected or internal CLI error | report the error JSON to the user; do not resubmit until `tripo balance` and `tripo usage` show what happened |
| 2 | bad parameters (also dry-run `valid:false`) | fix the step, dry-run again |
| 3 | auth | `tripo doctor`; the user signs in (`tripo login`); never ask for the key in chat |
| 4 | insufficient credits | stop; suggest `tripo topup` to the user; never top up automatically |
| 5 | content policy | change the prompt or the image |
| 6 | task failed (refunded) or watch timed out (still running, billed on success) | timeout: `tripo task watch <id> --download`, never redo; failed: report the reason, a new run is a new paid step |
| 7 | network or server error (a 0.8.0+ artifact download failure too) | do not resubmit blindly: check `tripo balance` (frozen credits) and `tripo usage` first; a download failure is fixed with `tripo task get <id> --download` |
| 8 | not found | check the id, account and region |
| 9 | rate limit or concurrency pool full | wait, then retry |

## 9. Results on disk

- Downloads land in `<cwd>/tripo-out/<slug>-<id8>/` (`model.glb`, `task.json`, previews). `task.json` records the wire model, the seeds and the payload.
- Output URLs expire after about 5 minutes: re-download with `tripo task get <id> --download`, never store a URL.
- A rig-check verdict is not in `task.json`: read it from the command's stdout JSON.
- Prices still to measure on the first paid runs are listed in `cli-updates.md` section 5.
