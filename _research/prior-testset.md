# Prior work → test set for the `tripo` skill

Source: read-only inventory of two Godot games done by hand / ad-hoc scripts.
- GRIME = `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay`
- PATINA = `/Users/muhsin/Documents/GitHub/mumudevx/patina`

Every path below is written out in full. Triangle counts come from reading glTF accessors (index count / 3, mode 4) with a stdlib-only script, `/private/tmp/claude-501/-Users-muhsin-Desktop/166dc050-13e0-46a5-8f2e-efdde9f7525c/scratchpad/glbstat.py` (`python3 -I glbstat.py <glb...>`). It also prints meshes, materials, images, skins and joints. Worth porting into the skill as a zero-install QA preflight.

---

## 0. Inventory (counts and sizes)

| dir | files | size | .glb | task.json | preview.(png/jpg) | front.png | notes |
|---|---|---|---|---|---|---|---|
| `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src` | 1878 | 1.7G | 166 | 64 | 120 | 102 | 59 `sheet_green.png` chroma-key turnaround sheets; 57 `job3d.id` (Higgsfield H3.1 jobs); 7 .py; 173 of 878 ".png" are really JPEG |
| `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source` | 1668 | 2.0G | 146 | 100 | 88 | 111 | 37 GLBs >10 MB (1.5 GB total: the un-limited ~1.4M-tri generations); 191 of 1039 ".png" are really JPEG |
| `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets` | 529 | 50M | 86 | 0 | 0 | 0 | cleaned GLBs, 1 mesh / 1 material / 1K JPEG each, 0.24-0.7 MB |
| `/Users/muhsin/Documents/GitHub/mumudevx/patina/assets` | 963 | 191M | 49 | 0 | 0 | 0 | GLBs are **byte-identical** to Tripo output (md5 checked on 3 files). Fixes live in Godot (52 `meshes/*.res` + generator scripts) |
| `/Users/muhsin/Documents/GitHub/mumudevx/patina/art` | 2 | 4K | 0 | - | - | - | only `palette.png` + `.gdignore`, so it does not matter here |

Where the raw outputs come from (the skill has to recognise all three):
1. **tripo-cli 0.6.1**: `<dir>/tripo-out/<label>-<8-char task id>/{task.json, model.glb, preview.png, rendered_image.webp}`, plus a sibling `tripo_<id>.json` (summary) and `tripo_<id>.log` (progress). Example: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/tripo/pickup/tripo-out/pickup-g2-88b150b0/`.
2. **Higgsfield wrapper of Tripo H3.1** (`higgsfield generate create tripo_h3_1_multiview_to_3d`, script `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/make3d.py`): `<id>/{sheet_green.png, views/, job3d.id, job3d.json, model_h31.glb, model_h31.orig.glb, preview.jpg, placed.glb, fixed.glb}`. Example: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_park_bench/`.
3. **PATINA layout**: `<object>/{parts.json, concept/<part>/{hero,front,left,back,right}.png+.txt, tripo_raw/<part>/{full,reduced}/tripo-out/*/, turn/<part>/ (8 Godot turnaround renders), final/*.glb, ingame/*.png}`. Example: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/folding_camera_01/`.

The CLI drops state into its cwd: `.tripo/context.json` (`{"last_task_id": ...}`) sits in `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/.tripo/`, `/Users/muhsin/Documents/GitHub/mumudevx/patina/.tripo/`, `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/props/mailbox_01/.tripo/` and `.../folding_camera_01/concept/body/.tripo/`. Without a label, the output folder is named from the absolute input path (`users-muhsin-documents-github-mu-10-2dac6c9c`), which makes the folders hard to pair. GRIME's labelled runs (`@crew-rig`, `pickup-g2`) pair cleanly.

Asset logs: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/asset_log.md` (202 lines, one row per id; "L<n>" below is the line number in that file) and `/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/asset_log.md` (21 lines, one row per part group).

---

## 1. Test cases (12): reference ↔ raw ↔ fixed ↔ fix script ↔ log

Abbreviations inside the table cells: `GA=/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src`, `GS=/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models`, `GT=/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender`, `PA=/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source`. The full paths follow each table.

