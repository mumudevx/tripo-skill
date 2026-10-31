"""Pixel checks for preflight_ref.py (run through bl.py; numpy is only available here).

    --image <path> (repeatable)  --views auto|single|sheet  --bg auto|#rrggbb
    --thresholds <qa_thresholds.json>

Returns {"images": [...], "views": [...], "checks": [...]}. Codes made here:
LOW_RES, MULTI_OBJECT, TWO_ROWS, LR_COPY, BACK_COPY, CHROMA_INSIDE, GROUND_LINE,
NON_PLAIN_BG and the info code LAYOUT. FAKE_FORMAT is the driver's (magic bytes).

Pipeline per image: background = mode colour of the border pixels (or --bg); foreground =
colour distance > fg_distance; blobs = connected components (run-length union-find on a
<= work_px mask); fragments whose boxes overlap are merged; a thin band joining or
underlining the views is stripped as a ground line; rows = vertical bbox overlap; a row
whose blob heights differ (ortho views share one height) and that holds a cut-out blob
(straight top/left/right edge, or touching the image edge) is a detail-panel row;
views = the remaining blobs, rows top to bottom, each row left to right.
"""
import json
import os
import re

import bpy
import numpy as np

import skill_io as sio

ROLES = ("front", "left", "back", "right")


def cfg(p):
    p.add_argument("--image", action="append", required=True)
    p.add_argument("--views", choices=("auto", "single", "sheet"), default="auto")
    p.add_argument("--bg", default="auto")
    p.add_argument("--thresholds", required=True)


# ---------------------------------------------------------------- loading

