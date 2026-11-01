"""Parametric fix operators for recipes (spec 13), run inside one NormalKeeper per mesh.

    from fixkit import ops
    ctx = ops.Ctx(meshes, asset="tool_chest", base_dir=<recipe dir>)
    with contextlib.ExitStack() as stack:
        ctx.open(stack)                       # one keeper per mesh; transforms baked
        ops.run_step(ctx, "mirror_half", {"axis": "x", "keep": "+"})
    ctx.finalize()                            # work that must follow the normal restore

Every op is `op(ctx, **params) -> dict`, registered in OPS. Lengths and regions are
fractions of the current model bbox, never metres: a `box` is [x0, y0, z0, x1, y1, z1]
in 0-1 bbox space, `*_pct` values are percent of a bbox size, offsets are fractions of
the bbox size per axis. The one exception is `normalize`, whose params are Task 9's
(`target_height` / `target_size` are the game's metres). Frame: Blender, Z up.

Invariants inside the block: every mesh has an identity transform (open() bakes it
through the keeper), so mesh coordinates are world coordinates, until separate_parts
gives each part its own pivot. Geometry moves go through the keeper: whole-mesh moves
with nk.transform(), copies of part of a mesh with nk.add_copies(), split-off parts get
nk.fork(). Normals are never recomputed globally (B7).

Ops (params -> result keys):
  normalize(yaw, target_size, target_height, pivot, name)    Task 9 behaviour
  weld_boundary(eps_pct=0.001)       seam weld (1e-5 x diagonal), then open-edge vertices
                                     within eps_pct % of the diagonal
  remove_loose(min_tris_pct=1.0)     islands under min_tris_pct % of all triangles; the
                                     largest island always stays. Needs a weld first.
  remove_ground_slab(max_height_pct=3, reground=True)
                                     connected faces in the bottom band that face up over
                                     >= 25 % of the footprint and span >= 60 % of it (the
                                     QA GROUND_SLAB rule); the model is moved back down to
                                     its old floor. Needs a weld.
  delete_region(box)                 faces whose centre lies in box
  fill_holes(max_edges=64)           boundary-loop walker (not bmesh.ops.holes_fill, which
                                     skips holes); caps triangulated (beauty), UVs taken
                                     from the rim. A cap that would not be manifold is not
                                     added (holes_skipped lists edge counts). Needs a weld.
  mirror_half(axis, keep, plane=0.5) bisect at `plane` (0-1 along axis), drop the other
                                     side, add the kept side mirrored, weld the seam
                                     (seam_open_edges: open edges left on the plane)
  flatten_region(box, axis, proud_pct=0.5)
                                     press relief standing out along axis (+x|-x|+y|-y|
                                     +z|-z) back onto the main plane of the faces facing
                                     that way; collapsed walls are deleted
  clone_part(src_box, dst_offsets)   copy the faces in src_box to src_box + offset (each
                                     offset [dx, dy, dz] in bbox fractions), replacing the
                                     faces there
  hard_edges(angle=30, box=None)     edges sharper than angle: marked sharp, normals split
                                     there (corners at those edges get fan normals); runs
                                     at finalize(), after the keepers. Needs a weld.
  separate_parts(by="loose")         one object per loose part / material, named
                                     <asset>_part_NN under an empty <asset>, each with its
                                     pivot at its bbox bottom centre. Loose needs a weld.
                                     Must be the last geometry step.
  recolour(hsv_shift | ref_palette)  base-colour texture pixels: hsv_shift [hue_deg,
                                     sat_mul, val_mul], or ref_palette <image> (saturation
                                     scaled so the texture's median matches the
                                     reference's foreground); written back in the
                                     image's own format (JPEG stays JPEG)
"""
import inspect
import math
import os
import re
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

import _mesh
from fixkit import normals

FACING_COS = math.cos(math.radians(35))  # flatten_region: a face faces the axis within 35 deg
DEPTH_BIN = 0.005       # flatten_region: depth histogram bin, fraction of the axis extent
SLAB_SPAN = 0.60        # remove_ground_slab, same rule as qa.py GROUND_SLAB
SLAB_UP_AREA = 0.25
NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*\Z")
AXES = {"x": 0, "y": 1, "z": 2}


class RecipeError(ValueError):
    """The recipe cannot run as written (unknown op, bad params, wrong order): exit 2."""


# ---------------------------------------------------------------- context

