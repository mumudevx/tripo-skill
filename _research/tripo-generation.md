# Tripo generation reference (3D + image pre-steps)

Research note for the `tripo-skill`. Sources: the official docs at developers.tripo3d.ai (fetched 2026-10-30), the pricing page and its JS bundle (`/assets/PricingPage-*.js`, which holds the P-series and Splat tabs that are not server-rendered), the bundled `tripo-cli` v0.6.1 docs (`skill/commands/generate.md`, `make.md`, `examples/*.md`, `common-errors.md`), the CLI source (`dist/knowledge/{models,params,scenarios}.js`, `dist/core/requests.js`, `dist/commands/generate.js`) and real `tripo make ... --dry-run --json` runs.
Anything not stated by a source is marked **UNKNOWN**.

API base URL: `https://openapi.tripo3d.ai/v3`. All generation endpoints are async: `POST` returns `{"code":0,"data":{"task_id":...}}`, then you poll the task or use a webhook. The CLI does the polling.

---

## 0. TL;DR for the skill

- **Balance right now: 35 credits** (`tripo balance` → `{"balance":35,"frozen":0}`). That pays for one H-series text-to-model with texture (20), one H image-to-model with texture (30), or `--for game-pc` from text (30 + 5 convert = 35). **Only one P-series job is affordable: an untextured P1 text-to-model (30)** (`--model tripo-p1 -p texture=false -p pbr=false`). Textured P1 (40), any P1 image/multiview job (40/50) and all P2 jobs (100+) are out of reach. (Corrected 2026-10-30: an earlier draft said no P1 job was affordable, which contradicts the 30-credit price.)
- **Polycount**: `face_limit` is the main control. Omitting it gives "adaptive topology" (the count is UNKNOWN and can be high on H-series). For game assets, always set it.
- **Topology**: P1 gives clean low-poly triangles (50–20k). P2 (Preview) adds native quads (48–25k quads). On H-series, `smart_low_poly=true` gives hand-crafted-style low-poly (500–20k tris / 500–10k quads), and `quad=true` gives a quad remesh (FBX only).
- **Textures**: the levers are `texture_quality` (`fast`/`standard`/`detailed`/`extreme`=8K), `pbr`, `texture_version=v3.5-20260815` plus `delight`, and for image inputs `texture_alignment`.
- **Validate before spending.** Run `tripo make ... --dry-run --json`. `tripo generate ...` has **no `--dry-run` flag**, so never append it there (§9).
- **CLI auto-switch trap.** Without `--model`, a `face_limit` ≤ 20000 or a prompt containing "low poly", "voxel" and similar switches to P1, and the CLI then **silently strips** `smart_low_poly`/`quad`/`generate_parts`/`geometry_quality`. Pass `--model tripo-v3.1` explicitly when you want H-series low-poly.

---

## 1. Models and versions
Source: https://developers.tripo3d.ai/en/docs/models-and-versions

### 1.1 3D generation models (`model` is REQUIRED on text/image/multiview-to-model)

| Wire model ID | CLI alias (`--model`) | Series | Status (CLI) | Description (docs) | Recommended use (docs) |
|---|---|---|---|---|---|
| `v3.1-20260211` | `tripo-v3.1`, `v3.1` (CLI default) | H | GA | H3.1, latest high-precision model | AAA production pipelines / 3D printing & flexible manufacturing |
| `v3.0-20250812` | `tripo-v3.0`, `v3.0` | H | Legacy | H3.0, previous-generation stable version | Backward compatibility |
| `v2.5-20250123` | `tripo-v2.5`, `v2.5` | H | Legacy | H2.5, legacy version | Historical project compatibility |
| `P2-20260801` | `tripo-p2`, `p2`, `P2` | P | **Preview** (per CLI) | P2, native quad topology; 48–50,000 triangles or 48–25,000 quads | Game characters and props / hard-surface assets / real-time production pipelines |
| `P1-20260311` | `tripo-p1`, `p1`, `P1` | P | GA | P1, best low-poly performance; 50–20,000 faces | Game pipelines / UGC generative gameplay / mobile 3D assets |

Docs recommendations:
- New projects: `v3.1-20260211` for 3D.
- Highest quality: `v3.1-20260211`, optionally with `geometry_quality=detailed`.
- Low-poly or game assets: the P series, which gives "cleaner topology and more precise face-count control". `P2-20260801` has native quads and a higher face budget; `P1-20260311` is the other option.
- Production: pin a specific model version.

The API accepts **wire values only**. A raw alias such as `tripo-p1` sent to the API returns 1004 `invalid model` (per CLI docs). The CLI normalizes aliases. `task.json` records the wire value.

### 1.2 Image generation models (text-to-image / image-to-image)

| Model ID | Docs characteristics | t2i | i2i |
|---|---|---|---|
| `seedream_v4` | default for t2i; balanced | yes (default) | **no** |
| `seedream_v5` | latest, better quality and prompt following; default for i2i; "strongest editing, style transfer, and multi-image fusion" | yes | yes (default) |
| `banana` | fast | yes | yes |
| `banana_pro` | high quality | yes | yes |
| `banana2` | latest fast | yes | yes |
| `chat_image_1` | base; **retiring 2026-10-23** (already past as of 2026-10-30) | yes | yes |
| `chat_image_1.5` | higher quality; **retiring 2026-12-01** | yes | yes |
| `chat_image_2` | best quality | yes | yes |
| `chat_image_2.5_flare` | 2.5 speed tier; t2i quality on par with chat_image_2, noticeably faster | yes | yes |
| `chat_image_2.5_sunburst` | 2.5 fidelity tier; best at preserving the rest of the image when editing | yes | yes |

Docs recommendation for best image quality: `banana_pro` or `seedream_v5`, depending on the scenario.

---

## 2. Credits and pricing
Sources: https://developers.tripo3d.ai/en/docs/billing, https://developers.tripo3d.ai/en/pricing (plus its JS bundle for the P and Splat tabs)

**1 credit = $0.01 USD.**

Billing lifecycle: on task creation the required credits are **frozen**. On success they are consumed. On failure or cancellation they are returned. Failed and cancelled tasks are not charged.

Endpoints:
- `GET /v3/account/balance` returns `{balance, frozen}`. CLI: `tripo balance`.
- `GET /v3/account/usage` returns `[{task_id, type, credits_consumed, created_at}]`. CLI: `tripo usage`.

### 2.1 3D generation: H series (v3.x / v2.5)

| Task | No texture | Standard texture |
|---|---|---|
| Text to 3D | 10 | 20 |
| Image to 3D | 20 | 30 |
| Multiview to 3D | 20 | 30 |

**Add-ons, stacked on the base credits (H series):**

| Add-on | Triggering parameter | Credits |
|---|---|---|
| HD Texture | `texture_quality=detailed` | +10 |
| 8K Ultra Texture | `texture_quality=extreme` | +20 |
| HD Geometry Quality | `geometry_quality=detailed` | +20 |
| Quad Mesh | `quad=true` | +5 |
| Smart Low-poly | `smart_low_poly=true` | +10 |
| Generate Parts | `generate_parts=true` | +20 |

- `texture_quality=fast` costs the same as `standard` (per the generation docs).
- How the parameter maps to the add-on is inferred from the names. The pricing page lists only the add-on labels.

### 2.2 3D generation: P series

| Task | P1 no tex | P1 std tex | P2 no tex | P2 std tex |
|---|---|---|---|---|
| Text to 3D | 30 | 40 | 100 | 110 |
| Image to 3D | 40 | 50 | 100 | 110 |
| Multiview to 3D | 40 | 50 | 100 | 110 |

