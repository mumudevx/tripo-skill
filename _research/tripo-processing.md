# Tripo model processing reference (texture, segment, smartsegment, complete, decimate, uv, convert, import)

Scope: every Tripo v3 model-processing endpoint that a game-asset skill uses to detect and fix problems after generation.
Sources, read in full on 2026-10-30:
- Official docs: `https://developers.tripo3d.ai/en/docs/<page>`. The full server-rendered HTML was downloaded and read. WebFetch only returned summaries, so it was not used as the source.
- Official pricing page: `https://developers.tripo3d.ai/en/pricing`. This is the only place that lists credit costs for texture, convert and completion.
- Bundled CLI docs and source for tripo-cli v0.6.1: `<npm-global>/tripo-cli/skill/commands/process.md`, `commands/make.md`, `examples/pipes.md`, `examples/game-asset.md`, `common-errors.md`, plus `dist/knowledge/{params,chains,models}.js`, `dist/core/requests.js` and `dist/commands/process-groups.js`.
- Offline checks: `tripo make <file|task> --then ... --dry-run --json`. This makes no network calls and spends no credits.

Anything the sources do not state is marked **UNKNOWN**. Statements derived from the docs rather than quoted are marked **(derived)**.

---

## 0. Cross-cutting facts

### 0.1 Base URL, async model, task result shape
- Base URL: `https://openapi.tripo3d.ai/v3`. Auth: `Authorization: Bearer <key>`.
- Every endpoint below is asynchronous. A POST returns `{"code":0,"data":{"task_id":"..."}}`. You then poll the task, or use a webhook.
- The result is in `data.output`. Most steps return `model_url` and `rendered_image_url`. Exceptions: uv returns `uv_render_url`; smartsegment returns `seg_model_url`, `mask_url` and others.
- Output URLs expire after about 5 minutes (common-errors.md). Never cache them. Re-fetch with `tripo task get <id> --download`.

### 0.2 The `input` field (shared by texture, segment, decimate, uv, convert)
Exactly one of the following:
- `task_id`. The docs say "returned by a previous 3D generation task (`text_to_model`, `image_to_model`, `multiview_to_model`)". The CLI accepts any model-producing task type as upstream: `text_to_model, image_to_model, multiview_to_model, refine_model, texture_model, stylize_model, convert_model, import_model, highpoly_to_lowpoly, mesh_segmentation, mesh_completion, mesh_edit, mesh_uv, animate_rig, animate_retarget`. Whether the server accepts every one of these for every endpoint is **UNKNOWN** from the docs. The CLI's own recipes chain `decimate → uv` and `segment → convert part_names`, so at least those pairs are intended.
- `file_token`, from the File Upload API.
- A public URL.
- Formats: GLB, GLTF, FBX, OBJ, STL. Maximum size **150 MB**.
- common-errors.md: `.gltf` files cannot be uploaded because they reference external files. Upload `.glb`, or pass a `.gltf` as a URL. File tokens are short-lived (error 2019).
- When a step receives a `file_token` or URL, the server imports the model first. Such tasks return `normalize_scale` and `normalize_translation` (see §8).

### 0.3 Billing model
From https://developers.tripo3d.ai/en/docs/billing:
- Credits are frozen when the task is created. They are deducted on success, and returned if the task fails or is cancelled.
- 1 credit = $0.01 (pricing page).

### 0.4 Credit cost table for processing
Source: https://developers.tripo3d.ai/en/pricing

| Operation | Credits | Notes |
|---|---|---|
| Texture (Fast) | 10 | `texture_quality=fast`, needs texture model `v3.5-20260815` |
| Texture (Standard) | 10 | `texture_quality=standard` |
| Texture (HD) | 20 | Presumably `texture_quality=detailed`. The label mapping is (derived). |
| Texture (8K Ultra) | 30 | `texture_quality=extreme` |
| Format Convert (Basic) | 5 | All options at their defaults |
| Format Convert (Advanced) | 10 | Any non-default value of: `quad, face_limit, flatten_bottom, flatten_bottom_threshold, texture_size, texture_format, pivot_to_center_bottom, scale_factor` |
| Retopology v3.0 Triangle | 35 | `mesh/decimate model=v3.0` |
| Retopology v3.0 Quad | 40 | `model=v3.0, quad=true` |
| Retopology v2.0 Smart | 30 | Server default |
| Retopology v1.0 Basic | 10 | |
| Smart UV | 20 | `mesh/uv` |
| Segmentation | 40 | `mesh/segment`. The doc example result also shows `credits_consumed: 40.00`. |
| Part Completion (Default) | 50 | `completion_mode=ai_completion` |
| Part Completion (Quick Cap) | 30 | `completion_mode=quick_cap` |
| Smart Segmentation (Image) | 85 | `seg_type=image` |
| Smart Segmentation (Model) | 55 | `seg_type=model` |
| Import Model | **UNKNOWN** | Not on the pricing page. `tripo make <file>` always creates an import task, so check `credits_consumed` after the first real run. |
| Rig Check / Auto Rig / Retarget | Free / 25 / 10 per animation | Listed for context; covered in the animation note |

Budget reality: the account has about 35 credits. That covers one texture (10–30), one plain convert (5), one decimate v1.0 (10), or one uv (20). It does **not** cover segment (40), complete (50), smartsegment (55/85), or decimate v3.0 quad (40). Decimate v2.0 (30) or v3.0 tri (35) fits only if nothing else runs.

### 0.5 CLI surface for processing
- Direct commands: `tripo model texture|convert|import|refine`, `tripo mesh segment|complete|decimate|uv|smartsegment`.
- Input resolution order: explicit argument (task id / `@last` / `@name` / file / URL) > piped NDJSON task from stdin > `@last`.
  - **Gotcha:** if you run a direct command with no input argument and nothing piped, it silently uses `@last`.
