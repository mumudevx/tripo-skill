# Game AI-Mesh QA: defects, detection, fixes (skill reference)

Scope: QA for meshes from Tripo / Meshy / Rodin / Hunyuan3D / TRELLIS(.2) before they go into Godot 4 / Unity / Unreal.
Verified on this machine (2026-10-31): **Blender 5.2.3 LTS** (`/opt/homebrew/bin/blender -b --factory-startup`), tripo-cli 0.6.1. `gltf-validator` and `@gltf-transform/cli` are not installed globally; run them with `npx`.

Tags:
- **[S]** a cited source states this.
- **[H]** a heuristic default chosen for this skill. Tune it on real Tripo outputs.
- **[V]** verified headless on this machine: the operator exists, the default was read from RNA, or the script ran on a synthetic test asset.

---

## 0. Ground rules

1. **Audit, report, ask, fix, re-audit.**
   - Run the detector (§4) and store the JSON.
   - Show the user each finding with its severity and fix options (§5).
   - Apply only the options the user approved, then re-run the detector after every step.
2. **Cleanup can create defects, so measure after every step** [S: QtMeshEditor PR #1102; bdeda TRELLIS.2 PR #1].
   - Raw TRELLIS.2 output had **0 boundary edges** in 6 of 6 generations. A weld at voxelSize/8 raised non-manifold edges from **1.8k to 20k**, and the meshopt simplify then flipped "hundreds" of edges.
   - Fixes: weld at voxelSize/64 (i.e. a tiny epsilon), and run debris cull plus winding unify **after** simplify as well as before.
3. **Keep the untouched original.** Every destructive op (voxel remesh, decimate, Quadriflow, symmetrize) must be followed by a bake from the original (§2.15) [S: Blender manual retopology; neural4d retopo guide].
4. **Free first.** Blender fixes cost nothing. Tripo fixes cost credits, and the account has about 35. Offer the Tripo route with its price and default to Blender. Never auto-run a paid fix.
5. **Units and axes.**
   - glTF: meters, +Y up, the asset front faces **+Z** [S: glTF 2.0 spec].
   - Godot and Unity: 1 unit = 1 m.
   - The Blender importer converts to Z-up, so the asset front is **−Y** in Blender [S: Godot model export considerations].
6. **Separate "real-time renderable" from "pipeline-safe".**
   - A GPU draws non-manifold and holey meshes without complaint.
   - The damage shows up downstream: baking, tangent generation, LOD generation, collision, rigging, voxel remesh and 3D print [S: gamedev.net non-manifold summary; CGTrader help]. Severity therefore depends on the **intended use** (§2 severity column).

---

## 1. Budgets per platform / asset class

### 1.1 Triangle budgets (LOD0, per asset)

| Asset class | Mobile / Quest / WebGL | PC / console (classic) | UE5 Nanite | Source |
|---|---|---|---|---|
| Clutter / background prop | 300–1.5k | 500–3k | any opaque/masked static | [S] neural4d (vendor) 500–3k; [H] mobile |
| Medium prop / weapon | 1k–5k | 3k–15k | any | [S] Meshy pipeline repo: mobile props 1k–5k |
| Hero prop / vehicle | 3k–10k | 10k–50k | any | [S] Meshy remesh doc: 20–50k PC/console, 5–20k mobile/web |
| Character (skinned) | 3k–15k | 15k–60k | see note below | [S] Tripo `--for game-mobile` = P1 + face_limit 15000; 80.lv: Tripo Smart Mesh character ≈20k |
| VR whole frame | Quest 2: 750k–1M; Quest 3/3S: 1.3–1.8M | – | Nanite does not support VR stereo | [S] Meta Unity perf guide; UE Nanite docs |

Nanite note for characters [S: UE Nanite docs, current]: skeletal meshes now have a Nanite path (one draw call per mesh, animation LODs instead of geometry LODs). It still does **not** support morph targets, translucency, forward rendering, VR stereo or MSAA. Keep classic budgets for blendshape faces, mobile, VR, Godot and Unity.

Raw output sizes:
- Tripo H-series / v3.x: "a few million polygons" [S: 80.lv].
- A Polycount artist's AI image-to-3D test came out at **about 500k tris**, against **about 130k** for the hand-optimised version [S: Polycount thread 238705, via search snippet].
- Hunyuan3D-2's own `FaceReducer` defaults to `max_facenum=40000` [S: postprocessors.py].
- TRELLIS.2 1024_cascade: **13M tris** before simplify [S: bdeda PR #1].
- **Assume every raw high-detail output fails the budget.**

Remesh triggers [S: Meshy remesh doc]: over 50k faces for PC games, over 10k for mobile.
Meshy bands:

| Faces | Use case |
|---|---|
| < 5k | Mobile AR / casual; detail loss noticeable |
| 5–20k | Mobile / web; minor loss |
| 20–50k | PC / console; minimal loss |
| 50–100k | High-quality renders |
| > 100k | Film |

Tripo knobs at generation time (cheapest, because they avoid a paid retopo):
- P1: `face_limit` 48–20000, tris only.
- P2: 48–50000 tri / 48–25000 quad.
- v3.x: `smart_low_poly` 500–20000 tri / 500–10000 quad.
- `quad=true` forces FBX output (no GLB).

### 1.2 Texel density and map sizes

| Camera / platform | Target | Source |
|---|---|---|
| Third-person (console) | 512 px/m (a 2k map covers 4 m) | [S] Polycount forum; Maxon 5.12 px/cm |
| First-person | 1024 px/m (1024–2048 for close props) | [S] Polycount; Maxon 10.24 px/cm; Strayspark |
| Mobile | 256–512 px/m | [H] |

- *Consistent* density across neighbouring assets matters more than the absolute value [S: Strayspark].
- Map sizes [H]:
  - Mobile: 512–1k.
  - PC prop: 1k–2k.
  - Hero: 2k–4k.
  - Tripo `convert` defaults to `texture_size` **4096**, so always set it. `--for game-mobile` sets 2048.
- Use power-of-two sizes. glTF-Validator reports `IMAGE_NPOT_DIMENSIONS` (Info).

### 1.3 PBR value ranges

Adobe Substance PBR Guide pt. 2 [S]:
- Dielectric albedo: darkest **30–50 sRGB** (30 tolerant, 50 strict), brightest **240 sRGB**.
- Metal albedo: **180–255 sRGB**.
- Metallic is ~binary: 235–255 for raw metal, 0 for non-metal.
- "Base color should be devoid of lighting information with the exception of micro-occlusion."

glTF channel layout [S]:
- baseColor is sRGB.
- metallicRoughness is linear, with **G = roughness, B = metal**.
- Occlusion is the **R** channel.
- `doubleSided=false` means back faces are culled.

---

## 2. Defect catalog: cause, detection, severity, fix

Severity levels:
- **S0 BLOCKER**: breaks import, rig, bake or collision, or is visibly broken in game.
- **S1 MAJOR**: visible artefact or budget breach.
- **S2 MINOR**: cosmetic or optimisation.
- **S3 INFO**: report only.

Where a severity depends on intended use, it is given as "S0 rig / S1 static".

### 2.1 Dense triangle soup / over budget

**Cause.**
- Generators build an implicit field (SDF/UDF or occupancy), then extract triangles with marching cubes, dual contouring or FlexiCubes.
- The result is isotropic tiny triangles with no edge flow, plus "over-smoothing and bumpy artifacts" [S: Meshtron paper; neural4d; Meshy "excessive triangles and irregular topology"].

**Detect.**
- Compare `tris` with table 1.1: S1 above 1.5× budget, S2 above 1.0× [H].
- Soup signature [H]: quad ratio = 0, and edge-length coefficient of variation < 0.35.
- Seam bloat [H]: post-export vert/tri > 1.0. UV seams, hard edges and material borders all split vertices.

**Fix (Blender, free).**
- *Static prop*: Decimate modifier, **Collapse**.
  - Organic: ratio 0.3–0.5. Below 0.2 the silhouette usually breaks [S: neural4d].
  - Hard surface: **Planar** (`angle_limit` default 5° [V]); raise it to 10–15° for more reduction [H].
  - Set `delimit` to UV/seam so UVs survive.
  - Turn on `use_symmetry` (default False, axis Y [V]) for symmetric assets.
  - The ratio counts triangles, and quads that are not collapsed stay quads [S: Blender manual].
- *Deforming mesh*: `object.quadriflow_remesh(mode='FACES', target_faces=N)`, then bake. Defaults: `target_faces` 4000, `use_mesh_symmetry` **True**, `use_preserve_sharp`/`use_preserve_boundary` False [V].
  - Quadriflow needs a manifold input with consistent normals and does not clean intersections [S: Blender manual].
  - The manual also says Voxel and Quadriflow are **not** final deforming topology: "no perfect automatic tools exist… done manually".
- *Hunyuan's own reducer as a model* [S: postprocessors.py]: pymeshlab `meshing_decimation_quadric_edge_collapse(targetfacenum=N, qualitythr=1.0, preserveboundary=True, boundaryweight=3, preservenormal=True, preservetopology=True, autoclean=True)`. This is a good recipe if pymeshlab is available.
- *Strict-budget retry* [S: QtMeshEditor #1134]: if the result lands under 80% of budget, retry with a higher target, and keep the retry only if it is within 2× of budget. Hole fills can push the count back over budget, so cap the fill triangles.

**Fix (Tripo, paid).**
- `tripo mesh decimate --face-limit N`. It bakes by default, which is right for LODs.

  | Model | Price | Notes |
  |---|---|---|
  | v2.0 smart retopo | 30 cr | default |
  | v3.0 | 35 cr tri / 40 cr quad | `--smart-uv` unwraps in the same task at no extra cost |
  | v1.0 basic | 10 cr | face_limit required, no bake |

  Face-limit range: 500–20000 tri / 500–10000 quad.
- Prevention is cheaper: regenerate with `face_limit` / `smart_low_poly`.

**Fix (Unreal).**
- Static opaque props: enable Nanite and skip retopo [S: UE docs].
- Disable Generate Lightmap UVs on very dense meshes when you don't use baked lighting.

### 2.2 Duplicate / unwelded vertices (split shells)

**Cause.**
- Per-face or UV-split export. Neural4d (vendor) reports **3k–8k (up to 10k) vertices** removed by Merge by Distance on a medium Meshy model.
- **All glTF** stores vertices split at UV and hard-normal seams. That split is legitimate, but it makes the raw topology look shattered (see §4 gotchas).

**Detect.**
- Weld a *copy* at `eps = 1e-5 × bbox diagonal` [H]. Count the merged vertices (`seam_split_verts`).
- Boundary edges that disappear after the weld mean real duplicate geometry, not UV seams.
- Severity: S1 if boundary edges close after the weld, otherwise S3 [H].

**Fix.**
- `bmesh.ops.remove_doubles(dist=…)`. Defaults: Merge by Distance 1e-4 [V], Weld modifier 1e-3 [S: manual].
- **Start small and scale with the asset.** Over-aggressive welds created most bad edges in the TRELLIS.2 study (voxel/8 → 20k non-manifold edges; voxel/64 fixed it) [S: QtMeshEditor].
- gltf-transform: `weld`.
- Unity welds on import by default (**Weld Vertices: enabled** [S: Unity manual]). Godot's shadow-mesh generation also welds [S: Godot import docs].

### 2.3 Non-manifold edges / holes / open boundaries

**Cause.**
- TRELLIS.2's decoder drops faces where a neighbour voxel is missing [S: Cinevva].
- One 13M-tri helmet had **157,715 non-manifold edges** (edges with more than 2 faces) and **17,975 open loops**, 16,617 of them ≤ 8 edges [S: bdeda PR #1].
- Weld and simplify add more [S: QtMeshEditor]. Neural4d claims 50–200 non-manifold edges per medium Tripo model (vendor, unverified).
- Meshy: holes after remesh come from "non-manifold edges" in the original; fix them first or remesh at a higher count [S: Meshy remesh doc].

**Detect.**
- Non-manifold edges: `not e.is_manifold and not e.is_boundary` (3+ faces or wire). Count boundary edges separately with `e.is_boundary`. **`is_manifold` is also False for boundary edges**, so don't double-count.
- Euler genus per closed shell: `g = (2 − (V − E + F)) / 2`. An unexpected g means tunnels.
- **0 boundary edges does not prove closure.** Cinevva saw visible slits with 0 boundary edges. Pair the count with the ray-escape test (§2.7) or a render.
- The edit-mode equivalent is `mesh.select_non_manifold`, with defaults wire, boundary, multi_face, non_contiguous and verts all True [V].

**Severity.** S0 if the mesh will be rigged, voxel-remeshed, used for collision or printed; S1 if a hole is visible; S2 if hidden (underside of a floor prop).

**Fix. Order matters.**
1. **Repair non-manifold edges first, then fill holes.** The hole filler can only trace loops that are manifold. Before repair, only 11k of 33k boundary components were traceable. After the repair, open loops fell from 17,975 to **654**, with positions unchanged (vertex split) [S: bdeda PR #1].
   - Blender: select edges with `len(e.link_faces) > 2` and run `bmesh.ops.split_edges(bm, edges=…)`. There is **no** `mesh.split_non_manifold` operator in 5.2 [V].
2. Small holes: `bmesh.ops.holes_fill(bm, edges=boundary, sides=N)` or `mesh.fill_holes(sides=N)`.
   - Default `sides` = 4 [V]; 0 means any size. Use 8–32 for AI pinholes [H].
   - Large holes: Grid Fill or Bridge Edge Loops (manual) [S: manual].
3. Unify winding, then flip any piece whose signed volume is negative (signed volume is unreliable on open pieces) [S: bdeda PR #1]. In bmesh this is `recalc_face_normals`.
4. Heavy damage or double walls: Voxel remesh ("new manifold mesh", no interior [S: manual]), then decimate, then bake. Alternatively use a signed-distance remesh with about 0.55-cell inflation [S: QtMeshEditor #1134]. QtMeshEditor's remesh-then-link-condition-QEM reached **0 non-manifold / 0 boundary / 0 flipped** on 6 of 6 meshes at 25k, with mean drift 0.2% of the bbox diagonal (max 0.64%).
5. Tripo: `mesh segment` → `mesh complete --completion-mode quick_cap` (no AI) or `ai_completion`. `complete` accepts segment tasks only. Both are paid.

### 2.4 Flipped / inconsistent normals

**Cause.**
- Inverted interior cavities (neural4d on Tripo, vendor claim).
- Simplifiers flip triangles [S: QtMeshEditor].
- Raw TRELLIS.2 decode had **100% inward-facing area** before the orientation fix [S: bdeda PR #1].

**Detect.**
- `e.is_manifold and not e.is_contiguous` means neighbour winding disagrees [V: 20 reversed faces on Suzanne gave 18 flagged edges].
- `bm.calc_volume(signed=True) < 0` per closed shell means the shell is inside-out.
- Look for see-through patches in a back-face-culled render.
- glTF: `ACCESSOR_VECTOR3_NON_UNIT` (Error).

**Severity.** S0 if any culled face is visible. glTF `doubleSided=false` culls back faces, as do engine defaults.

**Fix.**
- `bmesh.ops.recalc_face_normals` or `mesh.normals_make_consistent(inside=False)` [V].
- **Don't** mask the problem with double-sided materials: that doubles fragment cost and gives wrong lighting.

### 2.5 Custom split normals / shading artefacts

**Cause.**
- Imported custom normals become patchy after any topology edit [S: neural4d on Meshy].
- **Every glTF import in Blender sets `has_custom_normals=True` [V]**, so this flag carries no information on glTF input. Check it only after edits.
- Crease handling: one TRELLIS.2 generation had 7,730 corners whose vertex normal opposed the face. Crease-aware normals reduced that to 252 [S: QtMeshEditor #1134].

**Detect [H].**
- Count face corners where `dot(loop_normal, face_normal) < 0`. Flag S2 above 0.1% of corners.

**Fix.**
- `mesh.customdata_custom_splitnormals_clear` [V], then `object.shade_auto_smooth(angle=…)`.
  - The default is 30° [V]. In 4.1+ it adds a "Smooth by Angle" geometry-nodes modifier, so export with `export_apply=True` (default False [V]).
  - Use 30° for hard surface and 60° for organic [S: neural4d].
- Alternative: Data Transfer modifier → Custom Normals from the original.
- Engine side: Unity Normals = **Import** by default, mode Area-and-Angle Weighted [S: Unity manual].

### 2.6 Floating / disconnected islands (floaters, debris)

**Cause.**
- Marching-cubes noise and thin parts breaking up [S: Blender manual remesh: thin parts "can become loose"].
- TRELLIS.2 output after vertex split had **40,404 connected pieces** [S: bdeda PR #1].

**Detect.** Connected components by face flood fill on a welded copy. Then:
- **Main island = the island with the largest bbox**, not the one with the most faces. In testing, an inner shell had more faces than the head [V].
- Floater if faces < **0.5% of total** [S: Hunyuan3D FloaterRemover `nbfaceratio=0.005`] **or** bbox diagonal < 5% of the main island's [H].
- Flag islands whose bbox lies fully inside the main bbox as *interior candidates*: eyes, teeth or a duplicate shell.
- Severity: S1 if visible, S2 if hidden.

**Fix.**
- Delete selected islands with a custom bmesh delete.
- **`mesh.delete_loose` defaults to `use_faces=False` [V]**: it removes loose verts and edges only, not small face islands.
- Remesh modifier `use_remove_disconnected` (exists [V]) with a threshold.
- The pymeshlab equivalent is `compute_selection_by_small_disconnected_components_per_face(nbfaceratio=0.005)` [S].
- **Never auto-delete.** Eyes, buttons and straps are intended islands. Show the user the list (faces, bbox, centre) and ask.

### 2.7 Interior geometry / double walls / self-intersections

**Cause.**
- Narrow-band UDF plus dual-contouring bakes an **inner duplicate shell** into most TRELLIS.2 generations [S: TRELLIS.2 issue #140; root cause per a commenter, not confirmed by the maintainer].
- Contact zones (armpits, wing roots) are porous [S: Cinevva].

**Detect.**
- **Ray-escape test** [S: TRELLIS.2 #140, ectomia]. For each face, cast 26 Fibonacci-sphere rays from the centre with a 1e-4 offset. A face with 0 escaping rays is *enclosed*. Report `enclosed_face_frac`.
  - [V] An inner sphere inside Suzanne gave 0.516. A clean but intersecting Suzanne (subdiv 4, 252k tris) gave 0.040, because the eyeball backs sit inside the head.
  - Thresholds [H]: > 5% suspect, > 15% strong. Raise the ray count if armpits and folds give false positives.
- `BVHTree.overlap(self)` gives self-intersecting face pairs (adjacent faces are not reported) [V]. Note that Suzanne itself has 194 pairs (eyes through head), so judge relative to the asset.
- `mesh.select_interior_faces` (exists [V]) catches faces fully inside volumes.
- Severity: S1 (bakes break, z-fighting, wasted tris); S0 for voxel or collision work.

**Fix.**
- Separate shells: select the outer shell linked from sky-facing faces, invert, delete [S: #140 author, ~99% removed].
- Welded shells: delete enclosed faces from the ray test, then clean loose geometry and normals. Leave hole-fill **off**, because existing holes bridge the two walls.
- Voxel remesh, then decimate/Quadriflow, then bake. A global voxel remesh seals slits but softens edges, so bake normals from the original [S: Cinevva].

### 2.8 Degenerate / zero-area faces

**Detect.**
- Area < 1e-10 m², or edge length < 1e-6 m [H].
- glTF `ACCESSOR_INDEX_TRIANGLE_DEGENERATE` (Info) [S].
- Severity: S2, or S1 if it breaks the tangent bake.

**Fix.** `bmesh.ops.dissolve_degenerate(dist=1e-4)` [V default]. Also drop NaN vertices; research pipelines strip NaN and zero-area faces first [S: arXiv cleanup pipelines].

### 2.9 Fused parts (limbs to body, weapon to hand, legs together)

**Cause.** A single-image prior plus a closed-surface decoder merges contact zones [S: Cinevva].

**Detect.**
- `tripo anim check` returns `riggable` and `rig_type` (GLB only, ≤150 MB). Run it before spending rig credits.
- Slice heuristic [H] for a biped: slice horizontally at 10 heights.
  - Slices at 30–45% of height should show **2 leg loops**.
  - Slices at 60–75% should show the arms separate from the torso.
  - One single loop means fused.
- Islands = 1 when the prompt implied detachable props.
- Severity: S0 for rigging, S2 for static props.

**Fix.**
- Prevention: T/A-pose input (`text-to-image -p template=t_pose`, then image-to-model) or multiview.
- v3.x `generate_parts=true` (forces texture off; re-texture afterwards).
- `mesh segment` (v2.0 `split_by_connectivity`), then `mesh complete`; or `smartsegment` (55 cr from a model / 85 cr from an image).
- Blender: separate manually, then fill. Voxel remesh **will not** un-fuse parts.

### 2.10 Baked lighting in albedo

**Cause.**
- The texture is projected from a lit input image, so shadows and highlights end up in base color and contradict engine lights.
- Hunyuan3D-2 runs a dedicated de-light model (`hunyuan3d-delight-v2-0`, an InstructPix2Pix-style edit) on the input image *before* painting [S: Hunyuan3D-2 pipeline code / ComfyUI node docs].
- Meshy has a "Remove Lighting" option [S: Meshy docs]. Rodin claims de-lit albedo (vendor claim).

**Detect** (texqa.py, §4.2) [V on a synthetic asset]:
1. **Pearson r between per-face albedo luminance (sampled at the UV centroid) and face normal Z.**
   - Thresholds [H]: |r| > 0.35 suspect, > 0.5 strong.
   - [V] A synthetic top-lit albedo gave **r = 0.835**. Random albedo on the same mesh gave **r = 0.069**.
2. Face-sampled fraction below **30 sRGB** > 3%, or above **240 sRGB** > 1% [S range; H fractions]. Sample only inside UV islands; empty atlas background skews whole-image stats.
3. Optional AO correlation: bake AO in Cycles (`bake type AO` exists [V]) and correlate it with albedo luminance. r > 0.4 is suspect [H].
- Severity: S1. For stylised or hand-painted art styles, where painted light is intended, use S3 and ask the user.
- 8-bit `image.pixels` values are already sRGB/255. Convert linear to sRGB only for float images (`img.is_float`) [V].

**Fix.**
- Tripo `model texture --texture-alignment geometry` (PBR on by default; paid).
- Prevention: flat, diffuse-lit input with no hard shadows. Real photos benefit most from de-lighting; clean flat renders do not need it [S: ComfyUI Hunyuan delight node].
- External tools: Adobe Substance 3D Sampler **Delight (AI Powered)**, Agisoft De-Lighter (free) [S].
- Blender (partial): divide albedo by a normalised AO bake, or clamp levels to 30–240. Neither removes directional cast shadows; regenerate the texture for those.

### 2.11 Blurry / smeared / low-res textures

**Cause.** A low-res atlas stretched over a large area, multi-view blending, or upscaling.

**Detect [H].**
- Texel density: `td = sqrt(Σuv_area × W × H / Σarea_m²)` [V]. Compare with table 1.2 (±50% is OK).
- Mean absolute Laplacian of luminance. Flag if it is < 25% of the median for accepted assets, or use the back/front ratio (§2.12).
- A high share of near-identical neighbouring texels means an upscaled image.
- Severity: S1 for hero assets, S2 for props.

**Fix.**
- Tripo re-texture `--texture-quality detailed` (higher tier).
- Blender: `uv.average_islands_scale` + `uv.pack_islands` to give the map more texels, then bake the original material onto the new UVs.

### 2.12 Back-side texture artefacts; asymmetry

**Cause.** With single-image input the unseen side is hallucinated. Tripo's default `texture_alignment=original_image` favours the photo over the geometry.

**Detect [H].**
- Split faces by `dot(n, front)`, where front = −Y in Blender: > 0.5 is front, < −0.5 is back.
- Compare back vs front on three measures:
  - Laplacian sharpness ratio: **< 0.5 means a smeared back**.
  - Mean luminance or colour ΔE: **> 10 is suspect**.
  - Texel density ratio.
- **Symmetry**: mirror the main island's vertices across X through its bbox centre, then KD-match them within 0.5% of the main diagonal.
  - Flag < 90% matched on assets meant to be symmetric: S2, or S1 for characters to be rigged.
  - [V] Suzanne scored 1.0. Use the main island's centre, not the whole bbox; a single floater dropped the score to 0.011 in testing.

**Fix.**
- Prevention: multiview `tripo make front.png back.png …` (2–4 views).
- Tripo `convert --quad -p force_symmetry=true` (quad only, FBX; complex-convert price).
- Blender `mesh.symmetrize(direction='NEGATIVE_X', threshold=1e-4)` [V defaults], or Decimate `use_symmetry` / Quadriflow `use_mesh_symmetry`.
  - Symmetrize *before* UV and bake.
  - For texture symmetry, re-bake or use `uv.copy_mirrored_faces` (exists [V]).

### 2.13 Wrong scale / orientation / pivot

**Conventions.**
- glTF: +Y up, front **+Z**, meters.
- Godot: characters face **+Z**; `look_at(..., use_model_front=true)` expects +Z [S]. Godot also asks you to apply transforms and export skinned meshes in rest pose [S].
- Tripo's default **`export_orientation` is `+x`**, and downstream tasks don't inherit it. Set it **only on the final `convert`** [S: tripo docs].
- Meshy FBX is in cm, so Unity needs Scale Factor 0.01 [S: Meshy pipeline repo]. AI exports frequently lack unit info [S: neural4d].
- Unity's Scale Factor / Convert Units and Godot's **Apply Root Scale** are the engine-side fixes [S].

**Detect.**
- `main_island_dims_m` vs the class range [H]:

  | Object | Expected size |
  |---|---|
  | Human | 1.6–1.9 m |
  | Door | 2.0–2.2 m |
  | Chair seat height | ≈0.45 m |
  | Sword | 0.8–1.2 m |
  | Crate | 0.5–1.0 m |

- A ratio near 100× means a cm/m mix-up; near 1000× means mm.
- `zmin ≈ 0` means the pivot is at the bottom. Non-unit `obj.scale` or non-zero rotation means transforms were not applied.
- Front: for characters, the face or toe centroid offset should point −Y in Blender.
- Severity: S1, or S0 if a rig or retarget depends on it.

**Fix.**
- Blender: scale, then `object.transform_apply(location, rotation, scale)` [V], then origin to bottom-centre.
- Tripo: `convert --scale-factor`, `--auto-size` (v3.x), `--pivot-to-center-bottom`, `--export-orientation` (complex-convert price).

### 2.14 Messy UVs (thousands of islands, overlaps, no padding, out of 0–1)

**Cause.** xatlas-style charting of triangle soup. xatlas can even fail on dense TRELLIS meshes [S: ComfyUI-Trellis2 issue #120]. "Poor UVs and topology" is the top complaint about AI meshes (Meshy CEO interview, preview only).

**Detect [H].**

| Check | Flag | Severity |
|---|---|---|
| UV island count | > 0.05 × faces or > 500 | S2 |
| Overlap (raster at 1k) | > 1% of covered pixels, unless intended mirroring | S1 |
| UVs outside 0–1 (no UDIM in games) | any | S1 |
| UV coverage (`Σuv_area`; a value > 1 means overlap) | < 0.5 | S2; good packs reach 0.65–0.8 |
| Padding | < 4 px @1k, 8 px @2k, 16 px @4k | mip bleeding |
| No UV layer | glTF `MESH_PRIMITIVE_TOO_FEW_TEXCOORDS` (Error) | S0 |

- Blender's bake margin default is 16 px [V].
- Lightmap UV2 must not overlap, must stay in [0,1], and needs chart margins [S: Unity lightmap UV doc]. Unity auto-UV2 defaults: **Hard Angle 88°, Angle Error 8%, Area Error 15%, Pack Margin 4 px** (assuming a 1024 lightmap) [S]. Godot: Light Baking = Static Lightmaps generates UV2, with Lightmap Texel Size [S].

**Fix.**
1. `uv.smart_project` (defaults: angle_limit 66°, island_margin 0, margin_method SCALED [V]). Set island_margin to about 0.003–0.01 [H].
2. `uv.pack_islands(margin=0.002–0.005)` (default 0.001 [V]).
3. Bake (§2.15).
- `uv.lightmap_pack` exists for UV2 [V].
- Tripo `mesh uv`: **20 cr**, input ≤ 80k equivalent tris (larger input fails and refunds). It remaps existing textures, rig and animation. Or `mesh decimate --smart-uv` (v3.0, 35 cr, no atlas image).

### 2.15 Bake-transfer recipe (after any remesh / retopo / re-UV) [V ops exist]

1. Use Cycles. Select the original high-poly and the new low-poly, with the low-poly active, and set `use_selected_to_active=True`.
2. Cage: `use_cage=True`, `cage_extrusion` ≈ 0.5–2% of the bbox diagonal [H]. **The defaults are `cage_extrusion=0`, `max_ray_distance=0`, `use_cage=False` [V], so set them explicitly.**
3. Passes:
   - `DIFFUSE` with only Color enabled (direct/indirect off) gives albedo without lighting [S: manual].
   - `NORMAL` in TANGENT space (default [V]) for animated meshes.
   - `ROUGHNESS`.
   - Use an `EMIT` pass routed from the metallic channel for metal [H].
4. Margin 16 px (default [V]). `margin_type` defaults to EXTEND [V]; ADJACENT_FACES is an alternative.
5. Export glTF with `export_tangents=True` (default False [V]) whenever there is a normal map. The validator flags `MESH_PRIMITIVE_GENERATED_TANGENT_SPACE` (Warning); MikkTSpace is the spec default.
   - Godot's **Ensure Tangents** generates MikkTSpace when tangents are missing [S].
   - Unity uses Calculate Mikktspace when Normals = Calculate [S].
   - Nanite derives tangents in the pixel shader, so expect minor edge discontinuities [S: UE docs].

### 2.16 Rig / animation-specific checks

**S0 if any of these fails:**
- Single manifold body.
- No fused limbs (§2.9).
- T or A rest pose.
- Transforms applied.
- Meters.
- Correct front axis.
- Enclosed-face fraction low (no inner shell to skin).

Other checks:
- Keep skinned meshes within table 1.1. Godot auto-LOD (meshoptimizer, Threshold Pixels default **1 px**) "may occasionally introduce rendering issues (especially in skinned meshes)". Disable LOD generation per mesh in Advanced Import Settings if it does [S].
- Tripo chain:
  1. `anim check` (gate).
  2. `anim rig` (`--spec mixamo` for Unity Humanoid).
  3. `anim retarget` (≤ 5 animations, billed per animation; use `--animate-in-place` for game locomotion).
- glTF skin codes:
  - Errors: `MESH_PRIMITIVE_JOINTS_WEIGHTS_MISMATCH`, `ACCESSOR_WEIGHTS_NON_NORMALIZED`, `ACCESSOR_JOINTS_INDEX_OOB`, `SKIN_NO_COMMON_ROOT`.
  - Warnings: `ACCESSOR_JOINTS_USED_ZERO_WEIGHT`, `NODE_SKINNED_MESH_PARENT_TRANSFORMS`.
  - Info: `NODE_SKINNED_MESH_NON_ROOT`.
- Godot Skins import: "4 Influences (Compatible)" vs "All Influences". Use 4 for mobile and compatibility [S].

---

## 3. QA checklist (run in order; stop and report at the first S0)

| # | Check | Metric / tool | Pass | Fail severity |
|---|---|---|---|---|
| 1 | File validity | `npx gltf-validator in.glb` | 0 Errors | S0 |
| 2 | Scale | `main_island_dims_m` vs class | 0.5–2× expected | S1 (S0 at ~100×) |
| 3 | Transforms / pivot | scale=1, rot=0, zmin≈0 | yes | S1 |
| 4 | Orientation | front −Y Blender / +Z glTF | yes | S1 (S0 rig) |
| 5 | Triangle budget | `tris` vs §1.1 | ≤ budget | S2 >1×, S1 >1.5× |
| 6 | Non-manifold edges | `nonmanifold_edges` (3+ faces / wire) | 0 rig/collision; ≤0.1% edges static [H] | S0 / S1 |
| 7 | Holes | `boundary_edges` after weld | 0 visible | S1 (S0 rig/voxel) |
| 8 | Winding | `winding_flip_edges`, `signed_volume` | 0 / >0 | S0 if visible |
| 9 | Real duplicates | boundary edges vanish after weld | weld applied | S1 |
| 10 | Floaters | `floaters` list | 0 unintended (user confirms) | S1 / S2 |
| 11 | Inner shell / interior | `enclosed_face_frac` | <5% [H] | S1 (S0 rig/voxel) |
| 12 | Self-intersection | `self_intersect_pairs` | ≈0 for single-shell assets | S2 / S1 |
| 13 | Degenerate faces | `degenerate_faces` | 0 | S2 |
| 14 | Fused limbs (rig only) | slice loops / `tripo anim check` | separable / riggable | S0 |
| 15 | Symmetry (if intended) | `symmetry_x` | ≥0.90 | S2 (S1 rig) |
| 16 | UVs | layers ≥1, `uv_out_of_01_frac`=0, overlap <1% | yes | S0 missing, S1 |
| 17 | UV efficiency | islands, coverage, padding | §2.14 | S2 |
| 18 | Texel density | `texel_density_px_per_m` | ±50% of §1.2 | S2 |
| 19 | Baked lighting | `lum_vs_normalZ_r` | <0.35 | S1 (S3 stylised) |
| 20 | Albedo range | face-sampled <30 / >240 sRGB | <3% / <1% | S2 |
| 21 | Back side / blur | `back_front_sharpness_ratio` | ≥0.5 | S2 (S1 hero) |
| 22 | Texture size | POT, ≤ platform max | yes | S2 |
| 23 | Normals data | no inverted loop normals after edits; tangents present with a normal map | yes | S2 |
| 24 | Engine import | Godot/Unity import with no warnings; 6-view render check | yes | S1 |

---

## 4. Headless scripts (tested on Blender 5.2.3 [V])

### 4.1 Geometry / UV detector: `qa.py`

[V] Runtime: 1.1 s on a 2k-tri test, **5.4 s on 252k tris**. Ray and symmetry tests are sampled to 20k faces/verts.

```python
# blender -b --factory-startup --python qa.py -- in.glb out.json
import bpy, bmesh, json, sys, math, random
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
inp, outp = sys.argv[sys.argv.index("--")+1:][:2]   # pass ABSOLUTE paths
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=inp)
def fib_dirs(n):
    g = math.pi*(3-math.sqrt(5)); out=[]
    for i in range(n):
        y = 1-2*(i+0.5)/n; r = math.sqrt(1-y*y); t = g*i
        out.append(Vector((math.cos(t)*r, y, math.sin(t)*r)))
    return out
DIRS = fib_dirs(26); rep = {}
for obj in [o for o in bpy.context.scene.objects if o.type=='MESH']:
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(obj.matrix_world)
    raw_v = len(bm.verts)
    lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)]); hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    diag = (hi-lo).length or 1.0
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=diag*1e-5)   # glTF is split at seams: weld a copy first
    bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table(); bm.edges.ensure_lookup_table()
    F = len(bm.faces)
    seen=set(); isl=[]                                             # islands (face flood fill)
    for f in bm.faces:
        if f.index in seen: continue
        st=[f]; seen.add(f.index); members=[]
        while st:
            c=st.pop(); members.append(c.index)
            for e in c.edges:
                for g in e.link_faces:
                    if g.index not in seen: seen.add(g.index); st.append(g)
        isl.append(members)
    isl.sort(key=len, reverse=True)
    def bbox_of(fidx):
        vs={v for fi in fidx for v in bm.faces[fi].verts}
        a=Vector([min(v.co[i] for v in vs) for i in range(3)]); b=Vector([max(v.co[i] for v in vs) for i in range(3)])
        return a,b,vs
    boxes=[bbox_of(i) for i in isl]
    main=max(range(len(isl)), key=lambda k:(boxes[k][1]-boxes[k][0]).length)  # largest bbox, NOT most faces
    mlo,mhi,mverts = boxes[main]; mdiag=(mhi-mlo).length
    floaters=[]
    for k,i in enumerate(isl):
        if k==main: continue
        a,b,_ = boxes[k]
        small = len(i) < 0.005*F or (b-a).length < 0.05*mdiag
        inside = all(mlo[j]-1e-6<=a[j] and b[j]<=mhi[j]+1e-6 for j in range(3))
        if small or inside: floaters.append(dict(island=k, faces=len(i), bbox_diag=round((b-a).length,4),
                                                 inside_main_bbox=inside, center=[round(x,3) for x in (a+b)/2]))
    bvh = BVHTree.FromBMesh(bm)                                    # ray-escape test (TRELLIS.2 #140)
    sample = bm.faces if F <= 20000 else random.Random(0).sample(list(bm.faces), 20000)
    enclosed=0
    for f in sample:
        c = f.calc_center_median()
        enclosed += not any(bvh.ray_cast(c + d*diag*1e-4, d)[0] is None for d in DIRS)
    kd = KDTree(len(bm.verts))                                     # mirror symmetry across X of main island
    for i,v in enumerate(bm.verts): kd.insert(v.co, i)
    kd.balance(); cx=(mlo.x+mhi.x)/2; tol=0.005*mdiag
    mv=list(mverts); vs = mv if len(mv)<=20000 else random.Random(1).sample(mv,20000)
    sym = sum(kd.find(Vector((2*cx-v.co.x, v.co.y, v.co.z)))[2] <= tol for v in vs)/max(1,len(vs))
    uvm = {}; uvl = bm.loops.layers.uv.active
    if uvl:
        us=[l[uvl].uv for f in bm.faces for l in f.loops]
        def uvarea(f):
            p=[l[uvl].uv for l in f.loops]; a=0
            for i in range(1,len(p)-1):
                a+=abs((p[i].x-p[0].x)*(p[i+1].y-p[0].y)-(p[i+1].x-p[0].x)*(p[i].y-p[0].y))/2
            return a
        uv_area=sum(uvarea(f) for f in bm.faces); area3d=sum(f.calc_area() for f in bm.faces)
        img = next((n.image for m in me.materials if m and m.use_nodes for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image), None)
        W,H = (img.size[0], img.size[1]) if img else (1024,1024)
        uvm = dict(uv_out_of_01_frac=round(sum(not(-1e-4<=u.x<=1.0001 and -1e-4<=u.y<=1.0001) for u in us)/len(us),4),
                   uv_coverage_sum=round(uv_area,3), tex_size=[W,H], tex_found=bool(img),
                   texel_density_px_per_m=round(math.sqrt(uv_area*W*H/area3d),1) if area3d else None)
    rep[obj.name]=dict(
        tris=sum(len(f.verts)-2 for f in bm.faces), faces=F, verts_welded=len(bm.verts), seam_split_verts=raw_v-len(bm.verts),
        nonmanifold_edges=sum(not e.is_manifold and not e.is_boundary for e in bm.edges),  # 3+ faces / wire
        boundary_edges=sum(e.is_boundary for e in bm.edges),
        winding_flip_edges=sum(e.is_manifold and not e.is_contiguous for e in bm.edges),
        signed_volume=round(bm.calc_volume(signed=True),6),
        degenerate_faces=sum(f.calc_area()<1e-10 for f in bm.faces),
        islands=len(isl), island_sizes_top=[len(i) for i in isl[:8]], floaters=floaters[:20],
        main_island_dims_m=[round(x,4) for x in (mhi-mlo)],
        enclosed_face_frac=round(enclosed/max(1,len(sample)),4),
        self_intersect_pairs=len(bvh.overlap(bvh)), symmetry_x=round(sym,3),
        dims_m=[round(x,4) for x in (hi-lo)], zmin=round(lo.z,4), obj_scale=list(obj.scale), obj_rot=list(obj.rotation_euler),
        uv_layers=len(me.uv_layers), materials=len(me.materials), **uvm)
    bm.free()
json.dump(rep, open(outp,"w"), indent=1)
```

[V] Synthetic defect test: Suzanne + inner sphere + 20 reversed faces + tiny ico floater. The detector reported:
- `winding_flip_edges` 18.
- `enclosed_face_frac` 0.516.
- `boundary_edges` 42 (eye sockets; normal for Suzanne).
- Floaters list: 4 entries. The tiny ico floater was flagged by the bbox rule. The inner sphere and both eyes were flagged as `inside_main_bbox` candidates. This is correct behaviour; the user decides.
- `symmetry_x` 1.0.

### 4.2 Albedo detector: `texqa.py` (baked light, range, back-side blur)

```python
# blender -b --factory-startup --python texqa.py -- in.glb out.json
import bpy, bmesh, json, sys, numpy as np
from mathutils import Vector
inp,outp=sys.argv[sys.argv.index("--")+1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=inp)
def srgb(a): return np.where(a<=0.0031308, a*12.92, 1.055*np.power(np.clip(a,0,1),1/2.4)-0.055)
rep={}
for o in [o for o in bpy.context.scene.objects if o.type=='MESH']:
    me=o.data
    img=next((l.from_node.image for m in me.materials if m and m.use_nodes for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'
              for l in n.inputs['Base Color'].links if l.from_node.type=='TEX_IMAGE'), None)
    if not img: rep[o.name]={"albedo":"none"}; continue
    W,H=img.size; a=np.empty(W*H*4,np.float32); img.pixels.foreach_get(a); a=a.reshape(H,W,4)[...,:3]
    if img.is_float: a=srgb(a)                       # 8-bit pixels are already sRGB/255
    lum=(0.2126*a[...,0]+0.7152*a[...,1]+0.0722*a[...,2])*255
    lap=np.abs(4*lum[1:-1,1:-1]-lum[:-2,1:-1]-lum[2:,1:-1]-lum[1:-1,:-2]-lum[1:-1,2:])
    bm=bmesh.new(); bm.from_mesh(me); bm.transform(o.matrix_world); uvl=bm.loops.layers.uv.active
    L=[];NZ=[];FR=[];SH=[]
    for f in bm.faces:
        c=sum((l[uvl].uv for l in f.loops),Vector((0,0)))/len(f.loops)
        x=int(np.clip(c.x%1*W,0,W-1)); y=int(np.clip(c.y%1*H,0,H-1))
        L.append(lum[y,x]); NZ.append(f.normal.z); FR.append(-f.normal.y)      # Blender front = -Y
        y0,y1,x0,x1=max(1,y-4),min(H-2,y+4),max(1,x-4),min(W-2,x+4)
        SH.append(lap[y0-1:y1-1,x0-1:x1-1].mean() if y1>y0 and x1>x0 else 0)
    L,NZ,FR,SH=map(np.array,(L,NZ,FR,SH)); front,back=FR>0.5,FR<-0.5
    rep[o.name]=dict(tex=[W,H], pot=all((s&(s-1))==0 for s in (W,H)),
        frac_below_30_srgb=round(float((L<30).mean()),4), frac_above_240_srgb=round(float((L>240).mean()),4),
        laplacian_mean=round(float(lap.mean()),3),
        lum_vs_normalZ_r=round(float(np.corrcoef(L,NZ)[0,1]),3) if L.std()>0 else 0.0,
        back_front_sharpness_ratio=round(float(SH[back].mean()/max(1e-6,SH[front].mean())),3) if front.any() and back.any() else None,
        back_front_lum_delta=round(float(L[back].mean()-L[front].mean()),2) if front.any() and back.any() else None)
    bm.free()
json.dump(rep,open(outp,'w'),indent=1)
```

[V] Top-lit synthetic albedo: r = 0.835. Random-albedo control: r = 0.069.

### 4.3 Free fix chain (bmesh unless noted) [V ops exist]

1. `remove_doubles(dist ≈ 1e-5…1e-4 × diag)`: start small.
2. `dissolve_degenerate(dist=1e-4)`.
3. **Split non-manifold edges** (`split_edges` on edges with >2 faces) **before** `holes_fill(sides=8…32)`.
4. `recalc_face_normals`, then flip pieces with negative signed volume.
5. Delete floaters and enclosed faces **that the user approved**.
6. Decimate (modifier) or Quadriflow / voxel remesh (operators, need an active object).
7. **Repeat steps 3–5 after step 6.**
8. UV: `smart_project` + `pack_islands` (edit mode).
9. Bake from the original (§2.15).
10. `customdata_custom_splitnormals_clear` + `shade_auto_smooth`.
11. Triangulate (`bmesh.ops.triangulate`).
12. Export glTF. Defaults [V]: `export_yup=True`, `export_apply=False` (set True), `export_tangents=False` (set True with a normal map), Draco and meshopt off.

### 4.4 Headless operator availability, Blender 5.2.3 [V]

| Available headless (defaults read from RNA) | Not available |
|---|---|
| `mesh.select_non_manifold` (all 6 trait flags True) | `mesh.print3d_check_all`: `hasattr` says True, but the RNA lookup fails. The 3D-Print Toolbox is an **extension** since 4.2 and not bundled |
| `mesh.select_interior_faces`, `mesh.select_loose`, `mesh.delete_loose` (`use_faces=False`) | `mesh.split_non_manifold`: doesn't exist; use `bmesh.ops.split_edges` |
| `mesh.fill_holes` (sides=4), `mesh.remove_doubles` (1e-4), `mesh.dissolve_degenerate` (1e-4) | Bundled add-ons: only `cycles`, `io_scene_gltf2`, `io_scene_fbx`, `io_anim_bvh`, `io_curve_svg`, `io_mesh_uv_layout`, `pose_library`, `bl_pkg` |
| `mesh.symmetrize` (NEGATIVE_X, 1e-4), `mesh.normals_make_consistent` (inside=False) | |
| `mesh.decimate` (use_symmetry False, axis Y), `mesh.intersect` (EXACT solver) | |
| `object.voxel_remesh` (uses `mesh.remesh_voxel_size`, default 0.1 m: far too coarse; use diag/200–diag/400 [H]) | |
| `object.quadriflow_remesh` (target_faces 4000, symmetry True) | |
| `uv.smart_project` (66°, margin 0), `uv.pack_islands` (0.001), `uv.lightmap_pack`, `uv.average_islands_scale`, `uv.copy_mirrored_faces` | |
| `object.bake` types: COMBINED, AO, SHADOW, POSITION, NORMAL, UV, ROUGHNESS, EMIT, ENVIRONMENT, DIFFUSE, GLOSSY, TRANSMISSION | |
| Remesh modifier modes BLOCKS/SMOOTH/SHARP/VOXEL with `use_remove_disconnected` | |
| All bmesh ops used above: remove_doubles, dissolve_degenerate, recalc_face_normals, holes_fill, split_edges, triangulate, symmetrize, bisect_plane, dissolve_limit, find_doubles, weld_verts, reverse_faces | |

**Headless gotchas [V]:**
- Pass **absolute paths** to scripts. A relative image save failed with "Couldn't create directory".
- Edit-mode operators need `object.mode_set(mode='EDIT')` with an active object. Prefer bmesh where possible.
- Test operators with `op.get_rna_type()` in a `try`, never with `hasattr`.
- `import_scene.gltf(merge_vertices=True)` (default False) only merges vertices with identical attributes, so it does **not** fix seam splits. Weld a copy instead.
- glTF import always sets custom normals.
- Voxel remesh drops UVs and textures, so bake afterwards.

---

## 5. Fix-option menu to present to the user

| Defect | Free (Blender) | Paid (Tripo, check price first) | Prevent at generation |
|---|---|---|---|
| Over budget, static | Decimate collapse 0.3–0.5 / planar 5–15° | `mesh decimate -f N` (v2 30 cr, v3 35/40, v1 10) | P1/P2 `face_limit`, v3 `smart_low_poly` |
| Over budget, character | Quadriflow + bake (not final quality per manual) | `mesh decimate --quad` (v3 40 cr) | P2 `quad=true` / v3 quad + smart_low_poly |
| Non-manifold / holes | split NM edges → fill_holes → unify; voxel remesh + bake | `mesh segment` → `mesh complete quick_cap` | – |
| Inner shell / interior | ray-escape delete or outer-shell select; voxel remesh + bake | – | – |
| Normals | recalc + signed-volume flip | – | – |
| Floaters | approved island delete | – | – |
| Fused parts | manual separate + fill | `mesh segment`, `smartsegment` 55/85 cr | T/A-pose image, multiview, `generate_parts` |
| Baked light | AO-divide / clamp (partial); Substance Sampler Delight | `model texture --texture-alignment geometry` | flat-lit input; de-light the input image first |
| Blurry / back side | re-UV + bake (partial) | `model texture --texture-quality detailed` | multiview input |
| Asymmetry | symmetrize + re-bake | `convert --quad -p force_symmetry=true` | symmetric front view |
| Scale / orient / pivot | transform_apply, origin | `convert --scale-factor --export-orientation --pivot-to-center-bottom` | orientation only on the final convert |
| Messy UVs | smart_project + pack + bake | `mesh uv` 20 cr (≤80k tris); `decimate --smart-uv` | P1 `export_uv` |

Credit check:
- `tripo make <id> --then <step> --dry-run --json` validates the chain and prints `cost_notes`, but **not credit amounts** [V, earlier session].
- Take amounts from `tripo docs --topic commands/process`.
- `--dry-run` exists only on `make`. `tripo mesh …` and `tripo model …` reject it.

---

## 6. Where sources disagree

- **Budgets.**
  - Neural4d: hero 5–15k.
  - Meshy: PC/console 20–50k.
  - Meshy pipeline repo: 5–50k.
  - A Dec-2025 vendor guide: mobile 500–2k, PC 2k–10k.
  - Tripo sample character: ≈20k.
  - Use project and platform targets, not one number.
- **"Game-ready" claims.**
  - Tripo says Smart Mesh is game-ready "in under 5 seconds" [80.lv], and one reviewer took 50+ Tripo models straight into Unity.
  - Tripo's own P1 announcement concedes that AI assets "still require extensive manual cleanup".
  - On Polycount, the AI output saves blockout but then needs photogrammetry-like cleanup (about 500k → 130k), so the net gain is debated. **Always run QA.**
- **Where TRELLIS holes come from.**
  - QtMeshEditor: the raw output was closed, and weld/simplify did the damage.
  - Cinevva and bdeda: the decoder itself leaves non-manifold edges, open loops and inward winding. The bdeda helmet was 13M tris with 157k non-manifold edges.
  - Both views hold for different settings and pipelines. Measure raw output and after each step.
- **Inner shells.** The #140 commenter blames UDF + dual contouring. There's no maintainer confirmation; treat it as plausible.
- **Auto-remesh for animation.**
  - Blender manual: Voxel/Quadriflow are not deforming topology.
  - Vendors (Tripo quad, Hunyuan autoregressive retopo, Meshy, Rodin) claim animation-ready edge flow.
  - Accept vendor quads for indie and mobile; plan manual retopo for hero characters.
- **Non-manifold severity.**
  - CGTrader: "always avoid".
  - Practical guides: engines tolerate small hidden internal faces.
  - This skill grades by intended use (§2.3).
- **Merge distance.** Blender Merge-by-Distance defaults to 1e-4 and the Weld modifier to 1e-3. QtMeshEditor showed coarse welds are harmful (voxel/8 bad, voxel/64 good).
- **Albedo dark limit.** Adobe: 30 sRGB (tolerant) vs 50 (strict). Some artists use 60. Stylised games ignore these limits.
- **Texel density.** Third-person: 512 px/m (Polycount, Maxon) vs 512–1024 (Strayspark). First-person: 1024 vs 1024–2048. Polycount stresses there are no hard rules.
- **Nanite.** Older docs said skinned meshes were unsupported. The current docs list Nanite skeletal meshes, but morph targets, translucency, VR stereo and forward rendering are still unsupported.
- **Baked-lighting removal.** Rodin and Meshy claim de-lit albedo, and Hunyuan de-lights the input. None of these is independently tested, so run §4.2 regardless.

---

## 7. Sources

Read or verified this session (2026-10-31), plus the carried-over sources from 2026-10-30.

Engine / format / DCC docs:
- Blender Manual: Mesh Clean Up https://docs.blender.org/manual/en/latest/modeling/meshes/editing/mesh/cleanup.html
- Blender Manual: Retopology (Voxel/Quadriflow caveats) https://docs.blender.org/manual/en/latest/modeling/meshes/retopology.html
- Blender Manual: Remesh / Decimate / Weld modifiers https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/remesh.html , …/decimate.html , …/weld.html
- Blender Manual: Mesh Analysis (Overhang/Thickness/Intersect/Distortion/Sharp) https://docs.blender.org/manual/en/latest/modeling/meshes/mesh_analysis.html
- Blender Manual: Cycles Baking https://docs.blender.org/manual/en/latest/render/cycles/baking.html
- Khronos glTF 2.0 spec https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- Khronos glTF-Validator ISSUES.md (codes + severities) https://github.com/KhronosGroup/glTF-Validator/blob/main/ISSUES.md
- glTF-Transform CLI https://gltf-transform.dev/cli
- Godot 4: Import configuration https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/import_configuration.html
- Godot 4: Mesh LOD https://docs.godotengine.org/en/stable/tutorials/3d/mesh_lod.html
- Godot 4: Model export considerations https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/model_export_considerations.html
- Unity Manual: Model tab import settings https://docs.unity.com/en-us/engine/current/manual/assets-and-media/asset-types/models/importing/fbximporter-model
- Unity Manual: Generating lightmap UVs + reference https://docs.unity.com/en-us/engine/6000.6/manual/lighting-overview/direct-and-indirect-lighting/lightmapping/lighting-gi-uvs/generating-lightmapping-uvs , …/lighting-gi-uvs/reference
- Unreal Engine: Nanite https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
- Meta Quest Unity performance https://developers.meta.com/horizon/documentation/unity/unity-perf/
- Adobe Substance PBR Guide pt. 2 https://www.adobe.com/learn/substance-3d-designer/web/the-pbr-guide-part-2
- Adobe Substance 3D Sampler: Delight (AI Powered) https://helpx.adobe.com/substance-3d-sampler/filters/tools/delight-ai-powered.html
- Maxon C4D: Texel density https://help.maxon.net/c4d/2027/en-us/Content/html/Texel_Density.html

Community / practitioner / primary engineering reports:
- Polycount: "How are you actually handling AI-generated mesh cleanup before engine handoff?" https://polycount.com/discussion/238705 (403 to the fetcher; content taken from the search-engine snippet)
- Polycount: texel density discussion https://polycount.com/discussion/comment/2707204
- microsoft/TRELLIS.2 issue #140: duplicate inner mesh walls https://github.com/microsoft/TRELLIS.2/issues/140
- microsoft/TRELLIS.2 issue #105: broken geometry when remesh disabled https://github.com/microsoft/TRELLIS.2/issues/105
- bdeda/TRELLIS.2 PR #1: non-manifold repair before fill_holes https://github.com/bdeda/TRELLIS.2/pull/1
- QtMeshEditor PR #1102 / #1134 (TRELLIS.2 game-ready pass) https://github.com/fernandotonon/QtMeshEditor/pull/1102 , https://github.com/fernandotonon/QtMeshEditor/pull/1134 ; release notes https://github.com/fernandotonon/QtMeshEditor/releases/tag/3.54.0
- ComfyUI-Trellis2 issue #120 (xatlas failure on dense mesh) https://github.com/visualbruno/ComfyUI-Trellis2/issues/120
- Cinevva: where the holes in generated meshes come from https://app.cinevva.com/blog/2026-09-24-where-the-holes-in-generated-meshes-come-from
- gamedev.net: non-manifold geometry processing https://gamedev.net/news/3398-tangent-blow-ups-for-processing-non-manifold-geometry/
- CGTrader help: non-manifold geometry https://help.cgtrader.com/hc/en-us/articles/12485385944849
- 80.lv: How Tripo is tackling clean topology https://80.lv/articles/how-tripo-is-tackling-clean-topology-for-its-3d-asset-pipeline
- Unreal forums: overlapping lightmap UVs https://forums.unrealengine.com/t/overlapping-lightmap-uvs-by-x/357385

Generator code / vendor docs (vendor claims marked in the text):
- Hunyuan3D-2 postprocessors.py (FloaterRemover 0.005, FaceReducer 40000 + QEM params) https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2/main/hy3dgen/shapegen/postprocessors.py
- Hunyuan3D-2 de-light stage (ComfyUI node docs; pipeline code mirror) https://comfy.icu/node/DownloadAndLoadHy3DDelightModel , https://huggingface.co/spaces/tencent/Hunyuan3D-2mv/blame/refs%2Fpr%2F6/hy3dgen/texgen/pipelines.py
- Meshy docs: Remesh https://docs.meshy.ai/en/webapp/guides/3d-model/remesh ; AI Texturing https://docs.meshy.ai/en/webapp/guides/3d-model/ai-texturing
- Meshy game-asset-pipeline repo https://github.com/meshy-dev/game-asset-pipeline
- Meshtron paper (AI mesh topology defects) https://arxiv.org/pdf/2412.09548 ; FA-QEM simplification of generated assets https://arxiv.org/abs/2605.14029
- Neural4D cleanup and retopo guides (competing vendor; numbers unverified) https://blog.neural4d.com/user-guide/ai-3d-model-blender-cleanup-complete-mesh-fix-guide-2026/ , https://blog.neural4d.com/user-guide/blender-retopology-ai-3d-models/
- Strayspark: decimate vs remesh; texture resolution https://www.strayspark.studio/blog/reduce-polycount-ai-3d-model-blender-decimate-vs-remesh , https://www.strayspark.studio/blog/texture-resolution-guide-games-512-1k-2k-4k
- Tripo CLI bundled docs (local): `…/node_modules/tripo-cli/skill/commands/{generate,process,make}.md`, `common-errors.md`

Not reachable: reddit.com is blocked for both search and fetch, and the polycount.com pages returned 403 to the fetcher. The r/blender, r/gamedev and r/godot views here are therefore second-hand, via snippets and GitHub issues.