class Ctx:
    """State shared by the ops of one recipe run."""

    def __init__(self, meshes, asset: str, base_dir: str = "."):
        self.meshes = list(meshes)
        self.asset = asset
        self.base_dir = base_dir
        self.welded = False
        self.separated = False
        self.keepers = {}
        self.stack = None
        self.finalizers = []

    def open(self, stack) -> None:
        """One NormalKeeper per mesh for the whole recipe; bake every transform."""
        self.stack = stack
        eps = self.eps()
        for o in self.meshes:
            local = eps / (max(abs(s) for s in o.matrix_world.to_scale()) or 1.0)
            nk = stack.enter_context(normals.NormalKeeper(o, eps=local))
            self.keepers[o.as_pointer()] = nk
            nk.transform(o.matrix_world.copy())
            o.parent = None
            o.matrix_parent_inverse = Matrix.Identity(4)
            o.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()

    def keeper(self, o) -> normals.NormalKeeper:
        return self.keepers[o.as_pointer()]

    def finalize(self) -> None:
        """Run after the keepers have exited (their normals restored)."""
        for fn in self.finalizers:
            fn()
        self.finalizers = []

    def normal_stats(self) -> dict:
        ks = list(self.keepers.values())
        return {"kept": sum(k.stats["kept"] for k in ks),
                "rebuilt": sum(k.stats["rebuilt"] for k in ks)}

    def bbox(self):
        lo, hi = _mesh.world_bbox(self.meshes)
        if lo is None:
            raise RecipeError("the model has no vertices left")
        return lo, hi

    def eps(self) -> float:
        """Seam weld distance: 1e-5 x the current bbox diagonal."""
        return _mesh.weld_eps(self.meshes)

    def need_weld(self, op: str) -> None:
        if not self.welded:
            raise RecipeError(f"{op} needs a welded mesh: put weld_boundary (or normalize) "
                              "before it (an unwelded Tripo mesh is split at every UV seam)")

    def geometry(self, op: str) -> None:
        if self.separated:
            raise RecipeError(f"{op} changes geometry: separate_parts must be the last "
                              "geometry step")

    def region(self, box, name="box"):
        """World (lo, hi) of a 0-1 bbox-space box, grown by the weld epsilon on every side
        so a face lying on the box's surface counts as inside whatever float rounding the
        transforms left (box [0, 0, 0, 1, 1, 1] is always the whole model)."""
        b = _box(box, name)
        lo, hi = self.bbox()
        size, tol = hi - lo, self.eps()
        return lo + b[:3] * size - tol, lo + b[3:] * size + tol


def tri_count(objs) -> int:
    n = 0
    for o in objs:
        o.data.calc_loop_triangles()
        n += len(o.data.loop_triangles)
    return n


# ---------------------------------------------------------------- param checks

def _num(v, name, lo=None, hi=None, positive=False) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise RecipeError(f"{name} must be a finite number, got {v!r}")
    if positive and v <= 0:
        raise RecipeError(f"{name} must be positive, got {v!r}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise RecipeError(f"{name} must be within [{lo}, {hi}], got {v!r}")
    return float(v)


def _vec(v, name, n) -> np.ndarray:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise RecipeError(f"{name} must be a list of {n} numbers, got {v!r}")
    return np.array([_num(x, name) for x in v])


def _box(box, name="box") -> np.ndarray:
    b = _vec(box, name, 6)
    if (b < 0).any() or (b > 1).any() or (b[:3] > b[3:]).any():
        raise RecipeError(f"{name} must be [x0, y0, z0, x1, y1, z1] with 0 <= lo <= hi <= 1 "
                          f"(fractions of the bbox), got {box!r}")
    return b


def _axis(axis, signed=False):
    """'x' -> (0, None); '+y' -> (1, 1.0) when signed."""
    if signed:
        if not (isinstance(axis, str) and len(axis) == 2 and axis[0] in "+-"
                and axis[1] in AXES):
            raise RecipeError(f"axis must be one of +x -x +y -y +z -z, got {axis!r}")
        return AXES[axis[1]], (1.0 if axis[0] == "+" else -1.0)
    if axis not in AXES:
        raise RecipeError(f"axis must be x, y or z, got {axis!r}")
    return AXES[axis], None


def _inside(points, lo, hi) -> np.ndarray:
    return ((points >= lo) & (points <= hi)).all(-1)


# ---------------------------------------------------------------- bmesh helpers

class _Edit:
    """with _Edit(obj) as bm: ...  writes the bmesh back to obj.data on success."""

    def __init__(self, obj):
        self.obj = obj

    def __enter__(self):
        self.bm = bmesh.new()
        self.bm.from_mesh(self.obj.data)
        return self.bm

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.bm.to_mesh(self.obj.data)
            self.obj.data.update()
        self.bm.free()
        return False


def _centres(faces) -> np.ndarray:
    return np.array([tuple(f.calc_center_median()) for f in faces]).reshape(-1, 3)


def _ftris(f) -> int:
    return len(f.verts) - 2


def _components(n, a, b) -> np.ndarray:
    """Connected-component label per node for undirected pairs (a[i], b[i])."""
    lab = np.arange(n)
    if len(a) == 0:
        return lab
    while True:
        la, lb = lab[a], lab[b]
        if np.array_equal(la, lb):
            return lab
        m = np.minimum(la, lb)
        np.minimum.at(lab, la, m)
        np.minimum.at(lab, lb, m)
        while True:
            nxt = lab[lab]
            if np.array_equal(nxt, lab):
                break
            lab = nxt


def _face_islands(bm, faces=None) -> np.ndarray:
    """Island label per face of `faces` (default all), faces joined by shared vertices."""
    faces = list(bm.faces) if faces is None else faces
    bm.verts.index_update()
    a, b, first = [], [], []
    for f in faces:
        vs = [v.index for v in f.verts]
        first.append(vs[0])
        a += [vs[0]] * (len(vs) - 1)
        b += vs[1:]
    lab = _components(len(bm.verts), np.array(a, np.int64), np.array(b, np.int64))
    return lab[np.array(first, np.int64)] if first else np.zeros(0, np.int64)


def _delete(bm, faces) -> int:
    faces = list(faces)
    n = sum(_ftris(f) for f in faces)
    if faces:
        bmesh.ops.delete(bm, geom=faces, context="FACES")
    return n


def _translation(v) -> Matrix:
    return Matrix.Translation(tuple(float(x) for x in v))


# ---------------------------------------------------------------- ops

def normalize(ctx, yaw=0.0, target_size=None, target_height=None, pivot="bottom_center",
              name=None):
    """Task 9 normalize (weld, yaw, uniform scale, pivot, names) on the recipe's meshes."""
    import normalize as nz
    ctx.geometry("normalize")
    yaw = _num(yaw, "yaw")
    if target_size is not None and target_height is not None:
        raise RecipeError("normalize takes target_size or target_height, not both")
    if target_size is not None:
        target_size = tuple(_num(x, "target_size", positive=True)
                            for x in _vec(target_size, "target_size", 3))
    if target_height is not None:
        target_height = _num(target_height, "target_height", positive=True)
    if pivot not in ("bottom_center", "center"):
        raise RecipeError(f"pivot must be bottom_center or center, got {pivot!r}")
    if name is not None and not (isinstance(name, str) and NAME_RE.match(name)):
        raise RecipeError(f"name must be letters, digits, '_' or '-', got {name!r}")
    keepers = {o.name: ctx.keeper(o) for o in ctx.meshes}
    try:
        info = nz.normalize_meshes(ctx.meshes, keepers, ctx.eps(), yaw, target_size,
                                   target_height, pivot)
    except ValueError as e:  # a flat model cannot fit a height, etc.
        raise RecipeError(f"normalize: {e}") from None
    ctx.welded = True
    renamed = nz.rename(ctx.meshes, name) if name else {}
    return {**info, "renamed": renamed}


def weld_boundary(ctx, eps_pct=0.001):
    """Seam weld, then weld open-edge vertices within eps_pct % of the bbox diagonal."""
    ctx.geometry("weld_boundary")
    eps_pct = _num(eps_pct, "eps_pct", positive=True)
    lo, hi = ctx.bbox()
    seam = ctx.eps()
    dist = eps_pct / 100.0 * float(np.linalg.norm(hi - lo))
    out = {"verts_before": 0, "verts_after": 0, "boundary_edges_before": 0,
           "boundary_edges_after": 0}
    for o in ctx.meshes:
        with _Edit(o) as bm:
            out["verts_before"] += len(bm.verts)
            if seam > 0:
                bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=seam)
            open_verts = {v for e in bm.edges if e.is_boundary for v in e.verts}
            out["boundary_edges_before"] += sum(e.is_boundary for e in bm.edges)
            if dist > seam and open_verts:
                bmesh.ops.remove_doubles(bm, verts=list(open_verts), dist=dist)
            out["boundary_edges_after"] += sum(e.is_boundary for e in bm.edges)
            out["verts_after"] += len(bm.verts)
    ctx.welded = True
    return {"dist_pct": eps_pct, **out}