- Shared options: `-o, --out <dir>`, `--no-wait`, `--no-download`, `--notify`, `--timeout <s>`, `--name <name>`, `-p, --param key=value` (repeatable), `--json`, `--yes`, `--quiet`, `--no-open`, `--profile`.
- `-p` on direct commands parses JSON when the value starts with `[` or `{`. Example: `-p 'part_names=["tripo_part_0"]'` and `-p 'texture_prompt={"text":"worn leather"}'`. Values `true` and `false` become booleans, and digit strings become numbers.
- **Direct commands have NO `--dry-run`.** Only `tripo make` supports `--dry-run`. To validate a processing step offline, use:
  `tripo make <task-id|file.glb|@name> --then <steps> --dry-run --json`
  A plan that fails validation exits with code 2, `valid:false` and `errors[]`. For **any bare task id (UUID)**, chain legality is reported as "unverified" in `warnings`, **even when that id is in `~/.tripo/history.jsonl`**. The bare-id path never looks up local history (re-verified 2026-10-31). Example: `@last` resolves to `41d58880-… (multiview_to_model)`, and `tripo make @last --then complete` is `valid:false`. `tripo make 41d58880-… --then complete` with the same id is `valid:true`, with only the "unverified … no local history" warning.
  - **Skill rule:** always dry-run with `@last` or `@name`, never the raw UUID. Otherwise illegal chains such as `complete` after a non-segment task pass locally and fail on the server.
  - **Exception (verified 2026-10-30):** a `--then` string that fails to *parse* (an unknown step name such as `edit` without the env var, or an array with two or more items) does **not** produce JSON. The CLI prints `✗ Error: unknown step ...` and a stack trace to stderr and exits with code **1**, not 2. A skill that parses stdout as JSON must handle exit 1 with empty stdout.
  - **`cost_notes` are only filled for convert.** Dry-runs of texture, decimate, uv, segment and complete return `cost_notes: []` and no credit total. Credit estimates must come from the table in §0.4, not from the dry-run.
- Subcommand help: `tripo model texture --help`, `tripo mesh decimate --help` and so on **do** print the subcommand flags (verified 2026-10-30). `tripo model help texture` works too. (An earlier version of this note said `--help` printed the top-level help. That was a test artefact: in zsh, an unquoted `$c="model texture"` is passed as one argument, so commander saw an unknown command.)
- **Gotcha: `tripo make <file.glb> --then ...` always adds an `import` task first** (`POST /v3/models/import`), and its cost is UNKNOWN. A direct command such as `tripo model texture file.glb` uploads the file and passes the `file_token` straight to the step, with no separate import task.

### 0.6 `--then` syntax (tripo make)
- Steps are comma-separated. Valid steps: `refine, texture, convert, import, rig-check (aliases check/rigcheck), rig, retarget (alias animate), segment, complete, decimate (alias lowpoly), uv, smartsegment`. The hidden `edit` step needs `TRIPO_EXPERIMENTAL_MESH_EDIT=1`.
- Step arguments use the form `step:key=value,key=value`. A comma-separated token that contains `=` and is not a step name is treated as another argument of the previous step.
- A bare value sets the step's primary argument:

| Step | Primary argument |
|---|---|
| convert | format |
| decimate | face_limit |
| texture | texture_quality |
| segment | model |
| smartsegment | granularity |
| rig | rig_type |
| retarget | animation |

  Example: `convert:fbx`, `decimate:5000`, `texture:detailed`, `segment:v2.0-20260430`.
- `--then` only coerces `true`, `false` and numbers. **JSON is not parsed**, and a comma always splits tokens, so:
  - `part_names=[...]` with two or more names cannot be expressed in `--then`. The parse fails with `unknown step ""tripo_part_1"]"` (exit 1, no JSON).
  - `part_names=["tripo_part_0"]` with **one** name passes the dry-run (`valid:true`), but the payload carries the **string** `"[\"tripo_part_0\"]"`, not an array. Treat it as broken too.
  - A bare `part_names=tripo_part_0` (no brackets) is also sent as the **string** `"tripo_part_0"`, not `["tripo_part_0"]`, and still gives `valid:true` (verified 2026-10-31 on convert).
  - `texture:texture_prompt={"text":"..."}` is sent as a **string**, not an object. The dry-run reports it as valid, but the server will most likely reject or misread it (behaviour UNKNOWN).
  - Use direct commands with `-p` for any object or array parameter.
- `tripo make ... -p key=value` applies to the **generation** step only. It is not forwarded to `--then` steps. Verified: `tripo make file.glb --then texture -p 'texture_prompt=...'` produced a texture payload without `texture_prompt`.

---

## 1. Texture: `POST /v3/models/texture` (task type `texture_model`)
Source: https://developers.tripo3d.ai/en/docs/models-texture

Regenerates the texture maps of an existing model. Geometry is kept.

| Param | Type | Default | Allowed / constraints |
|---|---|---|---|
| `input` | string | required | task_id / file_token / URL (§0.2) |
| `model` | string | `v3.0-20250812` | `v3.5-20260815` is the newest and is **required** for `texture_quality=fast` and for `delight`. `v3.0-20250812` is recommended for meshes from v3.0-20250812 or v3.1-20260211. `v2.5-20250123` is recommended for meshes from v2.5-20250123. |
| `texture_prompt` | object | none | Optional if the model came from Tripo. Use exactly one of `text`, `image` or `images`. |
| `texture_prompt.text` | string | | Example: `{"text":"worn leather with scratches"}` |
| `texture_prompt.style_image` | file_token or url | | Only together with `text`. At least 256×256 px recommended. Example: `{"text":"cyberpunk style","style_image":{"url":"https://..."}}` |
| `texture_prompt.image` | file_token or URL | | A single reference image |
| `texture_prompt.images` | array | | Multi-view references, in one of two formats. **view-key (recommended):** `[{"front":"https://..."},{"left":"file_..."}]`. Each value is a URL, a file_token, `{url}`, `{file_token}` or `{object:{bucket,key}}`. Order does not matter. **positional:** 4 items in the order `[front, left, back, right]`, with `null` or `""` for a missing view. `front` is required and **at least 2 views** are needed. Do not mix the two formats. |
| `pbr` | boolean | `true` | Generates PBR materials |
| `texture_seed` | integer | random | The same seed gives identical textures. To keep geometry and change only the texture, keep `model_seed` and vary `texture_seed`. |
| `texture_alignment` | string | `original_image` | `original_image` matches the input image colours. `geometry` matches the generated geometry. |
| `texture_quality` | string | `standard` | `fast` (v3.5 only, same texture size and same price as standard), `standard`, `detailed`, `extreme` (8K, costs more than detailed). `fast` on any other texture model returns error `1004`; it does not fall back. |
| `part_names` | string[] | all parts | Part names from an earlier mesh segmentation task |
| `compress` | string | none | `geometry` applies meshopt compression |
| `bake` | boolean | `true` | Bakes advanced material effects into the base textures |
| `delight` | boolean | `true` | Removes baked-in lighting from the reference image. Only `v3.5-20260815` reads it; older models ignore it. |

- Doc note: when texturing from an existing task_id, re-supplying the reference image is **strongly recommended**.
- Result: `output.model_url` (PBR GLB) and `output.rendered_image_url` (preview PNG).
- Cost: fast or standard 10, detailed (HD) 20, extreme (8K) 30.

