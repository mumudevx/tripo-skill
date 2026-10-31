# Tripo3D Animation Reference: rig-check, auto rig, retarget

Researched 2026-10-30 against tripo-cli v0.6.1 (`tripo`, region ov).
Sources:
- API docs: https://developers.tripo3d.ai/en/docs/animations-rig-check , `/animations-rig` , `/animations-retarget`
- Pricing: https://developers.tripo3d.ai/en/pricing
- Changelog: https://developers.tripo3d.ai/en/docs/changelog (2026-10 "Rigging v3.0 and retargeting upgrade")
- Convert: https://developers.tripo3d.ai/en/docs/models-convert ; Import: https://developers.tripo3d.ai/en/docs/models-import
- Bundled CLI docs: `<tripo-cli>/skill/commands/process.md`, `examples/animation.md`, `common-errors.md`
- CLI source: `<tripo-cli>/dist/knowledge/{models,chains,params,scenarios}.js`, `dist/core/requests.js`, `dist/pipeline/runner.js`
- Verified behavior: `tripo make ... --dry-run --json` runs, which cost nothing and use no network (results quoted below)

`<tripo-cli>` = `/Users/muhsin/.local/share/mise/installs/node/24.13.0/lib/node_modules/tripo-cli`

Anything not stated in a source is marked **UNKNOWN**.

---

## 0. TL;DR pipeline

```
model task (generate / import / decimate / texture ...)
   └─> rig-check  (FREE)   -> {riggable, rig_type}
         └─> rig  (25 cr)  -> animate_rig task (rigged GLB/FBX)
               └─> retarget (10 cr per animation, 1–5 per task) -> animate_retarget task (animated GLB/FBX)
                     └─> (optional) convert (5 basic / 10 advanced) -> FBX preset, in-place, orientation, scale
```

Cheapest full character: rig 25 + retarget N×10. For example, idle + walk + run = 25 + 30 = **55 credits**, not counting generation.

---

## 1. Rig Check: `POST /v3/animations/rig-check`

Source: https://developers.tripo3d.ai/en/docs/animations-rig-check

- Task type: `animate_prerigcheck`. Async, so poll the task or use a webhook.
- Purpose: tells you whether the model can be rigged and recommends a rig type.
- **Cost: free.** The doc example returns `"credits_consumed": 0.00`, and the pricing page lists "Rig Check: Free".

### Request

| Param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `input` | string | yes | none | Pass exactly one of: a task_id (from `text_to_model` / `image_to_model` / `multiview_to_model`), a file_token (`file_...`), or a public URL |

Input constraints: **GLB, FBX, OBJ, STL**, max **150 MB**. The changelog (2026-10) says: "rig-check now accepts GLB, FBX, OBJ, and STL (previously GLB only)."
There are no optional parameters.

### Output

| Field | Type | Values |
|---|---|---|
| `riggable` | boolean | true / false |
| `rig_type` | string | `biped` (humanoid, 2 legs), `quadruped` (4 legs), `hexapod` (6 legs), `octopod` (8 legs), `avian` (bird / winged), `serpentine` (snake-like), `aquatic` (fish / aquatic) |

Rig-check never returns `others`, but `rig` accepts it (see 2).

Example result:
```json
{"code":0,"data":{"task_id":"...","type":"animate_prerigcheck","status":"success",
 "output":{"riggable":true,"rig_type":"biped"},"credits_consumed":0.00}}
```

### What makes a model riggable

The doc gives no criteria beyond the `riggable` boolean (**UNKNOWN**). The doc does not explain why a model fails and returns no reason field.
The only riggability advice in the sources is from the CLI (see 6): use a T-pose prompt, or pre-generate a T-pose image with `text-to-image -p template=t_pose`.

### CLI

```bash
tripo anim check [input] --json          # input: task id / @last / @name / file / URL / piped JSON
tripo make <src> --then rig-check,...    # used as a gate step in chains
```

Chain behavior, from `dist/pipeline/runner.js`:
- Rig-check is a **passthrough** step: the next step receives the *model* task, not the rig-check task.
- If `riggable === false`, the chain **stops early** and spends no further credits.
- The recommended `rig_type` is **automatically copied into the following `rig` step** when you did not set `rig_type` yourself.

---

## 2. Auto Rig: `POST /v3/animations/rig`

Source: https://developers.tripo3d.ai/en/docs/animations-rig