Pricing-page note (P tab, verbatim): "P1 does not support quad, smart_low_poly, generate_parts, or geometry_quality. P2 base is 100 credits; texture add-ons match P1 (standard +10). P2 face_limit: triangle 48–50,000; quad 48–25,000. P2 supports quad."

- The cost of P-series `detailed`/`extreme` texture is not listed on the pricing page: **UNKNOWN officially**. The CLI docs claim P2 costs 100 / 110 / 120 / 130 for none / standard / detailed / extreme, which matches the H add-ons of +10 and +20.
- Whether P2 `quad=true` adds +5: **UNKNOWN**. The P tab shows no add-on list.
- Note that P1 is **more expensive than H-series** for the same input type (text: 40 vs 20 with texture).

### 2.3 Splat
Image to Gaussian Splat: **30 credits** fixed (the doc page and the pricing JS agree).

### 2.4 Image generation (per image)

| Model | ≤1K | 2K | 4K |
|---|---|---|---|
| seedream_v5 / seedream_v4 | 5 | 5 | 5 |
| banana | 5 | — | — |
| banana2 | 10 | 10 | 15 |
| banana_pro | 15 | 15 | 20 |
| chat_image_1 (retiring 2026-10-23) | 5 | — | — |
| chat_image_1.5 (retiring 2026-12-01) | 10 | — | — |
| chat_image_2 | 10 | 10 | 15 |
| chat_image_2.5_flare | 10 | 10 | 15 |
| chat_image_2.5_sunburst | 10 | 10 | 15 |

chat_image quality tiers:

| Model · quality | ≤1K | 2K | 4K |
|---|---|---|---|
| chat_image_2 · high | 20 | 25 | 40 |
| chat_image_2.5_* · high | 20 | 25 | 40 |
| chat_image_2.5_* · xhigh | 25 | 30 | 45 |
| chat_image_2.5_* · max | 30 | 50 | 50 |

Billing rules for these tiers: omitting `quality`, or passing `low`/`medium`, bills at the base price; `auto` is not supported; when `size=auto`, the 2K tier applies.

| Operation | Credits |
|---|---|
| Image to Multiview | 10 |
| Edit Multiview | 5 per edited image |

(The t2i/i2i doc examples show `"credits_consumed": 20.00`. That is only an example payload.)

### 2.5 Downstream prices that matter for planning (from the pricing page; details live in other research notes)

| Operation | Credits |
|---|---|
| Texture (Fast) | 10 |
| Texture (Standard) | 10 |
| Texture (HD) | 20 |
| Texture (8K Ultra) | 30 |
| Format Convert, Basic | 5 |
| Format Convert, Advanced | 10 |
| Retopology v3.0 Triangle | 35 |
| Retopology v3.0 Quad | 40 |
| Retopology v2.0 Smart | 30 |
| Retopology v1.0 Basic | 10 |
| Smart UV | 20 |
| Segmentation | 40 |
| Part Completion (default / quick cap) | 50 / 30 |
| Smart Segmentation (image / model) | 85 / 55 |
| Rig Check | free |
| Auto Rig | 25 |
| Retarget | 10 per animation |

Any non-default value for `quad`, `face_limit`, `flatten_bottom`, `flatten_bottom_threshold`, `texture_size`, `texture_format`, `pivot_to_center_bottom` or `scale_factor` triggers Advanced Convert (10).

### 2.6 Worked cost examples (text input; image input adds +10 on H and P1)
Each total is computed from the tables above and the dry-run payloads in §8.

| Command | Calls | Est. credits |
|---|---|---|
| `make "x" --model tripo-v3.1` | t2m with texture (pbr defaults true) | 20 |
| `make "x" --model tripo-v3.1 -p texture=false -p pbr=false` | bare t2m | 10 |
| `make "x" --model tripo-v3.1 -p smart_low_poly=true -p face_limit=5000` | t2m + SLP | 30 |
| `make "x" --model tripo-v3.1 -p texture=false -p pbr=false -p generate_parts=true` | bare + parts | 30 |
| `make "x" --for game-pc` | t2m detailed tex (30) + convert FBX basic (5) | 35 |
| `make "x" --for game-mobile` | P1 t2m tex (40) + convert FBX with texture_size=2048 → advanced (10) | 50 |
| `make "x" --for film` | 20 + HD tex 10 + HD geo 20 + quad 5 | 55 |
| `make "x" --for print` | bare 10 + convert STL flatten_bottom → advanced (10) | 20 |
| `make "x" --for ar-web` | 20 + decimate (no model → server default v2.0, per CLI = 30) + convert USDZ basic 5 | 55 (decimate tier is an inference) |
| `make "x" --for anim` | 20 + rig-check 0 + rig 25 + retarget 2×10 | 65 |
| `make "x" --for toy` | P1 t2m tex | 40 |
| `make "x" -n 4 ...` | 4 parallel generations | 4× the generation cost |

---

## 3. Text → 3D model

### 3.1 H series
Source: https://developers.tripo3d.ai/en/docs/generation-text-to-model/standard. Endpoint: `POST /v3/generation/text-to-model`.

| Param | Type | Req | Default | Allowed / constraints | Notes |
|---|---|---|---|---|---|
| `prompt` | string | **yes** | — | ≤1024 chars | Describe shape, material, style and scale. Good: "A low-poly medieval wooden treasure chest with iron hinges and a rusty lock." Bad: "A box." Material and style hints give better PBR. |
| `model` | string | **yes** | — | `v3.1-20260211` (recommended), `v3.0-20250812`, `v2.5-20250123` | |
| `negative_prompt` | string | no | — | ≤255 chars | e.g. "blurry, low quality, broken mesh" |
| `model_seed` | int | no | random | | Geometry seed. Same seed and same input give an identical mesh. |
| `image_seed` | int | no | random | | Seed for the internal text-to-image stage (the reference image made from the prompt before 3D). |
| `face_limit` | int | no | adaptive | Max: v3.1 tri 1.5M (standard) / 2M (Ultra); v3.0 tri 1M / 2M; v2.5 tri 500k / —; quad 150k. With `smart_low_poly`: tri 500–20k, quad 500–10k regardless of version. | Docs guidance: game-ready 50k–100k, web/mobile 10k–50k. |
| `texture` | bool | no | `true` | | `false` gives bare geometry |
| `pbr` | bool | no | `true` | | `base_color`, `metallic`, `roughness`, `normal`. `pbr=true` forces `texture=true`. |
| `texture_seed` | int | no | random | | Keep `model_seed` and vary `texture_seed` to get the same geometry with new textures. |
| `texture_quality` | string | no | `standard` | `fast` / `standard` / `detailed` / `extreme` | `fast`: fastest, same output size as standard, same cost, **requires `texture_version=v3.5-20260815`** (otherwise 1004, no silent fallback). `detailed`: higher fidelity, slower. `extreme`: 8K textures, highest fidelity, costs more than detailed. |
| `texture_version` | string | no | derived from `model` | `v3.5-20260815` (newest; needed for `fast` and `delight`), `v3.0-20250812` (default for v3.x **and P-series** geometry), `v2.5-20250123` (default for v2.5 geometry) | Pins the texture model independently of the geometry model. |
| `delight` | bool | no | `true` | | Removes baked-in lighting from the reference image before texturing. `false` keeps the original shading. Only read by texture v3.5; older texture versions ignore it. |
| `geometry_quality` | string | no | `standard` | `standard` / `detailed` (= Ultra, finer detail) | Only effective for ≥ v3.0. Do NOT use with v2.5. |
| `auto_size` | bool | no | `false` | | Scales to real-world size in meters (AR/VR, game engines) |
| `quad` | bool | no | `false` | | Quad mesh. **If `face_limit` is unset, the default face count is 10,000.** Forces **FBX** output. |
| `smart_low_poly` | bool | no | `false` | | "Low-poly model with hand-crafted, clean topology style. Best suited for simple, non-complex inputs. Complex models may occasionally fail." |
| `generate_parts` | bool | no | `false` | | Editable segmented parts. See the incompatibility rules below. |
| `compress` | string | no | — | `geometry` | meshopt compression for a smaller file |
| `export_orientation` | string | no | `+x` | `+x`, `-x`, `-y`, `+y` (forward axis) | Applies to this generation only. **Do not set it if you will post-process** (texture/rig/retarget/convert): the result can come out wrongly oriented while the task still reports `success`. Set the orientation on the final `/v3/models/convert` step instead. |
| `export_uv` | bool | no | `true` | | `false` gives faster generation and a smaller file; UV unwrapping then happens during texturing. |

