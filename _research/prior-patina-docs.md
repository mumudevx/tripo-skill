# Prior art: Patina (Godot 4.7.2) docs on the Tripo / Gemini / Godot asset pipeline

Source project: `/Users/muhsin/Documents/GitHub/mumudevx/patina` (read-only). Paths below are relative to that root unless absolute.
Read in full: `CLAUDE.md`, `docs/gdd/07-ai-asset-pipeline.md`, `docs/asset_log.md`, `scripts/dev/asset_concepts.py`, `scripts/dev/gemini_image.py`, `scripts/dev/model_turnaround.gd`. Read in their asset-related sections: `docs/decisions.md` (ADRs 2026-10-07 to 2026-10-12), `docs/later.md` ("Asset generation (needs credits)"), `docs/questions.md` (section 12 "Build, performance and models"). Headers read: `scripts/dev/model_kit.gd`, `mesh_reducer.gd`, `normal_crease.gd`. Also checked: `git log` (414 commits; asset commits are `art(...)` / `docs(assets)` / `docs(models)`; their bodies are mostly empty, so the docs are the record), and the git-ignored `art_source/` tree for file layout and `task.json` contents.

Nothing was rigged or animated by Tripo in Patina. Every model is a static part, and motion is Godot tweens on sockets. Patina has no prior art for the skill's rigging step.

---

## 1. The pipeline as it was actually run (summary)

`CLAUDE.md` section "3D models and reference images (Tripo CLI + Gemini)" (lines 218-252) and GDD 07 section 7.5 "As built" are the authoritative pipeline. GDD 07 sections 7.1-7.3 (Meshy, then a Blender split and cleanup) were never used. The banner at the top of `docs/gdd/07-ai-asset-pipeline.md` (line 3) says so.

1. Write a manifest `art_source/<antiques|props>/<id>/parts.json` with `reference_sheet`, `subject`, and `parts[]`. Each part has `id`, `name`, `description`, `faces` (every face described), optional `view_set`, and per-view `views` notes. Example: `art_source/antiques/folding_camera_01/parts.json`.
2. Generate a reference sheet for the whole object (assembled, plus parts laid out). The owner approves it.
3. `asset_concepts.py <parts.json> hero`: one hero image per part, made with the reference sheet as input.
4. `asset_concepts.py <parts.json> views`: front, left, back and right views, each made with the hero image as input.
5. `asset_concepts.py <parts.json> sheets`: an ffmpeg hstack contact sheet per part (`concept/<part>/_sheet.png`).
6. Approval gate: show the sheets to the owner and wait before any 3D credit is spent (`CLAUDE.md:234`).
7. `tripo generate multiview-to-model front.png left.png back.png right.png ... --model tripo-v3.1 -o <dir> --json --yes --no-open` with no face limit (`CLAUDE.md:235-240`).
8. `tripo mesh decimate <task> --model v3.0 --face-limit <n> --smart-uv`, a retopology that re-bakes the textures (`CLAUDE.md:242`).
9. Turnaround QA: `model_turnaround.gd` renders 8 views, which are checked by eye (`CLAUDE.md:247`).
10. Copy into `assets/models/<antiques|props>/<id>/<id>_<model>.glb`. A generator script (`scripts/dev/generate_<object>_models.gd` using `ModelKit`) builds the Godot scene: mesh to `.res` with hard edges, shared shader, picking box, socket. Scenes are never hand-edited (`CLAUDE.md:209`, `docs/gdd/07-ai-asset-pipeline.md:93-101`).
11. Add a row to the licence log `docs/asset_log.md` (`docs/gdd/07-ai-asset-pipeline.md:130-135`).
12. Ingame screenshots go to `art_source/.../ingame/`. Weak models are recorded in `docs/later.md` with the credit cost of a fix.

---

## 2. GENERAL lessons (true for any game). Candidates for the global skill.

