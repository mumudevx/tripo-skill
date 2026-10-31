# Game polygon budgets, LODs, draw calls: reference for tripo-skill

Researched 2026-10-30, extended 2026-10-31 (Godot LOD source code, Unity Mesh LOD generator, MSFS LOD rules, Khronos web publishing targets, Simplygon screen-size targets, Roblox, glTF spec). Every number has a source tag `[S#]` that points to the Sources list at the end.
Rows tagged **(synthesis)** are starting points built from several data points, not quotes from one source.
`DISAGREE` marks places where sources conflict.

---

## 0. TL;DR rules for the skill

1. **Count triangles, never "polys" or "faces".** GPUs only draw triangles [S1]. A Tripo `face_limit` with `quad=true` counts quads, and each quad becomes about 2 triangles. Tripo's own docs treat "a quad counts as two" triangles [T].
2. **The real cost is GPU vertices, not the vertex count your modelling tool shows.** Vertices are duplicated at every UV seam, hard edge (split normal) and material border [S1][S5][S12]. Check `gpu_verts / tris`. About 0.5–0.6 is a clean, connected mesh. Above 1.0 means heavy splitting. 3.0 means unwelded "triangle soup". (These thresholds are derived from mesh math, see §4.)
3. **Budget by asset class and platform** (§2). The whole frame must also fit the per-frame budget (§1). A single asset should rarely use more than about 5–10 % of the frame triangle budget unless it is the hero.
4. **Use materials per asset as the draw-call lever.** Each material/surface is at least one draw call, plus more for shadow passes. Mobile and VR: 1 material per asset (best rank on VRChat mobile = 1 material slot, 1 skinned mesh) [S16]. PC: 1–3.
5. **Character rig: 1 skinned mesh renderer per character.** Two skinned meshes "could roughly double the rendering time" in Unity [S8]. Use at most 4 bone influences per vertex for portability [S8][S19].
6. **LODs: each level has about 50 % of the previous level's triangles. Switch on screen size, not raw distance** [S13][S10][S11]. Use 3–4 LODs plus cull or impostor for props and characters that the camera approaches. Skip LODs for meshes that are already tiny (< ~500 tris), and for static cameras [S13].
7. **No micro-triangles.** Keep triangles above about 10 px in area on screen. Avoid long, thin triangles that are less than 10 px in one dimension [S13][S14]. LODs are the fix.
8. **Mobile hard limit: keep each mesh under 65,535 GPU vertices** (16-bit indices) [S13].
9. **Godot 4 generates LODs automatically on import** (meshoptimizer). Each step halves the triangle count, and the chain stops on its own (§6) [S2][S40]. Skinned meshes are the known weak spot [S2]. So use Tripo credits for LOD0 only, and build LOD1+ locally (Godot import, or Blender Decimate). Tripo `decimate` costs 30–35 credits per call [T].
10. **Nanite (UE5) does not apply to mobile or VR targets.** It does not support forward rendering, VR stereo, MSAA, translucent materials or morph targets [S9].
11. **Web/glTF single-object targets (Khronos):** 150k tris, 3 MB, < 20 draw calls and 2K textures for a mobile AR or web catalogue view. Desktop web view: 250k / 3 MB / < 100 draws [S36]. For a web *game*, divide the frame budget across all assets instead.
12. **The last LOD should be about 100 tris, 1 material, 1 draw call, with tiny or no textures** (MSFS rule) [S37]. Below about 5 % screen size, textures of 64² are enough [S37].

---

## 1. Per-frame (whole scene) budgets by platform

| Platform | Triangles / frame | Draw calls / frame | Source and notes |
|---|---|---|---|
| Low-end mobile (Android/iOS, WebGL on phones) | ~100k–300k **(synthesis)** | **100–200** [S20] | Arm "Armies" demo: ~210k tris/frame at ~30 fps, with hundreds of 360-tri soldiers [S13]. |
| Mid/high mobile (Unreal guidance) | **≤ 500k per view** [S21] | **≤ 700 per view** [S21]; ~700 on a Galaxy Tab S6, **< 500 on lower-end** [S22] | The 500k figure was "determined to be the maximum poly count that can hit 30fps on both iPad4 and iPad Air" [S21], so it dates from the iPad 4 era. Treat it as a ceiling, not a target. |
| Quest 1 | 350k–500k | 50–150 busy / 150–250 med / 200–400 light | [S17] |
| Quest 2 / Pro | **< 750k** [S18] (750k–1M [S17]) | **< 100** [S18] (80–200 busy … 400–600 light [S17]) | 72 Hz minimum, 13.8 ms frame [S18] |
| Quest 3 / 3S | **< 1.5M** [S18] (1.3M–1.8M [S17]) | **< 200** [S18] (200–300 busy … 700–1000 light [S17]) | 90 Hz recommended [S18] |
| PC VR (Rift-era guidance) | 1–2M tris/verts | 500–1,000 | Older Meta PC guidance, cited via search [S17b]. Treat as a rough upper reference. |
| Desktop/console (non-Nanite) | millions | "thousands every frame" at 60 fps on high-end desktop [S20] | No authoritative fixed number. Profile instead. |
| UE5 Nanite (desktop/console) | effectively unbounded source tris; cost scales with pixels | Nanite collapses draw calls | DX12 SM6 required; 16M instance cap [S9] |

`DISAGREE` on Quest draw calls. Meta's device-comparison page (updated 2026-05-11) says Quest 3 < 200 and Quest 2 < 100 [S18]. Meta's Unreal/Unity perf pages give workload-dependent ranges up to 700–1000 on Quest 3 [S17]. A Unity Learn VR tutorial quotes 500–1,000 for Quest 3 [S23]. **For a skill default, use the conservative device-comparison numbers.**

`DISAGREE` on mobile draw calls. PlayCanvas: 100–200 for low-end [S20]. Unreal: < 500 low-end, ~700 Tab S6 [S22]. The gap is renderer and device dependent. Use 100–200 for WebGL and low-end Android, and up to 500 for native mid-tier.

---

## 2. Per-asset triangle budgets (LOD0)

### 2a. Starting-point table (synthesis, then check against frame budget §1)

