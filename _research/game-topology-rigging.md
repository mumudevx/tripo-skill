# Game topology and rigging reference (for tripo-skill)

Research dates: 2026-10-30 (first pass), revised 2026-10-31 (second pass: Polycount wiki read over HTTP, CryEngine/Hunt budgets read in full, Roblox specs, Unity 2022.3 rig/perf pages, glTF skin section re-read, Tripo bundled docs re-checked).

Confidence tags:
- **[DOC]** official engine, spec or vendor documentation, read in this session.
- **[STUDIO]** a published studio budget (CryEngine docs on HUNT: Showdown).
- **[WIKI]** the Polycount wiki, the community reference page, read in full.
- **[COMM]** practitioner consensus from Polycount forum, tech-artists.org, CG Cookie, gamedev.net and Blender Artists.
- **[LEGACY]** official, but from the Unity 5.0 era.
- **[3P]** third-party blog or vendor guide. Low trust.
- **[UNVERIFIED]** widely repeated, but the authoritative page could not be read. Check it before relying on it.

---

## 0. TL;DR rules (apply in this order)

1. **Units.** 1 unit = 1 m in glTF, Godot and Unity. Unreal uses **cm**; its FBX importer converts (`Convert Scene Unit`). A humanoid stands **1.5–2.0 m** tall. Put the origin (pivot) on the floor between the feet. [DOC]
2. **Facing.** For glTF and Godot, the asset front faces **+Z**, +Y is up, and the asset's left side is +X. In Blender, the front faces **−Y**, Z is up, and the left side is +X. Unreal is Z-up and X-forward. [DOC]
3. **Pose.** Use a **T-pose** by default. It is the reference pose for Godot SkeletonProfileHumanoid and Unity Humanoid, and the safest input for auto-riggers. An A-pose deforms the shoulders better; Godot handles it with `Fix Silhouette`, Unreal with a Retarget Pose. Sources disagree; see §6.
4. **Influences.** Use **at most 4 bone weights per vertex**, weights ≥ 0, summing to 1.0. This works everywhere: the glTF set size, the Unity default, the Roblox maximum and the Godot default. Use 8 only on purpose (Unreal desktop via FBX, Godot). [DOC]
5. **Root.** Use exactly **one root bone** (`Root`/`root`) at (0,0,0), with hips/pelvis as its child. Root motion lives on the root bone. Mixamo rigs have no root (Hips is the top bone), so add one when the target is Unreal or Godot root motion. Roblox: the root joint sits at the origin with **no skin influences**. [DOC]/[COMM]
6. **Mesh.** Ship triangles: triangulate yourself and don't let the engine do it. Author and edit in quads. Use **0 n-gons** in deforming zones, at least 2 (mobile) or 3 (hero) edge loops per elbow and knee, and **no poles in the crook of a joint**. Remove hidden faces. Use no T-vertices, doubled faces, gaps or flipped faces. [DOC]+[WIKI]+[COMM]
7. **Budget.** Spend triangles on **silhouette** and **deformation zones**; every edge must be there for a reason. **Vertex count, not triangle count**, drives cost: UV seams, hard edges and material splits duplicate vertices. [WIKI]
8. **Bake and export from the same triangulation.** If the normal-map baker and the engine split quads differently, the shading zig-zags and black artifacts appear. [WIKI]+[DOC Adobe]

---

## 1. Quads vs triangles

| Fact | Source |
|---|---|
| "Polygon is interchangeable with triangle … GPUs only see vertices and triangles." A poly count from a modeling app is "always misleading": switch the counter to **triangles**. | Polycount wiki, Polygon Count [WIKI] |
| A quad can triangulate as a "ridge" or a "valley" depending on the tool. Inspect it in-engine and triangulate specific quads by hand if the diagonal is wrong. | Polycount wiki [WIKI] |
| If triangles flip differently at export than at bake time, "normal-mapped lighting [will] zig-zag across the model. Triangulating before baking will solve this." | Polycount wiki [WIKI] |
| Adobe Substance: there is no standard triangulation. Bake on a triangulated low poly so the triangulation is fixed and known. A mismatch gives **black artifacts** in baked normals. | Adobe Substance 3D Bakers docs [DOC] |
| Quads are worth preserving "as long as possible": edge-loop selection, easier judgment of flow, easier **skin weighting**. | Polycount wiki [WIKI] |
| Low-poly game mesh: "triangles are fine, but you want every edge to be there for a reason." Sculpt base: quads, to avoid pinching. Subdivision model: proper edge loops are crucial. | Polycount wiki, Topology [WIKI] |
| Godot: GPUs render only triangles. Import-time triangulation "may be unpredictable or incorrect, especially for N-gons". Triangulate before export: in Blender use a Triangulate modifier plus Apply Modifiers. | Godot, Model export considerations [DOC] |
| Unreal: "Meshes in Unreal Engine must be triangulated." When the FBX exporter triangulates with Split Non-Matching Triangles checked, smoothing becomes "completely random". | Epic FBX skeletal mesh pipeline [DOC] |
| Blender glTF exporter: "quads and n-gons are automatically converted to triangles". Discontinuous UVs and flat-shaded edges raise the vertex count. | Blender manual 4.2 [DOC] |
| glTF triangles: index count "MUST be divisible by 3 and non-zero". | glTF 2.0 spec [DOC] |
| Long, thin triangles slow rendering (fill rate, quad overdraw) and cause shading errors that carry into normal-map bakes. | Polycount wiki GameRenderingTerminology [WIKI]; Polycount forum [COMM] |
| Roblox: "use quads where possible (avoid N-gons)"; meshes must be watertight with non-zero thickness. | Roblox modeling specs [DOC] |
| N-gons on flat, non-deforming static surfaces are tolerable before the final triangulation; never in deform zones. | gamedev.net / Polycount [COMM] |

