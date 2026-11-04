# Rigging and animation: rig-check, rig, retarget, Godot BoneMap

When to read this: phase 7 (rig + animation), for characters and anything else that must deform; also in phase 3 when the reference shows a character.

## 1. Order (B18)

```
generation -> paid Tripo fixes -> Blender geometry fixes + normalize -> budget (decimate)
  -> clean GLB -> rig-check (free on a task; a file adds a paid import) -> rig (25) -> animations (10 each) -> Godot rig check
```

- Rig is the only cloud step that comes after local fixes: skinning must happen on the final mesh. Decimate to the budget before rigging.
- After rig, geometry is frozen: only materials and names may change. `apply_recipe.py` and `normalize.py` refuse rigged inputs (exit 2).
- The prior rigged worker kept its topology unchanged (7884 triangles before and after cleanup).
- The rig output carries a stray `Icosphere*` helper mesh: drop that object, keep the armature, the skin and every transform as they are.

## 2. Pose before generation (B6)

Default: **A-pose**, arms about 40 degrees from the body, elbows slightly bent, hands open and empty, legs slightly apart, clear gaps between arms, torso and legs. The user's only rig that passed was such an A-pose model; the first model failed because a lance was fused to the hands and torso. Tripo's docs and CLI suggest a T-pose instead, and Godot's humanoid profile uses a T-pose as its reference. Which pose rigs better on Tripo is an open question for the first paid run (compare, then record a lesson). Held props are always separate models attached in the engine. The image checks are in `image-preflight.md` items 6 and 7.

## 3. rig-check (free on a task, its own command; a file input adds a paid import)

Step: `{"kind": "rig_check", "label": "<asset>-rig_check-vNN", "input": {"file": "export/<asset>.glb"}}` (or `{"task": "@<label>"}` when the model was not edited locally).

<!-- unverified -->
```bash
tripo make export/worker.glb --then rig-check --name worker-rig_check-v01
```

- Returns `riggable` (true/false) and `rig_type` (`biped`, `quadruped`, `hexapod`, `octopod`, `avian`, `serpentine`, `aquatic`). It never returns `others`.
- The verdict is not stored in `task.json`: read it from the command's JSON output and write it into the asset state.
- A file input adds an import task (price not published; it also normalizes scale): the step is paid (`paid: true`), the lock window says "tahmin yok". Verified with a free dry-run on 0.9.0: `make <glb> --then rig-check` plans `import` + `rig-check`.
- Import only once. After a rig-check on a file, chain `rig` from that import task (`"input": {"task": "@<asset>-rig_check-vNN"}`; plain `@<name>` is the import, `@<name>-rig-check` the check) instead of the file, so the model is not imported and paid for twice.
- tripo-cli 0.9.0 also has `tripo anim check <glb>`, which uploads the file and runs rig-check with no import task. `tripo_plan.py` does not build it, so the skill does not use it (hard rule 1: steps come from the planner).
- `riggable: false`: stop and say why in one line. Usually a prop or the arms are fused to the body. Offer the image fix (A-pose, empty hands, prompt in `image-preflight.md` item 7) and a regeneration (counts toward the cap of 2). `rig_type=others` on rig v3.0 is untested for unriggable models.

## 4. rig (25 credits, plus the import when the input is a file)

Step: `{"kind": "rig", "label": "<asset>-rig-vNN", "input": {"file": "export/<asset>.glb"}, "model": "v3.0", "params": {"rig_type": "<from rig-check>", "spec": "mixamo"}}`

After a rig-check on the file, use `"input": {"task": "@<asset>-rig_check-vNN"}` (the import task) instead of the file: one import, not two.

<!-- unverified -->
```bash
tripo make export/worker.glb --then "rig:model=v3.0;spec=mixamo;rig_type=biped" --name worker-rig-v01
```

