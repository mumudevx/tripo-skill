"""Tests for scripts/tripo_plan.py. Every Tripo call here is `--dry-run --json` or
`models --json`: zero network, zero credits. The CLI comes from $TRIPO or PATH;
tests that need it skip when it is missing, and say so in one stderr line.
REQUIRE_TRIPO=1 turns that skip into a failure (see tests/README.md)."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.util import SCRIPTS, skip_if_missing, tmpdir

import tripo_plan  # noqa: E402  (tests.util puts scripts/ on sys.path)

CLI = str(SCRIPTS / "tripo_plan.py")
MAILBOX_FRONT = Path("/Users/muhsin/Documents/GitHub/mumudevx/patina/art_source/props/"
                     "mailbox_01/concept/front.png")
# a well-formed task id with no local history entry (dry-run only; never submitted)
TASK = "0d8a7c1e-1111-4222-8333-944455556666"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
GLB_MAGIC = b"glTF\x02\x00\x00\x00" + b"\x00" * 16


def need_tripo():
    if tripo_plan.tripo_bin() is None:
        raise unittest.SkipTest("tripo CLI not found ($TRIPO or PATH)")


def run_cli(*args, stdin=None):
    p = subprocess.run([sys.executable, CLI, *map(str, args)], capture_output=True,
                       text=True, input=stdin)
    lines = p.stdout.strip().splitlines()
    return p.returncode, (json.loads(lines[-1]) if lines else None), p


class Scratch(unittest.TestCase):
    """Temp dir with a dummy PNG and GLB (dry-run checks only that files exist)."""

    def setUp(self):
        self.dir = tmpdir("tripo-plan-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.png = self.dir / "front.png"
        self.png.write_bytes(PNG_MAGIC)
        self.glb = self.dir / "x.glb"
        self.glb.write_bytes(GLB_MAGIC)

    def gen(self, params=None, **extra):
        step = {"kind": "generate", "label": "mailbox-generate-v01",
                "input": {"images": [str(self.png)]}, "model": "tripo-v3.1",
                "params": params or {}}
        step.update(extra)
        return step


class NoGenerationStep(Scratch):
    """M11: a dry-run without the step's payload is an error, not a skipped B10 check."""

    def test_generate_without_generation_step_errors(self):
        dry = {"dry_run": True, "valid": True, "steps": [], "warnings": [], "errors": []}
        with mock.patch.object(tripo_plan, "dry_run", return_value=(dry, None)), \
                mock.patch.object(tripo_plan, "wire_id", return_value="v3.1-20260211"):
            r = tripo_plan.check(self.gen())
        self.assertTrue(any("dry-run planned no generation step" in e for e in r["errors"]), r["errors"])

    def test_then_step_without_its_step_errors(self):
        dry = {"dry_run": True, "valid": True, "warnings": [], "errors": [],
               "steps": [{"name": "import", "payload": {"input": "<upload:x.glb>"}}]}
        step = {"kind": "decimate", "label": "x-decimate-v01", "input": {"file": str(self.glb)},
                "model": "v3.0", "params": {"face_limit": 3000}}
        with mock.patch.object(tripo_plan, "dry_run", return_value=(dry, None)), \
                mock.patch.object(tripo_plan, "wire_id", return_value="v3.0-20250812"):
            r = tripo_plan.check(step)
        self.assertTrue(any("dry-run planned no 'decimate' step" in e for e in r["errors"]), r["errors"])

    def test_matching_payload_passes(self):
        dry = {"dry_run": True, "valid": True, "warnings": [], "errors": [],
               "steps": [{"name": "generate", "payload": {"model": "v3.1-20260211"}}]}
        with mock.patch.object(tripo_plan, "dry_run", return_value=(dry, None)), \
                mock.patch.object(tripo_plan, "wire_id", return_value="v3.1-20260211"):
            r = tripo_plan.check(self.gen())
        self.assertEqual([e for e in r["errors"] if "payload" in e or "planned no" in e], [])


