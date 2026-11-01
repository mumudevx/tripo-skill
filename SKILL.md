---
name: tripo-game-assets
description: Turns Godot placeholders into game-ready 3D assets through tripo-cli. Use when the user wants to convert a Godot placeholder into a 3D model ("placeholder'ı modele çevir"), generate a game asset with Tripo, check or fix a GLB/FBX that came from Tripo ("bu GLB'yi kontrol et"), rig or animate a model for Godot, or asks about Tripo credits, balance, spending or tripo-cli updates. Reviews reference images before any credit is spent, plans and prices one paid Tripo step at a time behind a credit lock, measures and renders every result in headless Blender, offers free Blender fixes against paid Tripo fixes, places the approved model in the Godot scene with a diff, and records project lessons. Also invoked as /tripo-game-assets.
---

# tripo-game-assets

Placeholder in a Godot scene -> reference check -> one paid Tripo step at a time -> Blender QA and fixes -> rig (characters) -> placement in Godot -> lessons.

**Paths.** `scripts/` and `references/` live in this skill's folder, `~/.claude/skills/tripo-game-assets/`. Call scripts by that absolute path (the working directory is often an asset's `raw/` folder). `<project>` = the Godot root (folder with `project.godot`); project data lives in `<project>/.claude/tripo/` (`profile.json`, `lessons.md`, `ledger.jsonl`, `assets/<id>.json`). Every script prints one JSON line; exit `0` ok, `2` usage, `3` input not found (the message names it), `4` internal error, `5` check failed or refused. Blender scripts run through `bl.py` (`python3 scripts/bl.py qa.py -- <args>`), which fails loudly and never leaves a stale result.

**Language.** Skill files, scripts and lessons are English. Everything shown to the user is Turkish (B13).

## 1. Session start (every time the skill is invoked)

1. `python3 scripts/cli_watch.py check --update` (at most once a day; `--update` installs a newer tripo-cli, the user granted this permanently, K13). Read `references/cli-updates.md` when it reports anything.
   - `skipped: true` -> say nothing.
   - Otherwise a 3-5 line Turkish summary built from `relevant` (new version `from` -> `installed`, changed parameters, defaults, prices), plus `changelog eksik: <versions>` when `changelog_missing`/`changelog_gaps` is set. Nothing changed and no error field (next line) -> say nothing.
   - `update_error` or `update_check_error` set -> one Turkish line saying the update or the check failed, with the error tail and the still-installed `installed` version (`update_available: true` means it is outdated). Never silent, even when `relevant` is empty. Free work goes on; paid steps run on the installed version.
   - Exit 5 (golden drift): report the drifted `golden.failed[].name` with the first diff line, then continue. Flag the matching `references/tripo-cli.md` sections and version-bound lessons "re-verify" (`lessons.py stale --cli <installed> --model <wire id> ...`) and write a proposal (section 8).
   - Exit 4 (tripo CLI missing or broken): report it; **no paid step until it is fixed**. Free work goes on. `tripo CLI not found` with `npm` on PATH -> reinstall with `npm install -g tripo-cli@latest` (covered by K13), then re-run the check and `tripo balance`. Usual cause: a Node version manager (mise, nvm) upgraded Node and dropped the global packages; say so in one line.
2. `tripo balance` (free). Keep the number for the plan lines.
3. Load `<project>/.claude/tripo/profile.json` (missing -> phase 1). Read both lesson files: `<project>/.claude/tripo/lessons.md` and `lessons/general.md` in this skill. A lesson with `status: needs_reverify` is a warning, not a rule. On conflict the project lesson wins.
4. Lock check (functional, decides the approval mode in section 3). Pipe a synthetic paid event into the installed hook command; never trust a grep of the settings:
   ```
   python3 -c 'import json,os,subprocess as sp; h=[x["command"] for m in json.load(open(os.path.expanduser("~/.claude/settings.json"))).get("hooks",{}).get("PreToolUse",[]) for x in m.get("hooks",[]) if "tripo_guard" in x.get("command","")]; e=json.dumps({"tool_name":"Bash","tool_input":{"command":"tripo make x.png --model tripo-v3.1"}}); print("LOCK OK" if any("\"permissionDecision\": \"ask\"" in sp.run(c,shell=True,input=e,capture_output=True,text=True,env={**os.environ,"TRIPO_GUARD_OFFLINE":"1"}).stdout for c in h) else "LOCK MISSING")'
   ```
   `LOCK OK` (the hook answered `"permissionDecision": "ask"`) -> "with the lock". Anything else (`LOCK MISSING`, an error, no `python3`) -> "without the lock" for the whole session, and say so in one Turkish line.