- Task type: `animate_rig`. Async.
- **Cost: 25 credits.** This is the pricing page figure and matches the doc example `"credits_consumed": 25.00`. Per-model-version pricing is not listed. The changelog says "Credits are unchanged" for v3.0, so all versions cost 25 as far as the docs show.
- Docs recommend running rig-check first.

### Request

| Param | Type | Required | Default (server) | Allowed values / notes |
|---|---|---|---|---|
| `input` | string | yes | none | Exactly one of task_id / file_token / URL. Files: GLB, FBX, OBJ, STL, max 150 MB. GLTF is no longer listed (changelog 2026-10). |
| `model` | string | no | `v1.0-20240301` | `v1.0-20240301`, `v2.5-20260210`, `v3.0-20260909` (see the version table below) |
| `rig_type` | string | no | `biped` | `biped` `quadruped` `hexapod` `octopod` `avian` `serpentine` `aquatic` `others` (`others` means a skeleton that fits no named topology, added 2026-10) |
| `spec` | string | no | `tripo` | Bone naming convention. **Only applies when `rig_type=biped`.** Values: `tripo`, `mixamo`, `actorcore`, `unity`, `unreal`, `vrm` |
| `out_format` | string | no | `glb` | `glb` (binary glTF, web-ready) / `fbx` (DCC tools and game engines) |

The field is `model`. The API has no `model_version` field.

### Rig model versions

| Wire value | Rig types | Notes from the doc |
|---|---|---|
| `v1.0-20240301` (server default) | `biped` only | Comes with the **90+ biped presets** (`preset:biped:*`) |
| `v2.5-20260210` (**CLI default**) | Non-humanoid creatures: quadruped, hexapod, octopod, serpentine, aquatic, avian | "Bipeds work but are not recommended. Use v3.0 for humanoids." Uses the 11 generic + 5 creature presets |
| `v3.0-20260909` | **Recommended for `biped`**; also `others` | "Faster, higher-quality humanoid rigging. Other rig types match v2.5 quality and speed." Supports specs `actorcore`, `unity`, `unreal`, `vrm`. Same presets as v2.5. **Must be requested explicitly.** |

Marketing aliases, normalized by the CLI in `dist/knowledge/models.js`: `rig-v1.0` → `v1.0-20240301`, `rig-v2.0` / `rig-v2.5` → `v2.5-20260210`.
The server rejects these marketing names with a 400 if they are sent raw.
**The CLI has no alias for v3.0.** Pass the full wire value `v3.0-20260909`. The CLI passes unknown model strings through unchanged (verified by dry run).

### Spec and engine compatibility

Source: rig doc spec table. Engine fit is inferred only from the spec names.

| `spec` | Doc description | Target |
|---|---|---|
| `tripo` | Tripo native | Tripo's own naming. Engine-humanoid compatibility is **UNKNOWN** |
| `mixamo` | Mixamo-compatible | Mixamo animation libraries and anything that consumes Mixamo bone names |
| `actorcore` | ActorCore humanoid | Reallusion ActorCore |
| `unity` | Unity Humanoid | Unity Mecanim Humanoid avatar |
| `unreal` | Unreal Mannequin | UE Mannequin skeleton naming (UE4 vs UE5 mannequin: **UNKNOWN**) |
| `vrm` | VRM 1.0 humanoid | VRM avatars |

Specs other than `tripo` / `mixamo` are listed in the doc only under v3.0. Whether they work on v1.0 or v2.5 is **UNKNOWN**. Use `model=v3.0-20260909` with them.

**Godot:** Tripo docs do not mention Godot (**UNKNOWN**).
Not from Tripo docs (verify in the project): Godot 4's scene importer can retarget a humanoid skeleton to its `SkeletonProfileHumanoid` through a `BoneMap` in the Advanced Import dialog. Test a rigged GLB (try `spec=mixamo` or `spec=vrm`) by importing it into Godot before buying many animations.

### Output

`output.model_url` is the rigged model (GLB or FBX). Example: `{"type":"animate_rig","status":"success","output":{"model_url":".../rigged.glb"},"credits_consumed":25.00}`

Doc defect: the "v3.0 with VRM skeleton" cURL example actually sends `spec: "mixamo"`.

### CLI

```bash
tripo anim rig [input] [--rig-type <t>] [--spec <s>] [--out-format glb|fbx] [-p model=v3.0-20260909] --json
```