**Tripo note:** GLB/glTF cannot store quads. `quad=true` forces FBX, and "quad + GLTF export → rejected" (tripo docs). For a Godot/GLB target, quad output only helps if Blender editing comes next: edit in quads, triangulate on export, and bake on the triangulated mesh.

---

## 2. Edge flow and deformation topology

### 2.1 Where topology matters most

Polycount wiki [WIKI]: "Topology is the most important where the model has to deform the most: **crotch/hips/butt, shoulders/armpits, mouth corners/cheeks, knees, elbows, hands/fingers.**" In-game models should "create a good silhouette, define edge-loops for better deformation, minimize extreme changes between vertex normals … and allow for good UV seams."

### 2.2 Joint loops (characters)

| Zone | Rule | Source |
|---|---|---|
| Elbow / knee (hero) | **≥3 edge loops**: one centered on the pivot and one on each side. Space them **tighter on the compressing side** and wider on the stretching side. A single loop collapses ("candy-wrapper" / hose pinch). | CG Cookie, Blender Artists [COMM] |
| Elbow / knee (alternative) | **2 full loops, one weighted to each bone** of the joint, give "clipping as opposed to collapsing and volume loss"; or 2 loops joined on the inside of the joint. | Polycount forum [COMM] |
| Very low poly (< ~1k tris) | A few extra loops at most: "add another edge loop on the side that bends". | Polycount forum [COMM] |
| Elbow vs knee | They bend in opposite directions, so **mirror** the wedge/extra-loop layout. | Polycount [COMM] |
| Crook of the elbow / back of the knee | Keep it clean: a **star point (pole) in the crook** is a known trouble spot. | Polycount forum [COMM] |
| Twist zones (forearm, upper arm, thigh) | Spread evenly spaced loops **along the limb length**. Linear blend skinning loses volume when twisted. Dual-quaternion skinning handles twist but **balloons bends**. | Polycount forum [COMM] |
| Shoulder / armpit | The hardest zone. Loops go around the deltoid and radiate from the armpit. Two schools exist: "muscle-contour" and "bendy-straw" (loops perpendicular to the arm), plus hybrids. Raising the arm above the reference pose works best via the clavicle bone. | Polycount wiki ShoulderTopology [WIKI] |
| Hip / pelvis | Loops around the thigh root plus a diagonal through the groin, so the leg can lift without tearing the crotch. | Polycount [COMM] |
| Wrist, ankle, neck | 2–3 loops each. | [COMM] |
| Face (only with facial animation or blendshapes) | Concentric loops around the **eyes** and **mouth**, plus the nasolabial fold. Without facial animation, spend the face budget on silhouette (jaw, nose, brow). | Polycount FaceTopology [WIKI]; 80.lv [COMM] |
| Fingers | 2 loops per knuckle on hero characters. Mitten or merged fingers are fine for mobile and crowds. | [COMM] |

### 2.3 Poles, n-gons, manifold

- **Pole** means a vertex with 3 edges or with 5 or more. "Poles can create dimples or bumps … they should be placed in flatter areas to hide them, and are best kept **away from areas that deform**." [WIKI] Good spots: chest, back, side of the head. Bad spots: joint crooks, mouth corners, eye corners.
- **Manifold:** "Avoid T-vertices, doubled faces, gaps, flipped faces, internal unseen faces, floating vertices." [WIKI] T-vertices cause gaps and seams. [WIKI]
- **N-gons:** allow none in deforming zones. Triangulate everything for the final export.
- **Edge flow** follows the anatomy and the clothing design lines. [COMM, 80.lv]

### 2.4 Polygon allocation (silhouette-driven)

- "Add more polygons where there's **curvature**, less where it's straight." [WIKI]
- "Don't waste polys where they don't add to the **silhouette**." [WIKI] Spend on the head outline, shoulders and hands as seen at gameplay camera distance, and on joints.
- Delete loops that neither define shape nor support deformation: flat panels, straight limb segments between joints, helmet interiors. Still give limbs 1–2 profile loops (calf, forearm, biceps); pure tubes look and deform badly. [COMM]
- **Remove hidden faces.** Unity: "cap holes, weld vertices, and remove hidden faces." [DOC] Exception: keep skin under **loose** clothing or armor that can separate during animation.
- **Vertex splits:** "seams in UVs, changes to shading/smoothing groups, and material changes … are all treated as a physical break" and duplicate vertices. Too many of them hurt the transform stage and memory. [WIKI] Unity: its vertex count exceeds the DCC count because vertices split on multiple normals, UVs or vertex colors. [DOC] Heuristic: a well-optimized closed mesh has about **0.5–0.7 render vertices per triangle**. Above **1.0** means too many seams or hard edges. [COMM heuristic]
- **Materials:** as few as possible, more only where shaders differ (for example the eyes). [DOC Unity] The Unity 5 manual says "two or three per character". [LEGACY] HUNT: Showdown uses many materials per hunter because the characters are customizable. That is a deliberate studio trade-off: drawcalls for modularity. [STUDIO]
- **One skinned mesh per character.** "Using two skinned meshes in place of a single one could roughly double the rendering time." [DOC Unity 2022.3]

### 2.5 Triangle budgets

The numbers drift with hardware, so treat them as ranges, not limits. The Polycount wiki itself says to "ask your Lead Artist" and that a model "may stretch anywhere from 2 triangles for a billboard, to 40,000+ triangles for a complex character". [WIKI]

