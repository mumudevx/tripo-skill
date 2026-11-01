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

    def test_heredoc_text_is_not_a_command(self):
        for cmd in ["cat >> notes.md <<'EOF'\ntripo make x.png --model tripo-v3.1\ntripo was missing\nEOF\ngit add notes.md",
                    'cat > a.md <<"EOF"\ntripo redo @a\nEOF',
                    "cat > a.md <<-EOF\n\ttripo make x.png\n\tEOF",
                    "python3 - <<EOF\nprint('tripo make x.png')\nEOF",
                    "cat <<A > a.md; cat <<B > b.md\ntripo redo\nA\ntripo make x\nB",
                    # I3: the standard PR/commit pattern quotes tripo commands in markdown
                    "gh pr create --title t --body \"$(cat <<'EOF'\n## Summary\n"
                    "- `tripo make \"crate\"` now asks\n- `tripo redo` is denied (it skips "
                    "the plan)\nEOF\n)\"",
                    "git commit -m \"$(cat <<'EOF'\nfix: `tripo make x` asks (a) b)\nEOF\n)\""]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)

    def test_substitutions_follow_bash_quoting(self):
        # I3, controller ruling: bash semantics. Single quotes and quoted heredoc
        # bodies are literal; an escaped backtick is literal; a backtick pair or $(...)
        # inside double quotes is live (bash would run it), so it asks.
        for cmd in ["echo '$(tripo make x)'", "git commit -m 'fix: `tripo make x` asks'",
                    'git commit -m "fix: \\`tripo make x\\` asks"',
                    "echo 'say \"$(tripo redo)\"'",
                    "x=$(tripo balance --json); echo \"$x\""]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)
        for cmd in ['git commit -m "fix: `tripo make x.png --model tripo-v3.1` asks"',
                    'echo "a $(tripo redo @a) b"', "echo $(tripo redo @a)",
                    "cat > a.md <<EOF\nit's $(tripo make x.png --model tripo-v3.1)\nEOF"]:
            with self.subTest(cmd=cmd):
                self.assertAsk(cmd)
        # a $(...) program is a command output the lock cannot see through
        self.assertIn("görülemeyen", self.assertAsk("$(command -v tripo) make x.png"))
        # a substitution inside a loop body runs once per iteration
        self.assertDeny('for i in 1 2; do echo "$(tripo make x.png --model tripo-v3.1)"; done')
        # two live substitutions with paid calls are two paid steps
        self.assertDeny('echo "$(tripo redo @a) `tripo redo @b`"')

    def test_comments_are_dropped(self):
        # R3: an apostrophe in a comment must not open a quote that hides a call
        block = ("cd art_src/props/crate/raw/crate-generate-v01\n"
                 "# run the planner's argv as is\n"
                 "tripo make crate.png --model tripo-v3.1 --name crate-generate-v01 --json\n"
                 "# the download lands in tripo-out (that's the frozen raw)\n")
        self.assertIn("label: crate-generate-v01", self.assertAsk(block))
        for cmd in ["echo a#b; tripo make x.png", "tripo make x.png # it's paid",
                    "true;# don't\ntripo redo @a", "(# it's\ntripo redo @a)",
                    "echo \"$(# it's\ntripo redo @a)\"",
                    "echo hi |# it's\ntripo redo @a",
                    "cat > a.md <<'EOF' # it's a note\ntext\nEOF\ntripo redo @a"]:
            with self.subTest(cmd=cmd):
                self.assertAsk(cmd)
        # a comment that only mentions tripo runs nothing
        for cmd in ["# later: tripo make x", "ls  # then tripo make x.png --model tripo-v3.1",
                    "echo ${#x}", "echo $# tripo", "echo '#' tripo",
                    "cat <<'EOF' | sh\n# tripo make x.png\nEOF"]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)
        # '#' inside a word, after $, inside quotes or escaped is not a comment
        for cmd in ["echo a#b tripo redo; tripo redo @a", "echo \\# x; tripo redo @a",
                    "echo \"# x\"; tripo redo @a", "echo $#; tripo redo @a",
                    "echo ${#x}; tripo redo @a"]:
            with self.subTest(cmd=cmd):
                self.assertAsk(cmd)
        # an unquoted heredoc body is data: its '#' does not hide a live $(...)
        self.assertAsk("cat > a.md <<EOF\n# id: $(tripo redo @a)\nEOF")

    def test_heredoc_live_parts_still_caught(self):
        # a heredoc fed to a shell runs its body
        self.assertAsk("bash <<'EOF'\ntripo make x.png --model tripo-v3.1\nEOF")
        self.assertAsk("cat <<EOF | sh\ntripo redo @a\nEOF")
        # an unquoted delimiter keeps command substitution live
        self.assertAsk("cat > a.md <<EOF\nid: $(tripo make x.png --model tripo-v3.1)\nEOF")
        # commands after the heredoc are scanned
        self.assertAsk("cat > a.md <<'EOF'\ntext\nEOF\ntripo make x.png --model tripo-v3.1")
        # here-strings are not heredocs
        self.assertAsk("bash <<< 'tripo redo @a'")

    def test_non_bash_tool_silent(self):
        self.assertIsNone(decision("tripo make x.png --model tripo-v3.1", tool="Write"))

    def test_hidden_forms_still_caught(self):
        self.assertAsk('bash -c "tripo make x.png --model tripo-v3.1"')
        self.assertAsk("sh -lc 'cd a && tripo redo'")
        # shell options that take a value before -c
        self.assertAsk("bash -o pipefail -c 'tripo make x.png --model tripo-v3.1'")
        self.assertAsk("bash -euo pipefail -c 'tripo make x.png --model tripo-v3.1'")
        self.assertAsk("bash -O extglob -c 'tripo make x.png --model tripo-v3.1'")
        self.assertAsk("bash +o posix -ec 'tripo redo'")
        self.assertAsk("bash --rcfile x.rc -c 'tripo redo'")
        self.assertAsk("bash -c -e 'tripo redo'")
        self.assertAsk('echo "$(tripo make x.png --model tripo-v3.1)"')
        self.assertAsk("echo `tripo redo`")
        self.assertAsk("(cd a && tripo make @a --then uv)")
        self.assertAsk("timeout 600 tripo make @a --then uv")
        self.assertAsk("tripo make @a --then uv > out.json 2>&1")
        self.assertAsk("tripo make @a --then uv &")
        self.assertAsk("if true; then tripo make @a --then uv; fi")

    # ---- C1: forms the lock must not miss ----

    def test_unknown_runner_falls_back_to_tripo_word(self):
        for cmd in ["mise exec -- tripo make x.png --model tripo-v3.1",
                    "mise x -- tripo make x.png --model tripo-v3.1",
                    "mise exec node@24 -- tripo make x.png --model tripo-v3.1",
                    "npm exec tripo-cli -- make x.png --model tripo-v3.1",
                    "npm exec -- tripo make x.png --model tripo-v3.1",
                    "pnpm exec tripo make x.png --model tripo-v3.1",
                    "yarn tripo make x.png --model tripo-v3.1",
                    "caffeinate -i tripo make x.png --model tripo-v3.1",
                    "stdbuf -oL tripo make x.png --model tripo-v3.1",
                    "command -p tripo make x.png --model tripo-v3.1",
                    "/usr/bin/env tripo make x.png --model tripo-v3.1",
                    "node ~/.npm/node_modules/tripo-cli/bin/tripo.js make x.png",
                    "mise exec -- bash -c 'tripo make x.png --model tripo-v3.1'",
                    "T=$(command -v tripo); $T make x.png --model tripo-v3.1"]:
            with self.subTest(cmd=cmd):
                self.assertAsk(cmd)
        # the same runners with a free command stay silent
        for cmd in ["mise exec -- tripo balance --json", "npm exec tripo-cli -- --version",
                    "npm install -g tripo-cli@latest", "mise exec -- tripo make x.png --dry-run"]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)

    def test_case_folded(self):
        self.assertAsk("/x/bin/TRIPO make x.png --model tripo-v3.1")
        self.assertAsk("Tripo make x.png --model tripo-v3.1")
        self.assertAsk("npx Tripo-CLI make x.png --model tripo-v3.1")
        self.assertAsk("mise exec -- TRIPO redo @a")
        self.assertSilent("TRIPO balance --json")

    def test_variable_program_asks(self):
        for cmd in ['"$TRIPO" make x.png --model tripo-v3.1', "cd tripo-out && $T make x.png",
                    "${T:-tripo} make x.png", "cd raw && $TRIPO_BIN redo"]:
            with self.subTest(cmd=cmd):
                self.assertIn("görülemeyen çağrı", self.assertAsk(cmd))
        # a $VAR program in a command that never mentions tripo is not the lock's business
        self.assertSilent("$EDITOR notes.md")

    def test_read_only_programs_silent(self):
        for cmd in ["which tripo", "command -v tripo", "type tripo", "man tripo",
                    "ls -la ~/.local/share/mise/installs/node/24.22.2/bin/tripo",
                    "head -3 tripo", "sed -n 1p tripo", "rg tripo make", "git log -- tripo",
                    "python3 -m unittest tests.test_guard"]:
            with self.subTest(cmd=cmd):
                self.assertSilent(cmd)

    def test_function_body_asks(self):
        self.assertAsk("f(){ tripo make x.png --model tripo-v3.1; }; f")
        self.assertAsk("function g { tripo redo @a; }")
        self.assertAsk("f() {\n  tripo make x.png --model tripo-v3.1\n}\nf")

    def test_shell_script_file(self):
        d = tmpdir("tripo-guard-script-")
        self.addCleanup(shutil.rmtree, d, True)
        (d / "run.sh").write_text("#!/bin/sh\nTripo make x.png --model tripo-v3.1\n")
        (d / "plain.sh").write_text("#!/bin/sh\necho hi\n")
        for cmd in ["bash run.sh", "sh -e run.sh", "zsh ./run.sh", f"bash {d}/run.sh",
                    "source run.sh", ". ./run.sh", "mise exec -- bash run.sh"]:
            with self.subTest(cmd=cmd):
                d_ = decision(cmd, cwd=str(d))
                self.assertIsNotNone(d_, cmd)
                self.assertEqual(d_[0], "ask")
                self.assertIn("run.sh", d_[1])
        # the file is resolved against the cwd of a preceding cd
        self.assertEqual(decision(f"cd {d} && bash run.sh")[0], "ask")
        for cmd in ["bash plain.sh", "bash missing.sh"]:
            with self.subTest(cmd=cmd):
                # these mention tripo only through the path: still silent
                self.assertIsNone(decision(cmd + " # tripo", cwd=str(d)))

    # ---- I1: one approval must not cover many paid tasks ----

    def test_loop_bodies_denied(self):
        for cmd in ['for i in 1 2 3; do tripo make "crate" --model tripo-v3.1; done',
                    "while true; do tripo mesh decimate @a --face-limit 3000; done",
                    "until false; do tripo redo @a; done",
                    "while tripo make x.png --model tripo-v3.1; do sleep 1; done",
                    "for f in *.png\ndo\n  tripo make \"$f\" --model tripo-v3.1\ndone",
                    "for f in a b; do if true; then tripo anim rig @a; fi; done",
                    "for f in a b; do bash -c 'tripo make x.png --model tripo-v3.1'; done",
                    "for f in a b; do mise exec -- tripo redo @a; done"]:
            with self.subTest(cmd=cmd):
                self.assertIn("birden çok ücretli görevi", self.assertDeny(cmd))
        # free calls in a loop and a paid call after the loop are fine
        self.assertSilent("for i in 1 2; do tripo task get $i; done")
        self.assertAsk("for i in 1 2; do echo $i; done; tripo make x.png --model tripo-v3.1")
        self.assertAsk("for x in tripo; do echo $x; done; tripo redo @a")

    def test_loop_after_a_shell_keyword_denied(self):
        # R2: a loop keyword after then/else/elif/do/time/! in the same segment
        for cmd in ["if [ -f x.png ]; then for i in 1 2 3; do tripo make x.png "
                    "--model tripo-v3.1; done; fi",
                    "if false; then :; else while true; do tripo make x.png; done; fi",
                    "if false; then :; elif true; then until false; do tripo redo @a; done; fi",
                    "for i in 1 2; do while true; do tripo redo @a; done; done",
                    "time while true; do tripo redo @a; done",
                    "! until false; do tripo redo @a; done",
                    # zsh `repeat N`: short form, do/done form, brace form
                    "repeat 3 tripo make x.png --model tripo-v3.1",
                    "repeat 3 do tripo make x.png --model tripo-v3.1; done",
                    "repeat 3\ndo\n  tripo redo @a\ndone",
                    "repeat 3 { tripo redo @a; }",
                    "repeat 3 {\n  tripo redo @a\n}",
                    "if true; then repeat 2 tripo redo @a; fi",
                    "f(){ tripo redo @a; }; repeat 2 f"]:
            with self.subTest(cmd=cmd):
                self.assertIn("birden çok ücretli görevi", self.assertDeny(cmd))
        # the loop ends where it ends: a paid call after it is one window
        for cmd in ["if true; then for i in 1 2; do echo $i; done; fi; tripo redo @a",
                    "repeat 2 echo hi; tripo redo @a",
                    "repeat 2 do echo hi; done; tripo redo @a",
                    "repeat 2 { echo hi; }; tripo redo @a",
                    "if true; then tripo redo @a; fi",
                    "time tripo redo @a"]:
            with self.subTest(cmd=cmd):
                self.assertAsk(cmd)
        self.assertSilent("repeat 3 tripo balance --json")

    def test_repeaters_denied(self):
        for cmd in ["seq 3 | xargs -I{} tripo make x.png --model tripo-v3.1",
                    "echo @a | xargs -n 1 tripo redo",
                    "ls *.png | parallel tripo make {} --model tripo-v3.1",
                    "find . -name '*.png' -exec tripo make {} --model tripo-v3.1 \\;",
                    "find . -name '*.png' -execdir tripo make {} +",
                    "fd -e png -x tripo make {} --model tripo-v3.1",
                    "watch -n 60 tripo make x.png --model tripo-v3.1",
                    "ls | xargs -I{} bash -c 'tripo make {} --model tripo-v3.1'"]:
            with self.subTest(cmd=cmd):
                self.assertDeny(cmd)
        self.assertSilent("find . -name tripo")
        self.assertSilent("ls | xargs -n1 tripo task get")

    def test_functions_called_many_times_denied(self):
        self.assertDeny("f(){ tripo make x.png --model tripo-v3.1; }; f; f")
        self.assertDeny("f() {\n  tripo redo @a\n}\nfor i in 1 2; do f; done")
        self.assertDeny("function g { tripo anim rig @a; }; g && g")
        # defined and called once, or never: one window
        self.assertAsk("f(){ tripo make x.png --model tripo-v3.1; }; f")
        self.assertAsk("f(){ tripo make x.png --model tripo-v3.1; }")
        # a free function body called twice is fine
        self.assertSilent("f(){ tripo balance --json; }; f; f")

    def test_batch_run_and_ai_request_denied(self):
        self.assertIn("manifest", self.assertDeny("tripo batch run jobs.yaml"))
        self.assertIn("senaryo", self.assertDeny("tripo ai 'a knight'"))
        self.assertDeny("tripo --profile work ai make a chest for my game")
        # bare `tripo ai` (interactive) is one window, not a deny
        self.assertAsk("tripo ai")

    def test_mcp_with_stdin_asks(self):
        # M9: JSON-RPC fed to `tripo mcp` can call tripo_make
        for cmd in ["echo '{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\"}' | tripo mcp",
                    "cat req.jsonl | tripo mcp --toolset full",
                    "tripo mcp < req.jsonl", "tripo mcp 0< req.jsonl",
                    "tripo mcp <<'EOF'\n{\"method\":\"tools/call\"}\nEOF",
                    "tripo mcp <<< '{\"method\":\"tools/call\"}'",
                    "printf x |& rtk tripo mcp"]:
            with self.subTest(cmd=cmd):
                self.assertIn("mcp", self.assertAsk(cmd))
        # without stdin it is the interactive server: free
        self.assertSilent("tripo mcp")
        self.assertSilent("tripo mcp --toolset full > log.txt 2>&1")
        self.assertSilent("tripo mcp | tee log.txt")

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
                    "tripo ai", "tripo --json make x.png --model tripo-v3.1"]:
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

    def test_dry_run_with_more_paid_steps_denied(self):
        # M2: a newer CLI that adds a default chain step is caught by its own dry-run
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 1,
                          "generation_credits_estimate": 30,
                          "steps": [{"name": "image-to-model", "task_type": "image_to_model"},
                                    {"name": "convert", "task_type": "convert_model"}]})
        d = decision("tripo make x.png --model tripo-v3.1", env_extra={"TRIPO_GUARD_DRYRUN": dry})
        self.assertEqual(d[0], "deny", d)
        self.assertIn(B17, d[1])
        self.assertIn("convert", d[1])
        # extra candidates are extra paid generations
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 2,
                          "steps": [{"name": "image-to-model", "task_type": "image_to_model"}]})
        d = decision("tripo make x.png --model tripo-v3.1", env_extra={"TRIPO_GUARD_DRYRUN": dry})
        self.assertEqual(d[0], "deny", d)
        # import + the free rig-check is one paid step
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 1,
                          "steps": [{"name": "import", "task_type": "import_model"},
                                    {"name": "rig-check", "task_type": "animate_prerigcheck"}]})
        self.assertEqual(self.ask("tripo make m.glb --then rig-check",
                                  TRIPO_GUARD_DRYRUN=dry)[:18], "Tripo kredi kilidi")
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 1,
                          "steps": [{"name": "texture", "task_type": "texture_model"}]})
        self.ask("tripo make @a --then texture", TRIPO_GUARD_DRYRUN=dry)

    @staticmethod
    def file_dry(*steps, estimate=None):
        """A 0.9.0-shaped dry-run for a local file: import first, then the chain."""
        return json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 1,
                           "generation_credits_estimate": estimate,
                           "steps": [{"name": "import", "task_type": "import_model"},
                                     *({"name": n, "task_type": t} for n, t in steps)]})

    def test_file_import_is_not_a_second_paid_step(self):
        # R1: the CLI's leading import of a local file is part of the one step
        for cmd, steps in [
                ('tripo make model.glb --then "rig:model=v3.0;spec=mixamo;rig_type=biped"',
                 [("rig", "animate_rig")]),
                ("tripo make model.glb --then decimate:face_limit=3000",
                 [("decimate", "highpoly_to_lowpoly")]),
                ("tripo make model.glb --then texture", [("texture", "texture_model")])]:
            with self.subTest(cmd=cmd):
                r = self.ask(cmd, TRIPO_GUARD_DRYRUN=self.file_dry(*steps, estimate=35))
                self.assertIn("tahmini kredi: 35 (dry-run)", r)  # the full dry-run price
        # two real paid steps after the import are still two (the real 0.9.0 plan for
        # `--then rig,animate:preset:walk`), whether our parse or the dry-run sees them
        rig_anim = self.file_dry(("rig", "animate_rig"), ("retarget", "animate_retarget"))
        for cmd in ["tripo make model.glb --then rig,animate:preset:walk",
                    "tripo make model.glb --then rig"]:  # a newer CLI adding a step
            with self.subTest(cmd=cmd):
                d = decision(cmd, env_extra={"TRIPO_GUARD_DRYRUN": rig_anim})
                self.assertEqual(d[0], "deny", d)
                self.assertIn(B17, d[1])
                self.assertIn("rig", d[1])
                self.assertIn("retarget", d[1])
        # a dry-run that names import by task type only is the same import
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 1,
                          "steps": [{"name": "upload", "task_type": "import_model"},
                                    {"name": "uv", "task_type": "uv_unwrap"}]})
        self.ask("tripo make model.glb --then uv", TRIPO_GUARD_DRYRUN=dry)
        # an import that is not the leading step is counted
        dry = json.dumps({"dry_run": True, "valid": True, "errors": [], "candidates": 1,
                          "steps": [{"name": "texture", "task_type": "texture_model"},
                                    {"name": "import", "task_type": "import_model"}]})
        d = decision("tripo make @a --then texture", env_extra={"TRIPO_GUARD_DRYRUN": dry})
        self.assertEqual(d[0], "deny", d)

    def test_deny_names_the_steps(self):
        d = decision("tripo make @a --then texture,rig")
        self.assertEqual(d[0], "deny")
        self.assertIn("texture", d[1])
        self.assertIn("rig", d[1])


