"""Inside-Blender helpers: parse args, import any model format, write the JSON result.

NOTE: `import _io` does NOT work in Python (`_io` is a built-in C module and always
wins). Blender scripts do `import skill_io` instead; that shim loads this file by path.

Typical script:

    import skill_io as sio
    def cfg(p): p.add_argument("--model", required=True)
    def run(a):
        objs = sio.load_model(a.model)
        return {"meshes": len([o for o in objs if o.type == "MESH"])}
    sio.main(run, cfg)
"""
import argparse
import json
import os
import sys
import traceback

EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_INTERNAL = 4


_AXES = ("-x", "-y", "+x", "+y")


def glue_option_values(argv):
    """Join `--front -x` into `--front=-x` (and `--game-cam -30,35,40` likewise)."""
    # argparse reads a following '-x'/'-y'/'-30,..' as an option flag, so the space form
    # fails with 'expected one argument'; the '=' form is always parsed as a value.
    out, i = [], 0
    while i < len(argv):
        tok = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if nxt is not None and ((tok == "--front" and nxt in _AXES) or
                                (tok == "--game-cam" and nxt[:1] == "-" and nxt[1:2] in tuple("0123456789."))):
            out.append(f"{tok}={nxt}")
            i += 2
        else:
            out.append(tok)
            i += 1
    return out


def args(configure=None) -> argparse.Namespace:
    """Parse the arguments after Blender's `--`. `--out` is always present.

    `configure(parser)` adds script-specific options (strict parsing). Without it,
    unknown options are collected in `ns.rest`.
    """
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    argv = glue_option_values(argv)
    p = argparse.ArgumentParser(prog="blender-script", add_help=False)
    p.add_argument("--out", required=True, help="where to write the result JSON")
    if configure is not None:
        configure(p)
        return p.parse_args(argv)
    ns, rest = p.parse_known_args(argv)
    ns.rest = rest
    return ns


def _json_default(o):
    """numpy scalars/arrays and other tolist()/item() carriers."""
    for attr in ("tolist", "item"):
        f = getattr(o, attr, None)
        if callable(f):
            return f()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def write(out: str, obj: dict) -> None:
    """Write `obj` as one JSON line, atomically. Raises on NaN/inf or non-dicts."""
    if not isinstance(obj, dict):
        raise TypeError(f"result must be a dict, got {type(obj).__name__}")
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                      default=_json_default, allow_nan=False)
    tmp = out + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(tmp, out)


def main(fn, configure=None) -> None:
    """Run `fn(args) -> dict` and write the result to --out.

    A missing input file exits 3 (EXIT_NOT_FOUND); argparse errors exit 2. On any
    other exception: print the traceback to stderr, write nothing, exit 4.
    """
    try:
        ns = args(configure)
        write(ns.out, fn(ns))
    except SystemExit as e:  # argparse errors etc. must not look like success
        sys.exit(e.code if e.code not in (None, 0) else EXIT_INTERNAL)
    except FileNotFoundError as e:  # nothing is written to --out
        print(f"input not found: {e}", file=sys.stderr)
        sys.stderr.flush()
        sys.exit(EXIT_NOT_FOUND)
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        sys.exit(EXIT_INTERNAL)


def sniff(path: str) -> str:
    """File format from magic bytes, not the extension: glb, gltf, fbx, obj."""
    with open(path, "rb") as f:
        head = f.read(4096)
    if head[:4] == b"glTF":
        return "glb"
    if head.startswith(b"Kaydara FBX Binary") or head.lstrip().startswith(b"; FBX"):
        return "fbx"
    if head.lstrip().startswith(b"{") and b'"asset"' in head + _more(path):
        return "gltf"
    text = head.decode("utf-8", "ignore")
    lines = [ln.split() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if lines and lines[0][0] in ("v", "vn", "vt", "f", "o", "g", "mtllib", "usemtl", "s", "l", "p"):
        return "obj"
    raise ValueError(f"unrecognised model format (magic bytes): {path}")


def _more(path: str) -> bytes:
    """glTF JSON may put `asset` late; read a bit more only when the head isn't enough."""
    with open(path, "rb") as f:
        f.seek(4096)
        return f.read(1 << 20)


def clear_scene() -> None:
    """Remove every object and all orphaned data (factory cube, light, camera, old imports)."""
    import bpy
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.armatures,
                 bpy.data.cameras, bpy.data.lights, bpy.data.textures, bpy.data.actions):
        for block in list(coll):
            coll.remove(block)


def load_model(path: str) -> list:
    """Clear the scene, import GLB/GLTF/FBX/OBJ (chosen by magic bytes) and return
    every imported object (meshes, armatures, empties)."""
    import bpy
    if not os.path.isfile(path):
        raise FileNotFoundError(f"model not found: {path}")
    fmt = sniff(path)
    clear_scene()
    before = set(bpy.data.objects)
    if fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.wm.obj_import(filepath=path)
    return [o for o in bpy.data.objects if o not in before]
