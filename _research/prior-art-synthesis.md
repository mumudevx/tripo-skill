# Prior-art synthesis: what the user already does by hand (GRIME + PATINA)

Inputs (the workflow passed "undefined" paths; these are the five prior-art notes actually in `_research/`):
`prior-grime-docs.md` (GD), `prior-grime-tools.md` (GT), `prior-grime-fixes.md` (GF), `prior-patina-docs.md` (PD), `prior-testset.md` (TS).
Generic notes skimmed for overlap: `game-ai-mesh-qa.md`, `game-pipeline-editability.md`, `game-polycount-lod.md`, `game-topology-rigging.md`, `game-uv-textures.md`, `tripo-generation.md`, `tripo-platform.md`, `tripo-processing.md`, `tripo-animation.md`.
GRIME = `/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay` (stylised toy props, flat albedo, Blender fixes). PATINA = `/Users/muhsin/Documents/GitHub/mumudevx/patina` (stylised-realistic antique parts, PBR, fixes in Godot generator scripts). Both: Godot 4.7.2, tripo-cli 0.6.1, Blender 5.2.3 at `/opt/homebrew/bin/blender`. Neither project has a `.claude/` dir yet.

---

## 1. The ACTUAL pipeline (merged), and where time/credits were lost

| # | Step | GRIME practice | PATINA practice | Time / credit sinks observed |
|---|---|---|---|---|
| 1 | Concept / manifest | per-object spec in `art_src/refs/specs.py`; sheet prompt template `sheet_green.prompt.txt` | `art_source/<kind>/<id>/parts.json` (`subject`, `parts[]` with `faces` per face, `view_set`, per-view notes) | content rethinks mid-art (storage box → pedal car, GD 2.8) |
| 2 | Style anchor | one approved single-object ref (`art_src/backyard_v2/pedal_car.png`) + byte-identical `tools/style/style_formula.txt` | `_reference_sheet.png` of whole object (assembled + parts) + byte-identical `STYLE`/`SUFFIX` in `asset_concepts.py` | multi-object style ref leaked ghost items into single-object images (GD 3, icons) |
| 3 | Reference images | ONE image holding 4 ortho views (+4 close-ups) on chroma `#00B140` (Gemini `gemini-3-pro-image` via `tools/gen_image.py`, later Higgsfield `nano_banana_pro`, 4 cr) | hero (3/4) against ref sheet, then front/left/back/right EACH as its own image against the hero (Gemini `gemini-3.1-flash-image`, 1K, Batch API at half price), white bg, ffmpeg contact sheet `_sheet.png` | **biggest sink**: 2–3 sheet rounds per complex object (tool chest, jerry can, glider, red planet, camera back ×3); side views drawn 3/4; right = copy of left; glass tinted by chroma |
| 4 | View prep | `tools/key_views.py`: key, despill, split 4 largest components, shared scale + ground line, 1024², `preview_white.png`; L/R IoU dedup in `make3d.py` | none needed (separate images) | splitter fragile (ground lines, two-row sheets, floating parts → `--gaps`, `--keep-thin`, glider cut by hand) |
| 5 | Gate A | owner approves sheet before 3D (policy, `docs/later.md`) | owner approves `_sheet.png` (`CLAUDE.md:234`) | gate existed but was a chat step, not tooling |
| 6 | 3D generation | v1 P1 `image_to_model face_limit 8000 pbr off` (50 cr) → v2 `multiview_to_model --model v3.1 smart_low_poly face_limit 8000 pbr off texture_quality detailed texture_alignment original_image` (50 cr) → v3 Higgsfield `tripo_h3_1_multiview_to_3d` (12 cr, bosses 18) | `tripo generate multiview-to-model … --model tripo-v3.1` **no face_limit** (30 cr, ~1.4M tris) then `tripo mesh decimate <task> --model v3.0 --face-limit N --smart-uv` (35 cr) = 65/part | re-rolls: garage 4/12 objects needed 1–2 extra runs (~300 cr); jerry can 3×50; PATINA A/B tests on shutter/back panel; unlabeled `tripo-out/users-muhsin-…-<id8>` dirs hard to pair |
| 7 | QA | `tools/blender/qa_render.py` (4 ortho + iso + iso_wire, **flat albedo**, JSON: tris, sliver %, lowest_pct per footprint third) → `tools/qa_models.py` self-contained HTML (old vs new from git LFS, in-game capture) ; three.js `model_viewer.py` / `model_compare.py` from game camera | `scripts/dev/model_turnaround.gd` (8 views, tris + AABB), eyes; in-game screenshots to `ingame/` | flat-albedo renders missed shading defects → owner found them later in lit viewer/game; every fix was triggered by owner eyes, never by a metric (GF 0.1) |
| 8 | Fix | Blender: `place_model.py` → `clean_model.py` (join, decimate, yaw, fit, origin, 1 mat, 1K) then hand-written `fix_<id>.py` (23 scripts, 30–244 lines, hard-coded metre boxes) on kit `mesh_fix.py`/`mesh_paint.py`/`keep_normals.py`/`fix_common.py`; paid `texture_model` retexture (20 cr) twice | GLB shipped byte-identical; fixes in GDScript generators (scale-press, offsets, `NO_NORMAL_TEXTURE`, `dark_tint`, glass shaders, hard-edge normals `normal_crease.gd`, `mesh_reducer.gd`); paid fixes priced in `docs/later.md` (65/part) | **2nd biggest sink**: one-off fix scripts with hand-measured constants; wrong-side fix on traffic light; two overlapping normal-keeper modules; constants break if yaw/height change |
| 9 | Place | `tools/place_model.py <id> raw.glb [--yaw -90] [--max-tris] [--height]`: reads placeholder `.tres` bounds height, rewrites WHOLE `.tscn` as wrapper (same root name + unique_id, child `Model`); batch `tools/place_refs.sh` (`place <zone> <id> <yaw> [fix]`, `H=` override) | generator script per object (`generate_<obj>_models.gd` + `ModelKit.lay()/prop_node()`), mesh cached to `meshes/<model>.res`, scenes never hand-edited; keep node names/sockets | yaw guessed per object (−90 default; 90/180/0 for ~10%); height overrides for long objects; Blender exit 0 on exception → scene pointed at stale glb silently |
| 10 | Post-place | prints (does not run) `bake_silhouette.gd`, `check_import.sh`, `run_tests.sh`, balance sim | `check_import.sh`, budget tests (`test_performance_budget.gd`, `test_model_fidelity.gd`) | re-measure feature points (lance tip, grip) after every swap; gameplay time shifted 5.23 h → 6.29 h |
| 11 | Log | `docs/asset_log.md` row per id (task id, params, credits, fixes, owner quotes with dates); ADR with cost summary | `docs/asset_log.md` row per asset group (licence focus); recipes in `CLAUDE.md` with date+object; `docs/later.md` weak models with priced fix; `docs/questions.md` | rows appended after the wrong section; docs drifted (GDD still says Meshy; P07 still says `--model tripo-p1`; budget 8k vs 12.4k kept silently) |

