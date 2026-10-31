#!/usr/bin/env python3
"""Stdlib-only statistics for GLB / glTF files.

The format is decided from magic bytes, never from the extension. Non-glTF
formats (FBX, OBJ) return only `format` and `bytes` plus a pointer to
blender/qa.py.

Usage: glbstat.py <file> [--json]
Output is always exactly one JSON line (`--json` is accepted for symmetry).
Exit codes: 0 ok, 2 usage, 3 file not found, 5 not a valid glTF/GLB.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
NOTE = "use blender/qa.py"


class GlbError(ValueError):
    pass


def sniff_format(head: bytes) -> str:
    """Classify a file from its first bytes."""
    if head[:4] == GLB_MAGIC:
        return "glb"
    if head.startswith(b"Kaydara FBX Binary") or head.lstrip().startswith(b"; FBX"):
        return "fbx"
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if text.startswith(b"{") and b'"asset"' in head:
        return "gltf"
    if _looks_like_obj(text):
        return "obj"
    return "unknown"


def _looks_like_obj(text: bytes) -> bool:
    try:
        s = text.decode("ascii")
    except UnicodeDecodeError:
        return False
    keys = ("v ", "vt ", "vn ", "f ", "o ", "g ", "mtllib ", "usemtl ", "s ")
    seen = 0
    for line in s.splitlines()[:50]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(keys):
            return False
        seen += 1
    return seen > 0


def parse_glb(data: bytes):
    """Return (json_dict, bin_bytes or None) for a GLB container."""
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise GlbError("not a GLB container")
    _version, total = struct.unpack_from("<II", data, 4)
    end = min(total, len(data))
    pos, doc, blob = 12, None, None
    while pos + 8 <= end:
        clen, ctype = struct.unpack_from("<II", data, pos)
        body = data[pos + 8:pos + 8 + clen]
        if len(body) < clen:
            raise GlbError("truncated GLB chunk")
        if ctype == JSON_CHUNK and doc is None:
            try:
                doc = json.loads(body.decode("utf-8"))
            except ValueError as exc:
                raise GlbError(f"bad JSON chunk: {exc}")
        elif ctype == BIN_CHUNK and blob is None:
            blob = body
        pos += 8 + ((clen + 3) & ~3)
    if doc is None:
        raise GlbError("GLB has no JSON chunk")
    return doc, blob


def image_size(b: bytes):
    """(mime, width, height) from PNG / JPEG / WebP headers; (None, None, None) if unknown."""
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) >= 24:
        w, h = struct.unpack(">II", b[16:24])
        return "image/png", w, h
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg", *_jpeg_size(b)
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp", *_webp_size(b)
    return None, None, None


def _jpeg_size(b: bytes):
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    i, n = 2, len(b)
    while i + 4 <= n:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seglen = struct.unpack(">H", b[i + 2:i + 4])[0]
        if marker in sof and i + 9 <= n:
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + seglen
    return None, None


def _webp_size(b: bytes):
    kind = b[12:16]
    if kind == b"VP8 " and len(b) >= 30:
        w, h = struct.unpack("<HH", b[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if kind == b"VP8L" and len(b) >= 25:
        bits = struct.unpack("<I", b[21:25])[0]
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X" and len(b) >= 30:
        w = int.from_bytes(b[24:27], "little") + 1
        h = int.from_bytes(b[27:30], "little") + 1
        return w, h
    return None, None


def _prim_tris(doc: dict, prim: dict) -> int:
    accessors = doc.get("accessors", [])
    mode = prim.get("mode", 4)
    if "indices" in prim:
        n = accessors[prim["indices"]]["count"]
    else:
        pos = prim.get("attributes", {}).get("POSITION")
        n = accessors[pos]["count"] if pos is not None else 0
    if mode == 4:
        return n // 3
    if mode in (5, 6):
        return max(n - 2, 0)
    return 0  # points / lines


def _image_bytes(doc: dict, blob, img: dict, base_dir):
    """Raw bytes of one glTF image, or None when it cannot be reached."""
    if "bufferView" in img:
        if blob is None:
            return None
        bv = doc["bufferViews"][img["bufferView"]]
        off = bv.get("byteOffset", 0)
        return blob[off:off + bv["byteLength"]]
    uri = img.get("uri")
    if not uri:
        return None
    if uri.startswith("data:"):
        import base64
        try:
            return base64.b64decode(uri.split(",", 1)[1])
        except (IndexError, ValueError):
            return None
    if base_dir is not None:
        from urllib.parse import unquote
        p = Path(base_dir) / unquote(uri)
        if p.is_file():
            return p.read_bytes()
    return None


def _gltf_stats(doc: dict, blob, base_dir=None) -> dict:
    meshes = doc.get("meshes", [])
    prims = [p for m in meshes for p in m.get("primitives", [])]
    images = []
    for i, img in enumerate(doc.get("images", [])):
        raw = _image_bytes(doc, blob, img, base_dir)
        mime, w, h = image_size(raw) if raw is not None else (None, None, None)
        images.append({
            "name": img.get("name") or f"image_{i}",
            "mime": img.get("mimeType") or mime,
            "width": w,
            "height": h,
            "bytes": len(raw) if raw is not None else None,
        })
    skins = doc.get("skins", [])
    return {
        "tris": sum(_prim_tris(doc, p) for p in prims),
        "meshes": len(meshes),
        "primitives": len(prims),
        "materials": len(doc.get("materials", [])),
        "images": images,
        "skins": len(skins),
        "joints": sum(len(s.get("joints", [])) for s in skins),
        "animations": len(doc.get("animations", [])),
    }


def stat(path) -> dict:
    """Statistics for one model file. Raises FileNotFoundError / GlbError."""
    path = Path(path)
    size = path.stat().st_size  # FileNotFoundError if missing
    with open(path, "rb") as fh:
        head = fh.read(4096)
    fmt = sniff_format(head)
    if fmt in ("fbx", "obj", "unknown"):
        out = {"format": fmt, "bytes": size}
        if fmt != "unknown":
            out["note"] = NOTE
        return out
    data = path.read_bytes()
    if fmt == "glb":
        doc, blob = parse_glb(data)
        base = None
    else:
        try:
            doc, blob = json.loads(data.decode("utf-8-sig")), None
        except ValueError as exc:
            raise GlbError(f"bad glTF JSON: {exc}")
        base = path.parent
    try:
        stats = _gltf_stats(doc, blob, base)
    except (KeyError, IndexError, TypeError) as exc:
        raise GlbError(f"inconsistent glTF ({type(exc).__name__}: {exc})")
    return {"format": fmt, **stats, "bytes": size}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    args = [a for a in args if a != "--json"]
    if len(args) != 1 or args[0].startswith("-"):
        common.fail(common.EXIT_USAGE, "usage: glbstat.py <file> [--json]")
    path = Path(args[0])
    try:
        result = stat(path)
    except FileNotFoundError:
        common.fail(common.EXIT_NOT_FOUND, f"file not found: {path}", path=str(path))
    except IsADirectoryError:
        common.fail(common.EXIT_USAGE, f"not a file: {path}", path=str(path))
    except GlbError as exc:
        common.fail(common.EXIT_CHECK, str(exc), path=str(path))
    common.emit({"ok": True, "path": str(path), **result})
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