| Asset class | Mobile / standalone VR / web | Mid PC / Switch-class | PC / console hero (LOD0) | Source |
|---|---|---|---|---|
| Hero / player character | 1.5k–5k (high-end mobile up to ~10k) | 8k–20k | 20k–50k; AAA 35k–70k+ | [3P] Neural4D; Polycount [COMM]; HUNT [STUDIO] |
| HUNT: Showdown "Hunters" (main) | – | – | **LOD0 35,000–70,000; LOD3 5,000–8,000** | CryEngine docs [STUDIO] |
| HUNT "Grunts" (non-primary) | – | – | **LOD0 25,000–35,000; LOD3 4,000–5,000** | [STUDIO] |
| HUNT "Bosses" (special) | – | – | **LOD0 25,000–45,000; LOD3 4,000–7,000** | [STUDIO] |
| Secondary NPC / enemy | 1k–3k | 5k–10k | 15k–35k | [COMM] |
| Crowd / background | 300–1k | 1k–3k | 3k–8k | [COMM] |
| Roblox, any single mesh | hard cap **20,000 tris** per mesh | | | Roblox specs [DOC] |
| Character (Unity 5.0 docs) | 300–1500 | 1500–4000 | – | [LEGACY] |
| Hand-held weapon / hero prop | 300–1.5k | 2k–6k | 5k–20k | [COMM] |
| Small prop | 50–500 | 200–1.5k | 500–5k | [COMM] |

HUNT texture budget example [STUDIO]:
- Face 1024², head 256², eyeballs 2048² (512² in some cases).
- Lashes, hair, beard and brows 512² each. Hands 4096×2048. Legs 1024².
- Gear: backpack 2048², harness 2048×1024, trinket 256².
- Grunts use about 1024² per body part. Armored monsters use one material with 7 IDs at about 1024² (armor 2048²).

Hair cards can cost as much as the body (about 20k tris reported for Uncharted 4-era hair [COMM]). On current hardware, shader cost, overdraw and texture memory often matter more than triangle count.

Meta Quest (per frame, not per asset) [DOC Meta]:
- Interactive apps need at least **72 FPS**.
- An older Meta Unity page gives about 500–1000 draw calls and 1–2M triangles per frame, but that is Rift (PC).
- Quest 1 Unreal table: 50–150 draw calls for a busy simulation, 200–400 for a light one.
- The newer pages give no fixed triangle number.

**LOD chain:** each LOD roughly halves the triangle count (LOD1 ≈ 50%, LOD2 ≈ 25%, LOD3 ≈ 10–15%). HUNT's LOD3 is about **10–15%** of LOD0. [STUDIO] Keep the silhouette and the joint loops longest. Godot generates LODs on import (`Generate LODs`), so ship one clean LOD0 for Godot. [DOC]

**Mapping to Tripo `face_limit`** (bundled tripo-cli docs):

| Option | Range |
|---|---|
| P1 | 48–20000 (the CLI enforces ≥ 50) |
| P2 (Preview) | 48–50000 tri / 48–25000 quad |
| `smart_low_poly` (v3.x) | 500–20000 tri / 500–10000 quad |
| `mesh decimate` v2.0/v3.0 | 500–20000 tri / 500–10000 quad |
| `uv` input | ≤ 80k equivalent tris (a quad counts as 2) |

A quad-mode face_limit means about **2 × face_limit** triangles after triangulation.

---

## 3. Coordinate systems, units, facing

| Platform | Hand | Up | Forward / model front | Unit | Notes | Source |
|---|---|---|---|---|---|---|
| **glTF 2.0** | right | +Y | "+Z as forward, and −X as right; the front of a glTF asset faces +Z" | **meter** ("units for all linear distances are meters"); angles in radians | The skinned mesh node's own transform "**MUST be ignored**"; only joint transforms apply. | glTF spec §3.4, §3.7.3 [DOC] |
| **Godot 4** | right | +Y | camera forward −Z; oriented assets face **+Z** and their left side is +X. Use `look_at(..., use_model_front=true)` / `Vector3.MODEL_*` | 1 m | Apply object transforms before export. Export in T-pose/rest, not deformed. glTF 2.0 is the recommended format; FBX goes through ufbx (4.3+). | Godot model export considerations, available formats [DOC] |
| **Unity** | left | +Y | +Z forward | 1 unit ≈ 1 m: compare against the default 1 m cube | Recommended exchange format: FBX. Feet on the local origin. From Blender FBX: Forward −Z, Up Y; or use Bake Axis Conversion on import. | Unity humanoid page [DOC]; Unity forum [COMM] |
| **Unreal 5** | **left** | **+Z** | **+X** forward | **cm** | FBX options `Convert Scene`, `Force Front XAxis` (otherwise front = −Y), `Convert Scene Unit` (to cm). The skeletal-mesh pivot is always the root bone. Use FBX 2020.2. | Epic coordinate system; FBX import options; FBX skeletal pipeline [DOC] |
| **Blender** | right | +Z | "front view looks along the +Y direction", so the **model front faces −Y** | 1 m (default) | glTF exporter `+Y Up` converts. For Y-up FBX targets use "−Z Forward, Y Up". | Blender FBX/glTF manual; Godot docs [DOC] |
| **Roblox** | – | – | – | – | Bones must have scale (1,1,1) and rotation (0,0,0), frozen. The root joint is at (0,0,0) with no influences. One animation track per export. | Roblox specs [DOC] |
| **Mixamo** | – | +Y (FBX) | faces +Z | FBX is often in **cm** (the armature imports at 0.01 scale in Blender) | Fix the scale before the Godot/glTF export. | [COMM/UNVERIFIED] |
| **Tripo** | – | – | default `export_orientation` = **`+x`** ("forward axis", options ±x/±y) | `auto_size=true` scales to real-world meters (v3.0+) | Set `export_orientation` only on the **final `convert`**: downstream steps don't inherit it and silently produce wrong orientation. Always verify facing after download (§5). | tripo-cli docs `commands/generate`, `process`, `common-errors` |

