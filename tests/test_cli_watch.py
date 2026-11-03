"""Tests for scripts/cli_watch.py (CLI version watch + golden dry-runs).

Everything runs offline against either a stub CLI that logs its argv (proving the
watcher only ever calls `--version`, `update --check`, `make ... --dry-run` and, with
--update, `update --yes`) or, for the golden tests, the installed tripo ($TRIPO or PATH).
Real tripo calls are limited to `make --dry-run --json` (zero credits). Only the stub
ever sees an `update` install.
"""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from datetime import date

from tests.util import ROOT, SCRIPTS, tmpdir

import common  # noqa: E402  (tests.util puts scripts/ on sys.path)
import cli_watch  # noqa: E402
import tripo_plan  # noqa: E402

CLI = str(SCRIPTS / "cli_watch.py")
GOLDEN = ROOT / "tests" / "golden_dryruns.json"

# trimmed copy of the real tripo-cli changelog; 0.7.x is missing, as in the package today
CHANGELOG = """# Changelog

## 0.9.0

- Add `tripo mcp --toolset full`. It serves the hosted Tripo MCP tool set locally.
  - Image and model inputs also accept absolute local paths, which are uploaded first.
- Each MCP tool call keeps its own analytics operation, so concurrent calls cannot overwrite each other's event context.
- PBR is opt-in. 3D generation and the `texture` step send `pbr=false` when `pbr` is omitted (the API defaults it to `true`), in the CLI and in both MCP toolsets.

## 0.8.1

- Add `tripo models`: lists the model ids each capability accepts. It reads the local whitelist and makes no API call.

## 0.8.0

- Preflight every deterministic `make` chain request before uploads or generation.
- A task that succeeds but whose artifact download fails now exits 7 instead of reporting success;
  the error JSON carries `task_id`.
- Bundled skill: agents relay the P2 estimate.

## 0.6.1

- Fix a typo in the plan card.
"""

DRY_VALID = {"dry_run": True, "valid": True, "model": "v3.1-20260211",
             "steps": [{"name": "text-to-model", "payload": {
                 "prompt": "a crate", "pbr": False, "model": "v3.1-20260211"}}],
             "warnings": [], "errors": [], "generation_credits_estimate": 20}

STUB = r'''#!/usr/bin/env python3
import json, os, sys
d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(d, "calls.log"), "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
ver_file = os.path.join(d, "version")
ver = open(ver_file).read().strip()
a = sys.argv[1:]
if a == ["--version"]:
    print(ver)
elif a[:2] == ["update", "--check"]:
    if os.path.exists(os.path.join(d, "check_fails")):
        sys.stderr.write("offline\n")
        sys.exit(1)
    latest = open(os.path.join(d, "latest")).read().strip()
    print(json.dumps({"current": ver, "latest": latest, "update_available": latest != ver,
                      "updated": False}))
elif a[:1] == ["update"]:
    open(ver_file, "w").write(open(os.path.join(d, "latest")).read())
    print(json.dumps({"current": ver, "updated": True}))
elif a[:1] == ["make"] and "--dry-run" in a:
    for x in a[1:]:
        if x.endswith((".png", ".glb")) and not os.path.isfile(x):
            sys.stderr.write("file not found: %s\n" % x)
            sys.exit(2)
    text = open(os.path.join(d, "dryrun.json")).read()
    print(text)
    try:
        sys.exit(0 if json.loads(text)["valid"] else 2)
    except ValueError:
        sys.exit(1)
else:
    sys.stderr.write("stub: unexpected argv %r\n" % a)
    sys.exit(9)
'''


def make_stub(version="0.9.0", latest="0.9.0", dry=None, changelog=CHANGELOG):
    """A fake tripo-cli package: <dir>/package.json, CHANGELOG.md, bin/tripo (logging stub)."""
    root = tmpdir("cliwatch-stub-")
    (root / "bin").mkdir()
    (root / "package.json").write_text(json.dumps({"name": "tripo-cli", "version": version}))
    (root / "CHANGELOG.md").write_text(changelog)
    (root / "version").write_text(version)
    (root / "latest").write_text(latest)
    (root / "dryrun.json").write_text(json.dumps(dry or DRY_VALID))
    exe = root / "bin" / "tripo"
    exe.write_text(STUB)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return root


