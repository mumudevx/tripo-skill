# Generation planning: model, budget, texture, parts

When to read this: phase 4 (generation plan), after the image preflight passed or the user said "yine de gönder". Command syntax and prices are in `tripo-cli.md`.

The plan ends in one `tripo_plan.py` step whose dry-run is valid, shown to the user as a few Turkish lines (model, input, face budget decision, texture, price from the dry-run). Then the command runs and the lock window is the approval.

## 1. Inputs that decide the plan

| input | where it comes from |
|---|---|
| asset class | the brief (`assets/<id>.json` `class`): `small_prop`, `large_prop`, `env_piece`, `weapon_held`, `npc`, `hero`, `vehicle` |
| triangle budget | `profile.json` `budgets[class]` (defaults below; the profile may override any class) |
| art style | `profile.json` `art_style` (low poly / stylized / realistic ...) |
| PBR | `profile.json` `pbr` (default `false`) |
| pinned models | `profile.json` `pinned.gen_model`, `texture_model`, `rig_model` |
| references | 1 image, or 2 to 4 orthographic views, after `image-preflight.md` |
| hard surface or round | from the reference: holes, thin plates, sharp panels = hard surface |
| multi-part | movable or detachable parts seen in preflight (K7) |
| will be rigged | class `npc`/`hero`, or the brief says so |

Default LOD0 budgets (`scripts/data/budgets.json`, from `_research/game-polycount-lod.md` section 2a; starting points, not limits):

| class | mobile | pc |
|---|---|---|
| small_prop | 800 | 3000 |
| large_prop | 3000 | 15000 |
| env_piece | 2000 | 10000 |
| weapon_held | 3000 | 10000 |
| npc | 5000 | 20000 |
| hero | 10000 | 50000 |
| vehicle | 15000 | 30000 |

Count triangles, never "polys": with `quad=true`, `face_limit` counts quads and each quad is about 2 triangles.

## 2. Input type and model

