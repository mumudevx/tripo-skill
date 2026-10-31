"""Test helper (run through bl.run): NormalKeeper on a synthetic mesh.

A UV sphere (quads plus pole triangles) gets distinctive custom normals (tilted 25
degrees towards +X, which no automatic normal would produce). Inside the keeper the
whole mesh is rotated, scaled and moved with keeper.transform(), and one equator vertex
is pushed outwards. Expected after exit: triangles of the faces that touch the pushed
vertex are rebuilt (a quad is kept or rebuilt as a whole), every other triangle keeps
its (transformed) tilted normals.
-> {"tris", "touching", "kept", "rebuilt", "kept_max_dev_deg", "rebuilt_median_dev_deg",
    "rebuilt_max_face_dev_deg"}
"""
import math

import bpy
import numpy as np
from mathutils import Matrix

import skill_io as sio
from fixkit import normals

TILT = math.radians(25)


def corner_data(me):
    me.calc_loop_triangles()
    loops = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", loops)
    verts = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", verts)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    cn = np.empty(len(me.loops) * 3, np.float64)
    me.corner_normals.foreach_get("vector", cn)
    return loops.reshape(-1, 3), verts, co.reshape(-1, 3), cn.reshape(-1, 3)


def angle(a, b):
    d = np.einsum("ij,ij->i", a, b) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    return np.degrees(np.arccos(np.clip(d, -1, 1)))


def run(a):
    sio.clear_scene()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1.0)
    obj = bpy.context.object
    me = obj.data
    _, verts, co, _ = corner_data(me)
    radial = co[verts] / np.linalg.norm(co[verts], axis=1)[:, None]
    tilt = Matrix.Rotation(TILT, 3, "Y")
    tilted = radial @ np.array(tilt, np.float64).T
    me.normals_split_custom_set(tilted.tolist())

    push = int(np.argmin(np.abs(co[:, 2]) + np.abs(co[:, 1]) - co[:, 0]))  # equator, +X
    move = Matrix.Translation((0.5, -1.0, 2.0)) @ Matrix.Rotation(math.radians(30), 4, "Z") \
        @ Matrix.Scale(2.0, 4)
    with normals.NormalKeeper(obj) as nk:
        nk.transform(move)
        me.vertices[push].co = me.vertices[push].co * 1.3
    stats = dict(nk.stats)

    loops, verts, co, cn = corner_data(me)
    poly = np.empty(len(me.loop_triangles), np.int32)
    me.loop_triangles.foreach_get("polygon_index", poly)
    touching = np.isin(poly, [p.index for p in me.polygons if push in p.vertices])
    rot = np.array(move.to_3x3().normalized(), np.float64)
    expect = (tilted @ rot.T)[loops]                  # (T, 3, 3) kept normals, moved
    got = cn[loops]
    dev = angle(got.reshape(-1, 3), expect.reshape(-1, 3)).reshape(-1, 3)
    p = co[verts[loops]]
    face = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    face_dev = angle(got.reshape(-1, 3), np.repeat(face, 3, axis=0))
    # a quad's two triangles share loops, and a loop has one normal: measure each loop
    # against the closest face normal among the triangles that use it
    loop_dev = np.full(len(me.loops), np.inf)
    np.minimum.at(loop_dev, loops.ravel(), face_dev)
    return {"tris": int(len(loops)), "touching": int(touching.sum()),
            "kept": stats["kept"], "rebuilt": stats["rebuilt"],
            "kept_max_dev_deg": float(dev[~touching].max()),
            "rebuilt_median_dev_deg": float(np.median(dev[touching])),
            "rebuilt_max_face_dev_deg": float(loop_dev[loops[touching]].max())}


sio.main(run)