| Asset class | Mobile / Web / Quest | PC & console (non-Nanite) | Anchors |
|---|---|---|---|
| Hero / player character | **3k–10k** (cap ~15–20k for a lone showcase) | **30k–80k** (cinematic 100k+) | Mobile/Quest avatar ranks: Excellent 7.5k, Good 10k, Medium 15k, Poor 20k [S16]. Android: single showcase robot 11k [S13]. HUNT: Showdown hunters LOD0 35k–70k [S6]. PC VR avatar: Excellent 32k, Good+ 70k [S16]. |
| Boss / special | 5k–15k | 25k–45k | HUNT bosses LOD0 25k–45k [S6] |
| NPC / enemy (several on screen) | 1k–5k | 15k–35k | HUNT grunts LOD0 25k–35k [S6]. CryEngine 3 console side characters 1.2k–8k [S7] (2011-era). |
| Crowd unit (hundreds on screen) | 300–1k | 2k–8k | Armies soldier 360 tris [S13] |
| Weapon, held (3rd person / top-down) | 500–3k | 3k–10k | Dota 2 Pudge weapon LoD0 2,500 / LoD1 1,000 [S15] |
| Weapon, 1st person (fills screen) | 2k–8k | 10k–30k **(community practice; verify)** | Forum only: Polycount posters say 5k for older FPS view models, about double that later, and "20,000 to 50,000" for whole next-gen weapons [S47]. Bohemia forum: rifles average about 10k faces [S46]. On screen once, so it costs little in total [S47]. |
| Small prop (bottle, crate, potion) | 100–800 | 500–3k | Dota cosmetics 1.5k–3k LoD0 [S15]. Tripo example: potion at `face_limit=3000` [T], which is generous for mobile. |
| Large prop (cart, statue, tree trunk) | 500–3k | 3k–15k | Android cannon tower 3k [S13] |
| Environment modular piece (wall, floor, rock) | 200–2k | 1k–10k | Unreal LevelArchitecture LOD preset: 4 LODs at 50 % [S10] |
| Vehicle, player-driven | 5k–15k | 30k–100k **(weakly sourced; verify)** | Bohemia (Arma) forum: vehicles "up to around 20,000 faces" (older generation) [S46]. Roblox caps every single mesh at 20k tris, so split a vehicle into parts there [S41]. |
| Vehicle, traffic/background | 1k–4k | 5k–20k | — |
| Web/AR single-object viewer (glTF) | **30k–50k ideal, 100k max** (Scene Viewer); **150k** (Khronos mobile AR/catalogue); **250k** (Khronos desktop web) | — | Google Scene Viewer [S24]. Khronos 3DC publishing targets [S36]. Apple Quick Look rule of thumb is ~100k (WWDC 2018, via forum) [S25]. |
| Web multi-item scene (planner, banner) | **40k per item** (planner), **30k** (banner ad) | — | Khronos 3DC [S36] |
| Roblox (any platform) | **hard cap 20,000 tris per mesh**, max 4 bone influences per vertex | same | Roblox general specifications [S41] |

How to read it: these are LOD0 ranges. Stylized or flat-shaded art sits at the low end, and realistic art with a close camera at the high end. If a model needs more than the upper bound to hold its silhouette, the detail belongs in a normal map, not in geometry [S13][S26].

`DISAGREE` on hero characters. Vendor blogs give mobile heroes 1.5k–5k and others 3k–10k. PC heroes appear as 15k–50k, 20k–80k, or 50k–100k+ (search summaries). The only shipped-game, engine-vendor data are HUNT (35k–70k) [S6] and the 2011 CryEngine 3 figures (9.5k–11.5k for main characters on PC and console) [S7]. Budgets have grown about 5x in a decade. **Always ask the user for the target platform and camera distance before choosing.**

### 2b. Shipped and official data points (verbatim numbers)

**HUNT: Showdown (CRYENGINE docs, "Character Budgets")** [S6]

| Class | LOD0 tris | LOD3 tris | LOD3/LOD0 |
|---|---|---|---|
| Hunters (main) | 35,000–70,000 | 5,000–8,000 | ~11–14 % |
| Grunts (non-primary) | 25,000–35,000 | 4,000–5,000 | ~14–16 % |
| Bosses | 25,000–45,000 | 4,000–7,000 | ~16 % |

Textures for Hunters (one material per body part, for customization): face 1024², hands 4096×2048, legs 1024², eyeballs 2048² (512² in some cases), hair/brows/lashes 512². Grunts: 1024² per part. Armored monsters use **a single material with 7 material IDs**, and spiders one material with 4 IDs. The docs' advice is to "combine several smaller, individual textures into a single one" to save draw calls [S6].

**CRYENGINE 3 (2011-era, PC vs console)** [S7]: main character 9.5k–11.5k tris, the same on both. Side characters: PC 3.5k–16.5k, console 1.2k–8k. Body texture 2048² on PC, 1024² on console. Consoles load LOD1 instead of LOD0 at "about 50% of PC polycount".

**Dota 2 Workshop, Pudge** [S15] (top-down camera, strict importer caps):

| Slot | LoD0 | LoD1 | Texture |
|---|---|---|---|
| Head | 3,000 | 1,200 | 512² |
| Weapon | 2,500 | 1,000 | 256² |
| Back | 2,000 | 800 | 512² |
| Shoulders | 2,000 | 800 | 256² |
| Arms / Belt | 1,500 | 600 | 256² |

LoD1/LoD0 = 40 %. LoD0 is used for portrait/promo views and LoD1 for the in-game view. Both share one texture.

**VRChat avatar performance ranks** [S16] (a real-world VR budget with materials and bones):

| Stat | PC Excellent | PC Good | PC Poor | Mobile/Quest Excellent | Mobile Good | Mobile Medium | Mobile Poor |
|---|---|---|---|---|---|---|---|
| Triangles | 32,000 | 70,000 | 70,000 | 7,500 | 10,000 | 15,000 | 20,000 |
| Skinned meshes | 1 | 2 | 16 | 1 | 1 | 2 | 2 |
| Material slots | 4 | 8 | 32 | 1 | 1 | 2 | 4 |
| Bones | 75 | 150 | 400 | 75 | 90 | 150 | 150 |
| Texture memory | 40 MB | 75 MB | 150 MB | 10 MB | 18 MB | 25 MB | 40 MB |

**Google Scene Viewer (glTF on web/AR)** [S24]: ≤ 100k tris recommended (30k–50k ideal); ≤ 10 materials (2 may be alpha); textures ≤ 2048²; file ≤ 10 MB recommended, error above 15 MB. Hard limits: 1 UV set per mesh, ≤ 254 joints, ≤ 4 bone weights per vertex, 1 animation. Morph targets and vertex colors fail validation.

**Android/Arm geometry guide** [S13]: CircuitVR robot (single object) 11,000 tris. Armies soldier 360 tris. Cannon tower ~3,000. Scene ~210k tris at ~30 fps.

**Khronos 3D Commerce publishing targets** [S36] (per single glTF asset, web and AR):

| Target | Max file | Max tris | Draw calls (target / max) | Max JPG texture |
|---|---|---|---|---|
| Single-item mobile AR / 3D web catalogue | 3 MB | 150,000 | < 20 / 500 | 2K |
| Banner ad | 500 KB | 30,000 | < 5 / 100 | 512 |
| Web planning tool (one of many items) | 1 MB | 40,000 | < 5 / 50 | 1K |
| Single-item desktop 3D web view | 3 MB | 250,000 | < 100 / 800 | 2K |

`DISAGREE` (inside the same source): the banner-ad text says 1 MB / 60k tris, but the table says 500 KB / 30k [S36]. The Khronos glTF Asset Auditor ships stricter defaults: 100k tris, 5 MB, ≤ 5 materials (search excerpt, not verified in the tool) [S36b].

