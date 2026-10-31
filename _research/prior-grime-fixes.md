# Prior art: grime-does-pay Blender fix scripts — defect catalogue

Source repo (read-only): `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay` (all paths below are relative to it).
Scope read: every `tools/blender/fix_*.py` (24 files; `fix_common.py` and `fix_anchor.py` read too, anchor included as a data point), their shared kit (`tools/blender/mesh_fix.py`, `mesh_paint.py`, `keep_normals.py`, `fix_common.py`), the placement/cleanup steps (`tools/place_model.py`, `tools/blender/clean_model.py`, `tools/place_refs.sh`), QA (`tools/blender/qa_render.py`, `tools/qa_models.py`), `docs/asset_log.md`, `docs/gdd/07-ai-asset-pipeline.md`, `art_src/refs/make3d.py`, a sample of `art_src/refs/*/*/sheet_green.prompt.txt`.

---

## 0. TL;DR for the skill

1. **Every fix was triggered by owner visual review**, never by an automatic check (each script docstring starts "Owner review 2026-10-2x: …"). QA only produced renders + three numbers (tris, sliver %, lowest point per footprint third) — `tools/blender/qa_render.py:1-8`, `tools/qa_models.py:1-30`. The skill's headless QA should add automatic detectors for the defects below (section 4) so the review is pre-filled.
2. **~60% of fixed defects are "multiview hallucinations of the hidden side"**: front details copied onto the back, the far side misshapen, one side missing a part, a closed lid over a cavity no view sees into. These come from the reference sheet, not from Tripo settings, and are cheapest to prevent in the sheet prompt (explicitly describe the back and inside) and by reviewing the sheet's back/side views before spending 3D credits.
3. **The second big class is Tripo "wrinkles"**: flat faces wobble by 3–6 mm and smooth normals turn this into streaks/dents; Tripo also **paints those wrinkles/shadows into the albedo**. Fix = press faces onto fitted planes/cylinders/spheres + set custom normals + even out the albedo. All parametric.
4. **Normals policy is the single most reused lesson**: never let Blender recompute all normals after an edit — Tripo's exported normals hide wrinkles that recomputed smooth normals reveal. Keep exported normals on untouched geometry, write analytic normals (flat / radial / spherical) on fixed geometry (`tools/blender/keep_normals.py:1-11`, `tools/blender/fix_common.py:1-8`).
5. Fix scripts are 30–244 lines each with **hard-coded metre constants measured on the placed model** (e.g. `BACK_Y, BACK_X, BACK_Z = 0.26, 0.50, (0.145, 0.778)` in `tools/blender/fix_bus_stop.py:25`). They work but are one-off. ~10 parametric operators cover nearly all of them (section 3).

---

## 1. Generation context (from `docs/asset_log.md`)

Three generation pipelines were used; defect profile differs by pipeline.

| Pipeline | Settings (as logged) | Assets fixed by a fix_*.py | Notes |
|---|---|---|---|
| **A. Tripo P1 single image** (2026-10-26) | `image_to_model face_limit 8000, pbr off`, 50 credits; bosses face_limit 20000 (`docs/asset_log.md:11-23`) | boss_backyard (`fix_pool_pink.py`) | One three-quarter image → hidden sides guessed. Pool: float's pink projected onto the hidden inner wall (`tools/blender/fix_pool_pink.py:5`). Slivers 1.5–17.6% (`tools/qa_models.py` SLIVER_FLAG_PCT comment). Most P1 backyard objects were later replaced by pipeline B. |
| **B. Tripo v3.1 multiview via tripo-cli 0.6.1** (2026-10-27/28) | `multiview_to_model smart_low_poly, face_limit 8000 (pedal car 10000, boss 20000), pbr off, texture_quality detailed`, `texture_alignment geometry` (backyard v2) or `original_image` (garage); 50 credits; views = Gemini turnaround on chroma green `#00B140`, keyed to RGBA (`docs/asset_log.md:34-41, 190-202`) | flower_pot, pedal_car, bbq_grill, birdhouse, scooter, tool_chest, hatchback, engine_block, jerry_can, pickup | Slivers dropped to ~0.6–0.9% vs P1 (`docs/asset_log.md:34-35,39`). `texture_prompt` not accepted on multiview; a separate `texture_model` retexture costs 20 credits (`docs/asset_log.md:37-39`). |
| **C. Higgsfield `tripo_h3_1_multiview_to_3d`** (2026-10-29/30) | `texture_quality detailed, texture_alignment original_image, pbr false, face_limit 8000` (bosses 20000 + `geometry_quality detailed`), 12 Higgsfield credits; sheet = nano_banana_pro 4 ortho views + 4 close-ups on chroma green, 4 credits (`art_src/refs/make3d.py:43-46`, `docs/asset_log.md:42-91`) | bus_stop, fire_hydrant, mailbox, park_bench, parking_meter, phone_booth, statue, traffic_light, vending_machine, wheelie_bin, anchor | 10 of 12 depot objects needed a fix (fountain, road_barrier did not). All later shipyard/hangar/orbit/boss models were "placed unfixed (owner: flaws get fixed as they show in play)" (`docs/asset_log.md:56-91`, `tools/place_refs.sh:31`). |

Remakes (regeneration chosen over fixing) — useful for the "free Blender fix vs paid Tripo redo" decision:
- jerry_can: 2 rejected (first **sheet** drew side views as three-quarter views of the X face; second **model** had three handles and a second cap), 100 credits wasted, third kept + crack fix (`docs/asset_log.md:199`).
- tool_chest: 2 rejected, 100 credits; third from a "simpler reference" (`docs/asset_log.md:194`, `tools/blender/fix_tool_chest.py:5`).
- pickup: first had rear window glass running down onto the bed (`docs/asset_log.md:200`).
- go_kart: first missing the yellow steering wheel ring → remade, no fix (`docs/asset_log.md:193`).
- statue: v1 had the telescope through the head and a face on the back (16 credits); prompt rewritten to describe the back view explicitly; v2 still got an extra hand → telescope deleted in Blender (`docs/asset_log.md:46`, `tools/blender/fix_statue.py:5-10`).
- crew_worker: first model had the lance fused to the hands → not riggable; regenerated "holding NOTHING", A-pose, prop made as a separate model (`docs/asset_log.md:25`).
- Retexture as a fix: garden_bench and lawn_mower got a 20-credit `texture_model` retexture with `texture_alignment original_image` + texture_prompt (worked); pedal_car retexture "came out worse and is not used" (`docs/asset_log.md:37-39`). birdhouse got its wood grain procedurally in Blender for free instead (`tools/blender/fix_birdhouse.py:9-10`).
- Unfixed known defects accepted: eq_washer "front panel came out blue instead of orange" (`docs/asset_log.md:26`); glider "canopy came out pale green (the chroma green showed through the glass in the sheet)" (`docs/asset_log.md:90`); wheelie_bin "slight waves left on the lid's round corners" (`docs/asset_log.md:49`).