def remove_loose(ctx, min_tris_pct=1.0):
    """Delete islands with fewer than min_tris_pct % of all triangles (never the largest)."""
    ctx.need_weld("remove_loose")
    ctx.geometry("remove_loose")
    pct = _num(min_tris_pct, "min_tris_pct", lo=0, hi=100)
    total = tri_count(ctx.meshes)
    limit = pct / 100.0 * total
    per_mesh, biggest = [], (-1, None, None)
    for o in ctx.meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        lab = _face_islands(bm)
        tris = np.array([_ftris(f) for f in bm.faces], np.int64)
        roots, inv = np.unique(lab, return_inverse=True)
        sizes = np.bincount(inv, weights=tris, minlength=len(roots))
        bm.free()
        per_mesh.append((roots, inv, sizes))
        if len(sizes) and sizes.max() > biggest[0]:
            biggest = (sizes.max(), o.as_pointer(), int(sizes.argmax()))
    out = {"islands_before": 0, "islands_removed": 0, "tris_removed": 0}
    for o, (roots, inv, sizes) in zip(ctx.meshes, per_mesh):
        out["islands_before"] += len(roots)
        drop = sizes < limit
        if o.as_pointer() == biggest[1]:
            drop[biggest[2]] = False
        if not drop.any():
            continue
        with _Edit(o) as bm:
            faces = [f for f, i in zip(bm.faces, inv) if drop[i]]
            out["tris_removed"] += _delete(bm, faces)
        out["islands_removed"] += int(drop.sum())
    return out