**Microsoft Flight Simulator, LOD rules** [S37] (an official vendor spec with hard numbers):
- At least 4 LODs. Each LOD has ≤ 50 % of the previous level's vertices, ~50 % of its materials and ~50 % of its texels.
- Vertex caps by on-screen size: 250,000 at minSize 100 %, ~480,000 at 150 %, 300 at 1 %, 150 for the last LOD (forced to 0.5 %).
- Draw-call caps: 500 at 100 % screen size, 2 at ≤ 1 %. Textures ≤ 64² below about 5 %.
- Example (airport): LOD0 150 % / 8,632 faces / ~15 materials → LOD1 60 % / 3,712 / ~12 → LOD2 15 % / 2,063 / 2 → LOD3 7 % / 699 / 1 → LOD4 3 % / 319 / 1 → LOD5 1 % / 113 / 1.
- Animations freeze below 1 % screen size.

**Dying Light (Techland, via Simplygon)** [S45]: the heaviest character was 144,988 tris in source and 34,849 after reduction, about 76 % fewer. That is a realistic PC/console hero LOD0.

---

## 3. Materials, draw calls, rig and textures per asset

| Item | Mobile / Quest / Web | PC / console | Source |
|---|---|---|---|
| Materials (surfaces) per prop | **1** (atlas everything) | 1–2 | VRChat mobile Excellent = 1 slot [S16]. Godot: 20,000 objects with 100 shared materials render "much faster" than 20,000 unique materials [S3]. |
| Materials per character | 1 (eyes/hair alpha may justify a 2nd) | 2–4; more only for runtime customization (HUNT) | Unity: use more than one only for a different shader, e.g. eyes [S8]. HUNT [S6]. |
| Transparent parts | Put them on their **own surface/material**, and keep them as small as possible | same | Godot [S3][S14] |
| Skinned meshes per character | **1** | 1 (2 max) | Unity: 2 skinned meshes ≈ 2x render time [S8]. VRChat [S16]. |
| Bones | ≤ 75 (Excellent), ≤ 90–150 | ≤ 75–150 | VRChat [S16]. Unity: 15 extra bones on a 30-bone Generic rig = +50 % solve operations [S8]. glTF/Scene Viewer ≤ 254 joints [S24]. |
| Bone influences / vertex | 4 | 4 (Godot can do 8) | Unity linear blend skinning, max 4 [S8]. Godot "4 Influences (Compatible)" vs "All Influences" (up to 8, not every renderer) [S19]. |
| Texture per prop | 256–1024 | 1024–2048 | Dota 256–512 [S15]. CryEngine console 1024 vs PC 2048 [S7]. |
| Texture per hero | 1024–2048 | 2048–4096 (split across parts) | HUNT [S6]. Scene Viewer max 2048 [S24]. |
| Texture compression | ASTC (iOS/Android), ETC2 for pre-2016 Android | BCn | Unity [S27]. Godot compresses 3D textures in VRAM by default [S14]. |
| Vertex attributes | Drop unused NORMAL/TANGENT/TEXCOORD channels. Only POSITION needs full precision. | — | Meta [S17] |
| Animation sample rate | 30 fps bake is enough | 30 | Godot `animation/fps` default 30, "not much benefit" above 30 [S19] |

Draw-call math for one asset: `draws ≈ surfaces(materials) × (1 main pass + shadow cascades/lights it is in) (+1 depth prepass on Forward+)`. One shadow-casting omni light renders the scene **6 times** [S20]. A 4-material character in a 4-cascade directional shadow is therefore about 20 draws. Merging materials is the strongest per-asset lever.

---

## 4. Vertex count vs triangle count

- A closed, connected mesh has `V ≈ T/2` (Euler). Example from the Polycount wiki: "1 triangle uses 3 vertices, 2 triangles use 4" [S1]. Verified in Blender: a smooth UV sphere has 960 tris and 559 GPU verts, a ratio of **0.58**. A flat-shaded cube has 12 tris and 24 GPU verts, a ratio of **2.0**.
- **Splits happen** at UV seams, smoothing/hard-edge changes, and material changes. "The vertices must be duplicated at these breaks" [S1]. Unity: "UV mapping seams and hard edges … are doubled-up vertices" [S12]. A vertex needs a separate GPU copy wherever it has multiple normals, UVs or vertex colors [S8]. glTF splits on texcoord, normal or material [S26].
- **Modelling tools under-report.** Blender, Maya and Max show geometric vertices, so the in-engine count is higher [S1][S8]. A glTF file already stores split vertices, so after glTF import Blender's count ≈ the GPU count. Measure in the runtime when possible.
- **Rule: align hard edges with UV seams.** One split then covers both [S1]-forum consensus.
- **Mobile per-mesh cap: 65,535 vertices** (16-bit indices guaranteed). Beyond it you get "missing or incorrectly rendered geometry" [S13]. glTF adds that an index accessor "MUST NOT contain the maximum possible value" (65535 for unsigned short), because it triggers primitive restart [S42]. So a u16 primitive can address indices 0–65,534. Above that, exporters switch to u32, which is legal but costs bandwidth and isn't guaranteed everywhere.
- glTF: units are meters, +Y up [S42]. Clients SHOULD support at least one joints/weights set, which is 4 influences (VEC4) [S42]. So 4 is the portable cap.
- **Interpretation thresholds for `gpu_verts/tris`** (derived, use as triage):
  - **≤ 0.7**: healthy.
  - **0.7–1.0**: many seams or hard edges. Acceptable for hard-surface props.
  - **> 1.0**: over-split. Typical of auto-unwrapped AI meshes with hundreds of UV islands, or per-face flat shading.
  - **≈ 3.0**: unwelded triangle soup. Weld before anything else. meshoptimizer: "duplicate vertices should be welded first, because seams can cause the simplifier to get stuck" [S28].

---

## 5. LOD strategy

### 5a. How many LODs and what reduction