---

## 4. Rig standards

### 4.1 Bone influences per vertex

| Target | Default | Max | Source |
|---|---|---|---|
| glTF 2.0 | "limited to 4 per set" (`JOINTS_n`/`WEIGHTS_n` are VEC4) | more sets are allowed, but "Client implementations MAY support only a single set of up to four" | glTF spec §3.7.3.3 [DOC] |
| Unity | **Standard (4 bones)**: "Use a maximum influence of four bones" | Custom **1–32** (`Max Bones/Vertex`; `Max Bone Weight` drops small weights and renormalizes); global Quality > Skin Weights | Unity 2022.3 FBX Rig tab; humanoid page [DOC] |
| Unreal 5 | fixed path: **4 or 8**, depending on platform | "Unlimited" mode (Project Settings > Engine > Rendering > Skinning) is **capped at 12**. Epic recommends a threshold of **8**: 0–8 influences use the fixed path, 9–12 the unlimited path. Per-mesh LOD `Bone Influence Limit` (0 = project default). | Epic skeletal mesh rendering paths [DOC] |
| Unreal glTF (Interchange) | truncates to **4** | – | UE forum / UE-392966 [COMM/DOC] (first pass) |
| Godot 4 | 4 | **8** (`ARRAY_FLAG_USE_8_BONE_WEIGHTS`). `.blend` import: "4 Influences (Compatible)" or "All Influences" (up to 8; "may not work with all renderers") | Godot Mesh class; import configuration [DOC] |
| Roblox | – | **4** | Roblox specs [DOC] |
| Blender glTF exporter | `Bone Influences` = 4 | values other than 4 or 8 "may appear incorrectly in many viewers"; `Include All Bone Influences` is risky | Blender manual [DOC] |

**Weight rules (glTF):**
- Weights "MUST NOT be negative".
- The float sum "SHOULD be as close as reasonably possible to 1.0". Normalized-integer sums MUST be 255 or 65535.
- Unused slots: weight 0 **and** joint index 0.
- The number of JOINTS_n sets must equal the number of WEIGHTS_n sets.
- The inverse-bind matrices' 4th row must be [0,0,0,1].

[DOC]

**Skill rule:** use 4 for all portable, mobile and glTF assets. Use 8 only for hero faces or cloth on Unreal/Godot desktop, and only through FBX into Unreal.

### 4.2 Bone counts

| Context | Number | Source |
|---|---|---|
| Unity Humanoid | "**minimum of 15 bones**". Required: Hips, Spine, Head, and L/R UpperLeg, LowerLeg, Foot, UpperArm, LowerArm, Hand. Optional: Chest, UpperChest, Neck, Shoulders, Toes, Eyes, Jaw, fingers. | Unity humanoid page [DOC]; the required list comes from `HumanTrait.RequiredBone` [COMM; verify in the Avatar inspector] |
| Unity cost | "15 additional bones on a rig that already has 30 bones takes Unity **50% more operations** to solve in Generic mode." Unity bakes IK into FK; leftover IK nodes still cost CPU. | Unity 2022.3 "Creating models for optimal performance" [DOC] |
| Unity legacy | desktop 15–60, mobile < 30 | [LEGACY] |
| Unreal mobile | **75 bones per mesh section**. More bones means splitting into sections. | Epic [DOC] |
| Unreal desktop | **256 per section** with 8-bit indices (the default). 16-bit indices raise it to `MAX_GPUSKIN_Bones` = 65536. | Epic [DOC] |
| Godot SkeletonProfileHumanoid | **56 bones** in 4 groups (Body, Face, LeftHand, RightHand). Root bone `Root`, scale base bone `Hips`. | Godot class ref [DOC] |
| UE4 Mannequin / UE5 Manny / UEFN / MetaHuman | 68 / **89** / 88 / 342 | Reallusion manual [COMM, vendor] (first pass) |
| Mixamo | about 65 with full fingers; the Skeleton LOD option reduces finger chains (about 49 / 41 / 25) | [UNVERIFIED: Adobe help returned 403] |

Practical targets:
- Mobile humanoid: **20–40 deform bones**.
- PC/console hero: 50–90 deform bones, twist bones included.
- A facial rig adds 20–250 bones.

Export **deform bones only**: Blender glTF `Export Deformation Bones Only`. Godot *requires* this when the model has blend shapes, or the shading is wrong. [DOC Godot available formats]

### 4.3 Humanoid bone-name map (for renaming and mapping)