def remove_ground_slab(ctx, max_height_pct=3.0, reground=True):
    """Delete a slab/plate in the bottom max_height_pct % of the height (QA GROUND_SLAB)."""
    ctx.need_weld("remove_ground_slab")
    ctx.geometry("remove_ground_slab")
    pct = _num(max_height_pct, "max_height_pct", positive=True, hi=100)
    if not isinstance(reground, bool):
        raise RecipeError(f"reground must be true or false, got {reground!r}")
    lo, hi = ctx.bbox()
    size = hi - lo
    band = lo[2] + pct / 100.0 * size[2]
    footprint = float(size[0] * size[1])
    out = {"slabs": 0, "tris_removed": 0, "regrounded_pct": 0.0}
    for o in ctx.meshes:
        with _Edit(o) as bm:
            low = [f for f in bm.faces if all(v.co.z <= band for v in f.verts)]
            if not low or footprint <= 0:
                continue
            lab = _face_islands(bm, low)
            doomed = []
            for root in np.unique(lab):
                group = [f for f, g in zip(low, lab) if g == root]
                up = sum(max(f.normal.z, 0.0) * f.calc_area() for f in group)
                co = np.array([tuple(v.co) for f in group for v in f.verts])
                span = float(np.prod(co[:, :2].max(0) - co[:, :2].min(0)))
                if up >= SLAB_UP_AREA * footprint and span >= SLAB_SPAN * footprint:
                    doomed += group
                    out["slabs"] += 1
            out["tris_removed"] += _delete(bm, doomed)
    if out["tris_removed"] and reground:
        new_lo, _ = ctx.bbox()
        drop = float(lo[2] - new_lo[2])
        for o in ctx.meshes:
            ctx.keeper(o).transform(_translation((0.0, 0.0, drop)))
        out["regrounded_pct"] = round(-100.0 * drop / size[2], 4) if size[2] > 0 else 0.0
    return out


def delete_region(ctx, box):
    """Delete every face whose centre lies inside box."""
    ctx.geometry("delete_region")
    rlo, rhi = ctx.region(box)
    removed = 0
    for o in ctx.meshes:
        with _Edit(o) as bm:
            faces = list(bm.faces)
            hit = _inside(_centres(faces), rlo, rhi)
            removed += _delete(bm, [f for f, h in zip(faces, hit) if h])
    return {"tris_removed": removed}


def _boundary_loops(bm):
    """Boundary loops as lists of (vert, rim loop), and the count of open chains (walks
    stopped at a non-manifold vertex). A loop runs against the rim faces' winding, so a
    face built on its verts in this order faces outwards."""
    out_edges = {}
    for e in bm.edges:
        if e.is_boundary and e.link_loops:
            rim = e.link_loops[0]
            a, b = rim.link_loop_next.vert, rim.vert       # reversed rim direction
            out_edges.setdefault(a, []).append((b, rim))
    used, loops, open_chains = set(), [], 0
    for start, edges in out_edges.items():
        for first in edges:
            if id(first[1]) in used:
                continue
            chain, v, step = [], start, first
            while step is not None and id(step[1]) not in used:
                used.add(id(step[1]))
                chain.append((v, step[1]))
                v = step[0]
                if v == start:
                    break
                step = next((s for s in out_edges.get(v, ()) if id(s[1]) not in used), None)
            if v == start and len(chain) >= 3:
                loops.append(chain)
            else:
                open_chains += 1
    return loops, open_chains


def _cap(bm, chain, uv):
    """Cap one boundary loop: an n-gon on its verts, triangulated (beauty). Returns the new
    triangles, or None (nothing added) when the cap would not be manifold: a face on
    those verts exists, or a cap edge would get a third face (a loop that runs along
    both sides of a strip, or a chord already in the mesh)."""
    verts = [v for v, _ in chain]
    if len(set(verts)) != len(verts):
        return None
    try:
        f = bm.faces.new(verts)
    except ValueError:                                    # the face already exists
        return None
    f.material_index = chain[0][1].face.material_index
    f.smooth = True
    if uv is not None:                    # each corner takes a rim UV at its vertex
        rim_uv = {}
        for _, rim in chain:
            rim_uv[rim.vert] = rim[uv].uv.copy()
            rim_uv.setdefault(rim.link_loop_next.vert, rim.link_loop_next[uv].uv.copy())
        for loop in f.loops:
            loop[uv].uv = rim_uv[loop.vert]
    tris = bmesh.ops.triangulate(bm, faces=[f], quad_method="BEAUTY",
                                 ngon_method="BEAUTY")["faces"]
    if any(len(e.link_faces) > 2 for t in tris for e in t.edges):
        bmesh.ops.delete(bm, geom=tris, context="FACES")  # keeps the rim (used by its faces)
        return None
    return tris


def fill_holes(ctx, max_edges=64):
    """Cap every boundary loop of at most max_edges edges (loop walker, beauty fill)."""
    ctx.need_weld("fill_holes")
    ctx.geometry("fill_holes")
    max_edges = int(_num(max_edges, "max_edges", lo=3))
    out = {"holes_found": 0, "holes_filled": 0, "holes_skipped": [], "open_chains": 0,
           "tris_added": 0}
    for o in ctx.meshes:
        with _Edit(o) as bm:
            uv = bm.loops.layers.uv.active
            loops, open_chains = _boundary_loops(bm)
            out["open_chains"] += open_chains
            for chain in loops:
                out["holes_found"] += 1
                tris = _cap(bm, chain, uv) if len(chain) <= max_edges else None
                if tris is None:
                    out["holes_skipped"].append(len(chain))
                    continue
                out["holes_filled"] += 1
                out["tris_added"] += len(tris)
    return out


def _reflection(a, mid) -> Matrix:
    m = np.eye(4)
    m[a, a] = -1.0
    m[a, 3] = 2.0 * mid
    return Matrix(m.tolist())


