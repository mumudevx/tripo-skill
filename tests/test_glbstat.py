import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.util import BLENDER, ROOT, SCRIPTS, fixture, skip_if_missing, tmpdir

import common
import glbstat

CLI = str(SCRIPTS / "glbstat.py")


def run_cli(*args):
    return subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True)


class GlbstatFixtures(unittest.TestCase):
    def stat(self, name):
        p = fixture(name)
        skip_if_missing(p)
        return glbstat.stat(p)

    def test_pedal_car_tris(self):
        s = self.stat("pedal_car_raw")
        self.assertEqual(s["format"], "glb")
        self.assertEqual(s["tris"], 12367)

    def test_crew_rigged_skin(self):
        s = self.stat("crew_rigged")
        self.assertEqual((s["skins"], s["joints"], s["animations"]), (1, 27, 0))

    def test_tool_chest_g1_tris(self):
        self.assertEqual(self.stat("tool_chest_g1")["tris"], 17430)

    def test_documented_tri_counts(self):
        expected = {
            "tool_chest_g3": 9327, "pickup_g2": 9625, "crew_apose_raw": 7884,
            "jerry_can_g2": 10710, "jerry_can_g3": 10567, "bicycle_v1": 7990,
            "bicycle_v2": 10907, "back_panel_v2_20k": 29943,
            "top_plate_full": 1391172, "top_plate_reduced": 2443,
            "mailbox_letter_dec2000": 2000, "engine_block_g1": 10274,
        }
        for name, tris in expected.items():
            with self.subTest(name):
                self.assertEqual(self.stat(name)["tris"], tris)

    def test_shape_of_result(self):
        s = self.stat("pedal_car_raw")
        for key in ("tris", "meshes", "primitives", "materials", "images",
                    "skins", "joints", "animations", "bytes"):
            self.assertIn(key, s)
        self.assertGreater(s["bytes"], 0)
        self.assertGreaterEqual(len(s["images"]), 1)
        for img in s["images"]:
            self.assertEqual(set(img), {"name", "mime", "width", "height", "bytes"})
            self.assertIn(img["mime"], ("image/png", "image/jpeg", "image/webp"))
            self.assertGreater(img["width"], 0)
            self.assertGreater(img["height"], 0)