| Godot (SkeletonProfileHumanoid) [DOC] | Unity (HumanBodyBones) | Mixamo (`mixamorig:`) | UE5 Mannequin |
|---|---|---|---|
| Root | (n/a; Generic root node) | (none: Hips is the top bone) | root |
| Hips | Hips | Hips | pelvis |
| Spine | Spine | Spine | spine_01 |
| Chest | Chest | Spine1 | spine_02 / spine_03 |
| UpperChest | UpperChest | Spine2 | spine_04 / spine_05 |
| Neck | Neck | Neck | neck_01 (/ neck_02) |
| Head | Head | Head (+HeadTop_End) | head |
| Jaw, LeftEye, RightEye | Jaw, LeftEye, RightEye | – | (MetaHuman facial) |
| LeftShoulder (parent UpperChest) | LeftShoulder | LeftShoulder | clavicle_l |
| LeftUpperArm | LeftUpperArm | LeftArm | upperarm_l |
| LeftLowerArm | LeftLowerArm | LeftForeArm | lowerarm_l |
| LeftHand | LeftHand | LeftHand | hand_l |
| LeftThumbMetacarpal / Proximal / Distal | LeftThumbProximal / Intermediate / Distal | LeftHandThumb1/2/3(/4) | thumb_01_l/02/03 |
| Left{Index,Middle,Ring,Little}{Proximal,Intermediate,Distal} | same pattern | LeftHand{Index,Middle,Ring,Pinky}1/2/3(/4) | {index,middle,ring,pinky}_0{1,2,3}_l (+ _metacarpal_l) |
| LeftUpperLeg (parent Hips) | LeftUpperLeg | LeftUpLeg | thigh_l |
| LeftLowerLeg | LeftLowerLeg | LeftLeg | calf_l |
| LeftFoot | LeftFoot | LeftFoot | foot_l |
| LeftToes | LeftToes | LeftToeBase (+LeftToe_End) | ball_l |
| – | – | – | twist bones `*_twist_01_l`; IK bones `ik_foot_root`, `ik_foot_l/r`, `ik_hand_root`, `ik_hand_gun`, `ik_hand_l/r` |

Confidence by column:
- **Godot:** [DOC]. Hierarchy: Root > Hips > Spine > Chest > UpperChest > Neck > Head; shoulders hang off UpperChest, legs off Hips.
- **Mixamo, UE5:** [COMM/UNVERIFIED]. Cascadeur's docs confirm Hips/Spine/RightToeBase. Read the names from the real file before relying on them.

Naming guidance [DOC]:
- Unity: name bones by body part, with a consistent side convention (`arm_L` / `arm_R`). Natural chains: Hips-Spine-Chest-Shoulders-Arm-Forearm-Hand, and Hips-UpLeg-Leg-Foot-Toe-Toe_end.
- Godot: auto-mapping is pattern-based and works best with common English names. Missing, duplicate or wrong-parent mappings show magenta or red, but don't block import.
- Unreal: `FName` is case-insensitive. [COMM]

### 4.4 Rest pose: T-pose vs A-pose

| Requirement | Pose | Source |
|---|---|---|
| Godot SkeletonProfileHumanoid reference | **T-pose**, facing +Z, right-handed Y-up, no transform on the humanoid node. Bone +Y points parent→child; "+X rotation bends the joint like a contracting muscle". T-pose models don't need Fix Silhouette; **A-pose models should enable it**. It can't fix very different silhouettes or bone roll. `filter` can exclude the feet; `base_height_adjustment` handles bent knees. | Godot 4.7 retargeting [DOC] |
| Unity Humanoid | "If your character is a biped, model in a **T-pose**". It leaves room for underarm detail and makes it easier to fit the rig. | Unity [DOC] |
| Mixamo auto-rigger | Adobe: a "default or neutral pose". Rigging may fail on very asymmetric or pre-posed characters. Needs distinct head, body, arms and legs; nothing else in the scene; centered at the origin; a clean mesh. Wings, tails, large hair and clothing may fail. An A-pose works per an Adobe community answer. | Adobe FAQ via search snippet [DOC-snippet] |
| Mixamo polygon / file limit | not officially published. Third-party claims: < 100k tris, < 50 MB. | [3P/UNVERIFIED] |
| UE5 Manny / Quinn reference pose | A-pose. Retargeting between A and T needs a matching **Retarget Pose** in the IK Retargeter. | Epic IK Rig retargeting [DOC] |
| Studio practice | Skin/bind in **A-pose**. The arm travels about 45° to neutral instead of about 90°, which means less armpit collapse. The control rig then offsets to a T-pose for mocap and retargeting. | Polycount, tech-artists.org, CG Cookie, Neural4D [COMM/3P] |
| Counterpoint | A 45° arm can need extra correction; a relaxed 90° pose is easier to rig. With pose-space deformers, a T-pose works as the neutral midpoint. | Polycount forum [COMM] |

Export rules:
- Export **in the rest pose**, with no deformation applied. [DOC Godot]
- Blender glTF uses the rest pose only when `Use Rest Position Armature` is on; otherwise the current-frame pose becomes the rest pose. [DOC Blender]

### 4.5 Root bone and root motion

| Engine | Requirement | Source |
|---|---|---|
| Unreal | Needs a root bone with motion data on it. The root is a reference point, "not built to represent an element of the Skeletal Mesh". Root motion is **off by default** and enabled per Animation Sequence/Montage. `Root Motion Root Lock` = Ref Pose / Anim First Frame / Zero. `Force Root Lock` exists. While Walking or Falling, Z root motion is ignored. Root Motion Mode: No Extraction / Ignore / From Everything / From Montages Only. The pivot = the root bone. IK Retargeter: set **Retarget Root = pelvis**; keep the root out of the Spine chain. | Epic Root Motion; IK Rig retargeting; FBX pipeline [DOC] |
| Godot | Profile Root → Hips. `Remove Tracks > Unimportant Positions` keeps position tracks only on **Root and Hips**. `Normalize Position Tracks` scales by Hips height (`motion_scale`) to cut foot slip. `Overwrite Axis` is "the most important option" for sharing animations. Root motion is set via `root_motion_track` on AnimationMixer/AnimationTree. Animations: **FPS** sampling, "little benefit above 30". | Godot retargeting + import configuration [DOC] |
| Unity | Humanoid: root motion comes from the body center of mass. Generic: choose a **Root node** bone in the Rig tab, which "effectively defines the model's center of mass". | Unity Rig tab, humanoid page [DOC] |
| Mixamo | Hips is the top bone (no root), which breaks UE and Godot root motion. Options: download "In Place", or add a `root` bone at (0,0,0) and move the horizontal hips translation onto it (Blender add-ons: "Mixamo Root"; godot_mixamo_converter). Some clips have no In Place variant. | GitHub add-ons, Unamedia docs [COMM] |
| Roblox | The root joint is at (0,0,0) with **no skin influences**. | Roblox specs [DOC] |
| Tripo | `retarget … animate_in_place` (default false). In-game locomotion that is driven by code means `--animate-in-place`. ≤5 animations per retarget, billed per animation. | tripo-cli docs |