### 2.1 Reference images (the "review the reference image before sending" step)
- **Keep the style formula byte-identical in every prompt**, re-rolls included. The description goes before it and the framing suffix after it (`CLAUDE.md:231`; constant `STYLE` in `scripts/dev/asset_concepts.py:23-25`). Patina's suffix is "Plain pure white background, no shadow, no floor, the whole object inside the frame with a margin, one object only. Avoid: ... text, labels, numbers, logos, brand names." (`asset_concepts.py:26-28`).
- **Describe every face, including top, back and underside.** Whatever the prompt leaves open, image-to-3D invents. Example: "plain flat top, no slot, no grille" (`CLAUDE.md:232`). The `faces` field in the manifest exists for this (`art_source/antiques/folding_camera_01/parts.json`).
- **Use a hero-then-views chain.** The hero image (three-quarter view, from the front left, slightly above) is made against the approved reference sheet. Each orthographic view is made against the hero, never against the sheet (`asset_concepts.py:65-86`).
- **Tripo's side convention.** In `left.png` the front of the object points to the image's left edge. In `right.png` it points to the right edge. Name files by what the image shows, not by what the image model was asked for. Swapped sides gave the mailbox a letter slot on both faces (`CLAUDE.md:233`, `asset_concepts.py:29-37`).
- **Typical image-model failures in views, with their fixes** (`CLAUDE.md:233, 244`):
  - A side view comes back as a three-quarter view. Fix: say in the view note that the front face is not visible at all.
  - A view the model keeps drawing three-quarter (the camera body's back, 3 times). Fix: use the straight `front.png` as the input image instead of the hero. It came out flat at once.
  - A part drawn lying down in one view, when the part is rotationally symmetric. Fix: generate only `front` and reuse it as `back`.
  - A thin part (wire, rod) whose end-on view fills the frame. Fix: generate `front` and `back` only (the manifest's `view_set`).
  - A lying, all-round part (screwdriver). **Its back view must be the front view mirrored, never a plain copy.** A plain copy produced "two screwdrivers" (`CLAUDE.md:250`).
- **One view that disagrees with the others gets re-rolled, not kept** (`CLAUDE.md:233`).
- **Never feed a multi-object sheet to image-to-3D.** It fuses everything into one mesh (`CLAUDE.md:235`).
- **A single hero image through `tripo make` is a fallback only.** It leaves the unseen sides to chance. The first mailbox got a toothed strip across its lid this way (`CLAUDE.md:235`).
- **The clock case needed three straight views.** With two three-quarter views, the opening landed on a side face (`docs/decisions.md`, ADR 2026-10-07 "Desk clock look test", Notes).
- **No real brands or logos in prompts.** Use invented brand names (`docs/gdd/07-ai-asset-pipeline.md:38`).
- **Prompt hints for thin parts.** The mailbox letter came out "as thick as a parcel". The planned fix is to put "a flat, stiff paper envelope" in the prompt (`docs/later.md`, "Mailbox: the front of the letter is draped"). The camera's manifest gives dimensions in the description ("24 wide, 13 high, 7 deep") and says "exactly one single flat plate alone in the image" (`art_source/antiques/folding_camera_01/parts.json`).

### 2.2 Tripo generation parameters (tripo-cli; never invent a parameter, read `tripo docs`)
Source: `CLAUDE.md:235-246`. The Tripo manual is at `tripo docs --topic commands/generate` and `commands/process`.

- **Use `multiview-to-model` from 2 to 4 views** (`front` is mandatory). Same object and same light in all of them, PNG.
- **Set `--model tripo-v3.1` for anything the camera comes close to.** `tripo-p1` is auto-picked at `face_limit` 20000 or less and costs 50 credits. Use it only for far background decoration at about 3000 faces (`CLAUDE.md:236`). The first mailbox task really ran on P1 at 50 credits (`art_source/props/mailbox_01/tripo_raw/task.json`: `"model_version": "P1-20260311"`, `"credits_consumed": 50`).
- **Never set a `face_limit` at generation for hard-surface parts.** It makes hard surfaces wavy, turns small holes into dents, and leaves fine slots and grips soft. Generate at full resolution instead (about 1.4M tris, 30 credits), then reduce (`CLAUDE.md:237`, `docs/gdd/07-ai-asset-pipeline.md:105`).
- **Reduction recipe:** `tripo mesh decimate <generation task id> --model v3.0 --face-limit <n> --smart-uv` costs 35 credits. It re-bakes texture and normals for the new mesh, so flat faces stay flat and round walls stay smooth. The basic `--model v1.0` (10 credits) keeps the high-poly normal map on low-poly triangles: flat faces show a fan of facets and round walls look creased. The A/B was run on the camera's shutter (`art_source/antiques/folding_camera_01/tripo_raw/_ab_shutter/cmp_shutter.png`) and is recorded at `CLAUDE.md:242`. The reduction task in `task.json` has type `highpoly_to_lowpoly` with `{"bake": true, "quad": false, "smart_uv": true, "face_limit": 11000, "original_model_id": ...}` and `credits_consumed` 35 (`art_source/antiques/folding_camera_01/tripo_raw/body/reduced/...`).
- **Pick the face limit by eye, lowest first.** A knob holds at 3000. A panel with 45 holes needs about 12000 and crumples at 4000 (`CLAUDE.md:237`).
- **Do not use these:**
  - `smart_low_poly=true`: 40 credits and worse than a plain limit.
  - `--model v2.0` smart decimation: 30 credits. It dished the panel at 3000 and tore it into spikes at 20000.
  - `quad`: forces FBX.
  - `generate_parts`: switches the texture off.
  - `compress`, `auto_size`, `orientation`, `export_orientation`: later steps do not inherit them and report success on a model that lies wrong. Place the model in-engine instead.
  - `--for` presets: they add an FBX conversion that Godot does not need.

  Sources: `CLAUDE.md:236-237, 241`.
- **Do not use `geometry_quality=detailed` or `texture_quality=detailed`.** They cost 60 instead of 30 credits, turn printed detail (tick marks) into lumps at a game budget, and nothing else looks better after reduction (`CLAUDE.md:243`).
- **Keep texture and PBR on** (`CLAUDE.md:240`).
- **Re-roll rules.** `task.json` keeps `model_seed` and `texture_seed`. A bad mesh gets a new generation. A bad texture on a good mesh gets `tripo model texture <task> --texture-alignment geometry` (or `original_image`), never a new mesh (`CLAUDE.md:245, 247`). Cap re-rolls at 2 per object (`tripo redo`), then take the best (`CLAUDE.md:247`).
- **Higgsfield's earlier calls were no better.** It used `tripo_h3_1_image_to_3d` from one image with `face_limit` 1500-8000, and its parts carry the same face-limit damage (`CLAUDE.md:239`).

### 2.3 Money and credit safety (the "plan generation (budget)" step)
- **Price table as measured** (`CLAUDE.md:236-243`, `docs/later.md`):

  | Step | Credits |
  |---|---|
  | v3.1 generation, no face limit | 30 |
  | P1 generation | 50 |
  | Decimate v1.0 | 10 |
  | Decimate v2.0 | 30 |
  | Decimate v3.0 + smart-uv | 35 |
  | smart_low_poly | 40 |
  | Detailed quality | 60 |

  **One finished part is 30 + 35 = 65 credits.** `docs/later.md` prices every fix this way, for example "a new one is 65 credits a part".
- **Check the balance before and after.** Run `tripo balance` on both sides. The `generate` commands have no `--dry-run`, so the price comes from the balance difference. `tripo make` does have `--dry-run --json` (`CLAUDE.md:235, 246`).
- **CLI exit codes** (`CLAUDE.md:235, 246`):
  - Exit code 4: out of credits. Tell the owner and do not retry.
  - Exit code 6 with `timeout`: the task still runs. Use `tripo task watch <id> --download`, never a second generation.
  - Exit code 7: check `tripo balance` before resending, because the task may already exist.
- **A failed or cancelled task is not charged** (`CLAUDE.md:246`).
- **Generate only what was asked for.** Credits are the owner's (`CLAUDE.md:220`). Before an image run, tell the owner how many images and the rough cost. After it, report the token counts the script printed (`CLAUDE.md:224`).
- **Log a running balance with what it buys.** For example, "Tripo balance: 20 credits (2026-10-12). A new model is 65." (`docs/later.md`).
- **Image cost (Gemini, `gemini-3.1-flash-image`)** (`CLAUDE.md:223-227`, `scripts/dev/gemini_image.py`):
  - A 1K image is about 1450 output tokens: about 0.09 USD direct, half that through the Batch API. A batch takes about 4 minutes.
  - Hero plus 4 views comes to about 20 TRY direct, about 10 TRY batched.
  - `GEMINI_BATCH_RESUME=<batches/...>` fetches an already-paid job instead of resubmitting it.
  - **Keep views at 1K.** 512 px saved about 20% of tokens, but the views agreed less with each other and the Tripo model came out jumbled.
  - The lite model costs the same and drew the object differently. A GPT image model was not cheaper at the same quality.
  - Save money by needing fewer views (1 for an all-round part, 2 for a thin part), not by lowering resolution.

### 2.4 QA of a returned model (the "headless-Blender QA" step)
- **Check all sides, not only `preview.png`.** Look at front, back, top and underside for invented geometry, holes, fused details, and a face that appears twice (`CLAUDE.md:247`). Patina's tool is a windowed Godot render of 8 views (`scripts/dev/model_turnaround.gd`: front, back, left, right, top, under and two quarter views, light grey background). It also prints the triangle count and AABB of each mesh. A headless-Blender equivalent is the natural port.
- **Before blaming a mesh, look at it with its normal map off** (`normal_strength` 0). Two "mesh" faults turned out to be the normal texture: the radio's bent dial glass and the creased back panel (`CLAUDE.md:213`; `docs/decisions.md` ADR 2026-10-11 "Flat faces ... hard edges", section "five radio models are drawn without their normal texture").
- **Generated models have no hard edges.** Every vertex normal is the mean of all faces around it, so a flat face next to a steep one is lit as if dented (the clock dial showed a "fan of facets" and a dent beside every hour mark). The fix is normal splitting by angle: an edge is hard above 30 degrees between faces, faces joined by soft edges share an area-weighted normal, and vertices split only along hard edges. The first version (per-corner within 30 degrees of its own triangle) broke 1/5 of soft edges, so the decision must be made per edge (`docs/decisions.md` ADR 2026-10-11 "Flat faces of the models are flat", including its "Corrected the same day" section; `scripts/dev/normal_crease.gd`). In Blender the equivalent is Auto Smooth / "Smooth by Angle" at 30 degrees, plus weighted normals. The skill's QA should check for this, or apply it as the free fix.
- **Hard edges expose what a reduction did**, which smooth normals had hidden. This is one more reason to take a model whole when the budget allows (`docs/gdd/07-ai-asset-pipeline.md:103`).
- **Keep smooth normals for outline shaders.** A hover-outline hull grown along split normals opens at every hard edge. Patina stores the smooth normal in `CUSTOM0` (`CLAUDE.md:213`).
- **Glass always comes out opaque and painted.** Tubes, lenses, dial glass and magnifiers were all painted surfaces. The workaround is a shader that reads the painted area (grey or pale-blue) as glass (`glass_luminance_from/_to`, `glass_by_coolness`). Real see-through glass would need a separate glass model (`docs/gdd/07-ai-asset-pipeline.md:105, 112`; `CLAUDE.md:252`; `docs/questions.md` section 12 "Painted glass on the camera").
- **Common defects to look for:**
  - Holes embossed instead of cut.
  - Slots painted instead of cut. The mailbox slot is painted, so the letter passes through the surface.
  - Scale errors: thin parts come out thick (letter, top plate, door).
  - Wrong colour: the camera leather came out olive, not black.
  - Extra invented details: a pale pebbled strip, a post in an empty chamber, a cross head instead of a slot.
  - Square corners on a part meant to fit a round body.
  - Metal and wood sharing one material, so the metal looks dull.
  - Round outlines that read as polygons close up: about 24 segments on the clock bezel.

  Sources: `docs/later.md`, "Folding camera: models that came out weak", "Mailbox", "Desk clock: the bezel is a polygon", "Tool models for the rack".
- **Look at the model in the game, at the distance it is seen from**, and from the back too (turn it). The first radio screenshots never turned the antique, which hid the creased back panel (`docs/decisions.md` ADR 2026-10-11, section "five radio models"; `CLAUDE.md:213`).

### 2.5 Fixing: free (local) fixes vs paid (Tripo) fixes
Patina's documented pattern is to try the free in-engine fix first and record the paid fix with its price.

Free fixes that worked:
- Scale-press a part that came out too thick, using a non-uniform scale on its own axes (`docs/gdd/07-ai-asset-pipeline.md:110`).
- Offset a mesh that is not centred on its functional part (`docs/gdd/07-ai-asset-pipeline.md:110`).
- A shader `dark_tint` to pull the olive leather to black (`docs/later.md`).
- Glass shaders that read the painted glass areas.
- Hard-edge normals.
- Dropping a misfit normal texture.
- Engine LOD reduction with `MeshReducer`: it takes the finest LOD that fits, and closes the shortest edges when the model is within 1% over budget.

Paid fixes:
- `tripo model texture` for colour or wear problems on a good mesh. It is cheaper than a new model.
- Re-decimate with v3.0 (35 credits) when only the normal texture is wrong.
- Full regeneration (65 credits) when the mesh itself is wrong.

Sources: `docs/later.md` (each weak model with its fix and price), `CLAUDE.md:245-247`.

**Lesson: a model loses triangles only for a budget.** Halving the gear train and mainspring "looked crumpled". The radio cabinet at a quarter turned the grille opening into a polygon. A test now fails when a reduced model could come one LOD finer inside the budget (`docs/decisions.md` ADR 2026-10-11; `docs/gdd/07-ai-asset-pipeline.md:68`).

**When a set is over budget, choose with the models side by side** (old, half, quarter, whole) and on the bench. Give triangles to the parts that bend when halved and take them from flat panes and screws (`docs/decisions.md` ADR 2026-10-11, section "a model loses triangles only for a budget").

### 2.6 Placing into Godot (the "replace the placeholder" step)
- **Never hand-edit scenes for models.** A generator script builds the scene from the `.glb` files and is re-run. The `.glb` stays as it came. The mesh is saved once as `meshes/<model>.res`, and deleting the `.res` rebuilds it (`CLAUDE.md:209`; `docs/gdd/07-ai-asset-pipeline.md:96-103`; `scripts/dev/model_kit.gd` header).
- **Keep the placeholder's node names, sockets, data and payoff**, so no rule, data or save changes when the model scene replaces the greybox. Swapping the placeholder for a model must keep that interface (`docs/decisions.md` ADRs "the tube radio from its part models" and "The folding camera from its part models"; ADR 2026-10-09 "Park asset work": "an antique keeps its definition and its node names when its scene is replaced by a model one").
- **A Tripo model comes normalised to about 1 unit and faces its own way**, so every part needs a rotation, a scale and a place. Patina's helpers are `ModelKit.lay()` and `prop_node()`: which model axis lies along X, which points up, a press along its own axes, then stand the node with its middle over its place (`CLAUDE.md:250`; `docs/gdd/07-ai-asset-pipeline.md:94`).
- **Measure the layout from the main/case model, not from the placeholder numbers.** A generated case has its own wall thickness and features (`docs/decisions.md` ADR "the tube radio from its part models", point 2).
- **Let a part model's own details say where its neighbours go.** Screw holes and pockets in the plate model fix where the screws and the knob go, and a boss and a post on the body fix where the release and the spool go. A part model knows nothing of its neighbours (`docs/gdd/07-ai-asset-pipeline.md:107-110`).
- **Payoff animations must key scale as a share of the rest scale.** Model parts are scaled into place, so absolute keys "would have blown the speaker up" (`docs/decisions.md` ADR "the tube radio", point 3).
- **Watch collisions with gameplay space.** A prop's whole bounding box must stay out of interaction zones; the lamp was made small and put in a corner for this (`CLAUDE.md:250`).
- **Cold-load time grows with models.** The camera's first cold read took 1.0 s, so load scenes in the background (`docs/decisions.md` ADR 2026-10-12 "The folding camera", point on the probe).
- **For a draw-call budget, let display copies cast the shadow of their largest part only** (`docs/decisions.md` ADR "the tube radio", "Closed on 2026-10-11").

### 2.7 Records and licensing (the "record lessons" step)
- **Licence log, one row per asset or asset group.** Columns: `asset_path | source_tool | plan/license | generation_date | prompt_ref | human_edited | notes`. In the source tool, name the model version, the command, and whether a face limit and reduction were used (`docs/asset_log.md`; `docs/gdd/07-ai-asset-pipeline.md:130-135`). The log is evidence for the Steam AI content disclosure (`docs/gdd/12-publishing-steam-epic.md:35`). Reference images are logged too, as "input of the 3D step only".
- **Commercial terms of Tripo and Gemini were logged as "paid", not read.** Check them before release (`docs/gdd/07-ai-asset-pipeline.md:135`).
- **Owner decision: the credits name no AI tool.** A test enforces this, and disclosure happens on the store page (`docs/decisions.md` ADR 2026-10-11 "The demo looked at screen by screen", answers of the owner).
- **Lessons were captured as:**
  - recipes in `CLAUDE.md` with the date and object they were measured on;
  - an ADR per model batch (decision, rationale, measured numbers, "not verified");
  - `docs/later.md` items for each weak model, each with a concrete fix and its credit price;
  - `docs/questions.md` entries with "Built as: <default>" for anything the owner should confirm.

  This structure maps well to `<project>/.claude/tripo/`.

### 2.8 File layout of the raw work (proven, git-ignored)
Each object lives under `art_source/<kind>/<id>/`. The folder has a `.gdignore` so Godot does not import it (`art_source/.gdignore`). It holds:
- `parts.json`: the manifest.
- `concept/_reference_sheet.png`.
- `concept/<part>/{hero,front,left,back,right}.png`, each with a `.txt` file holding its exact prompt (`asset_concepts.py:44-45`), plus `_sheet.png`.
- `tripo_raw/<part>/{full,reduced}/tripo-out/<slug>-<taskid8>/{task.json,model.glb,preview.png}`.
- `final/`: the files that are copied into `assets/`.
- `turn/`: turnaround renders and comparison sheets (`_models_a.png`).
- `ingame/`: screenshots.
- `tripo_raw_rejected/`.

The Tripo CLI's directory context was added to `.gitignore` (commit `ec294e2`). In Godot only `assets/models/<antiques|props>/<id>/<id>_<model>.glb` is imported (`CLAUDE.md:102`).

---

## 3. PROJECT-SPECIFIC lessons (Patina only; do not promote)

- **Style constants** are "stylized realistic, soft beveled edges, simplified details, warm vintage, 1930s-1950s antique, clean readable shapes, game asset, centered, neutral lighting, plain background" (`docs/gdd/07-ai-asset-pipeline.md:31-36`). For a new object, the fallback style guide is `art_source/antiques/desk_clock_01/concept/_reference_sheet.png` (`CLAUDE.md:232`).
- **Triangle budgets:**
  - Part: 12k (raised from 3k on 2026-10-11, because perforated plates and thin glass do not survive 3k).
  - Antique: 60k (from 40k).
  - Scene: 500k.
  - Draw calls: under 300 on Steam Deck at 60 FPS.

  Enforced by `tests/integration/test_performance_budget.gd` and `test_model_fidelity.gd` (`docs/gdd/07-ai-asset-pipeline.md:58-68`; `docs/decisions.md` ADR 2026-10-11 "The demo is the goal"). The radio is 90k whole, so its generator gives a `TRIANGLES` table per model (59.3k) and a `NO_NORMAL_TEXTURE` list (`scripts/dev/generate_tube_radio_models.gd`).
- **Naming:**
  - Part mesh nodes are `part_<id>` and must equal `PartDefinition.id`.
  - Sockets are `socket_<id>`.
  - Collision is `part_<id>-convcolonly`.
  - Solder points are `solder_a` / `solder_b` markers in the part's own units.
  - Files are `<id>_<model>.glb`. A model used twice is one file.

  Sources: `CLAUDE.md:61, 102`; `docs/gdd/07-ai-asset-pipeline.md:83-101`.
- **Shaders:**
  - `antique_master.gdshader` (dirt and rust layers, brass/walnut profiles, `dark_tint`).
  - `antique_glass.gdshader` (`glass_by_coolness`, luminance range).
  - `prop_surface.gdshader` for props. `METAL_PROP_LOOK` shows the model's own metal map; it is not used where the map is wrong (the glue tube).

  Shared material library and lighting carry the style, so parts from separate generations read as one object (`CLAUDE.md:206, 250`; `docs/decisions.md` ADR 2026-10-07).
- **Generators and run order.** `generate_greybox.gd` runs first, then `generate_desk_clock_models.gd`, `generate_tube_radio_models.gd` and `generate_folding_camera_models.gd`. Generators re-assign `unique_id`s, so `git checkout -- scenes` whatever changes were not meant (`CLAUDE.md:31-34, 183, 209`).
- **Every part is AI-generated, even screws and plates.** This replaced GDD 07 section 7.1's "class C parts by hand in Blender". It was the owner's decision after the clock look test: "all parts must come from the same source to look consistent" (`docs/decisions.md` ADR 2026-10-07). It matches the user's global CLAUDE.md rule.
- **The tool stack changed.** Higgsfield was suspended on 2026-10-10. Since then the stack is the Tripo CLI plus the Gemini API (`GEMINI_API_KEY` is in the environment, never in the repo) (`CLAUDE.md:220`). GDD 01, the GDD index, and GDD 12 still say "Meshy → Blender → Godot" and "Meshy assets are disclosed". These are stale (`docs/gdd/01-vision-and-pillars.md:40`, `docs/gdd/index.md:9,39`, `docs/gdd/12-publishing-steam-epic.md:35`). `docs/later.md` has an open item to rewrite GDD 07.
- **Owner's design calls on specific models:**
  - The viewfinder stands on the body through the top plate (the plate model has no opening). Open question: change the dependency data instead? (`docs/questions.md` section 12)
  - The radio's back panel is kept whole because it is the first part the player works on.
  - The pocket watch is about 2x life size and still needs a real-model answer.
- **Weak models and their priced fixes** are listed in `docs/later.md` "Asset generation": radio cabinet, speaker, transformer (65 each); five radio models with a misfit normal texture (35 each, 175 total); clock bezel and case; mailbox letter and box with a cut slot; camera lens, body, top plate, back door, shutter, viewfinder, spool, screw; spatula and tweezers (65 each). The Tripo balance was 20 credits on 2026-10-12.
- **Desk clock.** Its 8 parts were generated through Higgsfield (GPT Image 2.5 concepts plus Tripo H3.1), not through this CLI recipe. Its dial and hands are still part of the case model, and the gear train must be split (about 40-50 credits) (`docs/later.md`, "Desk clock, missing parts").

---

## 4. Reusable tools and recipes worth porting into the skill

| Tool | Path | Port as |
|---|---|---|
| Manifest-driven hero, views and sheet image chain | `scripts/dev/asset_concepts.py` | Generic `concepts.py`. Keep: the byte-identical STYLE/SUFFIX, the `faces` field, `view_set`, per-view notes, the Tripo side convention text, skipping existing files (delete to re-roll), the prompt `.txt` beside each image, and the ffmpeg hstack contact sheet. |
| Gemini image client (direct and Batch API at half price, resume, token report) | `scripts/dev/gemini_image.py` | Optional backend for the reference-image step (the user may use Higgsfield instead). Inline batch kept under about 14 MB. |
| 8-view turnaround render with tri count and AABB print | `scripts/dev/model_turnaround.gd` | Headless-Blender `turnaround.py` (front, back, left, right, top, under, two quarters) plus a stats JSON. |
| Hard-edge normals by angle, smooth normals kept for outlines | `scripts/dev/normal_crease.gd` | Blender "Smooth by Angle" 30 degrees, plus a QA metric for "no hard edges" (share of edges above 30 degrees that are smooth-shaded). |
| Budget reducer (finest LOD that fits; within 1% over: close the shortest edges) | `scripts/dev/mesh_reducer.gd` | Free-fix option: Blender Decimate (collapse) to the face target, compared against paid `tripo mesh decimate --model v3.0`. |
| Godot placement kit (`.res` mesh cache, shared shader, picking box, socket, `lay()` / `prop_node()` axis mapping) | `scripts/dev/model_kit.gd`, `scripts/dev/generate_folding_camera_models.gd` | Pattern for the "place into Godot" step: generator script, never hand-edited `.tscn`. |
| Licence log format | `docs/asset_log.md` | Template for `<project>/.claude/tripo/asset_log.md` or the project's own log. |
| Budget tests | `tests/integration/test_performance_budget.gd`, `test_model_fidelity.gd` (named in `CLAUDE.md:213`) | Idea: per-project budget config the QA step reads. |

---

## 5. Implications and gaps for the skill design

1. **Rigging has no prior art.** Patina never rigged anything and every model is static. The skill's rig step needs its own research (Tripo `animate rig` / retarget docs via `tripo docs`).
2. **Blender is installed now** (`/opt/homebrew/bin/blender`; `/Applications/Blender.app` exists). The Patina ADR of 2026-10-10 said "there is no Blender on this machine", which is why all fixes went into Godot generator scripts (`docs/decisions.md` ADR "M5: first exports ... part budget kept by the generator", Rationale). Headless-Blender QA and free fixes are now possible, and should reproduce Patina's checks: tris vs budget, 8-view turnaround, hard-edge check, normal-map-off look, thickness/scale sanity, non-manifold geometry and holes.
3. **Ask for the budget per project.** Patina's numbers (12k part / 60k object) are project-specific, but the method is general: generate without a limit, reduce with v3.0 to the lowest count that holds by eye, and reduce only for a budget.
4. **Make two approval gates standard:** (a) the reference sheet and hero/views contact sheet before any 3D credit; (b) the credit plan (number of parts × 65, plus re-roll allowance of 2 per object) checked against `tripo balance`.
5. **Swap the placeholder by interface.** Keep node names, sockets and collision names, and keep the gameplay data untouched. Prefer regenerating the scene by script over editing the `.tscn`. Run the project's import check afterwards (`scripts/check_import.sh` in Patina, `CLAUDE.md:30, 94`).
6. **Record each lesson with:** the date, the object it was measured on, the measured numbers, and "not verified" where relevant. Promote to the global skill only rules that held across objects: the face-limit damage, the v3.0 reduction, the side convention, mirrored back views, painted glass, missing hard edges, and the price table.
7. **Watch for stale docs inside projects.** Patina's GDD 07 sections 7.1-7.3, GDD 01, GDD 12 and the GDD index still describe Meshy and Blender. The skill should treat a project's `CLAUDE.md` asset section and recent ADRs as authoritative over older GDD text.