class GlbstatSynthetic(unittest.TestCase):
    """Container and header parsing on files built in a temp dir."""

    def setUp(self):
        self.tmp = tmpdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write_glb(self, doc, blob=b""):
        import struct
        js = json.dumps(doc).encode()
        js += b" " * (-len(js) % 4)
        blob += b"\0" * (-len(blob) % 4)
        body = struct.pack("<II", len(js), 0x4E4F534A) + js
        if blob:
            body += struct.pack("<II", len(blob), 0x004E4942) + blob
        data = b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body
        p = self.tmp / "m.glb"
        p.write_bytes(data)
        return p

    def test_non_indexed_triangles(self):
        doc = {"asset": {"version": "2.0"},
               "accessors": [{"count": 9}],
               "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
        s = glbstat.stat(self.write_glb(doc))
        self.assertEqual((s["tris"], s["meshes"], s["primitives"]), (3, 1, 1))

    def test_indexed_and_non_triangle_modes(self):
        doc = {"asset": {"version": "2.0"},
               "accessors": [{"count": 30}, {"count": 100}],
               "meshes": [{"primitives": [
                   {"attributes": {"POSITION": 1}, "indices": 0},
                   {"attributes": {"POSITION": 1}, "indices": 0, "mode": 1}]}]}
        self.assertEqual(glbstat.stat(self.write_glb(doc))["tris"], 10)

    def test_image_sizes_from_headers(self):
        import struct
        png = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
               + struct.pack(">II", 64, 32) + b"\x08\x06\0\0\0")
        jpeg = (b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0" + b"\0" * 9
                + b"\xff\xc0" + struct.pack(">HBHH", 11, 8, 48, 96) + b"\0" * 8)
        webp = (b"RIFF" + struct.pack("<I", 22) + b"WEBPVP8 " + struct.pack("<I", 10)
                + b"\0" * 6 + struct.pack("<HH", 40, 20))
        blob = png + jpeg + webp
        views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(png)},
                 {"buffer": 0, "byteOffset": len(png), "byteLength": len(jpeg)},
                 {"buffer": 0, "byteOffset": len(png) + len(jpeg), "byteLength": len(webp)}]
        doc = {"asset": {"version": "2.0"}, "bufferViews": views,
               "images": [{"bufferView": 0, "name": "a"}, {"bufferView": 1},
                          {"bufferView": 2}]}
        imgs = glbstat.stat(self.write_glb(doc, blob))["images"]
        self.assertEqual([(i["mime"], i["width"], i["height"]) for i in imgs],
                         [("image/png", 64, 32), ("image/jpeg", 96, 48),
                          ("image/webp", 40, 20)])
        self.assertEqual(imgs[0]["name"], "a")
        self.assertEqual(imgs[0]["bytes"], len(png))

    def test_gltf_json_detected(self):
        p = self.tmp / "scene.dat"
        p.write_text(json.dumps({"asset": {"version": "2.0"},
                                 "accessors": [{"count": 6}],
                                 "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}))
        s = glbstat.stat(p)
        self.assertEqual((s["format"], s["tris"]), ("gltf", 2))

    def test_format_comes_from_magic_not_extension(self):
        obj = self.tmp / "thing.glb"
        obj.write_text("# cube\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
        self.assertEqual(glbstat.stat(obj)["format"], "obj")
        junk = self.tmp / "junk.glb"
        junk.write_bytes(b"\x00\x01\x02\x03" * 8)
        self.assertEqual(glbstat.stat(junk), {"format": "unknown", "bytes": 32})

    def test_truncated_glb_is_an_error(self):
        p = self.write_glb({"asset": {"version": "2.0"}})
        p.write_bytes(p.read_bytes()[:-8])
        r = run_cli(str(p))
        self.assertEqual(r.returncode, common.EXIT_CHECK)
        self.assertFalse(json.loads(r.stdout)["ok"])


class GlbstatFbx(unittest.TestCase):
    def test_fbx_passthrough(self):
        if not os.path.exists(BLENDER):
            self.skipTest("blender not available and no FBX fixture")
        tmp = tmpdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fbx = tmp / "cube.fbx"
        script = tmp / "mk.py"
        script.write_text(
            "import bpy\n"
            "bpy.ops.mesh.primitive_cube_add()\n"
            f"bpy.ops.export_scene.fbx(filepath={str(fbx)!r})\n")
        subprocess.run([BLENDER, "--background", "--factory-startup",
                        "--python-exit-code", "4", "--python", str(script)],
                       capture_output=True, check=True)
        renamed = tmp / "x.glb"
        fbx.rename(renamed)
        s = glbstat.stat(renamed)
        self.assertEqual(s["format"], "fbx")
        self.assertEqual(s["note"], "use blender/qa.py")
        self.assertEqual(s["bytes"], renamed.stat().st_size)
        self.assertNotIn("tris", s)


class GlbstatCli(unittest.TestCase):
    def test_missing_file_exit_3(self):
        r = run_cli("/nonexistent/definitely/missing.glb")
        self.assertEqual(r.returncode, common.EXIT_NOT_FOUND)
        out = json.loads(r.stdout)
        self.assertFalse(out["ok"])
        self.assertIn("not found", out["error"])

    def test_usage_exit_2(self):
        self.assertEqual(run_cli().returncode, common.EXIT_USAGE)

    def test_one_json_line_with_flag(self):
        p = fixture("pedal_car_raw")
        skip_if_missing(p)
        for args in ([str(p)], [str(p), "--json"]):
            r = run_cli(*args)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(len(r.stdout.splitlines()), 1)
            out = json.loads(r.stdout)
            self.assertTrue(out["ok"])
            self.assertEqual(out["tris"], 12367)


class CommonHelpers(unittest.TestCase):
    def test_find_project_root_and_tripo_dir(self):
        tmp = tmpdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "project.godot").write_text("")
        deep = tmp / "a" / "b"
        deep.mkdir(parents=True)
        self.assertEqual(common.find_project_root(deep), tmp.resolve())
        self.assertEqual(common.find_project_root(tmp), tmp.resolve())
        self.assertEqual(common.tripo_dir(tmp), tmp / ".claude" / "tripo")

    def test_find_project_root_none(self):
        tmp = tmpdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        # a temp dir outside any Godot project
        self.assertIsNone(common.find_project_root(tmp / "nope"))

    def test_fail_emits_json_and_exits(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
            common.fail(common.EXIT_CHECK, "bad", detail=1)
        self.assertEqual(cm.exception.code, 5)
        self.assertEqual(json.loads(buf.getvalue()), {"ok": False, "error": "bad", "detail": 1})


class FixtureRegistry(unittest.TestCase):
    def test_all_registered_and_direct_tripo_only(self):
        table = json.loads((ROOT / "tests" / "fixtures.json").read_text())
        names = [k for k in table if not k.startswith("_")]
        for n in ("pedal_car_raw", "tool_chest_g1", "crew_rigged", "top_plate_full",
                  "engine_block_g1", *[f"R{i}" for i in range(1, 13)]):
            self.assertIn(n, names)
        for n in names:
            self.assertTrue(table[n].startswith("/"), n)
            self.assertNotIn("model_h31", table[n])
            self.assertNotIn("job3d", table[n])

    def test_unknown_fixture(self):
        with self.assertRaises(KeyError):
            fixture("nope")


if __name__ == "__main__":
    unittest.main()