def mirror_half(ctx, axis, keep, plane=0.5):
    """Keep one side of the plane at `plane` (0-1 along axis), mirror it onto the other."""
    ctx.geometry("mirror_half")
    a, _ = _axis(axis)
    if keep not in ("+", "-"):
        raise RecipeError(f"keep must be '+' or '-', got {keep!r}")
    plane = _num(plane, "plane", lo=0, hi=1)
    lo, hi = ctx.bbox()
    mid = float(lo[a] + plane * (hi[a] - lo[a]))
    eps = ctx.eps()
    normal = [0.0, 0.0, 0.0]
    normal[a] = 1.0
    co = [0.0, 0.0, 0.0]
    co[a] = mid
    sign = 1.0 if keep == "+" else -1.0
    before = tri_count(ctx.meshes)
    out = {"axis": axis, "keep": keep, "plane": plane, "tris_mirrored": 0,
           "seam_open_edges": 0}
    for o in ctx.meshes:
        with _Edit(o) as bm:
            geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
            bmesh.ops.bisect_plane(bm, geom=geom, dist=eps, plane_co=co, plane_no=normal,
                                   clear_inner=keep == "+", clear_outer=keep == "-")
            src = [f for f in bm.faces
                   if not all(abs(v.co[a] - mid) <= eps for v in f.verts)]
            if not src:
                continue
            dup = bmesh.ops.duplicate(bm, geom=src)
            new_verts = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]
            new_faces = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)]
            for v in new_verts:
                v.co[a] = 2.0 * mid - v.co[a]
            bmesh.ops.reverse_faces(bm, faces=new_faces)
            seam = [v for v in bm.verts if abs(v.co[a] - mid) <= eps]
            bmesh.ops.remove_doubles(bm, verts=seam, dist=eps)
            out["tris_mirrored"] += sum(_ftris(f) for f in new_faces if f.is_valid)
            out["seam_open_edges"] += sum(
                1 for e in bm.edges
                if e.is_boundary and all(abs(v.co[a] - mid) <= eps for v in e.verts))
        ctx.keeper(o).add_copies(_reflection(a, mid),
                                 lambda c: sign * (c[:, a] - mid) >= -eps)
    out["tris_removed"] = before + out["tris_mirrored"] - tri_count(ctx.meshes)
    return out


def flatten_region(ctx, box, axis, proud_pct=0.5):
    """Press relief inside box that stands out along axis back onto the main plane."""
    ctx.geometry("flatten_region")
    a, sign = _axis(axis, signed=True)
    proud_pct = _num(proud_pct, "proud_pct", positive=True, hi=100)
    rlo, rhi = ctx.region(box)
    lo, hi = ctx.bbox()
    ext = float(hi[a] - lo[a])
    direction = np.zeros(3)
    direction[a] = sign
    depths, areas = [], []
    for o in ctx.meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        faces = list(bm.faces)
        if faces:
            c = _centres(faces)
            n = np.array([tuple(f.normal) for f in faces])
            sel = _inside(c, rlo, rhi) & (n @ direction > FACING_COS)
            depths.append(sign * c[sel, a])
            areas.append(np.array([f.calc_area() for f, s in zip(faces, sel) if s]))
        bm.free()
    depth = np.concatenate(depths) if depths else np.zeros(0)
    area = np.concatenate(areas) if areas else np.zeros(0)
    if not len(depth) or ext <= 0:
        raise RecipeError(f"flatten_region: no face in box faces {axis}")
    width = DEPTH_BIN * ext
    bins = np.floor((depth - depth.min()) / width).astype(np.int64)
    peak = int(np.argmax(np.bincount(bins, weights=area)))
    near = np.abs(bins - peak) <= 1
    plane = float(np.average(depth[near], weights=area[near] + 1e-30))
    proud = proud_pct / 100.0 * ext
    eps = ctx.eps()
    out = {"plane_pct": round(100.0 * (sign * plane - lo[a]) / ext, 4), "verts_pressed": 0,
           "faces_removed": 0}
    for o in ctx.meshes:
        with _Edit(o) as bm:
            pressed = []
            for v in bm.verts:
                p = np.array(v.co)
                if _inside(p, rlo, rhi) and sign * p[a] > plane + proud:
                    v.co[a] = sign * plane
                    pressed.append(v)
            if not pressed:
                continue
            out["verts_pressed"] += len(pressed)
            bm.normal_update()
            touched = {f for v in pressed for f in v.link_faces}
            walls = [f for f in touched
                     if all(abs(sign * w.co[a] - plane) <= proud for w in f.verts)
                     and (f.calc_area() <= eps * eps or f.normal.dot(direction) < 0.5)]
            out["faces_removed"] += len(walls)
            bmesh.ops.delete(bm, geom=walls, context="FACES_ONLY")
            near_plane = {w for f in touched if f.is_valid for w in f.verts}
            bmesh.ops.remove_doubles(bm, verts=list(near_plane | set(v for v in pressed
                                                                      if v.is_valid)),
                                     dist=eps)
            loose = [e for e in bm.edges if not e.link_faces]
            loose += [v for v in bm.verts if not v.link_faces]
            if loose:
                bmesh.ops.delete(bm, geom=loose, context="EDGES")
    return out