---

## 5. Detection checklist (headless Blender, zero credits)

Run with `blender -b --python audit.py -- model.glb`. Import with `bpy.ops.import_scene.gltf(filepath=...)`. Blender converts glTF Y-up to Z-up on import, so judge facing by Blender conventions (front = −Y, character left = +X).

| Check | How (bpy / bmesh) | Pass threshold | Fix |
|---|---|---|---|
| Triangle count | `sum(len(f.verts)-2 for f in bm.faces)` | ≤ the class budget (§2.5) | Tripo `mesh decimate --face-limit N` (v3.0; `--quad` for editable topology). Blender Decimate: Collapse; Un-Subdivide for quad grids; Planar for hard-surface. |
| Render vertex / tri ratio | count unique (pos, normal, UV) loop tuples ÷ tris | ≤ ~1.0 (good: 0.5–0.7) | Fewer UV seams; consistent smoothing; fewer materials |
| N-gons | `[f for f in bm.faces if len(f.verts)>4]` | 0 in export | Triangulate modifier (Beauty); hand-cut in deform zones |
| Quad ratio (editing quality) | quads ÷ faces | ≥ 0.9 for characters that will be edited; irrelevant for static props | Tripo `quad=true` / `decimate --quad`; Blender QuadriFlow |
| Poles in deform zones | non-boundary verts with `len(v.link_edges) != 4`, within r ≈ 0.25 × bone length of elbow/knee/shoulder/hip bone heads | 0 poles of valence ≥ 6; ≤ 1 pole of valence 3 or 5 per joint, and none in the crook | Manual retopo; locate them with Select All by Trait > Poles by Count |
| Joint loops | slice with planes normal to the bone at −0.1, 0 and +0.1 × bone length from the joint; count the distinct edge rings crossed | ≥ 3 (hero), ≥ 2 (mobile) | Loop cut, or regenerate at a higher face_limit / quad |
| Non-manifold | `[e for e in bm.edges if not e.is_manifold]`; Select All by Trait > Non Manifold | 0 for closed bodies (boundaries are OK on cards and hair) | Merge by Distance; Fill Holes; delete internal faces |
| T-vertices / gaps | boundary verts lying on another edge (distance < 1e-4) | 0 | Merge, or knife-connect |
| Loose geometry | verts with no edges, edges with no faces | 0 | Mesh > Clean Up > Delete Loose |
| Interior / hidden faces | Select All by Trait > Interior Faces; ray-cast from each face center along its normal (a back-face hit inside the bbox = hidden) | 0 (except under loose clothing) | Delete; or Tripo segment, then drop the parts |
| Degenerate / sliver faces | `f.calc_area() < 1e-8`; aspect ratio (longest edge² ÷ (2·area)) > 20 | 0 degenerate; < 1% slivers | Clean Up > Degenerate Dissolve; Limited Dissolve, then Beauty triangulate |
| Flipped normals | face normal · (center − centroid) < 0 on convex parts; diff against `normals_make_consistent` | 0 | Recalculate Outside |
| Scale / units | world bbox height | humanoid 1.5–2.0 m; door ~2.1 m; not 100× or 0.01× | Scale, then Apply Scale. Godot `Apply Root Scale`; Unity Scale Factor; Tripo `auto_size=true` at generation |
| Pivot / floor | world bbox min-Z ≈ 0; origin between the feet | abs(minZ) < 1 cm | Move to the floor; Apply Location |
| Applied transforms | mesh and armature `scale == (1,1,1)`, `rotation == 0` (Roblox requires this on bones too) | exact | Ctrl+A All Transforms; apply to armature and mesh together |
| Facing | rigged: a `Left*` bone head has **x > 0** in Blender, so the model faces −Y (correct). Unrigged: face/feet asymmetry, or compare against the source image. | left side at +X | Rotate 180° (or ±90°) about Z and apply. With Tripo, set `export_orientation` only on the final convert. |
| Influences per vertex | `len([g for g in v.groups if g.weight > 1e-4 and is_deform(g)])` | ≤ 4 (≤ 8 only if the target supports it) | Weights > **Limit Total** (4), then **Normalize All** |
| Weight sum | `abs(sum(w) - 1)` | < 0.01 | Normalize All |
| Negative / unweighted verts | any weight < 0; verts with no deform group | 0 | Assign to the nearest bone; Data Transfer weights; re-skin |
| Bone count | `len(arm.data.bones)`; deform bones (`bone.use_deform`) | mobile ≤ ~40 deform; ≤ 75 per UE mobile section; ≤ 256 per section by default | Delete non-deform/IK bones; export deform-only |
| Single root | bones with `parent is None` | exactly 1, at the origin | Add `root` at (0,0,0) and parent the hips to it |
| Rest pose type | upper-arm angle below horizontal: `degrees(asin(-dz/len))` of (tail_local − head_local) | T-pose < 10°; A-pose 30–55° | Godot Fix Silhouette; UE Retarget Pose; or re-pose and Apply as Rest (re-bind needed) |
| Name mapping | match against the §4.3 table, case-insensitive, after stripping `mixamorig:` / `_l` / `.L` / `Left` | all 15 Unity-required bones mapped | Rename (Blender script, Godot `Rename Bones`, UE IK Rig chains) |
| Animation track sanity | position tracks only on root/hips; sample rate | Godot: ≤ 30 FPS is enough | Godot Remove Tracks options; re-bake at 30 |
| glTF validity | Khronos glTF-Validator (`gltf_validator` / npm `gltf-validator`) | 0 errors | Re-export |

