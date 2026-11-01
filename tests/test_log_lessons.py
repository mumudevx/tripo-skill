"""Task 12: log_asset.py (provenance + project asset_log row) and lessons.py."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests.util import SCRIPTS, skip_if_missing, tmpdir

GAMES = Path("/Users/muhsin/Documents/GitHub/mumudevx")
GRIME_LOG = GAMES / "grime-does-pay" / "docs" / "asset_log.md"
PATINA_LOG = GAMES / "patina" / "docs" / "asset_log.md"
LOG = SCRIPTS / "log_asset.py"
LESSONS = SCRIPTS / "lessons.py"


def run(script, *args):
    proc = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True,
                          text=True, timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected one JSON line, got {proc.stdout!r} / {proc.stderr[-2000:]}"
    return proc.returncode, json.loads(lines[0])


def make_project(root: Path, **answers) -> Path:
    root.mkdir(parents=True)
    (root / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="Test Game"\n'
                                        'config/features=PackedStringArray("4.7")\n')
    base = {"paths": {"models": "assets/models", "art_source": "art_source"},
            "naming": {"model_pattern": "{id}.glb", "root": "assets/models"}, "check_commands": []}
    base.update(answers)
    code, out = run(SCRIPTS / "profile.py", "init", root, "--answers", json.dumps(base))
    assert code == 0, out
    return root


def table_rows(text: str, header_word: str):
    """Rows (cell lists) of every table, keyed by the nearest preceding '## ' heading."""
    out, heading, in_table = {}, None, False
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
        if line.startswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
            if not in_table:
                in_table = True
                continue  # header
            if set(line) <= set("|-: "):
                continue
            out.setdefault(heading, []).append(cells)
        else:
            in_table = False
    return out


class LogAsset(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir("log-asset-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def project(self, log_src=None, fmt="none", **answers):
        if log_src is not None:
            answers.setdefault("paths", {"models": "assets/models", "art_source": "art_source",
                                         "asset_log": "docs/asset_log.md"})
        proj = make_project(self.tmp / "game", asset_log_format=fmt, **answers)
        if log_src is not None:
            (proj / "docs").mkdir()
            shutil.copy(log_src, proj / "docs" / "asset_log.md")
        return proj

    def asset(self, proj: Path, recipe=True) -> Path:
        ref = proj / "art_source" / "small_prop" / "crate" / "refs" / "front.png"
        ref.parent.mkdir(parents=True)
        ref.write_bytes(b"\x89PNG fake reference")
        code, out = run(SCRIPTS / "asset_state.py", "new", proj, "crate", "--class", "small_prop",
                        "--brief", json.dumps({"prompt": "a wooden crate | with rope"}),
                        "--ref", "art_source/small_prop/crate/refs/front.png")
        self.assertEqual(code, 0, out)
        chain = [{"label": "crate-gen-v01", "kind": "generate", "model": "v3.1-20260211",
                  "task_id": "t-111", "credits": 20, "status": "done", "params": {"face_limit": 3000}},
                 {"label": "crate-tex-v01", "kind": "texture", "model": "v3.0-20250812",
                  "task_id": "t-222", "credits": 10, "status": "done", "params": {}}]
        args = ["update", proj, "crate"] + [a for e in chain for a in ("--append", "chain=" + json.dumps(e))]
        if recipe:
            rec = proj / "art_source" / "small_prop" / "crate" / "fixes" / "crate.recipe.json"
            rec.parent.mkdir(parents=True)
            rec.write_text(json.dumps({"steps": [{"op": "remove_ground_slab", "params": {"max_height_pct": 3}},
                                                 {"op": "normalize", "params": {"yaw": 90}}]}))
            args += ["--set", 'recipe="art_source/small_prop/crate/fixes/crate.recipe.json"']
        code, out = run(SCRIPTS / "asset_state.py", *args)
        self.assertEqual(code, 0, out)
        return Path(out["path"])

    def check_provenance(self, proj: Path, out: dict):
        prov_path = proj / "art_source" / "small_prop" / "crate" / "provenance.json"
        self.assertEqual(Path(out["provenance"]).resolve(), prov_path.resolve())
        prov = json.loads(prov_path.read_text())
        self.assertEqual(prov["cli_version"], "0.9.0")
        self.assertEqual(prov["models"], ["v3.1-20260211", "v3.0-20250812"])
        self.assertEqual([(t["task_id"], t["credits"]) for t in prov["tasks"]], [("t-111", 20), ("t-222", 10)])
        sha = hashlib.sha256(b"\x89PNG fake reference").hexdigest()
        self.assertEqual(prov["inputs"][0]["sha256"], sha)
        self.assertEqual([e["op"] for e in prov["human_edits"]], ["remove_ground_slab", "normalize"])
        self.assertTrue(prov["license"])
        self.assertIn("tripo-cli 0.9.0", prov["tools"])
        return prov

    def test_log_grime_format(self):
        skip_if_missing(GRIME_LOG)
        proj = self.project(GRIME_LOG, fmt="grime")
        asset = self.asset(proj)
        before_text = (proj / "docs" / "asset_log.md").read_text()
        before = table_rows(before_text, "id")
        code, out = run(LOG, proj, asset, "--cli-version", "0.9.0")
        self.assertEqual(code, 0, out)
        after_text = (proj / "docs" / "asset_log.md").read_text()
        after = table_rows(after_text, "id")
        self.assertEqual(len(after["Models"]), len(before["Models"]) + 1)
        for sec in before:
            if sec != "Models":
                self.assertEqual(after[sec], before[sec], sec)
        row = after["Models"][-1]
        self.assertEqual(len(row), 7)
        self.assertEqual(row[0], "crate")
        self.assertEqual(row[1], "small_prop")
        self.assertIn("v3.1-20260211", row[2])
        self.assertIn("t-111", row[4])
        self.assertIn(r"\|", row[4])  # the '|' in the prompt is escaped, the column count holds
        self.assertEqual(len(after_text.splitlines()), len(before_text.splitlines()) + 1)
        prov = self.check_provenance(proj, out)
        self.assertEqual(prov["asset_log"]["format"], "grime")

    def test_log_patina_format(self):
        skip_if_missing(PATINA_LOG)
        proj = self.project(PATINA_LOG, fmt="patina")
        asset = self.asset(proj)
        before_text = (proj / "docs" / "asset_log.md").read_text()
        before = table_rows(before_text, "asset_path")
        code, out = run(LOG, proj, asset, "--cli-version", "0.9.0")
        self.assertEqual(code, 0, out)
        after_text = (proj / "docs" / "asset_log.md").read_text()
        after = table_rows(after_text, "asset_path")
        (sec,) = before
        self.assertEqual(len(after[sec]), len(before[sec]) + 1)
        row = after[sec][-1]
        self.assertEqual(len(row), 7)
        self.assertEqual(row[0], "`assets/models/crate.glb`")
        self.assertTrue(row[5].startswith("yes"), row[5])
        self.check_provenance(proj, out)

    def test_log_none_needs_create(self):
        proj = self.project()
        asset = self.asset(proj, recipe=False)
        code, out = run(LOG, proj, asset, "--cli-version", "0.9.0")
        self.assertEqual(code, 5, out)
        self.assertTrue(out.get("create_needed"))
        self.assertFalse((proj / "docs" / "asset_log.md").exists())
        self.assertFalse((proj / "art_source" / "small_prop" / "crate" / "provenance.json").exists())
        code, out = run(LOG, proj, asset, "--cli-version", "0.9.0", "--create")
        self.assertEqual(code, 0, out)
        text = (proj / "docs" / "asset_log.md").read_text()
        self.assertIn("| asset_path | source_tool | plan/license | generation_date | prompt_ref | human_edited | notes |", text)
        rows = table_rows(text, "asset_path")
        self.assertEqual([len(r) for rs in rows.values() for r in rs], [7])
        self.assertEqual(list(rows.values())[0][0][5], "no")
        # the next asset still logs although the profile says none: the new file has the patina columns
        code, out = run(LOG, proj, asset, "--cli-version", "0.9.0")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["format"], "patina")
        self.assertTrue(out["warnings"])
        rows = table_rows((proj / "docs" / "asset_log.md").read_text(), "asset_path")
        self.assertEqual([len(r) for rs in rows.values() for r in rs], [7, 7])

    def test_log_missing_ref_named(self):
        proj = self.project(PATINA_LOG if PATINA_LOG.exists() else None, fmt="patina" if PATINA_LOG.exists() else "none")
        asset = self.asset(proj, recipe=False)
        (proj / "art_source" / "small_prop" / "crate" / "refs" / "front.png").unlink()
        code, out = run(LOG, proj, asset, "--cli-version", "0.9.0", "--create")
        self.assertEqual(code, 3, out)
        self.assertIn("front.png", out["error"])

    def test_log_cli_version_from_state(self):
        proj = self.project()
        asset = self.asset(proj, recipe=False)
        state = self.tmp / "state.json"
        state.write_text(json.dumps({"cli_version": "0.9.1"}))
        code, out = run(LOG, proj, asset, "--state", state, "--create")
        self.assertEqual(code, 0, out)
        prov = json.loads(Path(out["provenance"]).read_text())
        self.assertEqual((prov["cli_version"], prov["cli_version_source"]), ("0.9.1", "state"))

    def test_log_missing_art_source(self):
        proj = make_project(self.tmp / "game2", paths={"models": "assets/models", "art_source": None})
        code, out = run(SCRIPTS / "asset_state.py", "new", proj, "crate", "--class", "small_prop")
        self.assertEqual(code, 0, out)
        code, out = run(LOG, proj, out["path"], "--cli-version", "0.9.0", "--create")
        self.assertEqual(code, 3, out)
        self.assertIn("paths.art_source", out["error"])


class Lessons(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir("lessons-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = self.tmp / "state.json"
        self.general = self.tmp / "general.md"
        self.common = ["--state", self.state, "--general", self.general]

    def add(self, proj, title, rule, cli="0.9.0", model="v3.1-20260211", evidence="crate, t-1, 2026-11-01"):
        code, out = run(LESSONS, "add", "--project", proj, "--title", title, "--rule", rule,
                        "--evidence", evidence, "--cli", cli, "--model", model, *self.common)
        self.assertEqual(code, 0, out)
        return out

    def test_add_writes_project_file(self):
        proj = make_project(self.tmp / "game")
        out = self.add(proj, "Pass --model", "Always pass --model explicitly.")
        path = proj / ".claude" / "tripo" / "lessons.md"
        self.assertEqual(Path(out["path"]).resolve(), path.resolve())
        self.assertEqual(out["id"], 1)
        text = path.read_text()
        self.assertIn("## L1: Pass --model", text)
        self.assertIn("- status: active", text)
        self.assertIn("- confidence: 1", text)
        self.assertEqual(json.loads(self.state.read_text())["projects"], [str(proj.resolve())])
        # the same title again confirms the lesson instead of duplicating it
        out = self.add(proj, "Pass --model", "Always pass --model explicitly.")
        self.assertEqual(out["id"], 1)
        self.assertIn("- confidence: 2", path.read_text())
        self.assertFalse(self.general.exists())

    def test_promote_requires_flag(self):
        proj = make_project(self.tmp / "game")
        self.add(proj, "Pass --model", "Always pass --model explicitly.")
        code, out = run(LESSONS, "promote", "--project", proj, "--id", "1", *self.common)
        self.assertEqual(code, 2, out)
        self.assertIn("--approved", out["error"])
        self.assertFalse(self.general.exists())
        self.assertIn("- status: active", (proj / ".claude" / "tripo" / "lessons.md").read_text())
        code, out = run(LESSONS, "promote", "--project", proj, "--id", "1", "--approved", *self.common)
        self.assertEqual(code, 0, out)
        general = self.general.read_text()
        self.assertIn("## L1: Pass --model", general)
        self.assertIn("- source: game L1", general)
        self.assertIn("- status: promoted", (proj / ".claude" / "tripo" / "lessons.md").read_text())
        code, out = run(LESSONS, "promote", "--project", proj, "--id", "7", "--approved", *self.common)
        self.assertEqual(code, 3, out)

    def test_candidates_exclude_game_terms(self):
        proj = make_project(self.tmp / "game", art_style="flat toy",
                            naming={"model_pattern": "obj_{id}.glb", "root": "assets/models"})
        code, out = run(SCRIPTS / "asset_state.py", "new", proj, "garden_gnome", "--class", "small_prop")
        self.assertEqual(code, 0, out)
        self.add(proj, "Pass --model", "Always pass --model explicitly; the default drifts.")
        self.add(proj, "Gnome hat", "The garden_gnome hat needs a mirror fix.")
        self.add(proj, "Toy colours", "Toy props need one flat material.")
        self.add(proj, "Prefix", "Name every model obj_ first.")
        self.add(proj, "Game name", "Test Game crates sit on pallets.")
        code, out = run(LESSONS, "candidates", "--project", proj, *self.common)
        self.assertEqual(code, 0, out)
        self.assertEqual([c["id"] for c in out["candidates"]], [1])
        excluded = {e["id"]: e["terms"] for e in out["excluded"]}
        self.assertIn("garden_gnome", excluded[2])
        self.assertIn("toy", excluded[3])
        self.assertIn("obj", excluded[4])
        self.assertTrue({"test", "game"} & set(excluded[5]) or "test game" in excluded[5], excluded[5])

    def test_candidates_repeat_in_other_project(self):
        a = make_project(self.tmp / "game_a", art_style="flat toy")
        b = make_project(self.tmp / "game_b", art_style="realistic")
        self.add(a, "Toy rig pose", "Toy characters rig better in A-pose.")
        self.add(b, "Toy rig pose", "Toy characters rig better in A-pose.")
        code, out = run(LESSONS, "candidates", "--project", a, *self.common)
        self.assertEqual(code, 0, out)
        self.assertEqual([(c["id"], c["reason"]) for c in out["candidates"]], [(1, f"repeats in {b.resolve()}")])

    def test_stale_marking(self):
        proj = make_project(self.tmp / "game")
        self.add(proj, "Current", "Rule one.", cli="0.9.0", model="v3.1-20260211")
        self.add(proj, "Old cli", "Rule two.", cli="0.8.0", model="v3.1-20260211")
        self.add(proj, "Old model", "Rule three.", cli="0.9.0", model="v3.1-20250101")
        self.add(proj, "Other family", "Rule four.", cli="0.9.0", model="v3.0-20250812")
        code, out = run(LESSONS, "promote", "--project", proj, "--id", "2", "--approved", *self.common)
        self.assertEqual(code, 0, out)
        code, out = run(LESSONS, "stale", "--cli", "0.9.0", "--model", "v3.1-20260211", *self.common)
        self.assertEqual(code, 0, out)
        marked = sorted((Path(m["file"]).name, m["id"]) for m in out["marked"])
        self.assertEqual(marked, [("general.md", 1), ("lessons.md", 3)])
        text = (proj / ".claude" / "tripo" / "lessons.md").read_text()
        blocks = {int(m.group(1)): m.group(0) for m in re.finditer(r"## L(\d+):.*?(?=\n## L|\Z)", text, re.S)}
        self.assertIn("- status: active", blocks[1])
        self.assertIn("- status: promoted", blocks[2])  # the project copy keeps its promoted mark
        self.assertIn("- status: needs_reverify", blocks[3])
        self.assertIn("- status: active", blocks[4])
        self.assertIn("- status: needs_reverify", self.general.read_text())

    def test_missing_project_named(self):
        code, out = run(LESSONS, "candidates", "--project", self.tmp / "nowhere", *self.common)
        self.assertEqual(code, 3, out)


if __name__ == "__main__":
    unittest.main()
