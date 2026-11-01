# Fix trade-offs: Blender, Tripo or regenerate

When to read this: phase 6 (problem report, options, apply), right after a QA run that found something worth fixing.

For every finding the user gets up to three options: **A** Blender (0 credits), **B** Tripo (credits, through the lock window), **C** regenerate (only when the main geometry is broken or missing). Free work is prepared as a preview without asking; applying it, and every paid option, waits for the one batched answer ("1A, 2B, 3 geç").

## 1. The ladder (spec 13), cheapest first

1. **Engine-side setting** (`engine_side`): Godot import option, material, collision, LOD. 0 credits.
2. **Blender operator** from `fixkit` in a fix recipe. 0 credits.
3. **Retexture** (`tripo_retexture`, a Tripo `texture` step, 10 to 30): colour or texture problems on a good mesh. Worked about half the time in the prior projects.
4. **Re-decimate with v3.0** (`tripo_decimate`, 35): budget, messy triangles, broken UVs together.
5. **Regenerate** (`tripo_regenerate`, 20 to 60): only for a broken or missing main part. Cap 2 per asset (B11); if the image caused it, fix the image first (`image-preflight.md`).
6. **Place as is, fix later**: put it in the game and add a priced note to the later list in `assets/<id>.json` `decisions`.

Who fixes what (K12):

| in Blender (written into the GLB) | in Godot (engine side) |
|---|---|
| geometry, holes, loose parts, normals | glass and transparency material |
| scale, direction, pivot | collision |
| UVs, texture and colour fixes | LODs (Godot generates them) |
| separating parts, naming | import settings (texture size limit, compression) |

Order: **cloud first, then local**. All paid Tripo steps run (each its own command, B17) before any Blender fix; the raw output stays frozen in `raw/<label>/`. The one exception is rig (B18): rig is the last cloud step and comes after the Blender geometry fixes. Warn when a Blender choice makes a later Tripo step more expensive: a locally edited model can only go back to Tripo as a file, which adds an import task with an unpublished price and normalizes scale.

## 2. One row per QA code

Columns: A = Blender ops (the `fix_options` names `qa.py` reports); B = Tripo route and credits; C = when to regenerate; then what each route keeps. "A refuses rigged" means `apply_recipe.py` and `normalize.py` refuse a rigged input: geometry is never touched after rigging, so fix before rig.

