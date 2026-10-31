"""QA render sheet: one PNG the agent can read, 0 credits (run through scripts/bl.py).

    bl.py render_sheet.py -- <model> --png <out.png> [--front +x|-x|+y|-y]
                             [--game-cam "<yaw>,<pitch>,<fov>"] [--light-sweep]

-> {"png", "width", "height", "panels": [{"name", "pass", "view", "row", "col"}], ...}

Layout (long side <= 1500 px): one row per pass, one column per view.
  rows     lit               studio light, normal maps on
           lit_no_normalmap  same light, links into the Principled Normal socket cut
           albedo            emission-only base colour (no light, no shading)
           wire              wireframe over flat grey (Workbench; EEVEE has no wire view)
  columns  front back left right top iso, plus game_cam when --game-cam is given
  --light-sweep adds one row of 4 lit renders (iso view) with the key light at
  0/90/180/270 degrees around the model (0 = from the front); a texture with baked
  light does not change between them.

Overlay (3D geometry, so every pass shows it): a red arrow on the ground pointing out of
the front face, a grid on the ground (1 m; 0.1 m or 0.01 m for models smaller than
2 m / 0.2 m, 10x coarser if it would need more than 40 lines), and a header strip with
file name, triangle count, front axis and grid spacing. Panel labels are drawn with a
built-in 5x7 bitmap font (no font files, no PIL).

Frame conventions (Blender, Z up): `--front` is the axis the model's front faces; the
default -y is glTF +Z, the same default as qa.py. Cameras: front looks at the front
face; right is the side on the right-hand side of someone looking at the front face
(the usual orthographic right view); top has the front at the bottom of the image.
`--game-cam yaw,pitch,fov`: a perspective camera `yaw` degrees around the model from
the front towards the right, `pitch` degrees above the horizon, `fov` degrees vertical.
The six standard views and iso are orthographic and share one scale, so sizes compare
across panels. Lights follow each camera (key 35 degrees to its right), so no view is
left in the dark.

Extra result keys: front, grid_m, tris, normal_maps (the model has linked normal maps),
engine (the lit-pass render engine).
"""
import math
import os
import shutil
import struct
import tempfile
import zlib

import bpy
import numpy as np
from mathutils import Matrix, Vector

import _mesh
import skill_io as sio

MAX_SIDE = 1500
GAP = 2
HEADER_H = 22
BG = 0.30            # panel background, display space
SHEET_BG = 0.07
MARGIN = 1.12        # framing slack around the model
GRID_MAX_LINES = 40
UP = Vector((0, 0, 1))

PASSES = (("lit", "LIT"), ("lit_no_normalmap", "NO NM"), ("albedo", "ALBEDO"), ("wire", "WIRE"))
VIEWS = ("front", "back", "left", "right", "top", "iso")
SWEEP_AZ = (0, 90, 180, 270)

# --------------------------------------------------------------------------- 5x7 font
_GLYPHS = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11110 00001 00001 01110 00001 00001 11110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    ".": "00000 00000 00000 00000 00000 01100 01100", ",": "00000 00000 00000 00000 01100 00100 01000",
    ":": "00000 01100 01100 00000 01100 01100 00000", "-": "00000 00000 00000 11111 00000 00000 00000",
    "+": "00000 00100 00100 11111 00100 00100 00000", "/": "00001 00001 00010 00100 01000 10000 10000",
    "=": "00000 00000 11111 00000 11111 00000 00000", "(": "00010 00100 01000 01000 01000 00100 00010",
    ")": "01000 00100 00010 00010 00010 00100 01000", "%": "11001 11010 00010 00100 01000 01011 10011",
    "_": "00000 00000 00000 00000 00000 00000 11111", ">": "01000 00100 00010 00001 00010 00100 01000",
    " ": "00000 00000 00000 00000 00000 00000 00000", "?": "01110 10001 00001 00010 00100 00000 00100",
}
_FONT = {ch: np.array([[c == "1" for c in row] for row in g.split()], bool) for ch, g in _GLYPHS.items()}


