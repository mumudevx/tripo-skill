# Prior work: grime-does-pay (docs + git history)

Source project: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay` (Godot 4.7.2, code name `washline`, a pressure-washing incremental game). All paths below are relative to that root unless absolute. Everything here was read without changes. The Godot commit history has 50 commits; the asset work ran from 2026-10-26 to 2026-10-30.

Abbreviations: AL = `docs/asset_log.md`, ADR = `docs/decisions.md`, P07 = `docs/gdd/07-ai-asset-pipeline.md`.

---

## 0. TL;DR for the skill

1. **Use a four-view turnaround with multiview-to-3D, not one image.** A single three-quarter image leaves the hidden sides for the generator to guess. That caused colour bleed (pink float colour on the pool's inner wall), copied features (drawers and pulleys repeated on the back), and lost parts. The owner made this a rule on 2026-10-26 (P07 §7.2 step 1; ADR "2026-10-26 Backyard art"; AL rows 34–41 "replaced by the multiview v3.1 row").
2. **Show the reference to the owner before any 3D credits.** Most re-rolls came from a bad reference sheet, not a bad 3D run: tool chest 3 sheets, jerry can 3 sheets, glider/ship wheel 2 rounds, red planet 3 rounds (AL rows 89–91, 194, 199).
3. **QA in headless Blender, report numbers, then fix in Blender for free where you can.** About 25 per-model `tools/blender/fix_<id>.py` scripts replaced paid re-rolls (commit `edf1605`, `7f015bb`, `0e53390`).
4. **Placement is deterministic.** One script (`tools/place_model.py`) joins the meshes, decimates, sets the base origin, scales to the placeholder's height, applies a yaw (Tripo faces +X, so −90 turns it toward +Z), sets the texture to 1K and names the root. It then rewrites the Godot scene as a wrapper with the `.glb` instanced as `Model`.
5. **Rigging via Tripo works only on an A-pose model with empty, separated hands.** The first worker failed Tripo's rig check (lance fused to the torso). An A-pose re-model passed (ADR "2026-10-27 Crew workers are rigged").
6. **Log every generation**: task id, model version, parameters, credits, and the fixes applied (AL is the template, see §5).

---

## 1. The pipeline as practised (chronological evolution)

### v1: backyard, 2026-10-26: one image → Tripo P1 image_to_model
- Gemini (`gemini-3-pro-image`, `tools/gen_image.py`) made one concept per object, drawn against an approved multi-object style sheet `ref_backyard_v1` (13 objects) plus a fixed style formula (AL rows 11–23).
- Tripo `P1-20260311` via `tripo-cli 0.6.1`: `image_to_model face_limit 8000, pbr off` (bosses 20000), 50 credits each (AL rows 11–23).
- Cleanup: `tools/place_model.py` → `tools/blender/clean_model.py`: one mesh, ≤8k tris, 1K texture, base origin, scaled to the placeholder height, yaw −90 (AL notes column).
- Problems found:
  - The pool's inner wall carried the float's pink ("single-view projection"), fixed by `tools/blender/fix_pool_pink.py` (ADR 2026-10-26; commit `6fdcb11`).
  - The deck chair's first P1 run "lost the canvas", so it was reseeded (AL row 14).
  - The bicycle had "dark triangle teeth over the rims and stray sliver triangles" (commit `a4e88a7`).
  - Colours drifted: "the per-object Gemini concepts already lost some of the reference sheet's saturation, Tripo lost ~25% more on the slide and the Pool" (ADR 2026-10-26).
- Cost: 700 Tripo credits for 14 runs (ADR 2026-10-26).

### v2: scene pieces and the backyard remake, 2026-10-26 to 2026-10-28: four-view turnaround → Tripo multiview
- One Gemini image holds the same object four times (front, left, back, right) at the same scale on a plain background. It is cropped into four views and sent to Tripo `multiview_to_model` (P07 §7.2 steps 1–2). The documented CLI form is `tripo make front.png left.png back.png right.png --model tripo-p1 -p face_limit=8000 -p pbr=false`, re-rolled with `tripo redo <task>` (P07 §7.2 step 2).
- Scene pieces (belt, worker, washer, fence, hedges, shrub, tree, shed): 9 runs, 450 credits, "no hidden-side drift" (ADR "Backyard scene art").
- Upgrade to `Tripo v3.1-20260211` with `smart_low_poly, face_limit 8000, pbr off, texture_quality detailed, texture_alignment geometry|original_image` (AL rows 34–41, 190–202).
  - Bicycle pilot: slivers fell from 2.5% to 0.8%, "tyre and rim are clean rings" (commit `a4e88a7`).
  - Deck chair: 2.6% to 0.9%. Bench: 17.6% to 5.6% (AL rows 35, 37).
- Chroma-key sheets: the views go on `#00B140` green plus four close-ups underneath. `tools/key_views.py` keys them to transparent RGBA views at one scale and ground line (AL row 39; commit `3dbef2b`).
- Retexture: `texture_model`, `texture_alignment original_image`, `texture_prompt "..."`, 20 credits (AL rows 37, 38). A `texture_prompt` is not accepted on `multiview_to_model` itself, and a retexture with a prompt "came out worse" on the pedal car (AL row 39).