Pipeline order every fix assumes: raw GLB → `clean_model.py` via `place_model.py` (join to one mesh, decimate to budget, yaw so front faces −Y, scale to height, origin at base centre, one material, 1K JPEG) → `fix_<id>.py in.glb out.glb` on the placed output (`tools/place_refs.sh:12-18`, docstring line "Run after tools/blender/clean_model.py (--yaw -90, front toward −Y), on its output" in every depot fix). So all fix constants are metres in the canonical game frame (Z up, front −Y, base at z=0).

---

## 2. Defect catalogue

Format per defect: **assets** · **how detected** · **bpy recipe (exact)** · **generalizable?** · **generation-time cause**.

### D1. Front detail copied onto the back (multiview back-face hallucination)
- **Assets**: engine_block (belt + pulleys on back), tool_chest (four drawers + pulls on back), traffic_light (lamps on both faces), phone_booth (door handle copied onto back wall). `tools/blender/fix_engine_block.py:5-7`, `fix_tool_chest.py:8-10`, `fix_traffic_light.py:5-8`, `fix_phone_booth.py:5-8`.
- **Detected**: owner looking at the back render. Traffic light: the real front is "the face whose lamps have visors", so it was also placed with `--yaw 90` (`fix_traffic_light.py:5-7`).
- **Recipe A — press relief into the back plane** (engine_block, tool_chest):
  1. Back plane depth = most populated depth layer of back-facing geometry: `np.unique(np.round(co[facing,1],2), return_counts=True)`, take the nearest layer with >50 verts (engine) or the argmax (tool chest), then median of verts within 6–15 mm (`fix_engine_block.py:31-35`, `fix_tool_chest.py:72-74`).
  2. Verts in the back region box (inside side walls, within height band) with `y > plane_y + PROUD (8 mm)` → `co[:,1] = plane_y`; `Model.move(co, moved)` (fresh smooth normals only on moved verts) (`fix_engine_block.py:36-38`, `mesh_paint.py:55-69`).
  3. **Delete inner faces left coplanar** — they z-fight "as rings under light": faces on the plane with `normal.y < 0.5 or area < 1e-7` → `bmesh.ops.delete(context="FACES_ONLY")` (`fix_engine_block.py:39-50`, `fix_tool_chest.py:79-90`).
  4. Paint: median texel colour of plain back faces → `recolour(px, grow(raster(back), 2–3), colour, spread=0.0)`; tool chest picks texels by **3D position** (`raster(with_pos=True)`) and also samples 9 points along each UV edge of sliver faces because "sliver faces cover no texel centre" (`fix_tool_chest.py:97-107`).
  5. Custom normals `(0,1,0)` on all back-plane loops (`fix_engine_block.py:60-64`).
- **Recipe B — delete the copied part, cap, flatten** (traffic_light, phone_booth):
  1. Back limit = 99th percentile of side-wall verts' y + 4 mm; delete faces with any vert beyond it (`fix_traffic_light.py:37-41`). Phone booth: verts > 6 mm out of the wall in a z band (`fix_phone_booth.py:47-52`).
  2. Close holes with `fill_loops(m, vmask, uv, outward)` (custom boundary-loop walker, because `bmesh.ops.holes_fill` "skipped a hole of the traffic light") (`fix_common.py:56-96`).
  3. `flatten_face((0,1,0), box, tol=0.006)` then press remaining relief up to 20 mm deep inside a 25 mm edge margin (`fix_traffic_light.py:45-53`).
  4. Paint back faces `texels=3–4, spread=0` (also kills baked shadow of the handle — `fix_phone_booth.py:62-64`). **Fill triangles all share one UV point** → reassign them to the UV centre of the largest freshly painted face (degenerate UV area ≤ 1e-6) (`fix_traffic_light.py:58-67`, `fix_phone_booth.py:65-73`).
  5. Flat normals on the plane; pop those triangles from the "keep original normals" dict so they don't get the old lamp normals back (`fix_traffic_light.py:69-75`).
- **Generalizable**: YES — `flatten_back(axis, region_box, proud, colour_sample_region, mode=press|delete)`. Inputs the user/agent must give: which axis is "back", region box (can come from bbox + margin), mode.
- **Generation cause**: sheet back view either showed the detail or was ambiguous; multiview model copies front features. Statue v2 prompt adds an explicit back-view sentence: "The back view shows only the back of the coat … no face, no nose, no eyes and no telescope end on the back" (`art_src/refs/depot/obj_depot_statue/sheet_green.prompt.txt`). Tool chest's third sheet said "plain sides and back" yet drawers still appeared on the back (`docs/asset_log.md:194`) → prompt alone is not enough; QA must check the back.