def draw_text(img, x, y, text, scale=2, color=(1.0, 1.0, 1.0)):
    """Draw `text` (upper-cased; unknown glyphs become '?') at pixel (x, y) = top-left,
    in float image `img` (H, W, 3), with a 1 px dark outline. Clipped to the image."""
    glyphs = [_FONT.get(ch, _FONT["?"]) for ch in text.upper()]
    if not glyphs:
        return
    adv = 6 * scale
    mask = np.zeros((7 * scale, adv * len(glyphs)), bool)
    for i, g in enumerate(glyphs):
        mask[:, i * adv:i * adv + 5 * scale] = np.kron(g, np.ones((scale, scale), bool))
    pad = np.pad(mask, 1)
    outline = np.zeros_like(pad)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            outline |= np.roll(np.roll(pad, dy, 0), dx, 1)
    h, w = pad.shape
    x0, y0 = x - 1, y - 1
    ys, xs = max(0, y0), max(0, x0)
    ye, xe = min(img.shape[0], y0 + h), min(img.shape[1], x0 + w)
    if ye <= ys or xe <= xs:
        return
    o = outline[ys - y0:ye - y0, xs - x0:xe - x0]
    m = pad[ys - y0:ye - y0, xs - x0:xe - x0]
    region = img[ys:ye, xs:xe]
    region[o] = 0.0
    region[m] = color


def encode_png(rgb8: np.ndarray) -> bytes:
    """Minimal 8-bit RGB PNG encoder (stdlib zlib)."""
    h, w, _ = rgb8.shape
    raw = b"".join(b"\x00" + rgb8[r].tobytes() for r in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# --------------------------------------------------------------------------- geometry
def front_vector(front: str) -> Vector:
    v = Vector((0, 0, 0))
    v["xyz".index(front[1])] = -1.0 if front[0] == "-" else 1.0
    return v


def view_dir(view: str, front: Vector, yaw=None, pitch=None) -> Vector:
    """Unit vector from the model to the camera."""
    right = UP.cross(front)  # the right-hand side of someone looking at the front face
    if view == "front":
        return front.copy()
    if view == "back":
        return -front
    if view == "right":
        return right
    if view == "left":
        return -right
    if view == "top":
        return UP.copy()
    if view == "iso":
        yaw, pitch = 45.0, 35.264
    ya, pi = math.radians(yaw), math.radians(pitch)
    h = front * math.cos(ya) + right * math.sin(ya)
    return (h * math.cos(pi) + UP * math.sin(pi)).normalized()


def camera_basis(d: Vector, front: Vector):
    """(right, up) screen axes for a camera at +d looking at the target. In the top view
    the front is at the bottom of the image."""
    fwd = -d
    up = -front if abs(d.z) > 0.99 else UP
    right = fwd.cross(up).normalized()
    return right, right.cross(fwd).normalized()


def aim(cam, d: Vector, front: Vector, target: Vector, dist: float):
    right, up = camera_basis(d, front)
    cam.matrix_world = Matrix.LocRotScale(target + d * dist,
                                          Matrix((right, up, d)).transposed().to_quaternion(),
                                          None)


def prepare_materials(meshes):
    """Every mesh slot gets a material (grey default for empty slots / no slots)."""
    grey = None
    for o in meshes:
        if not o.material_slots:
            o.data.materials.append(None)
        for slot in o.material_slots:
            if slot.material is None:
                if grey is None:
                    grey = bpy.data.materials.new("sheet_default_grey")
                    grey.use_nodes = True
                    grey.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.6, .6, .6, 1)
                slot.material = grey


def principled(mat):
    nt = mat.node_tree if mat is not None else None
    if nt is None:
        return None
    return next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)


def cut_normal_maps(mats) -> int:
    """Remove every link into a Principled Normal socket; returns how many were cut."""
    n = 0
    for mat in mats:
        if mat.node_tree is None:
            continue
        for link in list(mat.node_tree.links):
            if link.to_node.type == "BSDF_PRINCIPLED" and link.to_socket.identifier == "Normal":
                mat.node_tree.links.remove(link)
                n += 1
    return n