### v3: zones 3–6, 2026-10-29 to 2026-10-30: Higgsfield nano_banana_pro sheet → Higgsfield `tripo_h3_1_multiview_to_3d`
- Sheet: 4 Higgsfield credits. 3D: 12 credits (`texture_quality detailed, texture_alignment original_image, pbr off, face_limit 8000`). Bosses add `face_limit 20000, geometry_quality detailed` for 18 credits (AL rows 42–91).
- The owner compared it with Tripo v3.1 direct on the same views: "same shape, but 13208 tris and a lumpier surface", 50 Tripo credits. The Higgsfield H3.1 result was used (commit `9b7363f`; AL row 33).
- The batch driver is `art_src/refs/make3d.py`: key_views → right/left dedup → `higgsfield generate create tripo_h3_1_multiview_to_3d` → `model_h31.glb` + `job3d.json`. `art_src/` is gitignored (`.gitignore:15`).
- Placement with fixes: `tools/place_refs.sh`, which is re-runnable and calls `place <zone> <id> <yaw> [fix_<id>.py]`, with `H=<m>` overriding the height.
- **Relevance for the tripo skill:** H3.1 through Higgsfield cost far fewer credits per model (16 vs 50) and gave smoother surfaces. The skill should at least know that H3.1 exists and compare the price and quality of direct `tripo-cli` model versions before defaulting to P1 or v3.1.

---

## 2. GENERAL lessons (true for any game)

### 2.1 Reference image: review before sending (the cheapest place to catch errors)
- **One object per sheet, four orthographic views, then multiview.** "Never a sheet of several objects seen from one angle" (P07 §7.2 step 1, owner 2026-10-26). Never feed a multi-object sheet to 3D. Use it only as a style `--ref` (AL rows 11–23 used `ref_backyard_v1` as a style ref only).
- **Style consistency**: pass one approved image as the reference and append a byte-identical style formula to every prompt (`tools/style/style_formula.txt`; P07 §7.2 step 1). Later zones all used one anchor ref (`art_src/backyard_v2/pedal_car.png`) for every sheet (AL rows 42–91).
- **Sheet prompt template that worked** (`art_src/refs/depot/obj_depot_statue/sheet_green.prompt.txt`):
  - "Reference sheet of exactly ONE object… the reference is a different object, use it for style only…"
  - TOP ROW: front, left, back, right; "flat orthographic elevation… camera straight on at the object's mid height, no perspective"; "left and right side views are exact mirror images; identical scale and identical ground line, evenly spaced with wide gaps".
  - BOTTOM ROW: four close-ups.
  - "ONE flat uniform chroma-key green colour (#00B140)… no shadow, no floor, no ground line, no panel borders, no text".
  - "no green reflections… no green parts anywhere on the object".