- First-class flags: `--rig-type`, `--spec`, `--out-format`. Use `-p model=...` for the version. `dist/commands/process-groups.js` picks `model, rig_type, spec, out_format`.
- CLI default `model` is `v2.5-20260210`, set in `CAPABILITY_DEFAULTS.rig`.
- The `--rig-type` help text lists only 7 values (no `others`), and `--spec` help lists only `tripo|mixamo`. Neither list is enforced: `RIG_TYPES` / `RIG_SPECS` are defined but never used for validation, so `others`, `unity`, `vrm` and similar values pass through. Dry-run verified:
  - `--then "rig:others;model=v3.0-20260909"` → payload `{"rig_type":"others","model":"v3.0-20260909"}`
  - `--then "rig:model=v3.0-20260909,spec=unity"` → payload `{"model":"v3.0-20260909","spec":"unity"}`
  - Nothing is validated, not even garbage: `--then "rig:rig_type=dragon;spec=bogus"` gives valid:true with payload `{"rig_type":"dragon","spec":"bogus"}`. The server catches typos, probably with a 1004. **The skill must check rig_type and spec values itself before submitting.**

`--then` syntax for rig: a bare value is `rig_type` (`rig:quadruped`). Separate key=value pairs with `;`, or with `,` when each pair contains `=`.

---

## 3. Animation Retarget: `POST /v3/animations/retarget`

Source: https://developers.tripo3d.ai/en/docs/animations-retarget

- Task type: `animate_retarget`. Async.
- **Cost: 10 credits per animation.** The pricing page says "10 per animation", the doc example shows `credits_consumed: 10.00`, and the CLI notes "billed per animation".
- 2026-10: the retarget endpoint switched to a new algorithm with "much better humanoid quality and speed". There is no new version and no request change.

### Request

| Param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `input` | string | yes | none | **task_id of a rig (`animate_rig`) task.** Only that: no file or URL. Error 2012 if it is not a rig task |
| `animation` | string | one of | none | One preset ID. Mutually exclusive with `animations` |
| `animations` | string[] | one of | none | **Up to 5** preset IDs. More than 5 is an error. Mutually exclusive with `animation` |
| `out_format` | string | no | `glb` | `glb` / `fbx` |
| `bake_animation` | boolean | no | none | **Deprecated and ignored.** Accepted only for backward compatibility. Do not send it |
| `export_with_geometry` | boolean | no | `true` | Include the mesh in the export. `false` presumably gives a skeleton plus animation only (exact behavior **UNKNOWN**) |
| `animate_in_place` | boolean | no | `false` | No root-motion displacement |

How a multi-animation result is packaged (one file with N clips vs. several files) is **UNKNOWN**. The doc shows one `output.model_url`.
Clip names inside the file are **UNKNOWN**.
Frame rate, clip length and looping are not documented (**UNKNOWN**).

### Preset catalogue

The preset set depends on which `model` the **upstream rig task** used.

**Rig v2.5-20260210 / v3.0-20260909 (16 presets):**

| Rig type | Presets |
|---|---|
| biped (generic, 11) | `preset:idle` `preset:walk` `preset:run` `preset:dive` `preset:climb` `preset:jump` `preset:slash` `preset:shoot` `preset:hurt` `preset:fall` `preset:turn` |
| quadruped | `preset:quadruped:walk` |
| hexapod | `preset:hexapod:walk` |
| octopod | `preset:octopod:walk` |
| serpentine | `preset:serpentine:march` |
| aquatic | `preset:aquatic:march` |
| avian | none listed (**UNKNOWN**; avian is a valid rig type, but the doc lists no avian preset) |
| others | none listed (**UNKNOWN**) |

The doc lists the 11 generic presets under "Biped". Whether they apply to non-biped rigs is **UNKNOWN**.
The CLI doc heading says "all rig types", which is ambiguous.

**Rig v1.0-20240301 (biped only, 101 presets, all `preset:biped:<name>`).** The full list comes from the expandable section of the retarget page. Groups follow the CLI doc's categories.

