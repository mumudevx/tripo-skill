"""QA metrics for one model, 0 credits (run through scripts/bl.py).

    bl.py qa.py -- <model> [--budget N] [--symmetric x|none] [--front -y|+y|-x|+x]
                  [--ref-palette <png>] [--class <class>] [--thresholds <json>]

-> {"schema": "qa/1", "file", "format", "class", "metrics": {...}, "findings": [...]}

Order: import (GLB/GLTF/FBX/OBJ by magic bytes) -> weld a COPY of each mesh
(1e-5 x bbox diagonal, scripts/blender/_mesh.py) -> topology metrics on the welded
copy; normals, slivers, UVs and texture metrics on the loaded data, which is never
modified. Blender is Z-up; the importers convert glTF/FBX Y-up to Z-up. The default
front is -Y, which is glTF +Z (Tripo's front).

Thresholds come from scripts/data/qa_thresholds.json ("qa"). A code whose severity
there is "info" has no calibrated threshold yet and is reported as info only;
"rule" means the severity is computed (OVER_BUDGET: S1 above 1.10 x budget, S0
above 2 x). `--class` is recorded only; the budget is passed in by the caller.

`--symmetric x` and `--front` read the model in its current frame: the asymmetry
mirror is world X, so turn the model to face -Y first (raw Tripo outputs often
face +X). Findings carry `fix_options`: fixkit op names (weld_boundary,
remove_loose, remove_ground_slab, delete_region, fill_holes, mirror_half,
flatten_region, clone_part, hard_edges, separate_parts, recolour, normalize) and
the other rungs of the fix ladder (engine_side, tripo_retexture, tripo_decimate,
tripo_rig, tripo_regenerate).

Extra metric keys beyond the plan: boundary_edges_raw (before weld), island_count
(islands lists the largest 32), front, palette.chroma_ratio.
"""
import json
import math
import os

import bpy
import numpy as np

import _mesh
import skill_io as sio

SCHEMA = "qa/1"
DEFAULT_THRESHOLDS = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "qa_thresholds.json"))

# metric definitions (fixed by the plan, not calibration values)
SLIVER_ANGLE_DEG = 5.0      # a sliver has a minimum angle below this
GROUND_BAND = 0.03          # bottom 3 % of the height
SLAB_SPAN = 0.60            # a slab spans >= 60 % of the footprint (XY bbox area)
SLAB_UP_AREA = 0.25         # ... and shows an upward face over >= 25 % of it (a box's
                            # bottom face faces down only, so it never counts)
SAMPLES = 150_000           # area-weighted surface samples
SEED = 7                    # fixed: the same file always gives the same numbers
QUERY_MAX = 40_000          # mirrored vertices used for the asymmetry mean
DEPTH_GRID = 64             # back_relief depth-map cells along the long side
UV_GRID = 512               # UV overlap raster
PIXEL_MAX = 1024            # textures are read downscaled to this long side
ISLANDS_LISTED = 32
KMEANS_K = 8

SEVERITY_RANK = {"S0": 0, "S1": 1, "S2": 2, "info": 3}
CODE_ORDER = ["OVER_BUDGET", "NON_MANIFOLD", "HOLES", "LOOSE_PARTS", "FLIPPED_NORMALS",
              "SLIVERS", "GROUND_SLAB", "NOT_GROUNDED", "ASYMMETRY", "BACK_COPY",
              "UV_OVERLAP", "LOW_TEXEL", "PALETTE_DRIFT", "BAKED_LIGHT",
              "TOO_MANY_INFLUENCES", "MULTI_MATERIAL", "TEXTURE_OVERSIZE"]
# fix op codes: fixkit OPS names (Task 10) plus the paid/engine rungs of the ladder (spec 13)
FIX_OPTIONS = {
    "OVER_BUDGET": ["tripo_decimate"],
    "NON_MANIFOLD": ["weld_boundary", "delete_region"],
    "HOLES": ["weld_boundary", "fill_holes"],
    "LOOSE_PARTS": ["remove_loose", "delete_region"],
    "FLIPPED_NORMALS": ["delete_region", "tripo_regenerate"],
    "SLIVERS": ["tripo_decimate", "tripo_regenerate"],
    "GROUND_SLAB": ["remove_ground_slab"],
    "NOT_GROUNDED": ["normalize", "delete_region"],
    "ASYMMETRY": ["mirror_half", "clone_part"],
    "BACK_COPY": ["flatten_region", "delete_region", "fill_holes", "tripo_retexture"],
    "UV_OVERLAP": ["tripo_retexture"],
    "LOW_TEXEL": ["tripo_retexture"],
    "PALETTE_DRIFT": ["recolour", "tripo_retexture"],
    "BAKED_LIGHT": ["tripo_retexture", "recolour"],
    "TOO_MANY_INFLUENCES": ["engine_side", "tripo_rig"],
    "MULTI_MATERIAL": ["engine_side", "separate_parts"],
    "TEXTURE_OVERSIZE": ["engine_side"],
}