def clone_part(ctx, src_box, dst_offsets):
    """Copy the faces in src_box onto src_box + each offset, replacing the faces there."""
    ctx.geometry("clone_part")
    slo, shi = ctx.region(src_box, "src_box")
    if not isinstance(dst_offsets, (list, tuple)) or not dst_offsets:
        raise RecipeError(f"dst_offsets must be a non-empty list of [dx, dy, dz], "
                          f"got {dst_offsets!r}")
    lo, hi = ctx.bbox()
    size = hi - lo
    moves = [_vec(off, "dst_offsets", 3) * size for off in dst_offsets]
    for m in moves:
        if (slo + m <= shi).all() and (shi + m >= slo).all():
            raise RecipeError("clone_part: a destination box overlaps src_box")
    eps = ctx.eps()
    out = {"src_tris": 0, "copies": len(moves), "tris_removed": 0, "tris_added": 0}
    for o in ctx.meshes:                       # the destinations may lie in any mesh
        with _Edit(o) as bm:
            faces = list(bm.faces)
            if not faces:
                continue
            c = _centres(faces)
            src = [f for f, s in zip(faces, _inside(c, slo, shi)) if s]
            doomed = set()
            for m in moves:
                doomed |= {f for f, s in zip(faces, _inside(c, slo + m, shi + m)) if s}
            out["tris_removed"] += _delete(bm, doomed)
            if not src:
                continue
            out["src_tris"] += sum(_ftris(f) for f in src)
            for m in moves:
                dup = bmesh.ops.duplicate(bm, geom=src)
                new_verts = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]
                bmesh.ops.translate(bm, verts=new_verts, vec=tuple(m))
                out["tris_added"] += sum(_ftris(g) for g in dup["geom"]
                                         if isinstance(g, bmesh.types.BMFace))
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=eps)
        nk = ctx.keeper(o)
        for m in moves:
            nk.add_copies(_translation(m), lambda cc: _inside(cc, slo, shi))
    if not out["src_tris"]:
        raise RecipeError("clone_part: src_box selects no faces")
    return out


def hard_edges(ctx, angle=30.0, box=None):
    """Mark edges sharper than `angle` degrees and split the normals there (finalize)."""
    ctx.need_weld("hard_edges")
    angle = _num(angle, "angle", positive=True, hi=180)
    region = ctx.region(box) if box is not None else None
    result = {"angle": angle, "sharp_edges": 0, "corners": 0}

    def apply():
        for o in ctx.meshes:
            n_edges, n_corners = _split_hard_edges(o, angle, region)
            result["sharp_edges"] += n_edges
            result["corners"] += n_corners

    ctx.finalizers.append(apply)
    return result


def _split_hard_edges(o, angle, region):
    me = o.data
    nl, ne, nf = len(me.loops), len(me.edges), len(me.polygons)
    if not nl:
        return 0, 0
    loop_edge = np.empty(nl, np.int32)
    me.loops.foreach_get("edge_index", loop_edge)
    loop_vert = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", loop_vert)
    start = np.empty(nf, np.int32)
    me.polygons.foreach_get("loop_start", start)
    total = np.empty(nf, np.int32)
    me.polygons.foreach_get("loop_total", total)
    loop_face = np.repeat(np.arange(nf), total)
    fn = np.empty(nf * 3, np.float64)
    me.polygon_normals.foreach_get("vector", fn)
    fn = fn.reshape(-1, 3)
    order = np.argsort(loop_edge, kind="stable")
    count = np.bincount(loop_edge, minlength=ne)
    two = np.flatnonzero(count == 2)
    first = np.searchsorted(loop_edge[order], two)
    fa, fb = loop_face[order[first]], loop_face[order[first + 1]]
    cos = np.einsum("ij,ij->i", fn[fa], fn[fb])
    sharp = two[cos < math.cos(math.radians(angle))]
    if region is not None and len(sharp):
        ev = np.empty(ne * 2, np.int32)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        co = _mesh.world_coords(o)
        mid = 0.5 * (co[ev[sharp, 0]] + co[ev[sharp, 1]])
        sharp = sharp[_inside(mid, *region)]
    if not len(sharp):
        return 0, 0
    current = np.empty(nl * 3, np.float64)
    me.corner_normals.foreach_get("vector", current)     # read before the marks change it
    current = current.reshape(-1, 3)
    attr = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    flags = np.zeros(ne, bool)
    attr.data.foreach_get("value", flags)
    flags[sharp] = True
    attr.data.foreach_set("value", flags)
    tmp = me.copy()                                        # fan normals: no custom normals,
    try:                                                   # every face smooth, sharp edges kept
        if "custom_normal" in tmp.attributes:
            tmp.attributes.remove(tmp.attributes["custom_normal"])
        if "sharp_face" in tmp.attributes:
            tmp.attributes.remove(tmp.attributes["sharp_face"])
        fan = np.empty(nl * 3, np.float64)
        tmp.corner_normals.foreach_get("vector", fan)
        fan = fan.reshape(-1, 3)
    finally:
        bpy.data.meshes.remove(tmp)
    ev = np.empty(ne * 2, np.int32)
    me.edges.foreach_get("vertices", ev)
    at_sharp = np.zeros(len(me.vertices), bool)
    at_sharp[ev.reshape(-1, 2)[sharp].ravel()] = True
    hit = at_sharp[loop_vert]
    current[hit] = fan[hit]
    me.normals_split_custom_set(current.tolist())
    return int(len(sharp)), int(hit.sum())