### T1 Park bench: thin parallel parts (wavy slats, fused slats). Pipeline: Higgsfield H3.1
- Ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_park_bench/sheet_green.png` (+ `views/{front,left,back,right}.png`). The reference is clean; I viewed it.
- Raw: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_park_bench/model_h31.orig.glb` (7104 tris, 2.76 MB). `model_h31.glb` is identical in tris.
- Intermediate: `.../obj_depot_park_bench/placed.glb` (7104 tris, 0.36 MB, after clean_model). Fixed: `.../obj_depot_park_bench/fixed.glb` = `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/depot/park_bench.glb` (7343 tris).
- Fix script: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_park_bench.py`. Each slat is rebuilt as a straight extrusion of its median cross-section, the fused front slat and lip are split, and a real 5 mm gap is cut.
- Log: GRIME asset_log L45.
- Known defects: wavy seat slats with uneven gaps; dented backrest slats; the front slat fused with the lip; a V notch that reads as a black zigzag.
- QA should catch: high curvature noise on faces that should be planar; gap width varies along the length.

### T2 Pedal car: vehicle, many separate defects, retexture tried. Pipeline: tripo-cli v3.1
- Ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard_v2/pedal_car_sheet_green.png`, `.../backyard_v2/pedal_car_views_v2/`, older `.../backyard_v2/pedal_car_turnaround.png`.
- Raw: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard_v2/tripo/pedal_car/tripo-out/pedal-car-v2-47bd0ee9/model.glb`: **12367 tris with face_limit 10000** and smart_low_poly=true, 50 credits.
- Paid retexture: `.../backyard_v2/tripo/pedal_car_retex/tripo-out/pedal-car-retex-4b70db23/model.glb` (texture_model v3.0, 20 credits, same 12367 tris).
- Before and after the second fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard_v2/pedal_car_fix2/{before.glb (12367), placed.glb, fixed.glb (11213)}`. Final: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/backyard/pedal_car.glb` (11213).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_pedal_car.py`, driven by `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/place_refs.sh` (tail).
- Log: L39.
- Known defects:
  - flat decal discs with smooth normals, which shade as a star of lines;
  - colour bleed (steering-wheel yellow on the seat);
  - **thin ground discs fused into 3 of 4 tyres**: fixed by deleting them and copying the one clean wheel to the other axles;
  - wrinkled body sides;
  - a dark smudge that reads as dirt.
- QA should catch: geometry below the ground plane or near it that does not belong to a wheel; inconsistency between wheels (3 differ from 1).

### T3 Tool chest: symmetry failure plus front detail copied onto the back; 3 paid generations
- Ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/tool_chest_sheet_green.png`, `.../garage/tool_chest_views/`. v1 views are in `.../garage/old/tool_chest_views_v1/`.
- Raws:
  - `.../garage/tripo/tool_chest/tripo-out/tool-chest-g1-14303625/model.glb`: **17430 tris with face_limit 8000** (smart_low_poly);
  - `.../garage/tripo/tool_chest_g2/tripo-out/tool-chest-g2-36cb4a67/model.glb` (10556);
  - `.../garage/tripo/tool_chest_g3/tripo-out/tool-chest-g3-ae290642/model.glb` (9327).
- Final: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/garage/tool_chest.glb` (9780).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_tool_chest.py`. The −X half is replaced by the +X half mirrored; the back is pressed flat and painted.
- Log: L194.
- Known defects: only the +X side got its handle; the 4 drawers and pulls were copied onto the plain back.
- QA should catch: L/R asymmetry on an object declared symmetric; back face has front-like relief.

### T4 Pickup: hidden concavity closed (bed lid). Vehicle
- Ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/pickup_sheet_green.png`, `.../garage/pickup_views/`. v1 sheet: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/old/v1_sheets/pickup_sheet_green.png` (viewed: four eye-level orthographic views; the bed interior shows only in a detail crop that Tripo never receives).
- Raws: `.../garage/old/v1_3d/pickup/tripo-out/pickup-g1-1bb89de6/model.glb` (9120) and `.../garage/tripo/pickup/tripo-out/pickup-g2-88b150b0/model.glb` (9625).
- Final: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/garage/pickup.glb` (9687).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_pickup.py`. The lid is cut out and a box with walls and a floor 16 cm down goes in.
- Log: L200. g1 was also rejected because the rear-window glass ran down onto the bed.
- Known defect: both generations closed the bed with a flat lid level with the walls.
- Pre-flight should catch: an open-top cavity that no input view looks into. Add a top or three-quarter view, or plan a Blender cut.

### T5 Crew worker: rigged character (rig pre-check fail, then pass)
- Bad ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard/scene/crew.png` (viewed: the worker holds the lance with both hands against the body).
  - Its raw: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard/scene/tripo/crew/tripo-out/scene-crew-750031d4/model.glb` (7847 tris, P1).
  - Rig pre-check: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/crew_rig/tripo-out/rig-check-17b22096/task.json` (`animate_prerigcheck`, 0 credits). It FAILED per `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/decisions.md` L291: arms and lance fused to the torso.
