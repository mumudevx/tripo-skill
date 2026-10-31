import os
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.util import BLENDER, ROOT, fixture, skip_if_missing, tmpdir

import bl
import glbstat

HELPERS = ROOT / "tests" / "blender"
_CACHE = {}
_TMP = []


def out_dir() -> Path:
    if not _TMP:
        _TMP.append(tmpdir("tripo-normalize-"))
    return _TMP[0]


def tearDownModule():
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def normalize(name, *args):
    """Run normalize.py once per (fixture, args) for the whole module; return (result, glb)."""
    key = (name, args)
    if key not in _CACHE:
        src = fixture(name)
        skip_if_missing(src)
        os.environ["BLENDER"] = BLENDER
        out = out_dir() / f"n{len(_CACHE)}.glb"
        _CACHE[key] = (bl.run("normalize.py", [str(src), "--out-model", str(out), *args]), out)
    return _CACHE[key]


def glb_doc(path):
    doc, _ = glbstat.parse_glb(Path(path).read_bytes())
    return doc


def file_bounds(path):
    """(min, max) of every POSITION accessor in the GLB, glTF axes (Y up). Asserts that no
    node carries a transform, so accessor bounds are the model's bounds."""
    doc = glb_doc(path)
    for node in doc.get("nodes", []):
        assert not any(k in node for k in ("matrix", "translation", "rotation", "scale")), node
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            lo = [min(a, b) for a, b in zip(lo, acc["min"])]
            hi = [max(a, b) for a, b in zip(hi, acc["max"])]
    return lo, hi


