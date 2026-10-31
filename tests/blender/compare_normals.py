"""Test helper (run through bl.run): how well normalize.py kept the input's normals.

    bl.run("tests/blender/compare_normals.py",
           [<in>, <out.glb>, "--yaw", DEG, "--scale", S, "--offset=X,Y,Z"])

The input's triangles are moved the way normalize moved them (yaw about Z, then uniform
scale, then offset) and matched to the output's triangles by their sorted corner
positions on a coarse grid. This is deliberately not the NormalKeeper's own matching.
-> {"tris_in", "tris_out", "matched", "max_angle_deg", "p99_angle_deg"}
"""
import math

import numpy as np

import _mesh
import skill_io as sio

GRID_REL = 2e-4  # matching grid, fraction of the output bbox diagonal


def triangles(path):
    """World-space corner positions and unit corner normals, both (T, 3, 3)."""
    meshes = _mesh.model_meshes(sio.load_model(path))
    pos, nrm = [], []
    for o in meshes:
        me = o.data
        me.calc_loop_triangles()
        loops = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("loops", loops)
        verts = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get("vertex_index", verts)
        cn = np.empty(len(me.loops) * 3, np.float64)
        me.corner_normals.foreach_get("vector", cn)
        m = np.array(o.matrix_world, np.float64)
        co = _mesh.world_coords(o)
        n = cn.reshape(-1, 3) @ np.linalg.inv(m[:3, :3])  # inverse transpose, row vectors
        n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
        pos.append(co[verts[loops]].reshape(-1, 3, 3))
        nrm.append(n[loops].reshape(-1, 3, 3))
    return np.concatenate(pos), np.concatenate(nrm)


def cells(p, g):
    return np.round(p / g).astype(np.int64)


def cfg(p):
    p.add_argument("model_in")
    p.add_argument("model_out")
    p.add_argument("--yaw", type=float, default=0.0)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--offset", default="0,0,0")


def run(a):
    p_in, n_in = triangles(a.model_in)
    t = math.radians(a.yaw)
    rot = np.array([[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1]])
    off = np.array([float(x) for x in a.offset.split(",")])
    p_in = a.scale * p_in @ rot.T + off
    n_in = n_in @ rot.T
    p_out, n_out = triangles(a.model_out)

    flat = p_out.reshape(-1, 3)
    g = GRID_REL * float(np.linalg.norm(flat.max(0) - flat.min(0)))
    c_in, c_out = cells(p_in, g), cells(p_out, g)
    table = {}
    for i, tri in enumerate(c_in):
        key = tuple(sorted(map(tuple, tri)))
        table[key] = None if key in table else i  # None: ambiguous, never matched
    angles = []
    for j, tri in enumerate(c_out):
        i = table.get(tuple(sorted(map(tuple, tri))))
        if i is None:
            continue
        for k in range(3):
            m = int(np.argmin(np.abs(c_in[i] - tri[k]).sum(1)))
            d = float(np.clip(np.dot(n_in[i, m], n_out[j, k]), -1.0, 1.0))
            angles.append(math.degrees(math.acos(d)))
    ang = np.array(angles) if angles else np.zeros(1)
    return {"tris_in": len(p_in), "tris_out": len(p_out), "matched": len(angles) // 3,
            "max_angle_deg": float(ang.max()), "p99_angle_deg": float(np.percentile(ang, 99))}


sio.main(run, cfg)
