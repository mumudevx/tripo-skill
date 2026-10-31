# Blind spots: completeness review of the tripo-skill design

Reviewer role: senior technical artist and tools engineer, acting as a completeness critic.
Inputs read: all `tripo-*.md` and `game-*.md` notes in full or by section, plus `prior-art-synthesis.md`. Spot checks run on 2026-10-31 (zero credits): `tripo --version` gives 0.6.1, `tripo balance --json` gives `{"balance":35,"frozen":0}`, `tripo docs --topic examples/game-asset`, and a `find` that located **50 real Tripo outputs (`tripo-out/**/task.json`) already on disk** in the GRIME repo.

What the user asked for:
1. Coverage of Generation, Processing and Animation.
2. Appropriate polygons, topology and textures.
3. Detect problems, propose alternatives ("X or Y?"), ask, then apply.
4. Game-ready: optimized and easy to edit later.

This file lists what the user has not asked for but a strong skill needs, ranked **MUST / SHOULD / NICE**. After that come the contradictions and weak spots in the notes, and the questions only the user can answer.

---

## A. MUST: without these the skill will waste credits or ship broken assets

### A1. The 35-credit reality has to drive the design, not sit in a footnote
- **Why it matters.** With 35 credits the account buys roughly **one** asset: one textured H-series image-to-model (30) plus a basic convert (5), or one decimate v3.0 (35). Every Tripo animation path costs more than the balance. Generation (20–30) + rig (25) + one retarget (10) = 55–65. Prior-art data adds 25–35 % re-roll overhead for mechanical objects, and a typical finished PATINA part cost 65. The user wants all three areas (Generation, Processing, Animation), but the balance cannot pay for one full pass through them.
- **Proposal.**
  - Add a **budget planner** that runs before any work. Given the asset brief, it prints the full planned credit path (generate, fix, rig, animate, convert), what fits in the current balance, and what needs a top-up.
  - Make "Blender/Godot first, Tripo only where it is uniquely better" the default fix ladder.
  - Keep a running **credit ledger** per project: planned vs actual, from `credits_consumed`.
  - Ship **one** price table (`references/price-table.md`) that records the date, the source (pricing page, measured, or CLI note) and a confidence level. Today three notes disagree (see section D).
  - The CLI pre-check only blocks at balance ≤ 0, and dry-run in 0.6.1 shows no numbers. So the skill has to compute cost itself from the final dry-run payload, using the pricing-page trigger list for advanced convert.

### A2. An asset brief and a persistent project profile, captured before anything is generated
- **Why it matters.** Every threshold in the notes depends on context: target engine, renderer, platform, camera distance and FOV, asset class, art style, whether the asset is static, rigged or destructible, and whether it is a hero or a background piece. That covers triangle budgets, texel density, texture size, material count, pivot rules, collision type and severity grading. The notes have the tables but no intake step. Without one, the agent either asks 15 questions per asset or silently uses `--for game-mobile`, whose `face_limit=15000` is several times too high for a mobile prop.
- **Proposal.**
  - Keep a one-time project profile at `<project>/.claude/tripo/project.json` with: engine and version (Godot 4.7.x), renderer (Forward+ / Mobile / Compatibility), platform list, game camera (position, FOV, typical distance), texel density target, art style (`pbr` on/off, stylised or realistic), naming scheme, folder roots, pinned Tripo model wire versions, pinned CLI version, and budgets per asset class.
  - Keep a per-asset brief that adds: class, real-world size, rig yes/no, parts list, hero or background, and deliverables.
  - Ask only what is missing. Auto-detect the existing project conventions (GRIME and PATINA layouts) instead of imposing new ones.

### A3. Pipeline ordering: a cloud phase, then a local phase ("the point of no return")
- **Why it matters.**
  - While an asset stays inside Tripo, chained by task id, steps are cheap and keep the lineage.
  - Once the asset is edited in Blender, every later Tripo step needs an upload. Through `make` that is an **import task of unknown cost**. The model also comes back **normalized** in scale and translation. Direct commands skip the import but have **no dry-run**.
  - Tripo's decimate **bakes** textures onto the low-poly, and `mesh uv` **remaps rig and animation**. Blender can do neither cheaply.
  - The notes compare fixes one at a time but never state this ordering rule.