| code | A: Blender (0 credits) | B: Tripo (credits) | C: regenerate when | keeps rig | keeps UV | keeps scale |
|---|---|---|---|---|---|---|
| `OVER_BUDGET` | none in fixkit (Godot LODs do not lower LOD0) | `tripo_decimate`: decimate `model=v3.0;face_limit=<budget>;smart_uv=true`, 35 (40 quad); never v2.0 | never for budget alone | A n/a; B no (decimate before rig) | B no: new UVs, texture re-baked | B unknown: re-run `normalize.py` |
| `NON_MANIFOLD` | `weld_boundary`, then `delete_region` on the bad faces (+ `fill_holes`) | segment 40 + complete `quick_cap` 30 | thousands of edges across the main body | A refuses rigged; B no | A yes on untouched faces; B unknown | A yes; B unknown |
| `HOLES` | `weld_boundary` (seam weld + open-edge snap), then `fill_holes` (loop walker, caps take rim UVs) | segment 40 + complete `quick_cap` 30 | a main part is missing, not just open | A refuses rigged; B no | A yes (caps get rim UVs); B unknown | A yes; B unknown |
| `LOOSE_PARTS` | `remove_loose` (pieces under `min_tris_pct`, needs a weld), or `delete_region` for a named piece | none | the pieces are a needed part that came out detached and broken | A refuses rigged | A yes | A yes |
| `FLIPPED_NORMALS` | `delete_region` + `fill_holes` on the flipped patch | `tripo_regenerate` | flipped over a large visible area | A refuses rigged; C no | A yes | A yes |
| `SLIVERS` | none in fixkit | `tripo_decimate` (v3.0, 35) remeshes; `tripo_regenerate` from views (bicycle 2.5% to 0.8%) | slivers come with broken shapes (spokes, teeth) | B no | B no: new UVs | B unknown |
| `GROUND_SLAB` | `remove_ground_slab` (max_height_pct 3, regrounds the model) | none | never; remove the ground line from the image for the next run | A refuses rigged | A yes | A yes (reground to the old floor) |
| `NOT_GROUNDED` | `normalize` (yaw, scale, `bottom_center` pivot); `delete_region` for a stray low piece | none | the model is tilted in its own geometry beyond a yaw fix | A refuses rigged | A yes | A sets it: uniform scale to the placeholder |
| `ASYMMETRY` | `mirror_half` (keep the good side, weld the seam), `clone_part` (copy a good handle or wheel over a bad one) | `tripo_regenerate` from a symmetric front view | both halves are bad | A refuses rigged | A yes (copied faces carry their UVs) | A yes |
| `BACK_COPY` | geometry only: `flatten_region` (press the copied relief flat) or `delete_region` + `fill_holes` (cut the copied parts, cap the hole). **Copied paint: none / partial.** Neither op removes paint: pressed faces keep their texture and `fill_holes` caps take their UVs from the rim, so the copied paint stays visible on the flat back and `UV_OVERLAP` rises (tool chest: back relief 0 after the fix, drawer paint still there, UV overlap 26.6%). `recolour` is no fix for it: it edits the whole texture, it has no region | `tripo_retexture` 10 to 30: the honest rung for copied paint (on a locally edited mesh it goes back as a file: import task, price unknown, so retexture before the Blender fix when possible); `tripo_regenerate` for copied geometry the image caused | the copy is a whole extra object (two screwdrivers) | A refuses rigged | A yes on pressed faces; caps reuse rim UVs (overlap rises); B new texture | A yes |
| `UV_OVERLAP` | none in fixkit (a manual re-unwrap + bake in Blender is possible) | `uv` (Smart UV) 20: re-unwraps and remaps the texture, rig and animation, at most 80000 tris; or decimate v3.0 `smart_uv` 35; `tripo_retexture` 10 to 30 only when the texture itself is bad | never | B `uv` yes | B `uv` new layout, texture remapped | B unknown |
| `LOW_TEXEL` | none (a larger texture cannot be invented locally) | `tripo_retexture`: texture `texture_quality=detailed` 20 (`extreme` 30) | never | B unknown: retexture before rig | B unknown | B same mesh |
| `PALETTE_DRIFT` | `recolour` with `ref_palette` (saturation matched to the reference) or `hsv_shift` | `tripo_retexture` 10 to 30 (texture v3.5) | never | A refuses rigged | A yes (pixels only) | A yes |
| `BAKED_LIGHT` | `recolour` (partial: lifts dark areas, cannot remove a light direction) | `tripo_retexture`: texture `model=v3.5;delight=true` 10 to 30 | never | A refuses rigged; B unknown | A yes | A yes; B same mesh |
| `TOO_MANY_INFLUENCES` | none in fixkit (geometry is frozen after rig) | `tripo_rig` again from the clean pre-rig GLB, 25 + import | never | `engine_side`: accept it when the target allows (Godot supports up to 8 weights; 4 is the portable limit), keeps the rig | yes | yes |
| `MULTI_MATERIAL` | `separate_parts` by material when the parts should move apart; else `engine_side`: keep a second material only for glass or emissive parts | none | never | A refuses rigged | A yes | A yes (each part gets its own bottom-centre pivot) |
| `TEXTURE_OVERSIZE` | none | convert `texture_size=1024` or `2048`, 10 (advanced tier) | never | `engine_side`: Godot texture import Size Limit, or resize in Blender; keeps everything | yes | yes |

Notes on the table:
- Material budget for `MULTI_MATERIAL`: 1 per prop, 2 with a glass, emissive or alpha part.
- A defect with no QA code (closed cavity, extra handle, fused prop) uses the same columns: `delete_region` + `fill_holes`, `clone_part`, `separate_parts`; Tripo segment 40 / complete 50; regenerate from a fixed image.
- Glass found in QA is marked as a material in Godot (spec 13). Tripo glass always comes out opaque and painted; PATINA used a shader that reads the painted grey or pale-blue area as glass.