- One image: image-to-model. Two to four orthographic views: multiview-to-model. Prefer multiview: it costs the same on the H series (20/30) and leaves less of the hidden sides to chance. Single images produced a toothed mailbox lid, a pink inner wall and 2.5% slivers on a bicycle (0.8% with views).
- Default model: `tripo-v3.1` (or the profile's `pinned.gen_model`). Always pass it with `--model`.
- Low-poly art style: offer a comparison with prices, never a silent switch:
  - `tripo-v3.1` + `smart_low_poly=true` + `face_limit` (30 from text, 40 from image): hand-made-style triangles, but measured over the limit (below);
  - `tripo-p1` (40/50): clean triangles, stays under the limit, no quads or parts;
  - `tripo-p2` (100/110): the only native-quad low poly, `face_limit` up to 50000 tris.
- P1 is used in the prior projects only for far background pieces; every close-up antique part was v3.1.
- `geometry_quality=detailed` and `texture_quality=extreme` are not used for game assets unless the user asks: they double the price and turn printed detail into lumps.

## 3. Face budget decision (B8, B9)

`face_limit` is a hint, not a cap. Measured on real outputs (`_research/prior-testset.md` section 3). **Re-verify the two `smart_low_poly` rows after 2026-12-01:** Tripo then runs `smart_low_poly` on retopology v3.0 (email 2026-11-02), so the overshoot may change; measure the first run and record a lesson:

| request | result |
|---|---|
| v3.1 multiview + `smart_low_poly`, limit 8000 | 7445 to 12175 tris over 20 objects; one tool chest 17430 |
| v3.1 + `smart_low_poly`, limit 10000 | 12367 (pedal car) |
| v3.1 without `smart_low_poly`, and P1 | under the limit: 2834/4000, 5456/6000, 18476/20000, 7364/8000 |
| no limit (v3.1) | 1.31 M to 1.93 M tris, 42 to 64 MB GLB |
| decimate v3.0 + `smart_uv` | 0.69 to 1.02 x the target |
| decimate v1.0 | the target within 2 faces, but no bake and a mismatched normal map that creases flat parts |
| decimate v2.0 | 20000 requested, 29943 delivered |

Rules:

1. **Hard surface** (holes, thin plates, panels, slats): generate with no `face_limit`, then `decimate` with `model=v3.0`, `smart_uv=true` and `face_limit` = the budget (35). A generation-time limit made thin plates wavy.
2. **Round, toy-like or organic props**: a generation-time `face_limit` is acceptable.
3. The profile may override rule 1 per art style.
4. Never `decimate` v2.0 (or a `decimate` without `model`, which is v2.0) when the budget matters.
5. After every generation, measure: `python3 scripts/glbstat.py <model.glb>` gives `tris`; `qa.py --budget <N>` reports `OVER_BUDGET` (info above 1.0 x, S1 above 1.1 x, S0 above 2 x). Report the gap between requested and measured triangles in the QA summary.
6. Decimate before `uv` (Smart UV accepts at most 80000 triangles) and before rig (skinning happens on the final mesh, B18).
7. LODs: spend credits on LOD0 only. Godot builds LODs on import (`meshes/generate_lods`, each step about half the triangles). The bundled tripo-cli `examples/game-asset.md` LOD recipe is wrong: it chains `@last`, so each LOD decimates the previous LOD instead of the source, and every LOD costs 30 to 35. Build LODs locally or let Godot do it.

## 4. Texture

- Default: `texture_version=v3.5`, `delight=true` (removes lighting baked into the reference; v3.5 only), `texture_quality=standard`; `detailed` (+10) for hero and large props seen up close.
- `delight=false` only for deliberately painted shading (hand-painted style).
- PBR is opt-in since 0.9.0. With `profile.pbr = false` send nothing (one base colour image); with `true` send `-p pbr=true` (base colour + metallic/roughness + normal maps). Prior projects: GRIME `pbr=false` (one JPEG, 1.5 to 3 MB raw, 1K after cleanup); PATINA PBR on (Color JPG, NormalGL PNG, ORM JPG, 1.3 to 5.6 MB).
- Colour drift: GRIME measured about 25% saturation loss against the concepts; QA's `PALETTE_DRIFT` measures it when `--ref-palette` is given.

## 5. One piece or parts (K7, K16)

Ask once, only for objects with movable or detachable parts (doors, lids, wheels, drawers), and show both prices in the same message:

| route | how | credits (image input, H3.1) |
|---|---|---|
| one piece | normal generation; Blender `separate_parts` later if needed | 30 to 40 |
| parts at generation | `generate_parts=true` with `texture=false`, `pbr=false` (untextured), then a `texture` step | 20 + 20 = 40, then 10 to 30 for texture |
| one piece, split by Tripo | normal generation, then `segment` (v2.0, price unknown; v1.0 was 40 and retires 2026-12-01), or `smartsegment` on a file (55) | 30 to 40 + unknown or 55 |

- Parts come only from Tripo (`generate_parts`, `segment`, `smartsegment`). Never one image and one generation per part: in PATINA such parts did not fit together and did not look like one family (K16, the seed lesson in `lessons/general.md`).
- `generate_parts` cannot be combined with `smart_low_poly` (rejected); with `quad=true` the parts come out as triangles.
- Per-part pivots (hinge, hub, grip) are set locally (`separate_parts` gives each part a bottom-centre pivot; adjust in Blender if a hinge is needed).

Example question (Turkish, one line plus prices): "Kapak ayrı parça olsun mu? Tek parça: 40 kredi. Parçalı (generate_parts + doku): 40 + 20 kredi."

## 6. Image pre-steps (paid, optional)

When only one image exists or a view is broken: `image_to_multiview` (10) or `edit_multiview` (5 per view). Offer the free fix in the user's image tool first (`image-preflight.md`), and mention these only as the paid alternative.

## 7. Characters and anything to be rigged

- The reference must pass the A-pose check before generation (`image-preflight.md` item 7): arms about 40 degrees from the body, elbows slightly bent, hands open and empty, legs slightly apart, clear gaps. The default is A-pose (B6); Tripo's docs suggest a T-pose, and the comparison is a first-paid-run lesson.
- Held props are separate models attached in the engine.
- Plan the rig steps after generation and all fixes (`rigging.md`); the free `rig-check` runs on the final mesh.

## 8. Never at generation time

`orientation`, `export_orientation`, `auto_size`: direction, scale and pivot are set locally from the placeholder (`normalize.py`, `godot.md`). `export_orientation` on a generation step is not inherited by later steps and gives a silently mis-oriented result. `tripo_plan.py` drops all three.

## 9. Re-rolls and files

- Re-roll cap: 2 regenerations per asset (B11). When the defect comes from the image (three-quarter view, copied back, fused prop), fix the image first; a new generation from the same image repeats the defect.
- Folder layout per asset (under `profile.json` `paths.art_source`, a git-ignored tree with a `.gdignore`):

```
<art_source>/<kind>/<id>/
  refs/                 reference images (inputs, hashed into provenance.json)
  raw/<label>/          untouched Tripo output, frozen (run tripo from here)
  work/vNN.blend        editable source, one per fix-recipe run (+ vNN.glb, export.sh)
  fixes/<id>.recipe.json
  qa/raw/, qa/vNN/      qa.json, sheet.png, report.md (raw output, work/vNN: same vNN)
  export/               the GLB that goes to Godot
```

- Labels: `<asset>-<kind>-vNN` (`crate-generate-v01`, `crate-decimate-v01`). Bump `vNN` for every new paid attempt.
- State: after the plan, `asset_state.py update <project> <id> --phase plan --append chain=<entry>` with `{"label", "task_id": null, "kind", "model", "credits": null, "status": "planned", "params"}`; after the run, `--chain-update <label>=<json>` with `task_id`, `credits` and `status`.

## 10. Worked plans (prices from 0.9.0 dry-run estimates and the price table)

| asset | plan | credits |
|---|---|---|
| hard-surface large prop, 3 views, PC | v3.1 multiview, v3.5 + delight, standard texture, no limit; then decimate v3.0 + smart_uv to 15000 | 30 + 35 = 65 |
| round small prop, 1 image, mobile | v3.1 image, v3.5 + delight, `face_limit=800`; measure | 30 |
| low-poly stylized prop, P1 | `--model tripo-p1`, `face_limit=3000`, textured image input | 50 |
| hero prop, detailed texture | v3.1 multiview, `texture_quality=detailed` | 40 |
| rigged NPC, A-pose views | v3.1 multiview (30), Blender fixes and decimate locally or v3.0 (35), rig-check (0), rig (25 + unknown import), animations 10 each | 55 to 90 + animations |