Valid only when `model ≥ v3.0-20250812`: `texture_quality`, `geometry_quality`, `auto_size`, `quad`, `smart_low_poly`, `generate_parts`, `compress`.

**`generate_parts` rules (server):**
- `texture=true` or `pbr=true` is rejected with **1004**. This includes **omitting `texture`**, because it defaults to true.
- `quad=true` is ignored; the parts come back as triangle meshes.
- With `smart_low_poly=true`, smart_low_poly wins and **no parts** are produced.
- To get parts: send `texture=false` and `pbr=false`, and do not send `quad` or `smart_low_poly`.

Response: `output.model_url` (e.g. `.../model_pbr.glb`) and `output.rendered_image_url` (preview PNG). The task `type` is `text_to_model`.

Doc examples:
```json
{"prompt":"A cat wearing a spacesuit","model":"v3.1-20260211","texture":true,"pbr":true,"texture_quality":"detailed"}
{"prompt":"A futuristic sci-fi helmet with glowing blue visor.","model":"v3.1-20260211","face_limit":80000,"geometry_quality":"detailed","auto_size":true}
```

### 3.2 P series
Source: https://developers.tripo3d.ai/en/docs/generation-text-to-model/p. Same endpoint, different `model`. "Optimized for low-poly output with clean topology."

Parameters listed: `prompt` (≤1024), `negative_prompt` (≤255), `image_seed`, `model` (required: `P1-20260311` = optimized for low-poly; `P2-20260801` = next-gen P with quad output), `model_seed`, `face_limit`, `texture`, `pbr`, `texture_seed`, `texture_quality` (same four values and rules as H), `texture_version`, `delight`, `auto_size`, `export_uv` (default true; "Set false for faster generation and smaller file size"), `export_orientation` (same warning as H), `quad` (**P2-20260801 only**).

**Not listed on the P pages:** `geometry_quality`, `smart_low_poly`, `generate_parts`, `compress`. The pricing note confirms that P1 lacks quad, smart_low_poly, generate_parts and geometry_quality. Whether `compress` works on P is **UNKNOWN**.

`face_limit` (P):
- `P1-20260311`: **50 – 20,000**
- `P2-20260801`: triangles **48 – 50,000**; with `quad=true`, **48 – 25,000**
- If omitted, it is adaptively determined.
- **"For best quality: simple models start from 150 faces, complex models start from 250 faces. Lower values may result in poor generation quality."**
- What P2 `quad=true` does without a `face_limit` (any default count) is **UNKNOWN**. The P pages do not repeat the H "10,000 default". Whether P2 quad also forces FBX is not stated on the P pages; the CLI assumes FBX (§10).

Doc examples:
```json
{"prompt":"A cat wearing a spacesuit","model":"P1-20260311","face_limit":3000,"texture":true,"pbr":true}
{"prompt":"A low-poly wooden chair","model":"P2-20260801","quad":true,"face_limit":5000,"texture":true,"pbr":true}
```

---

## 4. Image → 3D model
Endpoint: `POST /v3/generation/image-to-model`. Task type `image_to_model`.

### 4.1 H series
Source: https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard

These parameters are identical to H text-to-model **except**:
- **No `prompt`, `negative_prompt` or `image_seed`.**
- `input` (string, **required**). Use exactly one of: a `file_token` (from the File Upload API, e.g. `file_abc123`), a public URL, or the `task_id` of a previous `text_to_image` / `image_to_image` task (its output image is extracted automatically). Formats: PNG, JPEG, WebP. Max size **20 MB**. Recommended resolution **≥256×256**. The subject should be clearly visible, on a clean background, with minimal occlusion.
- `enable_image_autofix` (bool, default `false`). Optimizes the input before generation ("AI completion and 3D quality enhancement"; enhances low-resolution or low-quality images).
- `texture_alignment` (string, default `original_image`). `original_image` prioritizes matching the input image colors; `geometry` prioritizes matching the generated geometry.
- `orientation` (string, default `default`). `default` is automatic orientation; `align_image` aligns the model to the input image viewpoint. **Only effective when `texture` is `true`.**

Everything else matches §3.1: `model`, `face_limit` (same limits table), `texture`, `pbr`, `texture_seed`, `texture_quality`, `texture_version`, `delight`, `geometry_quality`, `auto_size`, `quad`, `smart_low_poly`, `generate_parts` (same rules), `compress`, `export_orientation`, `model_seed`, `export_uv`.

Doc example (autofix):
```json
{"input":"file_abc123","model":"v3.1-20260211","enable_image_autofix":true,"orientation":"align_image"}
```

### 4.2 P series
Source: https://developers.tripo3d.ai/en/docs/generation-image-to-model/p

Parameters: `input` (same rules), `model` (P1/P2), `enable_image_autofix`, `texture_alignment`, `orientation`, `model_seed`, `face_limit` (P ranges and the 150/250 advice), `texture`, `pbr`, `texture_seed`, `texture_quality`, `texture_version`, `delight`, `auto_size`, `export_uv`, `export_orientation`, `quad` (P2 only).

Doc examples:
```json
{"input":"https://example.com/image.png","model":"P1-20260311","face_limit":5000,"texture":true,"pbr":true}
{"input":"https://example.com/image.png","model":"P2-20260801","quad":true,"texture":true,"pbr":true}
```

---

## 5. Multiview → 3D model
Endpoint: `POST /v3/generation/multiview-to-model`. Task type `multiview_to_model`. "Multiple angles improve geometry accuracy and texture coverage."

### 5.1 H series
Source: https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard

`inputs` (object[] | string[], **required**) accepts **three formats. Use exactly one and do not mix them:**
1. **View-key (recommended).** An array of objects, each with exactly one key among `front`, `left`, `back`, `right`. A value may be a URL, a `file_token`, or nested `{url}` / `{file_token}` / `{object:{bucket,key}}`. Order does not matter; the server canonicalizes to [front, left, back, right].
2. **Legacy positional.** Exactly 4 strings in the order [front, left, back, right]. Use `""` to skip a view.
3. **task_id.** `[{"task_id":"<id>"}]` (a single-element array only) of a `success` task of type `image_to_multiview` or `edit_multiview`, reusing its 4 views.

Rules:
- The **front view cannot be omitted**.
- At least **2 images** are required.
- All images must show the same object under consistent lighting.
- Formats: PNG, JPEG, WebP. Recommended resolution ≥256×256.

Other parameters: `model`, `texture_alignment`, `orientation` (only effective with texture), `face_limit`, `texture`, `pbr`, `texture_seed`, `texture_quality`, `texture_version`, `delight`, `geometry_quality`, `auto_size`, `quad`, `smart_low_poly`, `generate_parts`, `compress`, `export_orientation`, `model_seed`, `export_uv`. These behave exactly as in §3.1.

