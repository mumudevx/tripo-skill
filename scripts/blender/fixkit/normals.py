"""NormalKeeper: keep the generator's custom normals through mesh edits (B7).

    from fixkit import normals
    with normals.NormalKeeper(obj) as nk:
        nk.transform(matrix)        # a move is not an edit: stored normals follow it
        ...edit obj.data...         # delete, add, move vertices, weld
    nk.stats                        # {"kept": <triangles>, "rebuilt": <triangles>}

Recomputing normals on a Tripo mesh shows waves and dents that the exported normals
hide, far away from the part that was fixed. So:

- on enter, every triangle's corner normals are stored, keyed by the triangle's welded
  corner positions (identity within the weld epsilon, 1e-5 x bbox diagonal by default);
- on exit, a triangle whose key still exists gets its stored normals back; only new or
  changed triangles get analytic normals: smooth across neighbours whose face normal is
  within 30 degrees (angle weighted), flat otherwise.

Keys are matched with a tolerance (3 x eps) rather than by rounding positions to a grid:
a coordinate that sits on a rounding boundary flips cells after a float32 transform, and
plain rounding would then rebuild a few percent of untouched triangles.

A polygon (quads in FBX/OBJ inputs) is kept only when all of its triangles are kept;
otherwise all of its corners are rebuilt, so one face never mixes both kinds.

`transform(matrix)` is the only way to move the mesh inside the keeper: it applies the
4x4 matrix to obj.data and remembers it, so stored positions are compared in the frame
they were taken in and stored normals are rotated with the mesh. On an exception inside
the block the mesh is left as it is (the caller is failing anyway).

This replaces the two prior mechanisms (per-vertex keep_normals.py and per-triangle
fix_common.save_keeping); there is one implementation.
"""
import math

import numpy as np
from mathutils import Matrix

import _mesh

SMOOTH_ANGLE = 30.0  # degrees: neighbours within this angle shade smooth on rebuilt triangles
MATCH_TOL = 3.0      # a stored corner matches within this many epsilons
CELL = 4.0           # triangle-centroid grid for candidate lookup, in epsilons
MIN_EPS_REL = 1e-6   # epsilon floor (fraction of the bbox diagonal) to keep cell keys in int64


def _ints(coll, attr, n, width=1):
    buf = np.empty(n * width, np.int32)
    coll.foreach_get(attr, buf)
    return buf.astype(np.int64).reshape(-1, width) if width > 1 else buf.astype(np.int64)


def _triangles(me):
    """Loop indices (T, 3), corner positions (T, 3, 3) in mesh space, polygon index (T,)."""
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    loops = _ints(me.loop_triangles, "loops", nt, 3)
    poly = _ints(me.loop_triangles, "polygon_index", nt)
    corner_vert = _ints(me.loops, "vertex_index", len(me.loops))
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    pos = co.reshape(-1, 3)[corner_vert[loops]] if nt else np.zeros((0, 3, 3))
    return loops, pos, poly


def _corner_normals(me):
    cn = np.empty(len(me.loops) * 3, np.float64)
    me.corner_normals.foreach_get("vector", cn)
    return cn.reshape(-1, 3)


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.divide(v, n, out=np.zeros_like(v), where=n > 1e-30)


def _face_normals(pos):
    return np.cross(pos[:, 1] - pos[:, 0], pos[:, 2] - pos[:, 0])


def _corner_angles(pos):
    """(T, 3) interior angle at each corner."""
    out = np.empty(pos.shape[:2])
    for k in range(3):
        a = _unit(pos[:, (k + 1) % 3] - pos[:, k])
        b = _unit(pos[:, (k + 2) % 3] - pos[:, k])
        out[:, k] = np.arccos(np.clip(np.einsum("ij,ij->i", a, b), -1.0, 1.0))
    return out


def smooth_by_angle(pos, which, eps, angle=SMOOTH_ANGLE):
    """Analytic corner normals (len(which), 3, 3) for triangles `which` of `pos` (T, 3, 3).

    A corner averages (angle weighted) the face normals of all triangles that share its
    position (within eps) and whose face normal is within `angle` of its own; a corner
    with no such neighbour is flat. Degenerate triangles get zero vectors (Blender then
    uses its default normal for those corners).
    """
    which = np.asarray(which, np.int64)
    if len(which) == 0:
        return np.zeros((0, 3, 3))
    fn = _unit(_face_normals(pos))
    ang = _corner_angles(pos)
    _, vid = np.unique(np.round(pos.reshape(-1, 3) / eps).astype(np.int64), axis=0,
                       return_inverse=True)
    vid = vid.ravel()
    order = np.argsort(vid, kind="stable")
    start = np.searchsorted(vid[order], np.arange(vid.max() + 1), "left")
    end = np.searchsorted(vid[order], np.arange(vid.max() + 1), "right")

    need = (which[:, None] * 3 + np.arange(3)).ravel()          # flat corner ids
    v = vid[need]
    counts = end[v] - start[v]
    owner = np.repeat(np.arange(len(need)), counts)              # pair -> needed corner
    first = np.repeat(start[v], counts)
    step = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    nb = order[first + step]                                     # neighbour corner ids
    t_self, t_nb = need[owner] // 3, nb // 3
    ok = np.einsum("ij,ij->i", fn[t_self], fn[t_nb]) >= math.cos(math.radians(angle)) - 1e-9
    w = ang[t_nb, nb % 3] * ok
    acc = np.zeros((len(need), 3))
    np.add.at(acc, owner, w[:, None] * fn[t_nb])
    return _unit(acc).reshape(-1, 3, 3)