**Defects it fixes:**
- Blurry, smeared or low-resolution texture: use `detailed` or `extreme`.
- Baked lighting or shadows in the albedo: use `delight=true`, which needs v3.5. See the CLI mismatch in §10.
- Texture colours that do not follow the geometry, such as seams or features painted in the wrong place: use `texture_alignment=geometry`.
- Wrong style or colour: use `texture_prompt.text`, optionally with `style_image`.
- Back side invented badly: use `texture_prompt.images` with several views.
- One part looks wrong: use `part_names` after `segment`.
- A family of assets drifts in style: use the same `style_image` or reference set and a fixed `texture_seed` (derived).
- Untextured imported model: run texture on the import (file/URL input).

**CLI:**
```bash
tripo model texture <task|@name|file|url> --texture-quality detailed --texture-alignment geometry \
    [-p pbr=true] [-p texture_seed=42] [-p 'texture_prompt={"text":"hand-painted stylized wood"}'] \
    [-p 'part_names=["tripo_part_0"]'] [-p model=v2.5-20250123]
# chain form (no objects/arrays possible):
tripo make <task|@name> --then texture:detailed,texture_alignment=geometry --dry-run --json
```
First-class flags are only `--texture-quality` and `--texture-alignment`. Everything else goes through `-p`.

**Texture gotchas:**
- Retexturing is the cheap fix for style problems. Keep a good mesh and retexture it rather than regenerating it.
- `extreme` (8K) is usually overkill for games. Pair it with convert `texture_size` to downsize, which counts as advanced convert (10 credits).

---

## 2. Mesh Segmentation: `POST /v3/mesh/segment` (task type `mesh_segmentation`)
Source: https://developers.tripo3d.ai/en/docs/mesh-segment

Splits an existing model into parts.

| Param | Type | Default | Allowed / constraints |
|---|---|---|---|
| `input` | string | required | task_id / file_token / URL (§0.2) |
| `model` | string | `v1.0-20250506` | `v1.0-20250506` is geometry-based. `v2.0-20260430` is **Beta** and does semantic segmentation with labelling. |
| `segmentation_granularity` | string | `balanced` | **v2 only.** `simple`, `balanced` or `detailed`. |
| `split_by_connectivity` | boolean | `true` | **v2 only.** Splits by connected components. |
| `ref_image` | string | | **v2 only.** A file_token or public URL. The doc's illustration shows a segmentation **mask** image used as `ref_image`. When it is set, `segmentation_granularity` and `split_by_connectivity` are **ignored**. Setting it on v1 returns error `1004` (common-errors.md / process.md). |

- Result: `output.model_url` (segmented GLB, e.g. `mesh_seg.glb`), `output.rendered_image_url` (`.webp`), `credits_consumed: 40.00`.
- Part naming: node names in the output GLB, such as `tripo_part_0` and `tripo_part_1` (from the mesh-complete page). Whether v2 semantic labels change the node names is **UNKNOWN**.
- Cost: 40.

**Use cases:**
- Prerequisite for `mesh/complete`.
- Per-part texture (`texture part_names`), per-part decimate (`decimate part_names`, v2.0/v3.0 only) and per-part export (`convert part_names`).
- Splitting an asset into pieces for a disassembled or interactive game object (derived).

**CLI:**
```bash
tripo mesh segment <task|file|url> [--model v1.0-20250506|v2.0-20260430] \
    [-p segmentation_granularity=detailed] [-p split_by_connectivity=false] [-p ref_image=<file_token|url>]
tripo make <task> --then segment:v2.0-20260430 --dry-run --json
```
`--model` is validated locally against `v1.0-20250506` and `v2.0-20260430`. `ref_image` through `-p` must already be a file_token or URL, because the CLI does not upload it. Whether the CLI auto-uploads a local path here is UNKNOWN; from the source, `-p` values are passed through untouched.

---

## 3. Smart Segmentation: `POST /v3/mesh/smartsegment` (task types `smartsegment_image` / `smartsegment_model`)
Source: https://developers.tripo3d.ai/en/docs/mesh-smartsegment

An end-to-end pipeline: asset, then automatic modelling, then segmentation. It differs from `/mesh/segment`, which only segments an existing model.

| Param | Type | Default | Allowed / constraints |
|---|---|---|---|
| `seg_type` | string | **required** | `image` takes PNG/JPEG/WebP and builds a model, then segments it. `model` takes **GLB only** and requires `transform`. |
| `input` | string | required | **file_token** (from File Upload or Presign Upload) **or public URL only. Task ids are NOT accepted.** For `seg_type=model` the file must be GLB. |
| `granularity` | string | `medium` | `coarse`, `medium` or `fine` |
| `hint` | string | | Free text that helps identify the parts, e.g. `"game character with sword and armor"` |
| `transform` | number[16] | conditional | **Required when `seg_type=model`.** A column-major 4×4 matrix. Identity: `[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]`. |

- Result: `output.prompt` (comma-separated part labels, e.g. `"head, body, left arm, right arm, legs"`), `output.mask_url` (PNG semantic mask), `output.seg_model_url` (segmented GLB), `output.seg_task_id` (inner segmentation task), `output.model_task_id` (inner image_to_model or import task), and `input.granularity`. Example `credits_consumed: 85.00` for the image pipeline.
- Cost: image 85, model 55.
- **(derived)** The inner `seg_task_id` is a segmentation task, so it should be usable as input to `mesh/complete`. Not verified; **UNKNOWN**.

**CLI:**
```bash
tripo mesh smartsegment <file.glb|url> [--seg-type model|image] [--granularity coarse|medium|fine] [--hint "..."]
```
- The CLI defaults `--seg-type` to **`model`**, while the server marks it required with no default. For `model` the CLI auto-fills the identity `transform` and prints a warning.
- It **cannot be chained**. `tripo make x.glb --then smartsegment` fails with "takes a file/URL input only and cannot follow another task in a chain". It cannot be dry-run either.

**Segment vs smartsegment:**
- You already have a Tripo task or mesh: use `segment` (40) and keep the id chain.
- You only have a photo or concept: smartsegment `image` (85) does generation and segmentation together.
- An external GLB where you want labelled parts and a mask: smartsegment `model` (55).

---

## 4. Mesh Part Completion: `POST /v3/mesh/complete` (task type `mesh_completion`)
Source: https://developers.tripo3d.ai/en/docs/mesh-complete

Completes segmented parts and repairs missing regions.

| Param | Type | Default | Allowed / constraints |
|---|---|---|---|
| `input` | string | required | **Only a task_id of a `mesh/segment` task** |
| `model` | string | `v1.0-20250506` | The only version |
| `part_names` | string[] | all parts | Node names from the segment output, e.g. `["tripo_part_0","tripo_part_1"]` |
| `completion_mode` | string | `ai_completion` | `ai_completion` uses AI diffusion to generate realistic geometry for missing regions. `quick_cap` quickly seals open boundaries without AI. |