5. Resume: if the user names an asset with a state file, `asset_state.py get <project> <id>` and continue from its `phase`. Exit 5 with `"migrate": true` -> say the file is from an older schema and ask before migrating; `"migrate": false` -> newer than this skill, stop and say so. Never guess.

## 2. Phases (spec 9)

| # | phase (`phase` in state) | scripts | read | ask the user |
|---|---|---|---|---|
| 0 | session start | `cli_watch.py`, `tripo balance` | `cli-updates.md`, `lessons-system.md` | nothing (only a change summary) |
| 1 | profile setup (when missing) | `profile.py detect`, then `profile.py init --answers` | `profile-schema.md` | only the keys in `unknown` |
| 2 | placeholder (`brief`) | `godot_place.py aabb`, `asset_state.py new` | `godot.md` 1-2 | nothing |
| 3 | image preflight (`preflight`) | `preflight_ref.py` (pixel work in `preflight_img.py`) + agent eye | `image-preflight.md` | if problems: fix the image or "yine de gönder" |
| 4 | plan + generate (`plan`, `generate`) | `tripo_plan.py`, then the printed argv; `asset_state.py ledger` | `generation-planning.md`, `tripo-cli.md` | one piece or parts (K7, both prices); the credit itself goes through the lock window |
| 5 | measure + render + QA (`qa`) | `glbstat.py`, `bl.py qa.py`, `bl.py render_sheet.py` | `qa-checklist.md` | nothing (front axis = one line inside the report) |
| 6 | report, options, apply (`fix`) | `bl.py apply_recipe.py`, `bl.py normalize.py`, `bl.py export.py`; paid options via `tripo_plan.py` | `fix-tradeoffs.md` | one batched question ("1A, 2B, 3 geç") |
| 7 | rig + animation (`rig`, characters) | `tripo_plan.py` (`rig_check`, `rig`, `retarget`), `godot_place.py rig_accept` | `rigging.md` | animation: Tripo retarget or Godot BoneMap, which clips (K9, B16) |
| 8 | Godot placement (`place`) | `bl.py export.py`, `godot_place.py plan` -> `apply --expect`, `log_asset.py` | `godot.md` | placement approval, shown as a diff (K6) |
| 9 | lessons (`lessons` -> `done`) | `lessons.py add` (also earlier, whenever a lesson is learned), `lessons.py candidates`, `lessons.py promote --approved` | `lessons-system.md` | one message with general-promotion candidates |

Order rule: **cloud first, then local.** Every paid Tripo step (each its own command) finishes before any Blender fix; the raw output stays frozen in `raw/<label>/`. The one exception is rig (B18): decimate to budget, fix and normalize locally, then rig as the last cloud step; after rig the geometry is frozen (only materials and names). Warn when a Blender choice makes a later Tripo step dearer (a locally edited model goes back as a file: an import task with an unknown price).

Checking a GLB/FBX the user hands over (no placeholder): run phases 5 and 6 on that file; the budget comes from `profile.json` `budgets[class]` when inside a project, else ask for the class once.

Placeholder **and** a raw generation result the user already has (made outside this session): phases 1-2 as usual; phase 3 preflight runs but is **report-only** (findings go into `decisions` and become QA expectations; no image fix is asked for, no credit is at stake). Phase 4 is replaced by freezing the file: copy it unchanged to `raw/<label>/` (label `<id>-generate-vNN`), make it read-only, and append the chain entry `{"label", "kind": "generate", "source": "user-supplied", "file": "raw/<label>/<name>", "task_id": null, "model": null}` (`status` becomes `done`, `credits` 0). Fill `task_id` or `model` only when the user states them; **never infer a task id** from a GLB node name (`tripo_node_<uuid>`) or a file name. No ledger row (`asset_state.py ledger --add` refuses one for that label). Then phases 5-9.

### Phase notes

