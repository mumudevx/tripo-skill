"""Export a work .blend for the engine (B12: editable source + one-command re-export).

    bl.py export.py -- <vNN.blend> --out-model <file.glb> [--engine godot] [--max-texture PX]

-> {"out_model", "engine", "blend", "tris", "images": [{"name", "format", "size"}],
    "textures_resized": [{"name", "from", "to", "format"}], "export_sh"}

Godot adapter: GLB, +Y up, images exported in their own format (PNG/JPEG unchanged,
never re-encoded to WebP), modifiers applied with a Triangulate modifier last on every
mesh (so `tris` is exactly what the engine gets). The .blend itself is never modified.

`--max-texture PX` (the free TEXTURE_OVERSIZE fix): every image whose long side is above PX
is scaled down to PX (aspect kept) and re-encoded in its own format (JPEG stays JPEG,
quality 95) before the glTF export, in memory only: the .blend keeps the full-resolution
source, and export.sh repeats the flag. normalize.py takes the same flag.

Also writes `<blend dir>/export.sh`: one command that re-runs this export with the same
arguments after the .blend has been edited by hand.

Importable: apply_recipe uses export_model() for its vNN.glb.
"""
import argparse
import os
import shlex
import sys
import tempfile

import bpy

import skill_io as sio

EXIT_USAGE = 2
ENGINES = ("godot",)
BL_PY = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                      "bl.py"))


def _glb_path(text: str) -> str:
    if not text.lower().endswith(".glb"):
        raise argparse.ArgumentTypeError(f"--out-model must end in .glb, got {text!r}")
    return text


def _max_texture(text: str) -> int:
    try:
        v = int(text)
    except ValueError:
        v = 0
    if not 16 <= v <= 16384:
        raise argparse.ArgumentTypeError(f"--max-texture must be pixels between 16 and 16384, got {text!r}")
    return v


def _repack(img) -> None:
    """Pack the image's current pixels in its own format (JPEG stays JPEG, else PNG)."""
    fmt = "JPEG" if img.file_format == "JPEG" else "PNG"
    fd, tmp = tempfile.mkstemp(prefix="export-", suffix=".jpg" if fmt == "JPEG" else ".png")
    os.close(fd)
    try:
        img.file_format = fmt
        img.save(filepath=tmp, quality=95)
        with open(tmp, "rb") as f:
            data = f.read()
        img.pack(data=data, data_len=len(data))
    finally:
        os.unlink(tmp)


def downsize_images(max_px: int) -> list:
    """Scale every used image whose long side exceeds max_px down to max_px (aspect kept),
    re-packed in its own format. In memory only: the caller never saves the .blend."""
    out = []
    for img in bpy.data.images:
        if img.type != "IMAGE" or not img.users:
            continue
        w, h = img.size
        if not w or not h or max(w, h) <= max_px:
            continue
        f = max_px / max(w, h)
        nw, nh = max(1, round(w * f)), max(1, round(h * f))
        img.scale(nw, nh)
        _repack(img)
        out.append({"name": img.name, "from": [w, h], "to": list(img.size), "format": img.file_format})
    return out


def export_model(out_path: str, engine: str = "godot", max_texture=None) -> dict:
    """Export every mesh in the scene to `out_path` (GLB) with the engine's settings;
    `max_texture` downsizes larger images first (in memory)."""
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}")
    resized = downsize_images(max_texture) if max_texture else []
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    added = []
    try:
        for o in meshes:                                   # appended: runs last
            m = o.modifiers.new("export_triangulate", "TRIANGULATE")
            m.quad_method, m.ngon_method = "BEAUTY", "BEAUTY"
            m.keep_custom_normals = True
            added.append((o, m))
        deps = bpy.context.evaluated_depsgraph_get()
        tris = 0
        for o in meshes:
            ev = o.evaluated_get(deps)
            me = ev.to_mesh()
            me.calc_loop_triangles()
            tris += len(me.loop_triangles)
            ev.to_mesh_clear()
        tmp = os.path.splitext(out_path)[0] + ".part.glb"
        try:
            bpy.ops.export_scene.gltf(filepath=tmp, export_format="GLB", export_yup=True,
                                      export_apply=True, export_image_format="AUTO",
                                      use_selection=False)
            os.replace(tmp, out_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    finally:
        for o, m in added:
            o.modifiers.remove(m)
    images = sorted({(i.name, i.file_format, tuple(i.size)) for i in bpy.data.images
                     if i.type == "IMAGE" and i.users})
    return {"out_model": out_path, "engine": engine, "tris": tris,
            "images": [{"name": n, "format": f, "size": list(s)} for n, f, s in images],
            "textures_resized": resized}


def write_export_sh(blend: str, out_model: str, engine: str, max_texture=None) -> str:
    """`<blend dir>/export.sh`: re-run this export with the same arguments."""
    path = os.path.join(os.path.dirname(blend), "export.sh")
    cmd = ["python3", BL_PY, "export.py", "--", blend, "--out-model", out_model,
           "--engine", engine]
    if max_texture:
        cmd += ["--max-texture", str(max_texture)]
    text = ("#!/bin/sh\n"
            "# Re-export the edited .blend for the engine (written by export.py).\n"
            "set -e\n"
            f"BLENDER=\"${{BLENDER:-{bpy.app.binary_path}}}\"\n"
            "export BLENDER\n"
            f"exec {' '.join(shlex.quote(c) for c in cmd)}\n")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)
    return path


def cfg(p):
    p.add_argument("blend")
    p.add_argument("--out-model", required=True, type=_glb_path)
    p.add_argument("--engine", choices=ENGINES, default="godot")
    p.add_argument("--max-texture", type=_max_texture, default=None)


def run(a):
    blend = os.path.abspath(a.blend)
    if not os.path.isfile(blend):
        raise FileNotFoundError(f"blend not found: {blend}")
    out_model = os.path.abspath(a.out_model)
    if os.path.exists(out_model):  # a stale model must never pass for this run's result
        os.unlink(out_model)
    bpy.ops.wm.open_mainfile(filepath=blend)
    if not any(o.type == "MESH" for o in bpy.context.scene.objects):
        print(f"usage error: no mesh objects in {blend}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    result = export_model(out_model, a.engine, a.max_texture)
    return {**result, "blend": blend,
            "export_sh": write_export_sh(blend, out_model, a.engine, a.max_texture)}


if __name__ == "__main__":
    sio.main(run, cfg)