| Rule | Value | Source |
|---|---|---|
| Reduction per level | **50 % of previous** (consistent ratio) | Android/Arm [S13]. Unreal LOD-group presets `LODPercentTriangles=50` [S10]. |
| Typical chain | LOD0 100 % → LOD1 50 % → LOD2 25 % → LOD3 12.5 % → cull/impostor | (synthesis) [S13][S10] |
| Alternative chain (Unreal manual example) | 100 / 75 / 25 / 12 % | [S10] |
| Alternative chain (Unity Asset Transformer) | 100 / 50 / 25 / 10 %; "start with 3-4 LOD levels". Farthest LOD = all parts merged into **one mesh, one baked material, one draw call**. LOD1–2 keep separate meshes and materials | [S39] |
| Flight-sim chain (MSFS) | ≥ 4 LODs, each ≤ 50 % verts, ~50 % materials, ~50 % texels; last LOD ≤ 150 verts / ~100 tris, 1 draw call, no textures | [S37] |
| Auto-generators (engine) | Godot and Unity Mesh LOD both halve per step automatically. Unity needs ≥ 256 source tris and stops at about 64 [S38]. Godot stops when a step saves < 25 % or the error exceeds its cap [S40] | [S38][S40] |
| Perception anchor | At 20 m, a 200-tri object and a 2,000-tri version look nearly identical | Unity Learn [S43] |
| Shipped character chain | LOD3 ≈ 11–16 % of LOD0 (4 levels) | HUNT [S6] |
| Top-down game cosmetic | LoD1 = 40 % of LoD0 | Dota 2 [S15] |
| Console vs PC same asset | console uses LOD1 ≈ 50 % | CryEngine 3 [S7] |
| Number of LODs, props | 4 (SmallProp / LargeProp / Deco / LevelArchitecture presets); HighDetail 6 | Unreal [S10] |
| Number of LODs, mobile | 2–3 + cull is common | (vendor guide via search; synthesis) |
| Vista / foliage presets | 1 LOD (impostor or other handling) | Unreal [S10] |
| When NOT to LOD | Static camera or static object; mesh already low-poly; every extra level costs CPU selection time, memory, file size and VRAM | [S13] |
| Distant LODs also simplify **materials** | Drop normal map (esp. mobile), rim, clearcoat, SSS, refraction | Godot [S5] |

`DISAGREE` on ratio-based vs error-based LOD. Arm and Unreal presets use fixed 50 % steps [S13][S10]. Simplygon "strongly recommend[s] not using triangle ratio or triangle count as reduction targets". It prefers max-deviation (distance-based switching) or screen-size targets, and its Unreal plugin sets switches for at most **1 pixel** of error [S29]. Godot's default threshold is also 1 px, error-driven [S2]. **Practical reconciliation:** generate a 50 % chain, then let the engine choose switch points by screen-space error. Don't hand-tune distances.

### 5b. Switching

- Switch on **screen size**, not distance. Unreal: "LOD changes depend on screen size". With Auto Compute LOD Distances, thresholds split evenly: with 2 LODs, LOD0 at ≥ 50 % screen size; with 3 LODs, 66.7 % / 33.3 % [S11].
- Godot: `Rendering > Mesh LOD > LOD Change > Threshold Pixels` defaults to **1.0** ("perceptually lossless"). Higher values switch sooner. Per-object `lod_bias` (>1 keeps detail longer). FOV and resolution are accounted for automatically [S2].
- Unity LOD Group: explicit screen-relative transition heights. Global `QualitySettings.lodBias`. Optional cross-fade, which renders 2 LODs during the blend [S30]. Unity 6 Mesh LOD selects automatically by screen size [S31].
- Cross-fades cost extra. Alpha fades force transparency (Godot "Self"/"Dependencies" fade modes). Dither fade is cheaper and best with 2 LODs [S4].
- Simplygon's screen-size anchor: full-screen ≈ **1000 px** of on-screen height for characters and important props. Try **500 px** if that is too dense, and 750 px as the midpoint [S29]. Example: a 36k-tri monster becomes 30k at 1000 px and 19k at 500 px [S29]. Convert with `max_deviation = bounding_sphere_diameter / target_screen_px`. Allow a **2–4 px** LOD pop error (quality multiplier 0.5–0.25) [S29]. Clean LOD0 to a common max deviation (e.g. 1 mm), with a triangle cap only as an outlier guard [S29]. Buildings and other very large objects need separate reasoning [S29].
- MSFS switch chain example: 150 % → 60 % → 15 % → 7 % → 3 % → 1 % of screen size [S37]. The second-to-last LOD should switch at ≥ 1 % [S37].

---

## 6. Engine specifics

### Godot 4

- **Automatic mesh LOD on import** for glTF, .blend, FBX and Collada, via meshoptimizer. OBJ only if imported "as Scene" [S2]. Import option `meshes/generate_lods` default **true**, with a per-mesh override in Advanced Import Settings [S19][S2].
- LOD stays in one mesh (index buffers). It works on MeshInstance3D, MultiMeshInstance3D and GPU/CPU particles [S2].
- **Known limitation:** generation "may cause rendering issues, especially with skinned meshes". If a mesh looks broken, disable LOD generation for it [S2].
- **What the importer actually does** (verified in Godot `master` source, `importer_mesh.cpp` + `resource_importer_scene.cpp`) [S40]:
  - Each step targets **half the triangles** of the previous LOD: `target_index_count = ((current_index_count/3)/2)*3`. The minimum is 12 indices, and the loop runs while there are more than 24.
  - The chain stops when a step saves less than 25 % (`new >= current*0.75`), or when the accumulated error passes `max_mesh_error = 1.0`. The error grows by at least ×1.5 per step. So the **LOD count depends on the mesh**, with no fixed number.
  - It always locks borders (`SIMPLIFY_LOCK_BORDER`), so open edges and UV-island borders limit how far it can reduce. Fragmented AI meshes with many islands reduce poorly. It also prunes small disconnected components, and uses `SIMPLIFY_REGULARIZE` on deformable meshes (bones or blend shapes).
  - For skinned meshes, it simplifies in the **posed skin transform** space (`_get_skinned_pose_transforms`). Normals only merge when within `normal_merge_angle`.
  - Defaults: `lods/normal_merge_angle` = **20°** (range 0–180). Lower it if LODs show shading artifacts, at the cost of less efficient LODs [S19b]. `normal_split_angle` is **unused** (the bind comment says so). The 4.3-era docs suggested 25°/60° [S32]. Only triangle primitives are processed.
- Other import defaults [S19][S40]: `meshes/generate_lods=true`, `create_shadow_meshes=true` (welds verts for the shadow pass), `ensure_tangents=true` (Mikktspace), `force_disable_compression=false` (enable it if normals or UVs look blocky, or for very large meshes), `light_baking` "Static Lightmaps" generates UV2 with `lightmap_texel_size=0.2`.
- **Visibility ranges (HLOD)** are for hand-made LODs, impostors, merged clusters and culling. Settings are begin/end distance plus margins. Fade mode Disabled (cheapest, hysteresis), Self, or Dependencies (both force transparency) [S4]. Use "visibility parent" to swap many objects for one merged mesh [S4].
- **Occlusion culling:** best for indoor and many-room scenes. The **Mobile renderer gains most** because it has no depth prepass. Only opaque MeshInstance3D are baked as occluders. Use simple occluders, because complex ones cost CPU [S33].
- Automatic instancing is Forward+ only. Use MultiMesh for thousands of copies [S5].
- Mobile vertex advice: "don't worry much about total vertex count", but **avoid concentrating vertices in a small screen area** (tile-based GPUs stall). Avoid sub-pixel triangles even on desktop [S14].
- Transparency: keep areas small. "More complex opaque geometry" can beat alpha [S14]. Prefer the Compatibility renderer when targeting desktop and mobile together [S14].
- Skinning and morphs cost a lot on some platforms. Lower the polycount of animated models, and throttle animation for distant/off-screen ones (VisibleOnScreenEnabler3D) [S5].
- Check in the editor viewport: Perspective menu → **View Information** (draw calls, primitives) and **View Frame Time**. Debug draw: **Wireframe** and **Disable Mesh LOD** [S2].