Owner policy shift (GRIME, 2026-10-30): remaining zones "placed unfixed, flaws fixed as they show in play". Gate B (QA page) and Gate C (placement) were real approval points before that.

---

## 2. Deduplicated lessons

Legend: **[G]** general → seeds `lessons/general.md` (still needs user approval to promote). **[C]** conditional/contested between the two projects → general only as a decision rule. **[P-GRIME]/[P-PATINA]** project-only. Evidence in brackets points to the source note + original file.

### 2.1 Reference image (pre-flight review)
- G1 [G] One object per image; never feed a multi-object sheet to 3D (it fuses). Multi-object sheets are style refs only — and even as refs they leak ghost content; prefer a single-object anchor. [GD 2.1, TS R4, GD 3 icons]
- G2 [G] Multiview (2–4 ortho views) over single image. Single image → hidden-side guessing: pool pink on inner wall, mailbox toothed lid, bicycle slivers 2.5% → 0.8%. [GD 1 v1, PD 2.1, TS T9]
- G3 [G] Style formula byte-identical in every prompt incl. re-rolls; description before, framing suffix after. [GD 2.1, PD 2.1] (matches user global CLAUDE.md)
- G4 [G] Pre-flight checklist (each item burned credits when missed):
  - side views truly orthographic, not 3/4 (jerry can v1, camera back ×3) [TS R5, R10]; fix: say "front face not visible", or generate the view from `front.png` instead of the hero [PD 2.1]
  - right view is not a copy of left (IoU same vs mirrored) [GD 2.1, `make3d.py`]
  - Tripo side convention: in `left.png` the object's front points to the image's left edge; name files by what the image shows (swap → slot on both faces) [PD 2.1]
  - a lying/all-round part's back = front **mirrored**, never copied (two screwdrivers) [TS R11]
  - count unique features (one handle, one cap); state asymmetric features per side ("plain sides and back"), describe every face incl. top/back/underside [GD 2.1, PD `faces`]
  - no prop crossing head/torso (telescope through head) [TS R6]
  - open cavities need a view into them, else Tripo lids them (pickup bed ×2) [TS R8]
  - "sits directly on the ground, no base plate/slab; no shadow, no floor, no ground line" [GF D8]
  - transparent parts: never over chroma; describe glass as opaque painted panel [TS R9, GF D11]
  - views on one row, each fits its quarter [TS R9]
  - say what colour must NOT appear ("nothing green") — generators drift to palette accents [GD 2.1]
  - ≥1K per view (512 px → jumbled model) [TS R12, PD 2.3]
  - real file format (≈18% of ".png" are JPEG bytes in both projects) [TS 0]
  - thin parts (< ~5% of length: slats, plates, envelopes, spokes, discs) → warn and plan a fix [TS 4.5]