- Good ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/crew_rig/worker_apose.png` + `worker_apose.prompt.txt` (A-pose about 40°, empty hands, gaps between arms, torso and legs). Views: `.../crew_rig/views/`.
  - Raw: `.../crew_rig/tripo/tripo-out/crew-apose-b615fca7/model.glb` (7884 tris, P1, face_limit 8000, 50 credits).
  - Pre-check 2: `.../crew_rig/tripo/tripo-out/rig-check-2-43a6665a/task.json` (passed).
  - Rigged: `.../crew_rig/tripo/tripo-out/crew-rig-4200bdf5/model.glb` (`animate_rig`, topology biped, 25 credits, 1 skin, 27 joints, 0 animations).
- Final: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/crew/worker_rig.glb` (0.37 MB).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/clean_rigged.py` (drops an `Icosphere*` helper mesh, 1K JPEG, no transform change).
- Log: L25. Decision: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/decisions.md` L288-291.
- Known gotchas:
  - Tripo bone names are `tripo::1_Right_Limb_0..2` (arms), `tripo::0_*_Limb_0..3` (legs), `tripo::Head_0..2`, `tripo::Spine_0`, `tripo::Root`, plus anonymous `bone_4/8/20-26`. This is not Mixamo or humanoid naming.
  - Godot renames `::` to `__`: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/scripts/components/crew_figure.gd` L25-28 uses `tripo__1_Right_Limb_0`.
  - The pre-check `task.json` has no result field; the verdict must be read from the CLI output.

### T6 Statue: organic figure + prop; a part through the head; extra hand. Pipeline: H3.1
- v1 ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_statue/v1/sheet_green.png` (viewed: the telescope is held across the face in every view, and the arm overlaps the head).
  - v1 raw: `.../obj_depot_statue/v1/model_h31.glb` (7244 tris, "telescope through the head and a face on the back", 16 credits).
- v2 ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_statue/sheet_green.png` (prompt rewritten: an upright telescope at the side).
  - v2 raw: `.../obj_depot_statue/model_h31.orig.glb` (7646).
- Fixed: `.../obj_depot_statue/fixed.glb` = `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/depot/statue.glb` (7178).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_statue.py` (removes the telescope and the extra hand by radius around the tube axis, then fills and smooths).
- Log: L46.
- Known defects: v1 had a prop through the head and a duplicated face on the back; v2 had a second hand gripping the prop while the arm's own hand was on the hip.
- Pre-flight should catch: a prop that overlaps the face or torso in the views.

### T7 Traffic light: front features duplicated onto the back; wrong-side orientation trap. Pipeline: H3.1
- Ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_traffic_light/sheet_green.png` (viewed: a clean, plain back is drawn, and Tripo still invented lamps there).
- Raw: `.../obj_depot_traffic_light/model_h31.orig.glb` (7767). Placements: `placed_yaw-90.glb`, `placed.glb`.
- Wrong fix: `.../obj_depot_traffic_light/fixed_wrongside.glb` (5851 tris; it removed the wrong face). Right fix: `fixed.glb` (7765).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_traffic_light.py`. The visored side is the front, so `--yaw 90`.
- Log: L52.
- Known defect: lamps on both faces of the housing. The front has to be identified by a feature (visors), not assumed from Tripo's +X axis.
- Same family of defect, back invents front detail: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_engine_block.py` (L198; raw `.../garage/tripo/engine_block/tripo-out/engine-block-g1-84c0c6f6/model.glb` 10274 → `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/garage/engine_block.glb` 9437; the pressed-flat inner faces were left coplanar and z-fought as rings, so they had to be deleted).

### T8 Jerry can: bad reference → bad model; re-roll budget
- Bad ref v1: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/old/v1_sheets/jerry_can_sheet_green.png` (viewed: the "side" views are three-quarter views of the X face). Views: `.../garage/old/v1_sheets/jerry_can_views/`.
  - Raw g1: `.../garage/old/v1_3d/jerry_can/tripo-out/jerry-can-g1-09184ab4/model.glb` (9464).
- Ref v2: `.../garage/old/v2_sheets/jerry_can_sheet_green.png`.
  - Raw g2: `.../garage/old/v2_3d/jerry_can/tripo-out/jerry-can-g2-5cac76fd/model.glb` (10710; **three handles and a second cap**).
