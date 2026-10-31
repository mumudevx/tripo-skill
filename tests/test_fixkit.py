import json
import math
import os
import shutil
import stat
import subprocess
import unittest
from pathlib import Path

from tests.util import BLENDER, ROOT, SCRIPTS, fixture, skip_if_missing, tmpdir

import bl
import glbstat

HELPERS = ROOT / "tests" / "blender"
THRESHOLDS = SCRIPTS / "data" / "qa_thresholds.json"
_TMP = []
_CACHE = {}


def scratch() -> Path:
    if not _TMP:
        _TMP.append(tmpdir("tripo-fixkit-"))
    return _TMP[0]


def tearDownModule():
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def write_recipe(d: Path, source, steps, asset="asset", name="r.recipe.json") -> Path:
    path = d / name
    path.write_text(json.dumps({"schema": "recipe/1", "asset": asset, "source": str(source),
                                "steps": [{"op": op, "params": params}
                                          for op, params in steps]}))
    return path


def apply(recipe: Path, work: Path) -> dict:
    os.environ["BLENDER"] = BLENDER
    return bl.run("apply_recipe.py", [str(recipe), "--work", str(work)])


def qa(model, *args) -> dict:
    os.environ["BLENDER"] = BLENDER
    return bl.run("qa.py", [str(model), *map(str, args)])


def cached(key, fn):
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


def obj_text(parts) -> str:
    """OBJ text for meshes given in Blender coordinates: parts = [(verts, faces)], faces
    0-based and wound counter-clockwise seen from outside. The OBJ importer maps OBJ
    (X, Y, Z) to Blender (X, -Z, Y), so a Blender point (x, y, z) is written `v x z -y`
    (a rotation: winding is kept). `s 1`: smooth shading, normals from the importer."""
    lines, base = [], 0
    for i, (verts, faces) in enumerate(parts):
        lines += [f"o part{i}", "s 1"]                 # `o` resets the smoothing group
        lines += [f"v {x!r} {z!r} {-y!r}" for x, y, z in verts]
        lines += ["f " + " ".join(str(base + j + 1) for j in f) for f in faces]
        base += len(verts)
    return "\n".join(lines) + "\n"


def box(x0, x1, y0, y1, z0, z1):
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 4, 7, 3),
             (1, 2, 6, 5)]
    return verts, faces


def cylinder(cx, n, r=1.0, h=2.0):
    """Closed cylinder along Z at (cx, 0), all triangles (4n): each side quad split in two,
    caps as fans around a centre vertex. Triangles only, so Blender's tessellation (which
    may split a square or a regular n-gon either way) cannot differ between copies."""
    ring = [(cx + r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n))
            for k in range(n)]
    verts = [(x, y, 0.0) for x, y in ring] + [(x, y, h) for x, y in ring]
    verts += [(cx, 0.0, 0.0), (cx, 0.0, h)]
    bottom, top = 2 * n, 2 * n + 1
    faces = []
    for k in range(n):
        j = (k + 1) % n
        faces += [(k, j, n + j), (k, n + j, n + k), (bottom, j, k), (top, n + k, n + j)]
    return verts, faces