### D2. Hidden/far side misshapen or a one-sided part (asymmetry) → mirror the good half
- **Assets**: scooter (far side: mirror disc floating 25 cm behind handlebars, narrow slanted panel, body fold), tool_chest (only +X got its side handle) (`fix_scooter.py:5-8`, `fix_tool_chest.py:6-7`). Related: pedal_car wheels (one clean wheel copied to the other three axles) (`fix_pedal_car.py:12-14`).
- **Detected**: owner review of side renders.
- **Recipe — mirror half** (`fix_scooter.py:30-61`, `fix_tool_chest.py:35-66`):
  1. Symmetry plane from a reliable sub-part's bbox (scooter: tyres below 10 cm, "Tripo's model is a little off y = 0"; tool chest: body below the handle because "the handle makes the bounds lopsided").
  2. Keep faces with **any** vertex on the good side (`min(y) <= mid` / `max(x) >= mid`) — "faces reaching the plane stay too, so the two halves overlap a little instead of leaving a gap" (no weld).
  3. Mirrored copy: `v' = 2*mid − v` on the axis; **reverse vertex order** per face ("mirroring flips the winding"); copy UVs in reversed loop order; copy corner normals in reversed order with the axis component negated.
  4. `me.clear_geometry(); me.from_pydata(...)`; new UV layer; `use_smooth=True`; `normals_split_custom_set(loop_n)`.
- **Recipe — clone a good part** (pedal car, `fix_pedal_car.py:59-121`): pick the instance with the fewest defects (fewest fused disc faces), delete the others' faces (non-red within 1.06×radius of each axle), add translated (and Y-mirrored with reversed winding) copies with source UVs and source Tripo normals, `remove_doubles(dist=1e-5)`.
- **Generalizable**: YES — `mirror_half(axis, plane_from=region|bbox|value, keep_side)` and `clone_part(selection, transforms)`. Caveat: mirrors asymmetric decals/text too; both halves share texels (fine for flat-colour style).
- **Generation cause**: side views in the sheet were not true mirrors (spray-gun sheet: "the drawn right view was a copy of the left one, mirrored", `docs/asset_log.md:33`); sheets later demand "the left and right side views are exact mirror images" (`art_src/refs/depot/obj_depot_traffic_light/sheet_green.prompt.txt`). Far side (away from game camera) gets least scrutiny.

### D3. "Tripo wrinkles" on flat faces (geometry noise 3–6 mm → streaks under smooth normals)
- **Assets**: mailbox (front around slot/door, side panels), vending_machine (back + coin panel), wheelie_bin (lid top, raised panel, chamfers, lid sides, rim), birdhouse (gable walls), pedal_car (body sides), phone_booth (back wall), park_bench (wavy slats) (`fix_mailbox.py:5-7`, `fix_vending_machine.py:5-7`, `fix_wheelie_bin.py:5-13`, `fix_birdhouse.py:6-8`, `fix_pedal_car.py:15-16`).
- **Detected**: owner review ("dents", "bumps", "bright streaks"). Docstrings note "Tripo's wrinkles reach about 6 mm" (`fix_mailbox.py:20`).
- **Recipe — `Mesh.flatten_face(axis, weight, tol=0.008, angle=35, depths=None, min_share=0.12)`** (`tools/blender/mesh_fix.py:135-172`):
  1. Facing faces = in weight region and `n·axis > cos(35°)`.
  2. Depth layers = area-weighted histogram of face-centre depth along the axis (2 mm bins); take peak, average depths within 3 mm, accept layer if it holds ≥ `min_share` of facing area; remove band within `tol`; repeat. This finds "a box face and a door raised on it" as separate layers.
  3. Verts of facing faces within `tol`(×1.5) of a layer move onto it, scaled by per-vertex weight (soft region falloff via `box(co, lo, hi, fade)`).
  4. Faces fully inside with weight > 0.99 are marked `flat[axis]`; `Mesh.save` writes exactly-flat corner normals and gives flat faces 1e3 weight at shared verts "so a panel stays flat right up to its edge" (`mesh_fix.py:233-256`).
  - Exclude other materials by colour so details keep their shape: mailbox excludes grey knob/hinges (`col[:,2] < col[:,0]*1.6`, `fix_mailbox.py:32-38`); vending machine presses only red faces but includes rims shared with red faces, "or the faces between them and the wall bend and shade as creases" (`fix_vending_machine.py:41-49`).
  - Typical params: tol 5–6 mm; vending `min_share=0.03` to catch the small coin panel layer.
  - Wheelie bin variant (`fix_wheelie_bin.py:41-88`): own `press()` with soft edge (full within tol, fading to 0 at 2·tol), `fit_plane()` by area-weighted SVD with 4 outlier-rejecting refits for the 45° chamfers. Lesson recorded: **flat shading creased where panels meet rounded edges → keep smooth normals there; pressing the body's soft taper drew streaks → leave tapered parts alone** (`fix_wheelie_bin.py:10-13`).
  - Birdhouse variant: verts within 12 mm of the median wall plane snapped, hole/perch excluded by fitted circles + margins; every face in the plane gets flat normal "also those touching the hole or perch rim: their long thin triangles would otherwise spread the rim's tilted normal across the wall" (`fix_birdhouse.py:37-67`).
- **Curved parts**: `Mesh.taubin(weight, iters=10, lam=0.5, mu=-0.53)` (shrink-free), weighted & faded, "keep it off feature edges" (`mesh_fix.py:6-8,99-110`); mailbox arched rims 15 iters, excluding panel verts (`fix_mailbox.py:40-42`).
- **Generalizable**: YES, the most reusable operator. Parameters: axis list (±X, ±Y, +Z), region box, tol, exclude-colour rule. Could be auto-applied to "box-like" assets: detect large near-planar regions with RMS planarity residual 1–6 mm.
- **Generation cause**: inherent to Tripo H3.1 / v3.1 surfaces; worse with `texture_alignment original_image`? (not established — no A/B in the log). v3.1 Tripo direct was judged "lumpier" than Higgsfield H3.1 on the spray gun (`docs/asset_log.md:33`).