def to_albedo(mats):
    """Rewire each material so its output is an Emission of the Principled base colour."""
    for mat in mats:
        nt = mat.node_tree
        if nt is None:
            continue
        pb = principled(mat)
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) \
            or next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if out is None:
            out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        if pb is not None:
            sock = pb.inputs["Base Color"]
            if sock.is_linked:
                nt.links.new(sock.links[0].from_socket, em.inputs["Color"])
            else:
                em.inputs["Color"].default_value = sock.default_value
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])


def flat_material(name, rgb, emission=True):
    """Emission material that also carries the colour for Workbench (diffuse_color)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (*rgb, 1.0)
    return mat


def overlay_object(name, verts, faces, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.visible_shadow = False          # overlays must not shade the model
    obj.visible_diffuse = False
    obj.visible_glossy = False
    return obj


def box_geom(lo, hi, base=0):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 4, 7, 3), (1, 2, 6, 5)]
    return v, [tuple(base + i for i in q) for q in f]


def grid_spacing(size_h: float):
    sp = 1.0 if size_h >= 2.0 else (0.1 if size_h >= 0.2 else 0.01)
    while (size_h * 1.7) / sp > GRID_MAX_LINES:
        sp *= 10
    return sp


def build_grid(lo, hi, spacing, z, width, mat):
    """Thin flat quads at integer multiples of `spacing`, covering the footprint plus slack."""
    size = max(hi[0] - lo[0], hi[1] - lo[1])
    slack = max(size * 0.35, spacing)
    x0, x1 = (math.floor((lo[0] - slack) / spacing), math.ceil((hi[0] + slack) / spacing))
    y0, y1 = (math.floor((lo[1] - slack) / spacing), math.ceil((hi[1] + slack) / spacing))
    ex0, ex1, ey0, ey1 = x0 * spacing, x1 * spacing, y0 * spacing, y1 * spacing
    verts, faces = [], []
    w = width / 2
    for i in range(x0, x1 + 1):
        x = i * spacing
        n = len(verts)
        verts += [(x - w, ey0, z), (x + w, ey0, z), (x + w, ey1, z), (x - w, ey1, z)]
        faces.append((n, n + 1, n + 2, n + 3))
    for j in range(y0, y1 + 1):
        y = j * spacing
        n = len(verts)
        verts += [(ex0, y - w, z), (ex1, y - w, z), (ex1, y + w, z), (ex0, y + w, z)]
        faces.append((n, n + 1, n + 2, n + 3))
    return overlay_object("sheet_grid", verts, faces, mat)


def build_arrow(centre, front, extent, diag, z, mat):
    """Flat arrow on the ground leaving the front face; returns (object, tip point)."""
    f = Vector((front.x, front.y, 0)).normalized()
    s = Vector((-f.y, f.x, 0))
    start = Vector((centre.x, centre.y, z)) + f * (extent + 0.02 * diag)
    shaft, head, sw, hw = 0.12 * diag, 0.07 * diag, 0.012 * diag, 0.05 * diag
    p0, p1 = start, start + f * shaft
    tip = p1 + f * head
    th = max(sw, 0.01 * diag)
    pts = [p0 - s * sw, p0 + s * sw, p1 + s * sw, p1 - s * sw,      # shaft
           p1 - s * hw, p1 + s * hw, tip]                           # head
    verts, faces = [], []
    for k in range(2):                                               # bottom, top
        verts += [(p.x, p.y, z + k * th) for p in pts]
    n = len(pts)
    faces += [(0, 1, 2, 3), (4, 5, 6)]                               # bottom
    faces += [tuple(n + i for i in q) for q in ((3, 2, 1, 0), (6, 5, 4))]
    for ring in ((0, 1, 2, 3), (4, 5, 6)):                           # sides
        for a, b in zip(ring, ring[1:] + ring[:1]):
            faces.append((a, b, n + b, n + a))
    return overlay_object("sheet_arrow", verts, faces, mat), tip


# --------------------------------------------------------------------------- scene setup
def set_engine(sc, names):
    for name in names:
        try:
            sc.render.engine = name
            return name
        except TypeError:
            continue
    raise RuntimeError(f"none of the render engines exist: {names}")


def setup_render(sc, px):
    r = sc.render
    r.resolution_x = r.resolution_y = px
    r.resolution_percentage = 100
    r.film_transparent = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.color_depth = "8"
    r.dither_intensity = 0.0
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    sc.display_settings.display_device = "sRGB"
    sc.sequencer_colorspace_settings.name = "sRGB"


def setup_world(sc, strength):
    world = bpy.data.worlds.new("sheet_world")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.8, 0.82, 0.86, 1.0)
    bg.inputs["Strength"].default_value = strength
    return world


def make_sun(name, strength, angle_deg=8.0):
    light = bpy.data.lights.new(name, "SUN")
    light.energy = strength
    light.angle = math.radians(angle_deg)
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def point_sun(sun, hdir: Vector, az_deg: float, el_deg: float):
    """Aim `sun` so the light arrives from azimuth `az_deg` (CCW seen from above) around the
    horizontal direction `hdir` (towards the camera), `el_deg` above the horizon."""
    a, e = math.radians(az_deg), math.radians(el_deg)
    h = Vector((hdir.x, hdir.y, 0)).normalized()
    h = Vector((h.x * math.cos(a) - h.y * math.sin(a), h.x * math.sin(a) + h.y * math.cos(a), 0))
    to_light = h * math.cos(e) + UP * math.sin(e)
    sun.rotation_euler = (-to_light).to_track_quat("-Z", "Y").to_euler()


def read_png(path):
    """(H, W, 4) float32 straight-alpha display values, top row first."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        img.alpha_mode = "CHANNEL_PACKED"
        w, h = img.size
        buf = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)[::-1].copy()
    finally:
        bpy.data.images.remove(img)