# yaw -90 as a separate argument also checks that a negative value parses
TARGET = ("--target-height", "0.5", "--pivot", "bottom_center", "--name", "jerry_can",
          "--yaw", "-90")


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class Normalize(unittest.TestCase):
    def test_target_height(self):
        r, glb = normalize("jerry_can_g3", *TARGET)
        self.assertAlmostEqual(r["bbox"]["size"][2], 0.5, delta=0.5 * 0.005)
        lo, hi = file_bounds(glb)                       # glTF Y is Blender Z
        self.assertAlmostEqual(hi[1] - lo[1], 0.5, delta=0.5 * 0.005)
        self.assertEqual(r["out_model"], str(glb))
        self.assertLess(r["scale_applied"], 1.0)

    def test_pivot_bottom_center(self):
        r, glb = normalize("jerry_can_g3", *TARGET)
        lo, hi = r["bbox"]["min"], r["bbox"]["max"]
        self.assertEqual(r["pivot"], "bottom_center")
        self.assertAlmostEqual(lo[2], 0.0, delta=1e-4)
        self.assertAlmostEqual((lo[0] + hi[0]) / 2, 0.0, delta=1e-4)
        self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0.0, delta=1e-4)
        flo, fhi = file_bounds(glb)
        self.assertAlmostEqual(flo[1], 0.0, delta=1e-4)
        self.assertAlmostEqual((flo[0] + fhi[0]) / 2, 0.0, delta=1e-4)
        self.assertAlmostEqual((flo[2] + fhi[2]) / 2, 0.0, delta=1e-4)

    def test_yaw_90(self):
        r0, _ = normalize("jerry_can_g3", "--yaw", "0")
        r90, _ = normalize("jerry_can_g3", "--yaw", "90")
        s0, s90 = r0["bbox"]["size"], r90["bbox"]["size"]
        self.assertGreater(abs(s0[0] - s0[1]) / max(s0[:2]), 0.05)  # the swap is visible
        self.assertAlmostEqual(s90[0], s0[1], delta=0.01 * s0[1])
        self.assertAlmostEqual(s90[1], s0[0], delta=0.01 * s0[0])
        self.assertAlmostEqual(s90[2], s0[2], delta=0.01 * s0[2])
        self.assertEqual((r0["yaw"], r90["yaw"]), (0.0, 90.0))
        self.assertEqual(r90["scale_applied"], 1.0)

    def test_normals_preserved(self):
        r, glb = normalize("jerry_can_g3", *TARGET)
        offset = ",".join(repr(x) for x in r["offset"])
        c = bl.run(str(HELPERS / "compare_normals.py"),
                   [str(fixture("jerry_can_g3")), str(glb), "--yaw", r["yaw"],
                    "--scale", r["scale_applied"], f"--offset={offset}"])
        self.assertGreaterEqual(c["matched"], 0.98 * c["tris_out"], c)
        self.assertLess(c["max_angle_deg"], 0.5, c)
        self.assertGreaterEqual(r["normals"]["kept"], 0.99 * r["tris"], r["normals"])

    def test_names(self):
        r, glb = normalize("jerry_can_g3", *TARGET)
        doc = glb_doc(glb)
        roots = doc["scenes"][doc.get("scene", 0)]["nodes"]
        self.assertEqual(len(roots), 1)
        self.assertEqual(doc["nodes"][roots[0]]["name"], "jerry_can")
        self.assertTrue(doc["meshes"][0]["name"].startswith("jerry_can"), doc["meshes"][0])
        self.assertTrue(doc["materials"][0]["name"].startswith("jerry_can"))
        self.assertTrue(doc["images"][0]["name"].startswith("jerry_can"), doc["images"][0])
        self.assertEqual(r["renamed"]["objects"], {
            "tripo_node_a08c5dde-a5e0-4d52-846b-d336606f6e3c": "jerry_can"})
        for kind in ("meshes", "materials", "images"):
            self.assertTrue(r["renamed"][kind], kind)

    def test_no_name_renames_nothing(self):
        r, _ = normalize("jerry_can_g3", "--yaw", "0")
        self.assertEqual(r["renamed"], {})


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class NormalizeFbx(unittest.TestCase):
    def test_fbx_with_parent_transform(self):
        # FBX input whose mesh sits under a scaled empty and carries its own rotation,
        # scale and offset: apply-transforms and the keeper must both see through them
        glb = fixture("jerry_can_g3")
        skip_if_missing(glb)
        d = tmpdir()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        fbx, script = d / "jc.fbx", d / "to_fbx.py"
        script.write_text(
            "import bpy, math\n"
            "for o in list(bpy.data.objects): bpy.data.objects.remove(o)\n"
            f"bpy.ops.import_scene.gltf(filepath={str(glb)!r})\n"
            "m = [o for o in bpy.data.objects if o.type == 'MESH'][0]\n"
            "root = bpy.data.objects.new('root', None)\n"
            "bpy.context.scene.collection.objects.link(root)\n"
            "root.scale = (2.0, 2.0, 2.0); root.location = (1.0, 0.5, -0.3)\n"
            "m.parent = root; m.rotation_euler = (0.0, 0.0, math.radians(35))\n"
            "m.scale = (0.7, 0.7, 0.7); m.location = (0.2, -0.1, 0.4)\n"
            f"bpy.ops.export_scene.fbx(filepath={str(fbx)!r})\n")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "4",
                        "--python", str(script)], capture_output=True, check=True)
        os.environ["BLENDER"] = BLENDER
        out = d / "out.glb"
        r = bl.run("normalize.py", [str(fbx), "--out-model", str(out), "--target-height", "0.5",
                                    "--name", "jerry_can"])
        self.assertAlmostEqual(r["bbox"]["size"][2], 0.5, delta=0.5 * 0.005)
        self.assertAlmostEqual(r["bbox"]["min"][2], 0.0, delta=1e-4)
        lo, hi = file_bounds(out)                  # no node transform left in the file
        self.assertAlmostEqual(hi[1] - lo[1], 0.5, delta=0.5 * 0.005)
        doc = glb_doc(out)
        self.assertEqual([doc["nodes"][i]["name"] for i in doc["scenes"][0]["nodes"]],
                         ["jerry_can"])           # the empty parent is gone
        offset = ",".join(repr(x) for x in r["offset"])
        c = bl.run(str(HELPERS / "compare_normals.py"),
                   [str(fbx), str(out), "--scale", r["scale_applied"], f"--offset={offset}"])
        self.assertGreaterEqual(c["matched"], 0.98 * c["tris_out"], c)
        self.assertLess(c["max_angle_deg"], 0.5, c)


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class NormalKeeperProbe(unittest.TestCase):
    def test_only_changed_triangles_rebuilt(self):
        os.environ["BLENDER"] = BLENDER
        p = bl.run(str(HELPERS / "keeper_probe.py"), [])
        self.assertGreater(p["touching"], 0)
        self.assertEqual(p["rebuilt"], p["touching"], p)
        self.assertEqual(p["kept"], p["tris"] - p["touching"], p)
        self.assertLess(p["kept_max_dev_deg"], 0.1, p)          # transform followed exactly
        self.assertGreater(p["rebuilt_median_dev_deg"], 10, p)  # really rebuilt
        self.assertLess(p["rebuilt_max_face_dev_deg"], 30.01, p)  # smooth-by-angle 30


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class NormalizeSynthetic(unittest.TestCase):
    def setUp(self):
        os.environ["BLENDER"] = BLENDER
        self.d = tmpdir()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        (self.d / "box.obj").write_text(
            "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0 0 1\nv 1 0 1\nv 1 1 1\nv 0 1 1\n"
            "f 1 4 3 2\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n")

    def test_missing_input_exits_3(self):
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run("normalize.py", [str(self.d / "nope.glb"), "--out-model",
                                    str(self.d / "o.glb")])
        self.assertEqual(cm.exception.code, 3)

    def test_both_targets_is_usage_error(self):
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run("normalize.py", [str(self.d / "box.obj"), "--out-model", str(self.d / "o.glb"),
                                    "--target-height", "1", "--target-size", "1,1,1"])
        self.assertEqual(cm.exception.code, 2)

    def test_obj_input_target_size_fits_largest_axis(self):
        # a 1 m cube, OBJ (non-GLB input), stale output in place: fit into 2 x 4 x 4 -> scale 2
        out = self.d / "o.glb"
        out.write_bytes(b"stale")
        r = bl.run("normalize.py", [str(self.d / "box.obj"), "--out-model", str(out),
                                    "--target-size", "2,4,4", "--pivot", "center"])
        self.assertAlmostEqual(r["scale_applied"], 2.0, places=5)
        for lo, hi in zip(r["bbox"]["min"], r["bbox"]["max"]):
            self.assertAlmostEqual(lo, -1.0, places=4)
            self.assertAlmostEqual(hi, 1.0, places=4)
        self.assertEqual(out.read_bytes()[:4], b"glTF")

    def test_rigged_input_is_usage_error(self):
        src = fixture("crew_rigged")
        skip_if_missing(src)
        out = self.d / "rig.glb"
        with self.assertRaises(bl.BlenderError) as cm:
            bl.run("normalize.py", [str(src), "--out-model", str(out)])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("rigged", cm.exception.stderr_tail)
        self.assertFalse(out.exists())

    def test_two_meshes_get_a_root_and_part_names(self):
        box = (self.d / "box.obj").read_text().splitlines()
        verts, faces = [l for l in box if l.startswith("v ")], [l for l in box if l.startswith("f ")]
        moved = [f"v {float(x) + 3} {y} {z}" for _, x, y, z in (l.split() for l in verts)]
        shifted = [" ".join(["f"] + [str(int(i) + 8) for i in l.split()[1:]]) for l in faces]
        (self.d / "two.obj").write_text("\n".join(["o a", *verts, *faces, "o b", *moved,
                                                     *shifted]) + "\n")
        out = self.d / "two.glb"
        r = bl.run("normalize.py", [str(self.d / "two.obj"), "--out-model", str(out),
                                    "--name", "crate"])
        self.assertEqual(r["renamed"]["root"], "crate")
        self.assertEqual(sorted(r["renamed"]["objects"].values()),
                         ["crate_part_01", "crate_part_02"])
        doc = glb_doc(out)
        root = doc["nodes"][doc["scenes"][0]["nodes"][0]]
        self.assertEqual(root["name"], "crate")
        self.assertEqual(sorted(doc["nodes"][i]["name"] for i in root["children"]),
                         ["crate_part_01", "crate_part_02"])
        self.assertEqual(r["tris"], 24)
        self.assertAlmostEqual(r["bbox"]["size"][0], 4.0, places=4)