### D4. Primitive shapes that should be exact (cylinder / sphere / revolution / extrusion)
- **Assets**: fire_hydrant (barrel cylinder, dome revolution), parking_meter (pole + collar cylinders, flat undersides), bbq_grill (lid sphere, knob → bar cylinder), park_bench (each slat a straight extrusion with even gaps) (`fix_fire_hydrant.py:7-14`, `fix_parking_meter.py:5-9`, `fix_bbq_grill.py:6-9`, `fix_park_bench.py:5-11`).
- **Recipes**:
  - Circle fit: `lstsq([2q, 1], |q|²)` → centre, `r = sqrt(s2 + c·c)` on a plain band (`fix_fire_hydrant.py:74-78`); sphere identical in 3D with 3 refits keeping points within 1 cm (`fix_bbq_grill.py:35-48`). Parking meter uses mean axis + median radius (`fix_parking_meter.py:38-43`).
  - Project: `co[sel,:2] = axis + rel/|rel| * radius`.
  - Surface of revolution: median radius per height bin (15 bins), smoothed `[.25,.5,.25]`, `np.interp`, keep end rings exact (`fix_fire_hydrant.py:108-120`).
  - Extrusion (bench): per slat, centre line from 10 cm bins + linear `polyfit`; cross-section frame from SVD; 72 angle bins of median radius, interpolated per vertex angle; width × 0.93 "so the gaps open evenly"; edits fade out toward the iron sides (`fix_park_bench.py:104-141`).
  - **Normals**: radial corner normals on cylinder faces, `(0,0,-1)` on flat undersides, sphere-radial normals on the lid patch (`fix_fire_hydrant.py:123-130`, `fix_parking_meter.py:73-78`, `fix_bbq_grill.py:76-82`).
- **Generalizable**: YES — `fit_primitive(region, kind=plane|cylinder|sphere|revolution|extrusion, axis_hint)` + analytic normals. Region selection by colour + height band works well (fire hydrant red barrel / yellow dome).
- **Generation cause**: same surface noise as D3; plus shading of long triangles (D5).

### D5. Shading artefacts that are not geometry (normals)
- **Assets**: fire_hydrant ("Dark spikes … The barrel is a clean cylinder already; the spikes are shading: the smooth normals of the flange's underside run down its long triangles", `fix_fire_hydrant.py:7-9`); parking_meter ("The shapes are already round; the dents are shading", `fix_parking_meter.py:6-8`); pedal_car number circles ("flat fans of triangles but carry the body's smooth normals, so they shade as a star of thin lines", `fix_pedal_car.py:6-7`); engine_block / tool_chest z-fighting after pressing (D1).
- **Detected**: owner; confirmable automatically by rendering with flat vs smooth shading and diffing.
- **Recipe**: write custom split normals — flat for planar fans/discs (`m.flat[circles] = sign*(0,1,0)`, `fix_pedal_car.py:141-142`), radial for cylinders, `(0,0,-1)` for undersides; everywhere else keep exported normals.
- **Global normals rule** (applies to every fix):
  - `keep_normals.snapshot(path)` before load: map rounded vertex position (GRID 1e-4 m) → mean exported corner normal; `keep_normals.save(m, dst, before, co0, fixed, loops)` keeps it for unmoved verts not touching a fixed face (`tools/blender/keep_normals.py:1-81`).
  - `fix_common.original_normals` / `save_keeping`: keyed per **triangle** (sorted corner positions rounded to 1e-5) — more exact; supports a `shift` applied *just before export* so re-grounding doesn't break the match (`fix_common.py:16-53`). Remove keys of triangles you want re-shaded (`before.pop(...)`) (`fix_statue.py:67-69`).
  - Reason: "Mesh.save rebuilds every normal, and on Tripo meshes the rebuilt smooth normals show waves that Tripo's own normals hide" (`fix_common.py:3-5`).
- **Generalizable**: YES, should be the default save path of every fix in the skill.

### D6. Albedo defects: baked shading, smears, wrong/bled colour, missing material variation
- **Assets & rule used**:
  - fire_hydrant: spikes painted into texture; dome yellow jagged onto flange → repaint barrel red / dome yellow / flange top red; texel-level split at the seam height "so the line between yellow and red runs level instead of zigzagging along whole faces" (`fix_fire_hydrant.py:132-152`).
  - phone_booth: "Tripo baked the handle's shadow into the wall around the mounts" (`fix_phone_booth.py:62-64`).
  - vending_machine: dents painted as dark smudges → even red (`SPREAD=0.035`); louvres were "paint only (no geometry), with pinched, uneven ends" → procedurally repainted 5 grooves, pitch 19.6 mm, lit lip (`fix_vending_machine.py:8-10, 51-75`).
  - wheelie_bin: "Tripo also painted the wrinkles into the lid's blue" → even out `SPREAD=0.05` (`fix_wheelie_bin.py:9-11,113-124`).
  - pedal_car: side wrinkles painted → even red; seat smear (steering-wheel yellow bled into the seat: texels > 1.35× seat median luminance → median with shade 0.9–1.1); cockpit dark smudge "reads as dirt" (< 0.9× body red → median red of a ring around it) (`fix_pedal_car.py:8-18, 143-164`). Note: this is a cleaning game — dirt-like smudges are a gameplay-readability defect.
  - hatchback: saturated teal line on wheel arches, "a colour the car has nowhere else" → `g − r > 0.2` texels grown 1 → body median blue (`fix_hatchback.py:5-29`).
  - boss_backyard (P1 single view): float's pink projected onto the hidden pool wall → HSV transfer: take teal hue+sat, keep each texel's V (`fix_pool_pink.py:5-8, 65-76`).
  - flower_pot: soil painted in the pot's terracotta → up-facing faces inside 0.86× rim radius, hue 12–40°, sat ≥ 0.3 → `SOIL_RGB` keeping relative luminance (`fix_pot_soil.py:5-8, 64-70`).
  - bbq_grill: pale vent disc (texel mean > 1.8× lid) → lid colour (`fix_bbq_grill.py:49-57`).
  - birdhouse: "The wood is one flat orange" → procedural grain multiplied into texels: freq 38 lines/m, darkness 0.16, plank tone 0.06, direction per face; factor spilled 3 texels past faces "so bilinear filtering finds no seam" (`fix_birdhouse.py:69-98`).
  - parking_meter: underside's dark paint runs onto the pole top → pole median grey `spread=0.04` (`fix_parking_meter.py:79-82`).