class StartupFailure(unittest.TestCase):
    """I2: a guard that cannot import tripo_plan must ask, not exit 1 (fail open)."""

    def setUp(self):
        self.dir = tmpdir("tripo-guard-broken-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "scripts" / "hooks").mkdir(parents=True)
        self.hook = self.dir / "scripts" / "hooks" / "tripo_guard.py"
        shutil.copy(HOOK, self.hook)

    def run_copy(self, command):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("TRIPO_GUARD_") and k != "PYTHONPATH"}
        env["TRIPO_GUARD_OFFLINE"] = "1"
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        return subprocess.run([sys.executable, str(self.hook)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=60)

    def check(self):
        p = self.run_copy("tripo make x.png --model tripo-v3.1")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, p.stdout)
        out = json.loads(lines[0])["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertIn("Tripo kredi kilidi başlatılamadı", out["permissionDecisionReason"])
        # case-insensitive, and silent for commands that never mention tripo
        p = self.run_copy("TRIPO redo @a")
        self.assertIn('"ask"', p.stdout)
        for command in ["ls -la", "bash -c 'echo hi'"]:
            p = self.run_copy(command)
            self.assertEqual((p.returncode, p.stdout.strip()), (0, ""), p.stderr)

    def test_syntax_error_in_tripo_plan(self):
        (self.dir / "scripts" / "tripo_plan.py").write_text("def broken(:\n    pass\n")
        self.check()

    def test_tripo_plan_missing(self):
        self.check()

    def test_tripo_plan_raises_at_import(self):
        (self.dir / "scripts" / "tripo_plan.py").write_text("import sys\nsys.exit(3)\n")
        self.check()


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