class NormalKeeper:
    """Context manager keeping `obj`'s custom normals on triangles an edit left alone.

    `eps` is the weld distance in mesh (local) units; default 1e-5 x the local bbox
    diagonal. Pass the weld epsilon in use when the edits include a weld.
    """

    def __init__(self, obj, eps: float = None):
        self.obj = obj
        self.eps = eps
        self.stats = {"kept": 0, "rebuilt": 0}
        self._m = np.eye(4)

    def __enter__(self):
        me = self.obj.data
        loops, pos, _ = _triangles(me)
        flat = pos.reshape(-1, 3)
        diag = float(np.linalg.norm(flat.max(0) - flat.min(0))) if len(flat) else 0.0
        eps = self.eps if self.eps is not None else _mesh.WELD_REL * diag
        self.eps = max(eps, MIN_EPS_REL * diag, 1e-12)
        self._pos = pos
        self._nrm = _corner_normals(me)[loops] if len(loops) else np.zeros((0, 3, 3))
        self._fn = _face_normals(pos)
        return self

    def transform(self, matrix) -> None:
        """Apply the 4x4 `matrix` to the mesh data; stored normals follow it."""
        m = Matrix(matrix)
        self.obj.data.transform(m)
        self._m = np.array(m, np.float64) @ self._m

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._restore()
        return False

    def _restore(self) -> None:
        me = self.obj.data
        loops, pos, poly = _triangles(me)
        if len(loops) == 0:
            self.stats = {"kept": 0, "rebuilt": 0}
            return
        inv = np.linalg.inv(self._m)
        back = pos @ inv[:3, :3].T + inv[:3, 3]           # current corners, enter frame
        match, corner = self._match(back)

        kept = match >= 0
        bad_poly = np.unique(poly[~kept])                 # a face is kept only as a whole
        kept &= ~np.isin(poly, bad_poly)

        lin = self._m[:3, :3]
        normal_m = np.linalg.inv(lin).T                   # stored normals -> current frame
        out = np.zeros(pos.shape)
        src = self._nrm[match[kept][:, None], corner[kept]]
        out[kept] = _unit(src @ normal_m.T)
        scale = abs(np.linalg.det(lin)) ** (1.0 / 3.0) or 1.0
        out[~kept] = smooth_by_angle(pos, np.flatnonzero(~kept), self.eps * scale)

        per_loop = np.zeros((len(me.loops), 3))
        per_loop[loops[kept].ravel()] = out[kept].reshape(-1, 3)
        per_loop[loops[~kept].ravel()] = out[~kept].reshape(-1, 3)
        me.normals_split_custom_set(per_loop.tolist())
        self.stats = {"kept": int(kept.sum()), "rebuilt": int((~kept).sum())}

    def _match(self, back):
        """For each current triangle (enter-frame corners `back`), the stored triangle with
        the same corners within MATCH_TOL x eps and the same winding: (T,) index or -1,
        and (T, 3) the stored corner each current corner maps to."""
        n = len(back)
        match = np.full(n, -1, np.int64)
        corner = np.zeros((n, 3), np.int64)
        if len(self._pos) == 0:
            return match, corner
        g, tol = CELL * self.eps, MATCH_TOL * self.eps
        k0 = np.floor(self._pos.mean(1) / g).astype(np.int64)
        # current centroids outside the stored range +-1 cell cannot match; clipping them
        # keeps the cell codes small (int64) whatever an edit added far away
        k1 = np.clip(np.floor(back.mean(1) / g).astype(np.int64), k0.min(0) - 1, k0.max(0) + 1)
        base = k0.min(0) - 2
        dims = k0.max(0) - base + 3

        def code(k):
            k = k - base
            return (k[:, 0] * dims[1] + k[:, 1]) * dims[2] + k[:, 2]

        order = np.argsort(code(k0), kind="stable")
        keys = code(k0)[order]
        fn1 = _face_normals(back)
        offsets = [(0, 0, 0)] + [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1)
                                 for z in (-1, 0, 1) if (x, y, z) != (0, 0, 0)]
        for off in offsets:
            todo = np.flatnonzero(match < 0)
            if len(todo) == 0:
                break
            q = code(k1[todo] + np.array(off))
            lo = np.searchsorted(keys, q, "left")
            count = np.searchsorted(keys, q, "right") - lo
            for r in range(int(count.max()) if len(count) else 0):
                sel = (count > r) & (match[todo] < 0)
                cur, cand = todo[sel], order[lo[sel] + r]
                if len(cur) == 0:
                    continue
                d = np.linalg.norm(back[cur][:, :, None, :] - self._pos[cand][:, None, :, :],
                                   axis=-1)                          # (n, 3 cur, 3 stored)
                ok = (d.min(2) <= tol).all(1) & (d.min(1) <= tol).all(1)
                ok &= np.einsum("ij,ij->i", fn1[cur], self._fn[cand]) >= 0
                match[cur[ok]] = cand[ok]
                corner[cur[ok]] = d[ok].argmin(2)
        return match, corner