- **Proposal.**
  - Encode an explicit phase order: **(1)** Tripo generation; **(2)** Tripo-only fixes, chained by `@name`, each priced and approved; **(3)** download and freeze `raw/`; **(4)** local Blender fixes, LODs, collision and export; **(5)** engine import and in-engine checks.
  - When a user picks a Blender fix while a Tripo fix might still be needed later, warn them that going back to Tripo will cost an import and a renormalization.
  - Record `normalize_scale` / `normalize_translation` from any file-based task and undo them locally.

### A4. One automated QA tool: unified, format-agnostic and calibrated
- **Why it matters.** The notes contain **five overlapping detectors** (`qa.py`, `texqa.py`, `audit_glb.py`, `mesh_stats.py`, and the specified but unwritten `check_uv_tex.py`). They disagree on basics:
  - Weld epsilon: 1e-5 × diagonal, vs 1e-5 absolute, vs 1e-4 m.
  - Non-manifold count: `audit_glb.py` counts boundary edges as non-manifold; `qa.py` excludes them.
  - Formats: `qa.py` and `texqa.py` import **glTF only**, yet quad, P2, decimate v2 quad and FBX rig outputs are all FBX.
  - Thresholds: almost all are `[H]`, never tuned on real Tripo output.
  - Failures: Blender exits 0 when a script raises (prior art gap #6), so a crash can look like a clean report.
- **Proposal.**
  - Write one `scripts/blender/qa.py` that imports GLB, FBX and OBJ.
  - Run it with `--python-exit-code 1`.
  - Output a **versioned JSON schema** (`schema_version`) so later runs can be diffed.
  - Give every metric a severity rule that depends on the brief, e.g. "S0 rig / S1 static".
  - Calibrate the `[H]` thresholds on the **50 real Tripo outputs already on disk** plus the prior-art test set (T1–T12, R1–R12). That costs 0 credits and gives real distributions for baked-light r, sliver %, island counts and face_limit overshoot.
  - Re-run QA after every fix step. If a metric gets worse, roll the step back automatically. The notes show that cleanup itself creates defects.

### A5. Visual QA the agent can actually look at
- **Why it matters.** Prior art is blunt: every real fix came from **owner eyes**, never from a metric. Albedo-only renders missed shading defects (waves, star fans, dark wedges). Orientation was guessed per object, and one fix landed on the wrong side. Claude can read PNGs, so a well-designed contact sheet turns the agent into a first-pass reviewer.
- **Proposal.**
  - Write `scripts/blender/render_sheet.py`. It produces one PNG contact sheet per asset version, kept under about 1500 px so it is cheap in context. Contents:
    - 6 ortho views plus an iso view, in three passes: lit (studio HDRI or matcap), flat albedo, and wireframe overlay.
    - A **normal-map-off** pass.
    - A **game-camera** view taken from the project profile.
    - A front-axis arrow and a ground grid in metres.
    - Text labels showing triangle count and size.
  - Optionally render an 8-frame turntable strip under a rotating key light. That catches baked lighting: shadows that do not move are baked into the albedo.
  - Use Workbench or EEVEE. **Verify headless EEVEE on this Mac**; fall back to Workbench with matcap.
  - Pair the sheet with the prior-art self-contained HTML QA page for the human (before/after, game shot).

### A6. Present findings as decisions, then apply them safely
- **Why it matters.** The user wants "should I do X or Y?". The notes have good per-defect fix menus, but no structure for **combining** findings into one decision, no way to mark which options are free and which are paid, no rule for what happens when fixes conflict (e.g. "symmetrize" vs "keep Tripo normals"), and no undo.
- **Proposal.**
  - Define a fix-plan schema. Each finding carries: severity; options as {route Blender / Tripo / regenerate / accept, credits, minutes, risk, reversibility, what it can break}; a recommended option; and dependencies (e.g. decimate before uv, uv before bake).
  - Show it with AskUserQuestion, one decision per S0/S1 cluster. Batch the S2/S3 findings into one "apply all free cosmetic fixes?" question.
  - Never put a paid step inside a bundle; each paid step gets its own explicit approval showing the credit number.
  - Make every applied fix a re-runnable script stored with the asset. Fixes start from `raw/`, use regions relative to the bbox, and carry the review note and date (prior art G29).
  - Keep "place as-is, fix later" as a first-class option, because the owner chose it in GRIME.

### A7. A hard credit-spend guard outside the model
- **Why it matters.**
  - In headless mode `--yes` is turned on automatically, so nothing stops a run once the command is issued.
  - `redo`, `batch`, `generate *`, `anim *`, `mesh *`, pipes and the MCP `tripo_make` all spend credits with no dry-run.
  - One wrong command can drain the whole balance.
  - Relying on the model to remember the rule is not enough.
- **Proposal.**
  - Add a Claude Code **PreToolUse hook** in the project, installed through `update-config` with the user's consent. It blocks any `tripo` invocation that is not `--help`, `docs`, `balance`, `usage`, `history`, `task get/list/watch`, `config list`, `doctor`, or `make ... --dry-run`, unless a fresh approval token exists.
  - The token is written only after the user approves a specific dry-run plan, and its hash binds it to that exact command line.
  - Also refuse `-p model=` (it silently overrides `--model`), `-n` combined with `--then`, `redo` without an explicit id, and `batch run` without `--retries 0`.

### A8. Animation that the balance can pay for: Tripo rig plus free clips, retargeted in Godot
- **Why it matters.**
  - Retarget costs 10 credits per clip. Rig v3.0 gives only **11 generic presets**, and the 101-clip library needs rig v1.0, which is biped-only and lower quality.
  - Clip names, packaging, frame rate and looping are all UNKNOWN.
  - Godot is **not** a listed rig `spec`.
  - The user owns Godot, which retargets humanoid animation libraries for free through `BoneMap` and `SkeletonProfileHumanoid`.
- **Proposal.**
  - Make the default animation route: free rig-check, then rig (25, `model=v3.0-20260909`, `spec` chosen by a test), then Godot retargeting of free or owned clip libraries. Paid Tripo retarget becomes an option.
  - Add a **rig acceptance test** before buying anything else. Import the rigged file into Godot headless, run the BoneMap auto-map, and fail on red or magenta bones.
  - Check the remaining rig facts: a single root (Mixamo naming has no root; Godot root motion needs one), at most 4 influences, rest-pose angle, and `tripo::` bone names becoming `__` in Godot.
  - Offer free fallbacks: Blender Rigify, or the Mixamo web auto-rigger (human step; Adobe terms apply).
  - Record each library's licence (see A9).

### A9. Licensing, commercial terms and store disclosure
- **Why it matters.** No tripo or game note covers Tripo's terms of service. The prior art says PATINA logged Tripo and Gemini as "paid, not read", and both projects keep an `asset_log.md` as evidence for the Steam AI-content disclosure. The open points are:
  - Ownership of outputs.
  - Commercial use under API credits.
  - Whether uploaded concept images may be used for training.
  - Whether the plan tier affects rights. **Unverified: check the current terms; do not assume.**
  - Licences of animation libraries and Mixamo.
  - Higgsfield terms for concept images.
- **Proposal.**
  - Add a `references/licensing.md` placeholder that the user fills in from the actual terms.
  - Write one provenance record per asset: tool, model wire version, CLI version, task ids, input image hashes and their source tool, human edits, licence row.
  - Write into the project's existing asset log in its own format.
  - Keep store disclosure separate from the user's rule of no AI attribution in commits: the two do not conflict.

### A10. Concept input pipeline and the user's Higgsfield rules
- **Why it matters.**
  - Prior art: input quality is the **biggest credit sink**. Problems included 3/4 side views, a right view copied from the left, chroma tint on glass, 512 px views, lidded cavities, ground slabs, and baked lighting caused by words like "key light, ambient occlusion" in the prompt.
  - The user's global rule requires reference-first, a byte-identical style formula, one object per image on a white background, AI generation for every part, and approval before 3D.
  - Two tensions follow:
    - **(a)** The user's rule says a "three-quarter view" single image, but Tripo multiview **requires a front view** and the research favours orthographic multiview.
    - **(b)** Tripo has its own image tools (t2i at 5, image-to-multiview at 10, edit-multiview at 5 per view; image pool concurrency 1), while the user's rule names Higgsfield.
  - There is also a trigger collision: the installed `higgsfield-generate` skill already claims "create a 3D model/GLB".
- **Proposal.**
  - Add a `prep` phase with `preflight_ref.py`, carrying over the automatable G4 checks: at least 1K per view, real file format (≈18 % of `.png` files were JPEG bytes), single object, L/R copy/mirror IoU, thin-part and glass warnings, no ground or shadow. The rest becomes a vision checklist the agent applies to the images.
  - Support both routes: a 3/4 hero for single-image generation, and front/left/back/right orthos derived **from the approved hero** for multiview. Name files by what the image shows, following Tripo's side convention.
  - Ask once which image backend the project uses: Higgsfield, Tripo t2i, or Gemini as in PATINA.
  - Write the skill `description` so it does not steal "make a 3D model" from `higgsfield-generate`. Scope it to Tripo, or say it defers to `higgsfield-generate` for concepts.

---

## B. SHOULD: needed for "game-ready and editable"

### B1. Tripo vs Blender trade-off table as a first-class reference
For each defect, give both routes with numbers. Example: polycount via Tripo decimate v3.0 (35, re-bakes textures, clean topology, max 20k, measured overshoot up to 1.5×) vs Blender Collapse (free, keeps UVs, breaks below ratio ≈0.2, no re-bake) vs QuadriFlow + bake (free, slow, manifold input only). Mark which routes keep rig and animation (Tripo `uv` does), which change UVs (bake needed), and which change the scale or pivot. The notes hold all the pieces; the skill needs them in one table.

### B2. A LOD workflow per engine, and a fix for the broken bundled recipe
- The bundled `examples/game-asset.md` "LODs from one high-poly" runs `tripo make @last --then decimate:1500`. After a chain, `@last` is the **last step**, which is LOD1. So LOD2 is built from LOD1, not from the source, and every LOD costs 30–35.
- Godot auto-LOD is the default, but it is weak on skinned meshes and on fragmented AI meshes, because it locks UV-island borders.
- Proposal: build LOD0 with Tripo or Blender; build LOD1+ locally with `scripts/blender/lod.py` (Collapse in 50 % steps, shared pivot, same armature for skinned meshes, `_LODn` naming for Unity/UE); use Godot auto-LOD for static props, plus a per-mesh disable and VisibilityRange manual LODs for characters. Measure the LOD count Godot actually produces after import.

### B3. Collision generation
The notes give conventions (`-colonly`, `-convcolonly`, UCX) but no generator. Proposal: `scripts/blender/collision.py` with three modes:
- primitive fit (box, capsule or cylinder from the OBB);
- convex hull with a vertex cap;
- convex decomposition, or leave decomposition to Godot.

Output Godot suffix-named meshes, or a Godot import-script / `.import` subresource setting. Never use the render mesh, except for static level geometry. The character capsule lives in the engine, sized from the bbox.

### B4. Godot import settings as code
The notes describe Advanced Import Settings in the UI only. To be reproducible, the skill should write or patch `<asset>.glb.import` params: `nodes/apply_root_scale`, `meshes/generate_lods`, `meshes/ensure_tangents`, `skins/use_named_skins`, `animation/fps`, `gltf/embedded_image_handling` set to Extract, and per-mesh `_subresources` for physics and LOD. It should then run `godot --headless --import` and parse the errors, and offer an `EditorScenePostImport` script for fix-ups that must survive re-import. Headless Godot cannot render, so the visual checks stay in Blender, or move to a windowed Godot run that must not steal focus (GRIME's `run_quiet.sh`).

### B5. An "editable later" deliverable package
Tripo output is triangle soup with no quads, no edge flow, unique baked atlases and JPEG textures. "Editable" has to be produced, not assumed. Proposal: for every asset, ship
- a `.blend` source with live modifiers (Triangulate last, Weighted Normal, Decimate-for-LOD), unpacked and named textures (PNG for data maps), collections `SRC_` / `EXPORT` / `REF`, kept custom normals, and the high-poly kept for re-baking;
- a one-command `export.py` that turns the `.blend` into a GLB with fixed settings (`export_apply`, `export_tangents`, Y-up, deform bones only, backface culling on);
- a short `README` in the asset folder (what was fixed, how to re-export).

Offer quad topology (P2 `quad`, decimate `--quad`, QuadriFlow) only when the brief says the asset will be re-modelled or deformed, because it costs credits or is lossy.

### B6. Folder layout, versioning and lineage
Problems today:
- History is **global across projects and profiles**.
- `@name` falls back to fuzzy substring matching.
- `@last` means the last successful last-step.
- Bare UUIDs skip chain validation in dry-run.
- `-o` nests into `tripo-out/<slug>-<id8>`.
- `.tripo/context.json` appears in cwd.
- Prior art lost time pairing unlabeled `tripo-out` directories.

Proposal:
- A canonical per-asset tree: `raw/<taskid8>/` (immutable, with task.json and preview), `work/<asset>_vNN.blend`, `export/`, `qa/vNN/` (JSON and contact sheet), `fixes/` (scripts), `provenance.json` (lineage graph of task ids, seeds, wire models, CLI version, prompt and reference hashes, credits, superseded-by).
- Unique names `<project>-<asset>-vNN` on every `--name`.
- Run tripo from the asset's raw directory, and check that `.tripo/` is git-ignored.
- Never use `@last` across sessions; resolve from provenance.
- Use git LFS for binaries where the project already does.

### B7. Style lock and family consistency
Separate generations drift in colour, detail density, bevel width and texel density, and Tripo also changes its defaults over time. Proposal: a project **style lock** containing
- pinned geometry, texture and rig wire versions, plus the CLI version;
- the byte-identical style formula and the reference image (user rule);
- a fixed texture budget (`texture_size`, texel density), and a fixed `texture_seed` when re-texturing;
- the same `style_image` for `texture_prompt` (direct command only, because `--then` cannot carry objects);
- a palette check: ΔE of the albedo histogram against the reference (prior art saw ≈25 % saturation loss);
- a **family sheet** render that puts new and existing assets side by side at the same scale and lighting before approval.

### B8. Failure and retry policy at skill level
The notes cover exit codes well. What is missing is the policy:
- A maximum of 2 re-rolls per asset, then keep the best result.
- What counts as a failure that justifies a paid re-roll: an S0 that cannot be fixed locally, a missing or duplicated major part, or a wrong reference. For the last case, fix the reference first.
- Exit 6 failed is refunded, so offer a retry with changed input. Exit 6 timeout means watch the task, never redo it.
- Exit 7 means check frozen credits first.
- `unknown` status is not terminal.
- `smart_low_poly` can fail on complex inputs (refunded).
- Local failures: Blender exit 0 on exception, output under 10 KB, stale GLB, missing render. Each must stop the pipeline loudly.

Long tasks should run with `run_in_background` and `tripo task watch`, not block the session.

### B9. CLI version drift as an explicit decision
The installed 0.6.1 is behind the web docs (0.8.0):
- It blocks texture v3.5, `delight` and `texture_quality=fast`, which are the main de-lighting lever.
- It auto-selects P1 for "low poly".
- `-p model=` silently wins over `--model`.

`tripo update` is free but changes behaviour that the notes verified on 0.6.1. Proposal: detect `tripo --version` at start, store the verified-behaviour matrix per CLI version, and ask the user whether to upgrade. If they upgrade, re-run the zero-credit dry-run golden tests (D1) before trusting the skill. The raw-API `curl` route for v3.5 would read the API key from config. Do not take it without user consent, and never print the key.

### B10. Measure face_limit; do not trust it
Prior art measured `face_limit` overshooting: v3.1 + smart_low_poly 8000 gave 7.4k–17.4k tris, and decimate v2.0 20000 gave 29,943. Proposal: treat `face_limit` as a hint, always measure the result, report the deviation from budget, and decide (accept, decimate locally, or pay) through A6. Also apply the C1 style rule: for hard-surface assets with holes or slots, generate at full resolution and decimate afterwards (decimate v3.0 + smart_uv); limiting at generation suits chunky, toy-like assets.

---

## C. NICE: raises quality once A and B exist

- **C1. Multi-part assembly.** The user's Higgsfield rule is about disassembled objects. Parts generated separately need a shared scale, registration against the reference, per-part pivots (hinge, hub, grip) and sockets. Add an `assemble.py` that fits each part's bbox to the reference proportions and writes `socket_*` empties or bones.
- **C2. Texture post-pipeline.** Tripo's `convert` defaults to 4096 JPEG, and JPEG is wrong for normal and ORM maps. Re-encode, resize to POT and repack locally for free instead of paying for an advanced convert (10). Optionally produce KTX2 for web targets and pick the Godot VRAM compression per platform.
- **C3. A lessons loop.** Keep a project `lessons.md` plus a path for promoting lessons to global (prior art gap #14), with date, object, measured numbers and a "verified" flag.
- **C4. Placement into Godot.** A surgical placeholder-subtree swap with a diff and approval (prior art `godot_place.py`), run after export.
- **C5. Webhook `balance.low`** set in the dashboard, given the small balance (a human step).
- **C6. Privacy.** Offer `TRIPO_ANALYTICS_ENABLED=0`.
- **C7. Splat.** Mention it only to rule it out, since it produces no mesh.

---

## D. Skill structure and testing (MUST for the skill itself)

### D1. Structure: progressive disclosure
- `SKILL.md` (≤ ~400 lines): trigger description, hard rules (credit guard, no `-p model=`, always `--model`, always `--name`, dry-run plus approval), the phase state machine (brief → prep → plan and price → generate → QA → fix plan → apply → export → engine check → log), and which reference to load in each phase.
- `references/`: `price-table.md`, `cli-0.6.1-gotchas.md` (one merged list), `defect-catalogue.md` (prior art wins over the generic catalogue on conflicts), `budgets.md`, `engine-godot.md` (with unity/unreal stubs), `rigging-animation.md`, `image-prep.md`, `style-lock.md`, `licensing.md`, `fix-tradeoffs.md`.
- `scripts/`: `tripo_plan.py` (builds the command, runs the dry-run, asserts `steps[0].payload.model == model`, validates the enums the CLI does not check — rig_type, spec, retarget presets, texture_quality in `--then`, completion_mode — blocks quad + GLTF across steps, and computes credits), `glbstat.py` (stdlib), `blender/qa.py`, `blender/render_sheet.py`, `blender/fixkit/`, `blender/lod.py`, `blender/collision.py`, `blender/export.py`, `godot_import.py`, `provenance.py`, `preflight_ref.py`.
- `assets/`: `project.json` schema, brief template, prompt templates.

### D2. Testing the skill at zero credits
- **Golden dry-run tests.** Commit the expected payloads for about 40 representative plans. Re-run them on every CLI version change.
- **A fake `tripo` binary on PATH** for end-to-end flow tests. It replays recorded `task.json` and output files from the 50 real downloads and simulates exits 4, 6 (failed and timeout) and 7.
- **QA fixtures.** Synthetic defects (the Suzanne set already in the notes), plus real Tripo outputs labelled with known defects from the GRIME and PATINA fix logs. Measure detector precision and recall per defect, and tune the `[H]` thresholds from that.
- **Skill evals.** Use `skill-creator` with prompts such as "make a mobile crate", "this character's arms are fused", or "I have 35 credits, animate this knight". Expected behaviour: correct questions, a correct price, refusal to overspend, and correct X/Y options.

---

## E. Contradictions and weak spots in the notes

1. **Prices.** `tripo-platform.md` §1 and §21 call H-series and P1 prices UNKNOWN and cite "text_to_model 110" as illustrative. `tripo-generation.md` §2 has the full pricing page (H text 10/20, image 20/30; P1 30–50; rig 25; retarget 10). Prior art measured matching numbers. The platform note is stale here.
2. **rig-check input.** `game-ai-mesh-qa.md` §2.9 and `game-topology-rigging.md` §7 say "GLB only". `tripo-animation.md` (changelog 2026-10) says GLB/FBX/OBJ/STL.
3. **Unity rig spec.** The QA, editability and topology notes and the bundled docs say `--spec mixamo` for Unity Humanoid. The animation note says `spec=unity` exists on rig v3.0 and Mixamo naming has no root bone.
4. **P1 face_limit floor.** The QA and topology notes say 48; the CLI enforces 50.
5. **Normals policy.** `game-ai-mesh-qa.md` (recalc, clear custom normals) vs prior-art G24 (never recompute normals globally on Tripo output). The synthesis picks prior art; the skill must say so explicitly.
6. **face_limit policy.** `tripo-generation.md` says "always set it". Prior art C1 says never limit at generation for hard-surface assets with holes. Measured data shows it is not a cap anyway (B10).
7. **Detector disagreements.** Weld epsilon and the non-manifold definition differ across the scripts (A4). The glTF-only importers miss FBX outputs.
8. **Baked-lighting fix.** The QA note proposes `texture_alignment=geometry` as the fix. That parameter controls colour fidelity, not de-lighting, and prior-art G11 found `original_image` follows colours better. The real lever (texture v3.5 + `delight`) is blocked in CLI 0.6.1. The prompt-side prevention (G5: no lighting words) is the cheapest fix and should be listed first.
9. **quad + GLTF.** Processing says a convert step with `quad=true, format=GLTF` is blocked. Platform and generation say generation `quad=true` followed by `--then convert:gltf` passes. Both are true. The skill needs its own cross-step check, including decimate v2.0 `quad` followed by a GLTF convert.
10. **The bundled LOD recipe is wrong** (`@last` after a chain; see B2). The `--for game-pc --then decimate` example also drops the scenario's FBX convert.
11. **`-p model=` hazard vs rig advice.** The animation note recommends `tripo anim rig ... -p model=v3.0-20260909` on the direct command. The platform note shows that `-p model=` on `make` silently overrides the model and skips validation. The direct-command behaviour cannot be dry-run. Prefer `make @name --then rig:model=...` for validation.
12. **Tripo forward axis.** Tripo's `+x` default vs glTF/Godot `+Z` is unverified. Prior art measured "most outputs face +X, about 10 % do not". Orientation must be confirmed from a render (A5), not computed.
13. **Unknown texture resolution** for `standard` and `detailed` blocks texel-density planning before generation. Measure it from the 50 local outputs instead of leaving it UNKNOWN.
14. **The animation budget line** "rig + 1 animation uses the entire balance" leaves out generation. Read honestly, the Tripo animation pipeline is unaffordable on the current balance.
15. **`--for game-mobile`** (P1, face_limit 15000, 2K textures) is presented as a mobile recipe, but it exceeds the mobile prop budgets in the polycount note by 5–20×.
16. **`tripo make <file>` vs direct commands.** `make` adds an import task of unknown cost; direct commands upload without import but have no dry-run. Neither note gives a policy. Suggested: dry-run with `make`, and run the direct command only when the import cost matters and the payload has been verified.
17. **Legacy statuses and processing input types.** Whether every processing endpoint accepts every model-producing task id is UNKNOWN. The skill relies on `decimate → uv` and `rig → convert` chains, so those two should be verified first with a cheap real run once credits allow.
18. **Measured vs documented decimate.** decimate v2.0 `face_limit=20000` produced 29,943 tris, above the documented 20k maximum. Budget checks must allow for this.

---

## F. Questions only the user can answer
1. Target platform(s) and Godot renderer for the first project? Is the skill Godot-only, or should Unity/Unreal export stay as stubs?
2. Credits: will you top up, and to what monthly budget? Or should the skill assume about 35 and run mostly local?
3. Animation route: Tripo retarget (10 per clip), or a Tripo rig plus free clip libraries retargeted in Godot? Which libraries are acceptable licence-wise?
4. Concept images: Higgsfield (your global rule), Tripo t2i/multiview, or Gemini (PATINA)? And how should "three-quarter view, single image" be reconciled with Tripo multiview's required front view?
5. Should the skill install a PreToolUse hook that hard-blocks non-dry-run `tripo` commands until you approve a priced plan?
6. Default fix location: a Blender-modified GLB (GRIME) or an untouched GLB plus engine-side fixes (PATINA)?
7. May the skill read the 50 existing GRIME `tripo-out` downloads as a calibration and test corpus (read-only)?
8. Upgrade tripo-cli 0.6.1 → 0.8.0+ to unlock texture v3.5 / `delight`? This changes verified behaviour.
9. Have you read Tripo's commercial and ownership terms for API-generated assets? Should the skill keep a licence row per asset?
10. Rig defaults: T-pose (docs) or A-pose (measured pass in GRIME)? Rig v3.0 (docs) or v2.5 (proven)?
11. Editability depth: is a `.blend` source with re-export script enough, or do you want quad topology for some asset classes (costs credits or quality)?
12. Lesson and report language: English, with Turkish user-facing summaries?