- `model`: `v3.0` (wire `v3.0-20260909`), the docs' recommendation for humanoids (B6). Since 0.10.0 an omitted rig model resolves after rig-check (quadruped `v2.5-20260210`, every other body `v3.0`); `tripo_plan.py` still requires an explicit model. `v2.5` is for creatures; `v1.0` is biped-only but carries the large preset library (section 6).
- `rig_type`: copy rig-check's answer; never force another one.
- `spec` (bone naming, applies to `biped` only): `tripo`, `mixamo`, `actorcore`, `unity`, `unreal`, `vrm`. Tripo's docs do not mention Godot. **Godot default: `mixamo`, to verify on the first paid run** (does Godot's BoneMap auto-map it?). Record the result as a lesson and in `profile.json` `pinned.rig_model`.
- Output format: GLB (the default `out_format`), which Godot imports directly.
- After the run: `python3 scripts/glbstat.py` (skins, joints, animations), then `qa.py` (`TOO_MANY_INFLUENCES`), then the Godot rig check (section 7).

## 5. Tripo bone names

- With the `tripo` naming the prior rig had 27 joints and no animations: `tripo::Root`, `tripo::Spine_0`, `tripo::Head_0..2`, `tripo::1_Right_Limb_0..2` (arms), `tripo::0_*_Limb_0..3` (legs) and unnamed `bone_4`, `bone_8`, `bone_20..26`. This is neither Mixamo nor Godot humanoid naming.
- Godot renames `::` to `__` on import: game code refers to `tripo__1_Right_Limb_0`, not `tripo::1_Right_Limb_0`. Bone attachments and scripts must use the Godot spelling.
- Mixamo naming has no root bone; Godot root motion needs one. Check `single_root` in the Godot rig check.

BoneMap for a `spec=tripo` biped onto `SkeletonProfileHumanoid` (Godot spelling; verified headless on grime-does-pay `crew_worker`, rig v2.5-20260210, 2026-11-03: a T-pose source clip raised the left arm and swung the right leg forward on the worker exactly as on the source):

| profile | Tripo bone | note |
|---|---|---|
| Hips | `tripo__Root` | its rest sits on the ground and carries no weights; there is no pelvis bone |
| Spine | `tripo__Head_0` | the torso, despite the name |
| Neck / Head | `tripo__Head_1` / `tripo__Head_2` | |
| LeftShoulder / RightShoulder | `bone_8` / `bone_4` | clavicles; the arms hang off them |
| Left/Right UpperArm, LowerArm, Hand | `tripo__1_<Side>_Limb_0`, `_1`, `_2` | |
| Left/Right UpperLeg, LowerLeg, Foot, Toes | `tripo__0_<Side>_Limb_0`, `_1`, `_2`, `_3` | |
| (unmapped) | `tripo__Spine_0`, `bone_20` to `bone_26` | childless pelvis and torso helpers parented to the root; they follow the hips |

- Chest and UpperChest stay empty (optional in the profile); every required profile bone is mapped.
- The hips rest on the ground, so Normalize Position Tracks scales hip position tracks by about 0: rotations retarget correctly, but hip bob and root motion from a clip are expected to be nearly flat (untested).

## 6. Animation question (K9, B16)

Ask every time a rig is done, once, with both routes and their cost. Suggested wording (Turkish):

> Rig tamam. Animasyon nasıl olsun?
> 1. Tripo retarget: animasyon başına 10 kredi, hazır listeden (idle, walk, run, jump, climb, dive, slash, shoot, hurt, fall, turn).
> 2. Godot'da kendi ya da ücretsiz kliplerini BoneMap ile uyarla: 0 kredi.
> Hangisi, hangi animasyonlar?

- Presets for a v3.0 (or v2.5) rig: biped `preset:idle`, `preset:walk`, `preset:run`, `preset:dive`, `preset:climb`, `preset:jump`, `preset:slash`, `preset:shoot`, `preset:hurt`, `preset:fall`, `preset:turn`; creatures `preset:quadruped:walk`, `preset:hexapod:walk`, `preset:octopod:walk`, `preset:serpentine:march`, `preset:aquatic:march`. None are listed for `avian` or `others`.
- The 101 `preset:biped:*` animations (emotes, dances, sports, combat) belong to rig `v1.0` only. Whether they work on a v3.0 rig is unknown: assume not. If the user needs them, the choice is made before the rig step.
- The CLI does not validate preset names: a typo fails only on the server. Copy names from this list.