- **Recipe core** (`tools/blender/mesh_paint.py`):
  - `Model.raster(polys, with_pos)`: barycentric rasterisation of UV triangles into a texel mask (edge tolerance −0.02), optionally with each texel's 3D position + face id. Use position-based masks when "a face's UV triangle may span other islands" (`fix_park_bench.py:235-238`).
  - `grow(mask, texels)`: dilate 1–6 texels — thin UV triangles cover no texel centre.
  - `recolour(px, mask, colour, spread)`: set colour × clamp(lum/mean_lum, 1±spread) — keeps a bit of shading; `spread=0` for a flat uniform patch.
  - Target colour = median texel colour of a "clean" sample region (by normal + height band + colour rule), never a hard-coded RGB except soil/glass.
  - Save: pixels → `img.pack()` → glTF export JPEG (`mesh_paint.py:71-76`).
- **Generalizable**: YES — `recolour(region, texel_rule, target=median(sample_region), spread, grow)` and `even_out(region, colour_rule, spread)`. Texel rules seen: channel differences (g−r, r>1.6g), luminance factor vs median, HSV hue range + sat min, "not in palette". Procedural overlays (grain, grooves) are per-asset but templatable.
- **Generation cause**: the style formula itself asks for lighting: "single warm key light from upper left with a soft cool fill, gentle ambient occlusion" (`tools/style/style_formula.txt`) → concept images carry shading, and with `texture_alignment original_image` it is projected into the albedo. Single-view P1 projects visible colours onto hidden surfaces (pool). Chroma-green sheets tint glass (glider).

### D7. Stray / fused / extra parts (hallucinated geometry)
- **Assets**: anchor (lone chain link fused into the ring), statue (extra hand gripping a telescope held by no arm), bbq_grill (knob on its own post in front of the handle), bus_stop (two sign poles as loose parts in front of/behind the shelter — though the prompt asked for "a round bus sign on a pole at one end"), park_bench (front slat fused to the curved lip), pedal_car (ground discs fused into three tyres) (`fix_anchor.py:5-7`, `fix_statue.py:5-9`, `fix_bbq_grill.py:8-9`, `fix_bus_stop.py:11`, `fix_park_bench.py:9-10`, `fix_pedal_car.py:12-14`).
- **Recipe — delete + clean + cap + blend**:
  1. Select: box + colour rule (anchor: light chain paint, lum > 0.33 in a box, plus faces within 8 mm of it = its dark underside) (`fix_anchor.py:29-38`); statue: SVD axis of seed-box face centres, everything within 6 cm of the axis segment except cream plinth (`fix_statue.py:36-46`); bus stop: whole islands whose min |y| > 0.4 (`fix_bus_stop.py:46-49`).
  2. `Mesh.delete(fmask)` (faces + orphan verts) (`mesh_fix.py:182-193`).
  3. Drop shreds: islands < 300 faces (anchor), < 5% of faces (statue), < 60 faces near openings (bus stop) (`fix_anchor.py:41-44`, `fix_statue.py:49-53`, `fix_bus_stop.py:74-81`). `Mesh.islands()` = union-find on shared verts.
  4. `fill_holes(vmask, uv_of(colour))` (bmesh `holes_fill` + BEAUTY triangulate, all new tris on one UV of matching colour) (`mesh_fix.py:195-211`).
  5. `taubin(patch_weight, 8–10)` around the cap; repaint patch with the surrounding median colour; pop patch triangles from the normals-keep dict (`fix_statue.py:60-69`).
  - Fused split (bench): two `bmesh.ops.bisect_plane` cuts 5 mm apart, delete the slab between, `triangle_fill` each cut outline as a flat wall (UV on a dark iron texel so the gap reads as shadow), `holes_fill` the end caps, re-triangulate n-gons (`fix_park_bench.py:143-218`).
  - Knob-on-post (bbq): project knob verts onto the bar cylinder, delete long post faces (z-span > 15 mm), weld + fill the lid spot, take a lid-coloured UV (`fix_bbq_grill.py:59-117`).
- **Generalizable**: PARTLY — the delete→drop-islands→cap→smooth→paint chain is generic; **selection needs a human hint** (box or picked faces from a QA render). Skill should ask the user to name the part and propose a box from the render.
- **Generation cause**: hand-held props and thin attachments (telescope, lance, chain link, sign pole) are the most failure-prone; worker lance was fused into the hands (`docs/asset_log.md:25`). Prevention: generate props separately and attach in-engine; keep the main object prop-free.

### D8. Ground slab / base plate / ground discs
- **Assets**: phone_booth ("a ragged dark-grey slab of ground lies under the plinth and sticks out around it"), pedal_car ("thin pale discs lie on the ground under the tyres, fused into three of them") (`fix_phone_booth.py:5-7`, `fix_pedal_car.py:12-14`).
- **Detected**: owner; QA already reports "lowest point in each third of the footprint" (`tools/blender/qa_render.py:7,98-110`) but not "thin geometry at z≈0".
- **Recipe**: delete faces with centre `z < 6 mm` (booth) / pale faces with centre `z < 13 mm` (car); `fill_loops(m, co_z < t+0.01, uv_of(plinth_colour), outward=(0,0,-1))`; re-ground by `drop = co[:,2].min()` applied as `save_keeping(..., shift=(0,0,-drop))` (`fix_phone_booth.py:39-43,81`, `fix_pedal_car.py:61-64,123,169`).
- **Generalizable**: YES — `remove_ground_slab(z_max, colour_rule=None, cap=True, reground=True)`; auto-detectable as large near-horizontal faces at the min z extending beyond the body's footprint.
- **Generation cause**: sheet drew a floor/shadow; later prompts add "no shadow, no floor, no ground line" (`art_src/refs/depot/obj_depot_traffic_light/sheet_green.prompt.txt`) and "sits directly on the ground with no base plate or slab around it" (statue, `docs/asset_log.md:46`).