- Ref v3: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/jerry_can_sheet_green.png`.
  - Raw g3: `.../garage/tripo/jerry_can/tripo-out/jerry-can-g3-a08c5dde/model.glb` (10567).
- Final: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/garage/jerry_can.glb` (10533).
- Fix: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_jerry_can.py` (welds a crack under the +X shoulder and rebuilds the normals).
- Log: L199. Total: 3 × 50 credits for one prop.

### T9 Bicycle: thin parts (spokes, rims); single image vs multiview
- v1 ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard/bicycle.png` (one three-quarter image).
  - v1 raw: `.../backyard/tripo/bicycle/tripo-out/by-bicycle-2e7197a0/model.glb` (7990 tris, P1 image_to_model).
- v2 ref: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard_v2/bicycle_turnaround.png`, `.../backyard_v2/bicycle_views/`.
  - v2 raw: `.../backyard_v2/tripo/bicycle/tripo-out/bicycle-v2-14424197/model.glb` (10907, v3.1 multiview).
- Final: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/assets/models/objects/backyard/bicycle.glb` (10907, not decimated). No fix script: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/place_model.py --yaw 180 --max-tris 12000` only.
- Log: L13 (v1) and L34 (v2): "no tyre/rim teeth, sliver triangles 2.5% → 0.8%".
- A good control case: QA should pass v2 and flag v1 (teeth, slivers).

### T10 Tube radio back panel and dial glass: perforated plate and thin framed glass vs face_limit and decimation (PATINA)
- Refs: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/tube_radio_01/concept/back_panel/` and `.../concept/dial_glass/`. Manifest: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/tube_radio_01/parts.json`. Batch runner: `.../tube_radio_01/run_tripo.sh` + `tripo_jobs.txt`.
- First raws, made with face_limit at generation:
  - `.../tube_radio_01/tripo_raw/back_panel/tripo-out/users-muhsin-documents-github-mu-2-df43efa0/model.glb` (5456 tris, limit 6000);
  - `.../tube_radio_01/tripo_raw/dial_glass/tripo-out/users-muhsin-documents-github-mu-10-2dac6c9c/model.glb` (2834, limit 4000).
- No-limit generations:
  - `.../tube_radio_01/tripo_raw/_quality_test/back_panel_high/tripo-out/front-3-548f50aa/model.glb` (1,467,502 tris, 44.9 MB, 30 credits);
  - `.../tube_radio_01/tripo_raw/_high/dial_glass/tripo-out/front-8-b99d5612/model.glb` (1,383,546).
- Decimation A/B (all in `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/tube_radio_01/tripo_raw/_quality_test/`):
  - `back_panel_v1_12k` (v1.0, 12000, 10 credits) is the one that shipped;
  - `back_panel_v1_4000` (4000, crumples);
  - `back_panel_v2_20k` (v2.0: **29943 tris for a 20000 request**, spikes);
  - `back_panel_dec` (v2.0 at 3000 → 4356, dished);
  - `back_panel_slp` (smart_low_poly, 3926, worse).
  - Visual comparison: `.../_quality_test/cmp_back_panel.png` (viewed: holes become dents with face_limit; real round holes in the decimated high-poly mesh).
- Dial glass at 3000, 8000 and 12000: `.../tube_radio_01/tripo_raw/_high/dial_glass_dec{3000,8000,12000}/`.
- Final: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/tube_radio_01/final/{back_panel,dial_glass}.glb` (12000 / 12002) = `/Users/muhsin/Documents/GitHub/mumudevx/patina/assets/models/antiques/tube_radio_01/tube_radio_01_dial_glass.glb` (same md5).
- Fix (Godot side): `/Users/muhsin/Documents/GitHub/mumudevx/patina/scripts/dev/generate_tube_radio_models.gd` (`NO_NORMAL_TEXTURE` L69, `TRIANGLES` L60) plus `/Users/muhsin/Documents/GitHub/mumudevx/patina/scripts/dev/mesh_reducer.gd` (12002 → 12000).
- Log: PATINA asset_log L11-12. Also `/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/decisions.md` L426 and L455, `/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/later.md` L98-110.
- Known defects:
  - a face_limit at generation makes hard surfaces wavy and turns holes into dents;
  - v1.0 decimation keeps the high-poly normal map on the low mesh, so the panes bend and the panel creases around every hole. The game turns that normal map off.