**No `enable_image_autofix`** (it is not listed on the multiview pages).

Doc examples include view-key with `"texture":false,"geometry_quality":"detailed"`, legacy positional with `""` for the left view, and `{"inputs":[{"task_id":"..."}],"model":"v3.1-20260211","texture":true,"pbr":true}`.

### 5.2 P series
Source: https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/p

Same `inputs` rules. Parameters: `model` (P1/P2), `texture_alignment`, `orientation`, `model_seed`, `face_limit` (P ranges), `texture`, `pbr`, `texture_seed`, `texture_quality`, `texture_version`, `delight`, `auto_size`, `export_uv`, `export_orientation`, `quad` (P2 only).

---

## 6. Image → Gaussian Splat
Source: https://developers.tripo3d.ai/en/docs/generation-image-to-splat. Endpoint: `POST /v3/generation/image-to-splat`. Task type `image_to_splat`.

- Fixed cost **30 credits**. Typical time is **about 4 minutes**.
- Output: `output.model_url` → a `.splat` file. This is **not a mesh**, so it cannot be textured, rigged or converted. Use image-to-model when you need an editable asset.

| Param | Type | Req | Notes |
|---|---|---|---|
| `input` | string | yes | `file_token` or public URL (no task_id listed). PNG/JPEG/WebP, ≤20 MB, ≥256×256 recommended, clear subject, clean background. |
| `model_seed` | int | no | Same seed and input give an identical .splat |

Irrelevant for game meshes. Mention it only as an option.

---

## 7. Image pre-steps (better inputs give better 3D)

Image pipeline concurrency is **1 per account by default** (common-errors.md), so run image jobs serially.

### 7.1 Text → image
Source: https://developers.tripo3d.ai/en/docs/generation-text-to-image. Endpoint: `POST /v3/generation/text-to-image`. Task type `text_to_image`. Output: `output.generated_image_url`. It does not accept reference images (use i2i for that).

| Param | Type | Req | Default | Values / notes |
|---|---|---|---|---|
| `model` | string | no | `seedream_v4` | see §1.2 |
| `prompt` | string | **yes** | — | Chinese or English. Recommended ≤300 Chinese chars or ≤600 English words. Put the most important elements first. **Negative prompt: append it after `--no`.** |
| `size` | string | no | `2048x2048` | Per model, see the size table below |
| `quality` | string | no | `low` | Only `chat_image_2` (low/medium/high) and `chat_image_2.5_*` (low/medium/high/xhigh/max). With other models it **errors**. `auto` is not supported. high/xhigh/max cost more and are slower. |
| `background` | string | no | (model decides) | `auto` / `opaque` / `transparent`; only for `chat_image_2.5_*`. Other models ignore it (no error). `transparent` requires `output_format=png` (jpeg plus transparent is an error). |
| `aspect_ratio` | string | no | `1:1` | **banana series only.** banana/banana_pro: 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9. banana2 also accepts 1:8, 1:4, 4:1, 8:1. seedream and chat_image use `size`. |
| `output_format` | string | no | `png` | `png` / `jpeg` |
| `watermark` | bool | no | `false` | seedream only. banana always embeds an invisible watermark; chat_image has no control. |
| `template` | string | no | — | `asset_extraction` (extract a subject from a scene), `character_completion` (complete a partial character), `t_pose` (character in T-pose), `variants` (design variations), `figure` (full-body figure) |

Size support per model (same table for t2i and i2i, except seedream_v4, which is t2i only):

| Model | Size rules |
|---|---|
| seedream_v5 | **Either** tier `2K`/`3K` (describe the aspect in the prompt) **or** explicit `WxH` (default 2048x2048, 3.69–10.40 MP, aspect 1:16–16:1). Do not combine the two. |
| seedream_v4 | **Either** tier `2K`/`4K` **or** `WxH` (~3.69–16.78 MP, aspect 1:16–16:1) |
| banana | Fixed sizes: 1024x1024, 832x1248, 1248x832, 864x1184, 1184x864, 896x1152, 1152x896, 768x1344, 1344x768, 1536x672. Default when omitted: 2048x2048 (=2K). |
| banana_pro | `1K`/`2K`/`4K` or `WxH`; default 2K |
| banana2 | `0.5K`/`1K`/`2K`/`4K` only; default 2K |
| chat_image_1 / 1.5 | 1024x1024, 1024x1536, 1536x1024, auto; default auto |
| chat_image_2 / 2.5_* | Presets 1024x1024, 1536x1024, 1024x1536, 2048x2048, 2048x1152, 3840x2160, 2160x3840, auto; default 2048x2048. Custom `WxH` is allowed if each edge is ≤3840 and a multiple of 16, the long edge is ≤3× the short edge, and the total is 655,360–8,294,400 px. Example: 1080x1920 is rejected; use 1088x1920. |

### 7.2 Image → image
Source: https://developers.tripo3d.ai/en/docs/generation-image-to-image. Endpoint: `POST /v3/generation/image-to-image`. Server task type `generate_image` (per the CLI). Output: `output.generated_image_url`.

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `model` | string | no | `seedream_v5` | `seedream_v4` is **not** accepted |
| `input` | string | **yes** | — | Public URL, `file_token` or `task_id` (exactly one). jpeg/png recommended; **webp is rejected on some provider routes**. ≤20 MB, ≤36 MP (6000×6000), min edge 14 px, aspect W/H in [1/3, 3]. |
| `inputs` | string[] | no | — | Multiple references: max **4** (seedream), **10** (banana), **16** (chat_image). Refer to them in the prompt as `image[1]`, `image[2]`, … |
| `prompt` | string | conditional | — | Required unless `template` is set |
| `size`, `quality`, `background`, `aspect_ratio`, `output_format` | | | | same as t2i |
| `template` | string | no | — | `t_pose` (convert to T-pose), `character_completion`, **`3d_enhance` (enhance for 3D generation)**, `variants`, `figure`. When set, `prompt` is optional. |

No `watermark` is listed for i2i.

Doc example (multi-image): `{"inputs":[url1,url2],"prompt":"Use character from image[1] and outfit from image[2].","model":"seedream_v5"}`

### 7.3 Image → multiview
Source: https://developers.tripo3d.ai/en/docs/generation-image-to-multiview. Endpoint: `POST /v3/generation/image-to-multiview`. Task type `image_to_multiview`. **10 credits.**

- `input` (required): a `file_token` or public URL. PNG/JPEG/WebP; clear subject, clean background. **No other parameters are documented.**
- Output: `output.generate_multiview_image.{front_view_url,left_view_url,back_view_url,right_view_url}`.
- Use: preprocessing for multiview-to-model (pass the task id as `inputs:[{"task_id":...}]`) or turntable previews.

### 7.4 Edit multiview
Source: https://developers.tripo3d.ai/en/docs/generation-edit-multiview. Endpoint: `POST /v3/generation/edit-multiview`. **5 credits per edited image.**

- `input` (required): the task ID of a **successful image-to-multiview** task by the same client.
- `prompts` (required, object[]): **1–4** items `{prompt, view}`. `prompt` is non-empty and ≤1024 chars. `view` is one of `front`/`left`/`back`/`right`, distinct per item, and must exist in the source task.
- The result task (type `edit_multiview`) can feed multiview-to-model via `inputs:[{"task_id":...}]`.
- Use: fix one inconsistent view (wrong colour, missing detail) before paying for 3D.

