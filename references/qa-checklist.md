# QA checklist: measure, render, look, report

When to read this: phase 5 (measure + render + QA) after every generation, every paid fix and every Blender fix; and when the user asks to check a GLB/FBX from Tripo.

QA costs 0 credits and runs without asking. It has three parts: numbers (`qa.py`), one picture (`render_sheet.py`), and the agent's eye on that picture. Fix options per code are in `fix-tradeoffs.md`.

## 1. Run order

```
python3 scripts/glbstat.py raw/<label>/model.glb
python3 scripts/bl.py qa.py -- raw/<label>/model.glb --budget 15000 --front -y --symmetric x --ref-palette refs/front.png --class large_prop
python3 scripts/bl.py render_sheet.py -- raw/<label>/model.glb --png qa/raw/sheet.png --front -y --game-cam "35,30,50" --light-sweep
```

- `glbstat.py`: stdlib quick look (`tris`, meshes, materials, images with sizes, skins, joints, animations). GLB/glTF only; FBX/OBJ get `format` and a pointer to `qa.py`.
- `qa.py` (through `bl.py`): GLB, GLTF, FBX and OBJ by magic bytes (quad and some rig outputs arrive as FBX). Output `{"schema": "qa/1", "file", "format", "class", "metrics", "findings"}`; each finding has `id`, `code`, `severity`, `message`, `value`, `threshold`, `fix_options` (a `BACK_COPY` on an unconfirmed front also has `"tentative": true`).
  - `--budget N` is the only budget input: take it from `profile.json` `budgets[class]`. `--class` is recorded, not looked up.
  - `--front -y|+y|-x|+x` (default `-y`, which is glTF +Z, Tripo's nominal front). Both `--front -x` and `--front=-x` work.
  - `--front-confirmed`: the user confirmed `--front` (`front_confirmed` in the metrics). Leave it off until the front is confirmed.
  - `--symmetric x` turns on the asymmetry metric (mirror across world X); `none` (default) skips it.
  - `--ref-palette <png>` compares the texture to the reference colours (`PALETTE_DRIFT`).
- `render_sheet.py`: one PNG, long side at most 1500 px. Rows: `lit`, `lit_no_normalmap` (normal maps cut), `albedo` (flat base colour), `wire`. Columns: front, back, left, right, top, iso, plus `game_cam` with `--game-cam "<yaw>,<pitch>,<fov>"` (from `profile.json` `game_camera`). `--light-sweep` adds 4 iso renders with the key light at 0/90/180/270 degrees. Overlay: a red arrow out of the front face, a ground grid (1 m, or 0.1 m / 0.01 m for small models) and a header with file name, triangle count, front axis and grid size.
- Save `qa.json`, `sheet.png` and the report in the folder named after the model checked: `qa/raw/` for the raw output, `qa/vNN/` for `work/vNN` (`apply_recipe.py` prints it as `qa_dir`; never the next free number), and append a short summary to the asset state: `asset_state.py update <project> <id> --phase qa --append qa=<json>`.
- Blender failures never pass silently: `bl.py` exits non-zero (4 internal, 3 missing input, 2 usage) and leaves no stale result.

## 2. The front axis comes first (spec 12)

- Raw Tripo outputs often face +X, not glTF +Z: about 10% of models came back with the front reversed, and one fix was applied to the wrong side. The front is decided from a feature (a door, a visor, a hose outlet, a face), never from Tripo's axes.
- `--symmetric x` mirrors across world X. On a raw model whose left/right axis is world Y (tool chest, pickup, pedal car and the A-pose worker all were), the "asymmetry" compares front with back and means nothing. Turn the model first (`normalize.py --yaw`, see `fix-tradeoffs.md`) or read the metric as unreliable.
- `back_relief` (`BACK_COPY`) depends only on the axis (X or Y), not on its sign, so qa.py reports both: `back_relief_x` and `back_relief_y`; `back_relief` is the one on the `--front` axis. A wrong axis compares the left and right sides, which correlate near 1 on a left/right-symmetric prop (tool_chest_g3 faces +X: `back_relief_x` 0.997, `back_relief_y` 0.20).
- Until `--front-confirmed` is passed, `BACK_COPY` is tentative: info, `"tentative": true`, fired when either axis exceeds `back_relief_max`. After the front is confirmed it uses the confirmed axis only, at the calibrated severity.
- Confirm the front with the user as one line inside the first QA report, suggested from a feature ("Kapı bu tarafta görünüyor, ön bu mu?"). It is not a separate question. Record the answer in `decisions`; later runs pass the confirmed `--front` and `--front-confirmed`. When the answer sets or changes the front, re-run QA and re-preview every side-specific fix before applying any of them (SKILL.md section 4); an unchanged default `-y` on a raw Tripo output may proceed.

## 3. Severity

| level | meaning |
|---|---|
| `S0` | broken: unusable in game or pipeline (rig, collision, import) |
| `S1` | visible in game |
| `S2` | cosmetic |
| `info` | did not pass calibration (agent-eye), or just above a limit: reported, never blocks, never decides on its own |

`scripts/data/qa_thresholds.json` `"qa"` holds the thresholds and a severity per code. A code at `info` did not pass calibration (spec 12: guessed thresholds do not ship): its finding is a lead for the agent's eye, never a verdict. Calibration (`docs/calibration-2026-10-31.md`, 159 direct Tripo outputs, labels in `tests/calibration_labels.json`) lets a code ship only if it catches every labelled positive and stays silent on every labelled clean case; only the two rules below passed. `OVER_BUDGET` is computed (`rule`): info above 1.0 x the budget, S1 above 1.1 x, S0 above 2 x. `TOO_MANY_INFLUENCES` ships at S1 (4 weights per vertex is the engine skinning default). Severity also depends on use: an open edge matters for a rig, collision or LOD, much less for a static background prop.

## 4. Code catalogue

Topology metrics run on a welded copy (Tripo splits vertices at every UV seam; the weld epsilon is 1e-5 x the bbox diagonal). `boundary_edges_raw` is the count before the weld, for comparison. Normals, slivers, UVs and textures are read from the loaded data, which is never modified.

| code | measures | threshold key (current) | detection notes |
|---|---|---|---|
| `OVER_BUDGET` | triangles vs `--budget` | `over_budget_s1` 1.1, `over_budget_s0` 2.0 | the gap between the requested `face_limit` and the result is normal (B8) |
| `NON_MANIFOLD` | edges shared by 3+ faces after the weld | `nonmanifold_edges_max` 0 | matters for rig, collision, LOD, baking; info, agent-eye: no labelled positive (57% of the corpus fires) |
| `HOLES` | open (boundary) edges after the weld | `boundary_edges_max` 0 | a high `boundary_edges_raw` with few after the weld is just seams; info, agent-eye: no labelled positive (79% of the corpus fires) |
| `LOOSE_PARTS` | separate pieces under `loose_tris_pct` 1.0% of the triangles each | `loose_parts_max` 0 | `islands` lists the 32 largest, `island_count` all; real separate parts (wheels, lids) are not defects: check on the sheet; info, agent-eye: jerry_can_g2's extra handles are fused, so it measures 0 |
| `FLIPPED_NORMALS` | % of triangles winding against their stored normals | `flipped_pct_max` 0.5 | Tripo normals are never recomputed globally (B7); info, agent-eye: no labelled positive |
| `SLIVERS` | % of triangles with a corner under 5 degrees | `sliver_pct_max` 3.0 | info, agent-eye: bicycle_v1 8.0 vs bicycle_v2 2.7, but clean decimated parts measure 22 to 24 |
| `GROUND_SLAB` | a thin connected sheet in the bottom 3% of the height spanning 60% or more of the footprint with upward faces over 25% of it | boolean | the ground line or plate in the reference; info, agent-eye: the pedal-car discs are fused into the tyres and raise no flag |
| `NOT_GROUNDED` | % of triangles in the bottom 3% of the height | `low_band_tris_pct_min` 0.1 | the model rests on a point (tilted, floating wheels); info, agent-eye: no labelled positive |
| `ASYMMETRY` | mean distance of X-mirrored vertices to the surface, % of the diagonal | `asymmetry_pct_max` 0.1 | needs `--symmetric x` and a model turned to face -Y; info, agent-eye: tool_chest_g1 (turned) 0.27, but the clean bellows measures 0.40 from its pleat relief |
| `BACK_COPY` | similarity of front and back relief (0 to 1) | `back_relief_max` 0.8 | info, agent-eye: missed the tool chest (0.07) and engine block (0.45) copies, while round parts measure 0.999 |
| `UV_OVERLAP` | % of used UV texels covered by more than one triangle | `uv_overlap_pct_max` 1.0 | deliberate mirrored UVs also overlap; info, agent-eye: no labelled positive |
| `LOW_TEXEL` | median texel density, px per model unit | `texel_density_min` 256 | compare with `profile.json` `texel_density` when set; info, agent-eye: no labelled positive |
| `PALETTE_DRIFT` | mean delta E between texture and reference palette | `palette_delta_e_max` 10.0 | needs `--ref-palette`; about 25% saturation loss was measured before; info, agent-eye: no labelled positive |
| `BAKED_LIGHT` | correlation of albedo brightness with upward normals | `baked_light_max` 0.35 | also look at the light-sweep row: baked light does not move with the key light; info, agent-eye: no labelled positive (clean metal knobs measure 0.6) |
| `TOO_MANY_INFLUENCES` | most bone weights on one vertex | `influences_max` 4 | rigged models only; S1 |
| `MULTI_MATERIAL` | material count | `materials_max` 1 | 1 material per prop is the draw-call rule; glass may need a second; info, agent-eye: no labelled positive |
| `TEXTURE_OVERSIZE` | largest texture side | `texture_max_px` 2048 | fixed at export (`export.py --max-texture`), not a generation problem; info, agent-eye: no labelled positive |

Extra metrics with no code: `tris`, `verts`, `verts_welded`, `meshes`, `images` (name, w, h), `bbox` (min, max, size in Blender axes, Z up), `uv`, `palette.chroma_ratio`, `skin.joints`.

## 5. Agent-eye checks on the render sheet

Look at the whole sheet every time; several known defects have no reliable number yet.

- **Back copied from the front**: front details (lamps, drawers, a face, handles) repeated on the back or far side; a far half that is botched while the near half is fine (scooter, tool chest handle).
- **Closed cavities**: an open bed, drawer or interior that came back closed or lidded (pickup bed, R8). No automatic code: agent-eye only.
- **Extra or missing parts**: a third handle (jerry can g2), a duplicated object (two screwdrivers from a copied back), a missing leg.
- **Fused parts**: a prop grown into a hand or torso; wheels fused to the body; slats merged.
- **Thin parts made thick or wavy**: slats, plates, glass panes, spokes, discs (`lit` and `wire` rows).
- **Normal-map dents**: compare `lit` with `lit_no_normalmap`. Dents or waves that appear only in one of them come from the normal map or from recomputed normals; most past "dent" complaints were normal-related.
- **Baked lighting**: dark undersides or bright tops in the `albedo` row; shading that stays fixed across the light-sweep row.
- **Wrong front**: the red arrow does not point out of the face the user would call the front.
- **Scale and grounding**: model size against the grid and the placeholder size (`godot.md`); floating or sunk wheels.
- **Game camera**: what the player actually sees (`game_cam` column) decides how much a defect matters.

## 6. Report to the user (K10, spec 13)

- On screen: 2 or 3 Turkish lines, one table, one batched question. Details go to `qa/vNN/report.md`.
- The first line of the first QA report carries the front confirmation (section 2).
- Table columns: `# | sorun | ciddiyet | A (Blender, 0 kredi) | B (Tripo, kredi) | öneri`. One row per real problem, most severe first; `info` rows only when they matter for this asset.
- One question for all rows, answered like "1A, 2B, 3 geç". Free fixes are prepared as a preview without asking; applying them is part of the batched answer.

Example:

```
Ham model 17.430 üçgen (bütçe 15.000), arka yüzde ön detay kopyası var. Kapı bu tarafta, ön -Y mi?
| # | sorun | ciddiyet | A | B | öneri |
| 1 | arka yüzde ön kopyası | S1 | flatten_region (geometri düzelir, boya kalır) | retexture 10-30 | B |
| 2 | bütçe aşımı 1,16x | S1 | - | decimate v3.0 35 | B |
Hangileri? (ör. "1A, 2B")
```

## 7. After every fix

Run QA and the render sheet again on the new version (in its own `qa/vNN/`, the `qa_dir` of the `work/vNN` it checks) and compare before and after: the fixed finding should be gone and no new finding should appear (cleanup can create defects: a coarse weld once raised non-manifold edges from 1.8k to 20k in another tool's pipeline).

## 8. Known cases (direct Tripo outputs, `tests/fixtures.json`)

| fixture | known defect | caught by |
|---|---|---|
| `tool_chest_g1` | lopsided, front detail on the back, 17430 tris for 8000 | `OVER_BUDGET` S0; asymmetry and back copy: agent-eye |
| `tool_chest_final` | mirrored-half fix | clean (asymmetry 0.011, not a calibration label) |
| `pedal_car_raw` | 12367 tris for 10000, ground discs | `OVER_BUDGET` S1; discs: agent-eye |
| `pickup_g2` | bed closed with a lid | agent-eye only |
| `jerry_can_g2` | three handles | agent-eye (fused, `LOOSE_PARTS` 0) |
| `bicycle_v1` / `bicycle_v2` | slivers, teeth / clean | agent-eye (`SLIVERS` info) / clean |
| `back_panel_v2_20k` | 29943 tris for 20000 (decimate v2.0) | `OVER_BUDGET` S1 |
| `engine_block_g1` | belt and pulleys copied onto the back | agent-eye (`BACK_COPY` 0.45) |
| `crew_rigged` | 27 joints, 1 skin, `tripo::` names | `TOO_MANY_INFLUENCES`, `godot_place.py rig_accept` |

Clean controls: `bellows`, `winding_knob`, `shutter_release` (patina, shipped as generated) and `bicycle_v2` raise no shipping code. Codes at `info` failed calibration on this corpus: they are leads for the agent's eye, not verdicts. Re-run `scripts/calibrate.py` when new labelled cases arrive.