def calls(root):
    log = root / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def golden_file(directory, entries):
    path = directory / "golden.json"
    path.write_text(json.dumps(entries))
    return path


GOOD_GOLDEN = [{"name": "crate_pbr_off",
                "argv": ["tripo", "make", "a crate", "--model", "tripo-v3.1"],
                "expect": {"valid": True,
                           "payload_subset": {"text-to-model": {"pbr": False}},
                           "warnings_contains": [], "errors_contains": [], "estimate": 20}}]


def run_cli(root, state, *args, golden=None):
    env = {k: v for k, v in os.environ.items() if k != "TRIPO"}
    # npm_config_prefix: `npm root -g` must not find the machine's real tripo-cli package
    env.update({"TRIPO": str(root / "bin" / "tripo"), "CLI_WATCH_OFFLINE": "1",
                "npm_config_prefix": str(root / "npm-prefix")})
    argv = [sys.executable, CLI, "check", "--state", str(state), *args]
    if golden:
        argv += ["--golden", str(golden)]
    p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=120)
    lines = p.stdout.strip().splitlines()
    return p.returncode, (json.loads(lines[-1]) if lines else None), p


class Changelog(unittest.TestCase):
    def test_changelog_slice(self):
        got = cli_watch.changelog_slice(CHANGELOG, "0.6.1", "0.9.0")
        self.assertEqual([s["version"] for s in got], ["0.8.0", "0.8.1", "0.9.0"])
        # nested bullets become items of their own; wrapped lines join their bullet
        items = {s["version"]: s["items"] for s in got}
        self.assertEqual(len(items["0.9.0"]), 4)
        self.assertTrue(any(i.startswith("Image and model inputs") for i in items["0.9.0"]))
        self.assertIn("exits 7 instead of reporting success; the error JSON carries `task_id`.",
                      items["0.8.0"][1])

    def test_slice_bounds_are_strict_below_and_inclusive_above(self):
        self.assertEqual([s["version"] for s in cli_watch.changelog_slice(CHANGELOG, "0.8.0", "0.8.1")],
                         ["0.8.1"])
        self.assertEqual(cli_watch.changelog_slice(CHANGELOG, "0.9.0", "0.9.0"), [])

    def test_headings_with_brackets_v_prefix_and_date(self):
        text = "## [v1.2.0] - 2026-01-01\n- a\n\n## v1.1.0 (2025-12-01)\n- b\n"
        got = cli_watch.changelog_slice(text, "1.0.0", "1.2.0")
        self.assertEqual([(s["version"], s["items"]) for s in got],
                         [("1.1.0", ["b"]), ("1.2.0", ["a"])])

    def test_missing_series_reported(self):
        got = cli_watch.changelog_slice(CHANGELOG, "0.6.1", "0.9.0")
        self.assertEqual(cli_watch.missing_series(got, "0.6.1", "0.9.0"), ["0.7.x"])

    def test_no_gap_when_every_series_is_covered(self):
        got = cli_watch.changelog_slice(CHANGELOG, "0.8.0", "0.9.0")
        self.assertEqual(cli_watch.missing_series(got, "0.8.0", "0.9.0"), [])

    def test_missing_target_version_is_a_gap(self):
        got = cli_watch.changelog_slice(CHANGELOG, "0.9.0", "0.9.2")
        self.assertEqual(cli_watch.missing_series(got, "0.9.0", "0.9.2"), ["0.9.2"])

    def test_relevant_filter(self):
        got = cli_watch.changelog_slice(CHANGELOG, "0.6.1", "0.9.0")
        rel = cli_watch.relevant(got)
        self.assertTrue(any("PBR is opt-in" in r for r in rel), rel)
        self.assertFalse(any("analytics operation" in r for r in rel), rel)
        self.assertTrue(all(r[:6] in ("0.8.0:", "0.8.1:", "0.9.0:") for r in rel), rel)
        # parameter names from prices.json count (quad is an add-on there)
        self.assertTrue(cli_watch.is_relevant("quad meshes now bill an extra 5 credits"))
        self.assertTrue(cli_watch.is_relevant("`face_limit` is validated"))
        # a keyword inside another word does not count (rig vs origin)
        self.assertFalse(cli_watch.is_relevant("Fix the origin of the spinner"))

    def test_keywords_include_prices_json_parameter_names(self):
        names = cli_watch.keywords()
        for k in ("texture_quality", "generate_parts", "smart_low_poly", "face_limit", "pbr",
                  "dry-run", "estimate", "decimate"):
            self.assertIn(k, names)