### 7.5 Recommended pre-3D image pipeline (from doc capabilities)
1. Concept: `text-to-image` (seedream_v4/v5 cost 5) with a front, three-quarter or orthographic description, a plain background, and the `--no ...` negative syntax. Characters for animation: `template=t_pose`.
2. Clean up an existing photo or concept: `image-to-image` with `template=3d_enhance` (or `asset_extraction` on t2i… note that asset_extraction is listed for **t2i only**, which is odd for "extract from a scene"; behaviour is **UNKNOWN**).
3. Optional: `image-to-multiview` (10) → inspect the 4 views → `edit-multiview` (5 per view) to fix them → `multiview-to-model` with `inputs:[{"task_id":...}]`.
4. Otherwise, `image-to-model` directly with the task id as `input` (it accepts `text_to_image`/`image_to_image` task ids).

---

## 8. CLI usage (tripo-cli 0.6.1)

### 8.1 Command shapes
```bash
# orchestrated (supports --dry-run, --for, --then, -n, --seed)
tripo make "<prompt>" [--model tripo-v3.1|tripo-p1|tripo-p2] [-p key=value ...] [--seed N] [-n 1..4] [--for <scenario>] [--then <steps>] --json --yes
tripo make image.png ...                       # → image-to-model
tripo make front.png back.png [left.png right.png] ...   # → multiview-to-model (filename hints front/back/left/right, else positional front,left,back,right)

# deterministic endpoints (NO --dry-run flag)
tripo generate text-to-model "<prompt>" [--model M] [-p k=v]...
tripo generate image-to-model <file|url|task_id|@last> [--model M] [-p k=v]...
tripo generate multiview-to-model <f1> <f2> [f3 f4] [--model M] [-p k=v]...
tripo generate text-to-image "<prompt>" [--model seedream_v5] [-p template=t_pose] [-p size=2K]
tripo generate image-to-image <input> --prompt "..." [--model seedream_v5] [-p template=3d_enhance]
tripo generate image-to-multiview <input>
tripo generate edit-multiview <i2mv-task-id> -p 'prompts=[{"view":"front","prompt":"add a sword"}]'
tripo generate image-to-splat <input> [-p model_seed=N]
tripo redo [@last] [--seed N]                  # same request, new or explicit model_seed
```
Shared options: `--json --yes -o/--out --no-wait --no-download --notify --timeout <s> --name <n> -p/--param key=value`.

`-p` value coercion (`shared.js`): `true`/`false` become booleans; integers and decimals become numbers; `[...]` or `{...}` are parsed as JSON; anything else stays a string. Unknown keys pass through to the API untouched.

### 8.2 Model auto-selection (`knowledge/models.js` `chooseModel`)
- An explicit `--model`, or the scenario's model, always wins.
- Otherwise, **text input** with a prompt matching `/low[\s_-]?poly/i`, `/voxel/i`, `低模`, `低面`, `手游` or `像素风` selects **P1**.
- Otherwise, a numeric `face_limit ≤ 20000` (any input type) selects **P1**.
- Otherwise **v3.1**.
- **P2 is never auto-selected.**

This also applies to `tripo generate *-to-model`, which is therefore *not* fully deterministic. Always pass `--model` in the skill.

### 8.3 Local validation (`knowledge/params.js`) — what the CLI actually enforces

