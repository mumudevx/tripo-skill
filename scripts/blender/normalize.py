"""Normalize a model for the game: weld, yaw, uniform scale, pivot, names; normals kept.

    bl.py normalize.py -- <in> --out-model <out.glb> [--yaw DEG]
                          [--target-size X,Y,Z | --target-height H]
                          [--pivot bottom_center|center] [--name <asset>]

-> {"out_model", "bbox": {"min", "max", "size"}, "scale_applied", "yaw", "pivot",
    "renamed": {"root", "objects", "meshes", "materials", "images"} ("root": the root
    node's name; the others {old: new}; {} without --name), "offset", "tris", "weld": {"eps", "verts_before", "verts_after"},
    "normals": {"kept", "rebuilt"}}

Order: weld (1e-5 x bbox diagonal, _mesh.weld_eps) -> yaw -> uniform scale to fit the
target -> pivot -> apply transforms -> rename -> export GLB. Everything that touches
geometry runs inside one fixkit NormalKeeper per mesh, so Tripo's normals survive (B7).

Frame (Blender, Z up; same as qa.py): `--yaw` turns the model DEG degrees about +Z,
counter-clockwise seen from above. `--target-size X,Y,Z` is in Blender axes; a Godot size
(gx, gy, gz) is (gx, gz, gy) here. The scale is uniform, never per axis: with
--target-size the axis with the largest size/target ratio decides (the model fits inside
the box); with --target-height the Z size does. No target: scale 1. `--pivot
bottom_center` (default) puts the origin at the bbox bottom centre, `center` at the bbox
centre. `offset` is the translation applied after yaw and scale.

Input: GLB/GLTF/FBX/OBJ (by magic bytes). Rigged inputs are refused (exit 2): normalize
runs before rigging. Output is always GLB, written atomically; a stale --out-model is
removed first.
"""
import argparse
import contextlib
import math
import os
import re
import sys

import bpy
import numpy as np
from mathutils import Matrix

import _mesh
import skill_io as sio
from fixkit import normals

EXIT_USAGE = 2
NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*\Z")


def _usage(msg: str):
    print(f"usage error: {msg}", file=sys.stderr)
    sys.stderr.flush()
    raise SystemExit(EXIT_USAGE)


def _positive(text: str) -> float:
    try:
        v = float(text)
    except ValueError:
        v = float("nan")
    if not (v > 0 and math.isfinite(v)):
        raise argparse.ArgumentTypeError(f"expected a positive number, got {text!r}")
    return v


def _size3(text: str) -> tuple:
    parts = text.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"--target-size must be X,Y,Z, got {text!r}")
    return tuple(_positive(p) for p in parts)


def _glb_path(text: str) -> str:
    if not text.lower().endswith(".glb"):
        raise argparse.ArgumentTypeError(f"--out-model must end in .glb, got {text!r}")
    return text


def _asset_name(text: str) -> str:
    if not NAME_RE.match(text):
        raise argparse.ArgumentTypeError(
            f"--name must be letters, digits, '_' or '-' (no dots or slashes), got {text!r}")
    return text


def yaw_matrix(deg: float) -> np.ndarray:
    t = math.radians(deg)
    m = np.eye(4)
    m[:2, :2] = [[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]]
    return m


def fit_scale(size, target_size=None, target_height=None) -> float:
    """Uniform scale: the largest size/target ratio decides; 1.0 without a target."""
    if target_height is not None:
        if size[2] <= 0:
            raise ValueError("model has no height; cannot fit --target-height")
        return float(target_height / size[2])
    if target_size is not None:
        ratios = [s / t for s, t in zip(size, target_size) if s > 0]
        if not ratios:
            raise ValueError("model has zero size; cannot fit --target-size")
        return float(1.0 / max(ratios))
    return 1.0


def normalize_meshes(meshes, keepers, eps, yaw=0.0, target_size=None, target_height=None,
                     pivot="bottom_center") -> dict:
    """Weld, yaw, scale, pivot and apply transforms on `meshes` (in place).

    `keepers` maps each mesh object's name to its open NormalKeeper; every move goes
    through keeper.transform() so stored normals follow. `eps` is the world weld distance.
    Afterwards every mesh has an identity transform and no parent.
    """
    verts_before = sum(len(o.data.vertices) for o in meshes)
    for o in meshes:                                   # weld, in mesh space
        bm = _mesh.welded_bmesh(o, eps, world=False)
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()
    verts_after = sum(len(o.data.vertices) for o in meshes)

    co = np.concatenate([_mesh.world_coords(o) for o in meshes])
    rot = yaw_matrix(yaw)
    co = co @ rot[:3, :3].T
    scale = fit_scale(co.max(0) - co.min(0), target_size, target_height)
    co = co * scale
    lo, hi = co.min(0), co.max(0)
    mid = (lo + hi) / 2
    offset = -np.array([mid[0], mid[1], lo[2] if pivot == "bottom_center" else mid[2]])
    move = np.eye(4)
    move[:3, :3] = np.eye(3) * scale
    move[:3, 3] = offset
    move = move @ rot

    worlds = {o.name: np.array(o.matrix_world, np.float64) for o in meshes}
    for o in meshes:                                   # apply transforms
        keepers[o.name].transform(Matrix((move @ worlds[o.name]).tolist()))
        o.parent = None
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    return {"yaw": float(yaw), "scale_applied": scale, "pivot": pivot,
            "offset": [float(x) for x in offset],
            "weld": {"eps": eps, "verts_before": verts_before, "verts_after": verts_after}}