### Tripo retarget (10 per animation)

One animation per command (one paid step, one price per window; `--then` cannot carry a list):

<!-- unverified -->
```bash
tripo make @worker-rig-v01-rig --then retarget:animation=preset:walk --name worker-retarget-v01
```

- The input must be the rig task (`@<label>-rig`), never a file (error 2012 otherwise).
- `animate_in_place=true` when game code moves the character (no root motion).
- Clip names, frame rate, looping and how several clips are packaged are not documented: inspect the first result with `glbstat.py` (`animations`) and record a lesson.

### Godot BoneMap retarget (0 credits)

Godot 4 retargets humanoid clips through a `BoneMap` onto `SkeletonProfileHumanoid` in the scene importer (Advanced Import Settings, select the Skeleton3D, Retarget).

- Auto-mapping matches common English bone names; missing, duplicate or badly parented bones show red or magenta. They do not block the import, but the animations will not share correctly.
- Reference pose: T-pose, facing +Z, Y up, no transform on the root node. **Check the facing first:** the `crew_worker` rig faced +X, and Fix Silhouette then opened its arms forward and backward instead of sideways. Rotate the model to face +Z in Blender (rotate and apply on the armature and its meshes, 0 credits) before retargeting.
- Rest Fixer options: **Fix Silhouette** for A-pose models (filter the feet out if needed); **Overwrite Axis** is the key option for sharing animations (it can damage models whose own bone rest matters); **Normalize Position Tracks** stores `motion_scale` from the hips height (less foot sliding); **Apply Node Transform** fixes exports that skipped Apply Transform.
- Remove Tracks, **Unimportant Positions**: keeps position tracks only on root and hips; on for shared animation libraries.
- **Unique Node** on the skeleton keeps track paths working when the hierarchy changes.
- Name looping clips with a `-loop` suffix (start or end of the clip name).
- Godot's BoneMapper auto-mapping is editor-only: the headless check below cannot run it. A hand-written `BoneMap` resource does apply headless: set it in the GLB's `.import` `_subresources` under `"nodes": {"PATH:<path to Skeleton3D>": {"retarget/bone_map": Resource("res://<map>.tres"), "retarget/rest_fixer/fix_silhouette/enable": true}}` and run `godot --headless --import` (delete the cached import first: Godot does not reimport when only the map changed). The skeleton is renamed to `GeneralSkeleton` and its bones to profile names.

## 7. Godot rig acceptance (headless, 0 credits)

```
python3 scripts/godot_place.py rig_accept <project> export/worker_rigged.glb
```

- Output: `skeletons`, `bones`, `single_root`, `max_influences`, `animations`, `bonemap_auto`, `verdict`, `reasons`.
- `verdict: fail` (exit 5) when the skeleton count is not 1, the skeleton has more than one root bone, or a vertex has more than 4 influences.
- `bonemap_auto` is a name heuristic against `SkeletonProfileHumanoid`, not the editor's BoneMapper. It is reported, never judged: a low count is not a failed rig. The prior `tripo::` rig maps 3 of 56 profile bones. Until the first paid rig run settles `spec`, retarget through the editor BoneMap path and look at the red bones there.
- Textures are discarded for this check (embedded textures crash Godot 4.7.2 headless).

## 8. Costs at a glance

| step | credits |
|---|---|
| rig-check | 0 on a task (+ import, unknown, for a file input) |
| rig | 25 (+ import, unknown, for a file input) |
| retarget | 10 per animation |
| Smart UV after rig (keeps rig and animation) | 20 |
| example: rig + idle + walk + run | 25 + 30 = 55 |

## 9. Open until the first paid rig runs (record each as a lesson)

A-pose vs T-pose on rig-check and rig; `spec=mixamo` (or another spec) against Godot's BoneMap (`spec=tripo` has the verified hand map in section 5, so mixamo is only worth its 25 credits for Mixamo clips); bone count, influences and scale of the v3.0 output; clip names and packaging of retarget output; the import price of a file input.