### D9. Cracks / separate shells / UV-seam splits
- **Assets**: jerry_can ("the shoulder … is a separate shell that stops a few millimetres short of the body, leaving a thin crack") (`fix_jerry_can.py:5-8`).
- **Recipe**: `remove_doubles(all, 1e-4)`, then `remove_doubles(boundary verts in region, dist=0.02)` — only open-edge verts move; report open-edge count before/after; rebuild smooth normals over the joined mesh (`fix_jerry_can.py:27-45`).
- Global: **Tripo GLBs are split at every UV seam** — `Mesh.__init__` welds `remove_doubles(1e-4)` and triangulates before any topology op (`mesh_fix.py:1-3,21-29`). Islands/hole logic is wrong without this.
- **Generalizable**: YES — `weld_boundary(region, dist)`; auto-detect: count boundary edges after 1e-4 weld; >0 on a supposedly closed prop = crack.

### D10. Closed volume where there should be a cavity (no view sees inside)
- **Assets**: pickup ("Both Tripo attempts closed the bed with a flat lid level with its walls (the four views never see inside it)") (`fix_pickup.py:5-8`).
- **Recipe**: select lid faces (`normal.z > 0.8` in a box); four `bisect_plane` cuts at `WALL=3.5 cm` inside the lid outline; delete the inner rectangle; build 4 walls + floor `DEPTH=16 cm` down with normals flipped toward the bed centre; UV all box faces to the centre of a **free 16×16 texel square** ("JPEG blocks are 8 texels") painted `body × 0.7`; flat normals (`fix_pickup.py:21-97`).
- **Generalizable**: YES — `carve_cavity(top_region, wall, depth, shade)` + `free_atlas_square(size)`.
- **Generation cause**: orthographic elevations at mid height can't show interiors; add a top view or a close-up of the interior to the sheet, or accept a Blender carve.

### D11. Transparency / glass
- **Assets**: bus_stop ("The glass came out as broken pale strips … torn sheets with holes"), pickup v1 (rear window glass ran onto the bed → remade), glider (canopy pale green from the chroma background) (`fix_bus_stop.py:6-10`, `docs/asset_log.md:200,90`).
- **Recipe** (`fix_bus_stop.py:51-159`): delete everything in each frame opening within 3 cm of its plane (except bench by colour and a timetable post), plus pale-blue faces within 7 cm; drop crumb islands < 60 faces; find a free texture square (sliding-window over unused-texel mask with 2 px padding; "Tripo packs its atlas tightly: about 50 is the largest free square", used 44 px); paint glass blue + two diagonal glints; add 6 mm-thick box panes reaching 8 mm into the frame, big faces mapped across the swatch, edges on its middle; flat normals. Panes are **opaque** because "The game draws a model with one opaque material".
- **Generalizable**: YES — `replace_glass(openings[], colour, glints)`; openings currently hand-measured (could be derived from frame-colour faces).
- **Generation cause**: Tripo produces no usable transparency; glass in the concept becomes fragmented geometry. Prevention: describe glass as "opaque light-blue painted panel" in the sheet, or leave openings empty and add panes in Blender; never put glass over chroma green.

### D12. Proportion / scale / orientation / pivot
- **Proportion**: fire_hydrant side outlets too big → shrink toward their axis ×0.8 across, ×0.85 out, barrel blended back over 85–115 mm "so no sloped skirt is left" (`fix_fire_hydrant.py:12-14, 82-99`). Generalizable: `scale_part(selection, axis, factors, blend_radius)`.
- **Orientation**: Tripo models face +X; `--yaw -90` is default, `90` when the reference front came out on the other side (fire hydrant: hose outlet is front; traffic light: visored lamps; jet ski; satellite dish), `180` for the Tripo v3.1 vehicle batch, `0` for the windsock "side on" (`tools/place_refs.sh:5-6,20-62`, `tools/place_model.py` `--yaw` help). Front is decided by **identifying a semantic feature**, not by bbox.
- **Scale**: height = the placeholder's baked bounds, overridden by `H=` for long objects "to stay inside the frame" (dinghy 0.40, fishing boat 0.88, biplane 0.62, glider 0.28 sized by wingspan) (`tools/place_refs.sh:7,33-44`); `--fit x|y` option exists (`tools/blender/clean_model.py:6-12`).
- **Pivot**: origin at base centre; `--origin top`, and `--origin surface` for the conveyor (top levelled, it "sloped ~8° toward the camera") (`clean_model.py:11-14`, `docs/asset_log.md:24`).
- All handled in the generic placement step, not per-asset fix scripts.

### D13. Missing parts / wrong part count (not fixable cheaply)
- go_kart missing steering-wheel ring (remade), jerry can 3 handles + 2 caps (remade), tool chest handle on one side only (mirrored), eq_washer wrong panel colour (accepted) (`docs/asset_log.md:193,199,194,26`). Rule of thumb from the record: **missing or duplicated major parts → regenerate (or mirror if symmetric); surface/colour/small-part issues → Blender**.

---

## 3. Parametric operator set distilled (for the skill's free-Blender fix menu)

| Operator | Covers | Key params | Source recipe |
|---|---|---|---|
| `weld(dist=1e-4)` + triangulate | prerequisite for everything | dist | `mesh_fix.py:21-29` |
| `remove_ground_slab` | D8 | z_max, colour rule, cap colour sample, reground | `fix_phone_booth.py:39-43` |
| `delete_part` → `drop_islands` → `cap_holes` → `taubin` → `paint` | D7, D1-B | box / colour / axis-cylinder selection; min island faces or share; cap UV by colour | `fix_anchor.py`, `fix_statue.py`, `mesh_fix.py:182-211` |
| `flatten_planes(axis, region, tol, min_share, exclude)` | D3, D1-A | axes, region box (+fade), tol 5–8 mm | `mesh_fix.py:135-172`, `fix_wheelie_bin.py:41-88` |
| `press_relief(axis, region, proud)` + `delete_coplanar_inner` | D1-A | plane auto from depth histogram | `fix_engine_block.py`, `fix_tool_chest.py` |
| `fit_primitive(region, kind)` + analytic normals | D4, D5 | plane / cylinder / sphere / revolution / extrusion | `fix_fire_hydrant.py`, `fix_parking_meter.py`, `fix_bbq_grill.py`, `fix_park_bench.py` |
| `mirror_half(axis, plane_from, keep)` / `clone_part` | D2 | axis, plane source region | `fix_scooter.py`, `fix_tool_chest.py`, `fix_pedal_car.py:59-121` |
| `weld_boundary(region, dist)` | D9 | dist ≤ 2 cm | `fix_jerry_can.py` |
| `carve_cavity(top_region, wall, depth, shade)` | D10 | | `fix_pickup.py` |
| `replace_glass(openings, colour)` | D11 | opening planes/extents | `fix_bus_stop.py` |
| `recolour` / `even_out` / `hsv_transfer` / procedural overlay | D6 | texel rule, sample region, spread, grow | `mesh_paint.py:79-97`, `fix_*` paint blocks |
| `free_atlas_square(size)` | D10, D11, new faces | size ≤ ~50 px on Tripo 1K atlas | `fix_bus_stop.py:85-91`, `fix_pickup.py:76-85` |
| `save_keeping_normals(flat, fixed_loops, shift)` | all | | `fix_common.py:29-53`, `keep_normals.py:41-81` |