- **Things to check in the reference before spending 3D credits** (each one burned credits when it was missed):
  - *Side views are real side views*, not three-quarter views of the front face. The first jerry-can sheet drew them as three-quarter views and the model came out wrong (AL row 199).
  - *Right view is not a copy of the left.* The generator often draws the left view twice. Detect it with an IoU test (same vs mirrored silhouette) and mirror it (`art_src/refs/make3d.py` DEDUP block; AL row 33, "the drawn right view was a copy of the left one, mirrored").
  - *Count unique features*: one handle, one cap. The second jerry can came out with "three handles and a second cap", so the third sheet says "single middle handle and a single spout" (AL row 199; commit `dbd76be`).
  - *Asymmetric features must be stated per side.* Tripo copies front details onto the back: tool-chest drawers, engine-block belt and pulleys (AL rows 194, 198). Say "plain sides and back" (AL row 194) and "the back view shows only the back of the coat… no face" (AL row 46: the statue's first model had "a face on the back").
  - *Thin or held props*: the statue's first model had the "telescope through the head". The prompt was rewritten to keep the telescope "beside his body, never in front of his face" (AL row 46). Later the telescope was removed in Blender anyway (`fix_statue.py`).
  - *Hollow or open volumes get closed.* Both pickup attempts closed the cargo bed with a flat lid, fixed in Blender by cutting it open and inserting a box (AL row 200). Expect this from any open container.
  - *Glass or transparent parts pick up the background.* The glider's canopy came out pale green because the chroma green showed through the glass (AL row 90). Use magenta (`#FF00FF`) for green or glassy objects. The icons already switched per object (AL rows 100, 104, 120, 134, 138).
  - *Layout*: all four views in one row. The glider sheet drew two rows and the views had to be cut by hand (AL row 90). Long or wide objects need "drawn small enough that each view fits in its own quarter".
  - *Colour words*: say what must NOT appear ("nothing green", "no green patina", "no blue, teal or green anywhere"; AL rows 46, 52, 91), because the generator drifts toward the palette's accent colours.
  - *Ground slabs and plates*: say "sits directly on the ground with no base plate or slab". Otherwise you get a slab that has to be cut off (`fix_phone_booth.py` removed "the grey ground slab", AL row 43; pedal-car "ground discs fused into three tyres", AL row 39).
- **Planets and organic forms**: ask for bumps, craters and irregularity. A plain sphere "looks artificial" (`docs/later.md` "Kredi yüklenince" bullet 6, owner 2026-10-29; AL rows 78–82 "NOT a perfect sphere").
- **View splitting is fragile.** `tools/key_views.py` needed fixes for:
  - a dark green or thin grey ground line joining the views;
  - the empty band above the views taken for the row gap;
  - an object floating above its stand splitting into the wrong views.
  
  It gained `--gaps` and `--keep-thin` for these (commit `2762450`). The skill should show the user the split views (or a `preview_white.png`) before submitting.

### 2.2 Generation planning (budget / topology / texture)
- **Budgets per asset class** (P07 §7.1):
  - A (props): ≤8k tris, 1 material slot.
  - B (bosses/hero): ≤30k tris.
  - C (backdrops): low detail; 512 px textures were used (AL rows 27–30).
  - D (equipment/crew): rig-free bob, or rigged.
  - E (icons): 2D only.
- **face_limit is not a triangle cap.** v3.1 `smart_low_poly face_limit 8000` returned 9,660–12,367 triangles (AL rows 34–41, 190–202), so placement used `--max-tris 12000` and kept them "not decimated". Plan with headroom or decimate afterwards. *Inference:* smart_low_poly likely counts quads as faces; verify on one run.
- **Pass `pbr=false`** when the game uses its own shader or a flat-albedo look (every row in AL). The art direction forbids PBR realism (`docs/gdd/06-art-direction.md` §6.2, §6.6: "no baked lighting, no imported textures beyond a flat albedo").
- **texture_alignment**: `geometry` was used first (AL rows 34–38). Later `original_image` was used everywhere (AL rows 39+) because it follows the reference colours.
- **Retexture before re-modelling** when only colour or texture is wrong: Tripo `texture_model` costs 20 credits against 50 for a new model (AL rows 37, 38). Exception: a texture prompt made the pedal car worse (AL row 39). Always compare.
- **Expect ~25% saturation loss through image-to-3D** (ADR 2026-10-26). Push the reference saturation, or plan a Blender colour pass.
- **Credit preflight**: record expected credits per step. Observed Tripo-direct prices:
  - image/multiview → model: 50;
  - retexture: 20;
  - rig: 25;
  - rig-check: free.
  
  Sources: AL rows 11–41, 25; ADR "Crew workers are rigged": "75 Tripo credits (model 50, rig 25)".
- **Re-roll rate**: in the garage, 4 of 12 objects needed 1–2 extra paid runs (go-kart, tool chest ×2, jerry can ×2, pickup), about 300 extra credits (AL rows 193–200). Budget roughly 25–35% re-roll overhead for complex mechanical objects.

### 2.3 QA in headless Blender (what to measure)
- **Model check page** `tools/qa_models.py` + `tools/blender/qa_render.py` (commit `578715f`):
  - the in-game screenshot (`scripts/dev/capture_object.gd`, one object on its stage);
  - four views and an iso view with mesh edges;
  - **triangle count, sliver share, lowest point per side**;
  - the reference views;
  - the previous model at a git revision beside the new one (`--old-rev`).
  
  It is a self-contained HTML page per batch for the owner's approval.
- **Sliver share is the useful mesh metric.** Good results were under ~1%; a bad P1 mesh was 2.5–17.6% (AL rows 34–37). A "long-sliver" metric was removed because "it did not separate good meshes from bad ones" (commit `3dbef2b`).
- **"Lowest point per side"** catches tilted bases and floating objects. The Tripo belt's top "sloped ~8° toward the camera and its origin was the highest point", so objects floated 4–10 cm (commit `d478a9f`). The fix was `clean_model.py --origin surface` (downward rays, level the top, origin on it, ±7 mm), locked in by `tests/unit/test_belt_surface.gd`.
- **Review from the game camera**:
  - `tools/model_viewer.py` and `tools/model_compare.py` start from the zone camera (front toward +Z, FOV 22). `--yaw` turns raw Tripo models.
  - The split-screen compare shows the original and the fixed model with one shared camera (commit `554e5ba`).
  - The viewer must never cache, so replaced models show at once (commit `1f426a7`).
- **Common Tripo defects seen** (the checklist for automatic QA):
  - wrinkled or wavy flat faces (box sides, lids, panels): mailbox, vending machine, wheelie bin, birdhouse gables (AL rows 42, 48, 49, 41);
  - lumpy curved parts: fire-hydrant dome, mailbox arched rims (AL rows 50, 42);
  - smeared normals giving dark spikes: hydrant barrel, "dark spikes under the flange were smeared normals" (AL row 50);
  - star-shaded flat discs: pedal-car number circles "shaded as a star of thin lines", fixed with flat normals (commit `3b139a3`);
  - z-fighting rings from inner faces left in a plane after a fix (commit `66ce403`);
  - colour bleed between adjacent parts: pot soil got the terracotta colour, pool wall got the float's pink, a teal line on the hatchback arches, a seat smear (AL rows 36, 23, 195, 39);
  - fused or duplicated parts: ground discs fused into tyres, duplicate handles, stray chain link, extra hand (AL rows 39, 199, 55, 46);
  - asymmetric halves where only one side got a feature: tool-chest side handle, scooter far side "mirror disc 24 cm behind its stem… a fold in the body" (AL rows 194, 190);
  - cracks or open seams: jerry-can shoulder "crack… welded shut" (AL row 199);
  - holes and overlapping layers: two failed tool-chest attempts (commit `b6274e3`);
  - glass strips broken: bus stop (AL row 44);
  - missing thin parts: go-kart steering-wheel ring, deck-chair canvas (AL rows 193, 14).
- **Tripo splits the mesh at every UV seam.** Weld on load before any topology repair (`tools/blender/mesh_fix.py` docstring).

### 2.4 Fix options: free Blender vs paid re-roll
- **Free Blender fix kit** (commit `edf1605`, `tools/blender/mesh_fix.py`, `fix_common.py`, `keep_normals.py`, `mesh_paint.py`):
  - `flatten_face(axis, weight)`: press each depth layer of a flat side flat, flat shading.
  - `taubin(weight)`: shrink-free smoothing of lumps; keep it off feature edges.
  - `delete(mask)` + `fill_holes`: cut parts off.
  - `paint(mask, colour)`: repaint texels.
  - `keep_normals`: keep Tripo's normals on triangles a fix did not touch.
  - Mirror-half replacement: the good side mirrored over the bad one (scooter, tool chest; AL rows 190, 194).
  - Copy one clean part to the others: the one clean wheel copied to all axles (AL row 39).
  - Rebuild exact primitives: pole and collar as exact cylinders (AL row 51); "every slat rebuilt straight with even gaps" (AL row 45).
  - Procedural paint: "procedural wood grain painted over the texture" (AL row 41).
- **One fix script per model, named `fix_<id>.py`**, carrying the owner's review notes, re-runnable from the raw `.glb` (`tools/place_refs.sh`). This makes fixes reproducible when the raw model or placement changes.
- **When to re-roll instead** (from AL history):
  - the shape is fundamentally wrong (handles count, missing ring, telescope through head);
  - the reference itself was wrong. Fix the sheet first, then re-roll (AL rows 46, 193, 194, 199, 200).
- **"Placed unfixed" is a valid owner choice.** For zones 4–6: "flaws get fixed as they show in play" (owner 2026-10-30; AL rows 56–88; commit `18aae8c`). The skill should offer "place as-is, fix later" as an explicit option.

### 2.5 Rigging via Tripo
- Rig input: a new turnaround in **A-pose**: "arms held clearly away from the body at about 40 degrees, elbows slightly bent, hands open and empty, legs slightly apart… holding NOTHING" (AL row 25).
- Flow (AL row 25):
  - multiview_to_model, 50 credits;
  - `animate_rig` biped `v2.5-20260210`, 25 credits, task recorded;
  - "rig-checks free". **Run the free rig check before paying for the rig.**
- A held prop fused to the hands makes a model "not riggable". Keep props as separate models attached in-engine (ADR "Crew workers are rigged": "The old model failed Tripo's rig check (arms and lance fused to the torso); the A-pose model passed").
- Rigged post-clean: `tools/blender/clean_rigged.py`:
  - drops Tripo's stray helper `Icosphere` mesh;
  - shrinks textures to 1024 px JPEG;
  - keeps the armature and skin;
  - **makes no transform changes**: the game scales and turns the figure.
- Engine side: the bones were posed in code (`Skeleton3D.set_bone_global_pose`), not animated, to aim arms (ADR 2026-10-27). Feature points (lance tip, grip, hose end) were measured on the model and re-measured after every model swap (commits `8216a10`, `9b7363f`).

### 2.6 Placing into the engine (replacing a placeholder)
- Placeholder contract: each object is a data resource pointing to a scene. Final art is "a drop-in swap of each definition's `scene`" (ADR "M6 pools… zones 2–4", rationale (1)).
- `tools/place_model.py <object_id> <raw.glb> [--yaw -90] [--max-tris] [--height]`:
  - reads the existing data resource for the scene path and **baked bounds height** of the placeholder;
  - runs the Blender clean;
  - writes `assets/models/objects/<zone>/<id>.glb`;
  - **rewrites the scene as a wrapper: same root node (name, unique_id), `.glb` instanced as `Model`** (the docstring of `tools/place_model.py`).
  
  Keeping the root node identity means nothing else in the game breaks.
- **Scale to the placeholder's size, but check the frame.** Long or tall models (dinghy 0.40 m, fishing boat 0.88 m, biplane 0.62 m, glider by its 1.3 m wingspan, bosses 0.93–0.94 m) needed `--height` overrides "to stay inside the frame" (AL rows 57, 59, 66, 86, 87, 90). Size by the dominant dimension, not only the height (`clean_model.py --fit z|x|y`).
- **Orientation**: Tripo models face +X. The default yaw is −90 (to +Z).
  - Many came out reversed and needed 180, or +90 when "the reference's front came out on the other side" (hydrant, traffic light, jet ski, satellite dish; AL rows 50, 52, 56, 74; `tools/place_refs.sh` header).
  - The windsock was placed side-on with yaw 0 (AL row 75).
  - **Always render from the game camera and ask which way is the front.**
- After placement: run the engine import check and tests (`./scripts/check_import.sh`, `./scripts/run_tests.sh`) and project-specific re-bakes (CLAUDE.md "Commands"; P07 §7.2 step 4).
- **Silhouette and gameplay side effects**: new models changed the silhouettes (+4% active cells) and gameplay time. The full game went from 5.23 h to 6.29 h after the zone 3–6 swaps (commit `b001015`, `docs/balance/sim_zone_art_2026-10-30.md`; ADR 2026-10-26). The skill should flag "re-run project validations" after a swap.
- **Ask for approval before swapping**: placement happened only after the owner reviewed the QA page (commit `edf1605` "places the approved models"; `docs/later.md` "Kredi yüklenince": "each first shows the reference image to the owner, 3D only after approval").

### 2.7 Logging and recording lessons
- Every generated asset gets one row at creation time (AL header). Columns:
  - id;
  - class;
  - tool + model version + CLI version;
  - date;
  - prompt or source (+ ref image, + style formula path);
  - 3D params + **task id** + credits;
  - license terms at generation time;
  - notes: Blender edits, tris, yaw, height, replaced-by, owner-quoted reason.
- Superseded rows stay with "replaced YYYY-MM-DD by …" (AL rows 12–22). Failed attempts keep their task ids and credits in the row (AL rows 193–194, 199–200).
- Decisions with a cost summary go in the ADR ("Cost: 700 Tripo credits (14 runs), 14 Gemini images"; ADR 2026-10-26).
- Raw generator output stays out of git: `art_src/` is gitignored; "Raw generator output (`.blend`, raw Meshy files) stays out of the repo" (CLAUDE.md "Git"; `docs/gdd/13-claude-code-conventions.md` line 64). Rejected versions are kept on disk as `v1/`, `old/`, `sheet_green_r*.png` (AL rows 46, 89–91, 193–200).
- Licensing and store disclosure: keep the log true for the AI-content disclosure (P07 §7.4; `docs/gdd/12-publishing.md`; AL "Store page disclosure").

### 2.8 Process / human-in-the-loop
- **Owner approval gates**: (1) reference sheet, (2) QA page after 3D, (3) placement. Credits are never spent without approval (`docs/later.md` "Yalnızca sahibe ait M3 maddeleri"; CLAUDE.md M6 checklist "(owner) … style reference first, approval before any 3D credits"; user global CLAUDE.md "Reference object first").
- **Owner feedback is quoted with a date in each fix** ("owner 2026-10-29: …") in the asset log and fix scripts (AL rows 39–53; commit `edf1605` "fix_<id>.py per model carries the owner's review notes").
- **Owner-facing docs are in Turkish**; code, commits and ADRs are in English (CLAUDE.md "Source of truth"). The skill's user-facing lesson files may need the user's language, while scripts stay English.
- **Content rethinks happen during art.** The storage box was removed ("a box is not something you wash") and replaced by a pedal car (AL row 22; commit `414b111`). The skill should allow "replace the object concept" as an outcome of reference review.

---

## 3. PROJECT-SPECIFIC lessons (grime-does-pay only)

- **Gameplay depends on the silhouette.** Dirt is a screen-space grid with a baked silhouette mask, so models need no UVs for dirt (ADR "Dirt is a screen-space grid"). After every swap, run `godot --headless --path . -s res://scripts/dev/bake_silhouette.gd -- <id>`; `tests/unit/test_silhouette_baker.gd` fails on a stale mask (ADR "CPU silhouette bake"). The bake rasterises on the CPU because headless runs have no GPU output (same ADR). A cell is active at ≥25% coverage, so thin parts like bicycle spokes may lose dirt (`docs/questions.md` line 51).
- **Balance re-check after art**: run the balance simulator (`--full-game`) after model swaps (commit `b001015`; ADR 2026-10-26).
- **Fixed camera per zone**: pitch ~25°, yaw ~15°, the object fills ~45% of the frame width and a boss ~75% (`docs/gdd/06-art-direction.md` §6.1). The backyard camera is at 4 m with a 22° FOV (ADR "CPU silhouette bake"). Size and yaw are judged from this camera only.
- **Look**: Filmic tonemap kept over AgX and Linear. AgX washed the colours and weakened the dirt/clean contrast (ADR 2026-10-26). The clean surface is saturated and slightly glossy; the dirt is matte. `DirtTarget` draws the model's albedo under the dirt (`clean_tex`).
- **Style formula** (`tools/style/style_formula.txt`): "Chunky stylized low-poly… soft bevelled edges… toy-like… flat matte colours… sunny yellow, coral red, teal, grass green… no text or logos; single warm key light from upper left…". The anchor style ref is `art_src/backyard_v2/pedal_car.png`.
- **Budgets**:
  - objects ≤8k tris (in practice 7.4k–12.4k kept);
  - bosses ≤30k (21.7k kept);
  - texture 1K;
  - backdrops 512 px;
  - one mesh + one material, root named `obj_<zone>_<id>` / `boss_<zone>` (P07 §7.1, §7.2, §7.3; AL).
- **Naming and paths**:
  - models `assets/models/objects/<zone>/<id>.glb`, bosses `assets/models/bosses/`, crew `assets/models/crew/`, equipment `assets/models/equipment/`, stage `assets/models/stage/`;
  - names `obj_<zone>_<id>`, `boss_<zone>`, `bg_<zone>`, `eq_<tier>`, `find_<zone>_<id>`, variants `<id>_v<n>`;
  - data in `data/objects/<zone>/<id>.tres`;
  - all from P07 §7.3 and CLAUDE.md "Folder structure".
- **Git LFS** for `*.glb *.png *.jpg *.wav *.ogg *.blend` (CLAUDE.md "Tech stack").
- **Scene pieces**:
  - The belt is one generated segment stretched ×2.75 with its top levelled (AL row 24).
  - The backdrop is tiled from generated pieces (fence every 1.24 m). The backdrop sets a `ground_y` meta that the Stage reads (ADR "Backyard scene art").
  - The washer model was removed from the stage after play-test (ADR "No washer machine on the stage").
- **Spray gun and crew**:
  - The gun is held bottom-left and turned to the aim. The tip, grip and hose end are measured on the model in `PlayerGun` / `CrewFigure` and re-measured after a model swap (commits `e2f9335`, `9b7363f`, `55e44b9`).
  - The jet starts one nozzle radius off the tip because the 2D jet is drawn over the 3D nozzle (commit `55e44b9`).
- **Open model items** (`docs/later.md` "Kredi yüklenince"):
  - spray gun redo with a new 4-view reference (done 2026-10-29, AL row 33);
  - 5 equipment tiers (hose → pressure cart → trailer → truck → tanker);
  - garage backdrop;
  - lunar rover;
  - Sun boss;
  - orbit planets "from Tripo, not Godot spheres".
  
  Commit `564b85a`: "The lunar rover and the Sun wait for credits."
- **2D icons pipeline** (not Tripo, but the same keying lessons):
  - `tools/key_icon.py` with `--near 1` drops ghost items leaked from a zone-sheet reference and keeps enclosed own-colour areas (commit `9b596ae`).
  - Using a multi-item sheet as the reference leaked "blurred ghosts of other items" into single-icon generations, and 10 icons had to be cleaned by hand (AL rows 125–158; commit `e3e8305`).
  - **General corollary:** a multi-object style ref can leak content into single-object generations. Prefer a single-object style anchor.

---

## 4. Concrete artefacts worth porting or mirroring into the skill

| Need in skill | Existing implementation (read-only reference) |
|---|---|
| Split a 4-view sheet into views | `tools/key_views.py` (chroma key `#00B140`, ground-line removal, `--gaps`, `--keep-thin`) |
| Detect a duplicated left/right view | IoU dedup block in `art_src/refs/make3d.py` |
| Batch generate + idempotent skip | `art_src/refs/make3d.py` (skips if `model_h31.glb` exists, logs `job3d.json`) |
| Clean/normalize a raw GLB | `tools/blender/clean_model.py` (`--height --max-tris --tex --yaw --fit --origin base|top|surface --min-island`) |
| Rigged GLB cleanup | `tools/blender/clean_rigged.py` |
| Replace placeholder, keep scene root | `tools/place_model.py` (wrapper scene, `Model` child) |
| Re-runnable place + fix list | `tools/place_refs.sh` |
| QA page (renders + metrics + before/after) | `tools/qa_models.py`, `tools/blender/qa_render.py`, `scripts/dev/capture_object.gd` |
| Interactive review from game camera | `tools/model_viewer.py`, `tools/model_compare.py` |
| Mesh repair primitives | `tools/blender/mesh_fix.py`, `fix_common.py`, `keep_normals.py`, `mesh_paint.py` |
| Per-model fix examples | `tools/blender/fix_*.py` (~25 scripts) |
| Style formula | `tools/style/style_formula.txt` |
| Sheet prompt template | `art_src/refs/depot/obj_depot_statue/sheet_green.prompt.txt` (and `art_src/refs/specs.py` for per-object specs) |
| Asset log format | `docs/asset_log.md` header and rows |

---

## 5. Suggested lesson-file schema (derived from AL + ADR practice)

Per generation (project-level, e.g. `<project>/.claude/tripo/log.md` or per-asset JSON):
- id
- class/budget
- reference image path(s) + style ref + style-formula hash
- approval date
- tool/model version
- CLI version
- task id(s)
- params (face_limit, smart_low_poly, texture_quality, texture_alignment, pbr, geometry_quality)
- credits
- QA numbers (tris, sliver %, lowest point per side, bounds)
- defects found
- fix applied (script path) or re-roll reason
- yaw/height used
- owner quote + date
- superseded-by

Sources: AL columns; ADR "Cost:" lines; `tools/place_refs.sh` comments.

---

## 6. Inconsistencies and stale spots noticed (don't copy these)

- The GDD index still says "Meshy → Blender → Godot" (`docs/gdd/index.md` line 26), and `docs/gdd/13-claude-code-conventions.md` line 64 mentions "raw Meshy files". The real tool is Tripo/Higgsfield. The skill should keep tool names in one place.
- P07 §7.2 step 2 still documents `--model tripo-p1`, but later work used v3.1 smart_low_poly and then H3.1 via Higgsfield (AL rows 34+, 42+). P07 was not updated for the switch, and no ADR records the Tripo-direct → Higgsfield-H3.1 switch (only commit `9b7363f` and AL row 33 explain it).
- P07 §7.1 budget "≤8k tris" vs actual 9.6k–12.4k kept undecimated (AL rows 34–41, 190–202). The budget drifted silently. The skill should report budget deviations explicitly.
- `docs/morning_brief.md` "Yalnızca senin yapabileceğin işler" says final art comes via "3D (Higgsfield)", while `docs/later.md` "Kredi yüklenince" says "Gemini → Tripo". The documents disagree about the 3D provider.
- The asset log has a sound/music section, then a "Store page disclosure" block, and then garage model rows appended *after* the disclosure (AL rows 187–202). Rows were appended at the end of the file instead of in their table. The skill's logger should insert into the right section.