- basic/locomotion: `idle` `walk` `run` `run_upstairs` `turn` `jump` `jump_down` `jump_rope_01` `jump_rope_02` `fall` `climb` `dive` `swim` `surf` `flip` `sit` `standing_relax` `look_around` `wait` `swagger`
- dance: `dance_01` `dance_02` `dance_03` `dance_04` `dance_05` `dance_06` `freaky`
- performance: `sing_01` `sing_02` `sing_03` `sing_04` `cheer`
- emotion/social: `clap` `bow` `greet_01` `greet_02` `greet_03` `greet_04` `wave_goodbye_01` `wave_goodbye_02` `agree` `heart_pose` `hug` `fold_arms` `laugh_01` `laugh_02` `cry` `sob` `afraid` `frightened` `scared_01` `scared_02` `angry_01` `angry_02` `angry_03` `depressed` `frustrated_01` `frustrated_02` `complain_01` `complain_02` `victory_celebration` `defeat_02` `defeat_03`
- daily: `scratch` `make_a_call_01` `make_a_call_02` `play_mobile_game` `play_video_game` `dig` `chop` `shovel` `lift_heavy`
- sports: `warm_up` `press-up` (with a hyphen) `cross_body_crunch` `basketball_shot` `crossover_dribble` `dribble` `pitch_baseball` `golf` `volleyball` `football_catch` `football_save` `football_pass`
- combat: `box_01` `box_02` `box_03` `front_kick_01` `front_kick_02` `slash` `shoot` `fire` `cast_a_spell` `hurt` `hit_to_body_01` `hit_to_body_02` `hit_to_head` `hit_to_side` `hit_to_stomach` `flee_01` `flee_02`

There is no `defeat_01` (sic). The CLI list matches the web list once its `…` ranges are expanded.

### Choosing a rig version for a game character

- You need the big humanoid library (emotes, combat hits, sports): rig with `model=v1.0-20240301` (biped only) and use `preset:biped:*`.
- You need the best humanoid skeleton quality or engine-specific bone names: rig with `v3.0-20260909`. Only the 11 generic presets are available.
- Whether v1.0 presets work on a v3.0 rig is **UNKNOWN**. The doc ties the presets to the rig version, so assume they do not.
- For creatures, use `v2.5-20260210` or `v3.0-20260909` with the creature preset.

### CLI

```bash
tripo anim retarget <rig-task|@last> --animation preset:idle preset:walk preset:run [--out-format fbx] [--animate-in-place] --json
```

- `--animation <name...>` is variadic. One value becomes `animation`, several become `animations[]`.
- First-class retarget args are `animation`, `out_format`, `animate_in_place`. Send `export_with_geometry` with `-p export_with_geometry=false` on `tripo anim retarget`. Inside a chain, write it as a key: `--then "rig,retarget:preset:walk;export_with_geometry=false"`. Dry run verified: the payload gets `export_with_geometry:false` as a boolean.
- Local validation (`validateRetargetParams`): the list must not be empty and may hold at most 5 entries. A 1-item list is collapsed to `animation`. A missing animation is an error.
- **Preset IDs are NOT validated locally.** `retarget:preset:dance` passes the dry run (valid:true). Typos only fail on the server.
- In `--then`, the bare value is `animation`: `retarget:preset:walk`.

---

## 4. Post-processing animated models: convert

Source: https://developers.tripo3d.ai/en/docs/models-convert , pricing page

Convert accepts a rig or retarget task (the CLI counts `animate_rig` and `animate_retarget` as model-producing types).

| Param | Default | Animation relevance |
|---|---|---|
| `with_animation` | true | Keep skeleton and animation |
| `animate_in_place` | false | Strip root motion at export time |
| `fbx_preset` | `blender` | API: `blender` / `3dsmax` / `mixamo` / `bake_scale` (bakes scale into the geometry on FBX export). FBX only |
| `export_orientation` | `+x` | Set the forward axis here, as the last step |
| `format` | none | FBX is for "Unreal, Unity, DCC tools". **OBJ cannot hold animation** ("legacy exchange, no animation") |

- Convert cost: Basic 5, Advanced 10. Advanced is billed when any non-default value is set for face_limit / quad / flatten_bottom / threshold / texture_size / texture_format / pivot_to_center_bottom / scale_factor (pricing page).
- The CLI gives two separate signals, and neither fires for a format-only convert (`convert:format=FBX` is clean, dry-run verified):
  - `warnings`: `non-default convert options use the "complex convert" price tier`. From `params.js`. It fires when any convert arg differs from its default (this includes `fbx_preset` other than `blender`, `animate_in_place:true`, `with_animation:false`, `export_orientation` other than `+x`, and similar), or when `face_limit` / `part_names` is set. An explicit default such as `fbx_preset=blender` does not trigger it.
  - `cost_notes`: `non-default convert options bill as complex convert`. From `ai/plan-card.js`. It fires whenever the convert step has more than one arg, even if the extra arg is an explicit default (`format=FBX;fbx_preset=blender` gets the cost note but no warning).
  - The CLI's list is wider than the pricing page's: `fbx_preset` and `animate_in_place` are not on the pricing page's Advanced list. Whether they really bill at 10 is **UNKNOWN**. The CLI may be over-warning.
- `quad` forces FBX output.

---

## 5. Credits summary