---

## 4. Detection: what was manual, what the skill could automate (my proposals, not in the repo)

Repo facts: QA = 4 ortho views + iso + iso_wire on white, flat albedo; JSON with tris, sliver % (area < 2% of longest edge²), lowest point per footprint third; flag at > 3% slivers (`tools/blender/qa_render.py:1-8`, `tools/qa_models.py:25-27`). Everything else was eyes.

Proposed automatic checks mapped to defects (headless bpy + numpy, all read-only):
- D8 slab: faces with centre z < 1–2% height and normal.z ≈ ±1 whose XY extent exceeds the footprint of geometry above 5% height.
- D7 strays: island count after 1e-4 weld; islands < 1–5% of faces; islands not touching the main body.
- D9 cracks: boundary-edge count after weld (should be 0 for a closed prop).
- D1 back copies: render front and back with flat albedo, mirror the back, compare edge/feature density or silhouette+interior SSIM; high similarity on an object whose sheet back is "plain" → flag.
- D2 asymmetry: for objects tagged symmetric, Hausdorff distance between mesh and its mirror about the bbox mid-plane (tool chest handle, scooter mirror disc would light up).
- D3 wrinkles: segment near-planar regions (normal clusters), report RMS distance to fitted plane; 1–6 mm on > N cm² → flag.
- D5 shading: render smooth vs flat-shaded; luminance streaks along long thin triangles; triangles with aspect > 10 adjacent to flat fans.
- D6 albedo: palette check — cluster texel colours, flag clusters absent from the reference image palette (hatchback teal); luminance variance within a single-colour region (baked wrinkles/shadows); for the cleaning game, dark low-saturation blotches that "read as dirt".
- D10 cavity: compare to sheet text keywords ("open", "bed", "hollow") — mostly a prompt-planning item.
- D11 glass: if the prompt mentions glass/window/transparent, always flag for review.

---

## 5. GENERAL lessons (true for any game using Tripo)

1. **Weld at 1e-4 before any topology logic** — Tripo splits vertices at every UV seam (`mesh_fix.py:1-3`).
2. **Preserve Tripo's exported normals on untouched geometry**; set analytic normals only where you changed shape; never globally recalc (`fix_common.py:3-5`, `keep_normals.py:1-11`). Re-ground/shift at export time, after normal matching (`fix_common.py:29-32`).
3. **Much "dent" feedback is normals, not geometry** — check flat-shaded first (`fix_fire_hydrant.py:7-9`, `fix_parking_meter.py:6-8`).
4. **Tripo paints its geometry defects and the concept's lighting into the albedo**; any geometric fix needs a matching albedo pass (wrinkles, handle shadow, spikes) (`fix_wheelie_bin.py:9-11`, `fix_phone_booth.py:62-64`, `fix_fire_hydrant.py:132-135`). Avoid lighting/AO words in the concept prompt if the asset will be lit in-engine (`tools/style/style_formula.txt` contains them — a likely contributor).
5. **Multiview hides nothing less than single view, it just moves the guesswork**: back faces copy front features; far sides deform; interiors get lidded. Describe back, sides and interior explicitly in the sheet prompt and **review the sheet's back/side views before paying for 3D** (jerry can first sheet failed at the sheet stage, `docs/asset_log.md:199`).
6. **Symmetric objects: mirror the good half** rather than regenerate (`fix_scooter.py`, `fix_tool_chest.py`); keep an overlap strip instead of welding.
7. **After pressing relief into a plane, delete the now-coplanar inward faces** or they z-fight (`fix_engine_block.py:39-43`).
8. **Painting**: rasterise UV triangles with dilation (thin triangles miss texel centres), keep relative luminance within a small spread, pick target colour as a median of a clean region; select by 3D texel position when UV triangles straddle islands (`mesh_paint.py:79-97`, `fix_tool_chest.py:97-107`, `fix_park_bench.py:235-238`).
9. **New faces need texture space**: Tripo atlases are tightly packed (~50 px max free square at 1K); find a free square, paint it, keep JPEG 8-px block alignment in mind (`fix_bus_stop.py:38-39`, `fix_pickup.py:25-26`). Hole caps all land on one UV point — move them onto a painted texel (`fix_traffic_light.py:58-67`).
10. **Glass/transparency is not a Tripo strength**; plan opaque painted panes or Blender-made panes; never chroma-key behind glass (`fix_bus_stop.py:9-10`, `docs/asset_log.md:90`).
11. **Props held by characters/objects fuse or multiply** (lance, telescope, chain link). Generate props as separate assets and attach in-engine; prompt "holding NOTHING" for riggable characters (`docs/asset_log.md:25,46`).
12. **Prompt against floors**: "no shadow, no floor, no ground line", "sits directly on the ground with no base plate" (sheet prompts; `docs/asset_log.md:46`).
13. **Fix vs regenerate**: missing/duplicated major parts → regenerate (≈ 50 Tripo credits or 12 Higgsfield credits per try); surface noise, back copies, strays, colour → free Blender. Retexture (20 credits) is a coin-flip: worked for bench/mower, worse for pedal car (`docs/asset_log.md:37-39`); a procedural Blender albedo overlay (grain) is a free alternative (`fix_birdhouse.py`).
14. **Run fixes on the normalised model** (front −Y, base at z=0, metres) so thresholds are meaningful, and make the pipeline re-runnable raw → place → fix (`tools/place_refs.sh:12-18`). But store the region parameters **relative to bbox** in the skill so re-scaling doesn't break them (the repo's absolute constants would).
15. **Tripo smart_low_poly (v3.1) cut slivers ~3–20× vs P1** (2.5% → 0.8% bicycle; 17.6% → 5.6% bench) (`docs/asset_log.md:34-37`). Sliver % is a cheap QA number worth keeping.
16. **Log every task id, settings, credits and every fix with its review date** in an asset log — this is what made this catalogue possible (`docs/asset_log.md:3-5`).

