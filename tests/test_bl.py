import json
import os
import shutil
import subprocess
import sys
import textwrap
import unittest

from tests.util import BLENDER, SCRIPTS, fixture, skip_if_missing, tmpdir

import bl
import common

HEADER = "import skill_io as sio\n"


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class BlenderRunner(unittest.TestCase):
    def setUp(self):
        os.environ["BLENDER"] = BLENDER
        self.tmp = tmpdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def script(self, name, body):
        p = self.tmp / name
        p.write_text(HEADER + textwrap.dedent(body))
        return str(p)

    def test_roundtrip_json(self):
        s = self.script("ok.py", "sio.main(lambda a: {'x': 1})\n")
        self.assertEqual(bl.run(s, []), {"x": 1})

    def test_script_args_reach_the_script(self):
        s = self.script("args.py", """
            def cfg(p):
                p.add_argument("--n", type=int, required=True)
                p.add_argument("--name")
            sio.main(lambda a: {"n": a.n, "name": a.name}, cfg)
        """)
        self.assertEqual(bl.run(s, ["--n", "7", "--name", "a b"]), {"n": 7, "name": "a b"})

    def test_numpy_values_serialise(self):
        s = self.script("np.py", """
            import numpy as np
            sio.main(lambda a: {"f": np.float32(1.5), "i": np.int64(3), "v": np.arange(3)})
        """)
        self.assertEqual(bl.run(s, []), {"f": 1.5, "i": 3, "v": [0, 1, 2]})

    def test_python_error_nonzero(self):
        out = self.tmp / "out.json"
        s = self.script("boom.py", "sio.main(lambda a: 1 / 0)\n")
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run(s, [], out=str(out))
        self.assertEqual(cm.exception.code, 4)
        self.assertIn("ZeroDivisionError", cm.exception.stderr_tail)
        self.assertFalse(out.exists())

    def test_uncaught_exception_outside_main_is_nonzero(self):
        # a script that forgets _io.main still must not exit 0
        s = self.script("raw.py", "raise RuntimeError('plain failure')\n")
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run(s, [])
        self.assertEqual(cm.exception.code, 4)
        self.assertIn("plain failure", cm.exception.stderr_tail)

    def test_stale_out_removed(self):
        out = self.tmp / "stale.json"
        out.write_text('{"stale": true}')
        s = self.script("boom.py", "sio.main(lambda a: 1 / 0)\n")
        with self.assertRaises(bl.BlenderError):
            bl.run(s, [], out=str(out))
        self.assertFalse(out.exists())

    def test_missing_out_file_is_error(self):
        # exits 0 but writes nothing: the runner must not invent a result
        s = self.script("silent.py", "pass\n")
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run(s, [])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("no output file", cm.exception.stderr_tail)

    def test_non_json_dict_result_fails(self):
        s = self.script("bad.py", "sio.main(lambda a: {'x': float('nan')})\n")
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run(s, [])
        self.assertEqual(cm.exception.code, 4)

    def test_non_dict_result_fails(self):
        s = self.script("lst.py", "sio.main(lambda a: [1])\n")
        with self.assertRaises(bl.BlenderError):
            bl.run(s, [])

    def test_unknown_script_name(self):
        with self.assertRaises(FileNotFoundError):
            bl.run("no_such_script.py", [])

    def test_missing_blender_binary(self):
        os.environ["BLENDER"] = str(self.tmp / "nope")
        s = self.script("ok.py", "sio.main(lambda a: {})\n")
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run(s, [])
        self.assertIn("blender", cm.exception.stderr_tail.lower())

    def test_timeout(self):
        s = self.script("slow.py", "import time\ntime.sleep(30)\n")
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run(s, [], timeout=3)
        self.assertEqual(cm.exception.code, 124)

    def test_blender_noise_does_not_break_json(self):
        s = self.script("noisy.py", "print('noise on stdout')\nsio.main(lambda a: {'ok': True})\n")
        self.assertEqual(bl.run(s, []), {"ok": True})


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class LoadModel(unittest.TestCase):
    def setUp(self):
        os.environ["BLENDER"] = BLENDER
        self.tmp = tmpdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.loader = self.tmp / "load.py"
        self.loader.write_text(HEADER + textwrap.dedent("""
            import bpy
            def cfg(p):
                p.add_argument("--model", required=True)
            def run(a):
                objs = sio.load_model(a.model)
                meshes = [o for o in objs if o.type == "MESH"]
                return {"objects": len(objs), "meshes": len(meshes),
                        "scene_meshes": len([o for o in bpy.data.objects if o.type == "MESH"]),
                        "tris": sum(len(m.data.polygons) for m in meshes)}
            sio.main(run, cfg)
        """))

    def load(self, path):
        return bl.run(str(self.loader), ["--model", str(path)])

    def make(self, name, op, extra=""):
        script = self.tmp / ("mk_" + name + ".py")
        target = self.tmp / name
        script.write_text(
            "import bpy\n"
            "[bpy.data.objects.remove(o) for o in list(bpy.data.objects)]\n"
            "bpy.ops.mesh.primitive_cube_add()\n"
            f"bpy.ops.{op}(filepath={str(target)!r}{extra})\n")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "4",
                        "--python", str(script)], capture_output=True, check=True)
        return target

    def test_load_fbx_and_glb(self):
        glb = fixture("pedal_car_raw")
        skip_if_missing(glb)
        r = self.load(glb)
        self.assertGreaterEqual(r["meshes"], 1)
        # scene was cleared: only the imported meshes exist, no factory cube
        self.assertEqual(r["scene_meshes"], r["meshes"])
        fbx = self.make("cube.fbx", "export_scene.fbx")
        r = self.load(fbx)
        self.assertEqual((r["meshes"], r["scene_meshes"], r["tris"]), (1, 1, 6))  # 6 quad faces

    def test_format_comes_from_magic_not_extension(self):
        fbx = self.make("cube.fbx", "export_scene.fbx")
        disguised = self.tmp / "cube_disguised.glb"
        shutil.copy(fbx, disguised)
        self.assertEqual(self.load(disguised)["meshes"], 1)

    def test_load_obj_and_gltf(self):
        obj = self.make("cube.obj", "wm.obj_export")
        self.assertEqual(self.load(obj)["meshes"], 1)
        gltf = self.make("cube.gltf", "export_scene.gltf", ", export_format='GLTF_SEPARATE'")
        self.assertEqual(self.load(gltf)["meshes"], 1)

    def test_unknown_format_fails(self):
        junk = self.tmp / "junk.glb"
        junk.write_bytes(b"\x00\x01\x02not a model")
        with self.assertRaises(bl.BlenderError) as cm:
            self.load(junk)
        self.assertEqual(cm.exception.code, 4)

    def test_missing_file_fails(self):
        with self.assertRaises(bl.BlenderError) as cm:
            self.load(self.tmp / "missing.glb")
        self.assertEqual(cm.exception.code, 3)  # missing input -> EXIT_NOT_FOUND


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class BlCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env = {**os.environ, "BLENDER": BLENDER}

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "bl.py"), *args],
                              capture_output=True, text=True, env=self.env)

    def test_cli_echoes_json(self):
        s = self.tmp / "ok.py"
        s.write_text(HEADER + "sio.main(lambda a: {'x': 1})\n")
        r = self.cli(str(s), "--")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ['{"x":1}'])

    def test_cli_failure_exit_4(self):
        s = self.tmp / "boom.py"
        s.write_text(HEADER + "sio.main(lambda a: 1 / 0)\n")
        r = self.cli(str(s), "--")
        self.assertEqual(r.returncode, common.EXIT_INTERNAL)
        out = json.loads(r.stdout)
        self.assertFalse(out["ok"])
        self.assertEqual(out["blender_exit"], 4)
        self.assertIn("ZeroDivisionError", out["stderr_tail"])

    def test_cli_usage(self):
        self.assertEqual(self.cli().returncode, common.EXIT_USAGE)

    def test_cli_unknown_script_exit_3(self):
        r = self.cli("no_such_script.py", "--")
        self.assertEqual(r.returncode, common.EXIT_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