### T11 Folding camera: multi-part antique (11 parts, 52.0k tris) with thin plates and A/B quality settings (PATINA)
- Root: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/folding_camera_01/` (`parts.json`, `concept/<part>/`, `concept/_rejected/`, `tripo_raw/<part>/{full,reduced}/`, `turn/<part>/`, `ingame/`).
- Shutter A/B, all in `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/folding_camera_01/tripo_raw/_ab_shutter/`:

  | variant | tris | size | credits |
  |---|---|---|---|
  | `std` (no limit) | 1,413,185 | 43 MB | 30 |
  | `detailed` (geometry + texture detailed) | 1,928,464 | 64 MB | 60 |
  | `std_v1` | 8000 | - | 10 |
  | `std_v3` (shipped) | 7481 | - | 35 |
  | `detailed_v1` | 8000 | 5.6 MB | - |
  | `detailed_v3` | 8148 | - | - |

  Comparison image: `cmp_shutter.png`.
- top_plate: `.../folding_camera_01/tripo_raw/top_plate/full/tripo-out/users-muhsin-documents-github-mu-19-b66b77be/model.glb` (1,391,172) → `.../top_plate/reduced/tripo-out/decimate-21-66246195/model.glb` (2443) = `/Users/muhsin/Documents/GitHub/mumudevx/patina/assets/models/antiques/folding_camera_01/folding_camera_01_top_plate.glb` (same md5).
- Fix (Godot): `/Users/muhsin/Documents/GitHub/mumudevx/patina/scripts/dev/generate_folding_camera_models.gd` presses plate, shutter and door thinner by scale (L55-57, L149-157). Shader fixes: `dark_tint` for olive leather, `glass_by_coolness` for the pale-blue painted glass.
- Log: PATINA asset_log L13. Weak models are listed in `/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/later.md` L148-170:
  - `top_plate`: a thick ridged bar with no viewfinder opening;
  - `back_door`: square corners on a body with round ends;
  - `shutter`: a deep barrel where the design has a flat disc;
  - `film_spool`: a square core;
  - `body_screw`: a cross head instead of one slot;
  - `body`: wrong leather colour and an invented strip;
  - `bellows`, `winding_knob`, `shutter_release`: fine. These are good negative controls.

### T12 PATINA props: thin envelope as a parcel, and a duplicated back view
- Mailbox:
  - Root: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/props/mailbox_01/`.
  - Single-hero first try: `tripo_raw/model.glb` (P1 image_to_model, 8054 tris; "a toothed strip across its lid").
  - Second try `tripo_raw/v2/tripo-out/concept-front-e9d74cd1/model.glb` (10710; left and right views swapped, which gave a letter slot on both faces per `/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` step 3). Kept: `tripo_raw/v3/tripo-out/front-86de2355/model.glb` (11121) = `final/box.glb`.
  - Letter: `tripo_raw/_high/letter/tripo-out/front-11-db2a0d96/model.glb` (1,484,148) → `tripo_raw/_high/letter_dec2000/tripo-out/decimate-13-26db2d03/model.glb` (2000) = `final/letter.glb` = `/Users/muhsin/Documents/GitHub/mumudevx/patina/assets/models/props/mailbox_01/mailbox_01_letter.glb`. "Thick as a parcel, front sags like cloth"; pressed by scale in `ShopRoomFront.build_mailbox`.
  - Log: PATINA asset_log L16; `/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/later.md` L115-121.
- Screwdriver, rejected:
  - Concept: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/props/bench_tools_01/concept/screwdriver/_sheet.png` (viewed: hero, front and back all point the same way, so "back" is a copy, not a mirror).
  - Raw: `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/props/bench_tools_01/tripo_raw_rejected/screwdriver_two_in_one/full/tripo-out/art-source-props-bench-tools-01-396e3fb6/{model.glb (1,484,666), preview.png}` (viewed: **two screwdrivers** side by side). Reduced: `.../reduced/tripo-out/decimate-28-1a6127fe/model.glb` (1764). Replacement: `.../bench_tools_01/tripo_raw/screwdriver/`.
  - The rule is in `/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` (prop section).

Other candidates, not picked:
- glider (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/hangar/obj_hangar_glider/`, L90): the canopy came out pale green.
- `boss_hangar` keeps a rejected `model_h31_bad.glb` (18393) next to `model_h31.glb` (18570) in `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/bosses/boss_hangar/`. The reason is not logged.
- scooter (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_scooter.py`, L190): far side mirrored from the near side.
- fire hydrant (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/fix_fire_hydrant.py`, L50): smeared normals, so it is replaced by an exact cylinder with radial normals.
- spray gun (L33): the v3.1 direct result `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/equipment/spray_gun/spray_gun_v31_direct.glb` (13208, "lumpier") lost to `spray_gun_h31.glb` (5910).
- About 35 GRIME objects were "placed unfixed (owner: flaws get fixed as they show in play)", L56-91. They form an untouched pool of raw models for blind QA (e.g. `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/orbit/*/model_h31.glb`, `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/hangar/*/model_h31.glb`).

