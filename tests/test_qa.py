import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.util import BLENDER, SCRIPTS, fixture, skip_if_missing, tmpdir

import bl

THRESHOLDS = SCRIPTS / "data" / "qa_thresholds.json"
METRIC_KEYS = {
    "tris", "verts", "verts_welded", "meshes", "materials", "images", "bbox", "weld_eps",
    "boundary_edges", "nonmanifold_edges", "islands", "flipped_pct", "sliver_pct", "ground",
    "asymmetry", "back_relief", "uv", "texel_density", "palette", "baked_light", "skin",
}
CODES = {
    "OVER_BUDGET", "NON_MANIFOLD", "HOLES", "LOOSE_PARTS", "FLIPPED_NORMALS", "SLIVERS",
    "GROUND_SLAB", "NOT_GROUNDED", "ASYMMETRY", "BACK_COPY", "UV_OVERLAP", "LOW_TEXEL",
    "PALETTE_DRIFT", "BAKED_LIGHT", "TOO_MANY_INFLUENCES", "MULTI_MATERIAL", "TEXTURE_OVERSIZE",
}

_CACHE = {}


def qa(model, *args):
    """Run qa.py once per (model, args) for the whole module; Blender runs are slow."""
    key = (str(model), args)
    if key not in _CACHE:
        os.environ["BLENDER"] = BLENDER
        _CACHE[key] = bl.run("qa.py", [str(model), *map(str, args)])
    return _CACHE[key]


def qa_fixture(name, *args):
    path = fixture(name)
    skip_if_missing(path)
    return qa(path, *args)


def by_code(report, code):
    return [f for f in report["findings"] if f["code"] == code]


