# Game-asset pipeline hygiene and editability: reference

Scope: what a generated model (Tripo GLB/FBX) needs before it counts as game-ready and easy to edit later. Covers format choice, axes and units, applied transforms, pivots, real-world scale, naming (objects, materials, textures, bones, LODs, collision), modular kits, separate parts and sockets, collision meshes, material slots, keeping a source .blend, and topology and UVs for editability. Engines covered: Godot 4 (primary), Unity, Unreal 5, with Blender as the DCC.

Confidence tags:
- **[doc]**: stated in official engine, DCC, or spec documentation that was read for this note.
- **[talk]**: GDC talk or studio write-up.
- **[forum]**: practitioner consensus (Polycount, Godot forum, Blender Artists).
- **[heuristic]**: common industry practice, not found verbatim in a source read this session. Treat these as defaults the user can override.
- **[unverified]**: from memory. Verify before you hard-code it into the skill.

---

## 0. Top rules (apply to every asset)

| # | Rule | Tag |
|---|------|-----|
| 1 | Deliver **GLB (glTF 2.0)** to Godot. Deliver **FBX** to Unity and Unreal (both still FBX-first). Keep a **.blend** as the editable source of truth. | doc |
| 2 | **1 unit = 1 metre** in Blender, glTF, Godot, and Unity. Unreal uses **1 uu = 1 cm**. Unit conversion happens at export or import, never by scaling objects. | doc |
| 3 | **Apply all transforms** before export (loc 0, rot 0, scale 1). Unapplied scale breaks physics, collision primitives, selection, and LOD. | doc |
| 4 | Pivot rules: **prop = bottom-centre**, **character = ground point between the feet**, **door/lid = hinge axis**, **wheel = hub centre**, **modular piece = the kit's agreed snap point** (Skyrim: ground plane, centred). | doc + talk |
| 5 | Facing: author in Blender with the front facing **-Y** (Z-up). The glTF exporter's +Y-up conversion then makes the front **+Z**, which matches glTF and Godot. | doc |
| 6 | **No negative scale** (mirroring). It flips triangle winding and normals. Apply it, then recalculate normals. | doc |
| 7 | **One material per prop** where possible. Each extra material slot becomes a separate glTF primitive (an extra draw call). Characters: 1, plus 1 more only for a different shader (eyes, hair, glass). | doc + heuristic |
| 8 | Naming: `PREFIX_Name_Descriptor_Variant`, ASCII, no spaces, no dots. LODs `_LOD0.._LOD9`. Collision uses engine-specific tokens (see §6). | doc |
| 9 | Collision cost order, cheapest first: **primitives, then convex hulls, then trimesh**. Trimesh only on static bodies. | doc |
| 10 | Parts that move or swap (doors, wheels, weapons, lids) are **separate objects** with their own pivot. They attach through sockets or bone attachments, never baked into the main mesh. | doc + forum |
| 11 | Every hard edge sits on a UV seam. Leave UV padding between islands. **No overlapping UVs** unless the overlap is a deliberate mirror or tile, and never on lightmap UV2. | forum |
| 12 | Keep **quads in the source**. Triangulate **at export** (Triangulate modifier plus "Apply Modifiers"), not destructively. | doc + forum |
| 13 | Skinned meshes: **≤4 bone influences per vertex**, **one root bone**, rest pose = T-pose (A-pose is tolerated in Godot with "Fix Silhouette"). | doc |
| 14 | Export **deform bones only** and only the needed actions. Name looping clips with the `-loop` suffix for Godot. | doc |
| 15 | Re-import every export into a clean scene and audit it. File sanity: a file under ~10 KB means something went wrong. | doc |

---

## 1. Axes and units per platform

| Platform | Handedness | Up | Model front faces | Unit | Notes |
|---|---|---|---|---|---|
| Blender | right | +Z | **-Y** (the Front view looks along +Y) | 1 BU = 1 m (Unit Scale 1.0) | glTF export: Transform > **+Y Up** on. |
| glTF 2.0 | right | +Y | **+Z** ("the front of a glTF asset faces +Z") | metres (spec §3.4) | Spec: "+Y up, +Z forward, -X right". |
| Godot 4 | right | +Y | **+Z** (the camera looks down -Z, so the asset faces the camera) | metres | Use `look_at(..., use_model_front=true)` and the `Vector3.MODEL_*` constants. Terrain: +X east, -Z north. |
| Unity | left | +Y | +Z | 1 unit = 1 m | FBX default scale factor 0.01 (fixed by "Convert Units"). .blend/.dae factor 1. |
| Unreal 5 | left | +Z | **+X** | 1 uu = **1 cm** | FBX import: "Convert Scene", "Force Front XAxis" (maps front to +X instead of -Y), "Convert Scene Unit" (to cm). |
| Tripo `convert` | n/a | n/a | `export_orientation` `+x` (default) / `-x` / `+y` / `-y` | `auto_size` = real-world metres; `scale_factor` uniform | Set orientation **only on the final convert step**. The generation-time value is not inherited, and the chain gives no error (common-errors.md). |

How to check facing: import into Blender. The asset should face the -Y viewport direction (Numpad 1, the Front view, shows its face). In Godot, put it under a Node3D. The face should point toward +Z (the blue gizmo arrow).

How to fix: rotate the object in Blender, apply rotation, and re-export. Do not rotate the root node in the engine. As a free alternative to a Tripo convert step, fix it locally.

---

## 2. File format choice

| Format | Use for | Strengths | Weaknesses | Tag |
|---|---|---|---|---|
| **GLB** (binary glTF) | Godot delivery, web, AR | Godot's recommended format. Single file with embedded textures. PBR metal/rough. Skins, morphs, animations. Custom props become `extras`. | Triangles only, so **no quads** (Tripo rejects `quad=true` with GLTF output). Embedded textures can't be edited separately in git. | doc |
| **.gltf + .bin + textures** | Godot under version control | Same data. Textures stay separate, so diffs are smaller and textures edit independently. | Many files. Tripo `import` won't take a local `.gltf` (upload a `.glb`). | doc |
| **.blend** (direct in Godot) | Solo or small teams where everyone has Blender | No manual export step. Godot runs Blender's glTF exporter in the background and exposes Blender-only import options. | Blender (3.0+, 3.5+ preferred, official build) is required on **every** machine, including CI. Not available in the Android or web editors. Forum reports of breakage on Blender version jumps (e.g. 4.2). | doc + forum |
| **FBX** | Unity and Unreal delivery. Tripo **quad** output. Mixamo. | Industry standard for Unity/UE. Stores quads, smoothing groups, LOD groups (Max/Maya). | Proprietary. Godot 4.3+ reads it via ufbx (FBX2glTF is discouraged). Unreal pipeline is built against FBX **2020.2**. Unity advises **not** embedding media. | doc |
| **OBJ** | Static mesh exchange only | Universal | No skinning, animation, UV2, or PBR. | doc |
| **USDZ** | iOS AR | n/a | Not a game-engine delivery format. | doc |

Decision:
- Godot target: `.blend` (source) → `.glb` (deliverable). Use `.gltf` separate files when the project is in git and textures change often.
- Unity target: `.blend` → `.fbx`. Use **Bake Axis Conversion** or the Blender FBX "Apply Transform" option [unverified]. Textures live in a `Textures/` folder next to the model, not embedded.
- Unreal target: `.blend` → `.fbx` (Unit Scale and Apply Scalings: see §3, where sources disagree).
- Tripo quad output (`quad=true`) can only be FBX, OBJ, or USDZ. Bring it into Blender, save it as `.blend`, then export a triangulated GLB for Godot.

---

## 3. Transforms and scale

**Rules**
- Before export: Ctrl+A > **All Transforms** on every mesh. Result: location (0,0,0) relative to the parent, rotation 0, scale (1,1,1). [doc: Godot export considerations, Blender manual]
- Blender caveats [doc, Blender manual]:
  - Multi-user mesh data must be made single-user first (Object > Relations > Make Single User).
  - Applying transforms on an armature does **not** update pose, animation curves, or constraints. Apply transforms **before** rigging or animating.
  - Negative scale: use the "Corrective Flip Normals" option (on by default in recent versions) or recalculate normals afterwards.
- Unreal [doc]: spheres and boxes in collision do not work on non-uniformly scaled static meshes. Apply scale.
- Godot import [doc]: **Apply Root Scale** bakes the root scale into meshes and animations, keeping the root at scale 1. Prefer that over scaling nodes.
- Skinned meshes: the armature object must also be at scale 1. If it isn't, the root bone imports with scale 100 or 0.01 (classic Blender → UE issue). [forum]

**Real-world scale defaults** [heuristic: common architectural and game metrics; one talk datapoint marked]