---

## 6. Where sources disagree

1. **T-pose vs A-pose.** The engine references and auto-riggers prefer T: Godot's profile, Unity's docs, Mixamo's "neutral". Deformation-focused riggers and UE5 Manny use A. Some riggers prefer a relaxed 90° pose. **Skill default:** generate in a T-pose (Tripo `template=t_pose` / `t_pose=true` on the concept image), then pose-match at retarget time (Godot Fix Silhouette, UE Retarget Pose). Recommend A-pose only for hero characters with exposed shoulders that will be hand-skinned.
2. **Joint loops: 2 or 3.** CG Cookie and Blender Artists say 3. A Polycount reply says 2 full loops, one per bone. Sub-1k-tri meshes need only 1 extra loop on the bend side. **Skill rule:** 3 for hero, 2 for mobile, 1 extra for < 1k tris.
3. **4 vs 8 (vs 12 vs 32) influences.** glTF guarantees 4 per set. Unreal Interchange truncates to 4. Unreal FBX allows 4/8, or up to 12 in unlimited mode. Godot allows 8; Unity Custom allows up to 32; Roblox allows 4. The portable answer is 4.
4. **Triangle budgets.** Unity's legacy figures (300–4000) are far below current practice (HUNT 35–70k LOD0). Third-party "mobile 1.5k–5k" figures are plausible but not studio-sourced. The Polycount wiki refuses to give one number ("ask your Lead").
5. **Triangulate before export?** Godot, Unreal and Adobe say yes: triangulate and bake on the triangulated mesh. The Polycount wiki says keep quads as long as possible *while authoring*. These are compatible: keep a quad source and ship and bake the triangulated copy.
6. **N-gons in low poly.** They're acceptable on flat static surfaces (gamedev.net), but Roblox says to avoid them and Godot warns about their triangulation. Never use them in deform zones.
7. **Mixamo limits.** Adobe publishes no triangle or file-size limit. Old reports: 10k tris / 30 MB. Recent third-party claims: < 100k tris / 50 MB. Treat as unknown and test.
8. **Unreal character facing.** Unreal's world forward is +X, but skeletal meshes conventionally face +Y in asset space and are rotated −90° yaw in the Character Blueprint [COMM]. Don't "fix" this at import unless the project convention says to.
9. **Tripo default orientation.** Tripo's default `export_orientation=+x` doesn't obviously match the glTF/Godot front (+Z). The meaning of "forward axis" isn't documented precisely, so measure facing after download (§5) before any engine-specific rotation.

---

## 7. Tripo levers (zero-credit planning; verify with `--dry-run --json`)

| Problem detected | Tripo option (from the bundled docs) | Local alternative (Blender, free) |
|---|---|---|
| Too many tris | `mesh decimate --face-limit N` (v2.0 30 cr; v3.0 35 tri / 40 quad; `bake` true keeps the textures) | Decimate modifier + bake |
| Triangle soup, needs editable flow | `quad=true` (v3.x / P2; forces FBX) or `decimate --quad` (≤ 10k quads) | QuadriFlow remesh + shrinkwrap + bake |
| Low-poly look from the start | `--model tripo-p1` (face_limit 48/50–20000) or `smart_low_poly=true` (v3.x, 500–20000 tri) | – |
| Not in a T-pose | concept image `-p template=t_pose` or `-p t_pose=true` (text-to-image / image-to-image) before 3D | Pose + Apply as Rest |
| Wrong scale | `auto_size=true` (v3.0+) | Scale + Apply |
| Needs a rig | `anim check` first (GLB only, ≤ 150 MB; returns `riggable` + `rig_type`), then `anim rig --rig-type <from check> --spec mixamo` for Unity Humanoid / Mixamo naming (`--spec tripo` otherwise) | Rigify / Auto-Rig Pro |
| Locomotion for game code | `retarget --animate-in-place` | Zero the root/hips XY translation |
| Engine export | `convert --fbx-preset mixamo/blender/3dsmax`; set `export_orientation` **only** on the final convert | Blender export presets (§3) |
| Bad UVs (many islands) | `uv` (20 cr, ≤ 80k eq. tris) or `decimate --smart-uv` (v3.0) | Smart UV Project + pack |

---

## Sources

