# Prior art: grime-does-pay asset tools (read-only audit)

`G` = `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay`. Every claim cites a file. Line numbers are from the files as read on 2026-10-30.
Environment checked: `blender` = `/opt/homebrew/bin/blender`, Blender 5.2.3 LTS. Godot is pinned to 4.7.2 (`G/scripts/godot_bin.sh`).

## 0. How the tools chain together (the pipeline the user ran by hand)

1. Reference image: `G/tools/gen_image.py` (Gemini) or Higgsfield nano_banana_pro, using a chroma-green (#00B140) four-view sheet. The style formula `G/tools/style/style_formula.txt` is added byte-identical to every prompt (`G/docs/gdd/07-ai-asset-pipeline.md` §7.2 step 1).
2. Split the sheet into views: `G/tools/key_views.py` writes front/left/back/right RGBA files at one shared scale and one ground line. These go to Tripo multiview (`G/docs/asset_log.md` rows 34-41, 190-202: `multiview_to_model smart_low_poly, face_limit 8000, pbr off, texture_quality detailed, texture_alignment original_image|geometry`, 50 credits each).
3. Clean and place: `G/tools/place_model.py` → `G/tools/blender/clean_model.py`. For batches: `G/tools/place_refs.sh` and `G/tools/blender/backyard_scene.sh`. Rigged output goes through `G/tools/blender/clean_rigged.py`.
4. Per-model fixes after owner review: `G/tools/blender/fix_<id>.py` (23 scripts), built on `mesh_paint.py` → `mesh_fix.py` → `fix_common.py` / `keep_normals.py`.
5. Godot post-steps: `G/scripts/dev/bake_silhouette.gd`, `G/scripts/check_import.sh` and the tests. `place_model.py` only prints these steps; it does not run them (`G/tools/place_model.py:10`).
6. Review: `G/tools/qa_models.py` builds a self-contained HTML approval page (renders from `G/tools/blender/qa_render.py`, in-game shots from `G/scripts/dev/capture_object_driver.gd`). The interactive pages are `G/tools/model_viewer.py` (one model) and `G/tools/model_compare.py` (before/after split screen).

---

## 1. Per-script audit

### 1.1 `G/tools/qa_models.py`: approval page
- **Purpose:** builds one self-contained HTML page per batch of object ids, with images embedded as base64 JPEG (`:78-86`). Per object it shows the in-game screenshot (old/new), the iso wireframe (old/new), a 4-view strip, the stats and the reference sheet (`:101-136`).
- **Inputs:** `ids...`, `--out page.html`, `--work dir`, `--old-rev <git rev>`, `--refs dir` (expects `<refs>/<id>_views_sheet.png`, `:59`), `--title` (`:31-39`).
- **Outputs:** `<work>/new/<id>_{front,left,back,right,iso,iso_wire}.png` plus `<id>.json` (from qa_render), `<work>/new/<id>_game.png`, and the HTML.
- **Metric/threshold:** `SLIVER_FLAG_PCT = 3.0`. The comment calibrates it: old Tripo P1 models 0-17.6%, most 1.5-4.8%; v3.1 smart low poly 0.8% (`:26-28`). The flag is the only automatic verdict (`:89-93`). The page tells the owner that the number alone does not decide and that the wireframe and in-game images are the real check (`:182`). Commit 3dbef2b removed a "long-sliver" metric because "it did not separate good meshes from bad ones" (`git show 3dbef2b`).
- **Godot assumptions:**
  - The glb path comes from `data/objects/*/<id>.tres` → the `PackedScene` ext_resource → the first `res://...glb` in that scene (`_glb_path`, `:66-69`).
  - In-game capture runs `scripts/run_quiet.sh --resolution 1280x800 -s res://scripts/dev/capture_object.gd -- --out=<dir> ids` (`:44-46`). That windowed run puts one object on its zone's Stage and waits 30 frames before the grab (`G/scripts/dev/capture_object_driver.gd:4,28-33`).
- **Old model:** read with `git show <rev>:<glb>`, then `git lfs smudge` (`:52-58`), because `*.glb` is in LFS (`G/.gitattributes`).
- **Generic, worth porting:** the self-contained approval page (summary table plus a section per model, old vs new pairs); embedding images so the page can be shared or published; pulling the "old" version from git for before/after.
- **Game-specific:** the `.tres`/scene lookup, `capture_object.gd`, Turkish UI strings, `_views_sheet.png` naming.
- **Bugs and fragile parts:**
  - Blender and Godot run with `stdout/stderr=DEVNULL` and `check=True` (`:44-46,73-74`). Blender exits 0 when the script raises (verified: `blender -b --python-expr "raise ..."` exits 0; with `--python-exit-code 3` it exits 3). A failed render therefore shows up as a confusing `FileNotFoundError` on `<prefix>.json` (`:75`), with no log.
  - `run_quiet.sh` on macOS uses `open -W -g -n` (`G/scripts/run_quiet.sh:12`), so the exit code does not reflect Godot failures. Missing screenshots are skipped silently (`:118-121`).
  - The "old in-game" shot must be captured by hand before replacement (docstring `:7-8`); nothing enforces this.
  - `_glb_path` raises `StopIteration` or `AttributeError` on an unknown id or a scene without a glb (`:67-69`).
  - The fixed crop box `(0.2,0.15,0.8,0.9)` on game shots assumes the object sits in the centre slot (`:112`).
  - Fonts load from Google Fonts (a network dependency).

### 1.2 `G/tools/place_model.py`: put a model into the game for an existing object id
- **Purpose:** replaces a placeholder by object id (`:2-10`).
- **Inputs:** `object_id raw.glb [--yaw -90] [--max-tris] [--height m]` (`:24-28`).
- **Logic:**
  - It finds exactly one `data/objects/*/<id>.tres`. The zone is the parent folder name; boss = the literal `is_boss = true` in the tres (`:31-38`).
  - Height defaults to the stored `bounds = AABB(...)` component 4, i.e. the size along Godot Y of the currently placed model or placeholder (`:39-42`). This is how a replacement inherits the placeholder's size. Width and depth follow the model's own aspect ratio.
  - Triangle budget: 8000, or 30000 for a boss (`:43`), matching `G/docs/gdd/07-ai-asset-pipeline.md` §7.1.
  - Output paths: `assets/models/objects/<zone>/<id>.glb`, or `assets/models/bosses/<id>.glb` for bosses. Root and material name: `obj_<zone>_<id>`, or `<id>` for bosses (`:45-50`).
  - It calls clean_model (`:52-56`). Then it **rewrites the whole object .tscn** as a wrapper: the same root node name and `unique_id`, one child `Model` instancing the glb, with `unique_id = root+1` (`:57-65`).
- **Godot conventions:**
  - Scene format 3 and the `unique_id=` node attribute (Godot 4.7). The ext_resource is written without `uid=`, so Godot resolves it by path.
  - Glb import keeps the defaults plus `gltf/embedded_image_handling=1`, which extracts textures as `<glb>_<image name>.jpg`, e.g. `bbq_grill_obj_backyard_bbq_grill.jpg` (`G/assets/models/objects/backyard/bbq_grill.glb.import`). The extracted texture import uses `compress/mode=0` (lossless) and mipmaps on (`...bbq_grill_obj_backyard_bbq_grill.jpg.import`).
  - Afterwards the user runs `bake_silhouette.gd` (recomputes `silhouette` + `bounds`, `G/scripts/dev/bake_silhouette.gd:58-63`) and `check_import.sh`.
- **Default yaw -90** because "Tripo models face +X; -90 turns them to +Z" (`:26`). In practice the per-object yaw varied: 90 (fire hydrant, traffic light, jet ski, satellite dish), 180 (pedal car), 0 (windsock) (`G/tools/place_refs.sh:22-73`).
- **Generic, worth porting:**
  - Keep the scene file, root node name and node ids so every reference to the scene stays valid, and swap only the visual.
  - Size the new model from the placeholder's measured extent.
  - Use a per-category triangle budget.
  - Put the facing correction (yaw) in one place.
- **Game-specific:** the ObjectDefinition `.tres` layout, the zone/boss folder rules, the `obj_<zone>_<id>` naming, and the follow-up silhouette bake.
- **Bugs and fragile parts:**
  - **Destructive rewrite:** every other node, script, collision shape, group or exported property on the object scene is dropped (`:60-65`). That was fine here only because object scenes held nothing but primitives (original placeholder: `git show bb8f311:scenes/objects/backyard/obj_backyard_bbq_grill.tscn`). A generic skill must replace only the placeholder MeshInstance3D subtree.
  - **Blender exit code not checked:** clean_model failures exit 0, so the scene is rewritten to point at a missing or stale glb. Output is filtered to lines with `clean_model:` or `Error` (`:56`), which hides tracebacks that do not contain "Error". Fix: pass `--python-exit-code 1` and check that the output file exists and has a fresh mtime.
  - The regex `type="Node3D" unique_id=(\d+)` returns None (AttributeError) if the root has another type, a script attribute, or attributes in another order (`:59`).
  - Height is always fitted along Z (vertical). There is no `--fit` passthrough, although clean_model supports it. Long or flat models needed a hand-picked `H=` override "to stay inside the frame" (`G/tools/place_refs.sh:42-55`).
  - Bounds are re-baked after placement, so a re-run scales to the new model's height. This is stable only if nothing else changes.
  - It does not trigger a Godot import, so no `.import` file exists until the editor or `--import` runs.

### 1.3 `G/tools/model_compare.py`: before/after split-screen viewer
- **Purpose:** a local three.js page. It draws two scenes into the left and right halves of one canvas with one shared OrbitControls camera (`:67-125`).
- **Inputs:** a spec JSON `[{label:"Group/Name", before, after, notes[]}]`, plus `--port 8766`, `--out` (`:5-7,138-159`).
- **Output:** copies the models to `<out>/m/NNN_{before,after}.glb` and serves them with the `Cache-Control: no-store` handler (`:130-135`). You can therefore overwrite `<out>/m/*.glb` and click again without restarting.
- **Scripted screenshots:** `?m=<label>&cam=x,y,z&t=x,y,z`, and `document.body.dataset.ready` is set after two rAFs (`:11-12,92-93,109`). A headless browser can use this for regression shots.
- **Camera:** opens from the game camera direction `(0.938, 2.090, 3.502)` normalised, FOV 22°, distance `r / sin(fov/2) * 1.05` (`:86-89`). The comment ties it to `data/zones/*.tres camera_transform` and an owner rule from 2026-10-29: "a review looks first at what the player sees".
- **Shows:** triangle count before → after (`:96,107`), a wireframe toggle, auto-spin, "reset to game angle", arrow-key navigation, and `localStorage` remembering the last item.
- **Generic, worth porting:** almost all of it. Parametrise the camera direction and FOV, read from the project's camera, and add a yaw per entry.
- **Fragile:**
  - three@0.160.0 loads from unpkg (needs internet).
  - Framing uses only the "before" model's bounding box (`:90`).
  - It has no `--yaw`, so both models must already be in the game orientation.
  - `serve_forever` blocks; the skill must run it in the background and stop it afterwards.

### 1.4 `G/tools/model_viewer.py`: single-model review list
- **Purpose:** the same stack as model_compare: an object list with groups (`label` containing "/"), orbit, wireframe, spin, game angle. The info line shows the triangle count and the `x × z × y` size in metres (`:84-88`).
- **Inputs:** `[--yaw deg] model.glb | label=model.glb ...`. `--yaw -90` previews raw Tripo output in game orientation (`:9-10,121`).
- **Generic, worth porting:** yes, merge it with compare into one viewer script that has modes.
- **Fragile:**
  - `spec.rpartition("=")` breaks on paths that contain "=" (`:127`).
  - One `--yaw` applies to every model (`:130`).
  - CDN dependency.

### 1.5 `G/tools/key_views.py`: chroma-green sheet → 4 multiview inputs
- **Purpose:** keys a #00B140 sheet to alpha and splits the top row into front/left/back/right RGBA at **one common scale and ground line** (`:1-8`).
- **Algorithm and thresholds:**
  - Spill = `g - max(r,b)`. Alpha ramps from spill 25 to 70 (`:21-23`).
  - Dark green with `g > 1.6*max(r,b)` and `g > 40` counts as backdrop (drawn ground lines, shadows) (`:24-25`).
  - Rows over 90% filled count as ground lines (`:27-29`). Thin-run rows (<25 px tall, >30% of the row, with no thick object 12-72 rows below) are cleared (`:30-39`).
  - Despill: `g = min(g, max(r,b))` (`:40-42`).
  - Row cut: the widest empty band between 20% and 80% of the height (`:44-58`).
  - The 4 largest components over 400 px, sorted by x, are named front, left, back, right in that order (`:76-91`). Smaller pieces attach to the nearest view.
  - `--gaps` splits at the 3 widest empty column bands instead, for objects whose parts float apart (`:59-75`).
  - Output: square side = largest view extent × 1.15, ground at 92% of the side, resized to 1024² with LANCZOS (`:88-99`), plus `preview_white.png`.
- **Generic, worth porting:** the shared-scale and shared-ground-line normalisation of multiview inputs, chroma key with despill, and the white-background preview for human review.
- **Specific:** the sheet layout (one top row of 4 views, close-ups below, `G/docs/asset_log.md:33,49`).
- **Fragile:**
  - It exits hard unless exactly 4 views are found (`:80-81`).
  - View names are positional, assuming the sheet order is F, L, B, R. The skill must confirm which side "left" means for the Tripo multiview API (the object's left or the viewer's left).
  - Each view is centred on its own bounding box (`:97`), so asymmetric side views shift the pivot between views.
  - Hand-rolled argv flags.
  - The glider still needed views "cut by hand (two-row sheet)" (`G/tools/place_refs.sh:51`).

### 1.6 `G/tools/key_icon.py`: chroma key for 2D UI icons
- **Purpose:** keys green, or magenta for green objects (detected from the corner colours, `:39-41`). It keeps the largest component plus pieces within `--near` px (`:44-48`), and refills enclosed holes whose colour is far from the background (`FILL_DIST=40`, `:20-22,55-64`). It crops with `MARGIN=0.06` and uses a **premultiplied-alpha downscale** to avoid green or dark fringes (`:65-77`).
- **Relevance to the tripo skill:** low (2D assets). The useful parts for reference images are magenta auto-switching for green objects and the hole-refill rule.

### 1.7 `G/tools/gen_image.py`: Gemini image generation
- **Purpose:** calls Gemini `generateContent` with `responseModalities [TEXT, IMAGE]`, `imageConfig {aspectRatio, imageSize}`, and the default model `gemini-3-pro-image` (`:22,46-53`).
- **Prompt:** `"<asset> Style: <formula>"`, with the formula byte-identical (`:39-40`). `--ref` images go inline as base64 (`:42-45`).
- **Outputs:** `<out>.png` and **`<out>.prompt.txt`** (model, aspect, size, refs, exact prompt) for `docs/asset_log.md` (`:76-78`).
- **Generic, worth porting:** a provenance sidecar next to every generated image or model, and the byte-identical style formula (this matches the user's global rule).
- **Fragile:**
  - `urllib.error.URLError` and timeouts are not caught (`:55-60`).
  - Only the first image is saved.
  - The key comes from env only.

### 1.8 `G/tools/blender/clean_model.py`: headless cleanup
- **Args:** `--in --out --name --height [--max-tris 8000] [--tex 1024] [--yaw] [--min-island 0] [--fit z|x|y] [--origin base|top|surface]` (`:3-5,24-35`).
- **Steps:**
  1. Factory reset, then import the glTF (`:37-38`).
  2. Bake parent transforms into the mesh data, delete all non-mesh objects, join into one mesh (`:39-53`).
  3. Optionally drop islands below a fraction of the total area. This is off by default because "small islands are often real details such as eyes or buckles" (`:7-8,56,137-164`).
  4. Decimate (collapse) with `ratio = max_tris/tris*0.98` (`:57-60`).
  5. Yaw about Z (`:64`). `--origin surface` ray-casts a 15×9 grid down over the middle 80% of the footprint, fits a plane, rotates it level twice and uses the median height as the origin (`:106-134`). This was added after the "objects float on the left" play-test: the belt's top sloped about 8° (`git show d478a9f`).
  6. Uniform scale so the extent along `--fit` equals `--height`. Origin at the centre of the bounding-box base, or the top or surface (`:66-73`).
  7. Keep one material. Material, image and object are all named `--name`, because "Godot extracts it as `<file>_<image name>.<ext>`". Textures are shrunk to `--tex` (`:75-88`).
  8. Export GLB with `export_image_format="AUTO"` (`:91-92`) and print a one-line report (`:93-94`).
- **Generic, worth porting:** nearly all of it: join, bake transforms, yaw, fit-to-dimension, base-centre origin, a single material with a predictable name, texture cap, surface levelling, a one-line machine-readable report.
- **Bugs and fragile parts:**
  - **Island removal runs on an unwelded mesh.** Blender's glTF import does not merge vertices, and Tripo meshes are split at every UV seam (stated in `G/tools/blender/mesh_fix.py:1-3`, which welds at 1e-4 m). `_drop_small_islands` walks edge connectivity (`:144-158`), so its "islands" are UV shells and it could delete pieces of real surface. Weld (by distance) before counting islands.
  - `material_slot_remove` with more than one slot collapses faces onto the remaining slot without remapping UV/texture, so the colours would be wrong (`:76-78`). It is harmless only because Tripo with `pbr=false` gives one material.
  - Collapse decimation on a seam-split mesh can tear UVs and shading. Ask Tripo for the budget (`face_limit`) instead of decimating locally. The asset log shows that every model used `face_limit` = budget.
  - `image.scale(tex, tex)` forces a square texture (`:85-86`). Only the first material's TEX_IMAGE nodes are touched.
  - If several objects share one mesh datablock, `o.data.transform(o.matrix_world)` is applied more than once.
  - Armatures are deleted (`:45-46`), so this must never run on rigged output. That is why clean_rigged exists.
  - Run from `place_model.py` without `--python-exit-code`, failures pass silently (see 1.2).
  - No normals handling. The original normals survive only because nothing edits the vertices except the uniform transforms.

### 1.9 `G/tools/blender/clean_rigged.py`: rigged-GLB pass-through
- **What it does:**
  - Deletes mesh objects whose names start with `Icosphere`: "Tripo's stray helper sphere" in rigged output (`:1-2,13-15`).
  - Scales textures wider than 1024 to 1024² and packs them (`:16-19`).
  - Renames the first mesh to `Body`.
  - Exports GLB with `export_animations=False, export_yup=True, export_image_format='JPEG'` (`:23-24`).
  - Leaves the transforms alone; the game scales and rotates the figure. Used in `G/tools/blender/backyard_scene.sh:16-18`.
- **Context lesson:** the first crew model failed Tripo's rig check because the arms and lance were fused to the torso. An **A-pose** four-view model passed. Cost: 50 credits for the model plus 25 for the rig (`G/docs/decisions.md:290-291`).
- **Fragile:**
  - Name-based removal of the helper.
  - Non-square textures get squashed.
  - JPEG drops alpha.
  - `export_animations=False` throws away any Tripo animation. This has to change if the skill uses Tripo animate.
  - The "first mesh" choice is arbitrary for multi-mesh rigs.

### 1.10 `G/tools/blender/qa_render.py`: renders and numbers
- **Output:**
  - `<prefix>_{front,left,back,right,iso}.png` and `<prefix>_iso_wire.png`: Workbench renderer, `light=FLAT`, `color_type=TEXTURE` (albedo only), white world, orthographic, 900 px (`:17-24,40-53`). The wireframe is a WIREFRAME modifier copy with thickness `size*0.0015`, drawn black (`:54-65`).
  - `<prefix>.json` with `tris`, `sliver_pct`, `size_m` and `lowest_pct` (`:76-112`). A sliver is a triangle with `area/longest_edge² < 0.02` (`:94`). `lowest_pct` is, for each side third of the footprint (left, right, front, back), the lowest Z as a % of the height. 0 means the side touches the ground, so the number catches a floating or tilted base.
- **View convention:** "front" is the camera at Blender −Y, which is Godot +Z after glTF export (`:8,18`). "left" is the camera at −X, i.e. the viewer's left when facing the front, which is the object's right side. Document this explicitly in the skill.
- **Generic, worth porting:**
  - The whole script.
  - The `lowest_pct` ground-contact metric, which is cheap and was validated by a real play-test bug (commit d478a9f, `G/tests/unit/test_belt_surface.gd` per that commit).
  - Sliver share as a weak signal only.
- **Gaps and bugs:**
  - **Flat albedo lighting cannot show the artefacts the owner complained about most:** normal waves, wrinkles on flat faces, star-shaded fans, dark wedges (see the docstrings of `fix_mailbox.py`, `fix_parking_meter.py`, `fix_pedal_car.py`, `fix_fire_hydrant.py`). Those were caught in the lit three.js viewer and in game captures. The skill's QA needs at least one lit render (studio light or matcap) next to the albedo render.
  - The ortho scale is `max_dim*1.15` (`:51`). The iso projection of a boxy object can be up to about 1.41× the max dimension, so iso views can crop corners.
  - The camera distance is `size*3` against the default clip_end of 100 m, so objects over about 30 m clip.
  - Only the iso view has a wireframe.
  - There are no non-manifold, open-boundary, loose-part, UV-overlap, texel-density or normal-flip checks.

### 1.11 `G/tools/blender/mesh_paint.py`: base layer for fixes
- **`Model(path)`:**
  - Factory reset plus import. Takes the first MESH and the **first TEX_IMAGE node of material slot 0** as the albedo (`:9-19`). With PBR maps this could pick the wrong image.
  - `texel(poly)` samples the UV centre.
  - `raster(polys, with_pos)` is a CPU barycentric rasteriser from faces to a texel mask. It can also return the model-space position and face id per texel (`:26-53`). It is pure Python per face and slow on large meshes.
  - `move(co, moved)` gives fresh smooth normals only to moved vertices and keeps the old custom normals elsewhere (`:55-69`).
  - `save()` writes pixels back, packs, and exports GLB with JPEG (`:71-76`).
- **Helpers:**
  - `grow(mask, texels)` dilates a mask, "because thin UV triangles cover no texel centre" (`:79-89`).
  - `recolour(px, mask, colour, spread)` sets a colour but keeps the relative luminance within ±spread, so the baked shading survives (`:92-97`).
- **Generic, worth porting:** all of it, for "free Blender fix" options such as texture recolour of a region (paint bleed, wrong colour on a hidden side).

### 1.12 `G/tools/blender/mesh_fix.py`: repair kit (`Mesh(Model)`)
- **Load:** weld with `remove_doubles 1e-4`, then triangulate. Data is kept as numpy arrays `co`, `tri`, `tri_uv` (`:20-46`).
- **Primitives:**
  - `normals`, `vertex_normals`, `face_mask(vmask, every)`, `colours()` (texel at each face's UV centre), and `islands()` (union-find on shared vertices) (`:52-96`).
  - `taubin(weight, iters=10, lam=0.5, mu=-0.53)`: shrink-free smoothing, weighted per vertex. It rounds feature edges, so keep it off them (`:7-8,99-110`).
  - `creases(angle=45)`: real feature edges; Tripo wrinkles fold less (`:112-121`).
  - `flatten_face(axis, weight, tol=0.008, angle=35, depths=None, min_share=0.12)` (`:135-172`):
    1. Finds faces facing `axis`.
    2. Builds an area-weighted depth histogram with 2 mm bins.
    3. Peels peaks that hold at least 12% of the area (e.g. the box face, then a raised door).
    4. Snaps vertices within 8 mm onto each plane.
    5. Marks those faces to shade exactly flat.
  - `delete(fmask)` deletes faces and loose vertices.
  - `fill_holes(vmask, uv, max_sides=400)` runs bmesh `holes_fill`, then BEAUTY triangulation, and gives every new face one UV point. Its colour comes from `uv_of(colour, near)`, which picks a face whose texel matches the colour (`:182-220`).
  - `paint` and `median_colour` (`:223-230`).
  - `save()`: angle-weighted smooth normals. Flattened faces get weight ×1000 and an exact plane normal, "so a panel stays flat right up to its edge"; custom split normals are set (`:233-256`).
  - `falloff()` and `box(co, lo, hi, fade)` build soft region weights in metres (`:259-271`).
- **Generic, worth porting:** yes, as the free-fix library: weld+triangulate arrays, flatten planar faces, taubin, delete+fill+colour-matched UV, region boxes with falloff, flat-shaded panels.
- **Fragile:**
  - Every tolerance is in **metres**, so it only works after clean_model has scaled the model to real size. Parametrise the tolerances relative to the bounding box, or require a scaled input.
  - Filling with a single UV point gives a flat colour patch with no texture detail.
  - `holes_fill` sometimes skips holes (`G/tools/blender/fix_common.py:56-59`, the traffic light).
  - `assert all triangles` (`:41`).
  - Requires Blender ≥ 4.1 (`corner_normals`); OK on 5.2.3.

### 1.13 `G/tools/blender/fix_common.py` and `G/tools/blender/keep_normals.py`: keep the generator's normals
- **Key finding (both docstrings):** "Mesh.save rebuilds every normal, and on Tripo meshes the rebuilt smooth normals show waves that Tripo's own normals hide" (`fix_common.py:3-5`). Recomputing normals shows "wrinkles … far from the part that was fixed" (`keep_normals.py:2-3`). **Never recompute normals globally on Tripo output; keep the exported custom normals wherever the geometry did not change.**
- **`fix_common`:**
  - `original_normals(path)` keys every input triangle by its sorted corner positions rounded to 1e-5 (`:16-26`).
  - `save_keeping(m, path, before, shift)` restores those normals on triangles that are unchanged. It does this by **monkey-patching `mesh_paint.Model.save`** inside try/finally (`:29-53`). This is fragile.
  - `fill_loops(m, vmask, uv, outward)` walks boundary loops itself, makes one face per loop oriented toward `outward`, then triangulates. It exists because `holes_fill` skipped a hole (`:56-96`).
- **`keep_normals`:**
  - `snapshot(path)` stores the mean corner normal per vertex position on a 1e-4 grid (`:18-38`).
  - `save(m, path, before, co0, fixed, loops)` keeps the snapshot normal for unmoved vertices that do not touch a fixed face (`:41-81`).
- **Shared caveat:** two overlapping implementations (per-triangle vs per-vertex matching). Both reset the Blender scene on load, so they **must be called before `Mesh(src)`**. The callers do this correctly (`fix_phone_booth.py:30-31`, `fix_parking_meter.py:34-35`, `fix_vending_machine.py:37-38`), but nothing enforces it. Consolidate into one `NormalKeeper` that snapshots inside `Mesh.__init__`.

### 1.14 `G/tools/blender/fix_anchor.py`: example per-model fix (pattern is generic, numbers are not)
- **Steps:**
  1. Select faces inside a hand-measured box `LINK_BOX`, in metres in the post-clean frame (front toward −Y), that are lighter than `CHAIN_LUM=0.33`.
  2. Add darker faces within `REACH=8 mm`.
  3. Delete them, then delete leftover islands under `SHRED_FACES=300`.
  4. Fill the holes inside the box with the UV of the ring's median "iron" colour.
  5. Taubin-smooth with a 1 cm fade (`:18-51`).
- **Context:** written from an owner review note with a date, and run after clean_model at `--yaw -90` (`:5-8`).
- **Generic recipe:** region (box + colour/luminance) → delete → drop shreds → fill → recolour by sampling a nearby colour → local smooth.
- **Project-specific:** every constant.

### 1.15 The other `fix_*.py` (not in scope in detail; taxonomy of the Tripo defects they fix)
Read from the docstrings of `G/tools/blender/fix_*.py`:
- **Hidden-side hallucination:** front details copied onto the back (`fix_engine_block`, `fix_tool_chest`, `fix_traffic_light`, `fix_phone_booth`) or a misshapen far side (`fix_scooter`). Fix: press flat and repaint, or **mirror the good half** with the same UVs and mirrored normals.
- **Wrinkled flat faces** (`fix_mailbox`, `fix_vending_machine`, `fix_birdhouse`): `flatten_face` plus flat shading.
- **Shading artefacts that look like dents** (`fix_parking_meter`, `fix_fire_hydrant`, `fix_pedal_car`): long faces share vertices with flat caps, so smooth normals bend. Fix: snap to true cylinders or surfaces of revolution with radial normals, and give caps flat normals.
- **Extra or stray parts:** `fix_anchor`, `fix_statue` (extra hand), `fix_bus_stop` (poles), `fix_bbq_grill` (knob), `fix_pedal_car` (ground discs fused to the tyres → reuse one clean wheel).
- **Ground slab fused under the object** (`fix_phone_booth`). Fix: cut it, close the bottom, re-ground the object.
- **Closed cavities the views never saw** (`fix_pickup`, cargo bed). Fix: cut and build an inner box.
- **Broken transparent parts** (`fix_bus_stop`, glass). The game uses one opaque material, so the glass is rebuilt as opaque panes painted from a free atlas corner.
- **Paint bleed and projection errors** (`fix_pool_pink`: a single-view projection of the float's pink onto a hidden wall; `fix_pot_soil`; `fix_hatchback`; the pedal-car seat smear). Fix: recolour while keeping luminance.
- **Cracks between shells** (`fix_jerry_can`). Fix: weld open-edge vertices within a distance.
- **Owner-workflow lessons (`G/tools/place_refs.sh:24-46`):**
  - Fix scripts are re-runnable and chained after placement, as `fix <out> <out>`.
  - Second and third Tripo attempts with a *simpler reference* often beat geometry surgery (`fix_tool_chest` "third Tripo attempt, simpler reference", `fix_jerry_can` "third multiview", the pickup's second sheet, `G/docs/asset_log.md:194,199,200`).
  - Placing unfixed and fixing flaws "as they show in play" was an accepted mode for less important items.

---

## 2. Cross-cutting bugs and fragile parts (fix these when porting)
1. **Blender exit codes:** every `subprocess.run(["blender","-b","--python",...], check=True)` (`qa_models.py:73`, `place_model.py:52`, and the shell scripts) silently succeeds on a Python exception. Always pass `--python-exit-code 1`, check that the outputs exist, and keep stderr for the log.
2. **Island logic on an unwelded glTF import** (`clean_model.py:137-164`). Weld first.
3. **Whole-scene rewrite** in `place_model.py:60-65`. Replace only the placeholder node, and keep the scripts, collision and siblings.
4. **Unit assumptions:** mesh_fix tolerances are in metres, and fix boxes are hand-measured in the post-clean frame. Any change to yaw, height or origin invalidates every fix script's constants. Re-running `place_refs.sh` with a different `H=` would put the fix boxes in the wrong place.
5. **Orientation is guessed per model** (yaw −90, 90, 180, 0 in `place_refs.sh`). The "Tripo faces +X" rule held for most models but not all. Detect it from QA renders and confirm it with the user.
6. **Two normal-preservation modules** plus a monkey-patch (`fix_common.py:41-52`). Merge them.
7. **Texture handling:** forced-square resize (`clean_model.py:85-86`, `clean_rigged.py:17-18`), first-TEX_IMAGE-is-albedo (`mesh_paint.py:15-16`), JPEG everywhere (no alpha).
8. **The QA render is flat albedo,** so it misses shading defects (see 1.10).
9. **CDN dependencies** in the viewers and the QA page.
10. **Hand-rolled argv parsing** in `key_views.py` and `key_icon.py`; positional view naming.

---

## 3. GENERAL lessons (true for any game; candidates for the global skill)
1. **Never recompute normals across a whole Tripo mesh.** Keep the generator's custom split normals on untouched geometry, and rebuild normals only on edited faces (`fix_common.py:3-5`, `keep_normals.py:1-11`).
2. **Weld before topology analysis.** Tripo GLBs are split at every UV seam (`mesh_fix.py:1-3`, weld 1e-4 m). Islands, holes and boundaries are meaningless until the mesh is welded.
3. **Ask Tripo for the triangle budget** (`face_limit`) rather than decimating afterwards. All logged models used face_limit = budget, and the local decimate is only a safety net (`clean_model.py:57-60`, `G/docs/asset_log.md:34-41`). Smart low poly (v3.1) gave about 0.8% slivers against 1.5-17.6% for P1 (`qa_models.py:26-27`).
4. **Measure facing; do not assume it.** Most Tripo outputs face +X (yaw −90 to Godot +Z), but about 10% needed 90, 180 or 0 (`place_refs.sh`). Pick the yaw from a 4-view render, with the user confirming which side is the front.
5. **Fit size to the placeholder:** use the placeholder's measured extent along a chosen axis (default height), uniform scale, origin at the centre of the base (`place_model.py:39-42`, `clean_model.py:66-73`). Long or flat objects need a different fit axis or explicit numbers (`place_refs.sh:42-55`).
6. **Check ground contact per side.** The `lowest_pct` per footprint third (`qa_render.py:98-111`) catches floating and tilted bases. A real play-test bug (an 8° belt slope, objects floating 4-10 cm) motivated this check and `--origin surface` (`git show d478a9f`).
7. **Automatic metrics are weak signals.** The owner's verdict comes from looking: wireframe, a lit view from the game camera, and an in-game capture (`qa_models.py:182`, commit 3dbef2b). Sliver % is a flag, not a gate.
8. **Review from the player's camera first** (direction and FOV taken from the project's camera), then orbit (`model_viewer.py:70-76`, owner rule 2026-10-29).
9. **QA needs a lit render,** not just albedo. Most owner complaints were shading defects that a flat albedo render cannot show (§1.10).
10. **Before/after split screen with a shared camera** is the right approval UI for fixes (`model_compare.py`).
11. **Provenance sidecars:** save the exact prompt, model, refs and task id next to every generated artefact (`gen_image.py:76-78`, `G/docs/asset_log.md`). The asset log also records credits per task.
12. **Multiview inputs:** one common scale, one ground line, transparent or white background, a single object per view (`key_views.py:88-99`). A four-view reference stops hidden-side guessing. A single view projects front colours onto hidden surfaces (`fix_pool_pink.py` docstring, `G/docs/decisions.md:259`).
13. **Typical Tripo defects** to look for in QA, in order of frequency:
    1. Hidden-side copies of front details.
    2. Wrinkled flat panels.
    3. Smooth-normal dark wedges where cylinders meet flat caps.
    4. Stray fused parts (ground slabs, discs under wheels, helper spheres in rigs).
    5. Closed cavities.
    6. Paint bleed between adjacent parts.
    7. Shell cracks.
    8. Broken transparent parts.

    See §1.15.
14. **Free-fix toolbox that worked** (port it): flatten planar faces by depth layers, taubin with region falloff, delete + shred removal + hole fill with a colour-sampled UV, mirror the good half (same UVs, mirrored normals), snap to cylinders or revolution surfaces, luminance-preserving recolour, dilate texel masks by 2 because of thin UV triangles.
15. **Re-roll with a simpler reference** often beats surgery: 2nd and 3rd sheets for the tool chest, jerry can and pickup (`G/docs/asset_log.md:194,199,200`).
16. **Rigging:** an A-pose multiview model with limbs separate from props passes Tripo's rig check. Fused arms or props fail it (`G/docs/decisions.md:290-291`). After rigging, strip the `Icosphere*` helper and keep the armature and skin untouched (`clean_rigged.py`).
17. **Godot glTF texture naming:** name the image after the asset. Godot's "extract textures" import writes `<glb>_<image name>.<ext>`, so a predictable image name gives a predictable texture path (`clean_model.py:84`, `bbq_grill.glb.import`).
18. **Keep scene identity when replacing:** same scene path, same root name, same node ids. Every resource that points at the scene keeps working (`place_model.py:57-65`).
19. **Make every step re-runnable** from raw output (`place_refs.sh`, `backyard_scene.sh`). Fixes are scripts with the review note in the docstring, not hand edits in Blender, so a re-placement can replay them.

## 4. PROJECT-SPECIFIC lessons (grime-does-pay only; do not promote)
- Data model: `data/objects/<zone>/<id>.tres` (ObjectDefinition with `scene`, `bounds`, `silhouette`, `is_boss`, `size_class`) → `scenes/objects/<zone>/obj_<zone>_<id>.tscn` → `assets/models/objects/<zone>/<id>.glb`. Bosses use `assets/models/bosses/` (`place_model.py:31-50`).
- Budgets: belt objects ≤ 8k triangles, 1 material, 1K texture. Bosses ≤ 30k (Tripo face_limit 20000). Backdrops 2-5k at 512 px (`G/docs/gdd/07-ai-asset-pipeline.md` §7.1, `backyard_scene.sh:20-26`).
- One opaque material per model, so glass becomes painted opaque panes (`fix_bus_stop.py` docstring).
- Game camera: from about (0.94, 2.09, 3.50) toward the origin, FOV 22°, the same in every zone (`model_viewer.py:70-73`). The silhouette mask and bounds are baked by `scripts/dev/bake_silhouette.gd`, which flags `OFF-SCREEN` (`:67-73`). This is why long models got `H=` overrides.
- Post-placement steps: `bake_silhouette.gd -- <ids>`, `scripts/check_import.sh`, `run_tests.sh` (`place_refs.sh:3-4`). `tests/unit/test_silhouette_baker.gd` fails on a stale mask (`G/docs/decisions.md:84`).
- Style formula text (`tools/style/style_formula.txt`); the chroma #00B140 sheet with 4 views plus 4 close-ups; `art_src/` and `.tripo/` gitignored; `*.glb/*.png/*.jpg` in Git LFS (`G/.gitignore`, `G/.gitattributes`).
- Windowed Godot runs must not steal focus (`run_quiet.sh:2-4`, owner rule 2026-10-23).
- Turkish UI strings in the review pages; the owner writes review notes in fix-script docstrings with dates.
- Belt surface: `--origin surface` exists only for the belt (`backyard_scene.sh:15`).
- Costs seen: 50 credits per multiview model, 25 per rig, 14 models = 700 credits (`G/docs/decisions.md:259-291`).

## 5. What to port into the skill's `scripts/` (concrete)
| Skill script | Source | Changes needed |
|---|---|---|
| `blender/normalize.py` (clean) | `clean_model.py` | `--python-exit-code`; weld before islands; `--fit` + explicit dims; JSON report to stdout or file; never on rigged input; keep custom normals; no forced-square textures |
| `blender/normalize_rigged.py` | `clean_rigged.py` | detect the helper by geometry or size, not only the name; optionally keep animations; preserve aspect ratio |
| `blender/qa.py` | `qa_render.py` | add a lit or matcap render, game-camera render, wireframe on all views, non-manifold, open-boundary, loose-part, flipped-normal, UV-overlap and texel-density stats; fix iso cropping (ortho scale from the projected bounds); `lowest_pct` kept; JSON schema stable |
| `blender/fixkit/` | `mesh_paint.py`, `mesh_fix.py`, `fix_common.py`+`keep_normals.py` merged | tolerances relative to the bounding box; one normal keeper that snapshots in the constructor; add `mirror_half(axis)`, `snap_cylinder`, `weld_open_edges`, `cut_below(z)+cap`; a fix-script template with the review note in the docstring |
| `qa_page.py` | `qa_models.py` | engine-agnostic inputs (glb list + optional old glb + optional game screenshot + reference); English or locale strings; no CDN fonts |
| `viewer.py` | `model_viewer.py` + `model_compare.py` | one script with `--compare`; camera dir and FOV from args or the project camera; per-entry yaw; vendored three.js or an offline fallback; run in background, kill on finish |
| `prep_views.py` | `key_views.py` | argparse; explicit view-order mapping that matches the Tripo multiview argument order; fail with a preview instead of exiting; magenta key option from `key_icon.py` |
| `godot_place.py` | `place_model.py` | edit the `.tscn` surgically (replace the placeholder MeshInstance3D or primitive subtree, keep the root, scripts, collision and ids); measure the placeholder AABB by headless Godot or by parsing primitives; show a diff and wait for user approval; then run `godot --headless --import` and report errors |
| provenance sidecar | `gen_image.py:76-78` | write `<asset>.provenance.json` (tool, model version, params, task id, credits, prompt, refs, date) |