| Object | Typical size (m) |
|---|---|
| Adult human (game) | 1.75–1.85 tall (Skyrim: 128 units ≈ 6 ft ≈ 1.83 m) [talk] |
| Interior door | 0.9 W × 2.0–2.1 H. Gameplay doors are often wider (1.0–1.2) so the camera fits. |
| Wall height (one storey) | 2.7–3.0 floor-to-ceiling; 3.0–4.0 per floor in modular kits |
| Table / counter / chair seat | 0.75 / 0.90 / 0.45 |
| Stair step | rise 0.15–0.20, run 0.25–0.30 |
| Car | 4.0–4.8 L × 1.8 W × 1.4–1.5 H; wheel Ø 0.6–0.7 |
| Crate (small/standard) | 0.5 / 1.0 cube |
| One-handed sword | 0.8–1.0 long |
| Min. traversable corridor | 2 character widths (two AI can pass) [talk: Skyrim] |

How to check: audit bbox size (§15 script) against the table. Flag anything outside 0.5×–2× of the expected size. Also flag the largest dimension if it is >50 m or <0.01 m, which suggests a units bug.

How to fix:
- Free local fix: uniform scale in Blender, then apply.
- Tripo: `auto_size=true` at generation or `scale_factor` on convert. Both cost credits (non-default convert options bill as "complex convert").
- Never fix scale by setting a node scale in the engine.

---

## 4. Pivot and origin per asset class

| Asset class | Pivot | Why | Tag |
|---|---|---|---|
| Floor-standing prop (crate, barrel, chair, tree) | **Bottom-centre** of the bbox, at Z=0 in Blender | Drops onto the ground with Y=0. Rotation spins in place. | doc (Omniverse) + heuristic |
| Wall-mounted prop (sign, torch, painting) | Back-centre (the face that touches the wall) | Snaps flush to the wall. | heuristic (Omniverse lists this class) |
| Hanging prop (lamp, chandelier) | Top attach point | Hangs from the ceiling. | heuristic |
| Character (biped/quadruped) | **Ground, between the feet**. Root bone at origin. | Unity: "stand on the local origin". Unreal: skeletal mesh pivot = root bone. Godot humanoid profile expects facing +Z with no Skeleton node transform. | doc |
| Door, lid, hatch, drawer | **Hinge axis** (door) / slide-start face (drawer), as a separate object | Rotation or translation works with no math. Centre pivot = classic "door rotates around its middle" bug. | doc (Omniverse) + forum |
| Wheel | Hub centre, axle along the local X (side) axis | Spin = one-axis rotation. Godot `-wheel` hint creates a VehicleWheel3D. | doc |
| Weapon / held item | Grip point (where the palm closes), blade/barrel along a fixed axis (document the axis per project) | Drops straight into a hand socket or BoneAttachment3D with zero offset. | forum + heuristic |
| Modular kit piece | Agreed kit point. Skyrim default: **ground plane, centred**. Unreal docs: **a corner** for grid snapping. Exceptions: pipes at an edge, platforms at the base. | Snapping. Changing it later means "manually updating hundreds of instances". | talk + doc (sources disagree, see §16) |
| LODs | **Identical** pivot and alignment to LOD0 | Popping and offsets otherwise. | doc (Unreal) |
| Collision mesh | Same object space as the render mesh (shared origin) | The importer pairs them by name or parenting. | doc |

How to check: in the audit, `origin_to_bottom_z` should be ≈0 for floor props and `xy_offset_from_center` ≈ (0,0). For hinged parts, the object origin should lie on the bbox edge, not the centre.

How to fix (Blender):
- Bottom-centre: Object > Set Origin > Origin to 3D Cursor, with the cursor snapped to the bbox bottom-centre. Or move the geometry so the bbox bottom-centre sits at world 0 (§15 fix script).
- Hinge: snap the cursor to the hinge edge, then Set Origin to 3D Cursor.
- In-engine workaround when you can't re-export: parent the mesh under a Node3D or empty placed at the desired pivot, and rotate the parent. [forum]
- Tripo: `convert` with `pivot_to_center_bottom=true` (complex-convert credits). It only handles the bottom-centre case.

---

## 5. Splitting into parts (doors, wheels, weapons, accessories)

Rules:
- One object per independently moving or swappable part. Each has its own pivot (§4) and transforms applied, and is named `<Asset>_<Part>`, e.g. `SM_Car_Wheel_FL`, `SM_Chest_Lid`.
- Keep parts **in the same file** when they always ship together (car + 4 wheels, chest + lid). Godot imports them as child nodes. Ship separate files for interchangeable items (weapons, hats).
- Mirrored parts get `_L`/`_R` (or `_FL`/`_FR`/`_RL`/`_RR`) suffixes. Skyrim used L/R suffixes for mirrored kit pieces. [talk]
- Skinned characters: keep the body as **one skinned mesh** where possible. Unity: two skinned meshes can roughly double render time. Unreal merges multi-part skeletal meshes at no penalty. Swappable gear can be separate meshes skinned to the same skeleton. [doc]

Attachments per engine:

| Engine | Mechanism | Authoring rule | Tag |
|---|---|---|---|
| Godot | `BoneAttachment3D` | In Blender, parent the item to a **bone** (Parent > Bone, keep transform), not to the armature. Godot imports it as a BoneAttachment3D. Bone constraints (Child Of, Copy Transforms) are **not** exported to glTF. A dedicated non-deforming `hand_r_socket` bone lets you adjust the grip without touching deform bones (exclude it from "Deformation Bones Only", or keep it as a deform bone with 0 weights). | forum + doc |
| Unreal | Sockets | Static mesh: an empty named `SOCKET_<RenderMeshName>_##`. Only **one** render mesh with sockets per FBX. Skeletal mesh sockets are usually added in the editor on bones. | doc |
| Unity | Child transforms / empties | Export empties as child transforms (e.g. `Socket_Hand_R`) and attach by script. | heuristic |

How to check: the audit lists objects. A single merged mesh for something with obviously separable parts (door in frame, wheels on car) is a finding.

How to fix:
- Tripo `mesh segment` (v2.0 gives semantic labels), then `convert` with `part_names` to export chosen parts. `mesh complete` fills holes left by cutting (credits).
- Locally in Blender (free): Edit Mode > select linked (L) > P > Selection, then set the origin per part. Hidden faces behind the removed part will be missing. Cap them (Fill / Grid Fill) or accept it if they're never visible.
- Note: Tripo `generate_parts` silently yields no parts with `smart_low_poly=true`, and yields triangulated parts with `quad=true`.

---

## 6. Naming conventions

### 6.1 Asset and object names

Pattern [doc, Epic]: `[TypePrefix]_[AssetName]_[Descriptor]_[Variant]`. Use ASCII, PascalCase or snake_case consistently, with **no spaces or dots**. Blender appends `.001` on duplicates; rename those before export.

| Type | Prefix (Epic) | Example |
|---|---|---|
| Static mesh | `SM_` | `SM_Crate_Wood_01` |
| Skeletal mesh | `SK_` | `SK_Knight` |
| Skeleton | `SKEL_` | `SKEL_Humanoid` |
| Physics asset | `PHYS_` | `PHYS_Knight` |
| Material / instance | `M_` / `MI_` | `M_Wood`, `MI_Wood_Dark` |
| Texture | `T_` | `T_Crate_Wood_01_BC` |
| Animation sequence / montage / blend space / anim BP | `AS_` / `AM_` / `BS_` / `ABP_` | `AS_Knight_Walk` |

Godot has no official prefix scheme. Using the same scheme is harmless. **But** node names feed the import-hint system (§6.3), so never end a name in `col`, `colonly`, `noimp`, `rigid`, `navmesh`, `occ`, `vehicle`, `wheel`, or `loop`/`cycle` by accident. Separators `-`, `_`, and `$` all count, and matching is case-insensitive, so a mesh named `Barrel_Col` **becomes collision**.

Variants: `_01/_02` (Skyrim kits). Mirrored: `_L/_R`. Junction pieces: `1Way/2Way/3Way/4Way` (Skyrim). [talk]

### 6.2 Texture suffixes [forum/heuristic: no single official standard]

| Map | Common suffixes | Notes |
|---|---|---|
| Base colour / albedo | `_BC`, `_D`, `_Albedo` | sRGB |
| Normal | `_N` | Linear. glTF/Godot/Blender = OpenGL (+Y), Unreal = DirectX (-Y). Flip G when moving to UE. [heuristic] |
| Packed occlusion/roughness/metallic | `_ORM` (R=AO, G=Rough, B=Metal) | Matches glTF exactly: AO in R, roughness in G, metallic in B. [doc: Blender glTF manual] |
| Roughness / Metallic / AO | `_R`, `_M`, `_AO` | Linear |
| Emissive | `_E` | |
| Opacity mask | `_A`/`_Mask` | |

Rule: one suffix scheme per project. Packed maps name their channels in order (`_ORM`, `_RMA`).

### 6.3 Collision and helper tokens