- G5 [G] Avoid lighting/AO words in the concept prompt when the engine lights the asset: Tripo bakes concept shading into albedo (GRIME style formula asks for "key light… ambient occlusion" → baked shadows/wrinkle paint). [GF D6, 5.4] Cross-ref `game-uv-textures.md` §3.2.
- G6 [G] A good reference does NOT guarantee a good back: Tripo still copied lamps onto a drawn plain back (traffic light). QA must check back/far side regardless. [TS R3, T7]
- G7 [G] One view that disagrees with the others gets re-rolled, not kept. Save money with fewer views (1 for all-round part, 2 for thin part), never lower resolution. [PD 2.1, 2.3]
- G8 [G] Organic/planet forms: ask for irregularity ("NOT a perfect sphere"). [GD 2.1]

### 2.2 Generation planning
- G9 [G] Always pass `--model` explicitly (CLI 0.6.1 silently switches to P1 at face_limit ≤ 20000 and strips H-only params; PATINA mailbox v1 really ran P1 at 50 cr). [PD 2.2, `tripo-generation.md` §10.2]
- G10 [G] `face_limit` is not a tri cap: v3.1 + smart_low_poly 8000 → 7.4k–17.4k (tool chest g1 17,430; pedal car 12,367/10,000); decimate v2.0 20,000 → 29,943. P1, v3.1 without slp, H3.1-Higgsfield, decimate v1.0 stay under. **Measure the GLB**, report budget deviation explicitly. [TS 3, GD 2.2, GD 6]
- C1 [C] **face_limit at generation vs full-res + decimate** — the two projects disagree; it is a style rule:
  - chunky/toy, few holes (GRIME): `face_limit` at generation acceptable; slp cut slivers 3–20× vs P1.
  - hard-surface with holes/slots/thin plates (PATINA): never limit at generation (waves, holes→dents); generate full (30) then `mesh decimate --model v3.0 --smart-uv` (35, re-bakes textures/normals). v1.0 decimate (10) keeps high-poly normal map → fans/creases; v2.0 dishes/spikes; slp worse. Pick decimate target by eye, lowest first (knob 3k, 45-hole panel 12k). [PD 2.2, TS T10, T11]
- C2 [C] `pbr`: off for flat-albedo/custom-shader games (GRIME), on otherwise (PATINA). Ask per project.
- C3 [C] `texture_quality/geometry_quality detailed`: GRIME used texture detailed; PATINA measured detailed = 60 vs 30 cr and lumpier printed detail after reduction → off. Default off, offer as option.
- G11 [G] `texture_alignment original_image` follows reference colours better than `geometry` (GRIME switched); but expect ~25% saturation loss through image-to-3D → push reference saturation or plan colour pass. [GD 2.2]
- G12 [G] Retexture (`texture_model`, 20 cr) before re-modelling when only colour is wrong — but it is a coin flip (bench/mower better, pedal car worse); always A/B. `texture_prompt` not accepted on multiview generation. [GD 2.2, GF 1]
- G13 [G] Measured price table (task.json `credits_consumed`): P1 50; v3.1 multiview std 30; v3.1+slp+tex detailed 50; geom+tex detailed 60; retexture 20; decimate v1.0/v2.0/v3.0 = 10/30/35; rig-check 0; rig 25; Higgsfield H3.1 12 (bosses 18, statue 16). Typical finished part 65 (PATINA). Budget 25–35% re-roll overhead for mechanical objects; cap 2 re-rolls/object then take best. [TS 3, GD 2.2, PD 2.3]
- G14 [G] Credit hygiene: `tripo balance` before and after (generate has no dry-run; use `tripo make … --dry-run --json` to validate); exit 4 out of credits → stop; exit 6 timeout → `tripo task watch <id> --download`, never resubmit; exit 7 → check balance/frozen first; failed tasks are not charged. Log a running balance with "what it buys". [PD 2.3, `tripo-platform.md` §1]
- G15 [G] Always pass a label/name so `tripo-out/<label>-<id8>` pairs with the asset. [TS 0]
- C4 [C] Higgsfield `tripo_h3_1_multiview_to_3d` was cheaper and smoother than direct v3.1 for GRIME's spray gun (16 vs 50, 5.9k vs 13.2k tris, "lumpier"); PATINA judged earlier Higgsfield single-image calls "no better" and Higgsfield was suspended there on 2026-10-10. The skill is tripo-cli-only, but record the comparison as a known alternative. [GD 1 v3, PD 2.2]

