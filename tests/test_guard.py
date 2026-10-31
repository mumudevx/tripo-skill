"""Tests for scripts/hooks/tripo_guard.py, the PreToolUse credit lock.

Most tests run the hook as Claude Code does (JSON on stdin, decision on stdout) with
TRIPO_GUARD_OFFLINE=1, so no subprocess is spawned: the balance comes from
TRIPO_GUARD_BALANCE and the make dry-run from TRIPO_GUARD_DRYRUN. The FakeCli tests
point $TRIPO at a stub that logs its argv, to prove the hook only ever calls
`make --dry-run` and `balance`. No real Tripo call is made anywhere.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.util import SCRIPTS, tmpdir

sys.path.insert(0, str(SCRIPTS / "hooks"))
import tripo_guard  # noqa: E402

HOOK = str(SCRIPTS / "hooks" / "tripo_guard.py")
B17 = "Her ücretli adım ayrı komut olmalı (B17)"


def run_hook(command, tool="Bash", offline=True, env_extra=None, cwd=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TRIPO_GUARD_")}
    if offline:
        env["TRIPO_GUARD_OFFLINE"] = "1"
    env.update(env_extra or {})
    payload = {"session_id": "t", "hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": {"command": command}, "cwd": cwd or os.getcwd()}
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True,
                       text=True, env=env, timeout=60)
    return p


def decision(command, **kw):
    """(permissionDecision, reason) or None when the hook stays silent."""
    p = run_hook(command, **kw)
    if p.returncode != 0:
        raise AssertionError(f"hook exit {p.returncode}: {p.stderr}")
    if not p.stdout.strip():
        return None
    lines = p.stdout.strip().splitlines()
    if len(lines) != 1:
        raise AssertionError(f"hook printed {len(lines)} lines: {p.stdout!r}")
    out = json.loads(lines[0])["hookSpecificOutput"]
    if out["hookEventName"] != "PreToolUse":
        raise AssertionError(out)
    return out["permissionDecision"], out["permissionDecisionReason"]


class Classification(unittest.TestCase):
    def assertSilent(self, command):
        self.assertIsNone(decision(command), command)

    def assertAsk(self, command):
        d = decision(command)
        self.assertIsNotNone(d, command)
        self.assertEqual(d[0], "ask", f"{command}: {d}")
        return d[1]

    def assertDeny(self, command):
        d = decision(command)
        self.assertIsNotNone(d, command)
        self.assertEqual(d[0], "deny", f"{command}: {d}")
        self.assertIn(B17, d[1])
        return d[1]

    def test_free_commands_silent(self):
        for cmd in [
            "tripo", "tripo -v", "tripo --version", "tripo --help", "tripo -h",
            "tripo make x.png --model tripo-v3.1 --dry-run --json",
            "tripo make --dry-run --json @chest-generate-v01 --then texture,rig",
            "tripo make x.png --model tripo-v3.1 --help",
            "tripo generate image-to-model x.png --model v3.1 -h",
            "tripo anim rig --help",
            "tripo docs", "tripo docs --topic commands/make", "tripo models --json",
            "tripo balance --json", "tripo --json balance", "tripo --profile work balance",
            "tripo usage --limit 5", "tripo whoami", "tripo doctor", "tripo history --limit 3",
            "tripo view @last", "tripo config list", "tripo config set language en",
            "tripo update --check", "tripo update", "tripo completion zsh", "tripo login",
            "tripo logout", "tripo use work", "tripo task get 0d8a7c1e --step",
            "tripo task list", "tripo task watch 0d8a7c1e --download -o out",
            "tripo files upload a.png", "tripo mcp", "tripo mcp --toolset full",
            "tripo anim check @chest-generate-v01",
            "tripo make @chest-generate-v01 --then rig-check --json",
            "tripo make @chest-generate-v01 --then check",
            "tripo generate", "tripo anim",
        ]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)

    def test_paid_make_asks(self):
        self.assertAsk("tripo make x.png --model tripo-v3.1 --name chest-generate-v01 --json")
        self.assertAsk("tripo make @chest-generate-v01 --then texture --json")
        self.assertAsk("tripo make 'a wooden chest' --model tripo-v3.1")

    def test_rtk_prefix(self):
        self.assertAsk("rtk tripo make x.png --model tripo-v3.1 --json")
        self.assertAsk("rtk proxy tripo make @a --then rig")
        self.assertSilent("rtk tripo balance --json")

    def test_env_prefix(self):
        self.assertAsk("env TRIPO_PROFILE=work tripo make x.png --model tripo-v3.1")
        self.assertAsk("TRIPO_PROFILE=work NO_COLOR=1 tripo make x.png --model tripo-v3.1")
        self.assertAsk("env -u FOO BAR=1 tripo redo @last")
        self.assertSilent("env TRIPO_PROFILE=work tripo balance")

    def test_cd_and_chain(self):
        self.assertAsk("cd a && tripo make x.png --model tripo-v3.1")
        self.assertAsk("cd a; tripo make x.png --model tripo-v3.1")
        self.assertAsk("cd a\ntripo make x.png --model tripo-v3.1")
        self.assertAsk("tripo balance --json && tripo make x.png --model tripo-v3.1")
        self.assertAsk("false || tripo make @a --then texture")

    def test_pipe_two_paid_denied(self):
        self.assertDeny("tripo make a.png --json | tripo anim rig --json")
        self.assertDeny("tripo make a.png --model tripo-v3.1 && tripo make @a --then rig")
        self.assertDeny("tripo mesh decimate @a --face-limit 3000; tripo model convert @a")
        # one paid call piped into a free tool is fine
        self.assertAsk("tripo make a.png --model tripo-v3.1 --json | jq .task_id")

    def test_then_two_paid_denied(self):
        self.assertDeny("tripo make @chest-generate-v01 --then texture,rig")
        self.assertDeny("tripo make @a --then 'decimate:model=v3.0;face_limit=4000,uv'")
        # a generation plus any paid chain step is two paid tasks
        self.assertDeny("tripo make x.png --model tripo-v3.1 --then texture")
        # a scenario preset brings its own paid chain
        self.assertDeny("tripo make x.png --for game-pc")
        # candidates are parallel paid generations
        self.assertDeny("tripo make x.png --model tripo-v3.1 -n 2")
        self.assertDeny("tripo make x.png --model tripo-v3.1 --candidates=3")

    def test_then_rig_check_plus_one_paid_asks(self):
        self.assertAsk("tripo make @chest-generate-v01 --then rig-check,rig")
        self.assertAsk("tripo make x.png --model tripo-v3.1 --then rig-check")
        self.assertAsk("tripo make x.png --for film")

    def test_redo_asks(self):
        reason = self.assertAsk("tripo redo @chest-generate-v01")
        self.assertIn("tahmin yok", reason)
        self.assertAsk("tripo redo")

    def test_npx_form(self):
        self.assertAsk("npx tripo-cli make x.png --model tripo-v3.1")
        self.assertAsk("npx -y tripo-cli@0.9.0 make @a --then rig")
        self.assertAsk("npx --yes tripo-cli redo")
        self.assertSilent("npx -y tripo-cli balance --json")

    def test_absolute_path_binary(self):
        self.assertAsk("/opt/homebrew/bin/tripo make x.png --model tripo-v3.1")
        self.assertAsk("~/bin/tripo generate image-to-model x.png --model v3.1")
        self.assertAsk("./node_modules/.bin/tripo anim retarget @a --animation preset:walk")
        self.assertSilent("/opt/homebrew/bin/tripo balance --json")

    def test_non_tripo_silent(self):
        for cmd in ['echo "tripo make x.png --model tripo-v3.1"',
                    "echo 'tripo redo'", "grep -rn 'tripo make' docs",
                    "cat tripo.log", "ls ~/.tripo", "git commit -m 'tripo make docs'",
                    "python3 scripts/tripo_plan.py step.json",
                    "TRIPO=/x/bin/tripo python3 -m unittest tests.test_plan",
                    "rtk git status"]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)

    def test_non_bash_tool_silent(self):
        self.assertIsNone(decision("tripo make x.png --model tripo-v3.1", tool="Write"))

    def test_hidden_forms_still_caught(self):
        self.assertAsk('bash -c "tripo make x.png --model tripo-v3.1"')
        self.assertAsk("sh -lc 'cd a && tripo redo'")
        self.assertAsk('echo "$(tripo make x.png --model tripo-v3.1)"')
        self.assertAsk("echo `tripo redo`")
        self.assertAsk("(cd a && tripo make @a --then uv)")
        self.assertAsk("timeout 600 tripo make @a --then uv")
        self.assertAsk("tripo make @a --then uv > out.json 2>&1")
        self.assertAsk("tripo make @a --then uv &")
        self.assertAsk("if true; then tripo make @a --then uv; fi")
        self.assertAsk("echo @a | xargs -n 1 tripo redo")

    def test_option_values_are_not_flags(self):
        # '--name -h' names the task '-h'; it is not a help request
        self.assertAsk("tripo make x.png --model tripo-v3.1 --name -h")
        self.assertAsk("tripo make x.png --model tripo-v3.1 --name --dry-run")
        # '--dry-run=…' is not the boolean flag
        self.assertAsk("tripo make x.png --model tripo-v3.1 --dry-run=true")
        # a -p value that mentions --dry-run is still a paid run
        self.assertAsk("tripo make x.png --model tripo-v3.1 -p note=--dry-run")

    def test_other_paid_commands_ask(self):
        for cmd in ["tripo generate image-to-model x.png --model v3.1",
                    "tripo generate text-to-image 'a chest'",
                    "tripo model convert @a --format FBX", "tripo model texture @a",
                    "tripo mesh decimate @a --model v3.0 --face-limit 3000",
                    "tripo mesh uv @a", "tripo anim rig @a --rig-type biped",
                    "tripo anim retarget @a --animation preset:walk preset:run",
                    "tripo batch run jobs.yaml", "tripo ai 'a knight'",
                    "tripo --json make x.png --model tripo-v3.1"]:
            with self.subTest(cmd=cmd):
                self.assertAsk(cmd)

    def test_unknown_subcommand_asks(self):
        reason = self.assertAsk("tripo topup")
        self.assertIn("topup", reason)

    def test_unparseable_command(self):
        self.assertIn("ayrıştırılamadı", self.assertAsk("tripo make 'x.png --model tripo-v3.1"))
        self.assertSilent("echo 'unbalanced")


class Reason(unittest.TestCase):
    BAL = json.dumps({"balance": 35, "frozen": 0})

    def ask(self, command, **env):
        d = decision(command, env_extra=env)
        self.assertIsNotNone(d)
        self.assertEqual(d[0], "ask", d)
        return d[1]

    def test_reason_contains_estimate_and_balance(self):
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [],
                          "generation_credits_estimate": 30})
        r = self.ask("tripo make x.png --model tripo-v3.1 --name chest-generate-v01",
                     TRIPO_GUARD_BALANCE=self.BAL, TRIPO_GUARD_DRYRUN=dry)
        self.assertIn("tahmini kredi: 30 (dry-run)", r)
        self.assertIn("bakiye: 35 kredi (donuk 0)", r)
        self.assertIn("label: chest-generate-v01", r)
        self.assertIn("adım:", r)

    def test_balance_unreadable(self):
        r = self.ask("tripo make x.png --model tripo-v3.1")
        self.assertIn("bakiye okunamadı", r)
        self.assertIn("label: yok", r)

    def test_then_step_priced_from_table(self):
        # the make dry-run has no estimate for chain steps: the price table fills it
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [],
                          "generation_credits_estimate": None})
        r = self.ask("tripo make @chest-generate-v01 --then texture:texture_quality=detailed",
                     TRIPO_GUARD_DRYRUN=dry)
        self.assertIn("tahmini kredi: 20 (fiyat tablosu)", r)
        r = self.ask("tripo make @a --then decimate:model=v3.0,face_limit=4000,quad=true")
        self.assertIn("tahmini kredi: 40 (fiyat tablosu)", r)
        r = self.ask("tripo make @a --then rig-check,rig")
        self.assertIn("tahmini kredi: 25 (fiyat tablosu)", r)

    def test_generation_table_fallback_offline(self):
        r = self.ask("tripo make x.png --model tripo-v3.1")
        self.assertIn("tahmini kredi: 30 (fiyat tablosu)", r)
        r = self.ask("tripo make x.png")  # no --model: the CLI auto-selects, price unknown
        self.assertIn("tahmin yok", r)

    def test_file_input_mentions_import(self):
        r = self.ask("tripo make clean.glb --then rig:rig_type=biped")
        self.assertIn("tahmin yok", r)
        self.assertIn("import", r)
        self.assertIn("25", r)

    def test_direct_commands_priced_from_table(self):
        self.assertIn("tahmini kredi: 25", self.ask("tripo anim rig @a"))
        self.assertIn("tahmini kredi: 20",
                      self.ask("tripo anim retarget @a --animation preset:walk preset:run"))
        self.assertIn("tahmini kredi: 35",
                      self.ask("tripo mesh decimate @a --model v3.0 --face-limit 3000"))
        self.assertIn("tahmini kredi: 10", self.ask("tripo model convert @a --quad"))
        self.assertIn("tahmin yok", self.ask("tripo generate text-to-image 'a chest'"))

    def test_dry_run_error_reported(self):
        dry = json.dumps({"dry_run": True, "valid": False, "errors": ["unknown model zz"],
                          "generation_credits_estimate": None})
        r = self.ask("tripo make x.png --model zz", TRIPO_GUARD_DRYRUN=dry)
        self.assertIn("unknown model zz", r)

    def test_deny_names_the_steps(self):
        d = decision("tripo make @a --then texture,rig")
        self.assertEqual(d[0], "deny")
        self.assertIn("texture", d[1])
        self.assertIn("rig", d[1])


class ThenParser(unittest.TestCase):
    def test_parse(self):
        steps = tripo_guard.parse_then("texture,rig:model=v3.0-20260909,rig_type=others,"
                                       "convert:fbx,retarget:preset:walk,check")
        self.assertEqual([s["name"] for s in steps],
                         ["texture", "rig", "convert", "retarget", "rig-check"])
        self.assertEqual(steps[1]["args"], {"model": "v3.0-20260909", "rig_type": "others"})
        self.assertEqual(steps[2]["args"], {"format": "fbx"})
        self.assertEqual(steps[3]["args"], {"animation": "preset:walk"})

    def test_semicolon_args_and_coercion(self):
        (s,) = tripo_guard.parse_then("decimate:model=v3.0;face_limit=4000;quad=true")
        self.assertEqual(s["args"], {"model": "v3.0", "face_limit": 4000, "quad": True})

    def test_unknown_step_kept(self):
        steps = tripo_guard.parse_then("refine,texture")
        self.assertEqual([s["name"] for s in steps], ["refine", "texture"])
        self.assertFalse(steps[0]["known"])


class FakeCli(unittest.TestCase):
    """$TRIPO points at a stub that records every call; the hook runs online."""

    def setUp(self):
        self.dir = tmpdir("tripo-guard-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.log = self.dir / "calls.jsonl"
        self.bin = self.dir / "tripo"
        self.bin.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "a = sys.argv[1:]\n"
            "with open(os.environ['FAKE_LOG'], 'a') as f:\n"
            "    f.write(json.dumps({'argv': a, 'cwd': os.getcwd()}) + '\\n')\n"
            "if 'balance' in a:\n"
            "    print(json.dumps({'balance': 12.5, 'frozen': 2}))\n"
            "elif 'make' in a and a[a.index('make') + 1] == '--dry-run':\n"
            "    print(json.dumps({'dry_run': True, 'valid': True, 'errors': [],\n"
            "                      'generation_credits_estimate': 40}))\n"
            "else:\n"
            "    print('PAID CALL', file=sys.stderr); sys.exit(99)\n")
        self.bin.chmod(0o755)
        self.work = self.dir / "work"
        (self.work / "sub").mkdir(parents=True)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def hook(self, command):
        env = {"TRIPO": str(self.bin), "FAKE_LOG": str(self.log)}
        p = run_hook(command, offline=False, env_extra=env, cwd=str(self.work))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None

    def test_only_dry_run_and_balance_are_called(self):
        out = self.hook("cd sub && tripo --profile work make x.png --model tripo-v3.1 "
                        "--name chest-generate-v01 -- --then")
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertIn("tahmini kredi: 40 (dry-run)", out["permissionDecisionReason"])
        self.assertIn("bakiye: 12.5 kredi (donuk 2)", out["permissionDecisionReason"])
        calls = self.calls()
        self.assertEqual(len(calls), 2, calls)
        make = next(c for c in calls if "make" in c["argv"])
        # --dry-run sits right after `make`, so no later token can swallow it
        self.assertEqual(make["argv"][:5], ["--profile", "work", "make", "--dry-run", "--json"])
        self.assertEqual(Path(make["cwd"]).resolve(), (self.work / "sub").resolve())
        bal = next(c for c in calls if "balance" in c["argv"])
        self.assertEqual(bal["argv"], ["--profile", "work", "balance", "--json"])

    def test_deny_and_free_make_no_calls(self):
        self.assertEqual(self.hook("tripo make @a --then texture,rig")["permissionDecision"],
                         "deny")
        self.assertIsNone(self.hook("tripo balance --json"))
        self.assertEqual(self.calls(), [])

    def test_command_binary_is_never_executed(self):
        # an absolute path in the command is classified but the trusted $TRIPO runs
        other = self.dir / "elsewhere" / "tripo"
        other.parent.mkdir()
        other.write_text("#!/bin/sh\necho ran > \"$0.ran\"\n")
        other.chmod(0o755)
        out = self.hook(f"{other} make x.png --model tripo-v3.1")
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertFalse(Path(str(other) + ".ran").exists())
        self.assertEqual(len(self.calls()), 2)

    def test_balance_timeout(self):
        slow = self.dir / "slow"
        slow.write_text("#!/bin/sh\nexec sleep 5\n")
        slow.chmod(0o755)
        with mock.patch.dict(os.environ, {"TRIPO": str(slow)}), \
                mock.patch.object(tripo_guard, "BALANCE_TIMEOUT", 0.3), \
                mock.patch.dict(os.environ, {"TRIPO_GUARD_OFFLINE": ""}):
            self.assertEqual(tripo_guard.balance_text([]), "bakiye okunamadı")


if __name__ == "__main__":
    unittest.main()