# --------------------------------------------------------------------------- main
def parse_game_cam(text):
    parts = [p.strip() for p in text.split(",")]
    try:
        yaw, pitch, fov = (float(p) for p in parts)
    except ValueError:
        raise argparse_error(text) from None
    if len(parts) != 3 or not (0 < fov < 170) or not (-89 <= pitch <= 89):
        raise argparse_error(text)
    return yaw, pitch, fov


def argparse_error(text):
    import argparse
    return argparse.ArgumentTypeError(
        f'--game-cam must be "<yaw>,<pitch>,<fov>" (fov 0-170, pitch -89..89), got {text!r}')


def cfg(p):
    p.add_argument("model")
    p.add_argument("--png", required=True)
    p.add_argument("--front", choices=("-y", "+y", "-x", "+x"), default="-y")
    p.add_argument("--game-cam", type=parse_game_cam, default=None)
    p.add_argument("--light-sweep", action="store_true")


def run(a):
    if os.path.exists(a.png):      # a stale sheet must never pass for this run's result
        os.unlink(a.png)
    objs = sio.load_model(a.model)
    meshes = _mesh.model_meshes(objs)
    if not meshes:
        raise ValueError(f"no mesh objects in {a.model}")
    for o in bpy.data.objects:
        if o not in meshes:
            o.hide_render = True
    prepare_materials(meshes)
    model_mats = {s.material for o in meshes for s in o.material_slots if s.material}

    lo, hi = _mesh.world_bbox(meshes)
    lo, hi = Vector(lo.tolist()), Vector(hi.tolist())
    centre = (lo + hi) / 2
    diag = max((hi - lo).length, 1e-6)
    front = front_vector(a.front)
    tris = sum(len(o.data.loop_triangles) for o in meshes)
    has_nm = any(l.to_node.type == "BSDF_PRINCIPLED" and l.to_socket.identifier == "Normal"
                 for m in model_mats if m.node_tree for l in m.node_tree.links)

    views = list(VIEWS) + (["game_cam"] if a.game_cam else [])
    ncols = len(views)
    px = (MAX_SIDE - GAP * (ncols + 1)) // ncols
    sheet_w = ncols * px + GAP * (ncols + 1)
    nrows = len(PASSES) + (1 if a.light_sweep else 0)
    sheet_h = HEADER_H + nrows * (px + GAP) + GAP

    sc = bpy.context.scene
    setup_render(sc, px)
    lit_engine = set_engine(sc, ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"))
    sc.eevee.taa_render_samples = 24
    setup_world(sc, 0.38)

    # overlay geometry (ground = lowest point of the model)
    z = lo.z - 0.0015 * diag
    arrow_mat = flat_material("sheet_arrow", (0.95, 0.12, 0.08))
    grid_mat = flat_material("sheet_grid", (0.62, 0.64, 0.68))
    fh = Vector((front.x, front.y, 0))
    extent = max(abs((hi.x - centre.x) * fh.x), abs((hi.y - centre.y) * fh.y))
    arrow, tip = build_arrow(centre, front, extent, diag, z, arrow_mat)

    # framing: orthographic views share one scale; the arrow tip is part of the frame
    pts = [Vector((x, y, zz)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for zz in (lo.z, hi.z)] + [tip]
    dirs = {v: view_dir(v, front) for v in VIEWS}
    if a.game_cam:
        gyaw, gpitch, gfov = a.game_cam
        dirs["game_cam"] = view_dir("game_cam", front, gyaw, gpitch)
    ortho = {}
    for v in VIEWS:
        r, u = camera_basis(dirs[v], front)
        xs, ys = [p.dot(r) for p in pts], [p.dot(u) for p in pts]
        ortho[v] = (((max(xs) + min(xs)) / 2) * r + ((max(ys) + min(ys)) / 2) * u,
                    max(max(xs) - min(xs), max(ys) - min(ys)))
    ortho_scale = max(s for _, s in ortho.values()) * MARGIN

    size_h = max(hi.x - lo.x, hi.y - lo.y)
    spacing = grid_spacing(size_h)
    line_w = 1.4 * ortho_scale / px
    grid = build_grid((lo.x, lo.y), (hi.x, hi.y), spacing, z, line_w, grid_mat)

    cam_data = bpy.data.cameras.new("sheet_cam")
    cam = bpy.data.objects.new("sheet_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam_data.clip_start = 0.001 * diag
    cam_data.clip_end = 100 * diag + 10 * ortho_scale

    key = make_sun("sheet_key", 2.6)
    fill = make_sun("sheet_fill", 1.1, 25)
    rim = make_sun("sheet_rim", 1.4, 15)

    def frame(view):
        """Position the camera for `view`; returns the world size of one pixel."""
        d = dirs[view]
        if view == "game_cam":
            cam_data.type = "PERSP"
            cam_data.sensor_fit = "VERTICAL"
            cam_data.angle_y = math.radians(gfov)
            r, u = camera_basis(d, front)
            t = math.tan(math.radians(gfov) / 2) / MARGIN
            dist = max(max(abs((p - centre).dot(r)), abs((p - centre).dot(u))) / t + (p - centre).dot(d)
                       for p in pts)
            aim(cam, d, front, centre, dist)
            return 2 * dist * math.tan(math.radians(gfov) / 2) / px
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho_scale
        target, _ = ortho[view]
        aim(cam, d, front, target, 2 * diag)
        return ortho_scale / px

    def light_follow(view, key_az=35.0, fill_on=True, key_abs=False):
        """Lights follow the camera; with key_abs the key azimuth is measured from the model front."""
        d = dirs[view]
        base = front if key_abs else Vector((d.x, d.y, 0)) if abs(d.z) < 0.99 else front
        point_sun(key, base, key_az, 42)
        if fill_on:
            point_sun(fill, Vector((d.x, d.y, 0)) if abs(d.z) < 0.99 else front, -70, 25)
            point_sun(rim, Vector((d.x, d.y, 0)) if abs(d.z) < 0.99 else front, 180, 30)
        fill.data.energy = 1.1 if fill_on else 0.0
        rim.data.energy = 1.4 if fill_on else 0.0

    tmp = tempfile.mkdtemp(prefix="tripo-sheet-")
    sheet = np.full((sheet_h, sheet_w, 3), SHEET_BG, np.float32)
    panels = []
    counter = [0]

    def shoot(pass_name, view, row, col, cap, name=None, bg=BG):
        path = os.path.join(tmp, f"panel_{counter[0]}.png")
        counter[0] += 1
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        rgba = read_png(path)
        os.unlink(path)
        tile = rgba[..., :3] * rgba[..., 3:4] + bg * (1 - rgba[..., 3:4])
        x0 = GAP + col * (px + GAP)
        y0 = HEADER_H + GAP + row * (px + GAP)
        draw_text(tile, 4, 4, cap)
        sheet[y0:y0 + px, x0:x0 + px] = tile
        panels.append({"name": name or f"{pass_name}_{view}", "pass": pass_name, "view": view,
                       "row": row, "col": col})

    try:
        # --- lit
        sc.render.engine = lit_engine
        for col, v in enumerate(views):
            frame(v)
            light_follow(v)
            shoot("lit", v, 0, col, f"LIT {v.upper().replace('_', ' ')}")
        # --- light sweep: a lit row, so it runs before the normal maps are cut
        if a.light_sweep:
            frame("iso")
            for col, az in enumerate(SWEEP_AZ):
                light_follow("iso", key_az=az, fill_on=False, key_abs=True)
                shoot("lit_sweep", "iso", nrows - 1, col, f"KEY {az}", name=f"lit_sweep_{az}")
        # --- normal maps off
        cut_normal_maps(model_mats)
        for col, v in enumerate(views):
            frame(v)
            light_follow(v)
            shoot("lit_no_normalmap", v, 1, col, f"NO NM {v.upper().replace('_', ' ')}")
        # --- albedo
        to_albedo(model_mats)
        for col, v in enumerate(views):
            frame(v)
            shoot("albedo", v, 2, col, f"ALBEDO {v.upper().replace('_', ' ')}")
        # --- wire (Workbench: flat grey base + a wireframe copy of every mesh)
        grey = flat_material("sheet_wire_grey", (0.62, 0.62, 0.62))
        ink = flat_material("sheet_wire_ink", (0.03, 0.03, 0.03))
        for o in meshes:
            for i in range(len(o.data.materials)):
                o.data.materials[i] = grey
        wires = []
        for o in meshes:
            w = o.copy()
            sc.collection.objects.link(w)
            for slot in w.material_slots:
                slot.link = "OBJECT"
                slot.material = ink
            m = w.modifiers.new("sheet_wire", "WIREFRAME")
            m.use_replace = True
            m.use_even_offset = False
            m.use_boundary = True
            m.offset = 1.0          # outside the surface: coplanar wire would z-fight
            wires.append((m, max(abs(x) for x in o.matrix_world.to_scale()) or 1.0))
        set_engine(sc, ("BLENDER_WORKBENCH",))
        sh = sc.display.shading
        sh.light, sh.color_type, sh.show_object_outline = "FLAT", "MATERIAL", False
        sh.show_shadows = False
        sc.display.render_aa = "8"
        for col, v in enumerate(views):
            pix = frame(v)
            for m, scale in wires:
                m.thickness = 1.1 * pix / scale
            shoot("wire", v, 3, col, f"WIRE {v.upper().replace('_', ' ')}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    name = os.path.splitext(os.path.basename(a.model))[0]
    if name.lower() == "model":      # Tripo outputs are all model.glb: name them by their folder
        name = os.path.basename(os.path.dirname(os.path.abspath(a.model))) or name
    header = f"{name[:30]}  TRIS {tris}  FRONT {a.front.upper()}  GRID {spacing:g}M"
    draw_text(sheet[:HEADER_H], 6, 4, header)

    os.makedirs(os.path.dirname(os.path.abspath(a.png)), exist_ok=True)
    tmp_png = a.png + ".part"
    with open(tmp_png, "wb") as f:
        f.write(encode_png((np.clip(sheet, 0, 1) * 255 + 0.5).astype(np.uint8)))
    os.replace(tmp_png, a.png)
    return {"png": os.path.abspath(a.png), "width": sheet_w, "height": sheet_h, "panels": panels,
            "front": a.front, "grid_m": spacing, "tris": tris, "normal_maps": has_nm,
            "engine": lit_engine}


sio.main(run, cfg)
