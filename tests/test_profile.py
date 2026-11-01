"""Tests for scripts/profile.py and scripts/asset_state.py. Game projects are only read:
detection tests copy the few files they need into a temp dir first."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests.util import SCRIPTS, skip_if_missing, tmpdir

import common  # noqa: E402  (tests.util puts scripts/ on sys.path)
import tripo_plan  # noqa: E402

PROFILE_CLI = str(SCRIPTS / "profile.py")
ASSET_CLI = str(SCRIPTS / "asset_state.py")
GRIME = Path("/Users/muhsin/Documents/GitHub/mumudevx/grime-does-pay")
PATINA = Path("/Users/muhsin/Documents/GitHub/mumudevx/patina")
COPY_FILES = ("project.godot", "scripts/godot_bin.sh", "scripts/check_import.sh", "scripts/run_tests.sh",
              "docs/asset_log.md", ".gutconfig.json", "export_presets.cfg")
ANSWERS = {"art_style": "stylized low poly", "platforms": ["pc"],
           "game_camera": {"yaw": 45, "pitch": 30, "fov": 50}, "texel_density": 512}


def run(cli, *args, stdin=None):
    p = subprocess.run([sys.executable, cli, *map(str, args)], capture_output=True, text=True,
                       input=stdin)
    lines = p.stdout.strip().splitlines()
    return p.returncode, (json.loads(lines[-1]) if lines else None), p


def profile_cli(*args, **kw):
    return run(PROFILE_CLI, *args, **kw)


def asset_cli(*args, **kw):
    return run(ASSET_CLI, *args, **kw)


def copy_project(src: Path, art_dir: str, files=COPY_FILES) -> Path:
    """Temp project holding only the detection inputs of `src` plus an empty <art_dir>/.gdignore."""
    dst = tmpdir("tripo-profile-")
    for rel in files:
        f = src / rel
        if f.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)
    (dst / art_dir).mkdir()
    (dst / art_dir / ".gdignore").write_text("")
    return dst


def minimal_project(features='"4.4", "Mobile"', extra="") -> Path:
    dst = tmpdir("tripo-profile-")
    (dst / "project.godot").write_text(
        f'config_version=5\n[application]\nconfig/name="T"\nconfig/features=PackedStringArray({features})\n{extra}')
    return dst


class Base(unittest.TestCase):
    def project(self, p):
        self.addCleanup(shutil.rmtree, p, True)
        return p


class DetectTests(Base):
    def test_detect_grime(self):
        skip_if_missing(GRIME)
        proj = self.project(copy_project(GRIME, "art_src"))
        code, out, _ = profile_cli("detect", proj)
        self.assertEqual(code, 0, out)
        prof = out["profile"]
        self.assertEqual(prof["schema"], "profile/1")
        self.assertEqual(prof["asset_log_format"], "grime")
        self.assertEqual(prof["paths"]["art_source"], "art_src")
        self.assertEqual(prof["paths"]["asset_log"], "docs/asset_log.md")
        self.assertEqual(prof["placement_mode"], "scene_swap")
        self.assertEqual(prof["engine"]["name"], "godot")
        self.assertEqual(prof["engine"]["version"], "4.7")
        self.assertTrue(prof["engine"]["binary"].endswith("Godot"))
        self.assertEqual(prof["renderer"], "forward_plus")
        self.assertEqual(prof["platforms"], ["pc"])  # export_presets.cfg: Windows/macOS/Linux
        self.assertTrue(any("check_import.sh" in c for c in prof["check_commands"]))
        self.assertIn("bash scripts/run_tests.sh", prof["check_commands"])
        self.assertFalse(any("gut_cmdln" in c for c in prof["check_commands"]))
        for key in ("art_style", "game_camera", "texel_density"):
            self.assertIn(key, out["unknown"])
        self.assertNotIn("paths.art_source", out["unknown"])

    def test_detect_patina(self):
        skip_if_missing(PATINA)
        proj = self.project(copy_project(PATINA, "art_source"))
        # the generator scripts decide placement_mode: only their names matter, so stub them
        gen = proj / "scripts" / "dev"
        gen.mkdir(parents=True)
        for src in sorted((PATINA / "scripts" / "dev").glob("generate_*_models.gd")):
            (gen / src.name).write_text("")
        self.assertTrue(list(gen.glob("generate_*_models.gd")))
        code, out, _ = profile_cli("detect", proj)
        self.assertEqual(code, 0, out)
        prof = out["profile"]
        self.assertEqual(prof["asset_log_format"], "patina")
        self.assertEqual(prof["paths"]["art_source"], "art_source")
        self.assertEqual(prof["placement_mode"], "generator_script")
        self.assertIn("bash scripts/run_tests.sh", prof["check_commands"])
        self.assertFalse(any("gut_cmdln" in c for c in prof["check_commands"]))

    def test_gut_fallback_without_run_tests(self):
        proj = self.project(minimal_project())
        (proj / ".gutconfig.json").write_text("{}")
        code, out, _ = profile_cli("detect", proj)
        self.assertEqual(code, 0, out)
        checks = out["profile"]["check_commands"]
        self.assertEqual(len(checks), 1, checks)
        self.assertIn("gut_cmdln.gd", checks[0])
        self.assertIn("-gexit", checks[0])

    def test_detect_minimal_and_unknowns(self):
        proj = self.project(minimal_project())
        code, out, _ = profile_cli("detect", proj)
        self.assertEqual(code, 0, out)
        prof = out["profile"]
        self.assertEqual(prof["engine"]["version"], "4.4")
        self.assertEqual(prof["renderer"], "mobile")
        self.assertEqual(prof["asset_log_format"], "none")
        self.assertIsNone(prof["paths"]["art_source"])
        self.assertIsNone(prof["paths"]["asset_log"])
        self.assertEqual(prof["placement_mode"], "scene_swap")
        self.assertEqual(prof["check_commands"], [])
        for key in ("platforms", "art_style", "paths.art_source", "paths.models"):
            self.assertIn(key, out["unknown"])
        self.assertNotIn("asset_log_format", out["unknown"])
        self.assertEqual(prof["pinned"]["cli"], "0.9.0")
        self.assertFalse(prof["pbr"])

    def test_art_source_needs_gdignore(self):
        proj = self.project(minimal_project())
        (proj / "art_src").mkdir()
        code, out, _ = profile_cli("detect", proj)
        self.assertEqual(code, 0, out)
        self.assertIsNone(out["profile"]["paths"]["art_source"])
        self.assertIn("paths.art_source", out["unknown"])
        self.assertTrue(any("gdignore" in w for w in out["warnings"]))

    def test_unrecognised_asset_log_is_unknown(self):
        proj = self.project(minimal_project())
        (proj / "docs").mkdir()
        (proj / "docs" / "asset_log.md").write_text("| a | b |\n|---|---|\n")
        code, out, _ = profile_cli("detect", proj)
        self.assertEqual(out["profile"]["asset_log_format"], "none")
        self.assertIn("asset_log_format", out["unknown"])

    def test_not_a_project(self):
        d = self.project(tmpdir("tripo-profile-"))
        code, out, _ = profile_cli("detect", d)
        self.assertEqual(code, 3)
        self.assertIn("project.godot", out["error"])

    def test_budgets_follow_platforms(self):
        budgets = json.loads((SCRIPTS / "data" / "budgets.json").read_text())["classes"]
        self.assertEqual(budgets["small_prop"], {"mobile": 800, "pc": 3000})
        self.assertEqual(budgets["vehicle"], {"mobile": 15000, "pc": 30000})
        self.assertEqual(sorted(budgets), sorted(["small_prop", "large_prop", "env_piece",
                                                  "weapon_held", "npc", "hero", "vehicle"]))
        proj = self.project(minimal_project())
        _, out, _ = profile_cli("init", proj, "--answers", json.dumps({"platforms": ["pc", "mobile"]}))
        # several platforms: the tighter budget wins
        self.assertEqual(out["profile"]["budgets"]["small_prop"], 800)
        self.assertEqual(out["profile"]["budgets"]["hero"], 10000)


class InitTests(Base):
    def test_init_writes_profile(self):
        proj = self.project(minimal_project())
        code, out, _ = profile_cli("init", proj, "--answers", json.dumps(ANSWERS))
        self.assertEqual(code, 0, out)
        path = proj / ".claude" / "tripo" / "profile.json"
        self.assertTrue(path.is_file())
        prof = json.loads(path.read_text())
        self.assertEqual(prof["art_style"], "stylized low poly")
        self.assertEqual(prof["game_camera"], {"yaw": 45, "pitch": 30, "fov": 50})
        self.assertEqual(prof["budgets"]["small_prop"], 3000)
        self.assertEqual(prof["engine"]["version"], "4.4")  # detected value survives the merge
        self.assertEqual(common.load_profile(proj), prof)
        self.assertNotIn("art_style", out["unknown"])

    def test_init_no_overwrite(self):
        proj = self.project(minimal_project())
        self.assertEqual(profile_cli("init", proj, "--answers", json.dumps(ANSWERS))[0], 0)
        path = proj / ".claude" / "tripo" / "profile.json"
        before = path.read_text()
        code, out, _ = profile_cli("init", proj, "--answers", json.dumps({"art_style": "x"}))
        self.assertEqual(code, 2)
        self.assertIn("--force", out["error"])
        self.assertEqual(path.read_text(), before)
        code, out, _ = profile_cli("init", proj, "--answers", json.dumps({"art_style": "x"}), "--force")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(path.read_text())["art_style"], "x")

    def test_init_answers_from_file_and_stdin(self):
        proj = self.project(minimal_project())
        f = proj / "answers.json"
        f.write_text(json.dumps(ANSWERS))
        self.assertEqual(profile_cli("init", proj, "--answers", f)[0], 0)
        self.assertEqual(profile_cli("init", proj, "--answers", "-", "--force",
                                     stdin=json.dumps(ANSWERS))[0], 0)

    def test_init_rejects_bad_answers(self):
        proj = self.project(minimal_project())
        for bad in ({"platforms": ["toaster"]}, {"asset_log_format": "csv"},
                    {"placement_mode": "magic"}, {"pbr": "yes"}, {"budgets": {"hero": "many"}},
                    {"game_camera": {"yaw": 1}}, {"schema": "profile/2"}, {"nonsense": 1},
                    {"pinned": {"cli": 9}}):
            code, out, _ = profile_cli("init", proj, "--answers", json.dumps(bad))
            self.assertEqual(code, 2, (bad, out))
        self.assertFalse((proj / ".claude" / "tripo" / "profile.json").exists())
        code, out, _ = profile_cli("init", proj, "--answers", "{not json")
        self.assertEqual(code, 2)
        code, out, _ = profile_cli("init", proj, "--answers", "/nonexistent/answers.json")
        self.assertEqual(code, 3)

    def test_init_creates_art_source_gdignore(self):
        # T17 F4: profile.py init owns <art_source>/.gdignore so Godot never imports raw files
        proj = self.project(minimal_project())
        code, out, _ = profile_cli("init", proj, "--answers",
                                   json.dumps({"paths": {"art_source": "art_src"}}))
        self.assertEqual(code, 0, out)
        self.assertTrue((proj / "art_src" / ".gdignore").is_file())
        self.assertEqual(out["created"], ["art_src/", "art_src/.gdignore"])
        # idempotent; an existing folder without the marker gets only the marker
        (proj / "art_src" / ".gdignore").unlink()
        (proj / "art_src" / "keep.txt").write_text("x")
        code, out, _ = profile_cli("init", proj, "--force", "--answers",
                                   json.dumps({"paths": {"art_source": "art_src"}}))
        self.assertEqual((code, out["created"]), (0, ["art_src/.gdignore"]))
        self.assertEqual((proj / "art_src" / "keep.txt").read_text(), "x")
        code, out, _ = profile_cli("init", proj, "--force", "--answers",
                                   json.dumps({"paths": {"art_source": "art_src"}}))
        self.assertEqual((code, out["created"]), (0, []))
        # no art source -> nothing created
        proj2 = self.project(minimal_project())
        code, out, _ = profile_cli("init", proj2, "--answers", json.dumps(ANSWERS))
        self.assertEqual((code, out["created"]), (0, []))
        # asset_state.py new repairs a deleted marker
        (proj / "art_src" / ".gdignore").unlink()
        code, out, _ = asset_cli("new", proj, "crate", "--class", "small_prop")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["created"], ["art_src/.gdignore"])
        self.assertTrue((proj / "art_src" / ".gdignore").is_file())

    def test_game_camera_pitch_sign(self):
        # T17 F3: pitch is degrees above the horizon (render_sheet.py --game-cam convention)
        proj = self.project(minimal_project())
        for bad in ({"pitch": 95, "yaw": 0, "fov": 70}, {"pitch": 35, "yaw": 0, "fov": 0},
                    {"pitch": -90, "yaw": 0, "fov": 70}):
            code, out, _ = profile_cli("init", proj, "--answers", json.dumps({"game_camera": bad}))
            self.assertEqual(code, 2, (bad, out))
        code, out, _ = profile_cli("init", proj, "--answers",
                                   json.dumps({"game_camera": {"yaw": 0, "pitch": -35, "fov": 70}}))
        self.assertEqual(code, 0, out)
        self.assertTrue(any("pitch" in w and "above the horizon" in w for w in out["warnings"]), out)
        code, out, _ = profile_cli("init", proj, "--force", "--answers",
                                   json.dumps({"game_camera": {"yaw": 0, "pitch": 35, "fov": 70}}))
        self.assertEqual(code, 0, out)
        self.assertFalse(any("pitch" in w for w in out["warnings"]), out)

    def test_init_is_deterministic_json(self):
        proj = self.project(minimal_project())
        profile_cli("init", proj, "--answers", json.dumps(ANSWERS))
        text = (proj / ".claude" / "tripo" / "profile.json").read_text()
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(list(json.loads(text))[:2], ["schema", "engine"])


class AssetStateTests(Base):
    def setUp(self):
        self.proj = self.project(minimal_project())

    def init_profile(self):
        self.assertEqual(profile_cli("init", self.proj, "--answers", json.dumps(ANSWERS))[0], 0)

    def asset_path(self, aid="crate"):
        return self.proj / ".claude" / "tripo" / "assets" / f"{aid}.json"

    def test_missing_profile_message(self):
        code, out, p = asset_cli("new", self.proj, "crate", "--class", "small_prop")
        self.assertEqual(code, 3)
        self.assertIn("profile.py init", out["error"])
        self.assertFalse(self.asset_path().exists())

    def test_asset_roundtrip(self):
        self.init_profile()
        code, out, _ = asset_cli("new", self.proj, "crate", "--class", "small_prop",
                                 "--placeholder-scene", "res://scenes/a.tscn",
                                 "--placeholder-node", "World/Crate",
                                 "--brief", json.dumps({"style": "chunky", "parts": []}))
        self.assertEqual(code, 0, out)
        a = out["asset"]
        self.assertEqual(a["schema"], "asset/1")
        self.assertEqual(a["id"], "crate")
        self.assertEqual(a["class"], "small_prop")
        self.assertEqual(a["phase"], "brief")
        self.assertEqual(a["placeholder"], {"scene": "res://scenes/a.tscn", "node": "World/Crate"})
        self.assertEqual(a["brief"]["style"], "chunky")
        for key in ("refs", "chain", "qa", "decisions"):
            self.assertEqual(a[key], [])
        self.assertIsNone(a["recipe"])
        self.assertEqual(json.loads(self.asset_path().read_text()), a)

        code, out, _ = asset_cli("get", self.proj, "crate")
        self.assertEqual((code, out["asset"]), (0, a))

        entry = {"label": "crate-generate-v01", "kind": "generate", "model": "v3.1-20260211",
                 "params": {"face_limit": 3000}, "credits": 40}
        code, out, _ = asset_cli("update", self.proj, "crate", "--phase", "generate",
                                 "--append", "chain=" + json.dumps(entry),
                                 "--append", "refs=" + json.dumps("refs/front.png"),
                                 "--append", "decisions=" + json.dumps({"q": "single part", "a": "yes"}),
                                 "--set", "brief.style=" + json.dumps("clean"))
        self.assertEqual(code, 0, out)
        a = out["asset"]
        self.assertEqual(a["phase"], "generate")
        self.assertEqual(a["brief"], {"style": "clean", "parts": []})
        self.assertEqual(a["refs"], ["refs/front.png"])
        self.assertEqual(a["chain"], [{**entry, "task_id": None, "status": "planned"}])

        code, out, _ = asset_cli("update", self.proj, "crate", "--chain-update",
                                 "crate-generate-v01=" + json.dumps({"task_id": "t-1", "status": "done"}))
        self.assertEqual(code, 0, out)
        got = asset_cli("get", self.proj, "crate")[1]["asset"]
        self.assertEqual((got["chain"][0]["task_id"], got["chain"][0]["status"]), ("t-1", "done"))
        self.assertEqual(got["chain"][0]["credits"], 40)  # untouched keys survive

    def test_chain_is_a_valid_tripo_plan_chain(self):
        self.init_profile()
        asset_cli("new", self.proj, "crate", "--class", "small_prop")
        step = {"label": "crate-rig-check-v01", "kind": "rig-check", "model": None,
                "params": {}, "task_id": "t-2", "credits": 0, "status": "done"}
        code, out, _ = asset_cli("update", self.proj, "crate", "--append", "chain=" + json.dumps(step))
        self.assertEqual(code, 0, out)
        entry = out["asset"]["chain"][0]
        self.assertEqual(entry["kind"], "rig_check")  # tripo_plan.KINDS spelling, never rig-check
        self.assertIn(entry["kind"], tripo_plan.KINDS)
        self.assertIsInstance(entry["params"], dict)
        chain_file = self.asset_path()
        self.assertIsInstance(json.loads(chain_file.read_text())["chain"], list)

    def test_update_rejects_bad_input(self):
        self.init_profile()
        asset_cli("new", self.proj, "crate", "--class", "small_prop")
        before = self.asset_path().read_text()
        bad_updates = [
            ("--phase", "nonsense"),
            ("--set", "id=\"other\""),
            ("--set", "schema=\"asset/2\""),
            ("--set", "chain=[]"),
            ("--set", "phase"),
            ("--set", "brief.style={not json"),
            ("--append", "chain=" + json.dumps({"label": "x", "kind": "warp"})),
            ("--append", "chain=" + json.dumps({"kind": "generate"})),
            ("--append", "chain=" + json.dumps({"label": "x", "kind": "generate", "status": "weird"})),
            ("--append", "brief=1"),
            ("--chain-update", "ghost=" + json.dumps({"status": "done"})),
        ]
        for args in bad_updates:
            code, out, _ = asset_cli("update", self.proj, "crate", *args)
            self.assertIn(code, (2, 3), (args, out))
            self.assertFalse(out["ok"])
        self.assertEqual(self.asset_path().read_text(), before)  # a refused update writes nothing

    def test_user_supplied_raw_chain_entry(self):
        # T17 F2: a raw result the user hands over is recorded without a guessed task id or a ledger row
        self.init_profile()
        asset_cli("new", self.proj, "chest", "--class", "large_prop")
        entry = {"label": "chest-generate-v01", "kind": "generate", "source": "user-supplied",
                 "file": "raw/chest-generate-v01/tripo-out/chest.glb"}
        code, out, _ = asset_cli("update", self.proj, "chest", "--append", "chain=" + json.dumps(entry))
        self.assertEqual(code, 0, out)
        got = out["asset"]["chain"][0]
        self.assertEqual(got, {**entry, "task_id": None, "model": None, "credits": 0,
                               "status": "done", "params": {}})
        # still a valid tripo_plan chain (extra keys are ignored there)
        self.assertIn(got["kind"], tripo_plan.KINDS)
        # no ledger row for it
        code, out, _ = asset_cli("ledger", self.proj, "--add", json.dumps(
            {"asset": "chest", "label": "chest-generate-v01", "kind": "generate", "estimate": 0}))
        self.assertEqual(code, 2, out)
        self.assertIn("user-supplied", out["error"])
        self.assertEqual(asset_cli("ledger", self.proj)[1]["rows"], [])
        # a later task id from the user is accepted through --chain-update
        code, out, _ = asset_cli("update", self.proj, "chest", "--chain-update",
                                 "chest-generate-v01=" + json.dumps({"task_id": "t-9"}))
        self.assertEqual(code, 0, out)
        self.assertEqual(out["asset"]["chain"][0]["source"], "user-supplied")
        before = self.asset_path("chest").read_text()
        for bad in ({"label": "b1", "kind": "generate", "source": "user-supplied"},           # no file
                    {"label": "b2", "kind": "generate", "source": "user-supplied", "file": "x.glb",
                     "credits": 30},
                    {"label": "b3", "kind": "generate", "source": "user-supplied", "file": "x.glb",
                     "status": "planned"},
                    {"label": "b4", "kind": "generate", "source": "elsewhere", "file": "x.glb"}):
            code, out, _ = asset_cli("update", self.proj, "chest", "--append", "chain=" + json.dumps(bad))
            self.assertEqual(code, 2, (bad, out))
        self.assertEqual(self.asset_path("chest").read_text(), before)

    def test_duplicate_chain_label_refused(self):
        self.init_profile()
        asset_cli("new", self.proj, "crate", "--class", "small_prop")
        e = "chain=" + json.dumps({"label": "crate-generate-v01", "kind": "generate"})
        self.assertEqual(asset_cli("update", self.proj, "crate", "--append", e)[0], 0)
        code, out, _ = asset_cli("update", self.proj, "crate", "--append", e)
        self.assertEqual(code, 2)
        self.assertIn("already", out["error"])

    def test_new_validation(self):
        self.init_profile()
        self.assertEqual(asset_cli("new", self.proj, "crate", "--class", "spaceship")[0], 2)
        self.assertEqual(asset_cli("new", self.proj, "Bad Id", "--class", "hero")[0], 2)
        self.assertEqual(asset_cli("new", self.proj, "crate", "--class", "hero",
                                   "--placeholder-scene", "res://a.tscn")[0], 2)  # scene without node
        self.assertEqual(asset_cli("new", self.proj, "crate", "--class", "hero")[0], 0)
        code, out, _ = asset_cli("new", self.proj, "crate", "--class", "hero")
        self.assertEqual(code, 2)
        self.assertIn("exists", out["error"])
        self.assertEqual(asset_cli("get", self.proj, "ghost")[0], 3)
        self.assertEqual(asset_cli("get", self.proj, "../profile")[0], 2)

    def test_old_schema_flagged(self):
        self.init_profile()
        path = self.asset_path("old_crate")
        path.parent.mkdir(parents=True)
        old = {"schema": "asset/0", "id": "old_crate", "class": "small_prop"}
        path.write_text(json.dumps(old))
        code, out, _ = asset_cli("get", self.proj, "old_crate")
        self.assertEqual(code, 5)
        self.assertTrue(out["migrate"])
        self.assertEqual(out["found"], "asset/0")
        self.assertEqual(json.loads(path.read_text()), old)  # never auto-migrated
        code, out, _ = asset_cli("update", self.proj, "old_crate", "--phase", "qa")
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(path.read_text()), old)

    def test_newer_schema_is_not_a_migration(self):
        self.init_profile()
        path = self.asset_path("future")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema": "asset/2", "id": "future"}))
        code, out, _ = asset_cli("get", self.proj, "future")
        self.assertEqual(code, 5)
        self.assertFalse(out["migrate"])
        self.assertIn("newer", out["error"])

    def test_corrupt_asset_file(self):
        self.init_profile()
        path = self.asset_path("broken")
        path.parent.mkdir(parents=True)
        path.write_text("{oops")
        code, out, _ = asset_cli("get", self.proj, "broken")
        self.assertEqual(code, 4)
        self.assertIn("not valid JSON", out["error"])

    def test_ledger(self):
        self.init_profile()
        asset_cli("new", self.proj, "crate", "--class", "small_prop")
        row = {"asset": "crate", "label": "crate-generate-v01", "kind": "generate",
               "estimate": 40, "consumed": None, "task_id": None}
        code, out, _ = asset_cli("ledger", self.proj, "--add", json.dumps(row))
        self.assertEqual(code, 0, out)
        self.assertEqual(set(out["row"]), {"ts", "asset", "label", "kind", "estimate", "consumed", "task_id"})
        row2 = {**row, "consumed": 40, "task_id": "t-1"}
        asset_cli("ledger", self.proj, "--add", json.dumps(row2))
        asset_cli("new", self.proj, "barrel", "--class", "large_prop")
        asset_cli("ledger", self.proj, "--add", json.dumps({**row, "asset": "barrel", "estimate": 20,
                                                              "label": "barrel-generate-v01"}))
        lines = (self.proj / ".claude" / "tripo" / "ledger.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 3)  # append-only
        code, out, _ = asset_cli("ledger", self.proj)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out["rows"]), 3)
        # the latest row per (asset, label) is the truth
        self.assertEqual(out["totals"], {"estimate": 60, "consumed": 40})
        code, out, _ = asset_cli("ledger", self.proj, "--asset", "barrel")
        self.assertEqual(out["totals"], {"estimate": 20, "consumed": 0})
        self.assertEqual(len(out["rows"]), 1)

    def test_ledger_rejects_bad_rows(self):
        self.init_profile()
        asset_cli("new", self.proj, "crate", "--class", "small_prop")
        good = {"asset": "crate", "label": "crate-generate-v01", "kind": "generate", "estimate": 40}
        for bad in ({**good, "asset": "ghost"}, {**good, "estimate": "lots"},
                    {k: v for k, v in good.items() if k != "label"}, {**good, "kind": "warp"},
                    {**good, "consumed": -1}):
            code, out, _ = asset_cli("ledger", self.proj, "--add", json.dumps(bad))
            self.assertIn(code, (2, 3), (bad, out))
        self.assertFalse((self.proj / ".claude" / "tripo" / "ledger.jsonl").exists())

    def test_no_project(self):
        d = self.project(tmpdir("tripo-profile-"))
        code, out, _ = asset_cli("get", d, "crate")
        self.assertEqual(code, 3)
        self.assertIn("project.godot", out["error"])


if __name__ == "__main__":
    unittest.main()
