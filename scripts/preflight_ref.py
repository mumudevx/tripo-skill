#!/usr/bin/env python3
"""Reference image preflight (0 credits): automatic checks before any Tripo call.

    preflight_ref.py <image>... [--views auto|single|sheet] [--bg auto|#RRGGBB]

One image = a sheet (up to 4 views on one row) or a single view; several images = one
view per file (roles from the file name: front/left/back/right, else that order).

Prints {"ok": true, "images": [...], "views": [{"index", "image", "role", "bbox_px",
"width", "height"}], "checks": [{"code", "level", "message", "evidence"}]}.
Exit 0 = no failed check, 5 = at least one check failed, 2 usage / unreadable image,
3 image not found, 4 internal (Blender) error.

The magic-byte check (FAKE_FORMAT) runs here; pixel work runs in headless Blender
(scripts/blender/preflight_img.py, numpy). Thresholds: scripts/data/qa_thresholds.json
under "preflight". The agent-eye checks live in references/image-preflight.md.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bl  # noqa: E402
import common  # noqa: E402

THRESHOLDS = Path(__file__).resolve().parent / "data" / "qa_thresholds.json"
EXT_FORMAT = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp",
              ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff"}
LEVEL_ORDER = {"fail": 0, "warn": 1, "info": 2}


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def sniff_image(path: Path) -> str:
    """Image format from magic bytes: png, jpeg, webp, bmp, tiff; '' when unknown."""
    with open(path, "rb") as f:
        head = f.read(16)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"BM"):
        return "bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    return ""


def parse(argv):
    p = Parser(prog="preflight_ref.py", add_help=False)
    p.add_argument("images", nargs="+")
    p.add_argument("--views", choices=("auto", "single", "sheet"), default="auto")
    p.add_argument("--bg", default="auto")
    a = p.parse_args(argv)
    if a.bg != "auto" and not re.fullmatch(r"#[0-9a-fA-F]{6}", a.bg):
        raise UsageError(f"--bg must be auto or #RRGGBB, got {a.bg!r}")
    return a


def main(argv) -> int:
    try:
        a = parse(argv)
    except UsageError as e:
        common.fail(common.EXIT_USAGE, f"usage: {e}")
    checks, paths = [], []
    for i, raw in enumerate(a.images):
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            common.fail(common.EXIT_NOT_FOUND, f"image not found: {raw}")
        fmt = sniff_image(path)
        if not fmt:
            common.fail(common.EXIT_USAGE, f"not a supported image (magic bytes): {raw}")
        claimed = EXT_FORMAT.get(path.suffix.lower())
        if claimed != fmt:
            checks.append({
                "code": "FAKE_FORMAT", "level": "warn",
                "message": f"{path.name} holds {fmt.upper()} bytes behind a "
                           f"'{path.suffix}' name: re-save it in its real format before "
                           "upload (some tools trust the extension)",
                "evidence": {"image": i, "extension": path.suffix, "magic": fmt}})
        paths.append(str(path))

    args = ["--views", a.views, "--bg", a.bg.lower(), "--thresholds", str(THRESHOLDS)]
    for p in paths:
        args += ["--image", p]
    try:
        result = bl.run("preflight_img.py", args)
    except bl.BlenderError as e:
        common.fail(common.EXIT_INTERNAL, "blender failed", blender_exit=e.code,
                    stderr_tail=e.stderr_tail)
    checks += result["checks"]
    checks.sort(key=lambda c: LEVEL_ORDER[c["level"]])
    common.emit({"ok": True, "images": result["images"], "views": result["views"],
                 "checks": checks})
    return common.EXIT_CHECK if any(c["level"] == "fail" for c in checks) \
        else common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