| Rule | Behaviour |
|---|---|
| prompt > 1024 / negative_prompt > 255 | error |
| P1 + quad / smart_low_poly / generate_parts / geometry_quality | stripped with a warning |
| P2 + smart_low_poly / generate_parts / geometry_quality | stripped with a warning |
| `pbr=true` and `texture=false` | texture forced true (warning) |
| `generate_parts=true` and texture/pbr/quad **explicitly `true`** | set to false (warning). Only flips keys that are explicitly true (see §10). |
| P1 face_limit outside 50–20000 | error |
| P2 face_limit outside 48–50000 (tri) / 48–25000 (quad) | error |
| H + smart_low_poly + face_limit outside 500–20000 (tri) / 500–10000 (quad) | error |
| `texture_quality` not in `standard/detailed/extreme` | error (**rejects the documented `fast`**) |
| `quad=true` | warning "forces FBX output" |
| H face_limit upper bounds (1.5M/2M/1M/500k/150k quad) | **not validated** |
| `geometry_quality` on v2.5 | **not validated** (docs: do NOT use) |
| Unknown `--model` (e.g. `tripo-turbo`) | **passes through** (dry-run says `valid:true`) |
| Image model / template whitelists | defined in `models.js` but **not enforced**; values pass as-is |
| `-n` > 4 | error "at most 4 candidates per run (-n 4)" |
| `--then convert:glb` | error: `unsupported format "glb" (GLTF/USDZ/FBX/OBJ/STL/3MF)`. GLB is the native generation output, not a convert target. Lower-case `fbx`/`gltf`/`usdz`/`obj` are upper-cased and accepted. |
| `quad=true` + `--then convert:gltf` | **not blocked** (`valid:true`, only the generic FBX warning), although make.md lists "quad + GLTF" as a blocking error (§11 #23) |
| Mixed text + image inputs | error "mixed input types (text + image-file)" |
| Missing local image file | error `file not found: "concept.png"` (dry-run does check that the file exists, but uploads nothing) |

### 8.4 `--for` scenario presets (verified by dry-run; source `knowledge/scenarios.js`)

| `--for` | Model | Generation params | Default chain (`--then` overrides it) | Deliverables | Est. credits (text) |
|---|---|---|---|---|---|
| `game-mobile` | P1 | `texture=true pbr=true texture_quality=standard face_limit=15000` | `convert format=FBX texture_size=2048` (advanced convert) | FBX, GLB | 40 + 10 = 50 |
| `game-pc` | v3.1 | `texture=true pbr=true texture_quality=detailed` (no face_limit, so adaptive) | `convert format=FBX` | FBX, GLTF | 30 + 5 = 35 |
| `film` | v3.1 | `texture=true pbr=true quad=true geometry_quality=detailed texture_quality=detailed` | none | FBX (quad); USDZ/OBJ via convert | 55 |
| `print` | v3.1 | `texture=false pbr=false` | `convert format=STL flatten_bottom=true` (advanced) | STL, 3MF (colored) | 10 + 10 = 20 |
| `ar-web` | v3.1 | `texture=true pbr=true` | `decimate face_limit=20000` → `convert format=USDZ` | GLB, USDZ | 20 + decimate + 5 |
| `anim` | v3.1 | `texture=true pbr=true` | `rig-check` → `rig model=v2.5-20260210 spec=tripo out_format=glb` → `retarget animations=[preset:idle,preset:walk]` | GLB, FBX | 20 + 0 + 25 + 20 = 65 |
| `toy` | P1 | `texture=true pbr=true face_limit=20000` | none | GLB; STL via convert | 40 |

User `-p` values override the preset genParams (`{...scenario.genParams, ...userParams}`). The scenario's model counts as "explicit", so `--for game-pc -p face_limit=5000` stays on v3.1.

Scenario notes from the source:
- game-mobile: "append --then rig if you need a skeleton".
- game-pc: "append --then decimate:5000 for LODs; use fbx_preset to match Blender/3dsMax".
- anim: "use rig:spec=mixamo for Mixamo/Unity Humanoid; prompt for a T-pose, or pre-generate with text-to-image template=t_pose".

### 8.5 Verified dry-run commands (all ran with `--dry-run --json`, zero credits)
```bash
tripo make "a stylized wooden crate" --for game-mobile          # P1, face_limit 15000, convert FBX 2048
tripo make "a wooden crate" --model tripo-v3.1 -p smart_low_poly=true -p face_limit=5000     # valid, SLP kept
tripo make "a wooden crate" -p smart_low_poly=true -p face_limit=5000                          # auto P1, SLP STRIPPED
tripo make "a wooden crate" --model tripo-p2 -p quad=true -p face_limit=12000                  # valid, FBX warning
tripo make "a wooden crate" --model tripo-p2 -p quad=true -p face_limit=30000                  # error 48–25000
tripo make "a wooden crate" --model tripo-p1 -p face_limit=48                                  # error 50–20000
tripo make "a wooden crate" --model tripo-v3.1 -p texture=false -p pbr=false -p generate_parts=true   # correct parts request
tripo make "a wooden crate" --model tripo-v3.1 -p texture_quality=extreme -p texture_version=v3.5-20260815 -p delight=false   # valid passthrough
tripo make "a wooden crate" --model tripo-v3.1 -p compress=geometry -p auto_size=true -p export_uv=false -p negative_prompt="floating parts, base, pedestal" -p image_seed=7 -p texture_seed=9 --seed 42
tripo make concept.png --model tripo-p2 -p quad=true -p face_limit=8000 -p orientation=align_image -p texture_alignment=geometry -p enable_image_autofix=true
tripo make front.png back.png left.png --model tripo-v3.1 -p face_limit=60000                  # view-key payload front/left/back
```

---

## 9. Quality levers: parameter → effect

| Parameter | Polycount | Topology | Texture | Notes / cost |
|---|---|---|---|---|
| `model` H v3.1 | adaptive (up to 1.5M tri, 2M Ultra) | dense, scan-like triangles | best texture pipeline (texture v3.0 default) | 10/20 (text), 20/30 (image) |
| `model` P1 | 50–20k | "clean topology", low-poly triangles | standard texture via v3.0 texture model | 30/40 (text), 40/50 (image) |
| `model` P2 (Preview) | 48–50k tri / 48–25k quad | native quads possible | same | 100/110 |
| `face_limit` | **direct cap** | lower = coarser. P: ≥150 (simple) / ≥250 (complex) recommended | lower poly means less geometric detail for the texture | H: game-ready 50–100k, web/mobile 10–50k (docs) |
| `quad` (H) | default 10,000 if no face_limit; max 150k | quad remesh | — | +5; **FBX only** |
| `quad` (P2) | ≤25k | native quads | — | add-on UNKNOWN |
| `smart_low_poly` (H ≥v3.0) | 500–20k tri / 500–10k quad | "hand-crafted, clean topology style" | — | +10; simple inputs only; complex ones may fail (failed = refunded) |
| `geometry_quality=detailed` (H ≥v3.0) | raises the cap to 2M | finer geometric detail | — | +20; pointless for low-poly game assets unless you decimate/bake later |
| `generate_parts` (H ≥v3.0) | — | separate part meshes | **none** (bare) | +20; retexture afterwards (`tripo model texture`, 10–30) |
| `texture_quality` | — | — | fast < standard < detailed < extreme (8K) | fast = standard cost (needs texture v3.5); detailed +10; extreme +20 |
| `texture_version=v3.5-20260815` | — | — | newest texture model; enables `fast` and `delight` | cost difference UNKNOWN (not listed) |
| `delight` (v3.5 only, default true) | — | — | removes baked lighting from the reference → cleaner albedo for game lighting | set `false` to keep painted/stylized shading |
| `pbr` (default true) | — | — | base_color + metallic + roughness + normal maps | `pbr=false texture=true` gives a colour-only texture (price difference UNKNOWN; the pricing table has no PBR line) |
| `texture_alignment` (image/multiview) | — | — | `original_image` = faithful colours; `geometry` = fits the mesh (stylized retexture) | |
| `orientation=align_image` | — | — | — | aligns the model to the photo viewpoint; only with texture on |
| `enable_image_autofix` (image only) | — | — | — | improves poor/low-resolution inputs |
| multiview input | — | better geometry accuracy | better texture coverage (back/sides) | +0 vs image on H (both 20/30) |
| `export_uv=false` | — | — | no UVs from generation | faster/smaller; UVs are made at texturing. Keep `true` for game delivery. |
| `compress=geometry` | — | — | — | meshopt-compressed output. Engine/DCC import support (EXT_meshopt_compression) in Godot/Blender is **UNKNOWN**; verify before using. |
| `auto_size=true` | — | — | — | real-world meters; useful for engine scale |
| `model_seed` / `texture_seed` / `image_seed` | — | reproducible geometry | reproducible texture | Vary only `texture_seed` to re-roll textures on the same mesh. `make --seed` sets `model_seed`; `redo` uses a fresh seed. |
| `negative_prompt` (text only) | — | — | — | ≤255. e.g. "base, pedestal, floating parts, text" |

### Game-oriented recipes (from the doc ranges; costs at H text pricing)
- Hero prop, PC: `--model tripo-v3.1 -p face_limit=50000 -p texture_quality=detailed` → 30.
- Low-poly prop, H-series with hand-crafted topology: `--model tripo-v3.1 -p smart_low_poly=true -p face_limit=3000` → 30.
- Low-poly prop, P1: `--model tripo-p1 -p face_limit=3000` → 40.
- Quad character for sculpting, rigging or subdivision: `--model tripo-v3.1 -p quad=true -p face_limit=20000` → 25 (FBX).
- Low-poly quads: `--model tripo-p2 -p quad=true -p face_limit=8000` → 110+.
- Kit-bash or modular parts: `--model tripo-v3.1 -p texture=false -p pbr=false -p generate_parts=true` → 30, then retexture.

---

## 10. Gotchas

1. **`tripo generate` has no `--dry-run`.** Only `tripo make` has it. (Corrected 2026-10-30 against `--help`: `tripo ai`, `batch run`, `redo`, `generate *`, `model *`, `mesh *` and `anim *` all lack `--dry-run`; an earlier draft wrongly said `ai` had it.) Appending `--dry-run` to `generate` is not a documented flag; do not do it, because it may error or submit. Validate the equivalent `tripo make` command instead (it uses the same payload builder `buildTextToModel/ImageToModel/MultiviewToModel`).
2. **Silent P1 auto-switch.** Without `--model`, `-p face_limit<=20000` or a "low poly" prompt switches to P1 and strips H-only params, with just a warning. Always pass `--model`.
3. **`generate_parts` 1004 trap.** The server rejects the request when `texture` is omitted (it defaults to true). The CLI only flips params that are explicitly `true`. Dry-run of `-p generate_parts=true` alone produced `{"generate_parts":true}` with no `texture:false`/`pbr:false`, which will 1004. With `-p texture=true`, it flips texture but leaves `pbr` unset (default true). **Always send `-p texture=false -p pbr=false -p generate_parts=true`.**
4. **`smart_low_poly` beats `generate_parts`** (no parts produced). With `quad=true`, parts are triangles.
5. **Quad forces FBX** (H docs). A quad mesh cannot be stored in GLB/GLTF, so later `convert` steps must target FBX/OBJ/USDZ. On H, `quad` without `face_limit` defaults to 10,000 faces.
6. **`export_orientation` corrupts post-processing silently.** Leave it unset and orient in the final `convert`.
7. **`orientation=align_image` does nothing without texture.**
8. **`texture_quality=fast` needs `texture_version=v3.5-20260815`**, otherwise 1004. The CLI rejects `fast` locally anyway (§11).
9. **`delight` is only read by texture v3.5.**
10. **`geometry_quality` must not be used with v2.5.** The v3.x-only params are listed in §3.1.
11. **P-series face_limit floor:** below 150/250 faces quality drops sharply.
12. **image-to-image rejects `seedream_v4`.** WebP inputs are rejected on some i2i provider routes; use PNG/JPEG.
13. **`quality` on a non-chat_image model is an error.** `background` on a non-2.5 model is silently ignored.
14. **`aspect_ratio` is honoured only by the banana family.** seedream and chat_image use `size`.
15. **chat_image_1 retired 2026-10-23.** Do not use it.
16. **Concurrency:** image generation runs 1 job at a time (serial), P series 5, H series 10 (error 2000 when full).
17. **Output URLs expire in about 5 minutes.** Re-download with `tripo task get <id> --download`. The file may be named `pbr_model` or similar.
18. **Failed tasks auto-refund.** A `timeout` exit (6) means the task is still running and will be billed. Do not `redo` it; run `tripo task watch <id>`.
19. **`-n` candidates multiply cost** (up to 4×). `-n` with `--then` needs a TTY.
20. **The 35-credit budget** rules out every P-series job except one untextured P1 text-to-model (30). (Corrected 2026-10-30.) Preflight with `tripo balance` and the §2 tables. The CLI's dry-run `cost_notes` are qualitative only (e.g. "higher price tier") and never numeric.
21. **multiview `inputs`:** front is required, at least 2 views, never mix the three input formats, and a `task_id` form must be a single-element array.

---

## 11. Doc vs CLI mismatches

| # | Topic | Official web docs | CLI 0.6.1 (bundled docs and/or code) |
|---|---|---|---|
| 1 | `texture_quality` values | `fast`, `standard`, `detailed`, `extreme` | `TEXTURE_QUALITIES = standard/detailed/extreme`. **`-p texture_quality=fast` is a blocking error** (dry-run verified). generate.md also omits `fast`. |
| 2 | `texture_version`, `delight` | Documented on all six 3D generation pages | Not in generate.md. They pass through `-p` untouched (dry-run verified). The `model texture` step whitelist `TEXTURE_MODELS` lacks `v3.5-20260815`. |
| 3 | `export_uv` scope | Listed on **H and P** pages (default true) | generate.md says "P series only" |
| 4 | P1 face_limit min | 50 (models page and P pages) | generate.md table says 48–20000 "(CLI enforces ≥50)". The code enforces 50. |
| 5 | `generate_parts` auto-fix | Omitting `texture` → 1004 | generate.md claims "The CLI flips both to false for you". The code only flips explicitly-true keys, so the default request still 1004s (dry-run verified). |
| 6 | H face_limit maxima (1.5M/2M/1M/500k; quad 150k) | Documented | Not validated (`face_limit=3000000` and quad `200000` → `valid:true`) |
| 7 | `geometry_quality` with v2.5 | "Do NOT use" | Not validated; passes through with a cost note |
| 8 | Unsupported models (`tripo-turbo`) | Not on the whitelist | generate.md says they are rejected (400), but `--model tripo-turbo` passes dry-run as `valid:true` and would fail server-side |
| 9 | "deterministic" `tripo generate` | — | Still runs `chooseModel`, so it auto-switches to P1 when `face_limit ≤ 20000` and no `--model` is given |
| 10 | Image model names | `banana`, `banana_pro`, `banana2` | generate.md lists `gemini-2.5-flash` / `gemini-3-pro` / `gemini-3.1-flash`, with the banana names as "backend aliases". Web docs and pricing use only the banana IDs; use those. |
| 11 | chat_image_2.5 models | `chat_image_2.5_flare`, `chat_image_2.5_sunburst` | Missing from generate.md and from the (unenforced) `TEXT_TO_IMAGE_MODELS`/`IMAGE_TO_IMAGE_MODELS` lists. They pass through. |
| 12 | t2i/i2i templates | t2i: asset_extraction, character_completion, t_pose, variants, figure. i2i: t_pose, character_completion, 3d_enhance, variants, figure. | generate.md lists all eight for both endpoints, including `head_extraction` and `print_clay` (in **no** web doc), plus `t_pose` and `sketch_to_render` booleans (in **no** web doc). These extra params are **UNKNOWN**/unverified. |
| 13 | Multi-reference syntax | `image[1]`, `image[2]` | generate.md says `[image 1]`, `[image 2]` |
| 14 | t2i prompt length | Recommended ≤300 CJK chars / ≤600 English words; negative after `--no` | generate.md says "≤1024 chars" for t2i/i2i and does not mention `--no` |
| 15 | t2i/i2i extra params | `size`, `quality`, `background`, `output_format`, `watermark` | Not documented in generate.md (passing them via `-p` works because unknown keys pass through) |
| 16 | image-to-multiview output | `output.generate_multiview_image.{front_view_url,...}` | generate.md lists the four `*_view_url` fields without the wrapper object |
| 17 | P-series pricing | Pricing JS: P1 text 30/40, image and multiview 40/50; P2 100/110; detailed/extreme for P not listed | generate.md: P2 "100 / 110 / 120 / 130 for none / standard / detailed / extreme". It is silent on P1 prices. |
| 18 | `--for game-mobile` chain | — | The make.md plan-card example shows a `texture` step plus convert; the actual scenario (code and dry-run) has only `convert FBX texture_size=2048`. Its texture_size makes it an **advanced** convert (10, not 5). |
| 19 | `--for film` "4K PBR" | — | film.md says "4K PBR", but the scenario only sets `texture_quality=detailed`. The texture resolution of `detailed` is **UNKNOWN** (only `extreme` = 8K is documented). |
| 20 | `--prompt` flag on generate subcommands | image-to-model/multiview/splat/i2mv/edit-mv have no prompt param | The CLI shows `--prompt` on all non-text subcommands, but only `image-to-image` uses it. Elsewhere it is silently ignored. |
| 21 | Splat input | file_token or URL (no task_id listed) | CLI resolves `@last`/task ids generically; whether the server accepts a task_id for splat is **UNKNOWN** |
| 22 | P2 quad → FBX | Only the H pages say quad forces FBX | CLI warns "forces FBX" for P2 quad as well. Actual P2 output format is **UNKNOWN**. |
| 23 | quad + GLTF convert | Quad cannot be stored in GLB/GLTF | make.md lists "quad + GLTF" among blocking dry-run errors, but `--model tripo-v3.1 -p quad=true --then convert:gltf --dry-run` returns `valid:true`. The skill must block this itself. |
| 24 | `--then` replaces scenario step args | — | `--for game-mobile --then rig,convert:fbx` drops the scenario's `texture_size=2048` (convert becomes basic, 5 credits) and the `rig` step gets only `model=v2.5-20260210` (no `spec`/`out_format`, no `rig-check` inserted). Pass step args explicitly when overriding. |

---

## 12. Open questions (UNKNOWN; resolve with a cheap real run or support)
- The actual face count produced when `face_limit` is omitted (H adaptive / P adaptive).
- Texture map resolution for `standard` and `detailed` (only `extreme` = 8K is documented).
- Credit cost of `texture_version=v3.5-20260815`, `pbr=false` with texture, and P2 `quad`.
- P1 `detailed`/`extreme` texture add-on prices.
- Whether `compress` is accepted on the P series, and whether Godot/Blender import meshopt-compressed GLBs.
- P2 output format with `quad=true`, and its default face count when `face_limit` is omitted.
- The undocumented CLI-only image params (`head_extraction`, `print_clay`, `sketch_to_render`, `t_pose` boolean).

---

## 13. Verified via dry-run (2026-10-30)

Adversarial re-check against the installed `tripo-cli` 0.6.1. Every command was run with `--dry-run --json --yes` appended (zero network, zero credits). Image commands used 256×256 placeholder PNGs, because dry-run errors with `file not found` when the file is missing. Flags were confirmed with `tripo make --help`, `tripo generate --help`, `tripo generate text-to-model --help`, `tripo generate image-to-model --help`, `tripo redo --help` and `tripo ai --help`.

| # | Command (`tripo make ...`) | valid | Model / payload | Warnings / errors |
|---|---|---|---|---|
| 1 | `"a stylized wooden crate" --for game-mobile` | true | P1; `texture,pbr,texture_quality=standard,face_limit=15000`; convert `FBX texture_size=2048` | W: non-default convert options use the "complex convert" price tier |
| 2 | `... --for game-pc` | true | v3.1; `texture,pbr,texture_quality=detailed`, no face_limit; convert `FBX` | none (cost note: detailed tier) |
| 3 | `... --for film` | true | v3.1; `texture,pbr,quad,geometry_quality=detailed,texture_quality=detailed`; no chain | W: quad=true forces FBX output |
| 4 | `... --for print` | true | v3.1; `texture=false,pbr=false`; convert `STL flatten_bottom=true` | W: complex convert tier |
| 5 | `... --for ar-web` | true | v3.1; `texture,pbr`; decimate (`/v3/mesh/decimate`, `highpoly_to_lowpoly`, `face_limit=20000`, no model) → convert `USDZ` | none |
| 6 | `... --for anim` | true | v3.1; `texture,pbr`; rig-check → rig `model=v2.5-20260210 spec=tripo out_format=glb` → retarget `[preset:idle,preset:walk]` | none (cost note: billed per animation) |
| 7 | `... --for toy` | true | P1; `texture,pbr,face_limit=20000`; no chain | none |
| 8 | `"a wooden crate" --model tripo-v3.1 -p smart_low_poly=true -p face_limit=5000` | true | v3.1; SLP kept | none |
| 9 | `"a wooden crate" -p smart_low_poly=true -p face_limit=5000` | true | **auto P1** ("face budget 5000 ≤ 20000 → P1"); SLP stripped | W: P1 does not support smart_low_poly (removed) |
| 10 | `"a wooden crate" --model tripo-p1 -p face_limit=3000` | true | P1, face_limit 3000 | none |
| 11 | `"a wooden crate" --model tripo-p2 -p quad=true -p face_limit=12000` | true | P2 | W: quad forces FBX |
| 12 | `"a wooden crate" --model tripo-v3.1 -p quad=true -p face_limit=20000` | true | v3.1 | W: quad forces FBX |
| 13 | `"a wooden crate" --model tripo-v3.1 -p texture=false -p pbr=false -p generate_parts=true` | true | correct parts request | none |
| 14 | `"a wooden crate" --model tripo-v3.1 -p generate_parts=true` | **true** | payload `{generate_parts:true}` only, so texture/pbr default to true server-side → 1004 at submit | **none** (the CLI does not catch it; gotcha 3 confirmed) |
| 15 | `"a wooden crate" --model tripo-v3.1 -p texture_quality=extreme -p texture_version=v3.5-20260815 -p delight=false` | true | passthrough | none |
| 16 | `"a wooden crate" --model tripo-v3.1 -p texture_quality=fast -p texture_version=v3.5-20260815` | **false** (exit 2) | — | E: texture_quality must be one of standard/detailed/extreme |
| 17 | `"a wooden crate" --model tripo-v3.1 -p face_limit=50000 -p texture_quality=detailed -p negative_prompt="base, pedestal" --seed 42` | true | `--seed` → `model_seed:42` | none |
| 18 | `concept.png --model tripo-p2 -p quad=true -p face_limit=8000 -p orientation=align_image -p texture_alignment=geometry -p enable_image_autofix=true` | true | image-to-model, `input:"<upload:concept.png>"`, pending_uploads `[concept.png]` | W: quad forces FBX |
| 19 | `front.png back.png left.png --model tripo-v3.1 -p face_limit=60000` | true | multiview view-key `[{front},{left},{back}]` (canonical order) | none |
| 20 | `concept.png --for game-mobile --then rig,convert:fbx` | true | P1 image-to-model (scenario params kept); rig `model=v2.5-20260210` only; convert `FBX` (no texture_size) | W: --then overrides the default game-mobile processing chain |

Extra checks (also dry-run):

| Command (`tripo make ...`) | Result |
|---|---|
| `--model tripo-turbo` | valid:true, sends raw `"model":"tripo-turbo"` |
| `--model tripo-v3.1 -p face_limit=3000000` / `-p quad=true -p face_limit=200000` | valid:true (H maxima not validated) |
| `--model tripo-p1 -p face_limit=48` | E: P1 face_limit must be within 50–20000 |
| `--model tripo-p2 -p quad=true -p face_limit=30000` | E: P2 face_limit must be within 48–25000 with quad=true |
| `--model tripo-v3.1 -p smart_low_poly=true -p face_limit=300` | E: smart_low_poly requires face_limit 500–20000 |
| `--model tripo-v3.1 -p smart_low_poly=true -p quad=true -p face_limit=15000` | E: smart_low_poly requires face_limit 500–10000 (quad halves the budget) |
| `--model tripo-v3.1 -p generate_parts=true -p texture=true` | valid; texture→false, pbr left unset (W: generate_parts=true disables texture) |
| `--model tripo-v3.1 -p generate_parts=true -p pbr=true -p quad=true` | valid; pbr→false, quad→false, texture left unset (two warnings) |
| `--model tripo-v2.5 -p geometry_quality=detailed` | valid; cost note only |
| `"a low poly wooden crate"` (no --model) | auto P1, reason "low-poly intent → P1", no warning |
| `--model tripo-v3.1 -p pbr=true -p texture=false` | valid; texture forced true (warning) |
| `--for game-pc -p face_limit=5000` | stays v3.1, face_limit 5000 merged |
| `--model tripo-p2 -p smart_low_poly=true -p generate_parts=true -p geometry_quality=detailed` | valid; all three stripped with warnings |
| `--model tripo-p1 -p quad=true` | valid; quad stripped, W suggests `--model tripo-p2` |
| `concept.png -p face_limit=8000` (no --model) | auto P1 for image input too |
| `-n 5` | E: at most 4 candidates per run |
| `--model tripo-v3.1 -p quad=true --then convert:glb` | E: unsupported format "glb" |
| `--model tripo-v3.1 -p quad=true --then convert:gltf` | **valid:true** (not blocked, see §11 #23) |
| §8.5 compress/auto_size/export_uv/seeds command | valid; all keys pass through, `--seed 42` → `model_seed` |

Doc spot-checks (`tripo docs --topic ...`), all confirmed as the note describes: generate.md P1 "48–20000 (CLI enforces ≥50)"; `export_uv` "P series only"; generate_parts "The CLI flips both to false for you" (contradicted by row 14); `tripo-turbo` "not on the v3 whitelist (400)" (contradicted by the dry-run); image models listed as `gemini-*` with banana aliases; templates include `head_extraction`/`print_clay`; multi-reference syntax `[image 1]`; texture_quality `standard/detailed/extreme` only; make.md plan card for game-mobile shows a `texture` step that the real scenario lacks; film.md "4K PBR"; common-errors concurrency H 10 / P 5 / image 1; process.md decimate default `v2.0` = 30 credits (supports the ar-web estimate); `tripo generate image-to-model --help` shows `--prompt`; the `make.md` dry-run example for row 20 matches the real output field for field.

Corrections applied in this pass: §0 (one P1 job is affordable), §10 gotcha 1 (`ai` has no `--dry-run`), §10 gotcha 20 (same P1 fix), §8.3 (new validation rows), §11 #23–24 (new mismatches).