### 2.3 QA
- G16 [G] Check all sides, not `preview.png`: front, back, left, right, top, underside, iso; with wireframe on all. [PD 2.4, GT 1.10]
- G17 [G] QA needs a **lit** render (studio/matcap) next to flat albedo; most owner complaints (waves, star fans, dark wedges) are invisible in albedo-only renders. Also render with normal map off before blaming a mesh (radio glass/back panel were the normal texture). [GT 1.10, PD 2.4]
- G18 [G] Review from the game camera first (dir + FOV from the project), at gameplay distance, then orbit; turn the object. [GT 1.3, PD 2.4]
- G19 [G] Weld (1e-4 m) before any topology metric: Tripo GLBs are split at every UV seam; islands/holes/boundaries are meaningless unwelded. [GF D9, GT 3.2] (agrees with `game-ai-mesh-qa.md` check #9)
- G20 [G] Cheap metrics worth keeping: tris vs budget; sliver % (area/longest_edge² < 0.02; flag > 3%; weak signal, not a gate); `lowest_pct` per footprint third (caught 8° belt slope, objects floating 4–10 cm); L/R mirror distance for symmetric objects; boundary-edge count after weld (cracks). A "long sliver" metric was tried and removed (did not separate). [GT 1.10, GF 4, GD 2.3]
- G21 [G] Tripo defect frequency (GRIME 22 fixed assets, ~60% hidden-side): back copies front detail; wrinkled flat panels (3–6 mm); smooth-normal dark wedges at cylinder/cap joins and star-shaded flat discs; stray/fused parts (ground slabs/discs, extra hand, chain link, helper icosphere); lidded cavities; paint bleed/off-palette lines; shell cracks; broken glass; thin parts thick (letter "as a parcel"); holes embossed/slots painted; round outlines polygonal (~24 seg); invented details; wrong-material colour (olive leather). [GF 2, PD 2.4]
- G22 [G] Generated models have no hard edges: per-edge split at ~30° (not per-corner — that broke 1/5 soft edges); keep smooth normals elsewhere for outline shaders. [PD 2.4]
- G23 [G] Glass always comes out opaque/painted; plan opaque panes or a separate glass model/shader. [PD 2.4, GF D11]

### 2.4 Fixes
- G24 [G] **Normals policy (most reused lesson):** never recompute normals globally on Tripo output — recomputed smooth normals reveal waves Tripo's normals hide. Keep exported custom normals on untouched triangles; write analytic normals (flat/radial/spherical) only on edited faces; apply re-ground shifts at export after matching. Much "dent" feedback is normals, not geometry. [GF D5, GT 3.1] **Conflicts with** `game-ai-mesh-qa.md` §5 "Normals: recalc_face_normals" and check #22 "custom split normals cleared after edits" — the prior-art rule wins for Tripo output.
- G25 [G] Fix ladder, cheapest first: (1) engine-side scale/shader/material/offset; (2) headless Blender op; (3) paid retexture (20) for colour on a good mesh; (3b) paid re-decimate v3.0 (35) when only the normal texture is wrong; (4) new generation only for broken geometry; plus explicit "place as-is, fix later". [TS 4.7, PD 2.5, GD 2.4]
- G26 [G] Regenerate when a major part is missing/duplicated or the reference was wrong (fix the sheet first; a simpler reference often beats surgery); Blender for surface noise, back copies, strays, colour, symmetric halves. [GF D13, GT 1.15]
- G27 [G] Parametric free-fix operators that covered all 23 GRIME scripts: weld+triangulate; `flatten_planes` (depth-histogram layers, tol 5–8 mm, colour excludes); `press_relief` + delete coplanar inner faces (else z-fight rings); `fit_primitive` plane/cylinder/sphere/revolution/extrusion + analytic normals; `mirror_half` (keep overlap strip, reverse winding, negate normal axis) / `clone_part`; delete → drop shreds → cap (custom loop filler; `holes_fill` skips) → taubin → paint; `remove_ground_slab` + reground; `weld_boundary`; `carve_cavity`; `replace_glass`; `recolour`/`even_out`/`hsv_transfer` keeping relative luminance; procedural overlay (grain); `free_atlas_square` (Tripo 1K atlas ≤ ~50 px free; mind 8-px JPEG blocks). [GF 3]
- G28 [G] Painting: rasterise UV triangles and dilate 1–6 texels (thin triangles miss texel centres); target colour = median of a clean sample region; select by 3D texel position when UV triangles straddle islands; hole caps land on one UV point → move to a painted texel. [GF 5.8–5.9]
- G29 [G] Fix scripts are re-runnable from raw GLB, one per model, carrying the owner's review note + date in the docstring; store region params **relative to bbox** (GRIME's absolute metre constants break on re-placement). Run fixes on the normalised model (front −Y Blender, base z=0, metres). [GF 5.14, GT 2.4]
- G30 [G] A model loses triangles only for a budget; when a set is over budget, compare old/half/quarter/whole side by side and spend tris where halving crumples. [PD 2.5]