## 6. PROJECT-SPECIFIC lessons (grime-does-pay only)

- Budget/format: ≤ 8k tris (belt objects, place_model up to 12–12.5k accepted for v3.1 vehicles), bosses ≤ 30k, 1 material, 1K JPEG albedo, root `obj_<zone>_<id>`, output `assets/models/objects/<zone>/<id>.glb` (`docs/gdd/07-ai-asset-pipeline.md:9,18`, `docs/asset_log.md:34-41`).
- One opaque material per model → glass must be opaque paint (`fix_bus_stop.py:9-10`).
- Game camera sees the front (−Y); the far side matters less, which is why defects there were first noticed late (`fix_scooter.py:5`).
- Cleaning game: dark smudges "read as dirt" and must be removed (`fix_pedal_car.py:17-18`); `DirtTarget` keeps the model texture under the dirt (`docs/gdd/07-ai-asset-pipeline.md` step 4).
- After every model swap: re-bake the silhouette mask (`bake_silhouette.gd`), `check_import.sh`, `run_tests.sh` (`tools/place_refs.sh:4`).
- Style formula + `art_src/backyard_v2/pedal_car.png` as the style ref for all sheets; chroma green `#00B140` sheets keyed by `tools/key_views.py` (`docs/asset_log.md:39,42`).
- Owner policy from 2026-10-30: remaining zones placed unfixed, "flaws get fixed as they show in play" (`tools/place_refs.sh:31`) — i.e. fixes are budgeted by visibility.
- Specific magic numbers (only valid for this project's scale/frame): wrinkle tol 5–8 mm, slab z < 6 mm, back proud 8 mm, glass swatch 44 px, pane 6 mm, bench gap 5 mm.

## 7. Per-asset index (fix script → defects → generation)

| Asset | Fix script | Defects | Pipeline / task (asset_log) |
|---|---|---|---|
| boss_backyard (pool) | `fix_pool_pink.py` | D6 projected colour on hidden wall | A, task 12f66517…, face_limit 20000 (`asset_log.md:23`) |
| obj_backyard_flower_pot | `fix_pot_soil.py` | D6 soil = pot colour | B, alignment geometry, 25e5402b… (`:36`) |
| obj_backyard_pedal_car | `fix_pedal_car.py` | D5 circles, D6 smear+smudge+wrinkle paint, D8 discs, D2 clone wheel, D3 sides | B, alignment original_image, face_limit 10000, 47bd0ee9…; retexture rejected (`:39`) |
| obj_backyard_bbq_grill | `fix_bbq_grill.py` | D4 lid sphere, D7 knob+post, D6 vent paint | B, alignment geometry, 31a5c5fe… (`:40`) |
| obj_backyard_birdhouse | `fix_birdhouse.py` | D3 gable walls, D6 flat wood → grain | B, alignment geometry, 83246ac3… (`:41`) |
| obj_garage_scooter | `fix_scooter.py` | D2 far side | B, original_image, d90a0301… (`:190`) |
| obj_garage_tool_chest | `fix_tool_chest.py` | D2 one handle, D1 drawers on back | B, 3rd attempt ae290642…, 100 credits wasted (`:194`) |
| obj_garage_hatchback | `fix_hatchback.py` | D6 off-palette teal line | B, 05e8d61a… (`:195`) |
| obj_garage_engine_block | `fix_engine_block.py` | D1 pulleys on back, z-fight | B, 84c0c6f6… (`:198`) |
| obj_garage_jerry_can | `fix_jerry_can.py` | D9 crack | B, 3rd attempt a08c5dde… (`:199`) |
| obj_garage_pickup | `fix_pickup.py` | D10 lidded bed | B, 2nd attempt 88b150b0… (`:200`) |
| obj_depot_bus_stop | `fix_bus_stop.py` | D11 broken glass, D7 sign poles | C, job 3320c3a5… (`:44`) |
| obj_depot_fire_hydrant | `fix_fire_hydrant.py` | D4, D5 spikes, D6, D12 outlets | C, 44007696…, yaw 90 (`:50`) |
| obj_depot_mailbox | `fix_mailbox.py` | D3 | C, 93f94583… (`:42`) |
| obj_depot_park_bench | `fix_park_bench.py` | D4 slats, D7 fused pair (two owner passes) | C, 3383532b… (`:45`) |
| obj_depot_parking_meter | `fix_parking_meter.py` | D4, D5, D6 | C, 1d279b57… (`:51`) |
| obj_depot_phone_booth | `fix_phone_booth.py` | D8 slab, D1 back handle, D6 baked shadow | C, 3ccc9fdc… (`:43`) |
| obj_depot_statue | `fix_statue.py` | D7 extra hand + telescope | C, 2nd model f9a323f2… (`:46`) |
| obj_depot_traffic_light | `fix_traffic_light.py` | D1 lamps on back | C, 2c6fbee3…, yaw 90 (`:52`) |
| obj_depot_vending_machine | `fix_vending_machine.py` | D3, D6 smudges + louvres | C, a0b09139… (`:48`) |
| obj_depot_wheelie_bin | `fix_wheelie_bin.py` | D3, D6 | C, ee930332…; residual waves (`:49`) |
| obj_shipyard_anchor | `fix_anchor.py` | D7 stray chain link | C, b2648263… (`:55`) |

(Line refs in this table are `docs/asset_log.md` line numbers.)