def load(path, hi_px, work_px):
    """(W, H, hi_rgb, hi_alpha, work_rgb, work_alpha); arrays are top-down, 0..255."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        W, H = img.size
        if W == 0 or H == 0:
            raise ValueError(f"cannot decode image: {path}")
        out = []
        for long_px in (hi_px, work_px):
            s = long_px / max(W, H)
            if s < 1 and max(img.size) > long_px:
                img.scale(max(1, round(W * s)), max(1, round(H * s)))
            w, h = img.size
            a = np.empty(w * h * 4, np.float32)
            img.pixels.foreach_get(a)
            a = a.reshape(h, w, 4)[::-1] * 255.0
            out += [a[..., :3].copy(), a[..., 3].copy()]
        return (W, H, *out)
    finally:
        bpy.data.images.remove(img)


def parse_hex(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def to_hex(c):
    return "#" + "".join(f"{int(round(float(v))):02x}" for v in c)


def border(a):
    return np.concatenate([a[0], a[-1], a[1:-1, 0], a[1:-1, -1]])


def background(rgb, override):
    """Mode colour of the border pixels (16-level bins, then the mean inside the bin)."""
    if override is not None:
        return override
    b = border(rgb)
    q = (b // 16).astype(np.int32)
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    return b[key == vals[counts.argmax()]].mean(axis=0)


# ---------------------------------------------------------------- labelling

def label(mask):
    """Connected components (8-connected) via union-find over horizontal runs.

    Returns (L, comps): L is an int32 image (0 = none), comps a list of dicts
    {"id", "area", "bbox": [x0, y0, x1, y1]} with exclusive x1/y1.
    """
    h, w = mask.shape
    pad = np.zeros((h, w + 2), np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    ys, xs = np.nonzero(d == 1)
    _, xe = np.nonzero(d == -1)
    n = len(ys)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    starts = np.searchsorted(ys, np.arange(h + 1)).tolist()
    xs_l, xe_l = xs.tolist(), xe.tolist()
    for y in range(1, h):
        i, i_end = starts[y - 1], starts[y]
        j, j_end = starts[y], starts[y + 1]
        while i < i_end and j < j_end:
            # 8-connectivity: runs touch diagonally when [s, e) ranges are adjacent
            if xs_l[i] <= xe_l[j] and xs_l[j] <= xe_l[i]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
            if xe_l[i] < xe_l[j]:
                i += 1
            else:
                j += 1
    L = np.zeros((h, w), np.int32)
    if n == 0:
        return L, []
    roots = np.array([find(i) for i in range(n)])
    _, lab = np.unique(roots, return_inverse=True)
    k = int(lab.max()) + 1
    area = np.bincount(lab, weights=xe - xs, minlength=k)
    x0 = np.full(k, w)
    np.minimum.at(x0, lab, xs)
    x1 = np.zeros(k, np.int64)
    np.maximum.at(x1, lab, xe)
    y0 = np.full(k, h)
    np.minimum.at(y0, lab, ys)
    y1 = np.zeros(k, np.int64)
    np.maximum.at(y1, lab, ys + 1)
    for y, s, e, l in zip(ys.tolist(), xs_l, xe_l, (lab + 1).tolist()):
        L[y, s:e] = l
    comps = [{"id": i + 1, "area": int(area[i]),
              "bbox": [int(x0[i]), int(y0[i]), int(x1[i]), int(y1[i])]} for i in range(k)]
    return L, comps


def box_area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def box_overlap(a, b):
    return box_area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def box_union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def blobs_from(mask, t):
    """Significant components, with overlapping fragments merged into one blob."""
    L, comps = label(mask)
    if not comps:
        return L, []
    largest = max(c["area"] for c in comps)
    keep = [c for c in comps
            if c["area"] >= max(t["min_blob_image_frac"] * mask.size,
                                t["min_blob_largest_frac"] * largest)]
    blobs = [{"ids": [c["id"]], "area": c["area"], "bbox": list(c["bbox"])} for c in keep]
    merged = True
    while merged:
        merged = False
        for i in range(len(blobs)):
            for j in range(i + 1, len(blobs)):
                a, b = blobs[i], blobs[j]
                small = min(box_area(a["bbox"]), box_area(b["bbox"])) or 1
                if box_overlap(a["bbox"], b["bbox"]) >= t["merge_overlap"] * small:
                    a["ids"] += b["ids"]
                    a["area"] += b["area"]
                    a["bbox"] = box_union(a["bbox"], b["bbox"])
                    del blobs[j]
                    merged = True
                    break
            if merged:
                break
    return L, blobs


def blob_mask(L, blob, box=None):
    x0, y0, x1, y1 = box or blob["bbox"]
    return np.isin(L[y0:y1, x0:x1], blob["ids"])


# ---------------------------------------------------------------- ground line

def runs_1d(v):
    """[start, end) of True runs in a 1-D bool array."""
    d = np.diff(np.concatenate([[0], v.astype(np.int8), [0]]))
    return list(zip(np.nonzero(d == 1)[0].tolist(), np.nonzero(d == -1)[0].tolist()))


def find_ground_band(m, t):
    """A thin, (nearly) full-width band in the bottom zone of blob mask `m`.

    Counts only when it joins several column groups (views standing on one line) or
    sticks out on both sides of what stands on it (a slab). Returns (r0, r1) or None.
    """
    h, w = m.shape
    fill = m.mean(axis=1)
    zone = int(h * (1 - t["ground_zone"]))
    for r0, r1 in runs_1d(fill >= t["ground_fill"]):
        if r1 <= zone or (r1 - r0) > max(1, t["ground_max_h_frac"] * h):
            continue
        above = m[:r0].any(axis=0)
        groups = runs_1d(above)
        if len(groups) >= 2:
            return r0, r1
        if groups:
            cx0, cx1 = groups[0][0], groups[-1][1]
            if cx0 >= t["ground_overhang"] * w and (w - cx1) >= t["ground_overhang"] * w:
                return r0, r1
    return None


def strip_ground(mask, t):
    """Remove ground bands from the mask; returns (mask, bands as work-px boxes)."""
    L, blobs = blobs_from(mask, t)
    bands = []
    if not blobs:
        return mask, bands
    tallest = max(b["bbox"][3] - b["bbox"][1] for b in blobs)
    for b in blobs:
        x0, y0, x1, y1 = b["bbox"]
        bh, bw = y1 - y0, x1 - x0
        others = [o for o in blobs if o is not b]
        # a separate thin line under everything else
        if others and bh <= t["ground_max_h_frac"] * tallest:
            ux0 = min(o["bbox"][0] for o in others)
            ux1 = max(o["bbox"][2] for o in others)
            under = y0 >= np.median([(o["bbox"][1] + o["bbox"][3]) / 2 for o in others])
            if under and bw >= (1 - t["ground_overhang"]) * (ux1 - ux0) and bw > 4 * bh:
                bands.append([x0, y0, x1, y1])
                mask[y0:y1, x0:x1] &= ~blob_mask(L, b)
                continue
        band = find_ground_band(blob_mask(L, b), t)
        if band:
            r0, r1 = band[0] + y0, band[1] + y0
            bands.append([x0, r0, x1, r1])
            mask[max(0, r0 - 1):r1 + 1, x0:x1] = False
    return mask, bands


# ---------------------------------------------------------------- layout

def longest_run(v):
    r = runs_1d(v)
    return max((e - s for s, e in r), default=0)


def is_clipped(L, blob, shape, t):
    """Looks cut out of a bigger picture: touches the image edge, or its top, left or
    right side is one straight edge over most of its length (the bottom is left out:
    objects standing on the ground have flat bottoms)."""
    x0, y0, x1, y1 = blob["bbox"]
    h, w = shape
    if x0 == 0 or y0 == 0 or x1 == w or y1 == h:
        return True
    m = blob_mask(L, blob)
    if min(m.shape) < 6:
        return False
    sides = (longest_run(m[:3].any(axis=0)) / m.shape[1],
             longest_run(m[:, :3].any(axis=1)) / m.shape[0],
             longest_run(m[:, -3:].any(axis=1)) / m.shape[0])
    return max(sides) >= t["clip_side_run"]


def is_detail_row(L, row, shape, t):
    """Close-up panels, not views: ortho views of one object share one height, a strip of
    cut-out close-ups does not, and at least one of them is visibly cut."""
    hs = [b["bbox"][3] - b["bbox"][1] for b in row["blobs"]]
    return (max(hs) / max(1, min(hs)) > t["view_height_ratio"]
            and any(is_clipped(L, b, shape, t) for b in row["blobs"]))


def group_rows(blobs, t):
    rows = []
    for b in sorted(blobs, key=lambda b: b["bbox"][1]):
        y0, y1 = b["bbox"][1], b["bbox"][3]
        for r in rows:
            ov = min(y1, r["y1"]) - max(y0, r["y0"])
            if ov >= t["row_overlap"] * min(y1 - y0, r["y1"] - r["y0"]):
                r["blobs"].append(b)
                r["y0"], r["y1"] = min(r["y0"], y0), max(r["y1"], y1)
                break
        else:
            rows.append({"y0": y0, "y1": y1, "blobs": [b]})
    rows.sort(key=lambda r: r["y0"])
    for r in rows:
        r["blobs"].sort(key=lambda b: b["bbox"][0])
    return rows


# ---------------------------------------------------------------- similarity

def resize(a, n):
    """Area-average down (nearest up) to n x n along the first two axes."""
    a = a.astype(np.float32)
    for axis in (0, 1):
        size = a.shape[axis]
        if size >= n:
            edges = (np.arange(n) * size) // n
            counts = np.diff(np.append(edges, size)).astype(np.float32)
            shape = [1] * a.ndim
            shape[axis] = n
            a = np.add.reduceat(a, edges, axis=axis) / counts.reshape(shape)
        else:
            a = np.take(a, ((np.arange(n) + 0.5) * size / n).astype(int), axis=axis)
    return a


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


def pixel_sim(ra, rb, ma, mb):
    both = ma & mb
    if not both.any():
        return 0.0
    return float(1 - np.abs(ra[both] - rb[both]).mean() / 255.0)


def compare(va, vb):
    """Silhouette IoU (plain and with b mirrored) and pixel similarity (plain)."""
    return {"iou": round(iou(va["sil"], vb["sil"]), 4),
            "iou_mirrored": round(iou(va["sil"], vb["sil"][:, ::-1]), 4),
            "pixel": round(pixel_sim(va["px"], vb["px"], va["sil"], vb["sil"]), 4)}


# ---------------------------------------------------------------- per-image analysis

def erode(m, r):
    for _ in range(r):
        e = m.copy()
        e[1:] &= m[:-1]
        e[:-1] &= m[1:]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        m = e
    return m


def dilate(m, r):
    return ~erode(~m, r)


def analyse(path, t, bg_override):
    W, H, hi_rgb, hi_a, rgb, alpha = load(path, t["hi_px"], t["work_px"])
    h, w = rgb.shape[:2]
    transparent = float((border(alpha) < 128).mean()) > 0.5
    bg = background(rgb, bg_override)
    dist = np.linalg.norm(rgb - bg, axis=2)
    mask = (alpha >= 128) if transparent else (dist > t["fg_distance"]) & (alpha >= 128)
    mask, bands = strip_ground(mask, t)
    L, blobs = blobs_from(mask, t)
    rows = group_rows(blobs, t)
    detail = [r for r in rows if is_detail_row(L, r, (h, w), t)]
    view_rows = [r for r in rows if r not in detail] or rows
    if len(view_rows) == len(rows):
        detail = []
    views = [b for r in view_rows for b in r["blobs"]]

    # silhouettes and pixels at hi resolution for the copy checks
    sx, sy = hi_rgb.shape[1] / w, hi_rgb.shape[0] / h
    for b in views:
        x0, y0, x1, y1 = b["bbox"]
        X0, Y0 = int(x0 * sx), int(y0 * sy)
        X1, Y1 = max(X0 + 1, int(np.ceil(x1 * sx))), max(Y0 + 1, int(np.ceil(y1 * sy)))
        crop, ca = hi_rgb[Y0:Y1, X0:X1], hi_a[Y0:Y1, X0:X1]
        if transparent:
            cm = ca >= 128
        else:
            cm = (np.linalg.norm(crop - bg, axis=2) > t["fg_distance"]) & (ca >= 128)
        b["sil"] = resize(cm, t["sim_px"]) >= 0.5
        b["px"] = resize(crop, t["sim_px"])

    # enclosed background (holes) and bg-tinted pixels inside each view
    _, holes = label(~mask)
    hole_area = {id(b): 0 for b in views}
    for c in holes:
        hb = c["bbox"]
        if (hb[0] == 0 or hb[1] == 0 or hb[2] == w or hb[3] == h
                or c["area"] < t["hole_min_px"]):
            continue
        for b in views:
            if box_overlap(hb, b["bbox"]) == box_area(hb):
                hole_area[id(b)] += c["area"]
                break
    # chroma key: pixels whose dominant channel is the background's, by a clear margin
    chroma = np.ptp(bg) >= t["chroma_min_saturation"] and not transparent
    k = int(np.argmax(bg)) if chroma else 0
    others = [c for c in range(3) if c != k]
    for b in views:
        x0, y0, x1, y1 = b["bbox"]
        b["holes_frac"] = hole_area[id(b)] / max(1, b["area"])
        b["tint_frac"] = 0.0
        if chroma:
            # a see-through part is one coherent tinted patch, not spill along the edges
            inner = erode(blob_mask(L, b), t["chroma_erode_px"])
            px = rgb[y0:y1, x0:x1]
            lead = px[..., k] - px[..., others].max(axis=2)
            _, patches = label(inner & (lead >= t["chroma_tint_margin"]))
            biggest = max((c["area"] for c in patches), default=0)
            b["tint_frac"] = biggest / max(1, b["area"])

    # background flatness: border spread, and soft (not bg, not object) pixels
    if transparent:
        border_p90, soft_frac = 0.0, 0.0
    else:
        bd = np.linalg.norm(border(rgb) - bg, axis=1)
        bd = bd[bd <= t["fg_distance"]]          # objects cut by the edge are not background
        border_p90 = float(np.percentile(bd, 90)) if len(bd) else 0.0
        bgpix = ~dilate(dist > t["fg_distance"], 3)
        soft = bgpix & (dist > t["bg_soft_distance"])
        soft_frac = float(soft.sum() / max(1, bgpix.sum()))

    return {"W": W, "H": H, "w": w, "h": h, "bg": None if transparent else bg,
            "views": views, "detail": [b for r in detail for b in r["blobs"]],
            "rows": len(view_rows), "bands": bands, "border_p90": border_p90,
            "soft_frac": soft_frac, "scale": W / w}


# ---------------------------------------------------------------- checks

def name_role(path):
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    for r in ROLES:
        if re.search(rf"(^|[^a-z]){r}([^a-z]|$)", stem):
            return r
    return None


def check(code, level, message, **evidence):
    return {"code": code, "level": level, "message": message, "evidence": evidence}


def run(a):
    with open(a.thresholds, encoding="utf-8") as f:
        t = json.load(f)["preflight"]
    override = None if a.bg == "auto" else parse_hex(a.bg)
    multi = len(a.image) > 1
    declared = 1 if a.views == "single" or (a.views == "auto" and multi) \
        else t["sheet_max_views"]
    images, views, checks = [], [], []
    hinted = [name_role(p) for p in a.image] if multi else [None]
    free = [r for r in ROLES if r not in hinted]

    for ii, path in enumerate(a.image):
        r = analyse(path, t, override)
        images.append({"path": path, "width": r["W"], "height": r["H"],
                       "bg": "transparent" if r["bg"] is None else to_hex(r["bg"])})
        s = r["scale"]
        px = lambda box: [int(round(v * s)) for v in box]  # noqa: E731
        n = len(r["views"])
        if n == 0:
            checks.append(check("MULTI_OBJECT", "fail", "no object found in the image",
                                image=ii, objects=0))
            continue
        if n > declared:
            checks.append(check(
                "MULTI_OBJECT", "fail",
                f"{n} separate objects but {declared} view(s) expected: image-to-3D fuses "
                "them into one mesh; give one object (or one view per image)",
                image=ii, objects=n, declared=declared,
                bboxes=[px(b["bbox"]) for b in r["views"]]))
        if r["rows"] > 1:
            checks.append(check(
                "TWO_ROWS", "warn",
                f"views sit on {r['rows']} rows: split them into one row (or one file per "
                "view) before generation; view roles below assume row-major order",
                image=ii, rows=r["rows"]))
        if r["bands"]:
            checks.append(check(
                "GROUND_LINE", "warn",
                "a horizontal line or slab runs under the views: Tripo builds it as a ground "
                "plate; remove it unless it is part of the object",
                image=ii, bands=[px(b) for b in r["bands"]]))
        if r["border_p90"] > t["bg_border_p90"] or r["soft_frac"] > t["bg_soft_max_frac"]:
            checks.append(check(
                "NON_PLAIN_BG", "warn",
                "background is not one flat colour (gradient, shadow or texture): regenerate "
                "on a plain background without shadows",
                image=ii, border_p90=round(r["border_p90"], 1),
                soft_frac=round(r["soft_frac"], 4)))
        info = {"image": ii, "views": n, "rows": r["rows"], "declared": declared}
        if r["detail"]:
            info["detail_panels"] = [px(b["bbox"]) for b in r["detail"]]
        checks.append(check("LAYOUT", "info",
                            f"{n} view(s) on {r['rows']} row(s)"
                            + (f", {len(r['detail'])} detail panel(s) ignored"
                               if r["detail"] else ""), **info))
        for vi, b in enumerate(r["views"]):
            if multi:   # one view per file: the file name (or the free order) gives the role
                role = (hinted[ii] or (free.pop(0) if free else None)) if vi == 0 else None
            else:
                role = ROLES[vi] if vi < len(ROLES) else None
            box = px(b["bbox"])
            views.append({"index": len(views), "image": ii, "role": role, "bbox_px": box,
                          "width": box[2] - box[0], "height": box[3] - box[1], "_blob": b})

    low = [{"view": v["index"], "long_px": max(v["width"], v["height"])} for v in views
           if max(v["width"], v["height"]) < t["low_res_min_px"]]
    if low:
        checks.append(check(
            "LOW_RES", "fail",
            f"object under {t['low_res_min_px']} px on its long side in a view (512-px views "
            "gave a jumbled model): regenerate each view at 1K or more",
            views=low, min_px=t["low_res_min_px"]))

    by_role = {v["role"]: v for v in views if v["role"]}
    if "left" in by_role and "right" in by_role:
        c = compare(by_role["left"]["_blob"], by_role["right"]["_blob"])
        if c["iou"] >= t["lr_copy_iou"]:
            checks.append(check(
                "LR_COPY", "fail",
                "left and right views are the same image, not mirror images: one side was "
                "copied; regenerate the right view as the mirror of the left",
                left=by_role["left"]["index"], right=by_role["right"]["index"], **c))
    if "front" in by_role and "back" in by_role:
        c = compare(by_role["front"]["_blob"], by_role["back"]["_blob"])
        if c["iou"] >= t["back_copy_iou"] and c["pixel"] >= t["back_copy_pixel"]:
            checks.append(check(
                "BACK_COPY", "fail",
                "the back view is a copy of the front (same silhouette and pixels, not "
                "turned): Tripo builds two objects or a front on both faces; redraw the back",
                front=by_role["front"]["index"], back=by_role["back"]["index"], **c))

    chroma = [{"view": v["index"], "holes_frac": round(v["_blob"]["holes_frac"], 4),
               "tint_frac": round(v["_blob"]["tint_frac"], 4)} for v in views
              if v["_blob"]["holes_frac"] >= t["hole_min_view_frac"]
              or v["_blob"]["tint_frac"] >= t["chroma_min_view_frac"]]
    if chroma:
        checks.append(check(
            "CHROMA_INSIDE", "warn",
            "transparent part shows background: background colour inside the object (glass, "
            "gaps between thin parts); Tripo paints it into the texture or closes the gaps",
            views=chroma))

    for v in views:
        del v["_blob"]
    return {"images": images, "views": views, "checks": checks}


sio.main(run, cfg)