# ---------------------------------------------------------------- helpers

def num(x, nd=4):
    """Round a finite number; NaN/inf/None -> None (sio.write refuses NaN)."""
    if x is None:
        return None
    x = float(x)
    return round(x, nd) if math.isfinite(x) else None


def clean(obj):
    """Recursively replace non-finite floats with None."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(obj) else None
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def pearson(a, b):
    if len(a) < 3:
        return None
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum()) / den if den > 0 else None


def components(n, a, b):
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


def srgb_to_lab(rgb):
    """(N, 3) sRGB in 0..1 -> CIE Lab (D65)."""
    c = np.clip(rgb, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]),
                     200 * (f[:, 1] - f[:, 2])], 1)


def kmeans(x, k, rng, iters=20):
    """(centres, weights) of a plain Lloyd k-means with k-means++ seeding."""
    k = min(k, len(x))
    centres = [x[rng.integers(len(x))]]
    for _ in range(1, k):
        d2 = np.min(((x[:, None, :] - np.array(centres)[None]) ** 2).sum(-1), 1)
        if d2.sum() <= 0:
            break
        centres.append(x[rng.choice(len(x), p=d2 / d2.sum())])
    c = np.array(centres)
    for _ in range(iters):
        lab = np.argmin(((x[:, None, :] - c[None]) ** 2).sum(-1), 1)
        for j in range(len(c)):
            sel = x[lab == j]
            if len(sel):
                c[j] = sel.mean(0)
    lab = np.argmin(((x[:, None, :] - c[None]) ** 2).sum(-1), 1)
    w = np.bincount(lab, minlength=len(c)) / len(x)
    return c, w


def image_pixels(img):
    """(h, w, 4) float32 pixels, downscaled to PIXEL_MAX on the long side; None if unreadable."""
    w, h = img.size
    if w == 0 or h == 0:
        return None
    src = img
    if max(w, h) > PIXEL_MAX:
        s = PIXEL_MAX / max(w, h)
        src = img.copy()
        src.scale(max(1, int(w * s)), max(1, int(h * s)))
    w2, h2 = src.size
    buf = np.empty(w2 * h2 * 4, np.float32)
    src.pixels.foreach_get(buf)
    if src is not img:
        bpy.data.images.remove(src)
    return buf.reshape(h2, w2, 4)


def base_color_image(mat):
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
    for n in nodes:
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image
    return None


# ---------------------------------------------------------------- gather

class Model:
    """Loaded data as numpy arrays (world space). Built once, never modified."""

    def __init__(self, meshes):
        self.meshes = meshes
        pos, cn, uv, has_uv, timg, raw_boundary = [], [], [], [], [], 0
        self.images, self.materials = [], []
        for o in meshes:
            me = o.data
            m = np.array(o.matrix_world, np.float64)
            nm = np.linalg.inv(m[:3, :3]).T
            co = _mesh.world_coords(o)
            me.calc_loop_triangles()
            nt = len(me.loop_triangles)
            tv = np.empty(nt * 3, np.int64)
            tl = np.empty(nt * 3, np.int64)
            tm = np.empty(nt, np.int64)
            me.loop_triangles.foreach_get("vertices", tv)
            me.loop_triangles.foreach_get("loops", tl)
            me.loop_triangles.foreach_get("material_index", tm)
            pos.append(co[tv].reshape(-1, 3, 3))
            n = np.empty(len(me.loops) * 3, np.float64)
            me.corner_normals.foreach_get("vector", n)
            cn.append((n.reshape(-1, 3)[tl] @ nm.T).reshape(-1, 3, 3))
            if me.uv_layers.active is not None:
                u = np.empty(len(me.loops) * 2, np.float64)
                me.uv_layers.active.data.foreach_get("uv", u)
                uv.append(u.reshape(-1, 2)[tl].reshape(-1, 3, 2))
                has_uv.append(np.ones(nt, bool))
            else:
                uv.append(np.zeros((nt, 3, 2)))
                has_uv.append(np.zeros(nt, bool))
            slot_img = []
            for slot in o.material_slots:
                mat = slot.material
                if mat is not None and mat not in self.materials:
                    self.materials.append(mat)
                img = base_color_image(mat)
                if img is not None and img not in self.images:
                    self.images.append(img)
                slot_img.append(self.images.index(img) if img is not None else -1)
            lut = np.array(slot_img or [-1], np.int64)
            timg.append(lut[np.clip(tm, 0, len(lut) - 1)])
            # raw (unwelded) boundary edges: edges used by exactly one face
            le = np.empty(len(me.loops), np.int64)
            me.loops.foreach_get("edge_index", le)
            raw_boundary += int((np.bincount(le, minlength=len(me.edges)) == 1).sum())
        cat = (lambda xs, shape: np.concatenate(xs) if xs else np.zeros(shape))
        self.pos = cat(pos, (0, 3, 3))
        self.cn = cat(cn, (0, 3, 3))
        self.uv = cat(uv, (0, 3, 2))
        self.has_uv = cat(has_uv, (0,)).astype(bool)
        self.timg = cat(timg, (0,)).astype(np.int64)
        self.raw_boundary = raw_boundary
        self.verts = sum(len(o.data.vertices) for o in meshes)
        self.lo, self.hi = _mesh.world_bbox(meshes)
        if self.lo is None:
            self.lo = self.hi = np.zeros(3)
        self.size = self.hi - self.lo
        self.diag = float(np.linalg.norm(self.size))
        cr = np.cross(self.pos[:, 1] - self.pos[:, 0], self.pos[:, 2] - self.pos[:, 0])
        self.area = 0.5 * np.linalg.norm(cr, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.fn = cr / (2 * self.area[:, None])
        self.fn[~np.isfinite(self.fn)] = 0.0
        self._pix = {}
        self._samples = None

    def pixels(self, i):
        if i not in self._pix:
            self._pix[i] = image_pixels(self.images[i])
        return self._pix[i]

    def samples(self):
        """Area-weighted surface samples: dict(p, tri, bary); empty when area is 0."""
        if self._samples is None:
            total = float(self.area.sum())
            if not total > 0:
                self._samples = {"p": np.zeros((0, 3)), "tri": np.zeros(0, np.int64),
                                 "bary": np.zeros((0, 3))}
            else:
                rng = np.random.default_rng(SEED)
                tri = rng.choice(len(self.area), SAMPLES, p=self.area / total)
                r1 = np.sqrt(rng.random(SAMPLES))
                r2 = rng.random(SAMPLES)
                bary = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
                p = (self.pos[tri] * bary[:, :, None]).sum(1)
                self._samples = {"p": p, "tri": tri, "bary": bary}
        return self._samples

    def sample_colours(self):
        """(rgb (N,3), tri (N,)) albedo at the textured samples; None when untextured."""
        s = self.samples()
        tri = s["tri"]
        ok = self.has_uv[tri] & (self.timg[tri] >= 0)
        if not ok.any():
            return None
        rgb = np.zeros((len(tri), 3), np.float32)
        good = np.zeros(len(tri), bool)
        for i in np.unique(self.timg[tri][ok]):
            pix = self.pixels(int(i))
            if pix is None:
                continue
            sel = ok & (self.timg[tri] == i)
            uv = (self.uv[tri[sel]] * s["bary"][sel][:, :, None]).sum(1) % 1.0
            h, w = pix.shape[:2]
            x = np.clip((uv[:, 0] * w).astype(np.int64), 0, w - 1)
            y = np.clip((uv[:, 1] * h).astype(np.int64), 0, h - 1)
            rgb[sel] = pix[y, x, :3]
            good[sel] = True
        if not good.any():
            return None
        return rgb[good], tri[good]


# ---------------------------------------------------------------- metrics

def topology(meshes, eps, diag):
    """Welded-copy metrics: verts_welded, boundary/non-manifold edges, islands, ground slab."""
    vco, tris, boundary, nonmanifold, offset = [], [], 0, 0, 0
    for o in meshes:
        bm = _mesh.welded_bmesh(o, eps)
        tmp = bpy.data.meshes.new("_qa_welded")
        bm.to_mesh(tmp)
        bm.free()
        try:
            co = np.empty(len(tmp.vertices) * 3, np.float64)
            tmp.vertices.foreach_get("co", co)
            le = np.empty(len(tmp.loops), np.int64)
            tmp.loops.foreach_get("edge_index", le)
            cnt = np.bincount(le, minlength=len(tmp.edges))
            boundary += int((cnt == 1).sum())
            nonmanifold += int((cnt > 2).sum())
            tmp.calc_loop_triangles()
            tv = np.empty(len(tmp.loop_triangles) * 3, np.int64)
            tmp.loop_triangles.foreach_get("vertices", tv)
        finally:
            bpy.data.meshes.remove(tmp)
        vco.append(co.reshape(-1, 3))
        tris.append(tv.reshape(-1, 3) + offset)
        offset += len(co) // 3
    co = np.concatenate(vco) if vco else np.zeros((0, 3))
    t = np.concatenate(tris) if tris else np.zeros((0, 3), np.int64)
    lab = components(len(co), np.concatenate([t[:, 0], t[:, 0]]),
                     np.concatenate([t[:, 1], t[:, 2]]))
    islands = []
    if len(t):
        roots, tri_lab = np.unique(lab[t[:, 0]], return_inverse=True)
        counts = np.bincount(tri_lab, minlength=len(roots))
        used = np.isin(lab, roots)  # loose vertices without a triangle are not an island
        vlab = np.searchsorted(roots, lab)
        lo = np.full((len(roots), 3), np.inf)
        hi = np.full((len(roots), 3), -np.inf)
        np.minimum.at(lo, vlab[used], co[used])
        np.maximum.at(hi, vlab[used], co[used])
        d = np.linalg.norm(hi - lo, axis=1)
        for j in np.argsort(-counts, kind="stable"):
            islands.append({"tris": int(counts[j]),
                            "bbox_pct": num(100 * d[j] / diag, 3) if diag > 0 else None})
    return {"verts_welded": len(co), "boundary_edges": boundary,
            "nonmanifold_edges": nonmanifold, "islands": islands, "co": co, "tris": t}


def ground_metrics(model, topo):
    lo, size = model.lo, model.size
    if not len(model.pos):
        return {"min_z": num(lo[2]), "low_band_tris_pct": None, "slab": False}
    band = lo[2] + GROUND_BAND * size[2]
    cz = model.pos[:, :, 2].mean(1)
    low_pct = 100.0 * float((cz <= band).mean())
    slab = False
    footprint = float(size[0] * size[1])
    co, t = topo["co"], topo["tris"]
    if footprint > 0 and len(t):
        inband = (co[t][:, :, 2] <= band).all(1)
        bt = t[inband]
        if len(bt):
            p = co[bt]
            cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
            up_area = np.where(cr[:, 2] > 0, 0.5 * cr[:, 2], 0.0)  # projected, upward only
            lab = components(len(co), np.concatenate([bt[:, 0], bt[:, 0]]),
                             np.concatenate([bt[:, 1], bt[:, 2]]))
            roots, tl = np.unique(lab[bt[:, 0]], return_inverse=True)
            up = np.bincount(tl, weights=up_area, minlength=len(roots))
            for j in np.nonzero(up >= SLAB_UP_AREA * footprint)[0]:
                q = p[tl == j].reshape(-1, 3)
                span = float(np.prod(q[:, :2].max(0) - q[:, :2].min(0)))
                if span >= SLAB_SPAN * footprint:
                    slab = True
                    break
    return {"min_z": num(lo[2]), "low_band_tris_pct": num(low_pct, 3), "slab": slab}


def flipped_pct(model):
    ok = model.area > 0
    if not ok.any():
        return None
    dots = (model.fn * model.cn.sum(1)).sum(1)
    return num(100.0 * float((dots[ok] < 0).mean()), 3)


def sliver_pct(model):
    if not len(model.pos):
        return None
    p = model.pos
    mins = np.full(len(p), np.pi)
    for i in range(3):
        a = p[:, (i + 1) % 3] - p[:, i]
        b = p[:, (i + 2) % 3] - p[:, i]
        den = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            cos = np.clip((a * b).sum(1) / den, -1, 1)
        ang = np.where(den > 0, np.arccos(cos), 0.0)
        mins = np.minimum(mins, ang)
    return num(100.0 * float((mins < math.radians(SLIVER_ANGLE_DEG)).mean()), 3)


def grid_nearest(points, queries, h, cap=24):
    """(distance, index) of each query's nearest point within the 27 cells around it
    (cell size h, at most `cap` points kept per cell); (inf, -1) when none is found."""
    best = np.full(len(queries), np.inf)
    arg = np.full(len(queries), -1, np.int64)
    if not len(points) or not len(queries):
        return best, arg
    pk = np.floor(points / h).astype(np.int64)
    qk = np.floor(queries / h).astype(np.int64)
    base = np.minimum(pk.min(0), qk.min(0)) - 1
    pk -= base
    qk -= base
    dims = np.maximum(pk.max(0), qk.max(0)) + 2

    def pack(k):
        return (k[:, 0] * dims[1] + k[:, 1]) * dims[2] + k[:, 2]

    key = pack(pk)
    order = np.argsort(key, kind="stable")
    uniq, start, cnt = np.unique(key[order], return_index=True, return_counts=True)
    rank = np.arange(len(order)) - np.repeat(start, cnt)
    keep = rank < cap
    table = np.full((len(uniq) + 1, cap), -1, np.int64)
    table[np.repeat(np.arange(len(uniq)), cnt)[keep], rank[keep]] = order[keep]
    pts = points.astype(np.float32)
    q32 = queries.astype(np.float32)
    offsets = [np.array([dx, dy, dz]) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
               for dz in (-1, 0, 1)]
    for chunk in range(0, len(queries), 8192):
        sl = slice(chunk, chunk + 8192)
        qc, qq = qk[sl], q32[sl]
        b = np.full(len(qq), np.inf)
        bi = np.full(len(qq), -1, np.int64)
        for off in offsets:
            k = pack(qc + off)
            i = np.searchsorted(uniq, k)
            i = np.where((i < len(uniq)) & (uniq[np.minimum(i, len(uniq) - 1)] == k),
                         i, len(uniq))
            cand = table[i]
            d2 = ((pts[np.maximum(cand, 0)] - qq[:, None, :]) ** 2).sum(-1)
            d2[cand < 0] = np.inf
            j = d2.argmin(1)
            dj = d2[np.arange(len(qq)), j]
            better = dj < b
            b[better] = dj[better]
            bi[better] = cand[np.arange(len(qq)), j][better]
        best[sl] = np.sqrt(b)
        arg[sl] = bi
    return best, arg


def nearest_points(points, queries, diag):
    """(distance, index) of the nearest point, via a coarse-to-fine cascade of hash
    grids: a result <= the cell size is exact; the rest go to the next, 4x coarser grid."""
    dist = np.full(len(queries), np.inf)
    idx = np.full(len(queries), -1, np.int64)
    todo = np.arange(len(queries))
    for h in (diag / 128, diag / 32, diag / 8, diag / 2):
        if not len(todo):
            break
        d, i = grid_nearest(points, queries[todo], h)
        better = d < dist[todo]
        dist[todo[better]] = d[better]
        idx[todo[better]] = i[better]
        todo = todo[dist[todo] > h]
    return dist, idx


def asymmetry(model, topo, declared):
    """Mean distance of X-mirrored welded vertices to the surface, % of the bbox diagonal.

    The surface is the area-weighted sample cloud; the distance to the nearest sample is
    refined to the distance from that sample's triangle plane, so sample spacing does
    not leak into the result (a symmetric mesh measures ~0, not ~spacing)."""
    if not declared:
        return {"axis": None, "mean_dist_pct": None}
    co = topo["co"]
    smp = model.samples()
    if not len(co) or not len(smp["p"]) or model.diag <= 0:
        return {"axis": "x", "mean_dist_pct": None}
    q = co
    if len(q) > QUERY_MAX:
        q = q[np.random.default_rng(SEED).choice(len(q), QUERY_MAX, replace=False)]
    q = q.copy()
    cx = 0.5 * (model.lo[0] + model.hi[0])
    q[:, 0] = 2 * cx - q[:, 0]
    d, i = nearest_points(smp["p"], q, model.diag)
    found = i >= 0
    n = model.fn[smp["tri"][i[found]]]
    plane = np.abs(((q[found] - smp["p"][i[found]]) * n).sum(1))
    # only the in-plane offset up to ~2 sample spacings is jitter; beyond that it is a gap
    spacing = math.sqrt(float(model.area.sum()) / len(smp["p"]))
    tangential = np.sqrt(np.maximum(d[found] ** 2 - plane ** 2, 0.0))
    refined = np.sqrt(plane ** 2 + np.maximum(tangential - 2 * spacing, 0.0) ** 2)
    d[found] = np.where((n ** 2).sum(1) > 0, refined, d[found])
    return {"axis": "x", "mean_dist_pct": num(100.0 * float(d.mean()) / model.diag, 4)}


def _box_blur(values, mask, r):
    """Mean of `values` over occupied cells in a (2r+1)^2 window (normalised convolution)."""
    def integral(a):
        s = np.zeros((a.shape[0] + 1, a.shape[1] + 1))
        s[1:, 1:] = a.cumsum(0).cumsum(1)
        return s

    def window(s):
        n, m = s.shape[0] - 1, s.shape[1] - 1
        i0 = np.clip(np.arange(n) - r, 0, n)
        i1 = np.clip(np.arange(n) + r + 1, 0, n)
        j0 = np.clip(np.arange(m) - r, 0, m)
        j1 = np.clip(np.arange(m) + r + 1, 0, m)
        return (s[i1][:, j1] - s[i0][:, j1] - s[i1][:, j0] + s[i0][:, j0])

    w = window(integral(mask.astype(np.float64)))
    v = window(integral(np.where(mask, values, 0.0)))
    with np.errstate(invalid="ignore", divide="ignore"):
        return v / w, w


def back_relief(model, front):
    """Similarity (0..1) of the front and back relief seen along the front axis.

    Depth maps come from surface samples binned on a grid perpendicular to the front
    axis; each is high-passed (minus a 9x9 local mean), the silhouette border is
    eroded away, and the Pearson correlation is taken both as-is (back mirrored
    through the side plane) and flipped left/right (back pasted as seen from behind).
    A flat or featureless side gives 0."""
    s = model.samples()["p"]
    if not len(s) or model.diag <= 0:
        return None
    sign = -1.0 if front[0] == "-" else 1.0
    ax = "xyz".index(front[1])
    side = 1 if ax == 0 else 0  # horizontal axis in the view plane
    d = sign * s[:, ax]
    u, v = s[:, side], s[:, 2]
    ext = max(model.size[side], model.size[2])
    if ext <= 0:
        return None
    cell = ext / DEPTH_GRID
    nu = max(1, int(math.ceil(model.size[side] / cell)))
    nv = max(1, int(math.ceil(model.size[2] / cell)))
    iu = np.clip(((u - model.lo[side]) / cell).astype(np.int64), 0, nu - 1)
    iv = np.clip(((v - model.lo[2]) / cell).astype(np.int64), 0, nv - 1)
    flat = iu * nv + iv
    front_map = np.full(nu * nv, -np.inf)
    back_map = np.full(nu * nv, -np.inf)
    np.maximum.at(front_map, flat, d)
    np.maximum.at(back_map, flat, -d)
    front_map = front_map.reshape(nu, nv)
    back_map = back_map.reshape(nu, nv)
    mask = np.isfinite(front_map)
    r = max(2, DEPTH_GRID // 16)
    hp_f = front_map - _box_blur(front_map, mask, r)[0]
    hp_b = back_map - _box_blur(back_map, mask, r)[0]
    _, cover = _box_blur(np.zeros_like(front_map), mask, r)
    interior = mask & (cover >= (2 * r + 1) ** 2)  # eroded: full window inside
    floor = 2e-3 * model.diag  # relief below this is "flat"
    best = 0.0
    for hb, ib in ((hp_b, interior), (hp_b[::-1], interior[::-1])):
        m = interior & ib
        if m.sum() < 25:
            continue
        a, b = hp_f[m], hb[m]
        if a.std() < floor or b.std() < floor:
            continue
        c = pearson(a, b)
        if c is not None:
            best = max(best, c)
    return num(min(1.0, max(0.0, best)), 4)


def uv_metrics(model):
    ok = model.has_uv & (model.area > 0)
    if not ok.any():
        return {"overlap_pct": None, "oob_pct": None}
    uv = model.uv[ok]
    eps = 1e-3
    oob = ((uv < -eps) | (uv > 1 + eps)).any(axis=(1, 2))
    shift = np.floor(uv.min(1))  # tile each triangle back into 0..1
    g = (uv - shift[:, None, :]) * UV_GRID
    groups = model.timg[ok]
    covered, multi = 0, 0
    for img in np.unique(groups):
        tri = g[groups == img]
        counts = np.zeros(UV_GRID * UV_GRID, np.int64)
        x0 = np.clip(np.floor(tri[:, :, 0].min(1)).astype(np.int64), 0, UV_GRID - 1)
        x1 = np.clip(np.floor(tri[:, :, 0].max(1)).astype(np.int64), 0, UV_GRID - 1)
        y0 = np.clip(np.floor(tri[:, :, 1].min(1)).astype(np.int64), 0, UV_GRID - 1)
        y1 = np.clip(np.floor(tri[:, :, 1].max(1)).astype(np.int64), 0, UV_GRID - 1)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        n = w * h
        ends = np.cumsum(n)
        lo = 0
        while lo < len(tri):  # chunks of ~4M candidate cells
            done = int(ends[lo - 1]) if lo else 0
            hi = max(lo + 1, int(np.searchsorted(ends, done + 4_000_000, side="right")))
            nn = n[lo:hi]
            idx = np.repeat(np.arange(lo, hi), nn)
            local = np.arange(len(idx)) - np.repeat(np.cumsum(nn) - nn, nn)
            cx = x0[idx] + local % w[idx]
            cy = y0[idx] + local // w[idx]
            px, py = cx + 0.5, cy + 0.5
            t = tri[idx]
            e = []
            for i in range(3):
                a, b = t[:, i], t[:, (i + 1) % 3]
                e.append((b[:, 0] - a[:, 0]) * (py - a[:, 1])
                         - (b[:, 1] - a[:, 1]) * (px - a[:, 0]))
            e = np.stack(e, 1)
            inside = (e > 0).all(1) | (e < 0).all(1)
            np.add.at(counts, (cy * UV_GRID + cx)[inside], 1)
            lo = hi
        covered += int((counts >= 1).sum())
        multi += int((counts >= 2).sum())
    return {"overlap_pct": num(100.0 * multi / covered, 3) if covered else None,
            "oob_pct": num(100.0 * float(oob.mean()), 3)}


def texel_density(model):
    ok = model.has_uv & (model.timg >= 0) & (model.area > 0)
    if not ok.any():
        return None
    uv = model.uv[ok]
    uv_area = 0.5 * np.abs(np.cross(uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]))
    wh = np.array([img.size[0] * img.size[1] for img in model.images], np.float64)
    px_area = uv_area * wh[model.timg[ok]]
    good = px_area > 0
    if not good.any():
        return None
    return num(float(np.median(np.sqrt(px_area[good] / model.area[ok][good]))), 1)


def palette(model, ref_path, rng):
    if not ref_path:
        return None
    sc = model.sample_colours()
    if sc is None:
        return {"delta_e_mean": None, "chroma_ratio": None}
    img = bpy.data.images.load(os.path.abspath(ref_path), check_existing=False)
    try:
        pix = image_pixels(img)
    finally:
        bpy.data.images.remove(img)
    if pix is None:
        raise ValueError(f"reference palette image is unreadable: {ref_path}")
    h, w = pix.shape[:2]
    rgb = pix[:, :, :3].reshape(-1, 3)
    alpha = pix[:, :, 3].reshape(-1)
    ring = max(1, min(h, w) // 50)
    border = np.concatenate([pix[:ring, :, :3].reshape(-1, 3), pix[-ring:, :, :3].reshape(-1, 3),
                             pix[:, :ring, :3].reshape(-1, 3), pix[:, -ring:, :3].reshape(-1, 3)])
    bg = np.median(border, 0)
    fg = (alpha > 0.5) & (np.linalg.norm(rgb - bg, axis=1) > 0.15)
    if fg.sum() < 50:
        return {"delta_e_mean": None, "chroma_ratio": None}

    def sub(x):
        return x[rng.choice(len(x), 20_000, replace=False)] if len(x) > 20_000 else x
    ref_lab = srgb_to_lab(sub(rgb[fg]).astype(np.float64))
    mod_lab = srgb_to_lab(sub(sc[0]).astype(np.float64))
    rc, rw = kmeans(ref_lab, KMEANS_K, rng)
    mc, mw = kmeans(mod_lab, KMEANS_K, rng)
    dist = np.linalg.norm(rc[:, None, :] - mc[None], axis=2)
    de = 0.5 * (float((dist.min(1) * rw).sum()) + float((dist.min(0) * mw).sum()))
    chroma_ref = float(np.hypot(ref_lab[:, 1], ref_lab[:, 2]).mean())
    chroma_mod = float(np.hypot(mod_lab[:, 1], mod_lab[:, 2]).mean())
    return {"delta_e_mean": num(de, 2),
            "chroma_ratio": num(chroma_mod / chroma_ref, 3) if chroma_ref > 0 else None}


def baked_light(model):
    sc = model.sample_colours()
    if sc is None:
        return {"score": None}
    rgb, tri = sc
    lum = srgb_to_lab(rgb.astype(np.float64))[:, 0]
    return {"score": num(pearson(lum, model.fn[tri, 2]), 4)}


def skin_metrics(objs, meshes):
    arms = [o for o in objs if o.type == "ARMATURE"]
    joints = sum(len(a.data.bones) for a in arms)
    bones = {b.name for a in arms for b in a.data.bones}
    most = 0
    for o in meshes:
        idx = {g.index for g in o.vertex_groups if g.name in bones}
        if not idx:
            continue
        for v in o.data.vertices:
            n = sum(1 for g in v.groups if g.group in idx and g.weight > 0)
            most = max(most, n)
    return {"joints": joints, "max_influences": most}


# ---------------------------------------------------------------- findings

def findings(metrics, islands, a, th):
    """Findings sorted by severity; `islands` is the full list (metrics holds the top 32)."""
    sev = th["severity"]
    out = []

    def add(code, value, threshold, message, severity=None):
        severity = severity or sev[code]
        if severity not in SEVERITY_RANK:  # "rule" belongs to computed codes only
            severity = "info"
        out.append({"code": code, "severity": severity, "message": message,
                    "value": value, "threshold": threshold,
                    "fix_options": list(FIX_OPTIONS[code])})

    m = metrics
    tris = m["tris"]
    if a.budget:
        ratio = tris / a.budget
        if ratio > th["over_budget_s0"]:
            s = "S0"
        elif ratio > th["over_budget_s1"]:
            s = "S1"
        elif ratio > 1.0:
            s = "info"
        else:
            s = None
        if s:
            add("OVER_BUDGET", tris, a.budget,
                f"{tris} triangles for a budget of {a.budget} ({ratio:.2f}x)", s)
    if m["nonmanifold_edges"] > th["nonmanifold_edges_max"]:
        add("NON_MANIFOLD", m["nonmanifold_edges"], th["nonmanifold_edges_max"],
            f"{m['nonmanifold_edges']} edges shared by 3+ faces after weld")
    if m["boundary_edges"] > th["boundary_edges_max"]:
        add("HOLES", m["boundary_edges"], th["boundary_edges_max"],
            f"{m['boundary_edges']} open (boundary) edges after weld")
    if tris:
        loose = sum(1 for i in islands[1:] if 100.0 * i["tris"] / tris < th["loose_tris_pct"])
        if loose > th["loose_parts_max"]:
            add("LOOSE_PARTS", loose, th["loose_parts_max"],
                f"{loose} separate pieces under {th['loose_tris_pct']}% of the triangles each")
    checks = [
        ("FLIPPED_NORMALS", m["flipped_pct"], "flipped_pct_max", ">",
         "% of triangles wind against their stored normals"),
        ("SLIVERS", m["sliver_pct"], "sliver_pct_max", ">",
         f"% of triangles have a corner under {SLIVER_ANGLE_DEG:g} degrees"),
        ("NOT_GROUNDED", m["ground"]["low_band_tris_pct"], "low_band_tris_pct_min", "<",
         "% of triangles lie in the bottom 3% of the height (the model rests on a point)"),
        ("ASYMMETRY", m["asymmetry"]["mean_dist_pct"], "asymmetry_pct_max", ">",
         "% of the bbox diagonal: mean distance of X-mirrored vertices to the surface"),
        ("BACK_COPY", m["back_relief"], "back_relief_max", ">",
         " similarity of front and back relief (front detail copied to the back?)"),
        ("UV_OVERLAP", m["uv"]["overlap_pct"], "uv_overlap_pct_max", ">",
         "% of used UV texels are covered by more than one triangle"),
        ("LOW_TEXEL", m["texel_density"], "texel_density_min", "<",
         " px per model unit (median texel density)"),
        ("PALETTE_DRIFT", (m["palette"] or {}).get("delta_e_mean"), "palette_delta_e_max", ">",
         " mean delta E between the texture and the reference palette"),
        ("BAKED_LIGHT", m["baked_light"]["score"], "baked_light_max", ">",
         " correlation of albedo brightness with upward normals (baked light?)"),
    ]
    for code, value, key, op, text in checks:
        if value is None:
            continue
        limit = th[key]
        if (value > limit) if op == ">" else (value < limit):
            add(code, value, limit, f"{value:g}{text}")
    if m["ground"]["slab"]:
        add("GROUND_SLAB", True, None,
            "a thin connected sheet in the bottom 3% of the height spans >= 60% of the footprint")
    if m["skin"]["max_influences"] > th["influences_max"]:
        add("TOO_MANY_INFLUENCES", m["skin"]["max_influences"], th["influences_max"],
            f"a vertex has {m['skin']['max_influences']} bone weights")
    if m["materials"] > th["materials_max"]:
        add("MULTI_MATERIAL", m["materials"], th["materials_max"],
            f"{m['materials']} materials")
    big = max((max(i["w"], i["h"]) for i in m["images"]), default=0)
    if big > th["texture_max_px"]:
        add("TEXTURE_OVERSIZE", big, th["texture_max_px"], f"largest texture is {big} px")

    out.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], CODE_ORDER.index(f["code"])))
    return [{"id": f"F{i}", **f} for i, f in enumerate(out, 1)]


# ---------------------------------------------------------------- main

def cfg(p):
    p.add_argument("model")
    p.add_argument("--budget", type=int)
    p.add_argument("--symmetric", choices=("x", "none"), default="none")
    p.add_argument("--front", choices=("-y", "+y", "-x", "+x"), default="-y")
    p.add_argument("--ref-palette")
    p.add_argument("--class", dest="asset_class")
    p.add_argument("--thresholds", default=DEFAULT_THRESHOLDS)


def run(a):
    if a.budget is not None and a.budget <= 0:
        raise ValueError(f"--budget must be positive, got {a.budget}")
    if a.ref_palette and not os.path.isfile(a.ref_palette):
        raise FileNotFoundError(f"reference palette not found: {a.ref_palette}")
    with open(a.thresholds, encoding="utf-8") as f:
        th = json.load(f)["qa"]
    path = os.path.abspath(a.model)
    objs = sio.load_model(path)
    meshes = _mesh.model_meshes(objs)
    model = Model(meshes)
    eps = _mesh.weld_eps(meshes)
    topo = topology(meshes, eps, model.diag)
    rng = np.random.default_rng(SEED)
    metrics = {
        "tris": int(len(model.pos)),
        "verts": model.verts,
        "verts_welded": topo["verts_welded"],
        "meshes": len(meshes),
        "materials": len(model.materials),
        "images": [{"name": i.name, "w": int(i.size[0]), "h": int(i.size[1])}
                   for i in bpy.data.images if i.type == "IMAGE" and i.size[0] > 0],
        "bbox": {"min": [num(x, 6) for x in model.lo], "max": [num(x, 6) for x in model.hi],
                 "size": [num(x, 6) for x in model.size]},
        "weld_eps": eps,
        "boundary_edges": topo["boundary_edges"],
        "boundary_edges_raw": model.raw_boundary,
        "nonmanifold_edges": topo["nonmanifold_edges"],
        "island_count": len(topo["islands"]),
        "islands": topo["islands"][:ISLANDS_LISTED],
        "flipped_pct": flipped_pct(model),
        "sliver_pct": sliver_pct(model),
        "ground": ground_metrics(model, topo),
        "asymmetry": asymmetry(model, topo, a.symmetric == "x"),
        "back_relief": back_relief(model, a.front),
        "front": a.front,
        "uv": uv_metrics(model),
        "texel_density": texel_density(model),
        "palette": palette(model, a.ref_palette, rng),
        "baked_light": baked_light(model),
        "skin": skin_metrics(objs, meshes),
    }
    metrics = clean(metrics)
    return {"schema": SCHEMA, "file": path, "format": sio.sniff(path),
            "class": a.asset_class, "metrics": metrics,
            "findings": findings(metrics, topo["islands"], a, th)}


sio.main(run, cfg)