- Result: `output.model_url` and `output.rendered_image_url`.
- Cost: `ai_completion` 50, `quick_cap` 30.

**Defects it fixes:**
- Holes or open boundaries on parts, such as the hidden faces where parts touched: use `quick_cap`, which is cheaper.
- Missing or occluded geometry on a separated part, such as the back of a part that was hidden in the source image: use `ai_completion`.
- Needed when a disassembled object's parts must look solid once separated (derived).
- Whether the completed parts keep their textures is **UNKNOWN**. The example output file is named `model_pbr.glb`, which suggests it is textured, but that is not confirmed. Plan a `texture` pass with `part_names` if the completed regions come back untextured.

**CLI:**
```bash
tripo mesh complete <segment-task|@name> [--completion-mode ai_completion|quick_cap] [-p 'part_names=["tripo_part_0"]']
tripo make <task> --then segment,complete:completion_mode=quick_cap --dry-run --json
```
Locally validated: `complete` after anything other than `segment` is a blocking error.

---

## 5. Retopology / Decimate: `POST /v3/mesh/decimate` (task type `highpoly_to_lowpoly`)
Source: https://developers.tripo3d.ai/en/docs/mesh-decimate

Reduces polycount with three algorithm tiers.

| Param | Type | Default | Allowed / constraints |
|---|---|---|---|
| `input` | string | required | task_id / file_token / URL. The doc header says "Accepts task_id or file_token" but still lists URL (§10). |
| `model` | string | `v2.0` | `v3.0`, `v2.0` or `v1.0` (see the tier table) |
| `face_limit` | integer | conditional | v3.0/v2.0: **optional**, triangle 500–20,000, quad 500–10,000, adaptive if omitted. v1.0: **required**, triangle up to 2,000,000, quad up to 150,000. The CLI enforces a minimum of 500 for v1.0 too. |
| `quad` | boolean | `false` | Quad mesh. Supported by v3.0, v2.0 and v1.0. On v3.0 it bills 40 instead of 35. |
| `smart_uv` | boolean | `false` | Unwraps UVs inside the retopology task. **v3.0 only.** On v1.0 or v2.0 it returns `400`/`1004`. No extra cost. It does **not** produce a UV atlas preview; use `mesh/uv` if you need one. |
| `bake` | boolean | `true` | Bakes textures onto the low-poly mesh. **Not supported on v1.0.** |
| `part_names` | string[] | | Parts to decimate (from segmentation). **Not supported on v1.0.** |