### Unity (6.x)

- **Mesh LOD generator rules** [S38]: needs **≥ 256 source triangles** to start. Each LOD has about half the indices of the previous one. It stops at the Limit LODs setting, at about 64 triangles, or when no more vertices can be removed. It **adds no vertices**: all LODs share one vertex buffer, and the index buffer grows by at most 100 %. It works best on organic shapes and dense flat areas. It "may give undesired results" on high-curvature meshes or meshes with **many disconnected pieces** (typical of AI output, so weld first). Meshes named `_LODx` import as an LOD Group instead [S38].
- **Mesh LOD (Unity 6)**: generated on import and stored in the original mesh's index buffer. It has no per-LOD material. It **ignores skin weights and blend shapes** while simplifying. **LOD0 is always deformed**, so it saves no skinning cost. Don't combine it with LOD Group. Static batching and particles always use LOD0. Cross-fade needs the GPU Resident Drawer [S31].
- **LOD Group**: author LODs yourself. It can reduce materials and renderers per LOD, which Mesh LOD cannot [S30].
- Dynamic batching only for meshes with **≤ 300 vertices / ≤ 900 vertex attributes**. Use the SRP Batcher for URP. Use `sharedMaterial`, because `.material` clones the material and breaks batching [S27].
- Mesh import: disable Read/Write (otherwise a CPU and GPU copy stays in memory). Disable rig/blendshapes on static meshes [S27].
- Characters: 1 SkinnedMeshRenderer, ≤ 4 influences, few bones, delete leftover IK nodes [S8].

### Unreal Engine 5

- **Non-Nanite LOD-group presets** (BaseEngine.ini) [S10]:

| Preset | NumLODs | % tris/LOD | PixelError |
|---|---|---|---|
| LevelArchitecture | 4 | 50 | 12 |
| SmallProp / LargeProp / Deco | 4 | 50 | 10 |
| HighDetail | 6 | 50 | 6 |
| Vista / Foliage | 1 | – | – |

- **Nanite supports**: static meshes, opaque and masked materials, foliage, landscape, tessellation/displacement, and skeletal meshes (newer versions; one draw call per mesh, animation LODs instead of geometry LODs) [S9].
- `DISAGREE` on how mature skeletal Nanite is. The official page lists skeletal meshes as supported, without morph targets [S9]. An Epic staff reply in the forums says morph targets, grooms and cloth were still largely missing after 5.5. 5.7 ships "Nanite Foliage and Skinning" as **Experimental** [S44]. For a Tripo-generated character, author classic skeletal LODs. Don't count on Nanite.
- **Nanite does not support**: translucent materials, morph targets, deformation beyond one 4x3 matrix, forward rendering, **VR stereo, MSAA**, lighting channels, distance culling. WPO is limited [S9]. → **Not for Quest or mobile targets.**
- Nanite costs: ~**14.4 bytes per input triangle** on disk (1M tris ≈ 13.8 MB). A 1.55M-tri mesh is 19.6 MB vs 149 MB as a 4-LOD static mesh (**7.6x smaller**) [S34]. **Closely stacked small objects cause overdraw.** Enable "Preserve Area" on foliage only [S34].
- The **fallback mesh** is used for ray tracing (by default), complex collision, lightmap baking and non-Nanite platforms. Tune it with Fallback Relative Error / Fallback Triangle Percent. Keep/Trim settings only reduce disk size [S9][S34].
- Mobile: ≤ 500k tris and ≤ 700 draws per view [S21]. Count with `stat RHI` [S22].

### Web (three.js / Babylon / PlayCanvas / model-viewer)

- glTF has triangles only. Quads are not supported [S26]. (Tripo: `quad=true` cannot export GLB/GLTF [T].)
- Scene Viewer limits (§2b) are the most concrete published web budget [S24]. Low-end mobile web: 100–200 draws [S20].
- Textures dominate memory on phones. Prefer ≤ 2048², KTX2/Basis, and meshopt/Draco geometry compression (Khronos lists PNG/JPG/WebP/KTX2) [S26].

---

## 7. HOW TO CHECK (detection recipe for the skill)

### 7a. Blender headless stats (tested on Blender 5.2.3)

```bash
blender -b --factory-startup --python mesh_stats.py -- model.glb   # prints one line: MESH_STATS_JSON {...}
```

```python
# mesh_stats.py: tris, GPU-vertex estimate (unique pos+normal+uv+material), materials, seams, bones
import bpy, sys, json
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if argv:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    p = argv[0]
    if p.lower().endswith((".glb", ".gltf")): bpy.ops.import_scene.gltf(filepath=p)
    elif p.lower().endswith(".fbx"): bpy.ops.import_scene.fbx(filepath=p)
    elif p.lower().endswith(".obj"): bpy.ops.wm.obj_import(filepath=p)
dg = bpy.context.evaluated_depsgraph_get()
rep = {"objects": [], "totals": {"tris": 0, "gpu_verts": 0, "mesh_verts": 0, "materials": set(), "draw_surfaces": 0}}
for ob in bpy.context.scene.objects:
    if ob.type != "MESH": continue
    me = ob.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    tris = len(me.loop_triangles)
    uv = me.uv_layers.active.data if me.uv_layers.active else None
    try: normals = [tuple(round(c, 4) for c in n.vector) for n in me.corner_normals]   # Blender 4.1+
    except AttributeError:
        me.calc_normals_split(); normals = [tuple(round(c, 4) for c in l.normal) for l in me.loops]
    loop_mat = [0] * len(me.loops)
    for poly in me.polygons:
        for li in poly.loop_indices: loop_mat[li] = poly.material_index
    keys = set()
    for l in me.loops:
        u = (round(uv[l.index].uv[0], 5), round(uv[l.index].uv[1], 5)) if uv else None
        keys.add((l.vertex_index, normals[l.index], u, loop_mat[l.index]))
    mats = {s.material.name for s in ob.material_slots if s.material}
    used = {p.material_index for p in me.polygons}
    o = {"name": ob.name, "tris": tris, "mesh_verts": len(me.vertices), "gpu_verts_est": len(keys),
         "gpu_verts_per_tri": round(len(keys) / max(tris, 1), 2), "material_slots_used": len(used),
         "uv_layers": len(me.uv_layers),
         "marked_seams": sum(e.use_seam for e in me.edges), "marked_sharp": sum(e.use_edge_sharp for e in me.edges),
         "skinned": any(m.type == "ARMATURE" for m in ob.modifiers) or (ob.parent is not None and ob.parent.type == "ARMATURE"),
         "vertex_groups": len(ob.vertex_groups),
         "shape_keys": len(me.shape_keys.key_blocks) if me.shape_keys else 0,
         "over_16bit_index": len(keys) > 65535}
    rep["objects"].append(o)
    t = rep["totals"]; t["tris"] += tris; t["gpu_verts"] += len(keys); t["mesh_verts"] += len(me.vertices)
    t["materials"] |= mats; t["draw_surfaces"] += len(used)
    ob.evaluated_get(dg).to_mesh_clear()
rep["totals"]["materials"] = sorted(rep["totals"]["materials"])
rep["totals"]["bones"] = sum(len(a.data.bones) for a in bpy.context.scene.objects if a.type == "ARMATURE")
print("MESH_STATS_JSON " + json.dumps(rep))
```

