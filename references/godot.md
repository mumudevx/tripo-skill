# Godot adapter: measure the placeholder, import, place, check

When to read this: phase 2 (pick the placeholder, measure it) and phase 8 (import into Godot and swap the placeholder); also when profile setup asks about naming or placement mode.

Everything goes through `scripts/godot_place.py`. It prints one JSON line; exit 3 names what is missing (profile, placeholder, scene, node, GLB), exit 5 means a check or a refusal. Godot binary: `--godot`, else `$GODOT`, else `profile.json` `engine.binary` (a project's `scripts/godot_bin.sh` pin is detected into it), else what `profile.py` finds. Windowed Godot runs must never steal focus; the skill only runs Godot headless.

## 1. Measure the placeholder (phase 2)

```
python3 scripts/godot_place.py aabb <project> res://scenes/main.tscn Crate
```

- Output: `size`, `center`, `bottom_center`, `yaw_deg`, `normalize_target_size`, plus the local values the swap needs (`scale`, `local_position`, `local_size`, `local_bottom_center`, `node_type`).
- Measured headless by `scripts/godot/aabb.gd`: the scene is instantiated but never added to the tree, so no game `_ready` code runs, and nothing is written into the project.
- Bounds merge the node's own visual AABB with its visible visual descendants, in the node's own axes; `size` is that local size times the global scale.
- Store the placeholder in the asset state: `asset_state.py update <project> <id> --set placeholder='{"scene": "res://...", "node": "..."}'`.

## 2. The frame rule (Godot Y up, Blender Z up)

- Godot sizes are `(gx, gy, gz)` with Y up. `normalize.py --target-size` takes Blender axes with Z up, so the same box is `(gx, gz, gy)`. The glTF exporter maps Blender `(x, y, z)` to Godot `(x, z, -y)`.
- `aabb` already gives the swizzled value as `normalize_target_size`. **Pass that one, never the raw `size`.** A raw size swaps height and depth (a crate 0.5 tall read as 0.8 deep) and the uniform fit then mis-scales the model.
- A +Z yaw in Blender is the same +Y yaw in Godot. `--pivot bottom_center` (min z = 0 in Blender) lands as min y = 0 in Godot.
- Front: glTF and Godot assets face +Z; in Blender that is -Y. `normalize.py --yaw` turns the model so its confirmed front (`qa-checklist.md` section 2) faces -Y before export.

```
python3 scripts/bl.py normalize.py -- work/v03.glb --out-model export/crate.glb --yaw -90 --target-size <normalize_target_size> --pivot bottom_center --name crate
```

- Write `normalize_target_size` as `X,Y,Z` (the Crate fixture's `[1, 0.8, 0.5]` becomes `--target-size 1,0.8,0.5`).
- The scale is uniform, never per axis: the axis with the largest size/target ratio decides, so the model fits inside the placeholder box. `--target-height H` fits the height instead.
- `normalize.py` refuses a rigged input: normalize before rigging.
- Output includes `bbox`, `scale_applied`, `yaw`, `offset`, `renamed`, `tris`, `weld` and `normals` (`kept`/`rebuilt`).

## 3. Plan, show, apply (K6)

```
python3 scripts/godot_place.py plan <project> <project>/.claude/tripo/assets/crate.json export/crate.glb
python3 scripts/godot_place.py apply <project> <project>/.claude/tripo/assets/crate.json export/crate.glb --expect <plan_sha256>
```

- `plan` writes nothing. It returns `copy_to` (from `profile.json` `naming.root` + `naming.model_pattern`, or `--copy-to`), `copy_to_exists` and `copy_to_sha256` (a file already at `copy_to`), `import_params`, `scene_diff` (unified diff), `before_after` (size, position, yaw of placeholder vs model, plus `normalize_target_size`), `warnings` and `plan_sha256`. Size warnings: a model that is not yet fitted gets the hint `normalize.py --target-size X,Y,Z` (commas, as normalize.py takes it); a model that already fills the placeholder on one axis gets both aspect ratios instead (a uniform fit cannot fill a box of another shape: accept the smaller footprint, fit by height, or resize the placeholder). Every kept `CollisionShape3D` that no longer fits the model (more than 25% larger, or smaller, on an axis) is named in a warning; the swap never changes it. A different file already at `copy_to` gets the warning "var olan dosyanın üzerine yazılacak": `apply` would replace it and nothing rolls back; show it in the approval message, or pass `--copy-to` to keep the old file.
- Show the user the diff and the before/after table (Turkish lines around it), then ask once for approval. Warnings to relay: an existing file at `copy_to` will be overwritten; the model size differs from the placeholder by a large margin; the model's base centre is not at its origin; a NodePath or a game script may name a renamed child.
- `apply --expect <plan_sha256>` recomputes the plan and refuses (exit 5, nothing written) when it no longer matches: the scene, the model or the file at `copy_to` changed since the user saw the diff. `--expect` is required: a bare `apply` is a usage error (exit 2).
- Then `apply` copies the GLB, writes the `.import` params, writes the scene, runs `godot --headless --import`, and every `profile.json` `check_commands` entry from the project root.
- **No rollback.** On a failed import or check, `apply` exits 5 with `step`, the output `tail` and `written` (the files it changed). Show those, fix the cause, and re-run `apply` (it is idempotent); or restore the listed files with git.
- Any non-zero exit or any line starting with `ERROR:` or `SCRIPT ERROR:` from Godot is a failure, as strict as the projects' own `scripts/check_import.sh` (which also matches `Parse Error`). A fresh clone that was never opened in the editor (no `.godot/global_script_class_cache.cfg`) can report class-cache errors once; the projects' own check script primes a first import, `godot_place.py` does not. Re-running `apply` after one import usually clears it.

## 4. What the swap does (`placement_mode: scene_swap`)

Only the visual part changes; scene path, root name, unique_id, script, transform, collision and socket children stay. Nothing is deleted.

1. **MeshInstance3D placeholder** (a primitive mesh on the node itself): the node keeps its name, path, type, unique_id, script and children. Its `mesh`, `skin`, `skeleton` and material overrides move to a new hidden child `<name>_placeholder` (the backup), and the model is added as a child scene instance `Model`.
2. **Container placeholder** (a Node3D whose direct children are the primitive meshes): each direct visual child is renamed `<child>_placeholder`, hidden, and keeps its unique_id. Descendants' `parent=` paths and `[connection]` entries are rewritten; a NodePath that may point at a renamed child produces a warning to check by hand, and so does every project `.gd` line that reaches a renamed child by name (`$Seat`, `$Body/Seat`, `get_node("Seat")`, `%Seat`; file and line listed). Show it with the diff: the script needs a change too, or the lookup fails after the swap.
3. `Model` is placed so that the GLB's base centre sits on the placeholder's local base centre, and it counter-scales a scaled placeholder.
4. **Refusals** (exit 5, nothing written): the placeholder is itself an instanced scene; a `Model` child already exists and points at another file; a `*_placeholder` name already exists. A `Model` child that already points at `copy_to` is an idempotent re-place: no scene change, an "already" warning.
5. New unique_ids are deterministic and collision-free; none are invented when the scene uses none.

## 5. Generator-script projects (`placement_mode: generator_script`, B19)

Some projects never hand-edit `.tscn` files: `scripts/dev/generate_*_models.gd` builds them. For those:

- `plan` returns `scene_diff: null` and `generator_hint`: `{file, symbols: [{line, text}], candidates}`, the generator file and the lines that name this scene, its constant, the asset id or the model file stem.
- The agent edits the generator itself (asset path, scale, yaw values), shows that diff, and asks for approval.
- `apply` then copies the GLB, writes the import params, imports, runs the generator, then the checks. It never touches a scene.
- Fixes still go into the GLB through Blender (K12 holds here too).

## 6. Import settings written into `<model>.glb.import`

| param | value | why |
|---|---|---|
| `gltf/embedded_image_handling` | 1 (Extract Textures) | editable textures; Godot extracts them as `<glb>_<image>` |
| `meshes/ensure_tangents` | true | MikkTSpace tangents for normal maps |
| `meshes/generate_lods` | true | automatic LODs (section 8) |
| `nodes/apply_root_scale` | true | scale baked into meshes, root stays (1, 1, 1) |

Other params already in the file are kept.

## 7. Naming

- From `profile.json`: `naming.model_pattern` (e.g. `{id}.glb`, or `{id}_{class}.glb`) under `naming.root` (default `paths.models`). Only the placeholders `{id}` and `{class}` exist.
- A pattern with any other placeholder (for example a zone, as in `obj_<zone>_<id>`) has no source: `plan` exits 2. Pass `--copy-to <res-relative path>` by hand for such projects.
- Root node, materials and textures carry the asset name (`normalize.py --name <asset>` renames root, objects, meshes, materials and images).
- Names: ASCII, no spaces, no dots. Watch for accidental Godot import hints at the end of object names (`-col`, `-colonly`, `-convcol`, `-convcolonly`, `-noimp`, `-navmesh`, `-rigid`, ...; matched case-insensitively, separators `-`, `_` or `$`), material names (`-alpha`, `-vcol`) and clip names (`loop`/`cycle` at the start or end).

## 8. LOD, collision, glass

- **LOD**: static assets get Godot's automatic LODs on import (meshoptimizer; each step about half the triangles; the chain length depends on the mesh, and it stops when a step saves under 25%). Open edges and many UV islands limit how far it can go, which is one more reason to weld and clean in Blender. Skinned meshes are the known weak spot: if a rigged model looks broken at a distance, disable LOD generation for that mesh and make LODs by hand if needed. Tripo credits are spent on LOD0 only.
- **Collision** lives in the engine. Cheapest first: primitives (box, sphere, capsule; required for dynamic bodies), one convex hull, several convex hulls, trimesh (static bodies only). The collision shape is a separate, simpler shape, never the render mesh for anything but static level geometry. Options: import hint suffixes on a separate collision mesh (`-colonly` trimesh, `-convcolonly` convex decomposition), or the editor's Mesh menu (single convex, multiple convex, trimesh static body). A character's capsule is a `CharacterBody3D` + `CapsuleShape3D` sized from the model's bounds, never part of the model file. An existing placeholder's collision stays as it is; `godot_place.py plan` warns, naming the node, when it no longer fits the new model's size. Resize it by hand after placement.
- **Glass and transparency**: a Godot material (or shader) decision, never a mesh fix. Tripo paints glass as an opaque surface; a shader that reads the painted area as glass is one way, a separate glass mesh another.

## 9. After placement

- `log_asset.py <project> <asset.json> --glb <export glb>` writes `provenance.json` next to the raw files and appends one row to the project's `asset_log` in its own format (B14). With `asset_log_format: none` it stops with `create_needed: true`; ask once, then `--create`.
- `asset_state.py update <project> <id> --phase place`.
- Look at the result once in the game camera if the user wants; never open a window that steals focus.