def separate_parts(ctx, by="loose"):
    """One object per loose part (or material), named <asset>_part_NN, pivot at the part's
    bbox bottom centre, all under an empty named <asset>."""
    ctx.geometry("separate_parts")
    if by not in ("loose", "material"):
        raise RecipeError(f"by must be loose or material, got {by!r}")
    if by == "loose":
        ctx.need_weld("separate_parts by loose")
    groups = []                                   # (obj, face indices, tris, centre)
    for o in ctx.meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        faces = list(bm.faces)
        if faces:
            if by == "loose":
                lab = _face_islands(bm)
            else:
                lab = np.array([f.material_index for f in faces], np.int64)
            tris = np.array([_ftris(f) for f in faces])
            c = _centres(faces)
            for g in np.unique(lab):
                idx = np.flatnonzero(lab == g)
                groups.append((o, idx, int(tris[idx].sum()), tuple(np.round(c[idx].mean(0), 6))))
        bm.free()
    groups.sort(key=lambda g: (-g[2], g[3]))
    names = {id(g): f"{ctx.asset}_part_{i + 1:02d}" for i, g in enumerate(groups)}

    parts = []
    for o in list(ctx.meshes):
        mine = [g for g in groups if g[0] == o]
        if not mine:
            continue
        nk = ctx.keeper(o)
        objs = [o]
        for _ in mine[1:]:                          # copies first, from the untouched mesh
            new = bpy.data.objects.new("_part", o.data.copy())
            for coll in o.users_collection:
                coll.objects.link(new)
            fork = nk.fork(new)
            ctx.stack.push(fork)
            ctx.keepers[new.as_pointer()] = fork
            objs.append(new)
        for obj, g in zip(objs, mine):
            keep = set(g[1].tolist())
            with _Edit(obj) as bm:
                bm.faces.ensure_lookup_table()
                bmesh.ops.delete(bm, geom=[f for i, f in enumerate(bm.faces) if i not in keep],
                                 context="FACES")
            parts.append((obj, g))
    for p in [p for p in bpy.data.objects if p.type == "EMPTY"]:
        bpy.data.objects.remove(p, do_unlink=True)     # old roots (normalize's rename)
    root = bpy.data.objects.new(ctx.asset, None)
    bpy.context.scene.collection.objects.link(root)
    for i, (obj, _) in enumerate(parts):            # two passes: no clash with old names
        obj.name = obj.data.name = f"__part_tmp_{i}"
    out = []
    for obj, g in parts:
        co = _mesh.world_coords(obj)
        lo, hi = co.min(0), co.max(0)
        pivot = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        ctx.keeper(obj).transform(_translation([-x for x in pivot]))
        obj.parent = root
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = _translation(pivot)
        obj.name = obj.data.name = names[id(g)]
        out.append({"name": obj.name, "tris": g[2], "pivot": [float(x) for x in pivot]})
    bpy.context.view_layer.update()
    ctx.meshes = [obj for obj, _ in parts]
    ctx.separated = True
    out.sort(key=lambda p: p["name"])
    return {"by": by, "parts": out}


# ---------------------------------------------------------------- recolour

def _base_color_image(mat):
    """The image feeding the Principled BSDF Base Color (else the first image node)."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None
    nodes = mat.node_tree.nodes
    for bsdf in (n for n in nodes if n.type == "BSDF_PRINCIPLED"):
        sock = bsdf.inputs.get("Base Color")
        todo, seen = list(sock.links) if sock else [], set()
        while todo:
            node = todo.pop(0).from_node
            if node.name in seen:
                continue
            seen.add(node.name)
            if node.type == "TEX_IMAGE" and node.image is not None:
                return node.image
            for inp in node.inputs:
                todo.extend(inp.links)
    return next((n.image for n in nodes if n.type == "TEX_IMAGE" and n.image is not None), None)


def _pixels(img) -> np.ndarray:
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(-1, 4)


def rgb_to_hsv(rgb):
    mx, mn = rgb.max(1), rgb.min(1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-12), 0.0)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    dd = np.maximum(d, 1e-12)
    h = np.where(mx == r, (g - b) / dd % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4))
    h = np.where(d > 0, h / 6.0, 0.0)
    return np.stack([h, s, mx], 1)


def hsv_to_rgb(hsv):
    h, s, v = hsv[:, 0] % 1.0, hsv[:, 1], hsv[:, 2]
    i = np.floor(h * 6).astype(np.int64) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    table = np.stack([np.stack(c, 1) for c in
                      ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))])
    return table[i, np.arange(len(h))]


def _median_saturation(rgba, mask=None, stride=7) -> float:
    sub = rgba[::stride]
    keep = sub[:, 3] > 0.5
    if mask is not None:
        keep &= mask[::stride]
    if not keep.any():
        return 0.0
    return float(np.median(rgb_to_hsv(sub[keep, :3].astype(np.float64))[:, 1]))


def _reference_saturation(path) -> float:
    """Median saturation of the reference's foreground (pixels unlike the border colour)."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = _pixels(img)
    finally:
        bpy.data.images.remove(img)
    grid = px.reshape(h, w, 4)
    border = np.concatenate([grid[0], grid[-1], grid[:, 0], grid[:, -1]])[:, :3]
    bg = np.median(border, 0)
    fg = np.abs(px[:, :3] - bg).max(1) > 0.12
    return _median_saturation(px, fg, stride=3)