Source: https://developers.tripo3d.ai/en/pricing. 1 credit = $0.01.

| Operation | Credits |
|---|---|
| Rig Check | **0 (free)** |
| Auto Rig (any version per docs) | **25** |
| Retarget | **10 per animation** (1–5 per task → 10–50) |
| Convert basic / advanced | 5 / 10 |
| Smart UV (keeps rig and animation) | 20 |
| Decimate (before rig) | v1.0 10 / v2.0 30 (default) / v3.0 35 tri, 40 quad (process.md) |
| Import model | **UNKNOWN** (not on the pricing page) |

Failed or cancelled tasks are not charged: frozen credits are refunded (billing doc).
With 35 credits available, one rig (25) plus one animation (10) uses the entire balance.

---

## 6. Input and pose requirements, quality levers

- **Pose:** the API docs state no pose requirement (**UNKNOWN** whether T or A pose is required).
  CLI guidance (`examples/animation.md`, `scenarios.js` anim tips): "prompt for a T-pose, or pre-generate with text-to-image template=t_pose". The example prompts use "T-pose, standing straight". `template=t_pose` (or `t_pose=true`) is called "the golden pre-step for the animation pipeline" in `commands/generate.md`.
  A-pose is not mentioned anywhere (**UNKNOWN**).
- **Formats and size:** GLB/FBX/OBJ/STL, max 150 MB, for both rig-check and rig. Retarget takes only a rig task id.
- **Polycount before rigging:** no doc limit or recommendation (**UNKNOWN**). The CLI chain allows `decimate` before `rig-check`/`rig`; dry run verified with `--then decimate:10000,rig-check,rig,retarget:preset:idle` (payload `face_limit:10000`, no model, so the server default decimate v2.0 at 30 credits applies). Decimating before rigging keeps skinning on the final low-poly mesh. That ordering is a recommendation, not a documented rule.
- **UVs after rigging:** Smart UV (`mesh uv`) "remaps existing textures, rigging and animation onto the new layout" (changelog). Its input must be at most 80k equivalent triangles.
- **Orientation:** do not set `export_orientation` at generation time if you will rig or retarget. Downstream steps do not inherit it and come out wrongly oriented without any error. Set it on a final `convert` (common-errors.md, generate.md).
- **Imported files are normalized.** `/models/import` returns `normalize_scale` and `normalize_translation`, and rig/post-processing with a file or URL input imports the file first (import doc). Expect the scale and position to change relative to the source file. Multiply back using these fields if real-world scale matters.
- **Quality levers:**
  - `model=v3.0-20260909` for humanoids (the doc's top recommendation; the CLI default v2.5 is "not recommended" for bipeds).
  - Use rig-check's `rig_type` and do not force a different one.
  - Pick a `spec` that matches the engine (`unity`, `unreal`, `mixamo`, `vrm`).
  - `animate_in_place=true` when game code drives movement.
  - `out_format=fbx` for Unity/Unreal; keep `glb` for Godot or web (the Godot preference is not from Tripo docs).

---

## 7. Failure modes and errors

Sources: `common-errors.md`, `dist/knowledge/error-catalog.js`, API docs.

| Code / exit | Meaning | Fix |
|---|---|---|
| 2011 (exit 2) | rig-check input task has no model output | Feed a model-producing task |
| 2012 (exit 2) | retarget only accepts a rig task | Run `rig` first; pass the rig task id |
| 2005/2006/2007 | Upstream task has the wrong type or did not succeed | Chain from a successful task of the right type |
| 1004 | Invalid parameter, e.g. marketing rig names sent raw (400), or non-GLB input to rig-check (stale note: rig-check now accepts FBX/OBJ/STL) | Use wire versions |
| 2004 | Unsupported file type (models: GLB/FBX/OBJ/STL max 150 MB; `.gltf` is not uploadable) | Upload `.glb` |
| 2010 (exit 4) | Insufficient credits | `tripo balance`; topping up is a human action |
| 2000 (exit 9) | Animation concurrency pool full (default 10 for rig-check/rig/retarget) | Wait |
| exit 6 | Task failed (refund) or watch timed out (still billed if it succeeds) | Failed: `tripo redo`. Timeout: `tripo task watch <id> --download`, never redo |
| `riggable:false` | Not riggable | Chain stops. Regenerate in T-pose (`template=t_pose`), or try `rig_type=others` on v3.0. Whether `others` succeeds on unriggable models is **UNKNOWN** |
| >5 animations | API error, also caught locally | Split into several retarget tasks on the same rig task |
| `animation` + `animations` together | Mutually exclusive | Send one |

Output URLs expire in about 5 minutes. Re-download with `tripo task get <id> --download`.

---

## 8. Verified CLI recipes (all checked with `--dry-run --json`, zero credits)

```bash
# Scenario preset: text→model(v3.1, PBR) → rig-check → rig(v2.5, spec=tripo, glb) → retarget [idle, walk]
tripo make "a knight in full armor, T-pose" --for anim --dry-run --json

# Humanoid, best quality, Unity Humanoid bone names
tripo make "a knight, T-pose" --then "rig-check,rig:model=v3.0-20260909;spec=unity,retarget:preset:walk" --dry-run --json

# Mixamo naming, FBX, in-place run
tripo make "a knight, T-pose" --then "rig:biped;spec=mixamo;out_format=fbx,retarget:animation=preset:run;animate_in_place=true;out_format=fbx" --dry-run --json

# Creature. Warning emitted: "--then overrides the default anim processing chain" (with --then, --for anim only adds texture:true,pbr:true).
# The explicit rig:quadruped is NOT replaced by rig-check's recommendation (autofill only when rig_type is unset).
tripo make "a wolf" --for anim --then "rig-check,rig:quadruped,retarget:preset:quadruped:walk" --dry-run --json

# Large v1.0 biped library
tripo make "a knight" --then "rig:model=rig-v1.0,retarget:preset:biped:dance_01" --dry-run --json

# Existing local file (imports first: endpoint /v3/models/import, pending upload)
tripo make ./hero.glb --then rig-check,rig,retarget:preset:walk --dry-run --json

# Low-poly first, then rig. decimate without model= uses server default v2.0 (30 credits; v3.0 35, v1.0 10 per process.md)
tripo make "a knight, T-pose" --then "decimate:10000,rig-check,rig,retarget:preset:idle" --dry-run --json

# Rig → retarget → Mixamo FBX convert, root motion stripped
tripo make "a knight, T-pose" --then "rig:spec=mixamo,retarget:preset:run,convert:format=FBX;fbx_preset=mixamo;animate_in_place=true" --dry-run --json
```

Several animations on one rig: use the standalone command, which has **no `--dry-run`**:
`tripo anim retarget <rig_task_id> --animation preset:idle preset:walk preset:run --json`
The other route is `--for anim`, which hard-codes `[idle, walk]`.

---

## 9. Doc vs CLI mismatches

1. **Default rig model.** Server default is `v1.0-20240301`; the CLI silently defaults to `v2.5-20260210`. The API doc says v2.5 is "not recommended" for bipeds and recommends `v3.0-20260909`. The CLI has no v3.0 alias or default, so pass `model=v3.0-20260909` explicitly for humanoids.
2. **`spec` values.** API: tripo/mixamo/actorcore/unity/unreal/vrm. CLI help and process.md: `tripo|mixamo` only. The CLI does not enforce the list, so the extra values pass through (dry-run verified).
3. **Unity advice.** process.md and examples/animation.md say "Unity Humanoid → `--spec mixamo`". The API now has `spec=unity` (Unity Humanoid) on v3.0.
4. **`rig_type`.** The API adds `others`. CLI help, process.md and `RIG_TYPES` list only 7 values. Not enforced, so `others` passes through.
5. **rig-check input.** CLI help ("GLB input"), process.md ("GLB only") and common-errors.md ("non-GLB input to rig-check" is a 1004) are stale. The API now accepts GLB/FBX/OBJ/STL (changelog 2026-10). The dry run with an `.fbx` file is valid.
6. **`bake_animation`.** process.md says "default true, glb only". The API doc says it is **deprecated and ignored**.
7. **Preset version labels.** process.md says "Presets for rig v2.0 / v2.5". The API says v2.5 / v3.0. "rig-v2.0" is a marketing alias that maps to v2.5.
8. **`fbx_preset=bake_scale`.** Documented in the convert API, but rejected locally by the CLI ("fbx_preset must be one of blender/3dsmax/mixamo"; dry-run exit 2).
9. **Multiple animations inside `--then`.** Not expressible. Commas split steps, so a JSON array breaks parsing: the CLI throws an uncaught `Error: unknown step ""preset"` with a stack trace (exit 1, no JSON on stdout). With `retarget:preset:idle;preset:walk` the **last value silently wins**: the payload contains only `preset:walk`. `make -p animations=[...]` goes to the *generation* payload, not to retarget. Use `tripo anim retarget --animation a b c` instead.
10. **No `--dry-run` on `tripo anim *`.** Only `tripo make` has `--dry-run`. Validate through `tripo make <src> --then ... --dry-run --json`.
11. **Rig file inputs in make.** `tripo make file.glb --then rig...` adds an explicit `import` step (`/v3/models/import`) first. The API rig endpoint can take a file token directly. Import credit cost is **UNKNOWN**.
12. **Rig doc example label.** The "v3.0 with VRM skeleton" cURL example sends `spec: "mixamo"` (a doc defect).

---

## 10. Unknowns to resolve with a real run (costs credits, so ask the user first)

- Clip naming and packaging for multi-animation retarget output (one file vs several; clip names).
- Whether v1.0 `preset:biped:*` presets work on a v3.0 rig.
- Avian and `others` presets: none are listed.
- Whether the generic presets (idle/run...) apply to non-biped rigs.
- What `export_with_geometry=false` returns.
- Skeleton bone count, max influences per vertex, and the scale or units of the rigged output.
- Godot import behavior for each spec.
- Import task credit cost.

---

## Verified via dry-run (2026-10-30)

Adversarial re-check against the installed tripo-cli v0.6.1. Every command was run with `--dry-run --json` only (no network, no credits). Exit codes were captured directly.

| # | Command (`--dry-run --json` appended) | valid | Exit | Warnings / errors | Key payload facts |
|---|---|---|---|---|---|
| 1 | `make "a knight in full armor, T-pose" --for anim` | true | 0 | none | t2m `v3.1-20260211` texture+pbr; rig `{model:v2.5-20260210, spec:tripo, out_format:glb}` (no rig_type, so rig-check fills it); retarget `animations:[preset:idle,preset:walk]`; deliverables GLB, FBX |
| 2 | `make "a knight, T-pose" --then "rig-check,rig:model=v3.0-20260909;spec=unity,retarget:preset:walk"` | true | 0 | none | rig `{model:v3.0-20260909, spec:unity}`; retarget `animation:preset:walk` |
| 3 | `make "a knight, T-pose" --then "rig:biped;spec=mixamo;out_format=fbx,retarget:animation=preset:run;animate_in_place=true;out_format=fbx"` | true | 0 | none | rig `{rig_type:biped, spec:mixamo, out_format:fbx, model:v2.5-20260210}`: no model was given, so the biped gets v2.5 (not recommended for bipeds). Add `model=v3.0-20260909` for quality. Retarget `{animation:preset:run, animate_in_place:true, out_format:fbx}` |
| 4 | `make "a wolf" --for anim --then "rig-check,rig:quadruped,retarget:preset:quadruped:walk"` | true | 0 | warning: `--then overrides the default anim processing chain` | t2m texture+pbr kept; rig `{rig_type:quadruped, model:v2.5-20260210}`; retarget `preset:quadruped:walk` |
| 5 | `make "a knight" --then "rig:model=rig-v1.0,retarget:preset:biped:dance_01"` | true | 0 | none | alias normalized: rig `model:v1.0-20240301` |
| 6 | `make ./hero.glb --then rig-check,rig,retarget:preset:walk` | true | 0 | none | first step `import` → `/v3/models/import` `input:<upload:./hero.glb>`; `pending_uploads:["./hero.glb"]`; rig model v2.5 |
| 7 | `make "a knight, T-pose" --then "decimate:10000,rig-check,rig,retarget:preset:idle"` | true | 0 | none | decimate `/v3/mesh/decimate` `highpoly_to_lowpoly` `{face_limit:10000}` (no model, so server default v2.0 at 30 credits) |
| 8 | `make "a knight, T-pose" --then "rig:spec=mixamo,retarget:preset:run,convert:format=FBX;fbx_preset=mixamo;animate_in_place=true"` | true | 0 | warning + cost_note: non-default convert options use the "complex convert" tier | convert `{format:FBX, fbx_preset:mixamo, animate_in_place:true}`; rig model v2.5 |
| 9 | `make "a robot arm" --then "rig:others;model=v3.0-20260909"` | true | 0 | none | rig `{rig_type:others, model:v3.0-20260909}` passes through |

Extra spot checks:

| Command / claim | Result |
|---|---|
| `--then "rig:model=v3.0-20260909,spec=unity"` (comma form) | valid; payload `{model:v3.0-20260909, spec:unity}`. Confirms the comma key=value syntax |
| `--then "rig,retarget:preset:dance"` (bogus preset) | valid:true. Confirms that preset IDs are not validated locally |
| `--then "rig,retarget:preset:idle;preset:walk"` | valid; payload `animation:preset:walk`. Confirms that the last value silently wins |
| `--then 'rig,retarget:animations=["preset:idle","preset:walk"]'` | uncaught `Error: unknown step ""preset"`, stack trace, exit 1, no JSON. Corrected in section 9 |
| `--then "rig,retarget:preset:idle,convert:format=FBX;fbx_preset=bake_scale"` | valid:false, exit 2, `convert: fbx_preset must be one of blender/3dsmax/mixamo`. Confirmed |
| `--then "rig,retarget"` (no animation) | valid:false: `retarget requires animation (single) or animations (list)` |
| `make ./hero.fbx --then rig-check,rig` | valid. Confirms that FBX reaches rig-check after import |
| `tripo anim --help`, `anim check/rig/retarget --help` | No `--dry-run` on any `anim` subcommand. `check` says "(GLB input)". `rig`: `--rig-type` lists 7 values, `--spec tripo\|mixamo`, `--out-format`. `retarget`: `--animation <name...>` (≤5), `--out-format`, `--animate-in-place`. All confirmed |
| `tripo docs --topic commands/process` | Confirms the stale claims: "GLB only" for rig-check, `spec tripo/mixamo`, `bake_animation (default true, glb only)`, "Mixamo / Unity Humanoid → --spec mixamo", heading "Presets for rig v2.0 / v2.5 (all rig types)", fbx_preset `blender/3dsmax/mixamo` only |
| `tripo docs --topic common-errors` | Confirms 2011/2012 exit 2, 2000 exit 9 with an animation pool of 10, 2010 exit 4, 1004 "non-GLB input to ... rig-check", output URLs expiring in about 5 min, and the export_orientation warning |
| `tripo docs --topic commands/generate` | Confirms that `template=t_pose` / `t_pose=true` is "the golden pre-step for the animation pipeline" |
| Source `dist/knowledge/models.js` | Aliases `rig-v1.0`, `rig-v2.0`, `rig-v2.5` exist and there is no v3.0 alias. `CAPABILITY_DEFAULTS.rig = v2.5-20260210`. `RIG_TYPES` / `RIG_SPECS` are defined but referenced nowhere else (not enforced) |
| Source `dist/pipeline/runner.js` | rig_type autofill only when `args.rig_type === undefined`; `riggable === false` stops the chain; rig-check is a passthrough. All confirmed |
| Source `dist/knowledge/params.js` `validateRetargetParams` | Empty list is an error, more than 5 is an error, a 1-item list collapses to `animation`. Confirmed |

### Second adversarial pass (2026-10-31)

All 9 recipes above were re-run with `--dry-run --json` (no `--yes` needed, no network). Results matched rows 1–9 exactly: all valid:true, exit 0, same payloads. The only warnings were the anim-override warning on #4 and the complex-convert warning on #8.
The help texts (`anim`, `anim check/rig/retarget`, `make`), `commands/process`, `commands/generate`, `examples/animation`, `common-errors`, `models.js` (aliases, `CAPABILITY_DEFAULTS`, unused `RIG_TYPES`/`RIG_SPECS`, `FBX_PRESETS`), `runner.js` (autofill, stop, passthrough) and `validateRetargetParams` were all re-checked and match.

New findings and corrections from this pass:

| Command / claim | Result |
|---|---|
| `--then "rig,retarget:preset:walk,convert:format=FBX"` | valid. **No warning and no cost_note.** A format-only convert counts as basic. Section 4 corrected: earlier it said the CLI warns on any extra arg |
| `--then "...,convert:format=FBX;fbx_preset=blender"` (explicit default) | valid. `warnings: []`, but `cost_notes` still says "bill as complex convert". The two signals use different logic (params.js checks for non-default values; plan-card.js checks for more than one arg). Documented in section 4 |
| `--then "rig,retarget:preset:walk;export_with_geometry=false"` | valid; payload has `export_with_geometry:false` (boolean). Section 3 updated: the key also works inside `--then`, not only through `-p` |
| `--then "rig:rig_type=dragon;spec=bogus"` | valid:true, passes straight through. Section 2 updated: rig_type/spec get no local validation at all |
| `--then "rig,retarget"` (no animation) | valid:false, exit 2, as before. Quirk: `cost_notes` still says "retarget 1 animation(s)" on the invalid plan |
| `--then 'rig,retarget:animations=["preset:idle","preset:walk"]'` | Re-confirmed: exit 1, stdout empty, stderr `Error: unknown step ""preset"` |