| Engine | Token | Meaning | Tag |
|---|---|---|---|
| Godot | `-col` | Keep mesh, add a **trimesh** StaticBody3D child (accurate, slow) | doc |
| Godot | `-convcol` | Keep mesh, add a **convex** collision child | doc |
| Godot | `-colonly` | Remove mesh, make a StaticBody3D trimesh from it (or a primitive from an **empty's draw type**: Cube→Box, Single Arrow→SeparationRay, Image→WorldBoundary, Sphere/other→Sphere) | doc |
| Godot | `-convcolonly` | Remove mesh, convex collision (convex decomposition) | doc |
| Godot | `-rigid` | Import as RigidBody3D | doc |
| Godot | `-navmesh` | Becomes NavigationMesh, mesh removed | doc |
| Godot | `-occ` / `-occonly` | Occluder3D (keep / replace mesh) | doc |
| Godot | `-vehicle` / `-wheel` | VehicleBody3D / VehicleWheel3D | doc |
| Godot | `-noimp` | Skip the node or animation | doc |
| Godot | `-loop` / `-cycle` | Looping animation (no separator needed, start or end of the clip name) | doc |
| Godot (material) | `-alpha` / `-vcol` | Alpha transparency / vertex-colour albedo | doc |
| Unreal | `UBX_<Mesh>_##` | Box (don't move its verts) | doc |
| Unreal | `UCP_<Mesh>_##` | Capsule (~8 segments) | doc |
| Unreal | `USP_<Mesh>_##` | Sphere (~8 segments) | doc |
| Unreal | `UCX_<Mesh>_##` | Any closed **convex** mesh | doc |
| Unreal | `SOCKET_<Mesh>_##` | Socket empty | doc |
| Unity | (none native) | Use a `_Collider`/`UCX_` child plus a MeshCollider or primitive colliders set up in a postprocessor. | heuristic |

Godot caveats: hints can be disabled with `nodes/use_node_type_suffixes=false` (`-noimp`, `-vcol`, `-loop` still work). The docs favour primitives over trimesh/convex. Draw-type-to-shape mapping is documented for Collada import only (re-checked 2026-10-31). Through a plain `.glb`, empties' draw type may not survive [unverified], so for GLB use **mesh** colliders with `-colonly`/`-convcolonly`, or set Physics > Shape Type per mesh in **Advanced Import Settings** (Body Type Static/Dynamic/Area; Shape Type Trimesh / Decompose Convex / Simple Convex / primitives; decomposition "Precision").

### 6.4 LOD naming

| Engine | Convention | Behaviour | Tag |
|---|---|---|---|
| Unity | `Name_LOD0`, `Name_LOD1`, … (grouped under one parent) | Auto-creates an LOD Group on FBX import. Newer Unity also has "Mesh LOD" auto-generation on import. | doc |
| Unreal | FBX LOD Group (Max/Maya). From Blender: an empty with custom prop `fbx_type=LodGroup` holding `_LOD0.._LODn` (third-party add-on behaviour); "Import Mesh LODs" must be on. | Forum reports of meshes splitting instead of grouping. Test per UE version. | doc + forum |
| Godot 4 | No suffix convention needed. **Generate LODs** on import (mesh simplification, tunable "Normal Merge Angle"). Manual LODs use VisibilityRange (HLOD) on separate nodes. | Auto LOD is default. | doc + unverified (VisibilityRange detail) |

Rules: ≤9 LODs (single digit), all LODs share pivot and alignment, lower LODs may use fewer materials. [doc + forum]

### 6.5 Bone names

- Use common English names with consistent sides: `LeftArm`/`RightArm` or `upperarm_l`/`upperarm_r`. Unity auto-Avatar and Godot `SkeletonProfileHumanoid` auto-mapping both match name patterns. [doc]
- Humanoid minimum: **15 bones** (Unity). Example hierarchy: `Hips > Spine > Chest > Neck > Head`, `Hips > UpLeg > Leg > Foot > Toe`. [doc]
- **One root bone.** Unreal: skeletal mesh pivot = root bone. A common practice is renaming the Blender armature object to `root` so UE's extra root becomes the real root. [doc + forum]
- Tripo rig: `--spec mixamo` gives Mixamo bone names (Unity Humanoid / Mixamo workflows), `--spec tripo` gives Tripo's names. Pick by target, and retarget in Godot with BoneMap + SkeletonProfileHumanoid.

---

## 7. Collision meshes

Cost and accuracy ladder [doc: Godot physics]:

| Type | Speed | Use for | Limits |
|---|---|---|---|
| Primitive (box, sphere, capsule, cylinder) | Fastest, most reliable | **All dynamic bodies** (RigidBody, CharacterBody), most props | Godot recommends primitives for dynamic objects. UE spheres/boxes break on non-uniform scale. |
| Single convex hull | Fast | Small irregular props | Must be truly convex and closed (UE `UCX_`). |
| Multiple convex (decomposition) | Medium | Concave props: chairs, arches, hollow boxes | Benefit fades after "a certain number" of hulls. UE: hulls must **not** intersect, so leave gaps. Auto-decomposition is "unpredictable" (UE). |
| Trimesh / concave | Slowest, most accurate | Static level geometry, terrain, whole buildings | **Static bodies only** (Godot). Not for CharacterBody or dynamic RigidBody. |

Rules:
- The collision mesh is a **separate, much simpler mesh**, never the render mesh, for anything but static level geometry. [doc]
- Heuristic budgets [heuristic]: prop collision ≤ 1–3 primitives or ≤ 4–8 convex hulls. Each hull should have tens of vertices, not hundreds (PhysX caps a convex hull at 255 polygons [unverified]).
- Don't transform collision shapes in-engine. A single untransformed shape on a StaticBody lets broad-phase culling work (Godot). [doc]
- Character capsule: lives in the engine (CharacterBody3D + CapsuleShape3D), not in the model file. Size it from the model bbox: height ≈ character height, radius ≈ 0.25–0.35 m [heuristic].
- Floors in modular kits need real thickness (Skyrim "stack test": floors must not be paper-thin). Players must not get stuck. Stress-test collision across piece seams. [talk, Level Design Book]

How to check: no collision object in the file → a finding for anything the player touches. Collision tri count >10% of the render mesh → a finding. Hull non-convex or open → a finding (UE).

How to fix:
- Godot editor (free): Mesh menu > **Create Single Convex Collision Sibling** (Quickhull), **Create Multiple Convex Collision Siblings** (V-HACD), **Create Trimesh Static Body**. Or Advanced Import Settings > Physics.
- Blender (free): duplicate the mesh, Decimate (Collapse) or the Convex Hull operator, name it `<mesh>-colonly` (Godot) or `UCX_<mesh>_00` (UE), and parent it to the render mesh.

---

## 8. Modular kits and grid snapping

From Skyrim GDC 2013 (Burgess/Purkeypile) [talk], 80.lv kit article, and The Level Design Book:

- **Footprint** = the full bounds of a piece. Geometry stays inside it and touches the edge only where it snaps.
- **Sub-kit footprints must be multiples of each other.** A 512 room tiles with a 256 hallway; a 384 room leaves gaps or overlaps.
- **Grid snap as large as possible.** Designers often use **half the footprint**.
- Hallways tile on one axis, rooms on two. **Avoid kits that tile on all axes** (they look the most repetitive).
- Default pivot: ground plane, centred (exceptions documented per kit). **Lock pivots, footprint, and transition metrics early.** Changing them later breaks hundreds or thousands of placements.
- One **uniform door/portal size across all kits**, so kits interconnect.
- Fix floor thickness up front to avoid co-planar (z-fighting) faces when stacking.
- Avoid "patch" pieces. Fix the core piece's footprint instead.
- Stress tests: loopback, stack, gap.
- Process: concept → proof (1–3 wk, near-blank meshes) → graybox (1–4 wk, most-used sub-kit first) → build-out → polish. Finish one piece fully before making variants.
- Texel density uniform across the kit. Use tiling or trim textures for walls of different lengths rather than unique textures per piece. [forum]

Grid numbers per engine [heuristic unless tagged]:

| Engine | Typical module grid |
|---|---|
| Unreal | Power-of-two cm: 64/128/256/512 uu (Skyrim used 512 Bethesda units). Many teams use 100/200/400 cm instead (see §16). |
| Godot | Metric: 1, 2, or 4 m. GridMap `cell_size` defaults to (2,2,2) m [unverified; the GridMap tutorial gives no number, only "set Size to match your mesh size" and "uncheck Center Y"]. See §17.4 for MeshLibrary rules. |
| Unity | Metric: 1/2/4 m (ProBuilder/ProGrids default 1 m snap [unverified]). |

How to check modular pieces: bbox dimensions must be exact multiples of the grid (tolerance ≤1 mm). Pivot at the agreed point. Open edges must lie exactly on the footprint boundary.

How to fix: snap verts to the grid in Blender (Snap to Increment / Absolute Grid Snap), or scale non-uniformly to the nearest multiple and then apply. Tripo output is organic and will **not** land on grid. Treat AI-generated kit pieces as needing a manual snap pass.

---

## 9. Materials and textures (slot organisation)

- Every material slot = one glTF primitive = one draw call. Blender export "No Export" materials **merges primitives and loses slot info**. "Placeholder" keeps the slots. [doc]
- Unity: "keep the number of materials per model as low as possible". Use more than one on a character only for a different shader (e.g. eyes). [doc]
- Unreal: **slot order matters**. Material 0 should be the body for characters. Use "Reorder Material to FBX Order". Only colour and normal maps auto-connect on FBX import. [doc]
- Budgets [heuristic]: prop 1 slot. Prop with glass/emissive/alpha part: 2. Character: 1–2 (+1 hair/eyes). Hero vehicle: ≤3–4. Kits: share 1–3 trim/tiling materials across the whole kit.
- glTF material mapping (Blender exporter) [doc]: use a Principled BSDF. Metallic/roughness come as one Non-Color image (**G = roughness, B = metallic**). AO goes into a `glTF Material Output` group node input "Occlusion" (R channel). Normal maps must be tangent space via a Normal Map node. Emission >1 uses `KHR_materials_emissive_strength`. Alpha mode is auto (Opaque/Mask/Blend).
- **Backface culling:** Blender's default is off, which exports as **double-sided**, and Godot then disables culling (a performance cost). Enable Backface Culling per material before export. [doc]
- Texture formats out of Blender: PNG/JPEG (WebP optional). Godot: choose "Embedded Texture Handling" (Extract / Embed Basis Universal / Uncompressed) and use **Extract Materials** to `.tres` so edits survive re-import. Renaming the material in the source breaks the link. [doc]
- Unity: don't embed textures in FBX. Use a `Textures/` folder next to the model. [doc]
- Texture sizes are power-of-two. Keep texel density consistent within a scene (sibling research note covers the numbers).

How to check: count slots per mesh, find unused slots, find duplicate materials (`Material.001`), find images not power-of-two, find double-sided materials on closed meshes.

How to fix: Blender Material > Remove Unused Slots, merge duplicates (Ctrl+L > Link Materials), rename slots to `M_<Asset>_<Part>`, bake multi-material to one atlas (Tripo `convert pack_uv=true` costs credits; Blender bake is free).

---

## 10. Topology, normals, and UVs for editability

| Concern | Rule | Tag |
|---|---|---|
| Quads vs tris | Source: quads (edge loops, easy to select, subdivide, retopo). Export: triangulated. Godot: triangulate first, because import triangulation of n-gons is "unpredictable". Unreal: triangulate in the DCC, because exporter triangulation can cause random smoothing. | doc |
| N-gons | None in deliverables. Allowed only on flat, non-deforming source faces. | doc + forum |
| Tripo quads | `quad=true` / `tripo-p2`: FBX/OBJ/USDZ only. `decimate --quad` limit is 500–10000 faces. | Tripo docs |
| Hard edges ↔ UV seams | Every hard edge must be a UV seam, with padding. Not every seam needs a hard edge. Hard edges on existing seams cost no extra vertices. | forum (Polycount) |
| Vertex count | The engine vertex count exceeds the DCC count. Every UV seam, hard edge, and vertex-colour split duplicates verts. Minimise seams, but not at the cost of stretching. | doc (Unity) |
| Normals | Export custom/split normals plus **tangents**. Godot "Ensure Tangents" generates MikkTSpace tangents, but the docs recommend exporting them. For high-poly baked normal maps, use Unity Smoothing Angle 180°. | doc |
| UV0 | No stretching or overlap (unless mirrored or tiled on purpose), 0–1 space, consistent texel density. Edge padding of 4–16 px depending on resolution and mip count [heuristic]. | forum + heuristic |
| UV1/UV2 (lightmap) | **No overlap at all**, unique. Godot can generate it on import (Light Baking = Static Lightmaps, Lightmap Texel Size). Keep ≤2 UV maps. Some glTF readers don't support multiple UV maps. | doc |
| Manifold / closed | Weld verts, cap holes, remove hidden interior faces, especially before auto-skinning (Unity). Tripo `mesh complete` / Blender Fill. | doc |
| Deformation topology | Loops around joints (shoulders, elbows, knees, mouth) for rigged meshes. AI meshes generally lack this, so retopo (Tripo `decimate` v3.0 smart retopology, or a quad remesh) before rigging when deformation matters. | doc (Unity: "topology that deforms well") + heuristic |

Non-destructive editability in Blender:
- Keep modifiers **live** in the .blend: Mirror, Bevel, Weighted Normal, Triangulate (Keep Normals on), Decimate for LODs. Apply them only at export ("Apply Modifiers" in the glTF exporter = the evaluated mesh). [doc]
- Separate collections: `SRC_` (high-poly/source), `EXPORT` (game mesh, LODs, collision), `REF` (reference). Use the glTF exporter's "Selected/Visible/Active collection" filters or Collection Exporters. Collection custom props export as scene `extras`. [doc]
- Use custom properties for engine metadata (e.g. `godot_body=static`). They export as glTF `extras` when "Custom Properties" is on. [doc]
- Don't use Blender **constraints, drivers, or geometry nodes** as the only source of a result the engine needs. They don't export. Bake them: Visual Transform, Visual Geometry to Mesh, Make Instances Real (Parent + Keep Hierarchy on). [doc]

---

## 11. Characters, skeletons, animation hygiene

- Rest pose **T-pose** (Unity, Godot humanoid profile). A-pose works in Godot with Rest Fixer > **Fix Silhouette**. For Tripo rig, ask for a T-pose input image (examples/animation.md). [doc]
- Godot humanoid reference: faces **+Z**, Y-up, **no transform on the Skeleton node**, +Y from parent to child joint. If a Blender export left a transform on the armature, use Rest Fixer > **Apply Node Transform**. Use **Overwrite Axis** to share animations across rigs. **Normalize Position Tracks** (motion scale by Hips height) prevents foot sliding across differently sized characters. [doc]
- Influences: **4 per vertex** (Unity default, glTF exporter default 4; values other than 4/8 display wrong in many viewers; Godot supports up to 8). [doc]
- Export **Deformation Bones Only** for Godot (non-deform bones cause incorrect shading with blend shapes). Remove IK/control bones. Unity bakes IK to FK anyway and still evaluates leftover nodes. [doc]
- Fewer bones = cheaper. Unity example: 15 extra bones on a 30-bone Generic rig = 50% more solve work. [doc]
- Clip export: the Blender glTF default "Actions" mode exports active or **NLA-stashed** actions only. Unstashed actions are silently skipped. Name clips `Walk-loop`, `Idle-loop` for Godot looping. Import FPS ≈ the DCC rate; >30 rarely helps (Godot). Unreal: one animation per skeletal mesh per FBX. [doc]
- Locomotion: Tripo `--animate-in-place` for engine-driven movement. Root motion needs motion on the root bone (Blender add-ons exist to transfer it). [Tripo docs + forum]
- Use Godot **Animation Library** import mode to import clips only and share them across models. [doc]

---

## 12. Source-of-truth and project hygiene

- Keep `<asset>.blend` (source) next to or above the export. **Never** treat the GLB/FBX as the master. Downloaded Tripo files go to `source/raw/` untouched. Edits happen in `.blend`, then re-export.
- Suggested layout [heuristic]:
  ```
  assets/<category>/<AssetName>/
    source/<AssetName>.blend          # master, modifiers live
    source/raw/<tripo_task_id>.glb    # untouched generator output + task.json
    export/SM_<AssetName>.glb         # what the engine imports
    textures/T_<AssetName>_{BC,N,ORM}.png
  ```
- Record export settings: Unity says to note every export option so you can match it on import. Use a scripted exporter (preset or Python) so re-exports are reproducible. [doc]
- In-engine edits that must survive re-import go into **extracted** resources (Godot Extract Materials `.tres`, Save mesh to `.res`) or an import script (`EditorScenePostImport`). Never edit the imported scene directly. [doc]
- Verify after export: file size sanity (<10 KB = broken), re-import into a clean Blender scene, then import into the engine with matching settings. [doc]

---

## 13. Platform checklist matrix

| Check | Godot 4 | Unity | Unreal 5 |
|---|---|---|---|
| Format | GLB/glTF (or .blend) | FBX (.blend possible if Blender is installed) | FBX (2020.2 SDK) |
| Unit at export | 1 m | 1 m (FBX: Convert Units / Apply Transform) | cm (Unit Scale 0.01 **or** "FBX All" scaling, see §16) |
| Front axis | +Z (Blender -Y) | +Z | +X ("Force Front XAxis" on import) |
| Pivot | Prop base / feet | same | same; skeletal = root bone; static grid kits often corner |
| Collision | `-col`/`-convcol`/`-colonly`/`-convcolonly` or Advanced Import Physics | Colliders in a prefab / postprocessor | `UBX_/UCP_/USP_/UCX_<Mesh>_##` |
| LOD | Auto-generated on import | `_LOD0.._LODn` auto LOD Group, or Mesh LOD | FBX LOD group, "Import Mesh LODs" |
| Sockets | BoneAttachment3D (bone-parented objects) | Child transforms | `SOCKET_<Mesh>_##` / skeleton sockets |
| Normal map | OpenGL (+Y) | OpenGL (+Y) | DirectX (-Y): flip G |
| Skin influences | 4 (up to 8) | 4 (raise via Skin Weights) | 4–8 [unverified] |
| Loop clips | `-loop` suffix | Import settings | Per sequence |
| Material slots | 1 per prop; disable double-sided | Minimise; extract or remap | Slot 0 = body; reorder to FBX |

---

## 14. Tripo option ↔ hygiene problem map (all of these cost credits; prefer the free Blender fix)

| Problem found | Tripo fix (credits) | Free local fix (Blender/Godot) |
|---|---|---|
| Wrong facing | `convert export_orientation=±x/±y` (last step only) | Rotate + apply rotation, re-export |
| Wrong size | `auto_size=true` (generate) / `convert scale_factor` | Uniform scale + apply |
| Pivot not at base | `convert pivot_to_center_bottom=true` | Set origin / translate mesh (§15 script) |
| Monolithic mesh, needs parts | `mesh segment` (v2 semantic) → `convert part_names=[…]`, `mesh complete` for holes | Separate by loose parts / selection (P), set origins, cap holes |
| Too many polys / need LODs | `mesh decimate` (500–20000 tri, `bake=true`), one call per LOD from the same source | Decimate modifier (Collapse) per LOD, or Godot auto LOD |
| Need editable quads | `quad=true` or `decimate --quad`, **FBX/OBJ only** | Quad remesh add-ons; keep tris if not deforming |
| Bad/missing UVs | `mesh uv` (≤80k tris) / `decimate --smart-uv` (v3.0) / `convert pack_uv` | Smart UV Project + pack (loses the texture unless re-baked) |
| Multiple materials → one | `convert pack_uv=true` | Bake to an atlas in Blender |
| Needs a skeleton | `anim check` → `anim rig --spec mixamo|tripo` → `retarget` | Rigify / manual (slow) |
| Format | `convert --format FBX/GLTF/…`, `--fbx-preset blender|3dsmax|mixamo` | Blender import/export (free, preferred) |

Skill guidance: run the audit locally first (free). Present findings with both a free local fix and a credit-costing Tripo fix. Preflight credit cost with `--dry-run --json`. Apply only after the user approves.

---

## 15. How to check and fix (tested scripts)

Tested 2026-10-30 with the local Blender (`/opt/homebrew/bin/blender`) on a sample GLB. It correctly reported unapplied scale and origin-not-at-base. After the fix it reported no warnings and size [0.8, 0.8, 1.0] m.

### 15.1 Audit (`blender -b --factory-startup -P audit_glb.py -- model.glb`)
The script prints one line, `AUDIT_JSON {...}`, containing per-object transforms, GPU vs welded vertex counts, tris/quads/ngons, non-manifold edges (after a weld), loose verts, UV layers, materials, shape keys, max bone influences, bone count and root bones, bbox in metres, pivot offsets, actions, and image sizes, plus a `warnings[]` list.

```python
import bpy, bmesh, sys, json, math
from mathutils import Vector
path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = path.lower().rsplit(".", 1)[-1]
if ext in ("glb", "gltf"): bpy.ops.import_scene.gltf(filepath=path)
elif ext == "fbx": bpy.ops.import_scene.fbx(filepath=path)
elif ext == "obj": bpy.ops.wm.obj_import(filepath=path)
r = {"file": path, "objects": [], "warnings": []}
allmin = Vector((1e9,)*3); allmax = Vector((-1e9,)*3)
for ob in bpy.context.scene.objects:
    o = {"name": ob.name, "type": ob.type,
         "loc": [round(v,4) for v in ob.location],
         "rot": [round(math.degrees(v),2) for v in ob.rotation_euler],
         "scale": [round(v,4) for v in ob.scale], "parent": ob.parent.name if ob.parent else None}
    if ob.type == "MESH":
        me = ob.data
        bm = bmesh.new(); bm.from_mesh(me)
        gpu_verts = len(bm.verts)  # glTF import keeps seam/hard-edge splits = engine vertex count
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # weld so manifold check is meaningful
        tris = sum(1 for f in bm.faces if len(f.verts)==3)
        quads = sum(1 for f in bm.faces if len(f.verts)==4)
        o.update(gpu_verts=gpu_verts, welded_verts=len(bm.verts), faces=len(bm.faces),
                 tris_equiv=sum(len(f.verts)-2 for f in bm.faces), tris=tris, quads=quads,
                 ngons=len(bm.faces)-tris-quads,
                 non_manifold_edges=sum(1 for e in bm.edges if not e.is_manifold),
                 loose_verts=sum(1 for v in bm.verts if not v.link_edges),
                 uv_layers=[u.name for u in me.uv_layers],
                 materials=[m.name if m else None for m in me.materials],
                 shape_keys=len(me.shape_keys.key_blocks) if me.shape_keys else 0)
        bm.free()
        for c in (ob.matrix_world @ Vector(c) for c in ob.bound_box):
            allmin = Vector(map(min, allmin, c)); allmax = Vector(map(max, allmax, c))
        if ob.vertex_groups:
            mx = max((sum(1 for g in v.groups if g.weight > 1e-4) for v in me.vertices), default=0)
            o["max_influences"] = mx
            if mx > 4: r["warnings"].append(f"{ob.name}: {mx} bone influences >4")
        if any(s < 0 for s in ob.scale): r["warnings"].append(f"{ob.name}: negative scale")
        if not me.uv_layers: r["warnings"].append(f"{ob.name}: no UV map")
        if len(me.uv_layers) > 2: r["warnings"].append(f"{ob.name}: >2 UV maps")
    if ob.type == "ARMATURE":
        o["bones"] = len(ob.data.bones)
        o["root_bones"] = [b.name for b in ob.data.bones if b.parent is None]
        if len(o["root_bones"]) > 1: r["warnings"].append(f"{ob.name}: {len(o['root_bones'])} root bones")
    if any(abs(s-1) > 1e-4 for s in ob.scale): r["warnings"].append(f"{ob.name}: unapplied scale {o['scale']}")
    r["objects"].append(o)
if allmin.x < 1e8:
    dims = allmax - allmin; ctr = (allmin + allmax) / 2   # Blender is Z-up after import
    r["bbox_m"] = {"min": [round(v,4) for v in allmin], "max": [round(v,4) for v in allmax],
                   "size": [round(v,4) for v in dims]}
    r["pivot_check"] = {"origin_to_bottom_z": round(allmin.z,4), "xy_offset_from_center": [round(ctr.x,4), round(ctr.y,4)]}
    if abs(allmin.z) > 0.01*max(dims.z,1e-6) + 1e-3: r["warnings"].append(f"origin not at base: min Z = {allmin.z:.4f} m")
    if max(dims) > 50 or max(dims) < 0.01: r["warnings"].append(f"suspicious scale: {max(dims):.4f} m")
r["actions"] = [a.name for a in bpy.data.actions]
r["materials_total"] = len(bpy.data.materials)
r["images"] = [(i.name, list(i.size)) for i in bpy.data.images]
print("AUDIT_JSON " + json.dumps(r))
```

Extra checks worth adding: names ending in Godot hint tokens (§6.3 regex `[-_$](col|colonly|convcol|convcolonly|noimp|rigid|navmesh|occ|occonly|vehicle|wheel)$`, case-insensitive). Names containing `.001` or spaces. Non-power-of-two image sizes. Double-sided materials (`use_backface_culling == False`). Facing heuristic for characters (compare the bbox depth of the front vs back half, or ask the user to confirm from a render).

### 15.2 Fix a prop: apply transforms, real-world height, bottom-centre pivot, rename, export GLB
`blender -b --factory-startup -P fix_prop.py -- in.glb out.glb SM_Name [target_height_m]`

```python
import bpy, sys
from mathutils import Vector, Matrix
a = sys.argv[sys.argv.index("--") + 1:]
src, dst, name = a[0], a[1], a[2]
target_h = float(a[3]) if len(a) > 3 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.make_single_user(object=True, obdata=True)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
if target_h:
    k = target_h / (mx.z - mn.z)
    for o in meshes: o.data.transform(Matrix.Scale(k, 4))
    mn, mx = mn * k, mx * k
off = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
for o in meshes:
    o.data.transform(Matrix.Translation(-off)); o.location = (0, 0, 0)
for i, o in enumerate(meshes):
    o.name = o.data.name = name if len(meshes) == 1 else f"{name}_{i:02d}"
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_yup=True, export_apply=True)
print("FIXED", dst, "size_m", [round(v, 4) for v in (mx - mn)])
```

Caveats:
- This flattens hierarchy (`parent_clear`). **Don't run it on rigged characters.** For skinned meshes, apply transforms on the armature and mesh together before rigging, or fix in-engine with Godot's "Apply Root Scale" / Rest Fixer.
- For hinged parts, compute the offset from the hinge edge, not the bbox centre.
- Rotation fixes (facing) need a user-confirmed angle first. Then use `o.data.transform(Matrix.Rotation(angle, 4, 'Z'))` before the pivot step.

### 15.3 Finding → proposed fix options (to present to the user)

| Finding | Severity | Option A (free, local) | Option B (Tripo, credits) |
|---|---|---|---|
| Unapplied scale/rotation | High | `fix_prop.py` (static) / apply in Blender | n/a |
| Origin not at base | Medium | `fix_prop.py` | `convert pivot_to_center_bottom=true` |
| Size implausible | High | `fix_prop.py … <height>` | `convert scale_factor` / regenerate with `auto_size` |
| Faces wrong way | Medium | Rotate Z by ±90/180 and apply | `convert export_orientation` |
| Single mesh, separable parts | Medium | Blender separate + set origins | `mesh segment` → `convert part_names` |
| >1 material on a simple prop | Low | Bake to an atlas | `convert pack_uv=true` |
| No/broken UVs | High | Smart UV Project (texture lost) | `mesh uv` / `decimate --smart-uv` |
| Non-manifold / holes | Medium | Fill / Merge by Distance | `mesh complete` (after segment) |
| N-gons in the deliverable | Low | Triangulate modifier on export | n/a |
| >4 influences | Medium | Weights > Limit Total (4) + Normalize All | n/a |
| Several root bones / extra non-deform bones | Medium | Re-parent under one root; export deform bones only | Re-rig `anim rig` |
| Name triggers a Godot hint by accident | High | Rename | n/a |
| Double-sided materials | Low | Enable Backface Culling, re-export | n/a |

---

## 16. Where sources disagree / it depends

1. **.blend vs .glb into Godot.** The Godot docs support `.blend` import, and it saves an export step. Forum consensus prefers `.glb` for reliability, portability (no Blender on CI or teammates' machines), and version stability. **Default: GLB deliverable + .blend source.**
2. **Modular pivot: centre vs corner.** Skyrim/Bethesda default is ground-plane **centre**. Epic's FBX static mesh doc says build at the origin "generally with the origin at one corner" for grid snapping. Either works if the **whole kit agrees** and it is locked early.
3. **Grid units: power-of-two vs decimal.** Skyrim used 512/256 footprints (power-of-two Bethesda units). Metric teams use 1/2/4 m (100/200/400 cm in UE). The requirement both camps share: sub-kit footprints must be integer multiples of each other.
4. **Blender → Unreal scale.** Option A: Unit Scale 0.01, model at UE size. Option B: Unit Scale 1.0 + FBX "Apply Scalings: FBX All". The wrong combination (1.0 + "All Local") gives a scale-100 armature root. Sources (third-party guides) are inconsistent. **Test with a rigged cube per Blender/UE version.**
5. **Quads vs triangles.** Editability favours quads (Polycount, film workflows, Tripo `quad`). Engines and baking want triangulated, deterministic meshes (Godot, Unreal, Polycount baking). Resolution: quads in source, Triangulate at export, and bake normals from the **same triangulation** the engine will use.
6. **LOD authoring.** Godot auto-generates LODs on import (manual LODs rarely needed). Unity supports both `_LODn` naming and auto Mesh LOD. Unreal's FBX LOD-group import from Blender is unreliable per forum reports. Tripo can make baked LODs with `decimate` (credits). Prefer engine auto-LOD on Godot. Ship manual LODs only for Unity/UE or when auto-LOD breaks silhouettes.
7. **Bone influences.** Unity default 4, Godot up to 8, glTF exporter default 4. **Use 4** unless the target and its viewers all support 8.
8. **Separate meshes on characters.** Unity warns that multiple skinned meshes cost roughly 2×. Unreal says multi-part skeletal meshes are merged at no penalty. For modularity (swappable gear) separate meshes are fine on UE. On Unity and mobile, merge where possible.
9. **Godot `-colonly` primitives via empties.** Documented for Collada only (current docs). Behaviour with a hand-exported `.glb` is unclear. Prefer Advanced Import Settings physics or mesh-based `-convcolonly`.
10. **Texture suffixes.** No official cross-engine standard (`_BC` vs `_D` vs `_Albedo`). Epic documents prefixes, not suffixes. Pick one per project.
11. **`.glb` vs `.gltf` (separate) for Godot.** Godot docs: separate `.gltf` + `.bin` + textures suits version control and keeps textures editable apart from materials. Third-party Blender→Godot checklist (Cinevva): prefer `.glb` because separate-file exports commonly lose textures (broken relative paths). **Default: `.glb`. Use separate `.gltf` only when the project is in git and textures are iterated often, and keep textures next to the `.gltf`.**
12. **Name-suffix collision vs embedded physics.** Godot `-col`/`-colonly` suffixes are the documented, zero-dependency route. The OMI physics glTF extension (`OMI_physics_body`, written by a Blender add-on, read natively by Godot) stores collision in the file instead of inferring it from names. Body types are marked experimental in that guide. **Default: suffixes or Advanced Import Settings. Consider OMI only for multi-engine glTF pipelines.**
13. **Character pivot vs rig root.** Engine-side pivot = ground between the feet (Unity forum, Unreal "pivot = root bone"). Inside the rig, the **pelvis/hips** is the animation root of the body because it works better for IK and walk cycles (Unity forum). Resolution: a `root` bone at the ground origin, with `Hips` as its child. Never make Hips the top-level bone when the engine needs root motion or ground placement.
14. **Texel density targets.** Common rules of thumb: ~512 px/m for third person, ~1024 px/m for first person (Polycount threads, third-party guide). Open-world titles often go lower. No official standard: set per project and keep it **uniform within a kit or scene**.
15. **Triangulate modifier and "Apply Modifiers".** Godot docs: add a Triangulate modifier **and** enable Apply Modifiers on export. One r/blenderhelp thread says to turn Apply Modifiers off, which contradicts the Godot docs and would export quads. **Follow the Godot docs.** The modifier exists so the bake mesh and game mesh share **one** triangulation (Blender dev list, 2012). Put it last in the stack, with Keep Normals on.

---

## 17. Verification pass addendum (2026-10-31): new or sharpened facts

Every item below was re-read from the source this session. Tags as in the header.

### 17.1 Godot import hints: exact behaviour [doc]
- Suffix matching is **case-insensitive**. Separators `-`, `$`, and `_` are all accepted, except `-loop`/`-cycle`, which need no separator but must sit at the **start or end** of the clip name. In Blender, name the clip by renaming the Action/NLA track.
- `nodes/use_node_type_suffixes=false` keeps node types unchanged, but `-noimp`, `-vcol`, and `-loop` still apply. `nodes/use_name_suffixes=false` turns off suffix parsing in the generic importer, **but the glTF importer still checks `-loop`**.
- `-convcol` uses a single ConvexPolygonShape3D, which suits simple or dynamic objects, not level geometry. `-convcolonly` runs **convex decomposition** (several hulls) and removes the mesh.
- Empty-based primitives (`-colonly` on an Empty: Cube→Box, Sphere→Sphere, Single Arrow→SeparationRay, Image→WorldBoundary) are documented for **Collada only** on the current page. Don't rely on them for GLB (confirms §16.9).
- Audit regex (case-insensitive) for accidental hints on object names: `[-_$](noimp|col|convcol|colonly|convcolonly|occ|occonly|navmesh|vehicle|wheel|rigid)$`. On material names: `[-_$](alpha|vcol)$`. On clip names: `(^loop|^cycle|loop$|cycle$)`.

### 17.2 Godot import options that matter for editability [doc]
- **Apply Root Scale** on: bakes scale into meshes and animations, and the root stays (1,1,1). Off: the root node scale is multiplied instead.
- **Blender .blend import > Skins:** "4 Influences (Compatible)" works with every renderer. "All Influences" keeps up to **8**, which Godot supports.
- **Blender .blend import > Materials:** Placeholder / Export / Named Placeholder.
- **Embedded texture handling (glTF/FBX):** Discard All / Extract Textures / Embed as Basis Universal / Embed as Uncompressed. Choose **Extract** for editable textures.
- **Import Script:** `EditorScenePostImport._post_import(scene)` must return the scene. Use it to make in-engine fix-ups (collision, materials, groups) reproducible across re-imports instead of hand-editing the imported scene.
- **Animation FPS:** match the DCC frame rate. Above 30 FPS rarely helps.
- **Light Baking = Static Lightmaps** generates UV2 on import. A smaller lightmap texel size gives more precise lightmaps at a higher bake cost. GridMap's auto-UV2 default texel size is **0.1**.
- **Ensure Tangents** generates MikkTSpace tangents when the file has none.
- Blender export for Godot: with shape keys, enable **Deformation Bones Only**, or "non-deforming bones … will lead to incorrect shading". Blender before 3.2 doesn't export emissive textures. The .blend importer needs Blender **3.0+** (3.5+ recommended), an official blender.org build (not distro/Flatpak), and a path set under Editor Settings > Filesystem > Import > Blender.

### 17.3 Godot retargeting prerequisites (SkeletonProfileHumanoid) [doc]
- The reference pose is a **T-pose**, facing **+Z**, right-handed Y-up, with **no transform on the root node**. Bone +Y points from parent to child joint, and +X rotation bends a joint like a contracting muscle.
- Auto-mapping pattern-matches **common English bone names**. Missing, duplicate, or wrongly parented mappings show as red/magenta in the BoneMap editor. They don't block import, but animations won't share correctly.
- Rest Fixer: **Overwrite Axis** is the key option for sharing animations, but it can damage models whose original bone rest matters. **Fix Silhouette** is for A-pose models (filter out the feet if needed). **Normalize Position Tracks** stores `motion_scale` from Hips height, which reduces foot sliding. **Apply Node Transform** fixes Blender exports that skipped Apply Transform.
- Remove Tracks: **Unimportant Positions** keeps position tracks only on Root and Hips. Enable it for shared AnimationLibraries, and disable it for scene imports that animate accessories.
- **Unique Node** makes the Skeleton a unique-named node, so track paths survive hierarchy changes.

### 17.4 Godot GridMap / MeshLibrary (modular kits in Godot) [doc]
- MeshLibrary source scene: root is `Node3D`, each child is a `MeshInstance3D` (one tile). Only the visual mesh is exported, so other child types are ignored.
- **Materials must sit in the Mesh resource's material slot**, not in the MeshInstance3D's override slot, which is ignored on export. This is an editability trap with imported GLBs: keep materials on the mesh.
- Each tile gets **at most one** `StaticBody3D` child (one or more `CollisionShape3D`, convex for simple tiles, trimesh for complex ones) and at most one `NavigationRegion3D` child.
- GridMap: set Cell Size to the module size and **uncheck Center Y**. A tile authored with its pivot at bottom-centre then sits on the cell floor. The navigation bake cell size must match the NavigationServer map cell size, or navmeshes won't merge.
- Implication for Tripo kit pieces: bottom-centre pivot, footprint an exact multiple of the cell size, one material on the mesh, and collision as a convex child.

### 17.5 Unity colliders: current manual (Unity 6) [doc]
- Mesh colliders are **concave by default** (PhysX). A concave mesh collider must be **static or kinematic**, and **two concave colliders never collide** with each other.
- Faces are **one-sided**: objects pass through from the back. Closed, outward-facing collision meshes matter.
- Rule from the manual: "**Mesh colliders for static scene geometry, compound colliders [convex/primitive] for moving GameObjects.**" Changing a collider mesh at runtime forces an expensive rebuild.
- Unity has no native name-based collision import. Build colliders with an `AssetPostprocessor` or in a prefab. The 255-polygon convex cap isn't on the current page (still [unverified]).

### 17.6 Unreal: collision and pivot details easy to miss [doc + forum]
- FBX static mesh: "the pivot point is always located at the **origin (0,0,0)**". The object's own origin is ignored, so **place the mesh at world origin before export**. Build pieces at the origin, ideally with the origin at one corner, so they snap to the grid.
- `USP_` spheres collide only for **rigid bodies and zero-extent traces**, not swept traces like player movement. Spheres and boxes fail on non-uniformly scaled meshes, so Epic suggests UCX in general. `UCP_`/`USP_` use ~**8 segments**. Don't move the vertices of UBX/UCP/USP.
- Several convex hulls work best when they **don't intersect**. Leave gaps.
- **Only the first mesh's custom collision is imported** when one FBX contains several meshes with custom collision. **One socketed render mesh per FBX.** Rule: **one hero static mesh (plus its UCX/SOCKET helpers) per FBX file.**
- Editor-side fallbacks: Simple primitives, K-DOP **10/18/26**, Auto Convex (Hull Count, Max Hull Verts, Hull Precision: higher = tighter and costlier).
- **Interchange importer (UE 5.5+) regressions (Epic issue tracker):** a mesh can get renamed (`MyAsset1`), which breaks `UCX_` pairing for grouped layouts (worked in 5.4 legacy). Sockets went missing in 5.5/5.6 (target fix 5.7). Interchange has a "one convex hull per UCX" option, and when it's off a UCX mesh is decomposed. **Check: after import, open the mesh and confirm the collision and socket counts match the source file.**
- Skeletal FBX: pivot = root bone. **One animation per skeletal mesh per file**, **one vertex-colour set**, and multi-part skeletal meshes are combined on import. Pre-triangulate, because exporter triangulation with Split Non-Matching Triangles can give "completely random smoothing".
- Epic's naming pattern `[Prefix]_[AssetName]_[Descriptor]_[Variant]` is a **recommendation**. Community guides range from "treat as law" (GitHub UE style guide) to "prefixes optional since search filters by type" (Tom Looman).

### 17.7 glTF spec and Blender exporter facts relevant to hygiene [doc]
- Spec: **metres** and **radians**. Animated nodes **must** use TRS (no `matrix`). A `matrix` must decompose to TRS, which non-uniform scale under rotation breaks (hence Blender's "Flatten Bone Hierarchy" option).
- Spec: **names are not guaranteed unique**. Don't key automation on glTF names alone; dedupe names in Blender before export. Morph-target names aren't standardised: exporters put them in `mesh.extras.targetNames`.
- Spec: custom vertex attributes must start with `_`. The Blender exporter exports mesh attributes **only** if their name starts with `_`.
- Spec: if normals are missing, readers must compute **flat** normals and ignore tangents. Always export normals.
- Blender exporter: images must be PNG or JPEG (WebP optional). Other formats get converted, which slows export. UDIMs split into one image per tile. Area lights, World, and physics/light/material animation aren't exported (Animation Pointer is experimental).
- Blender exporter: the Actions mode (default) exports active and **NLA-stashed** actions. Rename the NLA track to set the glTF clip name. Since Blender **4.4**, tracks merge by action, not by name. Leaving animation unsampled can export wrong animation.
- Blender **Collection Exporters** export at the **collection centre = centre of mass of the root objects**, not world origin. This is a pivot trap. Check the pivot after using Collection Exporters, or keep root objects at the intended origin.
- Format variants: GLB (one file), glTF Separate (`.gltf` + `.bin` + textures, easiest to edit), glTF Embedded (base64, least efficient, hidden behind a preference). Base64 adds about **33 %** payload.

### 17.8 Modular kit numbers (Skyrim GDC 2013 write-up) [talk]
- Character ≈ **128 units** (6 ft). Room footprint example 512³ with hallway 256³. A 384³ room breaks tiling.
- Snap normally at **half the footprint**. Larger snap = faster layout, and misalignment shows more.
- Narrowest walkable space ≥ **2 character widths**. AI handles slopes up to ~**60°**, but kits use **30–45°** because steeper slopes look bad.
- One **uniform door frame size** across the game, so kits swap doors and AI/animation get a fixed reference.
- Scale of reuse: **7 kits → 400+ dungeon cells**. Cave kit used 200+ times, 7 sub-kits, small-hall sub-kit ~**50 pieces**. Phases: proof 1–3 wk, graybox 1–4 wk, build-out months.
- Naming lesson: names like `UtlBayCorInMidPRTT01L01` were **too abbreviated to be used**. Keep tokens readable (`Kit_Sub_Piece_Variant_Side`). `In`/`Out` corners, `L`/`R` mirrors, `01/02` visual variants sharing one footprint.
- Players notice **repeated clutter before repeated architecture**, so spend variation budget on props.

### 17.9 Character/prop pivot consensus [forum]
- Unity forum and Panda3D forum: put standing objects' and characters' pivots at the **base** ("the feet on the ground is as constant as it gets"). Use the bbox centre only for camera targeting or wall collision, computed in code.
- three.js forum: an off-centre origin is an export problem. Fix it in Blender, not with code offsets.

### 17.10 Tripo-specific hygiene hooks (from bundled CLI docs, no credits spent)
- `convert` defaults: `export_orientation` **+x** (forward), `texture_size` 4096, `texture_format` JPEG, `bake` true, `pivot_to_center_bottom` false, `scale_factor` 1, `fbx_preset` blender. **Any non-default convert option bills as "complex convert".**
- `quad=true` → **cannot export GLTF** (FBX/OBJ/USDZ). For Godot, go quad FBX → Blender (.blend source) → triangulated GLB.
- `mesh uv` input ≤ **80,000** equivalent tris (a quad counts as 2). Larger inputs fail and refund, so decimate first. `decimate` 500–20000 tri / 500–10000 quad. `decimate --smart-uv` (v3.0) unwraps in the same task.
- `smartsegment --seg-type model` takes **GLB only**, with an identity `transform` auto-filled. `segment` v2 gives semantic labels. Then `convert -p 'part_names=[...]'` exports chosen parts, which is the Tripo route to "separate meshes for doors/wheels/weapons". Parts still need per-part pivots (hinge, hub, grip) set locally in Blender. Tripo only offers bottom-centre pivots.
- How `export_orientation` (+x default) maps onto glTF's +Z-front convention is **[unverified]**. Always confirm facing in Blender (front toward -Y) after download, before applying any Tripo orientation fix.

---

## 18. Sources (read for this note)

Official docs and specs:
- Godot: Node type customization using name suffixes. https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/node_type_customization.html
- Godot: Available 3D formats. https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html
- Godot: Model export considerations (axes, triangulation, apply transforms). https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/model_export_considerations.html
- Godot: Import configuration. https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/import_configuration.html
- Godot: Advanced import settings. https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/advanced_import_settings.html
- Godot: Collision shapes (3D). https://docs.godotengine.org/en/stable/tutorials/physics/collision_shapes_3d.html
- Godot: Retargeting 3D skeletons. https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/retargeting_3d_skeletons.html
- Godot: BoneAttachment3D class. https://docs.godotengine.org/en/4.2/classes/class_boneattachment3d.html
- Khronos glTF 2.0 spec §3.4 coordinate system and units. https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- Blender manual: glTF 2.0 add-on. https://docs.blender.org/manual/en/dev/addons/scene_gltf2.html
- Blender manual: Apply (transforms, visual transform, make instances real). https://docs.blender.org/manual/en/latest/scene_layout/object/editing/apply.html
- Unreal: FBX Static Mesh pipeline (UBX/UCP/USP/UCX, SOCKET_, pivots, LOD alignment). https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-static-mesh-pipeline-in-unreal-engine
- Unreal: FBX Skeletal Mesh pipeline. https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine
- Unreal: FBX import options reference. https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-import-options-reference-in-unreal-engine
- Unreal: Recommended asset naming conventions. https://dev.epicgames.com/documentation/en-us/unreal-engine/recommended-asset-naming-conventions-in-unreal-engine-projects
- Unreal: Units of measurement. https://dev.epicgames.com/documentation/en-us/unreal-engine/units-of-measurement-in-unreal-engine
- Unreal: Importing static mesh LODs. https://dev.epicgames.com/documentation/unreal-engine/importing-static-mesh-lods-using-fbx-in-unreal-engine
- Unity: Preparing model files for export (scale factors). https://docs.unity.com/en-us/engine/current/manual/assets-and-media/asset-types/models/creating-dccassets/preparing
- Unity: Importing model files. https://docs.unity.com/en-us/engine/current/manual/assets-and-media/asset-types/models/importing/importing-model-files
- Unity: Preparing humanoid models for export. https://docs.unity.com/en-us/engine/6000.6/manual/assets-and-media/asset-types/models/creating-dccassets/using-humanoid-chars
- Unity: Modeling characters for optimal performance. https://docs.unity.com/en-us/engine/6000.6/manual/assets-and-media/asset-types/models/creating-dccassets/modeling-optimized-characters
- Unity: Importing LOD meshes (`_LOD0` naming). https://docs.unity.cn/Manual/importing-lod-meshes.html
- Unity: Level of detail overview. https://docs.unity.com/en-us/engine/current/manual/analysis/graphics-performance-profiling/lod/level-of-detail

Talks, studio write-ups, books:
- Burgess & Purkeypile, "Modular Level Design for Skyrim", GDC 2013 (write-up). https://www.gamedeveloper.com/design/skyrim-s-modular-approach-to-level-design ; slides https://www.slideshare.net/slideshow/gdc2013-kit-buildingfinal/17728576
- 80.lv, "Building huge open worlds: modularity, kits & art fatigue". https://80.lv/articles/building-huge-open-worlds-modularity-kits-art-fatigue
- The Level Design Book, Modular kit design. https://book.leveldesignbook.com/process/blockout/metrics/modular

Forums (practitioner consensus):
- Polycount: hard edges / UV seams / padding threads. https://polycount.com/discussion/comment/2805697 , https://polycount.com/discussion/comment/2717595 , https://polycount.com/discussion/comment/2727831
- Polycount: modular texel density and grid threads. https://polycount.com/discussion/comment/2746032 , https://polycount.com/discussion/comment/2676994
- Godot forum: Blender glTF vs .blend. https://forum.godotengine.org/t/godot-blender-gltf-blend/104654
- Godot forum: attaching weapons to hand bones across animations. https://forum.godotengine.org/t/best-practice-for-attaching-weapons-items-to-a-characters-hand-across-many-animations-godot-4/141270 ; https://ask.godotengine.org/143779/how-to-attach-a-gun-to-a-hand-bone-in-blender-for-import
- Godot forum: grounding a rigged character (root bone offset, apply scale). https://forum.godotengine.org/t/3d-model-with-animation-not-grounded-when-animating/51273
- Blender Artists: character origin for game export. https://blenderartists.org/t/exporting-game-characters-to-game-engine-where-should-your-point-of-origin-be/1191905
- Blender bug T99075 (Blender → UE scale). https://developer.blender.org/T99075
- Unreal forum: Blender LOD-group FBX splitting bug. https://forums.unrealengine.com/t/bug-uefn-importing-fbx-mesh-with-its-containing-lods-causes-them-to-be-split-as-individual-meshes-lods-not-assigned-and-cant-be-added-to-sm/2842602

Added in the 2026-10-31 verification pass (§16.11–15, §17):
- Godot: Using GridMaps (MeshLibrary rules). https://docs.godotengine.org/en/stable/tutorials/3d/using_gridmaps.html
- Unity 6: Mesh colliders introduction. https://docs.unity.com/en-us/engine/6000.0/manual/physics-section/physics-overview/collision-section/collider-shapes/mesh-colliders/introduction
- Unity 6: Importing LOD meshes. https://docs.unity3d.com/6/Documentation/Manual/importing-lod-meshes.html
- Unreal: Setting up collisions with static meshes (K-DOP, auto convex). https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-collisions-with-static-meshes-in-unreal-engine
- Unreal: InterchangeGenericMeshPipeline (collision prefixes, one convex hull per UCX). https://docs.unrealengine.com/5.1/en-US/PythonAPI/class/InterchangeGenericMeshPipeline.html
- Unreal issue tracker: Interchange socket and UCX regressions. https://issues.unrealengine.com/issue/UE-243553 , https://issues.unrealengine.com/issue/UE-248981
- Community UE naming guides (disagreement on prefix strictness). https://tomlooman.com/unreal-engine-naming-convention-guide/ , https://github.com/S0nix12/ue4-style-guide
- Godot forum: OMI physics glTF collision export guide. https://forum.godotengine.org/t/guide-export-blender-collision-shapes-to-godot-with-gltf-omi-physics/142339
- Unity discussions: character pivot at feet vs middle (pelvis as rig root). https://discussions.unity.com/t/does-the-pivot-of-a-character-go-at-the-base-of-the-feet-or-the-middle-and-why/587258
- Blender dev list: why the Triangulate modifier exists (bake/game mesh triangulation parity). https://lists.blender.org/pipermail/bf-committers/2012-November/038094.html
- Texel density rules of thumb (forum + third-party). https://polycount.com/discussion/comment/2258750 , https://www.strayspark.studio/blog/texture-resolution-guide-games-512-1k-2k-4k
- Cinevva Blender → Godot checklist (GLB over separate glTF). https://app.cinevva.com/guides/blender-to-godot-export-checklist

Secondary (used only where marked):
- NVIDIA Omniverse asset requirements: logical pivot position (the fetch returned 403; class list taken from the search snippet). https://docs.omniverse.nvidia.com/kit/docs/asset-requirements/latest/capabilities/geometry/requirements/logical-pivot-position.html
- Cinevva: Blender → Unreal / Blender → Godot export checklists (third-party). https://app.cinevva.com/guides/blender-to-unreal-export-checklist
- Open Unreal Conventions (LOD ≤9, texture suffixes). https://jonasreich.github.io/OpenUnrealConventions/UnrealAssets/Naming.html

Local:
- tripo-cli 0.6.1 bundled docs: `skill/commands/process.md`, `skill/common-errors.md`, `skill/examples/{game-asset,animation}.md` (convert `pivot_to_center_bottom`, `export_orientation`, `scale_factor`, `auto_size`, `part_names`, `pack_uv`, quad→no GLTF, segment/complete/decimate limits).