- **1 Profile.** `profile.py detect <project>` proposes everything it can read from the project (engine, binary, platforms, art source, asset_log format, placement mode, check commands). Ask only for `unknown`, in one message, then `profile.py init <project> --answers '<json>'`; `init` creates `<art_source>/.gdignore` itself (never by hand), so Godot never imports raw files. Never re-ask what the profile answers.
- **2 Placeholder.** `godot_place.py aabb <project> <res://scene.tscn> <node>` -> `size`, `bottom_center`, `yaw_deg` and `normalize_target_size`. Create the state: `asset_state.py new <project> <id> --class <budget class> --placeholder-scene <scene> --placeholder-node <node> --brief '<json>' --ref <img>`. Put `kind` into the brief when it differs from the class.
- **Asset folder.** `<art_source>/<kind>/<id>/` with `refs/`, `raw/<label>/` (frozen Tripo output), `work/vNN.blend`, `fixes/<id>.recipe.json`, `qa/raw/` + `qa/vNN/`, `export/`. The QA folder is named after the model checked, never counted on its own: `qa/raw/` for the raw output, `qa/vNN/` for `work/vNN` (`apply_recipe.py` prints it as `qa_dir`). `<art_source>` = `profile.json` `paths.art_source`; kind = `--kind` > `brief.kind` > class. Pass the same kind to `log_asset.py --kind` so the raw files and `provenance.json` share one folder.
- **3 Preflight.** `preflight_ref.py <images...>` (exit 5 = a `fail` check), then look at every view with the agent-eye list. Report one Turkish line per problem with a ready English fix prompt for the image tool. A "yine de gönder" goes into `decisions`.
- **4 Plan.** One step as JSON -> `tripo_plan.py '<step>' --chain <project>/.claude/tripo/assets/<id>.json`. Show 2-4 Turkish lines: model, input, face-budget decision, texture, estimate (`estimate.credits`, or "tahmin yok" when null, never 0), balance. Append the chain entry (`status: planned`) and the ledger row before the run; after it, `--chain-update <label>=<json>` and a full second ledger row with the real `consumed` and `task_id`. Measure triangles afterwards: `face_limit` is a hint (B8).
- **5 QA.** `--budget` from `profile.json` `budgets[class]`; `--game-cam` from `game_camera`; `--front` from the confirmed front (until confirmed, propose one from a feature). `--symmetric x` only once the model's left/right lies on world X (turn it with `normalize.py --yaw` first). Save `qa.json`, `sheet.png` and `report.md` under the model's own folder (`qa/raw/`, or `qa/vNN/` for `work/vNN`); look at the sheet yourself before reporting.
- **6 Fix.** Free fixes are prepared as a recipe preview without asking; applying them and every paid option wait for the one batched answer. Fixes are recipes replayed from the raw model (`apply_recipe.py`, ops in `fixkit/ops.py`, normals kept by `fixkit/normals.py`), never one-off scripts. QA again after every fix, before/after side by side.
- **7 Rig.** `rig_check` (free) runs alone on the final clean GLB; `riggable: false` -> stop, give the reason in one line, offer the image fix. `rig` with `model: v3.0`, `rig_type` from rig-check, `spec` per `rigging.md`. Then `glbstat.py`, `qa.py`, `godot_place.py rig_accept <project> <glb>`.
- **Lessons, when learned (spec 17).** A project lesson is written the moment it is learned, not saved for phase 9: right after a paid step's real numbers are known (triangles vs `face_limit`, credits), after each QA/fix decision (a Tripo defect and the recipe or route that fixed it, an image problem that caused a defect or turned out harmless), after any user correction (front axis, a profile value, a preference), and after a placement plan teaches something (a fit that shrank the model, a collision that no longer fits). `lessons.py add --project ...` without asking (project scope, reversible); `--cli`/`--model` `any` when the lesson is not version-bound. A task that stops early (no approval, user ends it) keeps its lessons. General promotion still waits for the one end-of-task message (section 8) and explicit approval (K4).
- **8 Placement.**
  - Normalize before export (and, for characters, before rig). With a recipe, its first step is the `normalize` op (`target_size`, `yaw`, `pivot`, `name`), then `bl.py export.py -- work/vNN.blend --out-model export/<id>.glb` (also writes `export.sh`; add `--max-texture 1024` when `TEXTURE_OVERSIZE` was answered with A, also on `normalize.py`). Without one: `bl.py normalize.py -- <raw glb> --out-model export/<id>.glb --yaw <deg> --target-size <normalize_target_size> --pivot bottom_center --name <id>`.
  - The target size is always `normalize_target_size` (from `aabb` or the plan's `before_after`), written `X,Y,Z`, **never the raw Godot `size`** (Blender is Z up; a raw size swaps height and depth).
  - Always `godot_place.py plan <project> <asset.json> export/<id>.glb` first. Show `scene_diff` (or, in `generator_script` mode, your own diff of the generator file from `generator_hint`) and the `before_after` table, plus its warnings. Ask once. Exit 2 on a naming pattern it cannot fill (e.g. a zone in `obj_<zone>_<id>`) -> pass `--copy-to <res path>` to both `plan` and `apply`.
  - After approval: `godot_place.py apply <project> <asset.json> export/<id>.glb --expect <plan_sha256>` with the `plan_sha256` of the plan the user saw. Never a bare `apply`. Exit 5 = refused or a check failed: show `step`, `tail`, `written`; nothing rolls back.
  - Then `log_asset.py <project> <asset.json> --glb export/<id>.glb --kind <kind>`; `create_needed: true` -> ask once, then `--create`. A re-run (resumed session) adds no second row (`already_logged: true`). A user-supplied raw goes in with its file hash, and the licence reads "unknown — owner to confirm" unless the user gives `--license`.

## 3. Approval rules (spec 18, K5, K14)

- Free, reversible work is done without asking: image review, measuring, rendering, dry-runs, preparing a Blender fix as a preview.
- Ask only for: credits (the lock window), a scene change, a global lesson, two truly equal options, applying a Blender fix (inside the batched question).
- Project lessons are written without asking, as soon as they are learned; only a general (global) lesson needs a yes.
- Never ask again what `profile.json` already answers. Short screen report: a few lines + a table, details in a file. Turkish to the user.
- **With the lock** (the session-start lock check printed `LOCK OK`): never ask separately before a paid step. Run the single-step command, written as hard rule 3 demands; the permission window is the approval (K14).
- **Without the lock** (the check failed): ask in chat once before every paid step, one Turkish line with step, estimate, balance and label, and run only after a yes.
- A denied window or a "no" is final for that step: do not retry it, record it in `decisions`, offer the free alternative.
- Multi-part objects: ask "tek parça mı, parçalı mı?" once with both prices (K7). Parts come only from Tripo (`generate_parts` or one piece + `segment`/`smartsegment`), never one image per part (K16).
- Every rig: ask the animation question once (K9). Every placement: diff first (K6). Never write a general lesson without approval (K4).

## 4. Report format (K10)

- On screen: 2-3 Turkish lines, one table, one batched question. Details go to `qa/vNN/report.md` (`qa/raw/report.md` for the raw model).
- The **first line of the first QA report confirms the front axis**, suggested from a feature ("Kapı bu tarafta, ön -Y mi?"). It is not a separate question; record the answer in `decisions` and pass `--front` from then on.
- Table: `# | sorun | ciddiyet | A (Blender, 0 kredi) | B (Tripo, kredi) | öneri`, most severe first; `info` rows only when they matter.
- One question for all rows, answered like "1A, 2B, 3 geç".

```
Ham model 17.430 üçgen (bütçe 15.000), arka yüzde ön detay kopyası var. Kapı bu tarafta, ön -Y mi?
| # | sorun | ciddiyet | A | B | öneri |
| 1 | arka yüzde ön kopyası | S1 | flatten_region (geometri düzelir, boya kalır) | retexture 10-30 | B |
| 2 | bütçe aşımı 1,16x | S1 | - | decimate v3.0 35 | B |
Hangileri? (ör. "1A, 2B, 3 geç")
```

## 5. State

- Update `assets/<id>.json` after every phase (`asset_state.py update <project> <id> --phase <phase> [--set ...] [--append ...] [--chain-update ...]`): chain entries, QA summaries, recipe path, every user decision.
- A cut-off or summarised conversation resumes from `asset_state.py get`: read `phase`, `chain`, `decisions`, and go on from there without redoing paid steps.
- Every paid step is in `ledger.jsonl` (planned, then real). `asset_state.py ledger <project> [--asset <id>]` gives the totals for credit questions; `tripo usage` and `tripo balance` give the account side.
- Never edit the state files by hand; only through `profile.py` and `asset_state.py`.
- Orchestrator contract (spec 8.2): the brief lives in `assets/<id>.json`; outputs are the placed GLB path, the `.blend`, `provenance.json`, the QA summary and the scene diff.

## 6. Hard rules

1. Every generation, texture, decimate and rig step passes `--model` explicitly; never `-p model=` (B10). Build steps with `tripo_plan.py`, never by hand.
2. One paid step per command (B17). The free `rig-check` runs on its own command too. The lock denies a command with two paid steps.
3. Run tripo only as a bare `tripo …`, or as the absolute path to the binary. Never through `mise exec`/`mise x`, `npm exec`/`npx`/`pnpm exec`, a script, a loop, a function, `xargs`/`find -exec` or a `$VAR`: the lock cannot price those, and it denies loops and repeaters outright. When `tripo` is not on PATH, fix PATH (`export PATH=<dir of the binary>:$PATH`) or use the absolute path; never a wrapper.
4. Name every task `--name <asset>-<kind>-vNN` (the step's `label`; bump `vNN` for every new paid attempt). Chain the next step from the printed `ref`.
5. Run tripo from the asset's raw folder, `<art_source>/<kind>/<id>/raw/<label>/` (create it first); the download lands in its `tripo-out/` (read `output_dir`/`files` from the JSON). Check that `.tripo/` is git-ignored.
6. No `@last` across sessions; use labels or task ids.
7. Re-roll cap: 2 regenerations per asset (B11). If the image caused the defect, fix the image first.
8. Front axis: confirmed in the first QA report line; never apply a side-specific fix before that.
9. Never `tripo redo`, `tripo ai`, `tripo batch run` or the `tripo mcp` tools: they skip the plan and the lock.
10. Normals are never recomputed globally (B7). `orientation`, `export_orientation`, `auto_size` are never sent to Tripo; direction, scale and pivot are set locally.
11. Exit-code policy for tripo (spec 16.2; full table in `tripo-cli.md` section 8):

| exit | action |
|---|---|
| 4 | insufficient credits: stop, suggest `tripo topup`; never top up yourself |
| 6 | watch timeout: `tripo task watch <id> --download`, never redo; task failed: report, a new run is a new paid step |
| 7 | network/server: check `tripo balance` and `tripo usage` first, no blind retry; download failure: `tripo task get <id> --download` |
| 9 | rate limit: wait, then retry |
| 1, 2, 3, 5, 8 | report; fix the step (2), sign in via `tripo doctor`/`tripo login` (3), change image or prompt (5), check the id (8) |

## 7. Script map

| script | use |
|---|---|
| `cli_watch.py` | version check, update, changelog slice, golden dry-runs |
| `tripo_plan.py` | build, dry-run and price one step; uses `scripts/data/prices.json` |
| `hooks/tripo_guard.py` | the credit lock (global PreToolUse hook); never call it yourself |
| `profile.py` | `detect`, `init` (budgets from `scripts/data/budgets.json`) |
| `asset_state.py` | `new`, `get`, `update`, `ledger` |
| `preflight_ref.py` | reference image checks; drives `blender/preflight_img.py` |
| `glbstat.py` | quick GLB/glTF stats, no Blender |
| `bl.py` | Blender runner for every `blender/*.py` script |
| `blender/qa.py` | QA metrics and findings (thresholds in `scripts/data/qa_thresholds.json`) |
| `blender/render_sheet.py` | the render sheet the agent looks at |
| `blender/normalize.py` | weld, yaw, uniform scale, pivot, names |
| `blender/apply_recipe.py` | replay a fix recipe from the raw model |
| `blender/export.py` | `.blend` -> Godot GLB + `export.sh` |
| `godot_place.py` | `aabb`, `plan`, `apply`, `rig_accept` (headless helpers `godot/aabb.gd`, `godot/rig_accept.gd`) |
| `log_asset.py` | `provenance.json` + the project's asset_log row |
| `lessons.py` | `add`, `candidates`, `promote`, `stale` |

Internal modules, never called directly: `common.py` (exit codes, project and profile lookup), `blender/_io.py` and its shim `blender/skill_io.py` (load any format, write JSON, fail cleanly), `blender/fixkit/normals.py` (NormalKeeper), `blender/fixkit/ops.py` (recipe operators).

## 8. End of task

1. Most project lessons are already written (phase note "Lessons, when learned"). Add what is still missing from this task (triangles vs `face_limit`, real vs estimated credits, a recipe that fixed a finding, an image problem and its fix, a first-paid-run answer, a user preference the profile lacks): `lessons.py add --project <project> --title ... --rule ... --evidence "<asset, task_id, date>" --cli <version> --model <wire id>`; the same title confirms instead of duplicating. Project lessons need no approval. Run this section also when the task stops before placement.
2. `lessons.py candidates --project <project>` -> put every candidate into **one** Turkish message ("Bu dersler genel olsun mu? 1) ... 2) ..."). Promote only the approved ones with `lessons.py promote ... --approved`; note refusals in `decisions` and never ask again.
3. Changes to the skill's own logic (a missing QA check, a wrong threshold, an outdated reference) are proposals, not lessons: write `~/Desktop/tripo-skill/docs/proposals/<YYYY-MM-DD>-<topic>.md` with the reason, the evidence and the diff. Applied and committed only when the user asks.
4. `asset_state.py update <project> <id> --phase done`.