---

## 2. Pre-flight image review set (I viewed every image)

| # | verdict | path | why |
|---|---|---|---|
| R1 | GOOD | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/crew_rig/worker_apose.png` | one character in four orthographic views on one row, A-pose about 40°, empty hands, clear gaps. It passed the rig pre-check |
| R2 | GOOD, thin-part warning | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_park_bench/sheet_green.png` | four clean views. The thin parallel slats with background in the gaps should raise a warning ("expect wavy or fused slats; plan a Blender rebuild"); T1 confirms it |
| R3 | GOOD, but QA must still check the back | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_traffic_light/sheet_green.png` | the plain back is drawn, yet Tripo duplicated the lamps (T7). A good image does not guarantee a correct back |
| R4 | BAD: multi-object | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard/ref_backyard_v1.png` | 13 objects on one sheet, a style guide only. Sent to image-to-3D it fuses into one mesh |
| R5 | BAD: side views are three-quarter views | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/old/v1_sheets/jerry_can_sheet_green.png` | views 2 and 4 show the X face at three-quarters. It produced T8 g1 |
| R6 | BAD: prop occludes the head | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/depot/obj_depot_statue/v1/sheet_green.png` | the telescope crosses the face in all views, which produced a telescope through the head and a face on the back |
| R7 | BAD for rigging | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard/scene/crew.png` | the character holds a tool against the body, so the arms and tool fuse and the rig pre-check fails |
| R8 | BAD: unseen concavity | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/old/v1_sheets/pickup_sheet_green.png` | eye-level views never see into the bed, so it gets closed with a lid |
| R9 | BAD: layout and glass | `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/hangar/obj_hangar_glider/sheet_green.png` | the views sit on two rows (the auto splitter failed and the views were cut by hand), and the transparent canopy shows the chroma green, so the model's canopy is pale green |
| R10 | BAD: not orthographic | `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/folding_camera_01/concept/_rejected/body_back.png` | a "back" view that came out three-quarter (it happened 3 times; fixed by generating from `front.png` instead of the hero) |
| R11 | BAD: back copied, not mirrored | `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/props/bench_tools_01/concept/screwdriver/_sheet.png` | the result was two screwdrivers (T12) |
| R12 | BAD: resolution | `/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/tube_radio_01/tripo_raw/tuning_capacitor_512/` (+ `.../concept/tuning_capacitor/_compare_512.png`) | 512 px views gave a jumbled model (`/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md`, "Views stay at 1K") |

Suggested split for automatic tests: 3 good (R1-R3) and 5 clearly bad (R4, R5, R6, R7, R11), plus R8 and R9 as harder "warn" cases.

---

## 3. Measured facts (for planning and budget)

