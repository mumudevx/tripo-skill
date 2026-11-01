# Project state files: profile.json, assets/<id>.json, ledger.jsonl

When to read this: phase 1 (profile setup, when `profile.json` is missing) and whenever the skill resumes an asset or records a paid step.

All three live in `<project>/.claude/tripo/` (data only, small, safe to commit). Written and read only through `scripts/profile.py` and `scripts/asset_state.py`; never edit them by hand while a session is running.

## profile.json (`"schema": "profile/1"`)

Created once per game by `profile.py init`. `profile.py detect <project>` proposes it from the project files and lists `"unknown"`: the keys the project could not tell us. Ask the user for exactly those, then `init --answers <json>`. `init` refuses to overwrite an existing profile without `--force`. Any script that needs the profile and finds none stops with exit 3 and names `profile.py init`.

| key | type | meaning and how `detect` fills it |
|---|---|---|
| `engine.name` | string | `godot` |
| `engine.version` | string or null | first `N.N` in `config/features` of `project.godot` |
| `engine.binary` | string or null | Godot path pinned in `scripts/godot_bin.sh`, else `godot` on PATH, else the macOS app bundle |
| `renderer` | string or null | `renderer/rendering_method` in `project.godot`, else the renderer feature (`forward_plus`, `mobile`, `gl_compatibility`) |
| `platforms` | list of `pc` / `mobile` | from the platforms in `export_presets.cfg` (Windows, macOS, Linux = `pc`; Android, iOS, Web = `mobile`); empty when there are no presets (ask) |
| `art_style` | string or null | never detected (ask). Drives model choice (low poly: P1/P2 or v3.1 with `smart_low_poly`) |
| `pbr` | bool | default `false` (tripo-cli 0.9.0 default); the user can turn it on |
| `game_camera` | `{yaw, pitch, fov}` or null | never detected (ask). Decides which faces the player sees (detail budget, QA severity). Passed as `render_sheet.py --game-cam yaw,pitch,fov`, so it uses that convention: `yaw` degrees around the model from its front towards its right; `pitch` degrees **above** the horizon (positive = camera above the model looking down, -89..89; negative = below, looking up, which `init` warns about); `fov` vertical degrees (0-170). Example: a third-person camera slightly above and behind the player, looking at a prop's front: `{"yaw": 0, "pitch": 35, "fov": 70}` -> `--game-cam "0,35,70"` |
| `texel_density` | number or null | never detected (ask). Texels per metre target for textures |
| `budgets` | `{class: triangles}` | LOD0 triangles per class from `scripts/data/budgets.json`, for the profile's platforms; with several platforms the tightest wins. Answers overlay single classes |
| `naming.model_pattern` | string or null | model file name pattern, e.g. `{id}.glb` (ask) |
| `naming.root` | string or null | model root folder; defaults to `paths.models` |
| `paths.art_source` | string or null | existing `art_src/` or `art_source/` that holds a `.gdignore`; a folder without one is reported in `warnings`, not used |
| `paths.models` | string or null | `assets/models` when it exists |
| `paths.asset_log` | string or null | `docs/asset_log.md` when it exists |
| `asset_log_format` | `grime` / `patina` / `none` | by the header row: `id, class, ...` = `grime`; a column `asset_path` = `patina`; no file = `none`. A log in an unknown format is `none` and listed in `unknown` |
| `placement_mode` | `scene_swap` / `generator_script` | `generator_script` when `scripts/dev/generate_*_models.gd` exist (the `.tscn` files are generated, so placement edits the generator), else `scene_swap` |
| `pinned.cli` | string | tripo-cli version the profile was made for (`0.9.0`) |
| `pinned.gen_model` / `texture_model` / `rig_model` | string | wire ids passed to `--model` (never left to a default) |
| `check_commands` | list of strings | run from the project root after placement: `bash scripts/check_import.sh`, and, when `.gutconfig.json` exists, the project's `scripts/run_tests.sh` when present (it fails on parse errors and leaks that raw GUT reports as exit 0), else the raw GUT command |

Budget classes: `small_prop`, `large_prop`, `env_piece`, `weapon_held`, `npc`, `hero`, `vehicle`. The numbers are starting points (`_research/game-polycount-lod.md` section 2a); the profile may change any of them. Unknown answer keys are an error, not ignored.

## assets/<id>.json (`"schema": "asset/1"`)

`id` matches `[a-z0-9][a-z0-9_-]*`. Updated after every step so a cut-off session resumes at `phase`.

```
{"schema": "asset/1", "id": "...", "class": "<budget class>",
 "phase": "brief|preflight|plan|generate|qa|fix|rig|place|lessons|done",
 "placeholder": {"scene": "res://...", "node": "..."} | null,
 "brief": {...}, "refs": ["path", ...],
 "chain": [{"label", "task_id", "kind", "model", "credits", "status", "params"[, "source", "file"]}],
 "qa": [...], "recipe": "path to the fix recipe" | null, "decisions": [...]}
```

- A raw result the user supplied (no paid step in this session) adds `"source": "user-supplied"` and `"file"` (the frozen copy under `raw/<label>/`) to its chain entry: `status` is `done`, `credits` is `0`, `task_id` and `model` stay `null` unless the user states them (never inferred from node or file names), and it gets no ledger row (`ledger --add` refuses that label). Entries without `source` are Tripo steps the skill ran.
- `chain[].kind` uses the `tripo_plan.KINDS` spelling (`rig_check`, never `rig-check`; `asset_state.py` normalises the hyphen). `params` is the dict that was passed to `tripo_plan.py`. With those two, the asset file is a valid `tripo_plan.py --chain` input. `status` is `planned`, `running`, `done` or `failed`; `task_id` and `credits` stay `null` until known.
- `asset_state.py get` on a file with another schema exits 5. `"migrate": true` means older (migrate it deliberately; nothing is rewritten automatically); `"migrate": false` means newer than this skill.
- Operations: `new` (needs a profile), `get`, `update` (`--phase`, `--set KEY=JSON` for `phase`, `placeholder`, `brief.*`, `recipe`; `--append KEY=JSON` for `refs`, `qa`, `decisions`, `chain`; `--chain-update LABEL=JSON`). A failed operation writes nothing.

## ledger.jsonl

Append-only, one JSON object per line: `{"ts", "asset", "label", "kind", "estimate", "consumed", "task_id"}`. Write the row with `consumed: null` when the step is planned and append a second, complete row (same `asset`, `label`, `kind` and `estimate`, plus the real `consumed` and `task_id`) once the real cost is known; the latest row per `(asset, label)` wins in the totals that `asset_state.py ledger <project> [--asset ID]` prints. `ledger --add <json>` appends (the `ts` is added by the script).