Sanity results: default cube → 12 tris / 24 GPU verts (2.0). Smooth 32×16 UV sphere via GLB → 960 tris / 559 (0.58).

### 7b. Checks to run, with thresholds

| # | Check | Flag when | Severity |
|---|---|---|---|
| C1 | `tris` vs class budget (§2a, user's platform) | > upper bound | warn; > 2× = error |
| C2 | `tris` vs frame budget share | one non-hero asset > 10 % of frame tris (§1) | warn |
| C3 | `gpu_verts_per_tri` | > 1.0 warn, > 2.0 error (soup/unwelded) | §4 |
| C4 | `over_16bit_index` | any mesh > 65,535 GPU verts on mobile/web | error [S13] |
| C5 | materials / draw surfaces | mobile/VR > 1 (props) or > 2 (chars); PC > 3 | warn [S16][S8] |
| C6 | skinned meshes per character | > 1 | warn [S8][S16] |
| C7 | bones | > 75 (VR/mobile Excellent), > 150 warn, > 254 glTF hard fail | [S16][S24] |
| C8 | bone influences | > 4 per vertex | warn (Unity/Scene Viewer cap 4) [S8][S24] |
| C9 | textures | > 2048 on mobile/web; non-power-of-two (mobile compression needs POT [S27]) | warn |
| C10 | uv_layers | 0 (can't texture) or > 1 on web viewers | error / warn [S24] |
| C11 | micro-triangles | median triangle area at expected on-screen size < 10 px (§0.7) | warn [S13] |
| C12 | LOD presence | moving/approachable asset > ~1k tris with no LOD and engine ≠ Godot/Unity-MeshLOD auto | info [S13] |
| C13 | translucent material | any alpha-blend on Nanite target, or large alpha areas on mobile | warn [S9][S14] |
| C14 | quads in export | `quad=true` + glTF requested | error [T][S26] |
| C15 | disconnected pieces / loose islands | many loose parts in what should be one object (AI fragments) | warn: auto-LOD (Godot border lock, Unity "many disconnected pieces") reduces poorly [S38][S40] |
| C16 | long, thin triangles | many triangles with aspect ratio > ~10:1 | warn: wasteful, and they flicker on shiny surfaces [S13] |
| C17 | platform hard caps | Roblox mesh > 20k tris; Scene Viewer > 100k; Khronos target exceeded | error [S41][S24][S36] |
| C18 | too small for auto-LOD | < 256 tris (Unity Mesh LOD skips it) | info: no LOD needed [S38] |

### 7c. In-engine verification

- **Godot**: viewport Perspective menu → View Information (draw calls, primitives), View Frame Time. Debug Draw → Wireframe and Disable Mesh LOD. Compare primitive counts at several distances [S2].
- **Unity**: Frame Debugger (every draw call) [S27]. Stats window (batches, tris, verts). LOD Group preview.
- **Unreal**: `stat RHI` (draw calls, tris) [S22]. Nanite visualization modes, including Overdraw and Evaluate WPO [S34].
- **Web**: three.js `renderer.info.render` (calls, triangles). Validate glTF with the Khronos glTF Validator.

---

## 8. HOW TO FIX (problem → options to propose → tool)

| Problem | Options to offer the user (cheapest first) | Notes |
|---|---|---|
| Over triangle budget (C1) | (a) **Blender Decimate, Collapse mode** with `ratio = budget/tris`. Enable *Symmetry* for characters and *Triangulate*. Protect the face/hands with a vertex group [S35]. (b) Godot: keep as LOD0 and rely on auto-LOD if only distant views are heavy. (c) Tripo `mesh decimate --face-limit N` (v2.0 smart retopo 30 cr, v3.0 35 cr; 500–20,000 tri; bakes textures onto the low-poly by default) [T]. (d) Regenerate with `--model tripo-p1 -p face_limit=N` (50–20,000) [T]. | Decimate Collapse doesn't fit sculpted/AI meshes well when ratio < ~0.1; use retopo (c) then. Ratio counts triangles; leave Triangulate on to hit the exact count [S35]. |
| Flat areas wasting tris | Blender Decimate **Planar** (angle limit ~5°, Delimit: Seam + Sharp + UVs + Material) [S35] | Keeps UVs and material borders intact |
| Unwelded soup (C3 ≈ 3) | Blender: Merge by Distance (0.0001 m) → recompute normals | Required before any simplification [S28] |
| Too many GPU verts from seams/hard edges (C3 > 1) | (a) Smooth-shade + Auto Smooth / weighted normals. Put remaining hard edges *on* UV seams [S1]. (b) Re-unwrap with fewer islands: Blender Smart UV Project with a higher angle limit, or Tripo `mesh uv` (20 cr, input ≤ 80k tris) / decimate v3.0 `--smart-uv` [T]. | Re-unwrapping requires a texture rebake (Tripo `uv` remaps textures; Blender needs a bake) |
| > 65,535 verts per mesh (C4) | Decimate (above), or split into 2 meshes by material/part | Mobile [S13] |
| Too many materials (C5) | Merge materials into one atlas: Blender bake to a single 1024–2048 texture set (or Tripo `convert` with `pack_uv=true` / `bake=true`) [T]. Keep alpha parts as a separate 2nd material. | Each removed material ≈ −1 draw per pass |
| Multiple skinned meshes (C6) | Join meshes before rigging (Blender Ctrl+J), one armature | [S8] |
| Too many bones (C7) | Remove leaf/IK/helper bones, or merge face bones; for VR target ≤ 75 | [S16][S8] |
| > 4 influences (C8) | Blender: Weight → Limit Total (4) → Normalize All | [S8] |
| Oversized textures (C9) | Downscale to class target (§3); POT; ASTC/ETC2 or KTX2 for web | [S27][S26] |
| No LODs (C12) | Godot: nothing to do (auto). Unity 6: enable Mesh LOD on import (static meshes). Unity LOD Group/Unreal: build 50 % chain with Blender Decimate (LOD1 0.5, LOD2 0.25, LOD3 0.125), export as `name_LOD0/1/2`. Skinned chars: build LODs on the skinned mesh *with the same armature*. Check deformation, since auto tools ignore weights [S31][S2]. | Avoid spending Tripo credits per LOD |
| Skinned auto-LOD artifacts (Godot/Unity) | Disable auto LOD for that mesh. Supply manual LODs via Visibility Ranges (Godot) / LOD Group (Unity) | [S2][S31] |
| Micro-triangles / dense detail (C11) | Bake detail to normal map from the high-poly (Tripo decimate bakes by default [T]), then decimate | [S13] |
| Translucency on Nanite or big alpha on mobile (C13) | Switch to alpha-test (masked) or opaque geometry | [S9][S14] |
| Quad + glTF (C14) | Export FBX/OBJ for quads, or triangulate for glTF | [T][S26] |

**Tripo budget mapping (from bundled CLI docs [T]):**
- `--for game-mobile` defaults to **P1 with `face_limit=15000`** and 2K textures. That is above the §2a mobile range for everything except a showcase hero, so **always override `-p face_limit=` per asset class**. Examples: small prop 500–800, NPC 2k–4k, hero 6k–10k.
- P1 `face_limit` 50–20,000. P2 (preview) 48–50,000 tri / 48–25,000 quad. Decimate v2/v3 500–20,000 tri / 500–10,000 quad. Decimate v1.0 goes up to 2M but needs `face_limit` and cannot bake [T].
- **Budget LOD0 only through Tripo. Make LOD1+ locally** (free), because with ~35 credits one decimate (30–35 cr) is the whole balance.
- **Suggested `face_limit` per class** (from §2a, synthesis; Tripo "face" = triangle unless `quad=true`, where 1 quad ≈ 2 tris [T]):

| Class | Mobile / Quest / Web | PC / console | Tripo route |
|---|---|---|---|
| Small prop | 300–800 | 1,500–3,000 | P1 `face_limit` |
| Large prop / env piece | 1,000–3,000 | 5,000–15,000 | P1 |
| Weapon (held) | 1,000–3,000 | 5,000–10,000 | P1 |
| NPC | 2,000–5,000 | 15,000–20,000 (P1 cap) or up to 35k | P1, or P2 (≤ 50k, Preview), or v3.1 + local decimate |
| Hero character | 6,000–10,000 (≤ 15k showcase) | 30,000–80,000 | Above 20k: P2 (≤ 50k), or v3.1 adaptive then **local** Blender decimate. Tripo smart decimate v2/v3 caps at 20k tri; v1.0 goes higher but cannot bake [T] |
| Vehicle | 5,000–15,000 | 30,000+ | Same as hero; consider generating parts separately |

- After any Tripo decimate, weld vertices and run the §7a stats. Smart-retopo output usually has clean borders, so Godot/Unity auto-LOD then reduces it well. Raw v3.1 output with many UV islands reduces poorly (border lock) [S40].
- Validate any plan with `tripo make ... --dry-run --json`: it reports out-of-range `face_limit` and quad+GLTF as blocking `errors` at zero cost [T].

---

## 9. Disagreement summary

| Topic | Positions | Recommendation |
|---|---|---|
| Hero char tris, PC | 15–50k / 20–80k / 50–100k+ (vendor blogs) vs HUNT 35–70k [S6] vs CE3 2011 ~10k [S7] | Use HUNT as the realistic PC anchor. Scale down for stylized art. |
| Hero char tris, mobile | 1.5–5k vs 3–10k (vendor), VRChat mobile 7.5–20k [S16], Android showcase 11k [S13] | 3k–10k; ask the user about on-screen character count |
| Quest draw calls | <100 / <200 [S18] vs ranges up to 1000 [S17][S23] | Use [S18] defaults |
| Mobile draw calls | 100–200 [S20] vs <500 / ~700 [S21][S22] | 100–200 for web and low-end; ≤500 native mid |
| Ratio vs error LODs | 50 %/level [S13][S10] vs error/screen-size targets [S29] | 50 % chain, error-driven switching |
| Godot `normal_split_angle` | 60° suggested in 4.3 vs "unused" in current source [S32][S40] | Resolved: only tune `normal_merge_angle` (default 20° in current source) |
| Skeletal Nanite | "Supported" (docs) [S9] vs experimental, morph/cloth gaps (forum, 5.7 notes) [S44] | Classic skeletal LODs for characters |
| Khronos banner-ad budget | table 30k / 500 KB vs text 60k / 1 MB [S36] | Use the table (stricter) |
| Unreal mobile 500k/view | Official [S21], but calibrated on iPad 4/Air | Ceiling for 30 fps on old devices; modern devices go higher. Profile. |
| Do polycounts matter? | Godot: vertex cost low on PC/console, polycount "matters less than many artists assume" [S14]. Polycount wiki: "common sense, don't be wasteful" [S1]. Arm/Meta: vertices are expensive on mobile/VR [S13][S17]. | Strict on mobile/VR/web; on PC prioritize materials, overdraw and texture memory over raw tris |

---

## Sources

- [S1] Polycount Wiki, "Polygon Count" (last modified 2021-09-01). http://wiki.polycount.com/wiki/Polygon_Count
- [S2] Godot docs (stable), "Mesh level of detail (LOD)". https://docs.godotengine.org/en/stable/tutorials/3d/mesh_lod.html
- [S3] Godot docs, "GPU optimization" (material reuse example). https://docs.godotengine.org/en/stable/tutorials/performance/gpu_optimization.html
- [S4] Godot docs, "Visibility ranges (HLOD)". https://docs.godotengine.org/en/stable/tutorials/3d/visibility_ranges.html
- [S5] Godot docs, "Optimizing 3D performance". https://docs.godotengine.org/en/stable/tutorials/performance/optimizing_3d_performance.html
- [S6] CRYENGINE 5 docs, "Character Budgets" (HUNT: Showdown). https://www.cryengine.com/docs/static/engines/cryengine-5/categories/23756816/pages/23307976
- [S7] CRYENGINE 3 docs, "Character Budgets" (legacy). https://www.cryengine.com/docs/static/engines/cryengine-3/categories/1114113/pages/1310905
- [S8] Unity Manual, "Modeling characters for optimal performance". https://docs.unity.com/en-us/engine/current/manual/assets-and-media/asset-types/models/creating-dccassets/modeling-optimized-characters
- [S9] Unreal Engine docs, "Nanite Virtualized Geometry". https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
- [S10] Unreal Engine docs, "Static Mesh Automatic LOD Generation". https://dev.epicgames.com/documentation/en-us/unreal-engine/static-mesh-automatic-lod-generation-in-unreal-engine
- [S11] Unreal Engine docs, "Creating and Using LODs". https://dev.epicgames.com/documentation/en-us/unreal-engine/creating-and-using-lods-in-unreal-engine
- [S12] Unity Manual, "Optimizing graphics performance". https://docs.unity.com/en-us/engine/current/manual/analysis/graphics-performance-profiling/optimizing-graphics-performance
- [S13] Android Developers (Arm-authored), "Optimize geometry" (games). https://developer.android.com/games/optimize/geometry
- [S14] Godot docs, "GPU optimization". https://docs.godotengine.org/en/stable/tutorials/performance/gpu_optimization.html
- [S15] Valve, Dota 2 Workshop requirements, Pudge. https://dota2.com/workshop/requirements/pudge
- [S16] VRChat Creator Docs, "Avatar Performance Ranking System". https://creators.vrchat.com/avatars/avatar-performance-ranking-system/
- [S17] Meta Horizon docs, "Debug Android / performance (Unreal)": per-device draw-call and triangle ranges. https://developers.meta.com/horizon/documentation/unreal/unreal-debug-android
- [S17b] Meta PC (Rift) performance guidelines. https://developers.meta.com/horizon/documentation/native/pc/dg-performance-guidelines/
- [S18] Meta Horizon, "Device optimization comparison" (updated 2026-05-11). https://developers.meta.com/horizon/resources/device-optimization-comparison/
- [S19] Godot docs, ResourceImporterScene + "Import configuration". https://docs.godotengine.org/en/stable/classes/class_resourceimporterscene.html, https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/import_configuration.html
- [S20] PlayCanvas User Manual, "Optimization guidelines". https://developer.playcanvas.com/user-manual/optimization/guidelines/
- [S21] Unreal Engine docs, "Performance Guidelines for Mobile Devices". https://dev.epicgames.com/documentation/en-us/unreal-engine/performance-guidelines-for-mobile-devices-in-unreal-engine
- [S22] Unreal Engine docs, "Optimization and Development Best Practices for Mobile Projects". https://dev.epicgames.com/documentation/en-us/unreal-engine/optimization-and-development-best-practices-for-mobile-projects-in-unreal-engine
- [S23] Unity Learn, "3.2 Optimization" (VR). https://learn.unity.com/tutorial/3-2-optimization-2
- [S24] Google ARCore, "Scene Viewer" glTF asset requirements. https://developers.google.com/ar/develop/scene-viewer
- [S25] Apple Developer Forums, "Guidance on USDZ model sizes" (WWDC 2018 rule of thumb). https://developer.apple.com/forums/thread/693867
- [S26] Khronos 3D Commerce, "Real-time Asset Creation Guidelines". https://github.com/KhronosGroup/3DC-Asset-Creation/blob/main/asset-creation-guidelines/RealtimeAssetCreationGuidelines.md
- [S27] Unity Blog, "Optimize your mobile game performance: expert tips on graphics and assets". https://unity.com/blog/games/optimize-your-mobile-game-performance-expert-tips-on-graphics-and-assets
- [S28] meshoptimizer (zeux) README (Godot's LOD backend). https://github.com/zeux/meshoptimizer
- [S29] Simplygon blog, "What is the right reduction target for LOD creation?" + Unreal plugin LOD switch posts (read via search excerpts). https://simplygon.com/posts/b83478b7-a2a1-46a9-a0e1-cba3da7da307, https://simplygon.com/posts/dd10914d-b7a4-4a78-9b3c-35eec441495d
- [S30] Unity Manual, "Introduction to level of detail". https://docs.unity.com/en-us/engine/current/manual/analysis/graphics-performance-profiling/lod/level-of-detail
- [S31] Unity Manual 6000.6, "Mesh LOD introduction". https://docs.unity.com/en-us/engine/6000.6/manual/analysis/graphics-performance-profiling/lod/mesh-lod/mesh-lod-introduction
- [S32] Godot docs, ImporterMesh (`generate_lods`; 4.3 and latest). https://docs.godotengine.org/en/4.3/classes/class_importermesh.html
- [S33] Godot docs, "Occlusion culling". https://docs.godotengine.org/en/stable/tutorials/3d/occlusion_culling.html
- [S34] Unreal Engine docs, "Nanite Technical Details". https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-technical-details
- [S35] Blender Manual (5.2 LTS), "Decimate Modifier". https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/decimate.html
- [S19b] Godot docs, "Advanced Import Settings" (normal merge angle advice). https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/advanced_import_settings.html
- [S36] Khronos 3D Commerce, "Publishing Targets" (full-version section 99). https://github.com/mlimper/3DC-Asset-Creation/blob/main/asset-creation-guidelines/full-version/sec99_PublishingTargets/PublishingTargets.md
- [S36b] Khronos glTF Asset Auditor (default limits, via package listing). https://classic.yarnpkg.com/en/package/@khronosgroup/gltf-asset-auditor
- [S37] Microsoft Flight Simulator SDK docs, "LODs". https://docs.flightsimulator.com/html/Asset_Creation/3D_Models/LODs.htm
- [S38] Unity Manual 6000.2, "How the Mesh LOD generator works" + "Generate mesh LODs on import". https://docs.unity3d.com/6000.2/Documentation/Manual/lod/mesh-lod-generator.html, https://docs.unity3d.com/6000.2/Documentation/Manual/lod/mesh-lod-generate-lods.html
- [S39] Unity Asset Transformer SDK 2026.4, "LOD generation guidelines". https://docs.unity.com/en-us/asset-transformer-sdk/2026.4/manual/sdktips/lod-guidelines
- [S40] Godot engine source (master): `scene/resources/3d/importer_mesh.cpp` (`generate_lods`), `editor/import/3d/resource_importer_scene.cpp` (import defaults). https://github.com/godotengine/godot/blob/master/scene/resources/3d/importer_mesh.cpp, https://github.com/godotengine/godot/blob/master/editor/import/3d/resource_importer_scene.cpp
- [S41] Roblox Creator Docs, "General specifications" (modeling). https://create.roblox.com/docs/en-us/art/modeling/specifications
- [S42] Khronos glTF 2.0 specification. https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- [S43] Unity Learn, "Level of Detail". https://learn.unity.com/tutorial/level-of-detail-3653
- [S44] Unreal Engine forums, "Status of Skinned Meshes (and Metahuman) and Nanite Support" (Epic staff reply), plus UE 5.7 release coverage. https://forums.unrealengine.com/t/status-of-skinned-meshes-and-metahuman-and-nanite-support/2835575, https://tomlooman.com/unreal-engine-5-7-performance-highlights/
- [S45] DSOGaming, "Dying Light: Simplygon 6.0 used to reduce polycount of key assets by 70%". https://www.dsogaming.com/news/dying-light-simplygon-6-0-used-to-reduce-polycount-of-key-assets-by-70/
- [S46] Bohemia Interactive community wiki "LOD" + BI forum "Min and max polygons" (community, low authority). https://community.bistudio.com/wiki/LOD, https://forums.bistudio.com/topic/144270-min-and-max-polygons/
- [S47] Polycount forum threads on FPS weapon budgets (read via search excerpts; forum blocks direct fetch). https://polycount.com/discussion/comment/1456883
- [T] Bundled tripo-cli v0.6.1 agent docs: `skill/commands/process.md`, `commands/make.md`, `commands/generate.md`, `examples/game-asset.md`, `common-errors.md` (local, `…/node_modules/tripo-cli/skill/`).

Not reachable or not usable: the Polycount wiki (connection refused on 2026-10-31; cited from the 2026-10-30 read), Polycount forum threads (403), web.archive.org (blocked), and the Apple "Creating USD files" page (budget list not retrieved). No official three.js/WebGL per-frame budget exists. Web-game frame numbers are vendor or blog guidance (PlayCanvas [S20]).