def relief_box():
    """A unit cube whose +Y face carries a raised 0.4 x 0.4 'drawer' 0.1 proud of it
    (the back-copy defect): ring of 4 quads around the drawer, 4 drawer walls, front."""
    outer = [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)]           # +Y face corners
    inner = [(0.3, 1, 0.3), (0.7, 1, 0.3), (0.7, 1, 0.7), (0.3, 1, 0.7)]
    proud = [(x, 1.1, z) for x, _, z in inner]
    low = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]              # -Y face corners
    verts = low + outer + inner + proud                              # 0-3, 4-7, 8-11, 12-15
    faces = [(0, 3, 2, 1),                                           # -Y face
             (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]  # z0, x1, z1, x0 sides
    # +Y ring, wound to face +Y (seen from +Y: x to the left, z up)
    faces += [(4, 8, 9, 5), (5, 9, 10, 6), (6, 10, 11, 7), (7, 11, 8, 4)]
    faces += [(8, 12, 13, 9), (9, 13, 14, 10), (10, 14, 15, 11), (11, 15, 12, 8)]
    faces += [(12, 15, 14, 13)]
    return verts, faces


def glb_doc(path):
    doc, _ = glbstat.parse_glb(Path(path).read_bytes())
    return doc


def glb_vertex_count(path):
    doc = glb_doc(path)
    return sum(doc["accessors"][p["attributes"]["POSITION"]]["count"]
               for m in doc["meshes"] for p in m["primitives"])


def asym_threshold():
    return json.loads(THRESHOLDS.read_text())["qa"]["asymmetry_pct_max"]


def mirror_run():
    """tool_chest_g3 through [normalize, mirror_half x +] twice in one work dir."""
    def go():
        src = fixture("tool_chest_g3")
        skip_if_missing(src)
        d = scratch() / "mirror"
        d.mkdir(exist_ok=True)
        recipe = write_recipe(d, src, [("normalize", {"name": "tool_chest"}),
                                       ("mirror_half", {"axis": "x", "keep": "+"})],
                              asset="tool_chest")
        work = d / "work"
        return apply(recipe, work), apply(recipe, work), work
    return cached("mirror", go)


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class Recipes(unittest.TestCase):
    def test_mirror_half_fixes_asymmetry(self):
        r, _, _ = mirror_run()
        raw = qa(fixture("tool_chest_g3"), "--symmetric", "x")
        fixed = qa(r["glb"], "--symmetric", "x")
        limit = asym_threshold()
        self.assertGreater(raw["metrics"]["asymmetry"]["mean_dist_pct"], limit)
        self.assertLess(fixed["metrics"]["asymmetry"]["mean_dist_pct"], limit, fixed["metrics"])
        self.assertEqual([s["op"] for s in r["steps"]], ["normalize", "mirror_half"])
        mh = r["steps"][1]["result"]
        self.assertGreater(mh["tris_mirrored"], 0)
        # the mirrored half keeps the source's (mirrored) normals, not analytic ones
        self.assertGreaterEqual(r["normals"]["kept"], 0.95 * r["tris"], r["normals"])
        self.assertEqual(mh["seam_open_edges"], 0, mh)          # the halves are welded

    def test_recipe_reproducible(self):
        a, b, work = mirror_run()
        self.assertEqual((a["version"], b["version"]), ("v01", "v02"))
        self.assertEqual(a["tris"], b["tris"])
        self.assertEqual(a["bbox"], b["bbox"])
        self.assertEqual(glbstat.stat(a["glb"])["tris"], glbstat.stat(b["glb"])["tris"])
        for v in ("v01", "v02"):
            self.assertTrue((work / f"{v}.blend").is_file())
            self.assertTrue((work / f"{v}.glb").is_file())
        self.assertEqual(a["blend"], str(work / "v01.blend"))

    def test_export_roundtrip(self):
        a, _, work = mirror_run()
        out = scratch() / "export" / "tool_chest.glb"
        os.environ["BLENDER"] = BLENDER
        e = bl.run("export.py", [a["blend"], "--out-model", str(out), "--engine", "godot"])
        self.assertEqual(e["out_model"], str(out))
        self.assertEqual(glbstat.stat(out)["tris"], a["tris"])
        self.assertEqual(e["tris"], a["tris"])
        doc = glb_doc(out)
        self.assertEqual({i.get("mimeType") for i in doc["images"]}, {"image/jpeg"})
        roots = doc["scenes"][doc.get("scene", 0)]["nodes"]
        self.assertEqual([doc["nodes"][i]["name"] for i in roots], ["tool_chest"])
        # B12: one command re-exports the same model
        sh = Path(e["export_sh"])
        self.assertEqual(sh, work / "export.sh")
        self.assertTrue(sh.stat().st_mode & stat.S_IXUSR)
        out.unlink()
        env = dict(os.environ, BLENDER=BLENDER)
        p = subprocess.run([str(sh)], capture_output=True, text=True, env=env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["out_model"], str(out))
        self.assertEqual(glbstat.stat(out)["tris"], a["tris"])

    def test_normals_kept_through_recipe(self):
        src = fixture("jerry_can_g3")
        skip_if_missing(src)
        d = scratch() / "normals"
        d.mkdir(exist_ok=True)
        recipe = write_recipe(d, src, [
            ("normalize", {"yaw": -90, "target_height": 0.5, "name": "jerry_can"}),
            ("delete_region", {"box": [0.4, 0.4, 0.85, 0.6, 0.6, 1.0]}),
            ("fill_holes", {"max_edges": 4096})], asset="jerry_can")
        r = apply(recipe, d / "work")
        norm, deleted, filled = (s["result"] for s in r["steps"])
        self.assertGreater(deleted["tris_removed"], 0)
        self.assertGreater(filled["tris_added"], 0)
        # only the local edit is rebuilt: the move (yaw + scale) keeps every normal
        self.assertLessEqual(r["normals"]["rebuilt"], filled["tris_added"], r)
        offset = ",".join(repr(x) for x in norm["offset"])
        c = bl.run(str(HELPERS / "compare_normals.py"),
                   [str(src), r["glb"], "--yaw", norm["yaw"], "--scale", norm["scale_applied"],
                    f"--offset={offset}"])
        untouched = r["tris"] - filled["tris_added"]
        self.assertGreaterEqual(c["matched"], 0.98 * untouched, c)
        self.assertLess(c["max_angle_deg"], 0.5, c)


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class Synthetic(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def model(self, parts, name="m.obj") -> Path:
        path = self.d / name
        path.write_text(obj_text(parts))
        return path

    def run_recipe(self, src, steps, asset="thing"):
        return apply(write_recipe(self.d, src, steps, asset=asset), self.d / "work")

    def assert_usage_error(self, src, steps, text):
        with self.assertRaises(bl.BlenderError) as cm:
            self.run_recipe(src, steps)
        self.assertEqual(cm.exception.code, 2, cm.exception.stderr_tail)
        self.assertIn(text, cm.exception.stderr_tail)
        self.assertFalse((self.d / "work" / "v01.blend").exists())

    def test_remove_ground_slab(self):
        # a cube standing on a thin plate that sticks out around it
        src = self.model([box(0, 1, 0, 1, 0.02, 1.02), box(-0.3, 1.3, -0.3, 1.3, 0.0, 0.02)])
        r = self.run_recipe(src, [("weld_boundary", {}),
                                  ("remove_ground_slab", {"max_height_pct": 3})])
        slab = r["steps"][1]["result"]
        self.assertEqual(slab["tris_removed"], 12)
        self.assertEqual(r["tris"], 12)                        # the cube is untouched
        lo, hi = r["bbox"]["min"], r["bbox"]["max"]
        self.assertAlmostEqual(lo[0], 0.0, places=5)
        self.assertAlmostEqual(hi[0], 1.0, places=5)
        self.assertAlmostEqual(lo[2], 0.0, places=5)           # re-grounded onto the old floor
        self.assertAlmostEqual(hi[2] - lo[2], 1.0, places=5)

    def test_remove_ground_slab_keeps_plain_box(self):
        src = self.model([box(0, 1, 0, 1, 0, 1)])
        r = self.run_recipe(src, [("weld_boundary", {}), ("remove_ground_slab", {})])
        self.assertEqual(r["steps"][1]["result"]["tris_removed"], 0)
        self.assertEqual(r["tris"], 12)

    def test_remove_loose_needs_weld(self):
        src = self.model([box(0, 1, 0, 1, 0, 1)])
        self.assert_usage_error(src, [("remove_loose", {"min_tris_pct": 1})], "weld")

    def test_remove_loose_after_weld(self):
        src = self.model([cylinder(0, 32), box(3, 3.1, 0, 0.1, 0, 0.1)])
        r = self.run_recipe(src, [("weld_boundary", {}), ("remove_loose", {"min_tris_pct": 20})])
        self.assertEqual(r["steps"][1]["result"]["tris_removed"], 12)
        self.assertEqual(r["tris"], 4 * 32)

    def test_clone_part(self):
        # four wheels; the first (16 sides) is the clean one, the others differ
        src = self.model([cylinder(0, 16), cylinder(3, 9), cylinder(6, 11), cylinder(9, 13)])
        step = 3 / 11                                          # bbox x: -1 .. 10
        r = self.run_recipe(src, [
            ("weld_boundary", {}),
            ("clone_part", {"src_box": [0, 0, 0, 0.2, 1, 1],
                            "dst_offsets": [[step, 0, 0], [2 * step, 0, 0], [3 * step, 0, 0]]}),
            ("separate_parts", {"by": "loose"})], asset="cart")
        parts = r["steps"][2]["result"]["parts"]
        self.assertEqual(len(parts), 4)
        self.assertEqual({p["tris"] for p in parts}, {4 * 16})
        self.assertEqual(sorted(p["name"] for p in parts),
                         ["cart_part_01", "cart_part_02", "cart_part_03", "cart_part_04"])
        xs = sorted(p["pivot"][0] for p in parts)
        for got, want in zip(xs, (0.0, 3.0, 6.0, 9.0)):
            self.assertAlmostEqual(got, want, places=4)
        for p in parts:
            self.assertAlmostEqual(p["pivot"][2], 0.0, places=5)  # bottom centre
        # clones carry the source's normals: nothing is rebuilt
        self.assertEqual(r["normals"]["rebuilt"], 0, r["normals"])
        doc = glb_doc(r["glb"])
        root = doc["nodes"][doc["scenes"][0]["nodes"][0]]
        self.assertEqual(root["name"], "cart")
        kids = [doc["nodes"][i] for i in root["children"]]
        self.assertEqual(len(kids), 4)
        xs = sorted(k.get("translation", [0, 0, 0])[0] for k in kids)  # per-part pivot
        for got, want in zip(xs, (0.0, 3.0, 6.0, 9.0)):
            self.assertAlmostEqual(got, want, places=4)

    def test_separate_parts_after_normalize_keeps_clean_names(self):
        # normalize already named the two meshes crate_part_01/02 under a root `crate`;
        # separate_parts must reuse those names without Blender's .001 suffixes
        src = self.model([box(0, 1, 0, 1, 0, 1), box(2, 4, 0, 1, 0, 1)])
        r = self.run_recipe(src, [("normalize", {"name": "crate"}),
                                  ("separate_parts", {"by": "loose"})], asset="crate")
        parts = r["steps"][1]["result"]["parts"]
        self.assertEqual([p["name"] for p in parts], ["crate_part_01", "crate_part_02"])
        # equal triangle counts: ordered by centre (normalize moved the bbox centre to 0)
        self.assertEqual([round(p["pivot"][0], 4) for p in parts], [-1.5, 1.0])
        doc = glb_doc(r["glb"])
        root = doc["nodes"][doc["scenes"][0]["nodes"][0]]
        self.assertEqual(root["name"], "crate")
        self.assertEqual(sorted(doc["nodes"][i]["name"] for i in root["children"]),
                         ["crate_part_01", "crate_part_02"])
        self.assertEqual(len(doc["scenes"][0]["nodes"]), 1)

    def test_flatten_region_presses_relief(self):
        src = self.model([relief_box()])
        r = self.run_recipe(src, [("flatten_region", {"box": [0, 0.85, 0, 1, 1, 1],
                                                      "axis": "+y"})])
        res = r["steps"][0]["result"]
        self.assertEqual(res["verts_pressed"], 4)
        self.assertEqual(res["faces_removed"], 4)              # the collapsed drawer walls
        self.assertAlmostEqual(r["bbox"]["max"][1], 1.0, places=5)
        self.assertEqual(r["tris"], 2 + 8 + 8 + 2)

    def test_hard_edges_split_a_smooth_cube(self):
        src = self.model([box(0, 1, 0, 1, 0, 1)])
        smooth = self.run_recipe(src, [("weld_boundary", {})])
        self.assertEqual(glb_vertex_count(smooth["glb"]), 8)
        hard = self.run_recipe(src, [("weld_boundary", {}), ("hard_edges", {"angle": 30})])
        self.assertEqual(hard["steps"][1]["result"]["sharp_edges"], 12)
        self.assertEqual(glb_vertex_count(hard["glb"]), 24)    # every corner split

    def test_missing_source_exits_3(self):
        with self.assertRaises(bl.BlenderError) as cm:
            self.run_recipe(self.d / "nope.glb", [("weld_boundary", {})])
        self.assertEqual(cm.exception.code, 3)

    def test_unknown_op_and_param_are_usage_errors(self):
        src = self.model([box(0, 1, 0, 1, 0, 1)])
        self.assert_usage_error(src, [("melt", {})], "melt")
        self.assert_usage_error(src, [("delete_region", {"box": [0, 0, 0, 1, 1, 1],
                                                         "radius_m": 2})], "radius_m")
        self.assert_usage_error(src, [("delete_region", {"box": [0, 0, 0, 2, 1, 1]})], "box")

    def test_separate_parts_must_be_last_geometry_step(self):
        src = self.model([box(0, 1, 0, 1, 0, 1), box(2, 3, 0, 1, 0, 1)])
        self.assert_usage_error(src, [("weld_boundary", {}), ("separate_parts", {"by": "loose"}),
                                      ("delete_region", {"box": [0, 0, 0, 0.5, 1, 1]})],
                                "separate_parts")


@unittest.skipUnless(os.path.exists(BLENDER), "blender not available")
class Recolour(unittest.TestCase):
    def test_hsv_shift_raises_saturation_keeps_jpeg(self):
        src = fixture("jerry_can_g3")
        skip_if_missing(src)
        d = tmpdir()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        r = apply(write_recipe(d, src, [("recolour", {"hsv_shift": [0, 1.3, 1]})]), d / "work")
        res = r["steps"][0]["result"]
        self.assertEqual(len(res["images"]), 1)
        img = res["images"][0]
        self.assertGreater(img["saturation_after"], img["saturation_before"] * 1.15)
        self.assertEqual({i.get("mimeType") for i in glb_doc(r["glb"])["images"]},
                         {"image/jpeg"})

    def test_ref_palette_restores_saturation(self):
        src = fixture("jerry_can_g3")
        ref = fixture("R5")                                    # the jerry can sheet
        skip_if_missing(src)
        skip_if_missing(ref)
        d = tmpdir()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        r = apply(write_recipe(d, src, [("recolour", {"ref_palette": str(ref)})]), d / "work")
        res = r["steps"][0]["result"]
        self.assertGreater(res["ref_saturation"], 0)
        img = res["images"][0]
        want = res["ref_saturation"]
        self.assertLess(abs(img["saturation_after"] - want),
                        abs(img["saturation_before"] - want) + 1e-9, res)


if __name__ == "__main__":
    unittest.main()
