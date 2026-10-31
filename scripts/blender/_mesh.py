"""Shared mesh helpers for Blender scripts (QA, normalize, fixkit).

    import _mesh
    meshes = _mesh.model_meshes(objs)        # the model's mesh objects (scene-linked)
    eps = _mesh.weld_eps(meshes)             # 1e-5 x world bbox diagonal
    bm = _mesh.welded_bmesh(obj, eps)        # welded COPY; obj.data is never touched

Tripo splits vertices at every UV seam, so boundary/island/hole metrics are only
meaningful on a welded copy. The epsilon is relative to the bbox, never absolute.
"""
import bmesh
import bpy
import numpy as np

WELD_REL = 1e-5  # weld distance as a fraction of the world bbox diagonal


def model_meshes(objs) -> list:
    """Mesh objects of an imported model, without importer helpers.

    The glTF importer adds a bone-shape mesh (an icosphere) to rigged files; any mesh
    used as a pose-bone custom shape is display-only and not part of the model.
    """
    scene = bpy.context.scene.objects
    shapes = {pb.custom_shape.name for o in objs if o.type == "ARMATURE"
              for pb in o.pose.bones if pb.custom_shape is not None}
    return [o for o in objs if o.type == "MESH" and o.name in scene and o.name not in shapes]


def world_coords(obj) -> np.ndarray:
    """(V, 3) float64 world-space vertex positions of a mesh object."""
    me = obj.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(obj.matrix_world, np.float64)
    return co @ m[:3, :3].T + m[:3, 3]


def world_bbox(objs):
    """(min, max) world-space corners over all mesh vertices; (None, None) when empty."""
    chunks = [world_coords(o) for o in objs if o.type == "MESH" and len(o.data.vertices)]
    if not chunks:
        return None, None
    co = np.concatenate(chunks)
    return co.min(0), co.max(0)


def weld_eps(objs, rel: float = WELD_REL) -> float:
    """Weld distance: `rel` x the world bbox diagonal of the mesh objects (0.0 when empty)."""
    lo, hi = world_bbox(objs)
    if lo is None:
        return 0.0
    return float(np.linalg.norm(hi - lo)) * rel


def welded_bmesh(obj, eps: float, world: bool = True):
    """A new bmesh holding a welded copy of `obj`'s mesh. The caller frees it.

    world=True: coordinates are transformed to world space and `eps` is a world distance.
    world=False: local coordinates; `eps` (a world distance) is divided by the object's
    largest scale so the weld matches the world-space one.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if world:
        bm.transform(obj.matrix_world)
        dist = eps
    else:
        scale = max(abs(s) for s in obj.matrix_world.to_scale()) or 1.0
        dist = eps / scale
    if dist > 0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    return bm