**face_limit is not a triangle cap in every mode** (raw tris vs requested, from `task.json` and the GLB):
- v3.1 multiview **with smart_low_poly=true** goes over the limit:
  - limit 8000 gave 7445-12175 across 20 GRIME objects;
  - tool_chest g1 gave **17430**;
  - pedal_car gave 12367 for a 10000 limit.
  - Paths: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/backyard_v2/tripo/*/tripo-out/*/task.json` and `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/garage/tripo/*/tripo-out/*/task.json`.
- v3.1 without slp, and P1, stay under the limit: 2834/4000, 5456/6000, 18476/20000, 7364/8000.
- No limit gives 1.31M-1.93M tris, 42-64 MB GLB.
- `tripo mesh decimate` (the task type is `highpoly_to_lowpoly`):
  - v1.0 (10 credits) hits the target ±2;
  - v3.0 --smart-uv (35 credits) lands at 0.69-1.02× the target;
  - **v2.0 (30 credits) overshot 20000 → 29943**.
- Higgsfield H3.1 with face_limit 8000 gave 6286-7767, under the limit.

**Credits seen in `task.json` (`credits_consumed`):**

| task | credits |
|---|---|
| P1 image/multiview | 50 |
| v3.1 multiview, standard | 30 |
| v3.1 + slp + texture detailed | 50 |
| v3.1 geometry + texture detailed | 60 |
| texture_model (retexture) | 20 |
| decimate v1.0 / v2.0 / v3.0 | 10 / 30 / 35 |
| animate_prerigcheck | 0 |
| animate_rig | 25 |
| Higgsfield statue | 16 per the log |

**Texture and file size:**
- GRIME runs `pbr=false`: 1 JPEG image per GLB, raw 1.5-3 MB, cleaned to 1K at 0.24-0.7 MB.
- PATINA keeps PBR on: 3 images (Color jpg, NormalGL png, ORM jpg) per GLB, shipped as-is at 1.3-5.6 MB, plus loose texture files in `/Users/muhsin/Documents/GitHub/mumudevx/patina/assets/models/antiques/desk_clock_01/`.

**Raw → fixed triangles (GRIME Blender fixes change the count only a little):**

| object | raw | fixed |
|---|---|---|
| park bench | 7104 | 7343 |
| statue | 7646 | 7178 |
| bus stop | 6286 | 4983 |
| fire hydrant | 7752 | 7744 |
| traffic light | 7767 | 7765 (wrong-side attempt: 5851) |
| tool chest g3 | 9327 | 9780 |
| scooter | 9981 | 10776 |
| engine block | 10274 | 9437 |
| pickup g2 | 9625 | 9687 |
| jerry can g3 | 10567 | 10533 |
| pedal car | 12367 | 11213 |
| rigged worker (topology unchanged) | 7884 | 7884 |

---

## 4. GENERAL lessons (any game, any engine)

1. **One object per image; four orthographic views, each its own file; never a sheet.** Multi-object sheets fuse into one mesh (R4). Sources: `/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` step 5; `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/gdd/07-ai-asset-pipeline.md` §7.2.
2. **Multiview beats a single image.** Single images leave the hidden sides to chance: the mailbox's toothed lid (T12), the Pool's pink inner wall (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/decisions.md` L259), the bicycle's teeth and slivers 2.5% → 0.8% (T9).
3. **Pre-flight checklist derived from the failures:**
   - side views must be truly orthographic (R5, R10);
   - left and right named by Tripo's convention, so in `left.png` the front points to the left edge (the mailbox slot appeared on both faces);
   - a back view of a lying, rotationally same part must be a mirror, not a copy (R11);
   - no prop overlapping head or torso (R6);
   - characters to be rigged need an A-pose, empty hands and visible gaps (R1 vs R7);
   - open cavities need a view into them (R8);
   - views on one row; no transparent parts over a chroma background (R9);
   - at least 1K resolution (R12);
   - the file's real format: about 18% of ".png" inputs in both projects are JPEG bytes. Check magic bytes; PATINA's CLAUDE.md says the views should be PNG.
4. **A good reference does not guarantee a good back or far side.** Tripo copies front detail onto the back (traffic light, engine block, tool chest) and botches the far half (scooter, tool chest handle). QA must render all sides, not only `preview.png`. Sources: `/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` step 7; `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/qa_models.py`.
5. **Thin parts are the main failure class:** slats (T1), plates (top_plate, back_panel), envelopes (letter), glass (dial_glass), discs on the ground (pedal car), spokes (T9).
   - Pre-flight should warn when a part is thinner than about 5% of its length.
   - Cheap fixes: press by scale in the engine or rebuild in Blender.
   - Paid fix: no-limit generation plus v3.0 decimation.
6. **Do not trust face_limit; measure the GLB** (section 3). Never use smart_low_poly or decimate v2.0 if a hard budget matters. For hard-surface parts with holes: generate without a limit, then `tripo mesh decimate --model v3.0 --smart-uv` (30 + 35 credits). v1.0 decimation keeps a mismatched normal map that bends and creases flat parts (T10). Source: `/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` "mesh recipe".
7. **Fix ladder (cheapest first):**
   1. engine-side scale, shader or material change (PATINA);
   2. headless Blender script (GRIME `fix_*.py`);
   3. `tripo model texture` retexture for colour problems on a good mesh (20 credits; GRIME garden bench, lawn mower, pedal car);
   4. a new generation (30-60 credits) only for broken geometry.
   - Re-roll budget: 2 per object (`/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` step 7). The jerry can took 3 (T8).