def box_obj(boxes, inward_normals=False):
    """OBJ text for closed boxes given in Blender coordinates (x0, x1, y0, y1, z0, z1),
    faces wound outward. The OBJ importer maps OBJ (X, Y, Z) to Blender (X, -Z, Y), so a
    Blender point (x, y, z) is written as `v x z -y`. Each face carries a `vn`: outward,
    or pointing inward when `inward_normals` is set."""
    quads = [((0, 3, 2, 1), (0, 0, -1)), ((4, 5, 6, 7), (0, 0, 1)),
             ((0, 1, 5, 4), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
             ((0, 4, 7, 3), (-1, 0, 0)), ((1, 2, 6, 5), (1, 0, 0))]
    lines, nv, nn = [], 0, 0
    for x0, x1, y0, y1, z0, z1 in boxes:
        corners = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                   (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        lines += [f"v {x} {z} {-y}" for x, y, z in corners]
        for quad, (x, y, z) in quads:
            s = -1 if inward_normals else 1
            lines.append(f"vn {s * x} {s * z} {-s * y}")
            nn += 1
            lines.append("f " + " ".join(f"{nv + i + 1}//{nn}" for i in quad))
        nv += 8
    return "\n".join(lines) + "\n"


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class QaFixtures(unittest.TestCase):
    def test_budget_overshoot(self):
        r = qa_fixture("tool_chest_g1", "--budget", 8000, "--symmetric", "x")
        self.assertEqual(r["metrics"]["tris"], 17430)
        f = by_code(r, "OVER_BUDGET")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "S0")
        self.assertEqual(f[0]["value"], 17430)
        self.assertEqual(f[0]["threshold"], 8000)

    def test_pedal_car_budget(self):
        r = qa_fixture("pedal_car_raw", "--budget", 10000)
        f = by_code(r, "OVER_BUDGET")
        self.assertEqual([x["severity"] for x in f], ["S1"])

    def test_weld_first(self):
        r = qa_fixture("pedal_car_raw", "--budget", 10000)
        m = r["metrics"]
        self.assertGreater(m["boundary_edges_raw"], 0)
        self.assertLess(m["boundary_edges"], 0.05 * m["boundary_edges_raw"])
        self.assertLess(m["verts_welded"], m["verts"])

    def test_asymmetry_tool_chest(self):
        g1 = qa_fixture("tool_chest_g1", "--budget", 8000, "--symmetric", "x")
        final = qa_fixture("tool_chest_final", "--symmetric", "x")
        self.assertEqual(len(by_code(g1, "ASYMMETRY")), 1)
        self.assertEqual(by_code(final, "ASYMMETRY"), [])
        self.assertGreater(g1["metrics"]["asymmetry"]["mean_dist_pct"],
                           final["metrics"]["asymmetry"]["mean_dist_pct"])

    def test_asymmetry_needs_declaration(self):
        r = qa_fixture("tool_chest_g1")
        self.assertEqual(by_code(r, "ASYMMETRY"), [])
        self.assertIsNone(r["metrics"]["asymmetry"]["axis"])

    def test_slivers_bicycle(self):
        v1 = qa_fixture("bicycle_v1")
        v2 = qa_fixture("bicycle_v2")
        self.assertGreater(v1["metrics"]["sliver_pct"], v2["metrics"]["sliver_pct"])

    def test_influences(self):
        r = qa_fixture("crew_rigged")
        skin = r["metrics"]["skin"]
        self.assertEqual(skin["joints"], 27)
        self.assertGreater(skin["max_influences"], 0)
        self.assertLessEqual(skin["max_influences"], 4)
        self.assertEqual(by_code(r, "TOO_MANY_INFLUENCES"), [])
        # the importer's bone-shape icosphere is not part of the model
        self.assertEqual(r["metrics"]["meshes"], 1)
        self.assertEqual(r["metrics"]["tris"], 7884)

    def test_fbx_input(self):
        glb = fixture("jerry_can_g3")
        skip_if_missing(glb)
        tmp = tmpdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fbx = tmp / "jerry_can.fbx"
        script = tmp / "to_fbx.py"
        script.write_text(
            "import bpy\n"
            "for o in list(bpy.data.objects): bpy.data.objects.remove(o)\n"
            f"bpy.ops.import_scene.gltf(filepath={str(glb)!r})\n"
            f"bpy.ops.export_scene.fbx(filepath={str(fbx)!r}, path_mode='COPY', "
            "embed_textures=True)\n")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "4",
                        "--python", str(script)], capture_output=True, check=True)
        a = qa(glb)
        b = qa(fbx)
        self.assertEqual(b["format"], "fbx")
        self.assertEqual(a["format"], "glb")
        self.assertEqual(b["metrics"]["tris"], a["metrics"]["tris"])

    def test_palette(self):
        ref = fixture("R5")
        skip_if_missing(ref)
        r = qa_fixture("jerry_can_g3", "--ref-palette", ref)
        pal = r["metrics"]["palette"]
        self.assertIsInstance(pal["delta_e_mean"], float)
        self.assertGreaterEqual(pal["delta_e_mean"], 0.0)
        self.assertIsNone(qa_fixture("jerry_can_g3")["metrics"]["palette"])

    def test_schema(self):
        r = qa_fixture("tool_chest_g1", "--budget", 8000, "--symmetric", "x")
        self.assertEqual(r["schema"], "qa/1")
        self.assertEqual(r["format"], "glb")
        self.assertEqual(r["file"], str(fixture("tool_chest_g1")))
        m = r["metrics"]
        self.assertLessEqual(METRIC_KEYS, set(m))
        self.assertEqual(set(m["bbox"]), {"min", "max", "size"})
        self.assertAlmostEqual(m["weld_eps"],
                               1e-5 * sum(s * s for s in m["bbox"]["size"]) ** 0.5, places=9)
        self.assertEqual(set(m["ground"]), {"min_z", "low_band_tris_pct", "slab"})
        self.assertEqual(set(m["uv"]), {"overlap_pct", "oob_pct"})
        self.assertEqual(set(m["skin"]), {"joints", "max_influences"})
        self.assertIn("score", m["baked_light"])
        self.assertTrue(all(set(i) == {"name", "w", "h"} for i in m["images"]))
        self.assertEqual(m["images"][0]["w"], 4096)
        isl = m["islands"]
        self.assertTrue(isl and all(set(i) == {"tris", "bbox_pct"} for i in isl))
        self.assertEqual([i["tris"] for i in isl], sorted((i["tris"] for i in isl), reverse=True))
        self.assertTrue(0.0 <= m["back_relief"] <= 1.0)
        self.assertGreater(m["texel_density"], 0)
        self.assertTrue(r["findings"])
        for i, f in enumerate(r["findings"], 1):
            self.assertEqual(set(f), {"id", "code", "severity", "message", "value",
                                      "threshold", "fix_options"})
            self.assertEqual(f["id"], f"F{i}")
            self.assertIn(f["code"], CODES)
            self.assertIn(f["severity"], {"S0", "S1", "S2", "info"})
            self.assertIsInstance(f["fix_options"], list)


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class QaSynthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_degenerate_mesh_gives_nulls_not_nan(self):
        # one zero-area triangle, no UVs: every area ratio is undefined
        obj = self.tmp / "flat.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 2 0 0\nf 1 2 3\n")
        r = qa(obj)
        m = r["metrics"]
        self.assertEqual(r["format"], "obj")
        self.assertEqual(m["tris"], 1)
        self.assertIsNone(m["texel_density"])
        self.assertIsNone(m["uv"]["overlap_pct"])
        self.assertEqual(m["skin"], {"joints": 0, "max_influences": 0})

    def test_ground_slab(self):
        cube = (-0.4, 0.4, -0.4, 0.4, 0.02, 1.0)
        plate = (-1.0, 1.0, -1.0, 1.0, 0.0, 0.02)  # 2 % of the height, wider than the cube
        on_plate = self.tmp / "slab.obj"
        on_plate.write_text(box_obj([cube, plate]))
        alone = self.tmp / "cube.obj"
        alone.write_text(box_obj([cube]))
        r = qa(on_plate)
        self.assertTrue(r["metrics"]["ground"]["slab"])
        self.assertEqual(len(by_code(r, "GROUND_SLAB")), 1)
        self.assertEqual([i["tris"] for i in r["metrics"]["islands"]], [12, 12])
        c = qa(alone)
        # a flat-bottomed box sits on its own bottom face: no slab, and no holes after weld
        self.assertFalse(c["metrics"]["ground"]["slab"])
        self.assertEqual(by_code(c, "GROUND_SLAB"), [])
        self.assertEqual(c["metrics"]["boundary_edges"], 0)
        self.assertEqual(c["metrics"]["nonmanifold_edges"], 0)

    def test_flipped_normals(self):
        good = self.tmp / "good.obj"
        good.write_text(box_obj([(0, 1, 0, 1, 0, 1)]))
        bad = self.tmp / "bad.obj"
        bad.write_text(box_obj([(0, 1, 0, 1, 0, 1)], inward_normals=True))
        self.assertEqual(qa(good)["metrics"]["flipped_pct"], 0.0)
        r = qa(bad)
        self.assertEqual(r["metrics"]["flipped_pct"], 100.0)
        self.assertEqual(len(by_code(r, "FLIPPED_NORMALS")), 1)

    def test_uncalibrated_codes_are_info(self):
        table = json.loads(THRESHOLDS.read_text())
        self.assertIn("preflight", table)  # Task 3's key stays untouched
        sev = table["qa"]["severity"]
        self.assertEqual(set(sev), CODES)
        self.assertTrue(all(v in {"S0", "S1", "S2", "info", "rule"} for v in sev.values()))

    def test_missing_model_fails(self):
        os.environ["BLENDER"] = BLENDER
        with self.assertRaises(bl.BlenderError):
            bl.run("qa.py", [str(self.tmp / "nope.glb")])

    def test_cli_one_json_line(self):
        obj = self.tmp / "tri.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
        p = subprocess.run([sys.executable, str(SCRIPTS / "bl.py"), "qa.py", "--", str(obj),
                            "--budget", "1"], capture_output=True, text=True,
                           env=dict(os.environ, BLENDER=BLENDER))
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["schema"], "qa/1")


if __name__ == "__main__":
    unittest.main()
