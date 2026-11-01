"""Apply a fix recipe to the raw model: a reproducible, editable work version (spec 13).

    bl.py apply_recipe.py -- <recipe.json> --work <dir>

recipe.json: {"schema": "recipe/1", "asset": "<name>", "source": "<raw model path>",
              "steps": [{"op": "<fixkit op>", "params": {...}}, ...]}
`source` may be relative to the recipe file. Ops and params: scripts/blender/fixkit/ops.py
(lengths and regions are bbox fractions, never metres).

-> {"version": "vNN", "blend", "glb", "qa_dir", "steps": [{"op", "result"}], "tris", "bbox":
    {"min", "max", "size"}, "normals": {"kept", "rebuilt"}}

`qa_dir` is where this version's QA goes: <work>/../qa/vNN, the same vNN as the work file
(qa/raw holds the raw model's QA). It is named, not created.

Always starts again from the raw model, so the same recipe on the same raw gives the same
result; each run writes the next free version: <work>/vNN.blend (images packed, editable)
and <work>/vNN.glb (the Godot export settings of export.py). The whole recipe runs inside
one NormalKeeper per mesh (B7). Rigged inputs are refused (exit 2): geometry is not touched
after rigging (B18). A bad recipe (unknown op or param, wrong order, an op that needs a
weld before it) exits 2 and writes nothing; a missing recipe or source exits 3.
"""
import contextlib
import json
import os
import re
import sys

import bpy

import _mesh
import export
import skill_io as sio
from fixkit import ops

EXIT_USAGE = 2
SCHEMA = "recipe/1"
VERSION_RE = re.compile(r"v(\d{2,})\.(?:blend|glb)\Z")


def _usage(msg: str):
    print(f"usage error: {msg}", file=sys.stderr)
    sys.stderr.flush()
    raise SystemExit(EXIT_USAGE)


def load_recipe(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"recipe not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            recipe = json.load(f)
    except ValueError as e:
        _usage(f"recipe is not valid JSON: {e}")
    if not isinstance(recipe, dict) or recipe.get("schema") != SCHEMA:
        _usage(f"recipe schema must be {SCHEMA!r}")
    for key in ("asset", "source"):
        if not isinstance(recipe.get(key), str) or not recipe[key]:
            _usage(f"recipe needs a non-empty string {key!r}")
    if not ops.NAME_RE.match(recipe["asset"]):
        _usage(f"asset must be letters, digits, '_' or '-', got {recipe['asset']!r}")
    try:
        ops.check_steps(recipe.get("steps"))
    except ops.RecipeError as e:
        _usage(str(e))
    return recipe


def next_version(work: str) -> str:
    taken = [int(m.group(1)) for m in map(VERSION_RE.match, os.listdir(work)) if m]
    return f"v{max(taken, default=0) + 1:02d}"


def prepare(objs) -> list:
    """The model's meshes, unparented (world kept), own data; everything else removed."""
    if any(o.type == "ARMATURE" for o in objs):
        _usage("rigged model: geometry is not edited after rigging (B18)")
    meshes = _mesh.model_meshes(objs)
    if not meshes:
        _usage("no mesh objects in the source model")
    for o in meshes:                                   # instanced data would be edited twice
        if o.data.users > 1:
            o.data = o.data.copy()
    bpy.context.view_layer.update()
    for o in meshes:
        world = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = world
    for o in list(bpy.data.objects):
        if o not in meshes:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    return meshes


def pack_images() -> None:
    for img in bpy.data.images:
        if img.type == "IMAGE" and img.packed_file is None and img.filepath:
            img.pack()


def cfg(p):
    p.add_argument("recipe")
    p.add_argument("--work", required=True)


def run(a):
    recipe_path = os.path.abspath(a.recipe)
    recipe = load_recipe(recipe_path)
    base = os.path.dirname(recipe_path)
    source = os.path.join(base, os.path.expanduser(recipe["source"]))
    objs = sio.load_model(source)
    ctx = ops.Ctx(prepare(objs), recipe["asset"], base)
    steps = []
    try:
        with contextlib.ExitStack() as stack:
            ctx.open(stack)
            for step in recipe["steps"]:
                result = ops.run_step(ctx, step["op"], step.get("params", {}))
                steps.append({"op": step["op"], "result": result})
        ctx.finalize()
    except ops.RecipeError as e:
        _usage(str(e))

    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    version = next_version(work)
    blend = os.path.join(work, f"{version}.blend")
    glb = os.path.join(work, f"{version}.glb")
    pack_images()
    lo, hi = _mesh.world_bbox(ctx.meshes)
    tris = ops.tri_count(ctx.meshes)
    bpy.ops.wm.save_as_mainfile(filepath=blend, copy=True)
    export.export_model(glb, "godot")
    qa_dir = os.path.join(os.path.dirname(work), "qa", version)
    return {"version": version, "blend": blend, "glb": glb, "qa_dir": qa_dir, "steps": steps,
            "tris": tris,
            "bbox": {"min": lo.tolist(), "max": hi.tolist(), "size": (hi - lo).tolist()},
            "normals": ctx.normal_stats()}


if __name__ == "__main__":
    sio.main(run, cfg)