def _model_images(materials) -> list:
    seen = []
    for m in materials:
        if not m.node_tree:
            continue
        for node in m.node_tree.nodes:
            img = getattr(node, "image", None) if node.type == "TEX_IMAGE" else None
            if img is not None and img not in seen:
                seen.append(img)
    return seen


def _numbered(asset: str, i: int) -> str:
    return asset if i == 0 else f"{asset}_{i + 1:02d}"


def rename(meshes, asset: str) -> dict:
    """Name root, meshes, materials and images after `asset`.

    Returns {"root": name, kind: {old: new}} for objects, meshes, materials, images.

    One mesh: object and mesh data are `<asset>`. Several: an empty root `<asset>` with
    children `<asset>_part_NN`. Materials and images (in first-use order): `<asset>`,
    then `<asset>_02`, `<asset>_03`, ...
    """
    materials = []
    for o in meshes:
        for slot in o.material_slots:
            if slot.material is not None and slot.material not in materials:
                materials.append(slot.material)
    images = _model_images(materials)
    if len(meshes) == 1:
        objects = [(meshes[0], asset)]
        datas = [(meshes[0].data, asset)]
    else:
        root = bpy.data.objects.new(asset, None)
        bpy.context.scene.collection.objects.link(root)
        names = [f"{asset}_part_{i + 1:02d}" for i in range(len(meshes))]
        objects = [(o, n) for o, n in zip(meshes, names)]
        datas = [(o.data, n) for o, n in zip(meshes, names)]
        for o in meshes:
            o.parent = root
    plan = {"objects": objects, "meshes": datas,
            "materials": [(m, _numbered(asset, i)) for i, m in enumerate(materials)],
            "images": [(img, _numbered(asset, i)) for i, img in enumerate(images)]}
    out = {}
    for kind, pairs in plan.items():
        old = [blk.name for blk, _ in pairs]
        for i, (blk, _) in enumerate(pairs):           # two passes: no clash among them
            blk.name = f"__normalize_tmp_{i}"
        for blk, new in pairs:
            blk.name = new
        out[kind] = {o: blk.name for o, (blk, _) in zip(old, pairs)}
    out["root"] = (root if len(meshes) > 1 else meshes[0]).name
    return out


def export_glb(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = os.path.splitext(path)[0] + ".part.glb"
    try:
        bpy.ops.export_scene.gltf(filepath=tmp, export_format="GLB", export_yup=True,
                                  use_selection=False, export_apply=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def cfg(p):
    p.add_argument("model")
    p.add_argument("--out-model", required=True, type=_glb_path)
    p.add_argument("--yaw", type=float, default=0.0)
    fit = p.add_mutually_exclusive_group()
    fit.add_argument("--target-size", type=_size3)
    fit.add_argument("--target-height", type=_positive)
    p.add_argument("--pivot", choices=("bottom_center", "center"), default="bottom_center")
    p.add_argument("--name", type=_asset_name)


def run(a):
    out_model = os.path.abspath(a.out_model)
    if os.path.exists(out_model):  # a stale model must never pass for this run's result
        os.unlink(out_model)
    if not math.isfinite(a.yaw):
        _usage(f"--yaw must be a finite number, got {a.yaw}")
    objs = sio.load_model(a.model)
    if any(o.type == "ARMATURE" for o in objs):
        _usage("rigged model: normalize runs before rigging (weld/scale would break the skin)")
    meshes = _mesh.model_meshes(objs)
    if not meshes:
        raise ValueError(f"no mesh objects in {a.model}")
    for o in meshes:                                   # instanced data would move twice
        if o.data.users > 1:
            o.data = o.data.copy()
    bpy.context.view_layer.update()
    for o in meshes:                                   # unparent, keeping the world transform
        world = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = world
    for o in list(bpy.data.objects):                   # empties, cameras, lights
        if o not in meshes:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()

    eps = _mesh.weld_eps(meshes)
    with contextlib.ExitStack() as stack:
        keepers = {}
        for o in meshes:
            local = eps / (max(abs(s) for s in o.matrix_world.to_scale()) or 1.0)
            keepers[o.name] = stack.enter_context(normals.NormalKeeper(o, eps=local))
        info = normalize_meshes(meshes, keepers, eps, a.yaw, a.target_size, a.target_height,
                                a.pivot)
        renamed = rename(meshes, a.name) if a.name else {}
    kept = sum(k.stats["kept"] for k in keepers.values())
    rebuilt = sum(k.stats["rebuilt"] for k in keepers.values())

    lo, hi = _mesh.world_bbox(meshes)
    export_glb(out_model)
    return {"out_model": out_model,
            "bbox": {"min": lo.tolist(), "max": hi.tolist(), "size": (hi - lo).tolist()},
            **info, "renamed": renamed,
            "tris": sum(len(o.data.loop_triangles) for o in meshes),
            "normals": {"kept": kept, "rebuilt": rebuilt}}


if __name__ == "__main__":  # importable: apply_recipe reuses normalize_meshes/rename
    sio.main(run, cfg)