class State(unittest.TestCase):
    def setUp(self):
        self.dir = tmpdir("cliwatch-state-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = self.dir / ".state.json"

    def test_state_update_merges_and_keeps_other_keys(self):
        self.path.write_text(json.dumps({"projects": {"/a": {"x": 1}}, "last_check": "2026-01-01"}))
        common.state_update({"last_check": "2026-10-31", "cli_version": "0.9.0"}, path=self.path)
        common.state_update({"projects": {"/b": {"y": 2}}}, path=self.path)
        self.assertEqual(json.loads(self.path.read_text()),
                         {"projects": {"/a": {"x": 1}, "/b": {"y": 2}},
                          "last_check": "2026-10-31", "cli_version": "0.9.0"})

    def test_state_update_creates_the_file(self):
        common.state_update({"cli_version": "0.9.0"}, path=self.path)
        self.assertEqual(json.loads(self.path.read_text()), {"cli_version": "0.9.0"})

    def test_corrupt_state_is_kept_aside_not_dropped(self):
        self.path.write_text("{not json")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            common.state_update({"cli_version": "0.9.0"}, path=self.path)
        self.assertIn(".state.json.corrupt", err.getvalue())
        self.assertEqual(json.loads(self.path.read_text()), {"cli_version": "0.9.0"})
        self.assertEqual((self.dir / ".state.json.corrupt").read_text(), "{not json")

    def test_daily_skip(self):
        common.state_update({"last_check": date.today().isoformat(), "cli_version": "0.9.0",
                             "golden_ok_for": "0.9.0"}, path=self.path)
        # no CLI anywhere: a skipped run must not need one
        env = {k: v for k, v in os.environ.items() if k != "TRIPO"}
        env["PATH"] = "/nonexistent"
        p = subprocess.run([sys.executable, CLI, "check", "--state", str(self.path)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        out = json.loads(lines[0])
        self.assertIs(out["skipped"], True)
        self.assertEqual(out["installed"], "0.9.0")
        self.assertEqual(out["golden_ok_for"], "0.9.0")
        self.assertEqual(out["changelog"], [])

    def test_old_date_does_not_skip(self):
        common.state_update({"last_check": "2020-01-01", "cli_version": "0.9.0"}, path=self.path)
        root = make_stub()
        self.addCleanup(shutil.rmtree, root, True)
        gold = golden_file(self.dir, GOOD_GOLDEN)
        code, out, p = run_cli(root, self.path, golden=gold)
        self.assertEqual(code, 0, p.stderr)
        self.assertIs(out["skipped"], False)


class Watch(unittest.TestCase):
    def setUp(self):
        self.dir = tmpdir("cliwatch-run-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.state = self.dir / ".state.json"
        self.gold = golden_file(self.dir, GOOD_GOLDEN)

    def stub(self, **kw):
        root = make_stub(**kw)
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_force_overrides_daily_skip(self):
        root = self.stub()
        common.state_update({"last_check": date.today().isoformat(), "cli_version": "0.9.0"},
                            path=self.state)
        code, out, p = run_cli(root, self.state, "--force", golden=self.gold)
        self.assertEqual(code, 0, p.stderr)
        self.assertIs(out["skipped"], False)
        self.assertEqual(out["installed"], "0.9.0")

    def test_report_shape_and_state_written(self):
        root = self.stub()
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertEqual(code, 0, p.stderr)
        for key in ("installed", "latest", "updated", "changelog", "relevant", "golden", "skipped"):
            self.assertIn(key, out)
        self.assertEqual((out["installed"], out["latest"], out["updated"]), ("0.9.0", "0.9.0", False))
        self.assertEqual(out["golden"], {"passed": 1, "failed": []})
        st = json.loads(self.state.read_text())
        self.assertEqual((st["last_check"], st["cli_version"], st["golden_ok_for"]),
                         (date.today().isoformat(), "0.9.0", "0.9.0"))
        # a second run the same day is skipped
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertIs(out["skipped"], True)

    def test_without_update_flag_only_checks(self):
        root = self.stub(version="0.8.0", latest="0.9.0")
        common.state_update({"cli_version": "0.8.0"}, path=self.state)
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertEqual(out["installed"], "0.8.0")
        self.assertEqual(out["latest"], "0.9.0")
        self.assertIs(out["updated"], False)
        self.assertIs(out["update_available"], True)
        self.assertFalse(any(c[0] == "update" and "--check" not in c for c in calls(root)),
                         calls(root))

    def test_update_flag_installs_and_summarises_changelog(self):
        root = self.stub(version="0.8.0", latest="0.9.0")
        common.state_update({"cli_version": "0.8.0"}, path=self.state)
        code, out, p = run_cli(root, self.state, "--update", golden=self.gold)
        self.assertEqual(code, 0, p.stderr)
        self.assertIs(out["updated"], True)
        self.assertEqual(out["installed"], "0.9.0")
        self.assertEqual([s["version"] for s in out["changelog"]], ["0.8.1", "0.9.0"])
        self.assertTrue(any("PBR is opt-in" in r for r in out["relevant"]))
        self.assertIs(out["changelog_missing"], False)
        self.assertIn(["update", "--yes", "--json"], calls(root))
        self.assertEqual(json.loads(self.state.read_text())["cli_version"], "0.9.0")

    def test_changelog_missing_when_no_source_has_the_versions(self):
        root = self.stub(changelog="# Changelog\n\n## 0.9.0\n\n- x\n")
        common.state_update({"cli_version": "0.6.1"}, path=self.state)
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertIs(out["changelog_missing"], True)
        self.assertEqual(out["changelog_gaps"], ["0.7.x", "0.8.x"])
        self.assertEqual([s["version"] for s in out["changelog"]], ["0.9.0"])

    def test_no_changelog_needed_when_version_unchanged(self):
        root = self.stub()
        common.state_update({"cli_version": "0.9.0"}, path=self.state)
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertEqual(out["changelog"], [])
        self.assertIs(out["changelog_missing"], False)

    def test_golden_failure_exits_5_and_keeps_golden_ok_for(self):
        drifted = dict(DRY_VALID, steps=[{"name": "text-to-model",
                                          "payload": {"pbr": True, "model": "v3.1-20260211"}}])
        root = self.stub(dry=drifted)
        common.state_update({"golden_ok_for": "0.8.0"}, path=self.state)
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertEqual(code, 5, p.stderr)
        self.assertEqual(out["golden"]["passed"], 0)
        self.assertEqual(out["golden"]["failed"][0]["name"], "crate_pbr_off")
        self.assertIn("pbr", " ".join(out["golden"]["failed"][0]["diff"]))
        self.assertEqual(json.loads(self.state.read_text())["golden_ok_for"], "0.8.0")

    def test_missing_cli_is_an_internal_error(self):
        env = {k: v for k, v in os.environ.items() if k != "TRIPO"}
        env["PATH"] = "/nonexistent"
        p = subprocess.run([sys.executable, CLI, "check", "--state", str(self.state)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 4)
        self.assertIs(json.loads(p.stdout)["ok"], False)

    def test_update_check_failure_is_reported_not_fatal(self):
        root = self.stub()
        (root / "check_fails").write_text("")
        code, out, p = run_cli(root, self.state, golden=self.gold)
        self.assertEqual(code, 0, p.stderr)
        self.assertIsNone(out["latest"])
        self.assertIn("update_check_error", out)


class GoldenRunner(unittest.TestCase):
    def setUp(self):
        self.root = make_stub()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.exe = str(self.root / "bin" / "tripo")

    def run_one(self, expect, dry=None, argv=None):
        (self.root / "dryrun.json").write_text(json.dumps(dry or DRY_VALID))
        entry = {"name": "t", "argv": argv or ["tripo", "make", "a crate", "--model", "tripo-v3.1"],
                 "expect": expect}
        return cli_watch.run_golden(entry, self.exe, self.root)

    def test_pass(self):
        self.assertEqual(self.run_one({"valid": True, "estimate": 20,
                                       "payload_subset": {"text-to-model": {"pbr": False}}}), [])

    def test_diffs(self):
        self.assertTrue(self.run_one({"valid": False, "estimate": 20}))
        self.assertTrue(self.run_one({"valid": True, "estimate": 40}))
        self.assertTrue(self.run_one({"valid": True, "estimate": 20,
                                      "payload_subset": {"text-to-model": {"pbr": True}}}))
        self.assertTrue(self.run_one({"valid": True, "estimate": 20,
                                      "payload_subset": {"decimate": {"face_limit": 1}}}))
        self.assertTrue(self.run_one({"valid": True, "estimate": 20,
                                      "warnings_contains": ["quad"]}))
        self.assertTrue(self.run_one({"valid": True, "estimate": 20, "warnings_count": 1}))
        self.assertTrue(self.run_one({"valid": True, "estimate": 20, "errors_count": 1}))
        bad = dict(DRY_VALID, valid=False, errors=["smart_uv needs v3.0"], steps=[],
                   generation_credits_estimate=None)
        self.assertEqual(self.run_one({"valid": False, "estimate": None,
                                       "errors_contains": ["smart_uv"]}, dry=bad), [])
        self.assertTrue(self.run_one({"valid": False, "estimate": None,
                                      "errors_contains": ["nope"]}, dry=bad))

    def test_payload_subset_is_recursive_and_lists_match_exactly(self):
        dry = dict(DRY_VALID, steps=[{"name": "rig", "payload": {
            "model": "v3.0-20260909", "inputs": [{"front": "a"}], "opts": {"a": 1, "b": 2}}}])
        ok = {"valid": True, "estimate": 20}
        self.assertEqual(self.run_one({**ok, "payload_subset": {"rig": {"opts": {"a": 1}}}}, dry=dry), [])
        self.assertEqual(self.run_one({**ok, "payload_subset": {"rig": {"inputs": [{"front": "a"}]}}},
                                      dry=dry), [])
        self.assertTrue(self.run_one({**ok, "payload_subset": {"rig": {"opts": {"a": 2}}}}, dry=dry))
        self.assertTrue(self.run_one({**ok, "payload_subset": {"rig": {"inputs": []}}}, dry=dry))
        self.assertTrue(self.run_one({**ok, "payload_subset": {"rig": {"absent": None}}}, dry=dry))

    def test_placeholders_become_existing_files(self):
        # the stub exits 2 on a .png/.glb argument that is not a file, like the real CLI
        self.assertEqual(self.run_one({"valid": True, "estimate": 20},
                                      argv=["tripo", "make", "{png}", "{png2}", "--model", "tripo-v3.1"]), [])
        self.assertEqual(self.run_one({"valid": True, "estimate": 20},
                                      argv=["tripo", "make", "{glb}", "--then", "decimate:5000"]), [])
        # M1: --dry-run sits right after `make`, so no later token can swallow it
        self.assertEqual(calls(self.root)[-1][:3], ["make", "--dry-run", "--json"])

    def test_dry_run_survives_a_dangling_value_option(self):
        # a golden ending in a value option would have eaten an appended --dry-run
        self.run_one({"valid": True, "estimate": 20},
                     argv=["tripo", "make", "{png}", "--model", "tripo-v3.1", "--name"])
        self.assertEqual(calls(self.root)[-1][:3], ["make", "--dry-run", "--json"])

    def test_double_dash_rejected(self):
        with self.assertRaises(ValueError):
            cli_watch.run_golden({"name": "dd", "argv": ["tripo", "make", "{png}", "--", "x"],
                                  "expect": {"valid": True}}, self.exe, self.root)
        self.assertEqual(calls(self.root), [])

    def test_only_make_dry_runs_are_ever_executed(self):
        for argv in (["tripo", "balance"], ["tripo", "update"], ["tripo", "generate", "x"],
                     ["tripo", "make"], ["tripo"], ["curl", "make", "x"]):
            with self.assertRaises(ValueError, msg=argv):
                cli_watch.run_golden({"name": "bad", "argv": argv, "expect": {"valid": True}},
                                     self.exe, self.root)
        self.assertEqual(calls(self.root), [])

    def test_cli_that_prints_no_json_is_a_diff(self):
        (self.root / "dryrun.json").write_text("")
        diff = cli_watch.run_golden(
            {"name": "t", "argv": ["tripo", "make", "x", "--model", "tripo-v3.1"],
             "expect": {"valid": True}}, self.exe, self.root)
        self.assertTrue(any("no JSON" in d for d in diff), diff)


class GoldenFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads(GOLDEN.read_text(encoding="utf-8"))
        cls.by_name = {e["name"]: e for e in cls.entries}

    def test_size_shape_and_unique_names(self):
        self.assertTrue(25 <= len(self.entries) <= 40, len(self.entries))
        self.assertEqual(len(self.by_name), len(self.entries))
        for e in self.entries:
            self.assertEqual(e["argv"][:2], ["tripo", "make"], e["name"])
            self.assertNotIn("--dry-run", e["argv"])
            self.assertNotIn("--", e["argv"], e["name"])
            self.assertIn("valid", e["expect"], e["name"])
            self.assertIn("estimate", e["expect"], e["name"])
            self.assertLessEqual(set(e["expect"]), {
                "valid", "payload_subset", "warnings_contains", "errors_contains", "estimate",
                "warnings_count", "errors_count"}, e["name"])

    def test_no_machine_specific_paths(self):
        text = GOLDEN.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn("Documents/GitHub", text)

    def test_mandatory_entries(self):
        g = self.by_name
        # the Task 4 delight case
        d = g["delight_generate_v31"]
        self.assertEqual(d["expect"]["estimate"], 40)
        self.assertEqual(d["expect"]["payload_subset"]["image-to-model"]["model"], "v3.1-20260211")
        # face_limit without --model: records what the CLI picks and strips now
        for name in ("auto_model_face_limit_8000_text", "auto_model_face_limit_8000_image"):
            self.assertNotIn("--model", g[name]["argv"])
            self.assertIn("face_limit=8000", g[name]["argv"])
        # generate_parts + smart_low_poly is an error
        gp = g["parts_with_smart_low_poly_error"]
        self.assertIs(gp["expect"]["valid"], False)
        self.assertTrue(gp["expect"]["errors_contains"])
        # decimate --smart-uv without --model v3.0 (0.9.0 behaviour)
        su = g["decimate_smart_uv_without_model"]
        self.assertNotIn("model=v3.0", " ".join(su["argv"]))
        self.assertTrue(su["expect"]["errors_contains"])
        # pbr omitted -> false
        self.assertIs(g["pbr_omitted_is_false"]["expect"]["payload_subset"]["text-to-model"]["pbr"], False)
        # rig with spec=unity on v3.0
        ru = g["rig_spec_unity_v3"]["expect"]["payload_subset"]["rig"]
        self.assertEqual(ru["spec"], "unity")
        self.assertTrue(ru["model"].startswith("v3.0"))
        # quad=true + convert gltf
        qg = g["quad_convert_gltf"]
        self.assertIn("quad=true", qg["argv"])
        self.assertTrue(any("gltf" in a.lower() for a in qg["argv"]))

    def test_goldens_pass_on_installed(self):
        exe = tripo_plan.tripo_bin()
        if exe is None:
            raise unittest.SkipTest("tripo CLI not found ($TRIPO or PATH)")
        result = cli_watch.run_goldens(self.entries, exe)
        self.assertEqual(result["failed"], [], json.dumps(result["failed"], indent=1))
        self.assertEqual(result["passed"], len(self.entries))


if __name__ == "__main__":
    unittest.main()