class DryRunRules(Scratch):
    """B10/B17 rules checked against the real `tripo make --dry-run`. Skipped loudly without the
    CLI; REQUIRE_TRIPO=1 makes a missing CLI a failure."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.missing = tripo_plan.tripo_bin() is None
        if cls.missing and os.environ.get("REQUIRE_TRIPO") != "1":
            n = len(unittest.TestLoader().getTestCaseNames(cls))
            sys.stderr.write(f"\n{n} dry-run rule tests SKIPPED: tripo not on PATH (set TRIPO=<path>)\n")

    def setUp(self):
        if self.missing:
            if os.environ.get("REQUIRE_TRIPO") == "1":
                self.fail("REQUIRE_TRIPO=1 but the tripo CLI was not found (set TRIPO=<path> or fix PATH)")
            raise unittest.SkipTest("tripo CLI not found ($TRIPO or PATH)")
        super().setUp()

    def test_delight_generate(self):
        skip_if_missing(MAILBOX_FRONT)
        r = tripo_plan.check({
            "kind": "generate", "label": "mailbox-generate-v01",
            "input": {"images": [str(MAILBOX_FRONT)]}, "model": "tripo-v3.1",
            "params": {"texture_version": "v3.5", "delight": True,
                       "texture_quality": "detailed"}})
        self.assertEqual(r["errors"], [])
        payload = r["dry_run"]["steps"][0]["payload"]
        self.assertEqual(payload["model"], "v3.1-20260211")
        self.assertIs(payload["pbr"], False)
        self.assertEqual(r["estimate"], {"credits": 40, "source": "dry-run"})
        self.assertTrue(r["paid"])
        self.assertEqual(r["argv"][:2], ["tripo", "make"])
        self.assertNotIn("--dry-run", r["argv"])
        self.assertIn("--model", r["argv"])
        self.assertEqual(r["ref"], "@mailbox-generate-v01")

    def test_parts_forces_texture_off(self):
        r = tripo_plan.check(self.gen({"generate_parts": True}))
        self.assertEqual(r["errors"], [])
        argv = r["argv"]
        for kv in ("texture=false", "pbr=false", "generate_parts=true"):
            self.assertIn(kv, argv)
            self.assertEqual(argv[argv.index(kv) - 1], "-p")
        payload = r["dry_run"]["steps"][0]["payload"]
        self.assertIs(payload["texture"], False)
        self.assertIs(payload["pbr"], False)
        self.assertTrue(any("generate_parts" in w for w in r["warnings"]))

    def test_parts_with_slp_errors(self):
        r = tripo_plan.check(self.gen({"generate_parts": True, "smart_low_poly": True}))
        # the planner's own rule, not only the CLI's message
        self.assertTrue(any("cannot be combined with smart_low_poly" in e for e in r["errors"]),
                        r["errors"])

    def test_model_param_rejected(self):
        r = tripo_plan.check(self.gen({"model": "v3.1-20260211"}))
        self.assertTrue(any("-p model=" in e for e in r["errors"]))

    def test_multi_candidate_rejected(self):
        r = tripo_plan.check(self.gen(candidates=2))
        self.assertTrue(any("one paid task per approval" in e for e in r["errors"]))

    def test_quad_then_glb_errors(self):
        chain = [{"kind": "generate", "model": "tripo-v3.1", "params": {"quad": True},
                  "label": "ignored-extra-key"}]
        step = {"kind": "convert", "label": "mailbox-convert-v01",
                "input": {"task": TASK}, "params": {"format": "GLTF"}}
        r = tripo_plan.check(step, chain=chain)
        self.assertTrue(any("quad" in e and "GLTF" in e for e in r["errors"]), r["errors"])
        # without the quad history the same convert is clean
        self.assertEqual(tripo_plan.check(step, chain=[])["errors"], [])
        # a later tri decimate clears the quad state
        tri = chain + [{"kind": "decimate", "model": "v3.0", "params": {"quad": False}}]
        self.assertEqual(tripo_plan.check(step, chain=tri)["errors"], [])

    def test_quad_then_glb_errors_cli(self):
        asset = self.dir / "asset.json"
        asset.write_text(json.dumps({"schema": "asset/1", "chain": [
            {"kind": "generate", "model": "tripo-v3.1", "params": {"quad": True}}]}))
        step = {"kind": "convert", "label": "mailbox-convert-v01",
                "input": {"task": TASK}, "params": {"format": "gltf"}}
        code, out, _ = run_cli(json.dumps(step), "--chain", asset)
        self.assertEqual(code, 5)
        self.assertFalse(out["ok"])
        self.assertTrue(any("quad" in e for e in out["errors"]))

    def test_rig_spec_needs_biped(self):
        r = tripo_plan.check({"kind": "rig", "label": "wolf-rig-v01", "model": "v3.0",
                              "input": {"task": TASK},
                              "params": {"rig_type": "quadruped", "spec": "mixamo"}})
        self.assertTrue(any("only applies to rig_type=biped" in e for e in r["errors"]),
                        r["errors"])

    def test_rig_type_and_spec_enums(self):
        r = tripo_plan.check({"kind": "rig", "label": "crew-rig-v01", "model": "v3.0",
                              "input": {"task": TASK},
                              "params": {"rig_type": "humanoid", "spec": "maya"}})
        self.assertTrue(any("rig_type" in e for e in r["errors"]))
        self.assertTrue(any("spec" in e for e in r["errors"]))
        ok = tripo_plan.check({"kind": "rig", "label": "crew-rig-v01", "model": "v3.0",
                               "input": {"task": TASK}, "params": {"spec": "unity"}})
        self.assertEqual(ok["errors"], [])
        self.assertEqual(ok["dry_run"]["steps"][-1]["payload"]["model"], "v3.0-20260909")
        self.assertEqual(ok["estimate"], {"credits": 25, "source": "table"})

    def test_decimate_price_from_table(self):
        r = tripo_plan.check({"kind": "decimate", "label": "mailbox-decimate-v01",
                              "model": "v3.0", "input": {"task": TASK},
                              "params": {"face_limit": 8000}})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["estimate"], {"credits": 35, "source": "table"})
        self.assertEqual(r["dry_run"]["steps"][-1]["payload"]["model"], "v3.0")
        self.assertIn("--then", r["argv"])
        self.assertEqual(r["argv"][2], TASK)
        # make names the chain step's history entry <name>-<step>
        self.assertEqual(r["ref"], "@mailbox-decimate-v01-decimate")

    def test_import_price_unknown(self):
        r = tripo_plan.check({"kind": "rig", "label": "crew-rig-v01", "model": "v3.0",
                              "input": {"file": str(self.glb)}})
        self.assertEqual(r["errors"], [])
        self.assertIsNone(r["estimate"]["credits"])
        self.assertTrue(r["paid"])
        self.assertEqual(r["dry_run"]["steps"][0]["name"], "import")
        self.assertTrue(any("import" in w for w in r["warnings"]))

    def test_rig_check_free(self):
        r = tripo_plan.check({"kind": "rig_check", "label": "crew-rig_check-v01",
                              "input": {"task": TASK}})
        self.assertEqual(r["errors"], [])
        self.assertIs(r["paid"], False)
        self.assertEqual(r["estimate"], {"credits": 0, "source": "table"})
        for kind in tripo_plan.KINDS:
            if kind != "rig_check":
                self.assertTrue(tripo_plan.is_paid({"kind": kind, "input": {"task": TASK}}),
                                kind)

    def test_orientation_removed_with_warning(self):
        r = tripo_plan.check(self.gen({"auto_size": True, "orientation": "align_image",
                                       "export_orientation": "+x"}))
        self.assertEqual(r["errors"], [])
        self.assertEqual(sum("set locally instead" in w for w in r["warnings"]), 3)
        joined = " ".join(r["argv"])
        for key in ("auto_size", "orientation"):
            self.assertNotIn(key, joined)
            self.assertNotIn(key, r["dry_run"]["steps"][0]["payload"])

    def test_texture_model_alias_resolved(self):
        r = tripo_plan.check({"kind": "texture", "label": "mailbox-texture-v01",
                              "model": "v3.5", "input": {"task": TASK},
                              "params": {"texture_quality": "detailed", "delight": True}})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["dry_run"]["steps"][-1]["payload"]["model"], "v3.5-20260815")
        self.assertEqual(r["estimate"], {"credits": 20, "source": "table"})

    def test_unknown_model_errors(self):
        r = tripo_plan.check(self.gen(model="tripo-turbo"))
        self.assertTrue(any("tripo-turbo" in e for e in r["errors"]))

    def test_p1_priced_from_table(self):
        r = tripo_plan.check(self.gen(model="tripo-p1"))
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["estimate"], {"credits": 50, "source": "table"})

    def test_cli_clean_step_exit_0(self):
        code, out, p = run_cli("-", stdin=json.dumps(self.gen()))
        self.assertEqual(code, 0, p.stderr)
        self.assertTrue(out["ok"])
        self.assertEqual(len(p.stdout.strip().splitlines()), 1)
        self.assertEqual(out["estimate"], {"credits": 30, "source": "dry-run"})


class BuildAndTable(Scratch):
    """No CLI needed: argv shape, structural errors, price table."""

    def test_build_generate_argv(self):
        argv = tripo_plan.build(self.gen({"texture_quality": "detailed", "pbr": False}))
        self.assertEqual(argv[:3], ["tripo", "make", str(self.png)])
        self.assertEqual(argv[argv.index("--model") + 1], "tripo-v3.1")
        self.assertEqual(argv[argv.index("--name") + 1], "mailbox-generate-v01")
        self.assertIn("texture_quality=detailed", argv)
        self.assertIn("pbr=false", argv)
        self.assertEqual(argv[-1], "--json")

    def test_build_processing_argv(self):
        argv = tripo_plan.build({"kind": "decimate", "label": "mailbox-decimate-v01",
                                 "model": "v3.0", "input": {"task": "@mailbox-generate-v01"},
                                 "params": {"face_limit": 8000, "smart_uv": True}})
        self.assertEqual(argv[:3], ["tripo", "make", "@mailbox-generate-v01"])
        self.assertEqual(argv[argv.index("--then") + 1],
                         "decimate:model=v3.0;face_limit=8000;smart_uv=true")
        self.assertNotIn("-p", argv)
        argv = tripo_plan.build({"kind": "rig_check", "label": "crew-rig_check-v01",
                                 "input": {"task": "@crew-generate-v01"}})
        self.assertEqual(argv[argv.index("--then") + 1], "rig-check")

    def test_build_name_override(self):
        argv = tripo_plan.build(self.gen(name="custom-name"))
        self.assertEqual(argv[argv.index("--name") + 1], "custom-name")

    def test_build_direct_commands(self):
        argv = tripo_plan.build({"kind": "image_to_multiview", "label": "mailbox-image_to_multiview-v01",
                                 "input": {"images": [str(self.png)]}})
        self.assertEqual(argv[:4], ["tripo", "generate", "image-to-multiview", str(self.png)])
        argv = tripo_plan.build({"kind": "smartsegment", "label": "mailbox-smartsegment-v01",
                                 "input": {"file": str(self.glb)}})
        self.assertEqual(argv[:4], ["tripo", "mesh", "smartsegment", str(self.glb)])

    def test_structural_errors_raise(self):
        bad = [
            {**self.gen(), "label": None},
            {**self.gen(), "label": "mailbox-v01"},
            {**self.gen(), "model": None},
            {**self.gen(), "kind": "refine"},
            {**self.gen(), "input": {"task": TASK}},
            {"kind": "rig", "label": "a-rig-v01", "input": {"task": TASK}},
            {"kind": "retarget", "label": "a-retarget-v01", "input": {"task": TASK},
             "params": {"animations": ["preset:walk", "preset:run"]}},
            {"kind": "convert", "label": "a-convert-v01", "input": {"task": TASK},
             "params": {"format": "FBX;quad=true"}},
            {"kind": "convert", "label": "a-convert-v01", "input": {"task": TASK},
             "params": {"format=x": "FBX"}},
            {**self.gen(), "input": {"prompt": "--yes"}},
        ]
        for step in bad:
            with self.assertRaises(tripo_plan.PlanError, msg=step):
                tripo_plan.build(step)

    def test_missing_input_raises_not_found(self):
        step = self.gen()
        step["input"] = {"images": [str(self.dir / "nope.png")]}
        with self.assertRaises(tripo_plan.InputNotFound):
            tripo_plan.build(step)
        code, out, _ = run_cli(json.dumps(step))
        self.assertEqual(code, 3)
        self.assertFalse(out["ok"])

    def test_cli_build_needs_no_tripo(self):
        env_step = json.dumps({"kind": "rig_check", "label": "crew-rig_check-v01",
                               "input": {"task": "@crew-generate-v01"}})
        p = subprocess.run([sys.executable, CLI, env_step, "--build"], capture_output=True,
                           text=True, env={**os.environ, "TRIPO": str(self.dir / "no-tripo")})
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(out["ref"], "@crew-rig_check-v01-rig-check")
        self.assertEqual(out["argv"][-1], "--json")

    def test_cli_missing_tripo_exit_4(self):
        p = subprocess.run([sys.executable, CLI, json.dumps(self.gen())], capture_output=True,
                           text=True, env={**os.environ, "TRIPO": str(self.dir / "no-tripo")})
        self.assertEqual(p.returncode, 4)
        self.assertIn("tripo CLI not found", json.loads(p.stdout)["error"])

    def test_cli_usage_exit_2(self):
        code, out, _ = run_cli('{"kind": "generate"}')
        self.assertEqual(code, 2)
        self.assertFalse(out["ok"])

    def test_table_prices(self):
        tp = tripo_plan.table_price
        task = {"task": TASK}
        img = {"images": [str(self.png)]}
        cases = [
            ({"kind": "generate", "model": "tripo-v3.1", "input": img,
              "params": {"texture_quality": "extreme", "smart_low_poly": True}}, 60),
            ({"kind": "generate", "model": "tripo-v3.1", "input": img,
              "params": {"texture": False, "pbr": False, "generate_parts": True}}, 40),
            ({"kind": "generate", "model": "tripo-v3.1", "input": {"prompt": "a crate"},
              "params": {}}, 20),
            ({"kind": "generate", "model": "tripo-p1", "input": img,
              "params": {"texture": False}}, 40),
            ({"kind": "generate", "model": "tripo-p1", "input": img,
              "params": {"texture_quality": "detailed"}}, None),
            ({"kind": "generate", "model": "tripo-p2", "input": img, "params": {}}, 110),
            ({"kind": "texture", "model": "v3.5", "input": task, "params": {}}, 10),
            ({"kind": "texture", "model": "v3.5", "input": task,
              "params": {"texture_quality": "extreme"}}, 30),
            ({"kind": "convert", "input": task, "params": {"format": "FBX"}}, 5),
            ({"kind": "convert", "input": task,
              "params": {"format": "FBX", "texture_size": 2048}}, 10),
            ({"kind": "convert", "input": task,
              "params": {"format": "FBX", "texture_size": 4096}}, 5),
            ({"kind": "decimate", "model": "v3.0", "input": task, "params": {"quad": True}}, 40),
            ({"kind": "decimate", "model": "v1.0", "input": task, "params": {}}, 10),
            ({"kind": "decimate", "model": "v2.0", "input": task, "params": {}}, 30),
            ({"kind": "uv", "input": task}, 20),
            ({"kind": "segment", "input": task}, None),  # v2.0 default, price unpublished
            ({"kind": "segment", "model": "v1.0", "input": task}, 40),
            ({"kind": "complete", "input": task}, 50),
            ({"kind": "complete", "input": task, "params": {"completion_mode": "quick_cap"}}, 30),
            ({"kind": "smartsegment", "input": {"file": str(self.glb)}}, 55),
            ({"kind": "smartsegment", "input": {"file": str(self.png)}}, 85),
            ({"kind": "rig_check", "input": task}, 0),
            ({"kind": "rig", "model": "v3.0", "input": task}, 25),
            ({"kind": "retarget", "input": task, "params": {"animation": "preset:walk"}}, 10),
            ({"kind": "image_to_multiview", "input": img}, 10),
            ({"kind": "edit_multiview", "input": task,
              "params": {"prompts": [{"view": "front", "prompt": "a"},
                                     {"view": "back", "prompt": "b"}]}}, 10),
            ({"kind": "edit_multiview", "input": task}, None),
            ({"kind": "rig", "model": "v3.0", "input": {"file": str(self.glb)}}, None),
            ({"kind": "generate", "model": "tripo-turbo", "input": img, "params": {}}, None),
        ]
        for step, want in cases:
            self.assertEqual(tp(step), want, step)

    def test_price_table_dated(self):
        table = json.loads((SCRIPTS / "data" / "prices.json").read_text())
        self.assertEqual(table["as_of"], "2026-11-03")
        self.assertIsNone(table["import"])


    def test_retired_models_rejected(self):
        """Tripo retires H2.5 generation, texture v2.5 and segment v1.0 on 2026-12-01."""
        task = {"task": TASK}
        cases = [
            self.gen(model="tripo-v2.5"),
            self.gen(model="v2.5-20250123"),
            self.gen({"texture_version": "v2.5"}),
            {"kind": "texture", "label": "mailbox-texture-v01", "model": "v2.5", "input": task},
            {"kind": "segment", "label": "mailbox-segment-v01", "model": "v1.0", "input": task},
        ]
        for step in cases:
            _, _, errors = tripo_plan._rules(step)
            self.assertTrue(any("retired by Tripo on 2026-12-01" in e for e in errors), step)
        for step in (self.gen(), self.gen({"texture_version": "v3.5"}),
                     {"kind": "texture", "label": "mailbox-texture-v01", "model": "v3.5",
                      "input": task}):
            self.assertEqual(tripo_plan._rules(step)[2], [], step)

    def test_segment_model_pinned_to_v2(self):
        argv = tripo_plan.build({"kind": "segment", "label": "mailbox-segment-v01",
                                 "input": {"task": "@mailbox-generate-v01"}})
        self.assertEqual(argv[argv.index("--then") + 1], "segment:model=v2.0-20260430")
        argv = tripo_plan.build({"kind": "segment", "label": "mailbox-segment-v01",
                                 "model": "v2.0", "input": {"task": "@mailbox-generate-v01"}})
        self.assertEqual(argv[argv.index("--then") + 1], "segment:model=v2.0")


class DryRunArgv(unittest.TestCase):
    """M1: --dry-run goes right after `make`, never at the end, where a value option
    missing its value or a `--` could swallow it and submit a paid task."""

    def test_dry_run_flag_follows_make(self):
        from unittest import mock
        seen = []

        def fake(args, timeout):
            seen.append(args)
            return 0, json.dumps({"dry_run": True, "valid": True}), ""

        with mock.patch.object(tripo_plan, "_run_tripo", fake):
            data, err = tripo_plan.dry_run(["tripo", "make", "x.png", "--model", "tripo-v3.1",
                                            "--json", "--name"])
        self.assertIsNone(err)
        self.assertEqual(seen, [["make", "--dry-run", "x.png", "--model", "tripo-v3.1",
                                 "--json", "--name"]])

    def test_only_make_is_dry_run(self):
        with self.assertRaises(ValueError):
            tripo_plan.dry_run(["tripo", "anim", "rig", "@a"])


if __name__ == "__main__":
    unittest.main()