Tier table (from the doc's tabbed section):

| Tier | Credits | What it is | face_limit | quad | smart_uv | bake | part_names | Output format |
|---|---|---|---|---|---|---|---|---|
| v3.0 | 35 tri / 40 quad | Newest retopology, optional UV unwrap in the same task | optional, 500–20k tri / 500–10k quad, adaptive if omitted | yes | **yes** | yes (default true) | yes | UNKNOWN (not stated) |
| v2.0 (default) | 30 | "Smart Retopology: rebuilds clean topology with edge preservation and detail retention" | optional, 500–20k / 500–10k, adaptive | yes | no (1004) | yes | yes | Format param not supported. Outputs **GLB**, or **FBX when quad=true**. |
| v1.0 | 10 | "Basic Decimation: post-processing pipeline decimation" | **required**, up to 2M tri / 150k quad | yes | no (1004) | **no** | **no** | UNKNOWN |

- Result: `output.model_url` and `output.rendered_image_url`.
- Does it preserve existing UVs? **UNKNOWN** for v2.0 and v1.0. With `bake=true` the textures are re-baked onto the low-poly, which implies new UVs (derived). v3.0 + `smart_uv` explicitly unwraps new UVs. With v1.0 (no bake) the fate of textures and UVs is **UNKNOWN**.
- common-errors.md, error `2018` "too complex to remesh": lower `face_limit` or simplify the input.

**Defects it fixes:**
- Polycount over budget.
- Messy triangle soup from generation: v2.0/v3.0 retopology gives clean, edge-preserving topology.
- Need for quads, e.g. for deformation or editing in Blender: `quad=true`.
- LOD chain: run decimate several times from the same high-poly source with different `face_limit`. Baking keeps the appearance.
- Bad or missing UVs together with too many faces: v3.0 with `smart_uv=true` fixes both in one task.

**CLI:**
```bash
tripo mesh decimate <task|file|url> --face-limit 5000 [--model v3.0|v2.0|v1.0] [--quad] [--smart-uv] [--no-bake] \
    [-p 'part_names=["tripo_part_0"]']
tripo make <task> --then decimate:5000 --dry-run --json                              # v2.0 default, 30 cr
tripo make <task> --then decimate:model=v3.0,face_limit=5000,smart_uv=true --dry-run --json   # 35 cr
tripo make <task> --then decimate:model=v3.0,quad=true,face_limit=8000 --dry-run --json       # 40 cr
```
Local validation, verified by dry-run:
- `decimate:25000` gives the error "must be within 500–20000".
- `quad=true,face_limit=12000` gives the error "500–10000 (quad halves the budget)".
- `model=v1.0` without face_limit is an error.
- `model=v2.0,smart_uv=true` is an error.
- `--smart-uv` with no `--model` auto-selects v3.0 and prints a warning.
- `bake` and `part_names` on v1.0 are removed with a warning.

---

## 6. Smart UV: `POST /v3/mesh/uv` (task type `mesh_uv`)
Source: https://developers.tripo3d.ai/en/docs/mesh-uv

Re-unwraps a model's UVs and remaps the existing textures, rig and animation onto the new layout. The result also includes a UV atlas preview image.

| Param | Type | Default | Allowed / constraints |
|---|---|---|---|
| `input` | string | required | task_id / file_token / URL. **The input must not exceed 80,000 equivalent triangles; a quad counts as two.** A larger model is accepted at creation, then the task fails and the credits are refunded. Reduce the polycount first, for example with Retopology. |
| `model` | string | `default` | Only `default` |
| `bake` | boolean | `true` | Bakes the existing textures onto the new UV layout. `false` returns geometry and UVs only. |
| `export_orientation` | string | none | `+x`, `-x`, `+y` or `-y` |
| `compress` | string | none | `geometry` applies meshopt compression |

- Doc oddity: the uv page also says "The following parameters are only valid when `model ≥ v3.0-20250812`: texture_quality, geometry_quality, auto_size, quad, smart_low_poly, generate_parts, compress". This looks copied from the generation pages, since the uv `model` only accepts `default`. Treat it as noise, except that `compress` might be affected (UNKNOWN).
- Result: `output.model_url` and `output.uv_render_url` (`uv_render.webp`, a flat atlas layout, not a render; the CLI does not copy it to preview.png). Example `credits_consumed: 20.00`.
- Cost: 20.

**Defects it fixes:**
- Overlapping, fragmented or wasteful UVs, which cause texture bleeding or blurry texel density.
- Needing a clean layout for hand-painting or for Blender and Substance work.
- Keeping rig and animation while fixing UVs: this is the only UV path that says it remaps rig and animation.

**When to use which:**
- One task, no atlas image: `decimate --smart-uv` (v3.0, 35).
- UV only on an already low mesh, with the atlas image: `uv` (20).
- Too heavy mesh: `--then decimate:20000,uv` (30 + 20).

**CLI:**
```bash
tripo mesh uv <task|file|url> [--no-bake] [--export-orientation +x|-x|+y|-y] [-p compress=geometry]
tripo make <task> --then decimate:20000,uv --dry-run --json
```
The CLI does **not** check the 80k-triangle limit locally, because it cannot know the polycount. The skill should count triangles itself, e.g. with Blender headless, before choosing `uv`.

---

## 7. Convert Format: `POST /v3/models/convert` (task type `convert_model`)
Source: https://developers.tripo3d.ai/en/docs/models-convert

Converts to another format, with optional mesh processing, texture baking and export settings.

| Group | Param | Type | Default | Allowed / notes | Advanced-price trigger? |
|---|---|---|---|---|---|
| basic | `input` | string | required | task_id / file_token / URL. The header says "task_id or file_token" (§10). | — |
| basic | `format` | string | **required** | `GLTF` (web, Three.js, Babylon.js), `FBX` (Unreal, Unity, Maya, Blender), `USDZ` (Apple AR Quick Look, RealityKit), `OBJ` (legacy, no animation), `STL` (printing, geometry only), `3MF`. The first list says "3D with single color"; the second says "STL / 3MF: 3D printing, geometry only". **There is no `GLB` value; `GLB` is rejected locally.** | no |
| mesh | `quad` | boolean | false | Quad mesh. If `face_limit` is unset, the default face count becomes **10,000**. The doc says: "Enabling quad will force the output format to FBX." | **yes** |
| mesh | `force_symmetry` | boolean | false | Only valid when quad=true | not listed |
| mesh | `face_limit` | integer | keep original | Maximum polycount. Omit to keep the original face count. | **yes** |
| mesh | `flatten_bottom` | boolean | false | Flattens the bottom | **yes** |
| mesh | `flatten_bottom_threshold` | float | 0.01 | Flattening depth threshold | **yes** |
| texture | `texture_size` | integer | 4096 | Diffuse texture size in px. Allowed values are not listed (UNKNOWN). | **yes** |
| texture | `texture_format` | string | JPEG | `JPEG` (smallest), `PNG` (lossless, alpha), `WEBP`, `BMP`, `DPX`, `HDR`, `OPEN_EXR`, `TARGA`, `TIFF` | **yes** |
| texture | `bake` | boolean | true | Bakes advanced materials into the base textures | not listed |
| texture | `pack_uv` | boolean | false | Packs all UVs into one layout, which is useful for merging parts into one material (derived) | not listed |
| texture | `export_vertex_colors` | boolean | false | **OBJ and GLTF only** | not listed |
| export | `pivot_to_center_bottom` | boolean | false | Moves the pivot to the bottom centre | **yes** |
| export | `scale_factor` | float | 1 | Scale factor | **yes** |
| export | `with_animation` | boolean | true | Includes skeleton and animation | not listed |
| export | `animate_in_place` | boolean | false | Removes root displacement | not listed |
| export | `part_names` | string[] | | Parts to export, from mesh/segment | not listed |
| export | `export_orientation` | string | `+x` | Forward axis: `+x`, `-x`, `+y`, `-y` | not listed |
| export | `fbx_preset` | string | `blender` | `blender`, `3dsmax`, `mixamo`, `bake_scale` (bakes the scale transform into the geometry on FBX export instead of leaving it on the node) | not listed |

- Result: `output.model_url` (e.g. `converted-model`) and `output.rendered_image_url`.
- Cost: Basic 5, Advanced 10. The pricing page lists the advanced triggers, all of which are in the table above: `quad, face_limit, flatten_bottom, flatten_bottom_threshold, texture_size, texture_format, pivot_to_center_bottom, scale_factor`.
- The CLI is more conservative. It warns "complex convert" for **any** non-default option, including `bake, pack_uv, export_vertex_colors, with_animation, animate_in_place, export_orientation, fbx_preset, force_symmetry, part_names`. Its plan-card `cost_notes` even fire for `fbx_preset=blender`, which is the default. Pricing-page triggers are authoritative; the rest is UNKNOWN but probably basic.
- **The `warnings[]` and `cost_notes[]` signals behave differently** (verified 2026-10-31):
  - The `warnings[]` entry `non-default convert options use the "complex convert" price tier` checks values. It fires for a non-default value (`export_orientation=-y`, `animate_in_place=true`, `pack_uv=true`, `with_animation=false`, `bake=false`, `fbx_preset=mixamo`, `part_names=...`). It does **not** fire for default values (`export_orientation=+x`, `scale_factor=1`, `texture_size=4096`, `fbx_preset=blender`).
  - The `cost_notes[]` entry `non-default convert options bill as complex convert` fires whenever **any** key other than `format` is present, whatever its value. It also fires when the validator then strips that key and leaves a basic `{format}` payload (`force_symmetry` without quad, `export_vertex_colors` on FBX, `fbx_preset` on GLTF). It even fires on invalid plans.
  - So if a skill estimates convert cost, it should check the final payload against the pricing-page trigger list, and not rely on either CLI signal.

**Defects it fixes:**
- Wrong engine format.
- Wrong forward axis in the engine: `export_orientation`. Do this as the **last** step, because orientation set at generation time is not inherited by later steps; the output comes out mis-oriented with no error (common-errors.md).
- Pivot not at the feet or base: `pivot_to_center_bottom`.
- Wrong scale: `scale_factor`, or `fbx_preset=bake_scale` to get scale baked into the geometry for FBX.
- Textures too large for mobile: `texture_size` 2048 or 1024 with `texture_format`.
- Need for alpha: `PNG`.
- Polycount fix inside the export: `face_limit`. This is a cheaper polycount path than decimate (10 vs 30+), but the quality and algorithm are **UNKNOWN**. Prefer decimate for real retopology.
- Root motion unwanted: `animate_in_place`.
- Exporting a single part: `part_names`.
- Mixamo or Unity Humanoid pipeline: `fbx_preset=mixamo`.

**CLI:**
```bash
tripo model convert <task|file> --format FBX [--texture-size 2048] [--texture-format PNG] [--face-limit N] [--quad] \
    [--flatten-bottom] [--fbx-preset blender|3dsmax|mixamo] [--export-orientation +x|-x|+y|-y] [--scale-factor 1.5] \
    [--auto-size] [--pivot-to-center-bottom] [--export-vertex-colors] \
    [-p pack_uv=true] [-p animate_in_place=true] [-p with_animation=false] [-p bake=false] \
    [-p 'part_names=["tripo_part_0"]'] [-p force_symmetry=true] [-p flatten_bottom_threshold=0.02]
tripo make <task> --then convert:fbx,texture_size=2048,texture_format=PNG,pivot_to_center_bottom=true,export_orientation=-y --dry-run --json
```
- **Gotcha:** `tripo model convert` defaults `--format` to **GLTF** at the CLI level, so omitting `--format` silently gives GLTF.
- Local rules, verified by dry-run:
  - quad + GLTF is a blocking error.
  - `force_symmetry` without quad is removed.
  - `export_vertex_colors` on a format other than OBJ or GLTF is removed with a warning.
  - `fbx_preset` on a non-FBX format is removed.
  - `fbx_preset=bake_scale` is a **blocking error** (see §10).
  - `format=GLB` is a blocking error.

---

## 8. Import Model: `POST /v3/models/import` (task type `import_model`)
Source: https://developers.tripo3d.ai/en/docs/models-import

Imports an external 3D file into the platform for downstream processing.

| Param | Type | Default | Constraints |
|---|---|---|---|
| `input` | string | required | file_token (prefix `file_`) or URL. GLB, GLTF, FBX, OBJ, STL. Maximum **150 MB**. |

Response fields:

| Field | Type | Meaning |
|---|---|---|
| `model_url` | string | Download URL of the imported model, e.g. `tripo_input.glb` |
| `rendered_image_url` | string (optional) | Preview, e.g. `.webp` |
| `normalize_scale` | number (optional) | Uniform scale applied during normalisation: `normalized size = original size × normalize_scale`. `1.0` means not scaled, though the model may still have been translated. **The platform output keeps the normalised result.** |
| `normalize_translation` | number[3] (optional) | `[tx,ty,tz]`. `normalized = original × normalize_scale + normalize_translation`, and `original = (normalized − normalize_translation) / normalize_scale`. |

- Both `normalize_*` fields are also returned by post-processing tasks (rig, texture, convert, etc.) whose input is a file_token or URL. They are **not** returned for task_id input, or for tasks created before the field existed.
- Cost: **UNKNOWN**. It is not on the pricing page.
- Example result: `credits_consumed` is absent.

**Use cases:**
- Bringing a Blender-made or external asset into the Tripo pipeline for texture, segment, decimate, uv, rig or convert.
- **(derived)** Gotcha for game scale: imported assets come back normalised, i.e. resized and re-centred. To restore real-world size, apply `1/normalize_scale`, for example convert `scale_factor = 1/normalize_scale`, which is an advanced convert at 10 credits. Or fix it in Blender or Godot, and record `normalize_*` from `task.json`.

**CLI:**
```bash
tripo model import <file-or-url>                    # GLB/GLTF(URL only)/FBX/OBJ/STL ≤150 MB
tripo make model.glb --then texture,convert:fbx --dry-run --json   # make inserts the import step automatically
```

---

## 9. Chaining cheat-sheet (game assets)

Legal upstream types are enforced locally by `validateChain` and checked by the real run via the API.

| Step | Accepts upstream |
|---|---|
| texture, convert, segment, decimate, uv, rig-check, rig | any model-producing task, or a file/URL |
| complete | `mesh_segmentation` only |
| refine | `text_to_model` only |
| retarget | `animate_rig` only |
| import, smartsegment | file/URL only; never inside a chain after another step |

Typical defect-to-fix recipes. All costs are from the pricing page; validate first with `--dry-run --json`.

| Detected defect | Fix option(s) | Cost |
|---|---|---|
| Too many faces for the platform | `decimate:<N>` (v2.0) / `decimate:model=v3.0,face_limit=N` / v1.0 basic / convert `face_limit` | 30 / 35 / 10 / 10 |
| Bad topology for animation or editing | `decimate:model=v3.0,quad=true,face_limit=N`, or v2.0 quad (FBX out) | 40 / 30 |
| Bad or overlapping UVs | `uv` (≤80k tris) or `decimate:model=v3.0,smart_uv=true` | 20 / 35 |
| Heavy mesh plus bad UVs | `decimate:20000,uv` or v3.0 with `smart_uv` | 50 / 35 |
| Blurry texture | `texture:detailed` / `texture:extreme` | 20 / 30 |
| Baked lighting in albedo | texture `model=v3.5-20260815, delight=true` (raw API only; see §10) | 10–30 |
| Texture style mismatch across a set | texture + `texture_prompt` style_image / images + fixed `texture_seed` (direct command with `-p`) | 10–30 |
| Holes or open part boundaries | `segment,complete:completion_mode=quick_cap` | 40 + 30 |
| Missing or occluded part geometry | `segment,complete` (ai_completion) | 40 + 50 |
| Need separate parts | `segment` (v1 geometry / v2 semantic), or smartsegment for a file | 40 / 55–85 |
| Wrong axis, pivot or scale in the engine | final `convert` with `export_orientation`, `pivot_to_center_bottom`, `scale_factor`, `fbx_preset=bake_scale` | 5–10 |
| Textures too big for mobile | convert `texture_size=1024\|2048` | 10 |
| LODs | repeated `decimate:<N>` from the same high-poly source (bake on) | 30–40 each |

Ordering rules:
- Texture first, then decimate with `bake=true`, so detail is baked onto the low-poly mesh.
- Decimate before `uv` (80k limit).
- Segment before complete, part-texture, part-decimate or part-export.
- Convert last; it is the only place to set the final orientation.

---

## 10. Doc vs CLI mismatches (tripo-cli v0.6.1 vs docs as of 2026-10-30)

1. **Texture model `v3.5-20260815` is blocked by the CLI.** `TEXTURE_MODELS = ['v3.0-20250812','v2.5-20250123']` in `dist/knowledge/models.js`. `tripo make x.glb --then texture:model=v3.5-20260815,texture_quality=fast --dry-run` returns `valid:false` with "texture model must be one of v3.0-20250812/v2.5-20250123". So `texture_quality=fast` and `delight` **cannot be used through the CLI**; use the raw API (curl with the key) for them.
2. **`texture:fast` passes CLI validation but would fail on the server.** The dry-run of `--then texture:fast` is `valid:true` with `model=v3.0-20250812`. Per the docs the server returns `1004`, so the CLI lets a guaranteed error through.
   - Wider than `fast` (verified 2026-10-30): the `--then texture` step does **not validate `texture_quality` at all**. `texture:ultra` is also `valid:true`. `TEXTURE_QUALITIES` is only checked for generation params in `dist/knowledge/params.js`. The CLI likewise does not validate texture `texture_alignment` (`=foo` passes), complete `completion_mode` (`=foo` passes) or uv `export_orientation` (`=+z` passes). It **does** validate convert `export_orientation`, convert `texture_format`, convert `format`, `fbx_preset`, the segment `model` and the decimate `model` and `face_limit`. The skill must validate the unchecked enums itself before a real run.
3. **`fbx_preset=bake_scale` is documented but rejected by the CLI.** `FBX_PRESETS = ['blender','3dsmax','mixamo']`. The dry-run error is "fbx_preset must be one of blender/3dsmax/mixamo".
4. **CLI help lists texture qualities as `standard|detailed|extreme`.** The docs add `fast` (v3.5 only).
5. **Convert `quad` behaviour.** The docs say "Enabling quad will **force the output format to FBX**". The CLI says quad "cannot export GLTF; use FBX/OBJ/USDZ", allows `quad` with USDZ or OBJ, and blocks GLTF. Whether the server actually returns USDZ or OBJ for quad, or silently FBX, is UNKNOWN.
6. **Convert `auto_size`.** The CLI has `--auto-size` ("scale to real-world size") on `tripo model convert`, but the convert doc page has **no `auto_size` parameter**; it exists on generation endpoints. Server behaviour on convert is UNKNOWN.
7. **Advanced-convert triggers.** The pricing page lists 8 trigger params. The CLI warns "complex convert" for many more (bake, pack_uv, export_orientation, fbx_preset, with_animation, animate_in_place, export_vertex_colors, part_names, force_symmetry), and its `cost_notes` fire even for default-valued args such as `fbx_preset=blender`. So the CLI overstates cost for orientation-only converts. Per the pricing page those are basic (5).
8. **Convert format list.** The docs contradict themselves on 3MF ("single color" vs "geometry only"). Neither the docs nor the CLI offer `GLB` as a convert format. The CLI process.md calls the result of GLTF "GLTF"; whether the downloaded file is .gltf or .glb is UNKNOWN.
9. **Decimate `--model` default.** The server default is `v2.0`. The CLI help says "(default v2.0)", and process.md calls v2.0 the default. Consistent, but `--smart-uv` silently switches to v3.0 (+5 credits).
10. **Decimate v1.0 face_limit minimum.** The docs give only maximums (2M tri / 150k quad). The CLI enforces a minimum of 500.
11. **Input wording.** The convert and decimate pages say "Accepts task_id or file_token" in the header but list URL as an option. The docs say task_ids must come from generation tasks (text/image/multiview_to_model). The CLI allows any model-producing upstream, and its own recipes (`decimate:20000,uv`, `segment → convert part_names`) rely on that.
12. **smartsegment `seg_type`.** Required with no default on the server; the CLI defaults it to `model`. The CLI also auto-fills the identity `transform`.
13. **uv page parameter note.** The uv page says texture_quality, geometry_quality, auto_size, quad, smart_low_poly, generate_parts and compress are "only valid when model ≥ v3.0-20250812", although uv `model` only accepts `default`. This looks like a doc copy-paste.
14. **Process.md concurrency pools** list "mesh operations: segment, complete, decimate" and "model processing: texture, convert, refine". The pools for `uv`, `smartsegment` and `import` are UNKNOWN.
15. **First-class flags are missing for many documented parameters.** All of these need `-p`: texture `pbr`, `texture_seed`, `texture_prompt`, `part_names`, `compress`, `bake`, `delight`, `model`; segment v2 options and `ref_image`; complete `part_names`; decimate `part_names`; uv `compress`; convert `pack_uv`, `bake`, `with_animation`, `animate_in_place`, `part_names`, `force_symmetry`, `flatten_bottom_threshold`.
16. **`--then` cannot carry objects or arrays** (§0.6), and `make -p` does not reach chain steps. Per-part or prompt-guided processing therefore has to use direct commands, which have no `--dry-run`.
17. ~~Subcommand `--help` prints the top-level help.~~ **Retracted 2026-10-30:** `tripo <group> <sub> --help` works normally. The original observation was a zsh word-splitting artefact (see §0.5).
18. **No cross-step check on decimate quad output.** The docs say decimate v2.0 with `quad=true` outputs FBX. The CLI still accepts `decimate:model=v2.0,quad=true,face_limit=8000,convert:format=GLTF` as `valid:true` with no warning, although convert itself blocks `quad=true` with GLTF. Server behaviour for this chain is UNKNOWN.

---

## 11. UNKNOWN list (check before relying on these)
- Credit cost of `models/import`, and of the implicit import when a step receives a file/URL.
- Allowed `texture_size` values, and whether non-power-of-two sizes work.
- Whether decimate v1.0 and v2.0 preserve existing UVs. Decimate output format for v3.0 and v1.0.
- Whether `mesh/complete` output keeps textures.
- Node names produced by segment v2 semantic labelling, and whether the smartsegment `seg_task_id` can feed `mesh/complete`.
- Algorithm and quality of convert `face_limit` compared with decimate.
- Server behaviour for convert `auto_size`, and for quad with USDZ or OBJ.
- Whether each processing endpoint accepts every model-producing task type as a `task_id` input. The docs only name generation tasks.

---

## 12. Verified via dry-run (2026-10-30)

tripo-cli 0.6.1. Every command was run with `--dry-run --json` only: no network, no credits. `@last` resolved to `41d58880-53dc-4b1c-a930-b59124b8333d (multiview_to_model)`. `model.glb` is a Blender default cube exported to GLB in a scratch directory; the dry-run needs the file to exist and fails with "file not found" otherwise.

| # | `tripo make ... --dry-run --json` | valid | Warnings / errors / notes |
|---|---|---|---|
| 1 | `@last --then texture:detailed,texture_alignment=geometry` | yes | none. Payload adds `model=v3.0-20250812` |
| 2 | `@last --then texture:texture_quality=extreme,pbr=true` | yes | none. `pbr` coerced to boolean |
| 3 | `@last --then decimate:5000` | yes | none. No `model` in the payload, so the server default (v2.0) applies |
| 4 | `@last --then decimate:model=v3.0,face_limit=5000,smart_uv=true` | yes | none |
| 5 | `@last --then decimate:model=v3.0,quad=true,face_limit=8000,convert:format=FBX` | yes | none. `convert:format=FBX` correctly starts a new step |
| 6 | `@last --then decimate:model=v1.0,face_limit=3000` | yes | none |
| 7 | `@last --then decimate:20000,uv` | yes | none (the 80k limit is not checked locally) |
| 8 | `@last --then uv:bake=false` | yes | none |
| 9 | `@last --then segment:v2.0-20260430,complete:completion_mode=quick_cap` | yes | none |
| 10 | `@last --then segment,complete` | yes | none. Defaults (v1.0 segment, ai_completion) are left to the server |
| 11 | `@last --then convert:fbx,texture_size=2048,texture_format=PNG,pivot_to_center_bottom=true,export_orientation=-y` | yes | W: complex-convert price tier; cost_note |
| 12 | `@last --then convert:format=FBX,fbx_preset=mixamo,animate_in_place=true` | yes | W: complex-convert tier (the pricing page does not list these two as advanced triggers) |
| 13 | `@last --then convert:format=GLTF,texture_size=1024` | yes | W: complex-convert tier |
| 14 | `@last --then convert:format=USDZ,quad=true,force_symmetry=true,face_limit=8000` | yes | W: complex-convert tier. quad with USDZ is allowed locally |
| 15 | `@last --then texture:detailed,decimate:5000,uv,convert:fbx` | yes | none |
| 16 | `model.glb --then texture:detailed,convert:fbx` | yes | none. Plan = import → texture → convert; `pending_uploads:["model.glb"]` |
| 17 | `model.glb --then decimate:model=v3.0,face_limit=10000,smart_uv=true,convert:format=GLTF,texture_size=2048` | yes | W: complex-convert tier. Plan = import → decimate → convert |

Re-check of the note's local-validation claims:

| Claim | Result |
|---|---|
| `decimate:25000` gives an error | confirmed: "must be within 500–20000" (exit 2). v3.0 `face_limit=200` gives the same error |
| quad + 12000 gives an error | confirmed: "500–10000 (quad halves the budget)" |
| v1.0 without face_limit gives an error | confirmed: "requires face_limit (500–2000000)". 300 and 3,000,000 are rejected too |
| v2.0 + smart_uv gives an error | confirmed |
| smart_uv with no model selects v3.0 | confirmed; warning text mentions 35/40 vs 30 credits |
| v1.0 `bake`/`part_names` removed | confirmed, each with a warning |
| `lowpoly` alias | confirmed: `lowpoly:5000` maps to decimate |
| quad + GLTF convert blocked | confirmed |
| force_symmetry without quad, export_vertex_colors on FBX, fbx_preset on GLTF | confirmed: each removed with a warning |
| `fbx_preset=bake_scale` blocked | confirmed |
| `format=GLB` blocked | confirmed. A bare `convert` with no format is also blocked |
| cost_notes fire for `fbx_preset=blender` | confirmed (cost_note only, no warning) |
| texture v3.5 model blocked; `texture:fast` passes | confirmed. `texture:ultra` passes too (see §10.2) |
| complete after a non-segment step blocked | confirmed (after the generation step and after texture) |
| refine after multiview_to_model blocked | confirmed |
| smartsegment cannot be chained | confirmed, after `@last` and after a file's implicit import |
| `segment:v3.0` rejected | confirmed: "must be one of v1.0-20250506/v2.0-20260430" |
| `make -p` not forwarded to `--then` | confirmed: `-p texture_seed=42` is missing from the texture payload |
| `texture_prompt={...}` sent as a string | confirmed: payload `"{\"text\":\"wood\"}"` |
| 2+ `part_names` cannot be expressed | confirmed, but it is a parse error with exit 1 and no JSON (§0.5) |
| Bare task id with no history: "unverified" warning | **incomplete**: the warning appears for *every* bare UUID, including ones that are in history. `<uuid> --then complete` after a multiview task is `valid:true` (§0.5, corrected 2026-10-31) |
| `edit` hidden without the env var | confirmed: "unknown step" (exit 1). With `TRIPO_EXPERIMENTAL_MESH_EDIT=1` it parses and requires `bbox` |
| Subcommand `--help` prints top-level help | **wrong**: retracted (§0.5, §10.17) |
| Direct commands have no `--dry-run` | confirmed: no such flag in `tripo model help texture` and the other subcommand help pages |
| Direct command with a file uploads it straight to a file_token, with no import task | confirmed in `dist/core/task-service.js` `resolveInputValue` (model-file → `uploadLocalFile`) |
| `-p` parses JSON for `[...]`/`{...}` | confirmed in `dist/commands/shared.js` `coerceValue`. Decimal strings also become numbers |

### 12.1 Independent re-verification (re-run 2026-10-31, still tripo-cli 0.6.1)

An adversarial pass re-ran all 17 commands above with `--dry-run --json --yes` and stdin closed (`</dev/null`). `@last` was the same `41d58880-… (multiview_to_model)`. `model.glb` was a freshly exported Blender default cube. **All 17 matched the table above exactly:** `valid:true`, exit 0, and the same payloads. The only warning was the convert "complex convert" warning on rows 11, 12, 13, 14 and 17, together with the matching `cost_note`. Rows 1–10, 15 and 16 had empty `warnings`, `errors` and `cost_notes`. Payload details that were confirmed: row 3 has no `model` key (server default v2.0); row 7's `uv` payload is bare `{input}`; row 10 has bare `segment`/`complete` payloads; rows 16 and 17 add an `import` step with `input:"<upload:model.glb>"` and `pending_uploads:["model.glb"]`.

29 negative and edge probes were also re-run. Every local-validation claim in §5, §7 and §10 reproduced with the same error text and exit code 2, or valid with a warning where stated. Three new findings were added to the note:
1. **A bare UUID never consults history** (§0.5). This corrects the earlier "no local history" wording.
2. **The convert `warnings[]` and `cost_notes[]` differ** (§7). The warning checks values; the cost_note fires on any extra key, even stripped ones and default values.
3. **A bare `part_names=x` in `--then` is sent as a string** (§0.6).

Parse failures (`part_names=["a","b"]` in `--then`) still exit 1 with empty stdout. `tripo make … -p texture_seed=42` is still not forwarded to the texture step.

Subcommand `--help` flag lists match §1–§8 exactly (`model texture|convert|import`, `mesh segment|complete|decimate|uv|smartsegment`). `tripo docs --topic commands/process` and `--topic common-errors` agree with the parameter tables: the 80k uv limit, error 2018/2019, `.gltf` not uploadable, ~5 min URL expiry, export_orientation not inherited, and the 1004 cases (`smart_uv` on v1/v2, `ref_image` on segment v1).

Tooling note: when running the dry-runs in a `while read` loop, redirect tripo's stdin from `/dev/null`. tripo treats piped stdin as an input source. One loop without the redirect hung with no output, and the same loop with `</dev/null` finished normally. The cause is suspected, not proven.
