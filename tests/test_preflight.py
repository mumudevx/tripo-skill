import json
import os
import shutil
import struct
import subprocess
import sys
import unittest
import zlib

from tests.util import BLENDER, SCRIPTS, fixture, skip_if_missing, tmpdir

CLI = str(SCRIPTS / "preflight_ref.py")


def run_cli(*args):
    env = dict(os.environ, BLENDER=BLENDER)
    p = subprocess.run([sys.executable, CLI, *map(str, args)], capture_output=True,
                       text=True, env=env)
    lines = p.stdout.strip().splitlines()
    out = json.loads(lines[-1]) if lines else None
    return p.returncode, out, p


def codes(out, level=None):
    return {c["code"] for c in out["checks"] if level is None or c["level"] == level}


# ---------- tiny stdlib PNG painter for synthetic sheets ----------

class Canvas:
    """RGB, or RGBA when the background colour has 4 components."""

    def __init__(self, w, h, bg=(255, 255, 255)):
        self.w, self.h, self.n = w, h, len(bg)
        self.rows = [bytearray(bytes(bg) * w) for _ in range(h)]

    def _px(self, rgb):
        return bytes(rgb) + (b"\xff" if self.n == 4 and len(rgb) == 3 else b"")

    def rect(self, x0, y0, x1, y1, rgb):
        n, px = self.n, self._px(rgb) * (x1 - x0)
        for y in range(y0, y1):
            self.rows[y][x0 * n:x1 * n] = px

    def ell(self, x0, y0, x1, y1, rgb):
        """Filled axis-aligned ellipse inside the box (a shape with no straight edges)."""
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        for y in range(y0, y1):
            t = 1 - ((y + 0.5 - cy) / ry) ** 2
            if t <= 0:
                continue
            half = rx * t ** 0.5
            a, b = int(round(cx - half)), int(round(cx + half))
            self.rows[y][a * self.n:b * self.n] = self._px(rgb) * (b - a)

    def boot(self, x, y, w, h, rgb, mirror=False):
        """An asymmetric silhouette: tall body ellipse plus a toe pointing right (or left)."""
        self.ell(x, y, x + w, y + h, rgb)
        toe_w = int(w * 0.9)
        if mirror:
            self.ell(x - toe_w + w // 3, y + h - h // 6, x + w // 3 + w // 3, y + h, rgb)
        else:
            self.ell(x + w - w // 3 - w // 3, y + h - h // 6, x + w - w // 3 + toe_w, y + h, rgb)

    def save(self, path):
        raw = b"".join(b"\x00" + bytes(r) for r in self.rows)

        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8,
                                           6 if self.n == 4 else 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(png)
        return path


def four_view_sheet(path, right_mirrored=True, ground=None, bg=(255, 255, 255)):
    """front, left, back, right: 1100 px tall views on one row.

    ground: None, "joined" (a line the views stand on) or "separate" (a line below them).
    """
    c = Canvas(2600, 1400, bg)
    c.ell(80, 120, 480, 1220, (200, 40, 40))           # front
    c.boot(700, 120, 300, 1100, (40, 90, 200))         # left: toe points right
    c.ell(1300, 120, 1700, 1220, (90, 160, 60))        # back (different pixels)
    c.boot(2050, 120, 300, 1100, (40, 90, 200), mirror=right_mirrored)
    if ground == "joined":
        c.rect(30, 1215, 2570, 1235, (60, 60, 60))
    elif ground == "separate":
        c.rect(30, 1260, 2570, 1275, (60, 60, 60))
    return c.save(path)


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class PreflightFixtures(unittest.TestCase):
    _cache = {}

    def run_ref(self, name, *extra):
        p = fixture(name)
        skip_if_missing(p)
        key = (name, extra)
        if key not in self._cache:
            self._cache[key] = run_cli(p, *extra)
        return self._cache[key]

    def test_good_sheets_pass(self):
        for name in ("R1", "R2", "R3"):
            with self.subTest(name):
                code, out, proc = self.run_ref(name)
                self.assertEqual(code, 0, proc.stdout + proc.stderr)
                self.assertTrue(out["ok"])
                self.assertEqual(codes(out, "fail"), set(), out["checks"])
                # detail close-ups under R2/R3's views are not views
                self.assertEqual(len(out["views"]), 4, out["views"])

    def test_multi_object(self):
        code, out, _ = self.run_ref("R4")
        self.assertIn("MULTI_OBJECT", codes(out, "fail"))

    def test_back_copy(self):
        code, out, _ = self.run_ref("R11")
        self.assertIn("BACK_COPY", codes(out, "fail"))

    def test_two_rows_and_chroma(self):
        code, out, _ = self.run_ref("R9")
        warns = codes(out, "warn")
        self.assertIn("TWO_ROWS", warns)
        self.assertIn("CHROMA_INSIDE", warns)

    def test_low_res(self):
        p = fixture("R12") / "front.png"
        skip_if_missing(p)
        code, out, _ = run_cli(p)
        self.assertEqual(code, 5)
        self.assertIn("LOW_RES", codes(out, "fail"))
        self.assertIn("FAKE_FORMAT", codes(out, "warn"))   # JPEG bytes behind .png

    def test_exit_code_on_fail(self):
        code, out, _ = self.run_ref("R4")
        self.assertEqual(code, 5)
        self.assertTrue(out["ok"])

    def test_separate_view_files_use_name_roles(self):
        d = fixture("R12")
        skip_if_missing(d)
        files = [d / f"{v}.png" for v in ("back", "front", "right", "left")]
        code, out, _ = run_cli(*files)
        self.assertEqual(len(out["views"]), 4)
        self.assertEqual([v["role"] for v in out["views"]], ["back", "front", "right", "left"])
        self.assertEqual([v["image"] for v in out["views"]], [0, 1, 2, 3])
        self.assertNotIn("MULTI_OBJECT", codes(out))


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class PreflightSynthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_mirrored_sides_pass(self):
        code, out, proc = run_cli(four_view_sheet(self.tmp / "ok.png"))
        self.assertEqual(code, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(out["views"]), 4)
        self.assertEqual([v["role"] for v in out["views"]], ["front", "left", "back", "right"])
        self.assertEqual(codes(out, "fail") | codes(out, "warn"), set(), out["checks"])
        v = out["views"][1]
        self.assertGreaterEqual(max(v["width"], v["height"]), 1024)

    def test_lr_copy_unmirrored_fails(self):
        code, out, _ = run_cli(four_view_sheet(self.tmp / "copy.png", right_mirrored=False))
        self.assertEqual(code, 5)
        self.assertIn("LR_COPY", codes(out, "fail"))

    def test_ground_line_warns_and_views_survive(self):
        for kind in ("joined", "separate"):
            with self.subTest(kind):
                code, out, _ = run_cli(four_view_sheet(self.tmp / f"{kind}.png", ground=kind))
                self.assertIn("GROUND_LINE", codes(out, "warn"))
                self.assertEqual(len(out["views"]), 4)
                self.assertNotIn("MULTI_OBJECT", codes(out))
                self.assertEqual(code, 0)

    def test_non_plain_background(self):
        c = Canvas(1600, 1400)
        for y in range(c.h):          # vertical grey ramp 236 -> 255 (stays background)
            g = 236 + (19 * y) // c.h
            c.rows[y] = bytearray(bytes((g, g, g)) * c.w)
        c.ell(500, 150, 1000, 1300, (180, 30, 30))
        code, out, _ = run_cli(c.save(self.tmp / "ramp.png"))
        self.assertIn("NON_PLAIN_BG", codes(out, "warn"))
        self.assertEqual(len(out["views"]), 1)

    def test_transparent_background(self):
        c = Canvas(1400, 1400, (0, 255, 0, 0))   # fully transparent (green under alpha 0)
        c.ell(300, 100, 1100, 1300, (200, 40, 40))
        code, out, proc = run_cli(c.save(self.tmp / "cut.png"))
        self.assertEqual(code, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["images"][0]["bg"], "transparent")
        self.assertEqual(len(out["views"]), 1)
        self.assertEqual(codes(out, "warn"), set())

    def test_fake_format_png_named_jpg(self):
        src = four_view_sheet(self.tmp / "a.png")
        dst = self.tmp / "a.jpg"
        os.rename(src, dst)
        code, out, _ = run_cli(dst)
        self.assertIn("FAKE_FORMAT", codes(out, "warn"))

    def test_single_mode_counts_one_object(self):
        code, out, _ = run_cli(four_view_sheet(self.tmp / "s.png"), "--views", "single")
        self.assertIn("MULTI_OBJECT", codes(out, "fail"))

    def test_background_auto_and_override(self):
        p = self.tmp / "blue.png"
        c = Canvas(1400, 1400, (20, 40, 220))
        c.ell(200, 0, 1200, 1300, (240, 200, 30))   # touches the top edge: mode still blue
        c.save(p)
        code, out, proc = run_cli(p)
        self.assertEqual(code, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["images"][0]["bg"], "#1428dc")
        self.assertEqual(len(out["views"]), 1)
        auto_box = out["views"][0]["bbox_px"]
        code, out, _ = run_cli(p, "--bg", "#F0C81E")   # the object colour: object becomes bg
        self.assertEqual(out["images"][0]["bg"], "#f0c81e")
        self.assertEqual(out["views"][0]["bbox_px"], [0, 0, 1400, 1400])
        self.assertNotEqual(out["views"][0]["bbox_px"], auto_box)

    def test_usage_errors(self):
        p = four_view_sheet(self.tmp / "u.png")
        self.assertEqual(run_cli(p, "--bg", "green")[0], 2)
        self.assertEqual(run_cli(p, "--views", "grid")[0], 2)
        self.assertEqual(run_cli()[0], 2)
        junk = self.tmp / "junk.png"
        junk.write_bytes(b"not an image at all")
        code, out, _ = run_cli(junk)
        self.assertEqual(code, 2)
        self.assertFalse(out["ok"])

    def test_missing_image_exit_3(self):
        code, out, _ = run_cli(self.tmp / "nope.png")
        self.assertEqual(code, 3)
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