### 2.5 Rigging (GRIME only; PATINA never rigged)
- G31 [G] Run free rig-check before paying for rig. Fused held props → not riggable; regenerate "holding NOTHING", props as separate models attached in-engine. GRIME's A-pose (~40°, open empty hands, gaps) passed. [GD 2.5, TS T5] Note: Tripo docs/CLI recommend T-pose (`tripo-animation.md` §6) — A-pose is a measured pass, not a documented rule.
- G32 [G] Rig output: 27 joints `tripo::…` (non-Mixamo), 0 animations, a stray `Icosphere*` helper mesh to drop; Godot renames `::` → `__`; rig-check verdict is not in `task.json` (read CLI output). Don't touch transforms on rigged output. GRIME used CLI-default rig `v2.5-20260210`; docs recommend `v3.0-20260909` for humanoids. [TS T5, GT 1.9, `tripo-animation.md`]

### 2.6 Placement into Godot
- G33 [G] Swap by interface: keep scene path, root name, `unique_id`s, node names, sockets, collision, scripts, data; replace only the placeholder visual subtree. (GRIME's whole-file rewrite only worked because object scenes held nothing else.) [GT 1.2, PD 2.6]
- G34 [G] Scale from the placeholder's measured extent along a chosen axis (default height, uniform); long/flat objects fit by dominant dimension; origin at base centre (or top/levelled surface). [GT 3.5]
- G35 [G] Orientation: most Tripo outputs face +X (yaw −90 → Godot +Z) but ~10% needed 90/180/0; decide the front from a semantic feature (visors, hose outlet), confirm with the user from a 4-view render. Never set `orientation`/`export_orientation`/`auto_size` at generation (not inherited, silently mis-oriented). [GT 3.4, PD 2.2]
- G36 [G] Name the GLB image after the asset: Godot "extract textures" writes `<glb>_<image name>.<ext>`. [GT 3.17]
- G37 [G] After swap: run project import check + tests + project re-bakes; flag gameplay side effects (silhouette, measured feature points, balance, cold-load time, interaction-zone collisions); payoff animations key scale as a share of rest scale. [GD 2.6, PD 2.6]

### 2.7 Logging / process
- G38 [G] Three approval gates: reference → (QA page) → placement; never spend credits without approval; report image cost/count before an image run. [GD 2.8, PD 2.3]
- G39 [G] Log every generation at creation: tool+model+CLI version, task id(s), params, credits, refs/prompt path, QA numbers, fixes (script path), yaw/height, owner quote+date, superseded-by; failed attempts keep their task ids and credits. Provenance sidecar (`.prompt.txt` / task.json) next to every artefact. Lessons recorded with date, object, measured numbers, "not verified" flag. [GD 2.7, PD 2.7, GT 1.7]
- G40 [G] Treat the project's `CLAUDE.md` asset section + recent ADRs as authoritative over older GDD text (both projects have stale Meshy text). [PD 5.7, GD 6]

### 2.8 Project-only lessons (seed `<project>/.claude/tripo/lessons.md`, do not promote)
**GRIME:** class budgets A ≤8k (12–12.5k accepted for v3.1 vehicles), B ≤30k (face_limit 20000), C backdrops 2–5k @512 px, 1 mesh / 1 material / 1K JPEG, `pbr=false`; data chain `data/objects/<zone>/<id>.tres` → `scenes/objects/<zone>/obj_<zone>_<id>.tscn` → `assets/models/objects/<zone>/<id>.glb` (bosses `assets/models/bosses/`, crew `assets/models/crew/`); root `obj_<zone>_<id>`; game camera (0.94, 2.09, 3.50) FOV 22°, object ~45% frame width, boss ~75%; after swap `bake_silhouette.gd -- <ids>` (mandatory, test fails on stale mask) → `check_import.sh` → `run_tests.sh` → balance sim; dark smudges "read as dirt" (cleaning game); glass = opaque painted panes (one opaque material); chroma `#00B140` sheets + `key_views.py`; style formula + `pedal_car.png` anchor; Filmic tonemap; Git LFS for glb/png/jpg; windowed Godot runs must not steal focus (`run_quiet.sh`); "placed unfixed" policy from 2026-10-30; owner docs Turkish, code/ADRs English.
**PATINA:** budgets part 12k, antique 60k, scene 500k, <300 draw calls (Steam Deck 60 FPS), enforced by tests; `tripo-v3.1` for all parts, P1 only for far background ~3k; PBR on; never quad/slp/generate_parts/compress/auto_size/orientation/`--for`; parts naming `part_<id>`, `socket_<id>`, `part_<id>-convcolonly`, `solder_a/b`, files `<id>_<model>.glb`; GLB shipped untouched, fixes in `generate_<object>_models.gd` + `ModelKit` (generators re-assign unique_ids → `git checkout -- scenes` for unintended changes); shaders `antique_master` (`dark_tint`), `antique_glass` (`glass_by_coolness`), `prop_surface`; smooth normals stored in `CUSTOM0` for outlines; every part AI-generated incl. screws (owner ADR 2026-10-07); credits name no AI tool (test-enforced); Gemini key in env only; white-bg views, not chroma.

---

## 3. Reuse map

### 3.1 → skill `scripts/` (generalised)
| Skill script | Sources | Must change |
|---|---|---|
| `glbstat.py` (zero-install preflight: tris, meshes, materials, images, skins, joints, magic-byte check) | scratch `glbstat.py` from TS | stdlib only; JSON out |
| `prep_views.py` (sheet → views, or validate separate views) | GRIME `tools/key_views.py`, L/R IoU dedup from `art_src/refs/make3d.py`, magenta auto-switch + premultiplied downscale from `tools/key_icon.py` | argparse; explicit view→Tripo-arg mapping (side convention); fail with a preview instead of exit; also accept PATINA-style separate files (white bg) |
| `preflight_ref.py` (automatable G4 checks) | TS §2 R1–R12 set as test fixtures | L/R copy/mirror IoU, ≥1K, real format, one row, chroma vs glass hint, thin-part warning; rest stays a vision checklist |
| `blender/normalize.py` | `tools/blender/clean_model.py` | `--python-exit-code 1` + output mtime check; weld before islands; `--fit` axis + explicit dims; keep custom normals; no forced-square textures; image named after asset; JSON report; refuse rigged input |
| `blender/normalize_rigged.py` | `tools/blender/clean_rigged.py` | detect helper by size/geometry not name; optional keep animations; keep aspect |
| `blender/qa.py` | `tools/blender/qa_render.py` + PATINA `model_turnaround.gd` (8 views) | add lit/matcap + normal-map-off renders, game-camera render, wireframe on all views, iso framing from projected bounds, clip_end by size; metrics: tris vs budget, sliver %, lowest_pct, boundary edges after weld, islands, L/R mirror distance, planar RMS (wrinkles), hard-edge share, off-palette clusters; stable JSON schema. Merge with detector code in `game-ai-mesh-qa.md` §4 and `game-pipeline-editability.md` §15.1 (both tested on 5.2.3) |
| `qa_page.py` | `tools/qa_models.py` | engine-agnostic inputs (glb list, optional old glb from git/LFS, optional game shot, refs); no CDN fonts; English (Turkish optional) |
| `viewer.py` (single + `--compare`) | `tools/model_viewer.py` + `tools/model_compare.py` | camera dir/FOV from project; per-entry yaw; vendored three.js; run in background and kill; keep `no-store` + `?m=&cam=` screenshot hooks |
| `blender/fixkit/` | `mesh_fix.py`, `mesh_paint.py`, `fix_common.py` + `keep_normals.py` (merge into one `NormalKeeper` snapshotting in the constructor) | bbox-relative tolerances; operators from G27; fix-script template with review-note docstring |
| `godot_place.py` | `tools/place_model.py` (identity-preserving swap) + PATINA generator pattern | surgical `.tscn` edit of the placeholder subtree only; measure placeholder AABB (parse primitives or headless Godot); show diff, wait for approval; then `godot --headless --import` + project check commands from config |
| `log_asset.py` | GRIME + PATINA `docs/asset_log.md` formats, `gen_image.py` `.prompt.txt` sidecar | write `<asset>.provenance.json`; insert row in the right table section (GRIME appended after the disclosure block) |
| `tripo_run` wrapper (or recipe in SKILL.md) | PATINA `CLAUDE.md:235-247` exit-code rules, `run_tripo.sh`, `make3d.py` idempotent skip | balance before/after, `--model` always, label always, `make --dry-run --json` validation, exit 4/6/7 handling; ties to `tripo-platform.md` §1 |

Optional backend (not tripo, user may prefer Higgsfield/Tripo t2i): `scripts/dev/asset_concepts.py` (manifest → hero → views → contact sheet, skip-existing, prompt `.txt` beside each image) and `scripts/dev/gemini_image.py` (direct + Batch API half price, resume, token report). Port the manifest schema (`parts.json` with `faces`, `view_set`, `views`) as the skill's spec format regardless of image backend.

### 3.2 → `references/`
- `defect-catalogue.md`: GF D1–D13 (cause → detection → recipe → prevention) + PATINA weak-model list; merge with `game-ai-mesh-qa.md` §2 (generic) — prior-art version is Tripo-specific and wins on conflicts.
- `fix-examples/`: 4–5 representative `fix_*.py` (anchor = delete/fill, tool_chest = mirror+press, fire_hydrant = primitive fit, phone_booth = slab, bus_stop = glass) as worked examples, not runnable tools.
- `sheet-prompt-template.md`: `sheet_green.prompt.txt` (statue v2, traffic light) + PATINA STYLE/SUFFIX + view-note fixes.
- `price-table.md`: G13 measured prices merged with `tripo-generation.md` §2 / `tripo-processing.md` §0.4 / `tripo-platform.md` §1 (prior-art = measured, docs = listed).
- `godot-placement.md`: identity-preserving swap, ModelKit `lay()` axis mapping, glTF texture extraction naming, `::`→`__` bone names.
- `testset.md`: TS T1–T12 + R1–R12 paths as regression fixtures (read-only inputs for skill evals).
- `recipes-by-style.md`: C1–C3 decision table (chunky vs hard-surface; pbr; detailed).

### 3.3 Dropped
- Per-model `fix_<id>.py` constants; `backyard_scene.sh`, `place_refs.sh` (project batch lists; keep only the "re-runnable chain" idea); `bake_silhouette.gd`, `capture_object*.gd`, `run_quiet.sh` (GRIME-only; become project config hooks); GRIME `.tres` lookup; PATINA `normal_crease.gd`/`mesh_reducer.gd`/`model_kit.gd` as code (Godot-side; replaced by Blender Smooth-by-Angle + Decimate, but keep "generator script, never hand-edit .tscn" as an option); Higgsfield calls (`make3d.py` generate part); `key_icon.py` 2D pipeline; GDD Meshy text.

### 3.4 Overlap with generic notes
| Topic | Prior art | Generic note | Resolution |
|---|---|---|---|
| QA detector | `qa_render.py` (renders + 3 metrics) | `game-ai-mesh-qa.md` §3–4 (23-item checklist, tested bpy), `game-pipeline-editability.md` §15.1 audit, `game-polycount-lod.md` §7a `mesh_stats.py`, `game-topology-rigging.md` §4 | One `qa.py`: generic topology/UV/budget checks + prior-art renders/lowest_pct/sliver + Tripo-specific detectors |
| Normals | keep Tripo normals (G24) | generic says recalc/clear custom normals | prior art wins for Tripo output; note the conflict in SKILL.md |
| Weld | 1e-4 before topology | same (#9; Blender default 1e-4) | agree |
| Fix menu | ladder G25 + operators G27 | `game-ai-mesh-qa.md` §5 menu, `tripo-processing.md` §9 cheat-sheet | merge into one free-vs-paid table; add measured prices |
| Budgets | per project (8k/30k; 12k/60k) | `game-polycount-lod.md` §2 tables | generic table as defaults only; project config overrides |
| face_limit / decimate | C1, G10 measured overshoots | `tripo-generation.md` says "always set face_limit" | conflict: prior art says no limit for hard-surface; skill should present C1 rule |
| Facing / units | yaw guessed, +X | `game-pipeline-editability.md` §1 (+Z glTF, −Y Blender) | agree on target; prior art adds "measure, Tripo is unreliable" |
| Baked lighting | G5 (prompt cause) | `game-uv-textures.md` §3.2 detection, `tripo-processing.md` delight (v3.5, CLI 0.6.1 rejects texture v3.5) | combine prevention (prompt) + detection + paid delight option |
| Rig | A-pose pass, v2.5, Icosphere | `tripo-animation.md` (T-pose advised, v3.0 recommended, retarget 10/anim), `game-topology-rigging.md` | prior art = one data point; docs = default |
| Credit safety | exit codes, balance diff | `tripo-platform.md` §1 (identical + dry-run only on `make`) | agree; platform note is the fuller source |
| `.tripo/context.json` | only `last_task_id` observed | `tripo-platform.md` §13 (written on every real run; `output_dir` consumed) | adopt: run from asset dir, gitignore `.tripo/` |

---

## 4. Conventions the skill must adopt

- **Raw vs shipped split:** raw work in a git-ignored, `.gdignore`d source tree (`art_src/` GRIME, `art_source/` PATINA); only final GLBs under `assets/models/…` are imported. Skill should detect the existing name, not impose one; default `art_source/` if none. Rejected attempts kept on disk (`old/`, `v1/`, `tripo_raw_rejected/`, `sheet_green_r*.png`, `*_bad.glb`), never deleted.
- **Per-object raw layout** (PATINA is the cleaner template): `<src>/<kind>/<id>/{parts.json, concept/_reference_sheet.png, concept/<part>/{hero,front,left,back,right}.png + .txt prompt, _sheet.png, tripo_raw/<part>/{full,reduced}/tripo-out/<label>-<id8>/{task.json,model.glb,preview.png}, final/, turn/, ingame/}`. GRIME Higgsfield layout `{sheet_green.png, views/, model_h31.glb, .orig.glb, placed.glb, fixed.glb}` shows the useful raw → placed → fixed stage names.
- **.tripo/context.json:** written by every real submission (`last_task_id`) into cwd or nearest ancestor; both repos gitignore `/.tripo/`. Skill: run tripo from the per-object raw dir (or set `output_dir` via `tripo config context`), verify `.tripo/` is ignored, always `--name`/label.
- **asset_log.md:** both projects keep `docs/asset_log.md` (licence / Steam AI-disclosure evidence). GRIME columns `id | class | tool | date | prompt or source | license | notes` (tool = generator → Tripo version (tripo-cli version); prompt cell holds sheet path, style formula path, 3D params, task id, credits; notes hold placement args, tris, texture, yaw, fixes with owner quotes+dates, replaced-by). PATINA columns `asset_path | source_tool | plan/license | generation_date | prompt_ref | human_edited | notes`. Skill: append to the project's existing log in its own format (detect header), into the right table; keep its own structured log in `<project>/.claude/tripo/`.
- **Naming:** GRIME `obj_<zone>_<id>`, `boss_<zone>`, `bg_<zone>`, `eq_<tier>`, variants `<id>_v<n>`; PATINA `<id>_<model>.glb`, `part_<id>`, `socket_<id>`, `-convcolonly`. Skill: read from project config, root/material/image named after the asset.
- **Godot import habits:** default glb import + `gltf/embedded_image_handling=1` (extract textures → `<glb>_<image>.jpg`, lossless, mipmaps); GLB as `.glb` only; GRIME 1K JPEG single image, PATINA 3 PBR images as delivered; scripted placement (wrapper scene with `Model` child, or generator script) — never hand-edited `.tscn`; post-swap `scripts/check_import.sh` (both projects) + tests; Godot binary pinned via `scripts/godot_bin.sh` (GRIME).
- **Review style:** self-contained HTML approval page; game-camera first; before/after split screen; owner quotes with dates in fix docstrings and log.
- **Language:** owner-facing docs Turkish, code/commits/ADRs English. Lesson files: ask; default English with Turkish user-facing summaries.
- **Git:** LFS for glb/png/jpg (GRIME); no AI attribution anywhere (user global rule); PATINA credits must not name AI tools.

---

## 5. Gaps — what the hand pipeline never solved

1. **Automatic defect detection**: every fix came from owner eyes; no detectors for back-copies, wrinkles, slabs, cracks, asymmetry, off-palette paint, missing hard edges (proposals in GF §4).
2. **Lit/shading QA**: renders were albedo-only (GRIME) or windowed Godot (PATINA); no lit + normal-off + game-camera render in one headless step.
3. **Orientation detection**: yaw guessed per object; a fix was applied to the wrong side (traffic light).
4. **Parametric fixes**: 23 one-off scripts with absolute metre constants; no bbox-relative operator library, no region picking from QA renders.
5. **Safe Godot placement**: whole-scene rewrite (GRIME) or bespoke generator per object (PATINA); no surgical placeholder-subtree swap with diff + approval; placeholder AABB only from GRIME's baked `.tres`.
6. **Silent failure handling**: Blender exit 0 on exception, Godot `open -W` exit codes, missing screenshots skipped.
7. **Credit estimate before run**: tripo-cli 0.6.1 dry-run has no numbers; budgets came from balance diffs and hand notes. No per-batch plan vs actual.
8. **Rigging depth**: one biped, no retarget/animation, no rig v3.0, no quadruped, no Godot skeleton/retarget setup; bones posed in code. PATINA none.
9. **LOD**: neither project made LODs (relied on Godot auto-LOD / none); PATINA reduced only for budget.
10. **Multi-part assembly**: PATINA did it by hand in generators (positions measured from case model); no tool for fitting parts to each other.
11. **Glass/transparency**: only workarounds (opaque panes, coolness shader).
12. **Thin parts**: known main failure class; no pre-generation strategy beyond prompt hints and post-scale press.
13. **Colour fidelity**: ~25% saturation loss noted, never corrected systematically; no palette check vs reference.
14. **Lesson capture**: lessons scattered in CLAUDE.md, ADRs, later.md, asset_log, docstrings; docs drifted (Meshy, P1, budget). No promotion path project → global.
15. **Provenance pairing**: unlabeled tripo-out dirs; rig-check verdict not stored; `boss_hangar/model_h31_bad.glb` rejection reason never logged.
16. **Re-placement stability**: fix constants break when yaw/height change; GRIME bounds re-bake makes re-runs scale to the new model.
17. **Texture/version upgrades**: texture v3.5 + delight unavailable in CLI 0.6.1 (needs `tripo update`, a user decision).

### Open questions for the user (the skill should ask, not guess)
- Default recipe per project style (C1–C3), or always ask at plan time?
- Is Higgsfield H3.1 still an allowed alternative route, or tripo-cli only?
- Rig pose default: A-pose (proven) or T-pose (Tripo docs)? Rig model v2.5 (proven) or v3.0 (docs)?
- Lesson-file language (Turkish vs English)?
- Default fix location: Blender-modified GLB (GRIME) or untouched GLB + engine-side fixes (PATINA)?