## 3. Fix recipes, not one-off scripts

A fix is a recipe file, `fixes/<id>.recipe.json`, replayed from the raw model each time:

```
{"schema": "recipe/1", "asset": "tool_chest", "source": "../raw/tool-chest-generate-v01/model.glb",
 "steps": [{"op": "normalize", "params": {"yaw": -90}},
           {"op": "weld_boundary", "params": {}},
           {"op": "mirror_half", "params": {"axis": "x", "keep": "+"}},
           {"op": "hard_edges", "params": {"angle": 30}}]}
```

```
python3 scripts/bl.py apply_recipe.py -- fixes/tool_chest.recipe.json --work work/
python3 scripts/bl.py export.py -- work/v03.blend --out-model export/tool_chest.glb
```

- `apply_recipe.py` always starts again from `source` and writes the next free `work/vNN.blend` (images packed, editable) and `work/vNN.glb`. The same recipe on the same raw gives the same result; after a regeneration the recipe is simply tried again.
- A bad recipe (unknown op or parameter, wrong order, an op that needs a weld before it) exits 2 and writes nothing; a missing recipe or source exits 3.
- `export.py` writes the GLB for Godot (+Y up, images in their own format, a Triangulate modifier last so `tris` is exactly what the engine gets) and `export.sh`, one command to re-export after a hand edit of the `.blend` (B12).
- Every recipe runs inside one NormalKeeper per mesh: Tripo's normals are kept on every untouched triangle and only new or changed triangles get new normals (B7). Never recalculate normals globally.

## 4. fixkit operators (`scripts/blender/fixkit/ops.py`)

Lengths and regions are fractions of the model's bbox, never metres. A `box` is `[x0, y0, z0, x1, y1, z1]` in 0 to 1 bbox space; `*_pct` values are percent of a bbox size. Frame: Blender, Z up, front -Y after `normalize`.

| op | params | does | notes |
|---|---|---|---|
| `normalize` | `yaw`, `target_size`, `target_height`, `pivot`, `name` | weld, turn, uniform scale, pivot, names | sizes in metres; see `godot.md` for the axis order |
| `weld_boundary` | `eps_pct` 0.001 | seam weld, then open-edge vertices within `eps_pct` % of the diagonal | run before the ops that need a weld |
| `remove_loose` | `min_tris_pct` 1.0 | drops islands below the share; the largest always stays | needs a weld |
| `remove_ground_slab` | `max_height_pct` 3, `reground` true | removes the flat sheet in the bottom band | needs a weld |
| `delete_region` | `box` | deletes faces whose centre is inside | |
| `fill_holes` | `max_edges` 64 | caps boundary loops; skips caps that would not be manifold (`holes_skipped`) | needs a weld |
| `mirror_half` | `axis`, `keep`, `plane` 0.5 | cuts at `plane`, mirrors the kept side, welds the seam | |
| `flatten_region` | `box`, `axis`, `proud_pct` 0.5 | presses relief standing out along `axis` back onto the main plane | |
| `clone_part` | `src_box`, `dst_offsets` | copies the faces in `src_box` to each offset, replacing what was there | |
| `hard_edges` | `angle` 30, `box` | marks edges sharper than `angle` sharp and splits normals there | runs after the normal restore; needs a weld |
| `separate_parts` | `by` loose or material | one object per part, `<asset>_part_NN`, pivot at each part's bottom centre | last geometry step; loose needs a weld |
| `recolour` | `hsv_shift` [hue_deg, sat_mul, val_mul] or `ref_palette` | edits base-colour pixels, saves in the image's own format | |

Show the user what a box covers (render it, or describe it by feature) before applying: a box chosen on the wrong side is how a past fix landed on the wrong face.

## 5. Re-check

After each applied fix: QA + render sheet on the new version, before/after side by side (`qa-checklist.md` section 7). Update `assets/<id>.json` (`--set recipe=<path>`, `--append decisions=<json>`, `--phase fix`).
