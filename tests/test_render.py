import os
import shutil
import struct
import zlib
import unittest

from tests.util import BLENDER, fixture, skip_if_missing, tmpdir

import bl

PASS_NAMES = ["lit", "lit_no_normalmap", "albedo", "wire"]
VIEW_NAMES = ["front", "back", "left", "right", "top", "iso"]
CUBE_OBJ = "\n".join([
    "v -0.3 -0.2 0", "v 0.3 -0.2 0", "v 0.3 0.2 0", "v -0.3 0.2 0",
    "v -0.3 -0.2 0.5", "v 0.3 -0.2 0.5", "v 0.3 0.2 0.5", "v -0.3 0.2 0.5",
    "f 1 4 3 2", "f 5 6 7 8", "f 1 2 6 5", "f 3 4 8 7", "f 1 5 8 4", "f 2 3 7 6",
]) + "\n"

_CACHE = {}


def sheet(model, *args):
    """Run render_sheet.py once per (model, args) for the whole module; Blender runs are slow."""
    key = (str(model), args)
    if key not in _CACHE:
        os.environ["BLENDER"] = BLENDER
        out = tmpdir("tripo-sheet-test-")
        _CACHE[key] = (bl.run("render_sheet.py", [str(model), "--png", str(out / "sheet.png"), *args]), out)
    return _CACHE[key][0]


def tearDownModule():
    for _, out in _CACHE.values():
        shutil.rmtree(out, ignore_errors=True)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", head[16:24])


def png_rows(path):
    """Rows of grey values (R channel) of the 8-bit RGB, filter-0 PNG our sheet encoder writes."""
    data = open(path, "rb").read()
    w, h = struct.unpack(">II", data[16:24])
    pos, idat = 8, b""
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        if tag == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = 1 + 3 * w
    assert all(raw[r * stride] == 0 for r in range(h)), "unexpected PNG filter"
    return [raw[r * stride + 1:(r + 1) * stride:3] for r in range(h)]


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class RenderSheet(unittest.TestCase):
    def test_sheet_size(self):
        path = fixture("jerry_can_g3")
        skip_if_missing(path)
        r = sheet(path)
        self.assertTrue(os.path.isfile(r["png"]))
        self.assertLessEqual(max(r["width"], r["height"]), 1500)
        self.assertEqual(png_size(r["png"]), (r["width"], r["height"]))
        self.assertGreater(os.path.getsize(r["png"]), 20000)  # not a blank sheet

    def test_panels_complete(self):
        path = fixture("jerry_can_g3")
        skip_if_missing(path)
        r = sheet(path)
        self.assertEqual(len(r["panels"]), 24)
        self.assertEqual({(p["pass"], p["view"]) for p in r["panels"]},
                         {(a, b) for a in PASS_NAMES for b in VIEW_NAMES})
        self.assertEqual(len({p["name"] for p in r["panels"]}), 24)
        g = sheet(path, "--game-cam", "30,35,40")
        self.assertEqual(len(g["panels"]), 28)
        self.assertEqual({p["pass"] for p in g["panels"] if p["view"] == "game_cam"}, set(PASS_NAMES))
        self.assertLessEqual(max(g["width"], g["height"]), 1500)

    def test_bad_input_fails(self):
        os.environ["BLENDER"] = BLENDER
        out = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, out, True)
        png = out / "none.png"
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run("render_sheet.py", [str(out / "missing.glb"), "--png", str(png)])
        self.assertEqual(cm.exception.code, 3)
        self.assertFalse(png.exists())

    def test_bad_game_cam_is_usage_error(self):
        os.environ["BLENDER"] = BLENDER
        out = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, out, True)
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run("render_sheet.py", [str(out / "x.obj"), "--png", str(out / "a.png"),
                                       "--game-cam", "30,35"])
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse((out / "a.png").exists())

    def test_stale_png_removed_on_failure(self):
        os.environ["BLENDER"] = BLENDER
        out = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, out, True)
        png = out / "old.png"
        png.write_bytes(b"stale")
        with self.assertRaises(bl.BlenderError):
            bl.run("render_sheet.py", [str(out / "missing.glb"), "--png", str(png)])
        self.assertFalse(png.exists())

    def test_obj_input_front_flag_and_light_sweep(self):
        d = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, d, True)
        model = d / "cube.obj"            # no materials, no UVs: the default-grey path
        model.write_text(CUBE_OBJ)
        r = sheet(model, "--front", "+x", "--light-sweep")
        self.assertEqual(r["front"], "+x")
        self.assertEqual(r["tris"], 12)
        self.assertEqual(len(r["panels"]), 28)
        sweep = [p for p in r["panels"] if p["pass"] == "lit_sweep"]
        self.assertEqual(len(sweep), 4)
        self.assertEqual({p["row"] for p in sweep}, {4})
        self.assertTrue(os.path.isfile(r["png"]))
        self.assertLessEqual(max(r["width"], r["height"]), 1500)
        # a 0.6 m model gets the 0.1 m grid, a 3 m model would get 1 m (see render_sheet.grid_spacing)
        self.assertEqual(r["grid_m"], 0.1)

    def test_model_with_world_offset_is_in_every_panel(self):
        d = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, d, True)
        shifted = []
        for line in CUBE_OBJ.splitlines():     # OBJ (50, 20, -30) is Blender (50, 30, 20)
            if line.startswith("v "):
                x, y, z = map(float, line.split()[1:])
                line = f"v {x + 50} {y + 20} {z - 30}"
            shifted.append(line)
        model = d / "shifted.obj"
        model.write_text("\n".join(shifted) + "\n")
        r = sheet(model)
        self.assertEqual(len(r["panels"]), 24)
        rows = png_rows(r["png"])
        top, cw, ch = 22, r["width"] // 6, (r["height"] - 22) // 4   # header strip, 6 x 4 cells
        for p in r["panels"]:
            cell = [row[p["col"] * cw + 4:(p["col"] + 1) * cw - 4]
                    for row in rows[top + p["row"] * ch + 4:top + (p["row"] + 1) * ch - 4]]
            bright = sum(v > 150 for row in cell for v in row)    # background is dark grey (~77)
            self.assertGreater(bright / (len(cell) * len(cell[0])), 0.05, f"{p['name']} looks empty")

    def test_front_minus_x_as_separate_argument(self):
        d = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, d, True)
        model = d / "cube.obj"
        model.write_text(CUBE_OBJ)
        r = sheet(model, "--front", "-x")        # argparse would take '-x' for an option
        self.assertEqual(r["front"], "-x")
        self.assertEqual(len(r["panels"]), 24)

    def test_negative_game_cam_yaw_as_separate_argument(self):
        d = tmpdir("tripo-sheet-test-")
        self.addCleanup(shutil.rmtree, d, True)
        model = d / "cube.obj"
        model.write_text(CUBE_OBJ)
        r = sheet(model, "--game-cam", "-30,35,40")
        self.assertEqual(len(r["panels"]), 28)


if __name__ == "__main__":
    unittest.main()