Official docs and specs read in full or in part this session (2026-10-31):
- Khronos glTF 2.0 Specification (§3.4 units/axes, §3.7.2 meshes, §3.7.3 skins incl. "Skinned Mesh Attributes"): https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- Godot 4.7 docs, Retargeting 3D skeletons: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/retargeting_3d_skeletons.html
- Godot docs, SkeletonProfileHumanoid: https://docs.godotengine.org/en/stable/classes/class_skeletonprofilehumanoid.html
- Godot docs, Model export considerations: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/model_export_considerations.html
- Godot docs, Import configuration: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/import_configuration.html
- Godot docs, Available 3D formats: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html
- Godot docs, Mesh class (ARRAY_FLAG_USE_8_BONE_WEIGHTS): https://docs.godotengine.org/en/stable/classes/class_mesh.html
- Unity manual, Humanoid models: https://docs.unity.com/en-us/engine/current/manual/assets-and-media/asset-types/models/creating-dccassets/using-humanoid-chars
- Unity 2022.3 manual, FBX importer Rig tab: https://docs.unity3d.com/2022.3/Documentation/Manual/FBXImporter-Rig.html
- Unity 2022.3 manual, Creating models for optimal performance: https://docs.unity3d.com/2022.3/Documentation/Manual/ModelingOptimizedCharacters.html
- Unity manual, Quality settings (Skin Weights): https://docs.unity.com/en-us/engine/current/manual/unity-editor/editor-settings-reference/comp-manager-group/class-quality-settings
- Epic, Skeletal mesh rendering paths: https://dev.epicgames.com/documentation/en-us/unreal-engine/skeletal-mesh-rendering-paths-in-unreal-engine
- Epic, FBX skeletal mesh pipeline: https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine
- Epic, FBX import options reference: https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-import-options-reference-in-unreal-engine
- Epic, Coordinate system and spaces: https://dev.epicgames.com/documentation/en-us/unreal-engine/coordinate-system-and-spaces-in-unreal-engine
- Epic, Root Motion: https://dev.epicgames.com/documentation/en-us/unreal-engine/root-motion-in-unreal-engine
- Epic, Retargeting bipeds with IK Rig: https://dev.epicgames.com/documentation/en-us/unreal-engine/retargeting-bipeds-with-ik-rig-in-unreal-engine
- Blender manual 4.2, glTF 2.0 add-on: https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html
- Blender manual 4.2, FBX add-on: https://docs.blender.org/manual/en/4.2/addons/import_export/scene_fbx.html
- Adobe Substance 3D Bakers, Triangulating before baking: https://experienceleague.adobe.com/en/docs/substance-3d/bakers/guides/triangulating-before-baking
- Roblox Creator Docs, Modeling specifications: https://create.roblox.com/docs/art/modeling/specifications
- CryEngine 5 docs, Character Budgets (HUNT: Showdown): https://cryengine.com/docs/static/engines/cryengine-5/categories/23756816/pages/23307976
- Meta Horizon docs, Unity performance / WebXR perf workflow (search summaries): https://developers.meta.com/horizon/documentation/unity/unity-perf/ , https://developers.meta.com/horizon/documentation/web/webxr-perf-workflow/

Polycount wiki (read over HTTP this session):
- Polygon Count: http://wiki.polycount.com/wiki/Polygon_Count
- Topology: http://wiki.polycount.com/wiki/Topology
- ShoulderTopology / BodyTopology / Limb_Topology: http://wiki.polycount.com/wiki/ShoulderTopology , http://wiki.polycount.com/wiki/BodyTopology , http://wiki.polycount.com/wiki/Limb_Topology
- GameRenderingTerminology: http://wiki.polycount.com/wiki/GameRenderingTerminology

Community and practitioner sources (search snippets or partial reads):
- Polycount forum, joint loops (2 loops / star point in elbow crook / DQS): https://polycount.com/discussion/comment/1354571 , https://polycount.com/discussion/comment/1353327 , https://polycount.com/discussion/comment/706901
- Polycount forum, A-pose vs T-pose: https://polycount.com/discussion/comment/2544951 , https://polycount.com/discussion/comment/2544208 , https://polycount.com/discussion/comment/1398388 , https://polycount.com/discussion/comment/2582806/
- Polycount forum, triangulation and tangent basis: https://polycount.com/discussion/comment/2772971 , https://polycount.com/discussion/comment/2674834
- Blender Artists, joint loops: https://blenderartists.org/t/first-model-need-input-on-topology/652386
- tech-artists.org, A-pose vs T-pose: https://www.tech-artists.org/t/which-is-better-for-rigging-a-pose-or-t-pose/18456
- CG Cookie, T-pose or A-pose: https://cgcookie.com/community/20686-t-pose-or-not-to-t-pose-or-a-pose
- 80.lv, Topology for game characters: https://80.lv/articles/topology-for-game-and-game-based-characters
- Adobe Mixamo FAQ (403 on direct fetch; search snippet): https://helpx.adobe.com/en/creative-cloud/faq/mixamo-faq.html
- Mixamo root-bone tools: https://github.com/EIREXE/godot_mixamo_converter , https://github.com/RichardPerry/Mixamo-Root , https://www.unamedia.com/ue5-mixamo/docs/mixamo-root-motion-animations
- Cascadeur, Mixamo rig mapping: https://cascadeur.com/help/using_mixamo_rig_in_cascadeur
- Reallusion manual, CC vs UE skeleton bone counts: https://manual.reallusion.com/Metahuman-Interoperability/Content/MetaHuman-Interoperability/17-Metahuman-Interoperability/Skeleton-between-CC-and-UE-Characters.htm
- UE forum / issue, Interchange glTF truncates to 4 influences: https://forums.unrealengine.com/t/interchange-gltf-importer-truncates-skeletal-mesh-bone-influences-to-4-per-vertex/2745391 , https://issues.unrealengine.com/issue/UE-392966
- Neural4D (3P), A-pose vs T-pose and polygon-count guide: https://blog.neural4d.com/comparisons/a-pose-vs-t-pose/ , https://blog.neural4d.com/user-guide/polygon-count-for-3d-game-assets-printing-and-webar/

Local: tripo-cli 0.6.1 bundled docs, `SKILL.md`, `commands/generate.md`, `commands/process.md`, `commands/make.md`, `common-errors.md`, `examples/animation.md`, `examples/game-asset.md` (face_limit ranges, quad/FBX, `template=t_pose`, `auto_size`, `export_orientation` warning, rig-check/rig/retarget parameters, decimate/uv limits).