8. **Blender fix toolbox that recurs in GRIME** (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/mesh_fix.py`, `fix_common.py`, `keep_normals.py`):
   - weld the UV-seam splits on load;
   - `flatten_face` for wavy planar faces;
   - Taubin smoothing for lumps;
   - mirror the good half of a symmetric object;
   - delete by region, then fill the holes;
   - repaint the texels of chosen faces;
   - flat shading for flat decals;
   - **keep Tripo's normals wherever the fix did not move vertices** (recomputed smooth normals expose hidden waves);
   - delete coplanar leftover faces (z-fighting rings).
9. **Use QA metrics as gates:** triangle count, sliver share (triangles whose area is under 2% of their longest edge squared; flag above 3%, `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/qa_models.py` L28, `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/qa_render.py` L7), the lowest point per third of the footprint (floating or sunk wheels), and L/R symmetry difference. Render 4 sides plus iso with edges, next to the reference views.
10. **Rigging:** run `animate_prerigcheck` first (0 credits), then `animate_rig` biped (25 credits). The output has 27 joints named `tripo::...` and no animations. The clean-up drops the helper icosphere and must not touch transforms. In Godot, bone names become `tripo__...`.
11. **Orientation is unreliable:** the front must be decided from a feature (visors, hose outlet, bow), not from Tripo's +X. GRIME had to use yaw −90, 90, 0 or 180 per object (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/place_refs.sh`), and one fix was applied to the wrong side (T7).
12. **Money hygiene** (`/Users/muhsin/Documents/GitHub/mumudevx/patina/CLAUDE.md` step 6):
    - exit 4 means out of credits: stop;
    - exit 6 with timeout means the task is still running: `tripo task watch <id> --download`, never resubmit;
    - exit 7: check the balance first;
    - failed or cancelled tasks are not charged;
    - `generate` has no `--dry-run`, so read the balance before and after.
13. **Always pass a label** so `tripo-out/<label>-<id>` pairs with its asset, and keep the CLI's `.tripo/` state out of the repo, or run from `art_src`.

## 5. PROJECT-SPECIFIC lessons (do not promote without approval)

GRIME (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay`):
- Budgets and settings: class A ≤ 8k tris (in practice `--max-tris 12000`), bosses ≤ 30k, 1 mesh / 1 material / 1K JPEG, `pbr=false`. Style formula: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/style/style_formula.txt`.
- References are chroma-green sheets split by `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/key_views.py`, with a left/right dedup step in `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/art_src/refs/make3d.py`.
- Placement: `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/place_model.py` rewrites `scenes/objects/.../<id>.tscn` as a wrapper with the GLB instanced as `Model`. Then the silhouette re-bake (`scripts/dev/bake_silhouette.gd`) is mandatory, followed by `check_import.sh` and the tests.
- The default yaw is −90 because Tripo models face +X.
- Since 2026-10-30 the owner's rule is "placed unfixed, fixed as flaws show in play".
- Colour drift: Tripo lost about 25% saturation versus the concepts (`/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/decisions.md` L260).

PATINA (`/Users/muhsin/Documents/GitHub/mumudevx/patina`):
- Budgets: 3k-12k tris per part and 40k-60k per antique (`/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/decisions.md` L426).
- Model choice: `tripo-v3.1` for every antique part; P1 only for far background pieces. PBR stays on.
- Never set quad, smart_low_poly, generate_parts, auto_size or orientation.
- geometry/texture "detailed" is not used: it doubles the credits and turns printed detail into lumps.
- Reference images: Gemini `gemini-3.1-flash-image` at 1K, with a `parts.json` manifest driving `/Users/muhsin/Documents/GitHub/mumudevx/patina/scripts/dev/asset_concepts.py`; plain white background, not chroma.
- GLBs ship untouched. All fixes happen in GDScript generators (`generate_*_models.gd`, `ModelKit`, `mesh_reducer.gd`, `NO_NORMAL_TEXTURE`, scale presses, `antique_master.gdshader` `dark_tint` / `glass_by_coolness`), and turnarounds are rendered by `/Users/muhsin/Documents/GitHub/mumudevx/patina/scripts/dev/model_turnaround.gd`.
- Desk clock parts came from Higgsfield H3.1 single images (`/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/antiques/desk_clock_01/higgsfield_raw/`). The rule for a multi-part object: every part, even plain ones, is generated against one reference sheet (`/Users/muhsin/Documents/GitHub/mumudevx/patina/docs/decisions.md` L84).

## 6. Gaps and caveats
- The rig pre-check verdicts are not stored in `task.json`; the pass/fail comes from `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/docs/decisions.md` L291.
- The reason `boss_hangar/model_h31_bad.glb` was rejected is not recorded.
- `model_h31.orig.glb` and `model_h31.glb` have the same triangle count in the samples I checked; `.orig` looks like a pre-edit backup.
- GRIME's `refs/` models came through Higgsfield, not tripo-cli, so their provenance lives in `job3d.json` (`params.face_limit` etc.), not `task.json`.
- I did not compute sliver percentages myself; the numbers above are from the asset log. To compute them, port `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay/tools/blender/qa_render.py` L78-110.
