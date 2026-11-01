"""Task 12: godot_place.py (aabb / plan / apply / rig_accept) on temp copies of tests/godot_min."""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import unittest
from pathlib import Path

from tests.util import ROOT, SCRIPTS, fixture, skip_if_missing, tmpdir

GODOT = os.environ.get("GODOT", "/Applications/Godot.app/Contents/MacOS/Godot")
MIN_PROJECT = ROOT / "tests" / "godot_min"
PLACE = SCRIPTS / "godot_place.py"

sys.path.insert(0, str(SCRIPTS))
import godot_place  # noqa: E402


def run(script, *args, env=None):
    proc = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True,
                          text=True, timeout=900, env={**os.environ, **(env or {})})
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected one JSON line, got {proc.stdout!r} / {proc.stderr[-2000:]}"
    return proc.returncode, json.loads(lines[0])


def box_glb(path: Path, size, bottom=True) -> Path:
    """A stdlib GLB holding one box of `size` (glTF/Godot axes), bottom face at y=0 when `bottom`."""
    sx, sy, sz = size
    y0 = 0.0 if bottom else -sy / 2
    xs, ys, zs = (-sx / 2, sx / 2), (y0, y0 + sy), (-sz / 2, sz / 2)
    verts = [(x, y, z) for x in xs for y in ys for z in zs]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    idx = [i for a, b, c, d in quads for i in (a, b, c, a, c, d)]
    pos = b"".join(struct.pack("<3f", *v) for v in verts)
    ind = b"".join(struct.pack("<H", i) for i in idx)
    ind += b"\x00" * (-len(ind) % 4)
    blob = pos + ind
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": "crate", "mesh": 0}],
           "meshes": [{"name": "crate", "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "buffers": [{"byteLength": len(blob)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)},
                           {"buffer": 0, "byteOffset": len(pos), "byteLength": len(idx) * 2}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
                          "min": [xs[0], ys[0], zs[0]], "max": [xs[1], ys[1], zs[1]]},
                         {"bufferView": 1, "componentType": 5123, "count": len(idx), "type": "SCALAR"}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    return path


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def nodes_of(tscn: str) -> dict:
    """path -> header attrs for every [node] section (a test-side parse, independent of the script)."""
    out = {}
    for m in re.finditer(r"^\[node ([^\n]*)\]$", tscn, re.M):
        attrs = dict(re.findall(r'(\w+)=("[^"]*"|\S+?)(?=\s|$)', m.group(1)))
        attrs = {k: v.strip('"') for k, v in attrs.items()}
        parent = attrs.get("parent")
        name = attrs["name"]
        path = "." if parent is None else (name if parent == "." else f"{parent}/{name}")
        body_start = m.end()
        nxt = re.search(r"^\[", tscn[body_start:], re.M)
        attrs["_body"] = tscn[body_start: body_start + nxt.start()] if nxt else tscn[body_start:]
        out[path] = attrs
    return out


@unittest.skipUnless(os.access(GODOT, os.X_OK), "Godot binary not found ($GODOT)")
class GodotPlace(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir("godot-place-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = self.tmp / "game"
        shutil.copytree(MIN_PROJECT, self.proj)
        self.env = {"GODOT": GODOT}

    def make_profile(self, **answers):
        base = {"paths": {"models": "models", "art_source": "art_source"},
                "naming": {"model_pattern": "{id}.glb", "root": "models"},
                "check_commands": [], "placement_mode": "scene_swap"}
        base.update(answers)
        code, out = run(SCRIPTS / "profile.py", "init", self.proj, "--answers", json.dumps(base))
        self.assertEqual(code, 0, out)
        return out["profile"]

    def make_asset(self, asset_id="crate", scene="res://main.tscn", node="Crate"):
        args = ["new", self.proj, asset_id, "--class", "small_prop"]
        if scene:
            args += ["--placeholder-scene", scene, "--placeholder-node", node]
        code, out = run(SCRIPTS / "asset_state.py", *args)
        self.assertEqual(code, 0, out)
        return Path(out["path"])

    def apply(self, asset, glb, *extra):
        """plan, then apply with that plan's plan_sha256 (apply requires --expect)."""
        code, plan = run(PLACE, "plan", self.proj, asset, glb, *extra, env=self.env)
        self.assertEqual(code, 0, plan)
        return run(PLACE, "apply", self.proj, asset, glb, *extra, "--expect", plan["plan_sha256"], env=self.env)

    def glb(self, size=(1, 0.5, 0.8)):
        return box_glb(self.tmp / "crate_v01.glb", size)

    # ---- aabb ----
    def test_aabb_min_project(self):
        code, out = run(PLACE, "aabb", self.proj, "res://main.tscn", "Crate", env=self.env)
        self.assertEqual(code, 0, out)
        for got, want in zip(out["size"], (1, 0.5, 0.8)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        self.assertAlmostEqual(out["yaw_deg"], 90, delta=1e-3)
        for got, want in zip(out["center"], (2, 0, -1)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        for got, want in zip(out["bottom_center"], (2, -0.25, -1)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        # Task 9 ruling CV1: normalize.py takes Godot (gx, gy, gz) as (gx, gz, gy)
        for got, want in zip(out["normalize_target_size"], (1, 0.8, 0.5)):
            self.assertAlmostEqual(got, want, delta=1e-3)

    def test_aabb_container_root(self):
        code, out = run(PLACE, "aabb", self.proj, "stool.tscn", ".", env=self.env)
        self.assertEqual(code, 0, out)
        for got, want in zip(out["size"], (0.6, 0.5, 0.6)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        for got, want in zip(out["bottom_center"], (0, 0, 0)):
            self.assertAlmostEqual(got, want, delta=1e-3)

    def test_aabb_missing_node(self):
        code, out = run(PLACE, "aabb", self.proj, "res://main.tscn", "Nope", env=self.env)
        self.assertEqual(code, 3, out)
        self.assertIn("Nope", out["error"])

    def test_aabb_missing_scene(self):
        code, out = run(PLACE, "aabb", self.proj, "res://missing.tscn", "Crate", env=self.env)
        self.assertEqual(code, 3, out)

    # ---- plan ----
    def test_plan_writes_nothing(self):
        self.make_profile()
        asset = self.make_asset()
        glb = self.glb()
        before = tree_hash(self.tmp)
        code, out = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual(tree_hash(self.tmp), before)
        self.assertEqual(out["copy_to"], "models/crate.glb")
        self.assertIn('+[node name="Model" parent="Crate"', out["scene_diff"])
        self.assertIn('+[node name="Crate_placeholder" type="MeshInstance3D" parent="Crate"', out["scene_diff"])
        ba = out["before_after"]
        for got, want in zip(ba["size"]["before"], (1, 0.5, 0.8)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        for got, want in zip(ba["size"]["after"], (1, 0.5, 0.8)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        self.assertAlmostEqual(ba["yaw"]["before"], 90, delta=1e-3)
        for got, want in zip(ba["normalize_target_size"], (1, 0.8, 0.5)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        self.assertRegex(out["plan_sha256"], r"^[0-9a-f]{64}$")

    def test_plan_size_mismatch_warns(self):
        self.make_profile()
        asset = self.make_asset()
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(size=(1, 0.8, 0.5)), env=self.env)
        self.assertEqual(code, 0, out)
        self.assertTrue(any("size" in w for w in out["warnings"]), out["warnings"])
        # T17 F8b: the hint is the form normalize.py accepts and godot.md shows (X,Y,Z, commas)
        self.assertTrue(any("normalize.py --target-size 1,0.8,0.5 first" in w for w in out["warnings"]),
                        out["warnings"])

    def test_plan_aspect_mismatch_is_not_a_normalize_hint(self):
        # T17 F8a: already fitted to the box (uniform scale), the difference is the aspect
        self.make_profile()
        asset = self.make_asset()
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(size=(0.5, 0.5, 0.32)), env=self.env)
        self.assertEqual(code, 0, out)
        size_w = [w for w in out["warnings"] if w.startswith("model size")]
        self.assertEqual(len(size_w), 1, out["warnings"])
        self.assertIn("aspect differs", size_w[0])
        self.assertIn("1.00 : 0.50 : 0.80", size_w[0])      # placeholder x:y:z
        self.assertIn("1.00 : 1.00 : 0.64", size_w[0])      # model
        self.assertNotIn("--target-size", size_w[0])

    def test_plan_collision_fit_warnings(self):
        # T17 F8c: the kept collision is named when it no longer fits the model; never changed
        self.make_profile()
        asset = self.make_asset()
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(size=(0.5, 0.5, 0.32)), env=self.env)
        self.assertEqual(code, 0, out)
        cols = out["placeholder"]["collisions"]
        self.assertEqual([c["path"] for c in cols], ["Crate/Body/Shape"])
        for got, want in zip(cols[0]["size"], (1, 0.5, 0.8)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        col_w = [w for w in out["warnings"] if w.startswith("collision")]
        self.assertEqual(len(col_w), 1, out["warnings"])
        self.assertIn("Crate/Body/Shape", col_w[0])
        self.assertIn("larger than the model by more than 25% on x, z", col_w[0])
        self.assertNotIn("Shape", out["scene_diff"])                     # not changed automatically
        # matching model: no collision warning; a bigger model: the collision is smaller
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(size=(1, 0.5, 0.8)), env=self.env)
        self.assertEqual([w for w in out["warnings"] if w.startswith("collision")], [])
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(size=(1.2, 0.6, 0.96)), env=self.env)
        col_w = [w for w in out["warnings"] if w.startswith("collision")]
        self.assertEqual(len(col_w), 1, out["warnings"])
        self.assertIn("smaller than the model on x, y, z", col_w[0])

    def test_size_warnings_unit(self):
        ph = {"size": [1, 0.5, 0.8], "normalize_target_size": [1, 0.8, 0.5], "collisions": []}
        self.assertEqual(godot_place.size_warnings(ph, [1, 0.5, 0.8]), [])
        self.assertEqual(godot_place.size_warnings(ph, [0.99, 0.5, 0.79]), [])
        w = godot_place.size_warnings(ph, [0.4, 0.49, 0.3])                 # y within 2%: fitted
        self.assertIn("aspect differs", w[0])
        w = godot_place.size_warnings(ph, [0.4, 0.4, 0.3])                  # not fitted yet
        self.assertIn("--target-size 1,0.8,0.5", w[0])

    def test_plan_missing_profile(self):
        asset = self.tmp / "crate.json"
        asset.write_text(json.dumps({"schema": "asset/1", "id": "crate", "class": "small_prop",
                                     "placeholder": {"scene": "res://main.tscn", "node": "Crate"}}))
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(), env=self.env)
        self.assertEqual(code, 3, out)
        self.assertIn("profile.py init", out["error"])

    def test_plan_missing_placeholder(self):
        self.make_profile()
        asset = self.make_asset(scene=None)
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(), env=self.env)
        self.assertEqual(code, 3, out)
        self.assertIn("placeholder", out["error"])
        self.assertIn("asset_state.py update", out["error"])

    def test_plan_old_asset_schema(self):
        self.make_profile()
        asset = self.tmp / "crate.json"
        asset.write_text(json.dumps({"schema": "asset/0", "id": "crate"}))
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(), env=self.env)
        self.assertEqual(code, 5, out)
        self.assertTrue(out.get("migrate"))

    def test_plan_missing_naming(self):
        self.make_profile(naming={"model_pattern": None, "root": "models"})
        asset = self.make_asset()
        code, out = run(PLACE, "plan", self.proj, asset, self.glb(), env=self.env)
        self.assertEqual(code, 3, out)
        self.assertIn("naming.model_pattern", out["error"])

    def test_plan_missing_glb(self):
        self.make_profile()
        asset = self.make_asset()
        code, out = run(PLACE, "plan", self.proj, asset, self.tmp / "nope.glb", env=self.env)
        self.assertEqual(code, 3, out)

    # ---- apply ----
    def test_apply_keeps_identity(self):
        self.make_profile()
        asset = self.make_asset()
        glb = self.glb()
        old_text = (self.proj / "main.tscn").read_text()
        old = nodes_of(old_text)
        code, plan = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, plan)
        code, out = run(PLACE, "apply", self.proj, asset, glb, "--expect", plan["plan_sha256"], env=self.env)
        self.assertEqual(code, 0, out)
        new_text = (self.proj / "main.tscn").read_text()
        new = nodes_of(new_text)
        # root name and every original node: same path, same unique_id, same type
        self.assertEqual(new["."]["name"], "Main")
        for path, attrs in old.items():
            self.assertIn(path, new)
            self.assertEqual(new[path]["unique_id"], attrs["unique_id"], path)
            self.assertEqual(new[path].get("type"), attrs.get("type"), path)
        self.assertIn('script = ExtResource("1_main")', new["."]["_body"])
        self.assertIn("transform = Transform3D(0, 0, 1, 0, 1, 0, -1, 0, 0, 2, 0, -1)", new["Crate"]["_body"])
        self.assertNotIn("mesh =", new["Crate"]["_body"])
        ph = new["Crate/Crate_placeholder"]
        self.assertEqual(ph["type"], "MeshInstance3D")
        self.assertIn("visible = false", ph["_body"])
        self.assertIn('mesh = SubResource("BoxMesh_crate")', ph["_body"])
        model = new["Crate/Model"]
        self.assertRegex(model["instance"], r'^ExtResource\(')
        self.assertRegex(new_text, r'\[ext_resource type="PackedScene" path="res://models/crate.glb" id="[^"]+"\]')
        ids = [a["unique_id"] for a in new.values()]
        self.assertEqual(len(ids), len(set(ids)))
        # the applied change is exactly the planned diff
        self.assertEqual(godot_place.unified_diff(old_text, new_text, "res://main.tscn"), plan["scene_diff"])
        self.assertTrue((self.proj / "models" / "crate.glb").is_file())
        # Godot itself loads the swapped scene: the visible box sits where the placeholder was
        code, aabb = run(PLACE, "aabb", self.proj, "res://main.tscn", "Crate", env=self.env)
        self.assertEqual(code, 0, aabb)
        for got, want in zip(aabb["size"], (1, 0.5, 0.8)):
            self.assertAlmostEqual(got, want, delta=1e-3)
        for got, want in zip(aabb["bottom_center"], (2, -0.25, -1)):
            self.assertAlmostEqual(got, want, delta=1e-3)

    def test_apply_container_root(self):
        self.make_profile()
        asset = self.make_asset(asset_id="stool", scene="res://stool.tscn", node=".")
        glb = box_glb(self.tmp / "stool.glb", (0.6, 0.5, 0.6))
        old = nodes_of((self.proj / "stool.tscn").read_text())
        code, out = self.apply(asset, glb)
        self.assertEqual(code, 0, out)
        new = nodes_of((self.proj / "stool.tscn").read_text())
        old_ids = {a["unique_id"] for a in old.values()}
        self.assertEqual(old_ids - {a["unique_id"] for a in new.values()}, set())
        for name in ("Seat", "Leg"):
            self.assertNotIn(name, new)
            self.assertIn("visible = false", new[f"{name}_placeholder"]["_body"])
            self.assertEqual(new[f"{name}_placeholder"]["unique_id"], old[name]["unique_id"])
        self.assertIn("socket_sit", new)
        self.assertIn("Model", new)
        self.assertIn('metadata/kind = "furniture"', new["."]["_body"])

    def test_apply_twice_is_idempotent(self):
        self.make_profile()
        asset = self.make_asset()
        glb = self.glb()
        code, out = self.apply(asset, glb)
        self.assertEqual(code, 0, out)
        text = (self.proj / "main.tscn").read_text()
        code, out = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["scene_diff"], "")
        self.assertTrue(any("already" in w for w in out["warnings"]), out["warnings"])
        code, out = self.apply(asset, glb)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.proj / "main.tscn").read_text(), text)

    def test_apply_stale_plan_refused(self):
        self.make_profile()
        asset = self.make_asset()
        before = tree_hash(self.proj)
        code, out = run(PLACE, "apply", self.proj, asset, self.glb(), "--expect", "0" * 64, env=self.env)
        self.assertEqual(code, 5, out)
        self.assertEqual(tree_hash(self.proj), before)

    def test_apply_requires_expect(self):
        # I7: a bare apply would write whatever the plan is now, unseen
        self.make_profile()
        asset = self.make_asset()
        before = tree_hash(self.proj)
        code, out = run(PLACE, "apply", self.proj, asset, self.glb(), env=self.env)
        self.assertEqual(code, 2, out)
        self.assertIn("--expect", out["error"])
        self.assertEqual(tree_hash(self.proj), before)

    def test_plan_reports_existing_copy_to(self):
        # I7: a hand-made file at copy_to is named in the plan and covered by the digest
        self.make_profile()
        asset = self.make_asset()
        glb = self.glb()
        code, clean = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, clean)
        self.assertEqual((clean["copy_to_exists"], clean["copy_to_sha256"]), (False, None))
        self.assertFalse(any("üzerine yazılacak" in w for w in clean["warnings"]))
        (self.proj / "models").mkdir()
        hand = self.proj / "models" / "crate.glb"
        hand.write_bytes(b"hand-made chair")
        code, plan = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, plan)
        self.assertTrue(plan["copy_to_exists"])
        self.assertEqual(plan["copy_to_sha256"], hashlib.sha256(b"hand-made chair").hexdigest())
        self.assertTrue(any("var olan dosyanın üzerine yazılacak" in w for w in plan["warnings"]), plan["warnings"])
        self.assertNotEqual(plan["plan_sha256"], clean["plan_sha256"])
        # the plan shown before the file appeared no longer applies
        code, out = run(PLACE, "apply", self.proj, asset, glb, "--expect", clean["plan_sha256"], env=self.env)
        self.assertEqual(code, 5, out)
        self.assertEqual(hand.read_bytes(), b"hand-made chair")
        # the file changes after the plan was shown: refused too
        hand.write_bytes(b"hand-made chair v2")
        code, out = run(PLACE, "apply", self.proj, asset, glb, "--expect", plan["plan_sha256"], env=self.env)
        self.assertEqual(code, 5, out)
        self.assertEqual(hand.read_bytes(), b"hand-made chair v2")

    def test_import_params(self):
        self.make_profile()
        asset = self.make_asset()
        glb = self.glb()
        want = {"gltf/embedded_image_handling": "1", "meshes/ensure_tangents": "true",
                "meshes/generate_lods": "true", "nodes/apply_root_scale": "true"}
        code, plan = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, plan)
        self.assertEqual({k: json.dumps(v) if not isinstance(v, str) else v
                          for k, v in plan["import_params"].items()}, want)
        # an existing .import keeps its other settings; only the four params change
        (self.proj / "models").mkdir()
        (self.proj / "models" / "crate.glb.import").write_text(
            '[remap]\n\nimporter="scene"\nimporter_version=1\n\n[params]\n\n'
            'meshes/generate_lods=false\nanimation/fps=24\n')
        code, out = self.apply(asset, glb)
        self.assertEqual(code, 0, out)
        text = (self.proj / "models" / "crate.glb.import").read_text()
        params = dict(re.findall(r"^([\w/]+)=(.*)$", text.split("[params]", 1)[1], re.M))
        for k, v in want.items():
            self.assertEqual(params.get(k), v, k)
        self.assertEqual(params.get("animation/fps"), "24")
        self.assertTrue(list((self.proj / ".godot" / "imported").glob("crate.glb-*.scn")))

    def test_import_patch_text_unit(self):
        text = godot_place.patch_import_text(None, godot_place.IMPORT_PARAMS)
        self.assertIn('importer="scene"', text)
        self.assertIn("gltf/embedded_image_handling=1", text)
        patched = godot_place.patch_import_text(text.replace("meshes/generate_lods=true", "meshes/generate_lods=false"),
                                                godot_place.IMPORT_PARAMS)
        self.assertEqual(patched, text)

    def test_check_failure_exit5(self):
        self.make_profile(check_commands=["echo check-ran; false"])
        asset = self.make_asset()
        code, out = self.apply(asset, self.glb())
        self.assertEqual(code, 5, out)
        self.assertFalse(out["ok"])
        self.assertIn("check-ran", out["tail"])
        self.assertEqual(out["step"], "check")

    def test_check_plain_false_exit5(self):
        self.make_profile(check_commands=["false"])
        asset = self.make_asset()
        code, out = self.apply(asset, self.glb())
        self.assertEqual(code, 5, out)

    def test_generator_mode_hint(self):
        gen = self.proj / "scripts" / "dev" / "generate_crate_models.gd"
        gen.parent.mkdir(parents=True)
        gen.write_text('extends SceneTree\nconst SCENE_PATH: String = "res://main.tscn"\n'
                       'func _initialize() -> void:\n\tprint("crate")  # _part("crate", ...)\n\tquit()\n')
        self.make_profile(placement_mode="generator_script")
        asset = self.make_asset()
        glb = self.glb()
        before = tree_hash(self.tmp)
        code, out = run(PLACE, "plan", self.proj, asset, glb, env=self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual(tree_hash(self.tmp), before)
        self.assertIsNone(out["scene_diff"])
        self.assertEqual(out["generator_hint"]["file"], "scripts/dev/generate_crate_models.gd")
        texts = [s["text"] for s in out["generator_hint"]["symbols"]]
        self.assertTrue(any("SCENE_PATH" in t for t in texts), texts)
        self.assertTrue(any('"crate"' in t for t in texts), texts)
        main_before = (self.proj / "main.tscn").read_text()
        code, out = self.apply(asset, glb)
        self.assertEqual(code, 0, out)
        self.assertEqual([s["step"] for s in out["steps"]], ["import", "generator"])
        self.assertEqual((self.proj / "main.tscn").read_text(), main_before)
        self.assertTrue((self.proj / "models" / "crate.glb.import").is_file())

    # ---- rig acceptance ----
    def test_rig_accept_crew(self):
        glb = fixture("crew_rigged")
        skip_if_missing(glb)
        code, out = run(PLACE, "rig_accept", self.proj, glb, env=self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["skeletons"], 1)
        self.assertTrue(out["single_root"])
        self.assertLessEqual(out["max_influences"], 4)
        self.assertEqual(out["verdict"], "pass")
        self.assertGreater(out["bones"], 0)
        self.assertIn("mapped", out["bonemap_auto"])
        self.assertIsInstance(out["bonemap_auto"]["unmapped"], list)

    def test_rig_accept_static_fails(self):
        glb = fixture("jerry_can_g3")
        skip_if_missing(glb)
        code, out = run(PLACE, "rig_accept", self.proj, glb, env=self.env)
        self.assertEqual(code, 5, out)
        self.assertEqual(out["skeletons"], 0)
        self.assertEqual(out["verdict"], "fail")


class SwapUnit(unittest.TestCase):
    """swap_scene on text only (no Godot)."""

    def test_new_unique_ids_distinct_and_unused(self):
        text = (MIN_PROJECT / "main.tscn").read_text()
        new, _ = godot_place.swap_scene(text, "res://main.tscn", "Crate", "res://m/crate.glb", (0, -0.25, 0), (1, 1, 1))
        ids = re.findall(r"unique_id=(\d+)", new)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), len(re.findall(r"unique_id=", text)) + 2)

    def test_existing_placeholder_child_refused(self):
        text = (MIN_PROJECT / "main.tscn").read_text() + (
            '\n[node name="Crate_placeholder" type="MeshInstance3D" parent="Crate" unique_id=1310009]\n')
        with self.assertRaises(godot_place.PlaceError) as cm:
            godot_place.swap_scene(text, "res://main.tscn", "Crate", "res://m/crate.glb", (0, 0, 0), (1, 1, 1))
        self.assertEqual(cm.exception.code, 5)

    def test_instanced_placeholder_refused(self):
        text = ('[gd_scene format=3]\n\n[ext_resource type="PackedScene" path="res://box.tscn" id="1_b"]\n\n'
                '[node name="R" type="Node3D"]\n\n[node name="Box" parent="." instance=ExtResource("1_b")]\n')
        with self.assertRaises(godot_place.PlaceError) as cm:
            godot_place.swap_scene(text, "res://r.tscn", "Box", "res://m/box.glb", (0, 0, 0), (1, 1, 1))
        self.assertEqual(cm.exception.code, 5)

    def test_rename_updates_children_and_connections(self):
        text = ('[gd_scene format=3]\n\n[node name="R" type="Node3D"]\n\n'
                '[node name="Seat" type="MeshInstance3D" parent="."]\nmesh = null\n\n'
                '[node name="Bolt" type="Node3D" parent="Seat"]\n\n'
                '[connection signal="visibility_changed" from="Seat" to="." method="_on"]\n')
        new, _ = godot_place.swap_scene(text, "res://r.tscn", ".", "res://m/r.glb", (0, 0, 0), (1, 1, 1))
        self.assertIn('[node name="Bolt" type="Node3D" parent="Seat_placeholder"]', new)
        self.assertIn('from="Seat_placeholder"', new)
        self.assertNotIn("unique_id", new)  # the scene does not use them, so none are invented
        self.assertTrue(new.endswith('method="_on"]\n'))


class TscnRoundTrip(unittest.TestCase):
    def test_parse_render_is_lossless(self):
        for name in ("main.tscn", "stool.tscn"):
            text = (MIN_PROJECT / name).read_text()
            self.assertEqual(godot_place.Scene.parse(text).render(), text)

    def test_multiline_value_kept(self):
        text = ('[gd_scene format=3]\n\n[node name="R" type="Node3D"]\nmetadata/x = {\n"a": [1,\n2]\n}\n'
                '[node name="M" type="MeshInstance3D" parent="."]\nmesh = null\n')
        scene = godot_place.Scene.parse(text)
        self.assertEqual(scene.render(), text)
        self.assertEqual([n.path for n in scene.nodes()], [".", "M"])


if __name__ == "__main__":
    unittest.main()
