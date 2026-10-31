# Game UVs and Textures: Reference for tripo-skill

Scope: UV0 layout, lightmap UV2, texel density, padding, seams, mirroring; PBR metal/rough authoring; baked
lighting in albedo (the #1 AI-generation defect); channel packing; normal map conventions; resolution per
asset class/platform; power-of-two; GPU compression (BC / ASTC / ETC2 / KTX2-Basis); atlases and trim sheets;
mipmaps. Targets: Godot 4 (primary), Unity, Unreal, glTF/GLB (Tripo's native output), Blender 5.2 as the
local fix tool.

Tags: `[glTF]` `[Godot-img]` `[Godot-mat]` `[Godot-LM]` `[Unity-LMUV]` `[Unity-fmt]` `[Unity-nrm]`
`[Unity-HDRP]` `[UE-tex]` `[UE-LM]` `[Blender-bake]` `[Blender-probe]` `[PBR-Adobe]` `[KTX]` `[Arm]`
`[Meta]` `[BCn]` `[PC-*]` (Polycount forum), `[C4D-TD]`, `[Vendor]`. URLs at the end.
**(derived)** = computed from sourced facts. **(heuristic)** = skill threshold no source states; tune on real
assets. `[Blender-probe]` = default read from Blender 5.2.3 LTS headless on this machine (2026-10-31).

---

## 0. TL;DR rules (ranked by how often AI-generated assets break them)

| # | Rule | Number / threshold | Source |
|---|------|--------------------|--------|
| 1 | Base color has NO baked lighting, cast shadows, AO or specular highlights | Only micro-occlusion tolerated | [PBR-Adobe] |
| 2 | Non-metal base color range | ≥30 sRGB (tolerant) / ≥50 (strict), ≤240 sRGB | [PBR-Adobe] |
| 3 | Metal base color = measured reflectance | 180–255 sRGB (70–100 %) | [PBR-Adobe] |
| 4 | Metallic map is binary | 0 or 1; gray only for dirt/oxidation transitions; "metal" = ≥235 sRGB | [PBR-Adobe] |
| 5 | Normal-map Y convention matches the consumer | glTF/Godot/Unity/Blender = OpenGL Y+; Unreal = DirectX Y- | [glTF] [Godot-img] [Unity-nrm] |
| 6 | Color space | Base color + emissive = sRGB; normal, ORM, roughness, metal, AO = LINEAR (MUST in glTF) | [glTF] |
| 7 | glTF/Godot ORM packing | R = occlusion, G = roughness, B = metallic | [glTF] |
| 8 | UV0 for unique baked textures: no overlap (except deliberate mirrors offset +1 U at bake), inside 0–1 | 0 overlapping area | [PC-mirror] |
| 9 | Lightmap UV2: never overlap, inside 0–1, chart gaps | ≥4 texels (UE, 4×4 block compression); Unity Pack Margin default 4 px @1024 | [UE-LM] [Unity-LMUV] |
| 10 | Island spacing scales with resolution | ≈ res/128: 4 px @512, 8 @1024, 16 @2048, 32 @4096 (sources disagree at 2K/4K) | [PC-pad] |
| 11 | Consistent texel density across an asset and its neighbours | 10.24 px/cm FPS, 5.12 TPS, ≤2.56 top-down (examples, not a standard) | [C4D-TD] |
| 12 | Power-of-two, multiples of 4 | UE: NPOT "never streamed and do not generate mipmaps". KTX2: multiple of 4 mandatory | [UE-tex] [KTX] |
| 13 | Mipmaps on for every 3D texture | +~33 % memory | [Godot-img] |
| 14 | GPU-compress everything | VRAM ÷4–6 (1024² RGBA8+mips: 5.33 → 1.33 MiB) | [Godot-img] |
| 15 | No JPEG for normal/ORM/data maps; no JPEG as KTX2 source | Tripo `texture_format` defaults to JPEG → set PNG | [KTX] tripo docs |
| 16 | Every hard (split-normal) edge sits on a UV seam | — | [PC-hardedge] |
| 17 | Export tangents (MikkTSpace) for normal-mapped, mirrored meshes | Blender glTF `export_tangents` default False | [glTF-PR149] [Blender-probe] |

---

## 1. UV0 (material UVs)

### 1.1 Overlap and mirroring — when is it OK?
| Situation | Overlap/mirror OK? | Why |
|---|---|---|
| Unique baked maps (normal, AO, AI-painted albedo with unique detail) | NO | Two surfaces write/read the same texels; bakes corrupt |
| Symmetric halves of a prop/character with no unique detail (no text, logos, asymmetric dirt) | YES (saves ~30–50 % space, heuristic) | Identical detail is acceptable |
| Repeated identical parts (bolts, wheels, rivets, fence posts) | YES, stack them | Same reason |
| Tiling / trim materials | YES, may extend far outside 0–1 | Nothing unique baked; UE: "texture UVs may overlap, wrap, or tile" [UE-LM] |
| Lightmap UV2 / baked AO channel | NEVER | "Faces must not share pixels" [Godot-LM]; no overlap or wrapping [UE-LM] [Unity-LMUV] |
| Text, decals, logos, faces | NO | Mirror reads backwards; faces look uncanny symmetric |

**Mirroring procedure** [PC-mirror]:
1. Bake from the full mirrored model (deleting half before baking changes tangents → centre seam).
2. Offset the mirrored/duplicate shells by exactly +1.0 U (outside 0–1) BEFORE baking; baker only fills 0–1,
   the repeat wrap samples the same texels. Stacked shells during bake "lay two sets of information into the
   same space". (DISAGREEMENT: a few posters bake stacked then offset; one reported Blender wrapping a full
   tile back. Rule: offset first, verify in target engine.)
3. Mirror the triangulation too (asymmetric triangulation = classic mirror seam).
4. Export tangents: glTF `TANGENT.w` = ±1 handedness; all vertices of one triangle SHOULD share w [glTF].
   Engines that regenerate tangents can flip the normal-map sign on mirrored geometry; "supplying tangents is
   the safest thing to do" [glTF-PR149]. Blender glTF exporter `export_tangents` defaults to False
   [Blender-probe] → set True.

### 1.2 Seam placement
- Seams go (a) on hard edges (Unity auto-unwrap Hard Angle default 88°, 180° for organic [Unity-LMUV];
  Blender Smart UV angle limit default 66° [Blender-probe]), (b) where the camera rarely looks (inner limbs,
  under chin, back of head, prop bottoms), (c) at material boundaries, (d) along natural seams (clothing).
- **Every hard edge must be a UV seam** (split UV island + padding) or the baked normal map cannot hide the
  shading discontinuity → gradients/black lines. A hard edge on a UV border costs no extra vertices (UV seams
  already split them) [PC-hardedge]. Alternative on generous budgets: bevel and keep soft.
- Fewer, larger islands: less padding waste, fewer mip-bleed seams, better block compression. AI/auto unwraps
  (Tripo atlas, xatlas-style) often produce hundreds of tiny islands → flag (UV-04).
- Straighten/axis-align strips (cylinders, belts, planks, trims); align to the 4×4 block grid to reduce
  compression artifacts [KTX].
- Distortion bar: UV angles/areas close to 3D. Unity defaults Angle Error 8 %, Area Error 15 % [Unity-LMUV] are
  a usable acceptance threshold.

### 1.3 Padding (dilation) vs island spacing
- **Spacing (gutter)**: empty gap between islands in UV. **Padding/dilation**: island colours bled outward
  into the gutter at bake time so bilinear filtering and mips pick up the right colour. Always dilate to fill
  the whole gutter; never leave black/transparent background behind islands ("discontinuities at UV seams, due
  to texture filtering and mip-mapping" [Blender-bake]).
- Blender bake Margin: default **16 px**, type **Adjacent Faces** (fills from the neighbouring face across the
  seam; better than Extend) [Blender-bake] [Blender-probe].
- Blender Pack Islands default margin **0.001** (≈1 px @1024) [Blender-probe] — too small. Use
  `margin_method='FRACTION', margin = spacing_px / res`.

| Texture size | Island spacing (px) | Notes |
|---|---|---|
| 256 | 2 | [PC-pad] |
| 512 | 4 | [PC-pad] |
| 1024 | 8 | [PC-pad]; Unity lightmap Pack Margin default 4 px @1024 |
| 2048 | 16 (8 acceptable if dilated) | DISAGREEMENT: 8 vs 16; also "per island vs total gap" |
| 4096 | 32 (16 acceptable if dilated) | Forum/Blenderartists cite 32 @4K; others 16 |

**(derived) mip math**: islands stay separated down to mip N only if gap ≥ 2^N px at mip 0 ("2^n times as
many pixels at the larger mipmap levels" [GameDev.net]). 16 px @2048 survives to the 128 px mip. **Rule:
spacing ≈ res/128 (min 2 px) + full dilation.** For KTX2/BC/ASTC also snap islands to 4 px multiples.

### 1.4 Texel density (TD)
- TD = texture px per world unit. Uniform within an asset and across assets seen together, else sharp/blurry
  neighbours clash [C4D-TD].

| Camera / genre | px/cm | px/m | one 2048 map covers |
|---|---|---|---|
| First-person (touchable, weapons, doors) | 10.24 | 1024 | 2 m × 2 m |
| Third-person | 5.12 | 512 | 4 m × 4 m |
| Top-down / RTS / iso | ≤2.56 | ≤256 | ≥8 m |
| Mobile / VR | ~half desktop (heuristic); one guide: 256–512 px/m [StraySpark] | | |

- Allowed deviation (heuristic): faces/hands/hero details 1.5–2×; hidden undersides 0.25–0.5×; rest ±25 %.
- Trims/tiles: keep base materials at project TD; build trims at the same TD (make the same trim in several
  sizes if needed) [PC-trim].
- **(derived) required map size**: `res = next_pow2( sqrt(surface_m² / uv_fill) × px_per_m )`.
  Ex: 1.5 m², fill 0.7, 512 px/m → sqrt(2.14)×512 ≈ 749 → 1024.
- **(derived) measured TD per face**: `TD = sqrt(uv_area × W × H / area_3d_m²)` px/m.

### 1.5 UV fill (heuristic)
Hand packing 70–85 % of 0–1; auto packers 60–75 %; <50 % wastes half the memory → repack (rotation on)
before lowering resolution.

---

## 2. Lightmap UV2 (static GI only)

| Engine | Rules | Numbers |
|---|---|---|
| Godot 4 LightmapGI | "Faces must not share pixels in the texture". UV2 slot reserved for the lightmap after baking (custom shaders cannot reuse it) | Import: Meshes > Light Baking = **Static Lightmaps** (recommended; cached in `*.unwrap_cache` → commit it). **Lightmap Texel Size 0.2** default (small/medium), **0.5+** large scenes; too small can crash. Instances scaled >2× or <0.5× of the first: use MeshInstance3D Lightmap Scale. Mesh-menu "Unwrap UV2" on imported scenes is lost on reload. Unwrapping in a DCC is "generally not recommended" [Godot-LM] |
| Unity | Inside [0,1], no overlap, wide enough margin, low angle/area deviation [Unity-LMUV] | Generate Lightmap UVs → `Mesh.uv2`. Hard Angle **88°** (0–180), Angle Error **8 %**, Area Error **15 %**, Margin Method Manual/Calculate, **Pack Margin 4 px** (1–64) measured on a 1024² lightmap the mesh fills. Older 2022.3 manual: charts "at least two full texels apart" |
| Unreal | No overlap, no wrapping outside 0–1; texture UVs may overlap [UE-LM] | **≥4 texels between charts** (DXT works on 4×4 blocks). Grid snap: spacing = 1 / lightmap_res (1/64 = 0.015625); UE uses 1 px padding. Outer UV edges need no padding (Lightmass pads). Split charts at deep crevices; connect smooth surfaces. **Min Lightmap Resolution** = lowest res ever used (sets padding); lower per-instance res → seams/leaks |
| glTF | No lightmap concept in core; clients SHOULD support TEXCOORD_0 and TEXCOORD_1 [glTF] | Put lightmap UVs in TEXCOORD_1 |

- Skinned/animated characters and dynamic props: no UV2 needed → skip for rigged Tripo outputs.
- Make it: Godot import option (preferred for Godot); Blender second UV map → Lightmap Pack (default margin
  div 0.1, box div 12 [Blender-probe]) or Smart UV + Pack Islands (FRACTION margin) → exports as TEXCOORD_1;
  Unity checkbox; Unreal Generate Lightmap UVs + Min Lightmap Resolution.

---

## 3. PBR metal/roughness authoring

### 3.1 Value ranges
| Map | Rule | Source |
|---|---|---|
| Base color, dielectric | 30–240 sRGB (strict 50–240); coal ≈ darkest, fresh snow ≈ brightest; never 0/255 | [PBR-Adobe] |
| Base color, metal | 180–255 sRGB, measured (gold/copper tinted, iron grey) | [PBR-Adobe] |
| Metallic | 0 (0 sRGB) or 1; transitions for dirt/oxidation; if metal <235 sRGB, lower the base color reflectance | [PBR-Adobe] |
| Dielectric F0 | fixed 4 % (0.04) | [glTF] [PBR-Adobe] |
| Roughness | linear grayscale; 0 = mirror, 1 = fully blurred (Godot wording) | [Godot-mat] |
| AO | separate channel; affects indirect light only; renderers with their own GI SHOULD ignore it | [glTF] |
| Painted metal | dielectric (metallic 0) | [PBR-Adobe] |
| Edge artifact | metal/non-metal edges give white fringe (metal/rough) at low TD; fix with more TD / crisp aligned edges | [PBR-Adobe] |
| Godot specular | keep 0.5 unless needed | [Godot-mat] |

### 3.2 Baked lighting in albedo (THE AI-generation defect)
**Cause**: image-to-3D projects the source image's key light, cast shadows, highlights and AO into base color.
In-engine lighting then doubles up; a sun from the other side gives "shadows on both sides"; shading can also
become fake geometry (dents/bumps) [Vendor]. Tripo image inputs default to `texture_alignment=original_image`
(faithful to photo, including its lighting) [tripo docs].

**How to check** (any 2 positives = likely baked; thresholds heuristic):
1. Directional fit: per face, fit `L ≈ a + b·(n·d)` (L = mean albedo luminance in UV footprint, n = world
   normal, solve for best d). R² > 0.3 with b > 0 → baked key light. Correct albedo has no normal correlation.
   Special case d = +Z ("sky-lit tops brighter").
2. AO correlation: Blender Cycles AO bake on the low-poly; Pearson r(albedo luminance, AO) > 0.4 → baked AO.
3. Specular hot-spots: low saturation, near white (V > 0.9, S < 0.15) blobs on non-metal → also breaks ≤240.
4. Range: >1 % of non-metal texels <30 sRGB or >240 sRGB (p1/p99) [PBR-Adobe ranges].
5. Symmetry: on a symmetric mesh, mirrored halves differ in mean luminance >15 %.
6. Visual: Blender turntable with a rotating key light vs an emission-only (unlit) render; shadows that do not
   move with the light are baked.

**Fix options to propose** (cheapest first):
| Option | Cost | Quality | Notes |
|---|---|---|---|
| A. Re-texture in Tripo with `texture_alignment=geometry` + prompt "flat albedo, evenly lit, no shadows, no highlights" | texture task credits | good; look may drift | `geometry` = texture from mesh, meant for stylized re-texturing |
| B. Regenerate from a better source image: overcast/diffuse light, no cast shadows, neutral background, three-quarter view | full regen | best | Even overcast leaves soft contact darkening [Vendor/Trompe] |
| C. Local delight (Blender + numpy): divide linear albedo by `lerp(1, AO, k)` (k 0.5–0.8) and by the fitted directional term from check 1; keep chroma; clamp 30–240 | 0 credits | medium | Approximate; verify under 3+ test lights |
| D. Frequency split: high-pass luminance (radius 5–10 % of res), recombine with per-island mean colour | 0 credits | medium-low | Also removes genuine large-scale colour variation |
| E. External AI delight (Substance Sampler "Delight (AI Powered)") | external | good | Not local; mention only |
Re-run checks 1–4 after any fix.

### 3.3 Channel packing
| Target | Texture | R | G | B | A | Color space |
|---|---|---|---|---|---|---|
| glTF 2.0 | metallicRoughnessTexture; occlusionTexture may point to the same image | Occlusion | Roughness | Metallic | ignored | Linear [glTF] |
| Godot 4 ORMMaterial3D | ORM | AO | Roughness | Metallic | — | Linear; same as glTF (docs only say "single ORM texture"; Substance "Unreal Engine" preset exports it) [Godot-mat] |
| Unreal (convention) | ORM / ARM | AO | Roughness | Metallic | opt. mask | sRGB OFF, Compression = **Masks** ("disables sRGB as masks should not be gamma corrected") [UE4.27 via search] |
| Unity HDRP | Mask Map | Metallic | AO | Detail mask | **Smoothness** | Linear (sRGB off, Texture Type Default) [Unity-HDRP] |
| Unity URP/Built-in | Metallic map | Metallic | — | — | Smoothness | Linear; occlusion separate (verify per URP version, not fetched) |

- Unity wants smoothness: `A = 1 − roughness`.
- Packed maps flagged sRGB = wrong roughness/metal response → check import flags.
- ORM at ½–¼ of base color res is often fine (KTX example: 512 ORM for 1024 base color) [KTX]; keep full res
  if roughness carries the main surface detail.
- Constant maps (std < 1/255): drop the texture, use `metallicFactor`/`roughnessFactor`/`baseColorFactor`.
- UE textures page also suggests packing grayscale maps (e.g. emissive/roughness) into alpha to save memory
  and samplers [UE-tex].

---

## 4. Normal maps

### 4.1 Conventions
| Consumer | Convention | Toggle |
|---|---|---|
| glTF 2.0 | Tangent space; R→X, G→Y, B (0.5–1] → Z (0–1]; bitangent = cross(N,T)·w; MikkTSpace if tangents absent; = OpenGL Y+ | `normalTexture.scale` multiplies X,Y [glTF] |
| Godot 4 | "X+, Y+ and Z+ … OpenGL style"; built-in shaders read only R,G (B ignored, Z rebuilt) | Import **Process > Normal Map Invert Y** for DirectX maps [Godot-img] |
| Unity | "Unity uses Y+ normal maps, sometimes known as OpenGL format" | TextureImporter Flip Green Channel [Unity-nrm] |
| Unreal | DirectX Y- | Texture **Flip Green Channel**; Interchange `flip_normal_map_green_channel` (secondary + prior pass) |
| Blender | OpenGL Y+; bake swizzle default +X +Y +Z; DirectX = set G to −Y | [Blender-bake] [Blender-probe] |
| Substance Painter | DirectX in many templates; per export preset | verify per project |

DISAGREEMENT: some third-party pages call Unity DirectX or "auto-flip". Unity's manual says Y+. Trust the
manual. Tripo GLB → glTF → OpenGL Y+: correct for Godot/Unity/Blender as-is; flip G for Unreal FBX imports
(verify: UE's glTF importer may convert itself).

### 4.2 Requirements
- Linear transfer; blue SHOULD NOT be ≤0.5; flat = (0.5, 0.5, 1.0) = #8080FF [glTF] [Unity-nrm].
- Never JPEG (block + chroma subsampling breaks vectors). PNG 8-bit OK; 16-bit for smooth bakes.
- Synced tangent basis: bake with MikkTSpace and export tangents (or let engine compute MikkTSpace from the
  same normals/UVs). Mismatch = shading seams on low-poly normal-mapped surfaces.
- Compression: BC5/RGTC 2-channel on desktop (Godot "Detect" → RGTC [Godot-img]; UE TC_Normalmap = BC5;
  [BCn] BC5 "two grayscale channels", Z rebuilt). BC1 only if memory is desperate (colour-line assumption
  fails on normals) [BCn]. ASTC: encode X,Y as `rrrg` with `astcenc -normal`, reconstruct Z [Arm]; 6×6
  (3.56 bpp) now workable for normals with astcenc 4.4+ [Arm-blog]. KTX2: UASTC +
  `--assign_oetf linear --assign_primaries none` [KTX]. Unity: normal-map scaling unsupported on mobile
  [Unity-nrm].

### 4.3 Detecting the convention (heuristic)
1. Visual: raised bump lit from top of image → OpenGL shows green on top edge (red on right); DirectX green on
   bottom.
2. **Integrability test (derived, automatable)**: `gx = −nx/nz`, `gy = −ny/nz`; a height-derived field is
   curl-free (`∂gy/∂x − ∂gx/∂y ≈ 0`). Compute mean |curl| with G as-is and with G inverted; lower curl = the
   convention relative to image row direction (rows go top-down, V goes up → calibrate the sign once on a
   Blender-baked OpenGL map). Unreliable on mostly flat maps (skip if mean |∇| tiny).
3. Validity: |2·rgb − 1| ≈ 1 ± 0.1; mean B > 0.7 (0..1). Low/noisy B → object/world-space map or not a normal.
4. In engine: bumps read as dents while a light orbits → G flipped.

Fix: `G' = 1 − G` on linear data (numpy) for portable glTF; engine flag for engine-only assets.

---

## 5. Resolution

### 5.1 Hard limits / official thresholds
| Platform / engine | Limit | Source |
|---|---|---|
| Godot mobile/web | "often can't display textures larger than 4096×4096"; Process > Size Limit caps the longer side | [Godot-img] |
| Unreal | 1×1 to 8192²; "some GPUs may not support texture sizes larger than 8192"; most TextureGroups MaxLODSize 4096 → 8K needs `MaxLODSize=8192` in DeviceProfiles | [UE-tex] |
| Meta Quest (Unity best practices) | after LOD bias, >4K on PC and >2K on mobile = "excessive" | [Meta] |
| Web / KTX2 delivery | generally ≤2048² | [KTX] |
| Tripo convert | `texture_size` default **4096** — set explicitly per table below | tripo docs |

### 5.2 Budgets per asset class (heuristic consensus; derive from TD §1.4 when possible)
| Asset class | PC / console | Mobile / Quest / Web | Notes |
|---|---|---|---|
| Hero character (player) | 2048–4096 (often body + head sets) | 1024–2048 | Face 1.5–2× TD |
| NPC / enemy | 2048 | 1024 | |
| FPS view-model weapon | 2048–4096 | 1024 | Close to camera |
| Third-person weapon | 1024 | 512 | |
| Large prop / vehicle (2–5 m) | 2048 | 1024 | or trim + small unique |
| Medium prop (0.5–2 m) | 1024 (the default for most props) | 512 | [StraySpark] "1K default" |
| Small prop / pickup (<0.5 m) | 256–512 | 128–256 | Atlas several |
| Modular env piece | tile/trim at project TD | same | not unique bakes |
| Background / distant | 256–512 or atlas | 128–256 | |
| Normal map | = base color | = or ½ | |
| ORM | ½–¼ base color | ¼ | [KTX] |
Polycount forum consensus: "no firm rule"; hero/FPS 2048, props 512–1024 by size and camera distance.

### 5.3 Power of two
| Source | Statement |
|---|---|
| Unreal | "Use power of two sizes when possible… Non-power of two sizes are never streamed and do not generate mipmaps" [UE-tex] |
| glTF | Clients SHOULD resize NPOT on limited platforms when sampler repeats or uses mipmaps [glTF] |
| KTX2 | POT recommended; dimensions MUST be multiples of 4 for KHR_texture_basisu [KTX] |
| Godot | POT "recommended, but is not required"; non-square POT (1024×512) fine [Godot-img] |
→ **Always ship POT** (non-square allowed). Mip chain uses truncating /2 (20×12 → 10×6 → 5×3 → 2×1 → 1×1) [KTX].

---

## 6. Compression

### 6.1 Formats
| Format | bpp | Content | Use / platform |
|---|---|---|---|
| BC1 (DXT1) | 4 | RGB (+1-bit alpha), 5:6:5 endpoints → gradient banding | Opaque base color, desktop/console [BCn] [Unity-fmt] |
| BC3 (DXT5) | 8 | RGBA (BC4-style alpha) | Alpha base color; faster to encode than BC7 |
| BC4 | 4 | 1 channel, better than BC1 for grayscale | Height, roughness, masks |
| BC5 (RGTC) | 8 | 2 channels | Normal maps |
| BC6H | 8 | HDR RGB half | HDR/lightmaps/skies |
| BC7 (BPTC) | 8 | RGB(A), best quality, slow encode | Hero base color, ORM; DX11+ guaranteed |
| ETC2 RGB / RGBA | 4 / 8 | GLES3 / Vulkan baseline | Android fallback; Godot non-HQ mobile/web |
| ASTC 4×4 … 12×12 | 8 … 0.89 (= 128/(bw·bh): 5×5 5.12, 6×6 3.56, 8×8 2.0) | 1–4 channels, LDR/HDR | iOS A8+, modern Android, Quest. 6×6 most common on mobile [Arm-blog]; 6×6 and 8×8 most popular |
| KTX2 ETC1S | very small | low-variation colour | Stylized/toon/UI base color, emissive [KTX] |
| KTX2 UASTC | ~8 | high fidelity | Normal, ORM, detailed colour [KTX] |
BC2 is obsolete ("never used nowadays") [BCn]. All BC/ASTC/ETC work on fixed blocks (BC = 4×4).

### 6.2 Per-engine / platform choices
| Target | Base color | Normal | ORM / masks | Notes |
|---|---|---|---|---|
| Godot 4 desktop | VRAM Compressed → S3TC (BC1/BC3); High Quality → BC7 | RGTC (auto via Normal Map = Detect) | BC1/BC7 linear | HQ only Forward+/Mobile renderers, not Compatibility [Godot-img] |
| Godot 4 mobile/web | ETC2; High Quality → ASTC | RGTC/ETC2 RG | ETC2/ASTC | Basis Universal = smallest files, slow import, moderate loss |
| Unity desktop | DXT1 / BC7 | BC5 (normal map type) | BC7 | [Unity-fmt] |
| Unity Android/iOS | ASTC (ETC2 fallback) | ASTC | ASTC | ASTC devices: Adreno 4xx+, Mali T624+, Apple A8+ [Unity-fmt] |
| Unreal | Default (BC1/BC3, sRGB) or BC7 | Normalmap (BC5, sRGB off) | Masks (sRGB off); Grayscale/Alpha BC4 | [UE4.27 via search] |
| Quest | ASTC 6×6 typical, 4×4 for skyboxes (community) | ASTC | ASTC | trilinear/aniso filtering [Meta] |
| Web glTF | KTX2 ETC1S (simple) / UASTC | KTX2 UASTC | KTX2 UASTC | lamp: 96 MB → 21 MB GPU [KTX] |

- Memory: Godot 1024² RGBA8 + mips 5.33 MiB lossless vs 1.33 MiB VRAM-compressed [Godot-img]. UE full mip
  chain: 2048² DXT1 2.66 MB / DXT5 5.33 MB; 4096² 10.6 / 21.3 MB [UE-tex]. PNG/JPEG/WebP only shrink
  disk/download; VRAM is still RGBA8.
- ASTC: compress colour in sRGB mode (`-cs`), data in linear (`-cl`); sRGB applies to RGB only, alpha linear
  [Arm].
- KTX2 recipes [KTX]: normal/ORM `toktx --t2 --encode uastc --uastc_quality 4 --uastc_rdo_l .5
  --uastc_rdo_d 65536 --zcmp 22 --genmipmap --assign_oetf linear --assign_primaries none` (normals: rdo_l .25);
  simple colour `--t2 --encode etc1s --clevel 4 --qlevel 255 --genmipmap`. Or
  `npx @gltf-transform/cli uastc|etc1s in.glb out.glb`.
- Useless alpha (all 255) forces BC3/BC7-alpha instead of BC1 → 2× memory (derived).

---

## 7. Mipmaps and filtering
- Always generate mips in 3D; +~33 % memory; a 64² texture has 6 extra levels [Godot-img]. Godot "Detect 3D"
  auto-enables mips + VRAM compression on first 3D use; Mipmaps > Limit "currently not implemented".
- glTF: clients SHOULD generate mips at runtime; else fall back to non-mip filtering [glTF].
- UE TextureGroups: NumStreamedMips −1 = all streamable; NPOT never streams/mips [UE-tex].
- Godot Roughness > Src Normal: roughness filtered from normal map on import to cut specular aliasing.
- Godot Fix Alpha Border (default on): avoids dark outlines with bilinear filtering on alpha textures.
- Meta: trilinear or anisotropic filtering on all world textures [Meta].
- Mip bleed = insufficient spacing/dilation (§1.3); atlases need padding sized for the lowest visible mip.
- glTF `alphaMode: MASK` + `alphaCutoff` (≥ cutoff = opaque); dilate colour under transparent texels.

---

## 8. Atlases and trim sheets
- **Atlas** small props that appear together into one texture set → fewer materials/draw calls. Same TD,
  same shader, same blend mode (don't mix opaque and alpha-blended). Group by load context so one prop does
  not drag in a huge atlas. Padding per §1.3 for the lowest visible mip.
- **Trim sheet**: tiles in ONE axis (mouldings, panels, bolts strips); UV strips snapped to trims; many meshes
  share it. **Tileable**: tiles in both axes. Build every trim at project TD (e.g. 1024 px/m) [PC-trim].
  Trims often layered on a TD-consistent base via UV2.
- **Tripo relevance**: Tripo makes unique per-object baked atlases. Trim/tile only for architecture/modular
  kits or when many generated props must share one material (re-UV onto a trim in Blender, drop the unique
  bake).

---

## 9. Other AI-texture defects to scan for (heuristic)
| Defect | Check | Fix |
|---|---|---|
| Projection smear / blur on hidden or back faces (only front view had information) | Per-island detail energy (Laplacian variance) vs view-facing; back/under islands < 25 % of front median | Re-texture `texture_alignment=geometry`, multiview input, or local repaint |
| Fragmented atlas (hundreds of islands, effective TD far below nominal) | UV-04 + UV-07 | Tripo `uv` task, Blender re-unwrap + rebake |
| JPEG block artifacts in normal/ORM | file type; 8×8 blockiness metric | Re-export PNG (`texture_format=PNG`) |
| Grey "everything 0.5" metallic | TX-05 | Snap metallic to 0/1 by material mask |
| Constant roughness | TX-07 | Use factor or regenerate `texture_quality=detailed` |
| Visible seams in albedo along UV borders | colour delta across seam edges in 3D | Rebake with Adjacent Faces margin, or seam-aware blur |
| Baked lighting | §3.2 | §3.2 A–E |

---

## 10. Automated checks (Blender headless + numpy)
`blender -b --python-exit-code 1 --python check_uv_tex.py -- model.glb` (Blender bundles numpy). Set image
`colorspace_settings.name` correctly ('sRGB' vs 'Non-Color') before reading `pixels`.

| ID | Check | Method | Warn / fail (heuristic unless sourced) | Fix |
|---|---|---|---|---|
| UV-01 | Has UV0 | `mesh.uv_layers` | missing = FAIL | Tripo `uv` (20 cr) / `decimate --smart-uv` / Blender unwrap + bake |
| UV-02 | Inside 0–1 (unique bake) | loop UV min/max | outside on non-tiling = WARN | Pack Islands |
| UV-03 | UV0 overlap | `bpy.ops.uv.select_overlap()` then count | >0.5 % area, not a +1 U mirror = FAIL | Repack / offset mirrors |
| UV-04 | Fragmentation | bmesh island flood-fill | >200 islands per 10k tris, or median island <16×16 px = WARN | Re-unwrap, rebake |
| UV-05 | Fill ratio | Σ UV tri area | <0.5 WARN, <0.35 FAIL | Pack Islands, rotate on |
| UV-06 | Spacing | min island gap in px | < §1.3 table = WARN | Repack, FRACTION margin |
| UV-07 | TD uniformity | per-face TD (§1.4), area-weighted CV | CV >0.35 or >10 % area outside 0.5–2× median = WARN | Average Islands Scale + Pack, rebake |
| UV-08 | TD vs target | median vs §1.4 | <0.5× or >2× = WARN | Change texture_size / rescale |
| UV-09 | Distortion | angle/area ratio UV vs 3D | >15 % area or >8 % angle on >10 % faces | Re-unwrap with more seams |
| UV-10 | Hard edges vs seams | sharp / split-normal edges not on seam | any = WARN | Mark seam, re-unwrap |
| UV-11 | UV2 for static env assets | 2nd layer: overlap, 0–1, ≥4 texel gaps at min res | missing = INFO; overlap = FAIL | Godot Static Lightmaps import / Blender Lightmap Pack |
| UV-12 | Tangents exported for mirrored normal-mapped mesh | glTF TANGENT attribute present | absent + mirrored UVs = WARN | Re-export `export_tangents=True` |
| TX-01 | POT, multiple of 4 | `image.size` | NPOT = WARN (FAIL for KTX2/UE streaming) | Lanczos resize |
| TX-02 | Size vs class | §5.2 | >2× budget = WARN | Downscale / convert texture_size |
| TX-03 | Albedo range (non-metal mask) | sRGB luminance p1/p99 | p1<30 or p99>240 WARN; >5 % out FAIL | Levels remap 30–240 keep hue |
| TX-04 | Baked lighting | §3.2 1–3, 5 | ≥2 positives = FAIL | §3.2 A–E |
| TX-05 | Metallic binary | % 0.1<m<0.9 | >15 % = WARN | Snap; fix base color reflectance |
| TX-06 | Metal reflectance | base color where m>0.9 | <180 sRGB = WARN | Raise to measured values |
| TX-07 | Roughness sanity | std, mean | std<0.02 → factor; mean<0.1 on non-metal suspicious | Factor / regenerate |
| TX-08 | Normal validity | length ≈1 ±0.1, mean B>0.7, B>0.5 everywhere [glTF] | fail = not tangent-space | Rebake |
| TX-09 | Normal convention | §4.3 curl test | mismatch with target = FAIL | Invert G / engine flag |
| TX-10 | Data map format | extension/mime | JPEG normal/ORM = WARN | Re-export PNG |
| TX-11 | ORM layout | per-channel stats | G binary + B continuous (swapped) = FAIL | Swizzle |
| TX-12 | Color-space flags | slot vs flag | normal/ORM as sRGB = FAIL | Set linear |
| TX-13 | Useless alpha | alpha all 1 | WARN (2× VRAM) | Strip alpha |
| TX-14 | Constant map | std<1/255 | INFO | Material factor |
| TX-15 | Black/transparent gutters | sample outside UV mask | mean ≈0 = WARN | Dilate / bake margin |

Also useful: `npx @gltf-transform/cli inspect model.glb` (texture sizes, formats, GPU size estimate);
`npx gltf-validator` (spec compliance incl. TANGENT w, missing TEXCOORD).

---

## 11. Fix recipes (zero credit, local)
1. **Re-unwrap + rebake (Blender)**: duplicate mesh → new UV map → Smart UV Project (66°) or seams + Unwrap →
   Average Islands Scale → Pack Islands (`margin_method='FRACTION'`, margin = spacing/res, rotate on) →
   Cycles bake old-UV material onto new UV: albedo via **Diffuse pass with only Color enabled** (pass colour
   independent of lighting) or Emit; normals via Selected-to-Active with cage/extrusion; Margin ≥ spacing,
   type Adjacent Faces → delete old UV map → export GLB with `export_tangents=True`.
   Tripo alternatives: `uv` task (20 credits, ≤80k tris, keeps rig/animation, returns `uv_render.webp`),
   `decimate --smart-uv` (v3.0, during retopology).
2. **Normal G flip**: numpy `img[...,1] = 1 - img[...,1]` (linear); or Godot Normal Map Invert Y.
3. **ORM pack/swizzle**: numpy stack; Unity A = 1 − roughness.
4. **Albedo range clamp**: sRGB luminance remap `30 + (L − p1)·210/(p99 − p1)`, keep chroma; skip metal mask.
5. **Delight (approx.)**: AO bake (Cycles, 64+ samples) → `albedo_lin / lerp(1, AO, k)`, k 0.5–0.8; remove
   fitted directional term; clamp.
6. **Resize to budget, POT**: Lanczos; repack only if TD drops below target.
7. **Godot import**: VRAM Compressed + mipmaps (default for 3D); High Quality for hero assets; Size Limit for
   mobile.
8. **KTX2 for web**: glTF-Transform `uastc` (normal/ORM) / `etc1s` (simple colour), `--power-of-two`.
9. **Strip useless alpha / constant maps**: save RGB; use material factors.

## 12. Tripo levers (bundled tripo-cli docs; verify with `--dry-run --json`, never submit)
- Generation/texture: `texture_quality` standard/detailed/extreme; `pbr` (default true); `texture_alignment`
  `original_image` (image default; inherits photo lighting) vs `geometry`; `texture_seed`.
- `convert`: `texture_size` (default 4096 → set per §5.2), `texture_format` (default JPEG → PNG for data maps,
  then engine-compress), `bake` (advanced materials → base textures, default true), `pack_uv` (one layout),
  `export_vertex_colors` (OBJ/GLTF only).
- `uv`: re-unwrap + remap textures/rig/animation, input ≤80k equivalent tris (decimate first), 20 credits.
- `decimate --smart-uv` (v3.0 only) unwraps during retopology; decimate bakes normals by default.
- Quad output cannot be GLTF (FBX/OBJ/USDZ only) → glTF texture rules then apply via FBX import settings.

---

## 13. Where sources disagree / it depends
- **Spacing at 2K/4K**: 8 vs 16 px @2048, 16 vs 32 @4096; per-island vs total gap. → res/128 + full dilation.
- **Lightmap chart gap**: UE ≥4 texels (block compression) vs Unity 4 px @1024 default / older "two full
  texels" vs Godot "no shared pixels" (no number). → ≥4 texels at the minimum lightmap res.
- **Albedo dark floor**: 30 (tolerant) vs 50 (strict) sRGB [PBR-Adobe]; other validators use 240 or 249
  ceiling and 180–250 / 155–255 metal ranges.
- **Unity normal convention**: manual = Y+ (OpenGL); some secondary tables say DirectX. Trust the manual.
- **Mirroring order**: offset before baking (majority) vs bake then offset; one report of Blender wrap issue.
- **Power of two**: UE hard consequences (no mips/streaming) vs Godot "not required" vs glTF "SHOULD resize
  on limited platforms". → Ship POT.
- **Godot UV2 from DCC**: Godot docs call DCC-unwrapped UV2 "generally not recommended", while UE/Unity
  artists commonly hand-make UV2. For Godot targets prefer the import-time unwrap.
- **Texel density numbers**: 10.24 / 5.12 / 2.56 px/cm are examples; mobile/VR guidance varies
  (256–512 px/m). Set a project TD and keep to it.
- **Resolution budgets**: no official per-class table exists anywhere; §5.2 is forum/blog consensus.
- **Delighting**: every method is approximate; vendor claims are marketing; verify under several lights.
- **ASTC block for normals**: older guidance 4×4/5×5; Arm says 6×6 viable with astcenc 4.4+.

---

## Sources
Fetched / read this pass:
- [glTF] Khronos glTF 2.0 Specification (source adoc read in full for textures/materials): https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html , https://github.com/KhronosGroup/glTF/blob/main/specification/2.0/Specification.adoc
- [glTF-PR149] Khronos glTF-Sample-Models PR 149 (mirrored tangents): https://github.com/KhronosGroup/glTF-Sample-Models/pull/149
- [KTX] Khronos KTX Artist Guide: https://github.com/KhronosGroup/3D-Formats-Guidelines/blob/main/KTXArtistGuide.md
- [Godot-img] Godot docs, Importing images: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_images.html
- [Godot-mat] Godot docs, Standard Material 3D and ORM Material 3D: https://docs.godotengine.org/en/stable/tutorials/3d/standard_material_3d.html ; ORMMaterial3D class: https://docs.godotengine.org/en/stable/classes/class_ormmaterial3d.html
- [Godot-LM] Godot docs, Using LightmapGI: https://docs.godotengine.org/en/stable/tutorials/3d/global_illumination/using_lightmap_gi.html
- Godot blog, Fixing tangents for accurate normal maps (3.1-era): https://godotengine.org/article/fixing-tangents-accurate-normal-maps/
- [Unity-LMUV] Unity Manual, Generating lightmap UVs + Lightmap UVs settings reference: https://docs.unity.com/en-us/engine/current/manual/lighting-overview/direct-and-indirect-lighting/lightmapping/lighting-gi-uvs/generating-lightmapping-uvs , https://docs.unity.com/en-us/engine/6000.6/manual/lighting-overview/direct-and-indirect-lighting/lightmapping/lighting-gi-uvs/reference ; older 2022.3: https://docs.unity.cn/Manual/LightingGiUvs-GeneratingLightmappingUVs.html
- [Unity-fmt] Unity Manual, Choose a texture compression format by platform: https://docs.unity.com/en-us/engine/6000.0/manual/materials-and-shaders/textures/textures-getting-started/texture-compression-formats/texture-choose-format-by-platform
- [Unity-nrm] Unity Manual, Normal map: https://docs.unity.com/en-us/engine/6000.0/manual/materials-and-shaders/built-in/shader-built-in-configure-properties/standard-shader-texture-maps/material-parameter-normal-map/map
- [Unity-HDRP] Unity HDRP Mask and detail maps: https://docs.unity3d.com/Packages/com.unity.render-pipelines.high-definition%4013.1/manual/Mask-Map-and-Detail-Map.html
- [UE-tex] Unreal, Textures in Unreal Engine: https://dev.epicgames.com/documentation/en-us/unreal-engine/textures-in-unreal-engine ; Texture format support and settings: https://dev.epicgames.com/documentation/en-us/unreal-engine/texture-format-support-and-settings-in-unreal-engine
- [UE-LM] Unreal, Understanding lightmapping: https://dev.epicgames.com/documentation/en-us/unreal-engine/understanding-lightmapping-in-unreal-engine ; Generating lightmap UVs: https://dev.epicgames.com/documentation/en-us/unreal-engine/generating-lightmap-uvs-in-unreal-engine
- UE4.27 Texture compression settings (403 on fetch; content via search excerpts): https://docs.unrealengine.com/4.27/RenderingAndGraphics/Textures/TextureCompressionSettings
- [Blender-bake] Blender 5.2 manual, Render Baking: https://docs.blender.org/manual/en/latest/render/cycles/baking.html
- [Blender-probe] Blender 5.2.3 LTS defaults read headless (bake margin 16 / ADJACENT_FACES / swizzle +X+Y+Z; Smart UV 66°; Pack Islands margin 0.001; Lightmap Pack margin div 0.1; glTF export_tangents False, JPEG quality 75)
- [PBR-Adobe] W. McDermott, The PBR Guide (Allegorithmic/Adobe, 2018), metal/rough chapter: https://cgvr.cs.uni-bremen.de/teaching/cg_literatur/PBR%20Guide%20-%20Wes%20McDermott,%20allegorithmic,%202018.pdf ; Adobe page: https://www.adobe.com/learn/substance-3d-designer/web/the-pbr-guide-part-2 ; Sampler PBR Validate: https://experienceleague.adobe.com/en/docs/substance-3d-sampler/using/filters/tools/pbr-validate
- [Arm] Arm astc-encoder, Encoding guide: https://github.com/ARM-software/astc-encoder/blob/main/Docs/Encoding.md ; [Arm-blog] Yet more ASTC compression: https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/yet-more-astc-compression
- [Meta] Meta Horizon, Unity best practices: https://developers.meta.com/horizon/documentation/unity/unity-best-practices-intro/
- [BCn] N. Reed, Understanding BCn texture compression formats: https://www.reedbeta.com/blog/understanding-bcn-texture-compression-formats/
- [C4D-TD] Maxon Cinema 4D help, Texel Density: https://help.maxon.net/c4d/en-us/Content/html/Texel_Density.html
- [StraySpark] Texture resolution guide (secondary blog): https://www.strayspark.studio/blog/texture-resolution-guide-games-512-1k-2k-4k
- [PC-pad] Padding (search excerpts; Polycount returned 403): https://polycount.com/discussion/191707/padding , https://polycount.com/discussion/comment/1660890 , https://blenderartists.org/t/what-value-for-the-pixel-margin/1623197 ; [GameDev.net] https://gamedev.net/forums/topic/685357-uv-padding/ , https://gamedev.net/forums/topic/699809-uv-maps-with-linear-filtering-problem
- [PC-mirror] Mirrored UV baking threads (search excerpts): https://polycount.com/discussion/comment/2299599 , https://polycount.com/discussion/comment/2300086 , https://polycount.com/discussion/comment/2442008
- [PC-hardedge] Hard edges vs UV splits threads (search excerpts): https://polycount.com/discussion/comment/1943516 , https://polycount.com/discussion/comment/2400914 , https://polycount.com/discussion/comment/2351926
- [PC-trim] Trim/TD threads: https://polycount.com/discussion/comment/2592775 , https://chrisradsby.notion.site/Let-s-talk-about-Trim-Sheets-Techniques-16ea5b47012c802eba09d28ec5ce9189
- [Vendor] Baked lighting in AI textures (marketing; treat with care): https://www.neural4d.com/how-tos/how-to-solve-baked-shadows-and-lighting-issues , https://www.3daistudio.com/blog/best-way-to-generate-3d-model-from-image-for-game-development , https://wavect.io/blog/ai-3d-model-generators-game-development-2026.md , https://github.com/Patch-gg/trompe/wiki
- Normal-map convention secondary: https://www.strayspark.studio/blog/directx-vs-opengl-normal-maps-explained , https://worldofleveldesign.com/categories/texturing/normal-maps-directx-vs-opengl.php
- tripo-cli 0.6.1 bundled docs: `skill/commands/process.md`, `commands/make.md`, `common-errors.md`, `examples/game-asset.md`

Carried from prior pass (not re-fetched): Unity TextureImporter.flipGreenChannel https://docs.unity3d.com/Documentation/ScriptReference/TextureImporter-flipGreenChannel.html ; UE Interchange texture pipeline https://docs.unrealengine.com/5.3/en-US/PythonAPI/class/InterchangeGenericTexturePipeline.html ; Meta/Arm VR asset tips https://developers.meta.com/horizon/blog/top-tips-from-arm-for-vr-asset-optimization/ ; Roblox polished assets (tileables vs trims) https://create.roblox.com/docs/en-us/tutorials/curriculums/environmental-art/develop-polished-assets

Access notes: wiki.polycount.com refused connections; polycount.com forum, gamedev.net and UE4.27 docs returned
403 (cited via search excerpts only, no workaround attempted). Blender glTF manual page 404'd (manual
restructure); exporter defaults were read from Blender itself instead.