def _write_image(img, rgba) -> None:
    """New pixels, packed in the image's own format (JPEG stays JPEG, else PNG)."""
    img.pixels.foreach_set(rgba.ravel())
    fmt = "JPEG" if img.file_format == "JPEG" else "PNG"
    fd, tmp = tempfile.mkstemp(prefix="fixkit-", suffix=".jpg" if fmt == "JPEG" else ".png")
    os.close(fd)
    try:
        img.file_format = fmt
        img.save(filepath=tmp, quality=95)
        with open(tmp, "rb") as f:
            data = f.read()
        img.pack(data=data, data_len=len(data))
    finally:
        os.unlink(tmp)


def recolour(ctx, hsv_shift=None, ref_palette=None):
    """Shift the base-colour textures in HSV, or restore their saturation to a reference."""
    if (hsv_shift is None) == (ref_palette is None):
        raise RecipeError("recolour takes exactly one of hsv_shift or ref_palette")
    out = {"images": []}
    if hsv_shift is not None:
        hue, s_mul, v_mul = _vec(hsv_shift, "hsv_shift", 3)
        if s_mul < 0 or v_mul < 0:
            raise RecipeError(f"hsv_shift multipliers must be >= 0, got {hsv_shift!r}")
    else:
        if not isinstance(ref_palette, str):
            raise RecipeError(f"ref_palette must be an image path, got {ref_palette!r}")
        path = os.path.join(ctx.base_dir, os.path.expanduser(ref_palette))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"reference palette not found: {path}")
        out["ref_saturation"] = ref = round(_reference_saturation(path), 4)
        hue, v_mul = 0.0, 1.0
    images = []
    for o in ctx.meshes:
        for slot in o.material_slots:
            img = _base_color_image(slot.material)
            if img is not None and img not in images and img.size[0] > 0:
                images.append(img)
    for img in images:
        px = _pixels(img)
        before = _median_saturation(px)
        if ref_palette is not None:
            s_mul = min(max(ref / before, 0.25), 4.0) if before > 0 else 1.0
        for i in range(0, len(px), 1 << 21):                # chunks keep memory flat
            chunk = px[i:i + (1 << 21)]
            hsv = rgb_to_hsv(chunk[:, :3].astype(np.float64))
            hsv[:, 0] += hue / 360.0
            hsv[:, 1] = np.clip(hsv[:, 1] * s_mul, 0.0, 1.0)
            hsv[:, 2] = np.clip(hsv[:, 2] * v_mul, 0.0, 1.0)
            chunk[:, :3] = hsv_to_rgb(hsv)
        _write_image(img, px)
        out["images"].append({"name": img.name, "format": img.file_format,
                              "s_mul": round(float(s_mul), 4),
                              "saturation_before": round(before, 4),
                              "saturation_after": round(_median_saturation(_pixels(img)), 4)})
    return out


# ---------------------------------------------------------------- registry

OPS = {fn.__name__: fn for fn in (normalize, weld_boundary, remove_loose, remove_ground_slab,
                                  delete_region, fill_holes, mirror_half, flatten_region,
                                  clone_part, hard_edges, separate_parts, recolour)}
GEOMETRY_OPS = set(OPS) - {"hard_edges", "recolour"}


STEP_KEYS = ("op", "params")


def check_steps(steps) -> None:
    """Static checks before any work: known ops, known step keys, known/required params, op
    order (separate_parts is the last geometry step; hard_edges comes after every geometry op,
    because its region is resolved before later geometry changes)."""
    if not isinstance(steps, list) or not steps:
        raise RecipeError("steps must be a non-empty list of {op, params}")
    separated = hard = False
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("op"), str):
            raise RecipeError(f"step {i}: expected {{\"op\": <name>, \"params\": {{...}}}}")
        op, params = step["op"], step.get("params", {})
        extra = sorted(set(step) - set(STEP_KEYS))
        if extra:
            raise RecipeError(f"step {i} ({op}): unknown step key(s) {', '.join(extra)}; a step is "
                              f"{{\"op\": ..., \"params\": {{...}}}} and parameters go inside params "
                              f"(e.g. {{\"op\": \"{op}\", \"params\": {{\"{extra[0]}\": ...}}}})")
        if op not in OPS:
            raise RecipeError(f"step {i}: unknown op {op!r} (known: {', '.join(sorted(OPS))})")
        if not isinstance(params, dict):
            raise RecipeError(f"step {i} ({op}): params must be an object")
        try:
            inspect.signature(OPS[op]).bind(None, **params)
        except TypeError as e:
            raise RecipeError(f"step {i} ({op}): {e}") from None
        if separated and op in GEOMETRY_OPS:
            raise RecipeError(f"step {i} ({op}) changes geometry: separate_parts must be "
                              "the last geometry step")
        if hard and op in GEOMETRY_OPS:
            raise RecipeError(f"step {i} ({op}) changes geometry: hard_edges must come after "
                              "every geometry op (its region is fixed when it runs)")
        separated |= op == "separate_parts"
        hard |= op == "hard_edges"


def run_step(ctx, op: str, params: dict) -> dict:
    return OPS[op](ctx, **params)
