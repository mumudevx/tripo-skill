"""Checks on the skill's reference docs (references/*.md).

Every fenced `tripo ...` command must match the argv shape of a golden dry-run
(tests/golden_dryruns.json, recorded on tripo-cli 0.9.0) or carry the marker
`<!-- unverified -->` on the line right before its fence or inside the block.

Shape (Task 6 ruling CV4): both sides drop --dry-run/--json/--yes and every
positional input (prompt, image path, model file, task id or @label), then compare
the subcommand, the --model value (alias -> wire id), the --for scenario, the set
of -p keys and the --then steps with their argument keys.
"""
import ast
import json
import re
import shlex
import unittest

from tests.util import ROOT, SCRIPTS

REFS = ROOT / "references"
GOLDEN = ROOT / "tests" / "golden_dryruns.json"
PRICES = SCRIPTS / "data" / "prices.json"
THRESHOLDS = SCRIPTS / "data" / "qa_thresholds.json"
QA_PY = SCRIPTS / "blender" / "qa.py"
PREFLIGHT_PY = SCRIPTS / "blender" / "preflight_img.py"
LESSONS_PY = SCRIPTS / "lessons.py"

EXPECTED = ("tripo-cli.md", "generation-planning.md", "image-preflight.md", "qa-checklist.md",
            "fix-tradeoffs.md", "rigging.md", "godot.md", "lessons-system.md", "cli-updates.md",
            "profile-schema.md")
MAX_LINES = 400
MARKER = "<!-- unverified -->"

# `tripo make` options that take a value (anything else starting with '-' is a flag)
VALUE_OPTS = {"--model", "--then", "-p", "--param", "--name", "-n", "--candidates", "--seed",
              "-o", "--out", "--for", "--timeout", "--profile"}
DROP_FLAGS = {"--dry-run", "--json", "--yes", "--quiet", "--no-open", "--no-wait",
              "--no-download", "--notify"}
# --then step names and aliases (tripo-processing.md section 0.6), and the key a bare value sets
STEP_ALIASES = {"check": "rig-check", "rigcheck": "rig-check", "animate": "retarget",
                "lowpoly": "decimate"}
STEPS = {"refine", "texture", "convert", "import", "rig-check", "rig", "retarget", "segment",
         "complete", "decimate", "uv", "smartsegment", "edit", *STEP_ALIASES}
PRIMARY = {"convert": "format", "decimate": "face_limit", "texture": "texture_quality",
           "segment": "model", "smartsegment": "granularity", "rig": "rig_type",
           "retarget": "animation"}


def model_aliases():
    table = json.loads(PRICES.read_text())["generate"]["aliases"]
    return {k.lower(): v for k, v in table.items()}


def then_steps(spec: str):
    """`--then` string -> tuple of (step, frozenset(argument keys))."""
    steps = []
    for tok in spec.split(","):
        name, sep, args = tok.partition(":")
        name = name.strip()
        if name in STEPS:
            steps.append([STEP_ALIASES.get(name, name), set()])
            parts = args.split(";") if sep else []
        elif "=" in tok and steps:  # "decimate:model=v3.0,face_limit=5000"
            parts = tok.split(";")
        else:
            raise ValueError(f"cannot parse --then token {tok!r}")
        step = steps[-1]
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "=" in part and not part.startswith("preset:"):
                step[1].add(part.split("=", 1)[0].strip())
            else:
                step[1].add(PRIMARY.get(step[0], "<primary>"))
    return tuple((n, frozenset(k)) for n, k in steps)


def shape(argv, aliases):
    """Normalised shape of a tripo argv (list of tokens starting with 'tripo')."""
    if not argv or argv[0] != "tripo":
        raise ValueError(f"not a tripo command: {argv!r}")
    args = [a for a in argv[1:] if a not in DROP_FLAGS]
    sub, model, scenario, pkeys, steps = None, None, None, set(), ()
    i = 0
    while i < len(args):
        a = args[i]
        if a in VALUE_OPTS:
            if i + 1 >= len(args):
                raise ValueError(f"{a} without a value in {argv!r}")
            v = args[i + 1]
            if a == "--model":
                model = aliases.get(v.lower(), v.lower())
            elif a == "--for":
                scenario = v
            elif a in ("-p", "--param"):
                pkeys.add(v.split("=", 1)[0])
            elif a == "--then":
                steps += then_steps(v)
            i += 2
            continue
        if sub is None and not a.startswith("-"):
            sub = a
        i += 1
    return (sub, model, scenario, frozenset(pkeys), steps)


def golden_shapes():
    aliases = model_aliases()
    return {shape(g["argv"], aliases) for g in json.loads(GOLDEN.read_text())}


def fenced_commands(text: str):
    """Yield (line_no, argv, marked) for every `tripo ...` line inside a fenced block."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("```"):
            i += 1
            continue
        start = i
        prev = next((lines[j] for j in range(start - 1, -1, -1) if lines[j].strip()), "")
        i += 1
        block = []
        while i < len(lines) and not lines[i].lstrip().startswith("```"):
            block.append((i + 1, lines[i]))
            i += 1
        i += 1  # closing fence
        marked = MARKER in prev or any(MARKER in line for _, line in block)
        pending = None
        for no, raw in block:
            line = raw.strip()
            if pending is not None:
                pending = (pending[0], pending[1] + " " + line.rstrip("\\").strip())
                if not line.endswith("\\"):
                    yield pending[0], shlex.split(pending[1], comments=True), marked
                    pending = None
                continue
            if line.startswith("$ "):
                line = line[2:]
            if not re.match(r"tripo(\s|$)", line):
                continue
            if line.endswith("\\"):
                pending = (no, line.rstrip("\\").strip())
                continue
            yield no, shlex.split(line, comments=True), marked


def reference_files():
    return sorted(REFS.glob("*.md"))


class References(unittest.TestCase):

    def test_expected_files(self):
        missing = [n for n in EXPECTED if not (REFS / n).is_file()]
        self.assertEqual(missing, [], "reference files missing")

    def test_no_higgsfield(self):
        paths = [ROOT / "SKILL.md"] + list(REFS.rglob("*")) + list(SCRIPTS.rglob("*"))
        hits = []
        for p in paths:
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "higgsfield" in text.lower():
                hits.append(str(p.relative_to(ROOT)))
        self.assertEqual(hits, [], "files mention higgsfield (K11)")

    def test_line_caps(self):
        over = {p.name: n for p in reference_files()
                if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_LINES}
        self.assertEqual(over, {}, f"references over {MAX_LINES} lines")

    def test_when_to_read_first(self):
        bad = []
        for p in reference_files():
            head = p.read_text(encoding="utf-8").splitlines()[:6]
            if not any("When to read this" in line for line in head):
                bad.append(p.name)
        self.assertEqual(bad, [], "references must open with 'When to read this'")

    def test_commands_are_golden(self):
        shapes = golden_shapes()
        aliases = model_aliases()
        seen, bad = 0, []
        for p in reference_files():
            for no, argv, marked in fenced_commands(p.read_text(encoding="utf-8")):
                seen += 1
                if marked:
                    continue
                try:
                    s = shape(argv, aliases)
                except ValueError as e:
                    bad.append(f"{p.name}:{no}: {e}")
                    continue
                if s not in shapes:
                    bad.append(f"{p.name}:{no}: {' '.join(argv)}")
        self.assertGreater(seen, 0, "no fenced tripo commands found at all")
        self.assertEqual(bad, [], "fenced tripo commands with no golden shape and no "
                                  f"{MARKER} marker")

    def test_shape_normaliser(self):
        aliases = model_aliases()
        comma = shape(["tripo", "make", "@x", "--then",
                       "decimate:model=v3.0,face_limit=5000,smart_uv=true"], aliases)
        semi = shape(["tripo", "make", "/a/b.glb", "--then",
                      "decimate:model=v3.0;face_limit=5000;smart_uv=true", "--name", "y",
                      "--json"], aliases)
        self.assertEqual(comma, semi)
        self.assertIn(comma, golden_shapes())
        self.assertEqual(shape(["tripo", "make", "{task}", "--then", "convert:gltf"], aliases)[4],
                         (("convert", frozenset({"format"})),))
        self.assertNotIn(shape(["tripo", "make", "x.png", "--model", "tripo-v3.1", "-p",
                                "made_up=1"], aliases), golden_shapes())
        md = "```bash\ntripo make a.png --model tripo-v3.1 -p made_up=1\n```\n"
        self.assertEqual([m for _, _, m in fenced_commands(md)], [False])
        md = MARKER + "\n```bash\ntripo balance\n```\n"
        self.assertEqual([m for _, _, m in fenced_commands(md)], [True])

    def test_every_qa_code_has_tradeoff(self):
        tree = ast.parse(QA_PY.read_text(encoding="utf-8"))
        fix_options = next(ast.literal_eval(n.value) for n in tree.body
                           if isinstance(n, ast.Assign)
                           and any(getattr(t, "id", None) == "FIX_OPTIONS" for t in n.targets))
        severity = json.loads(THRESHOLDS.read_text())["qa"]["severity"]
        self.assertEqual(set(fix_options), set(severity), "qa.py and qa_thresholds.json disagree")
        rows = {}
        for line in (REFS / "fix-tradeoffs.md").read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*`?([A-Z][A-Z_]+)`?\s*\|", line)
            if m:
                rows[m.group(1)] = line
        missing = sorted(set(fix_options) - set(rows))
        self.assertEqual(missing, [], "QA codes without a row in fix-tradeoffs.md")
        unnamed = {c: [o for o in opts if o not in rows[c]] for c, opts in fix_options.items()}
        unnamed = {c: o for c, o in unnamed.items() if o}
        self.assertEqual(unnamed, {}, "a row does not name the fix_options qa.py reports")
        checklist = (REFS / "qa-checklist.md").read_text(encoding="utf-8")
        self.assertEqual([c for c in fix_options if c not in checklist], [],
                         "QA codes missing from qa-checklist.md")

    def test_back_copy_paint_is_not_offered_a_global_recolour(self):
        # T17 F5: recolour edits the whole texture (no region), so it cannot clean paint copied
        # onto one side; the free rung is geometry only and the paint needs a retexture
        tree = ast.parse(QA_PY.read_text(encoding="utf-8"))
        fix_options = next(ast.literal_eval(n.value) for n in tree.body
                           if isinstance(n, ast.Assign)
                           and any(getattr(t, "id", None) == "FIX_OPTIONS" for t in n.targets))
        self.assertNotIn("recolour", fix_options["BACK_COPY"])
        self.assertIn("tripo_retexture", fix_options["BACK_COPY"])
        row = next(ln for ln in (REFS / "fix-tradeoffs.md").read_text(encoding="utf-8").splitlines()
                   if ln.startswith("| `BACK_COPY`"))
        self.assertIn("none / partial", row)
        self.assertIn("no region", row)

    def test_fix_options_are_performed_by_a_script(self):
        # T17 F6: fix_options name only what a script does (a fixkit op, the export flag, or a
        # rung of the ladder routed through tripo_plan / the engine table)
        tree = ast.parse(QA_PY.read_text(encoding="utf-8"))
        fix_options = next(ast.literal_eval(n.value) for n in tree.body
                           if isinstance(n, ast.Assign)
                           and any(getattr(t, "id", None) == "FIX_OPTIONS" for t in n.targets))
        ops_src = (SCRIPTS / "blender" / "fixkit" / "ops.py").read_text(encoding="utf-8")
        registry = re.search(r"OPS = \{fn.__name__: fn for fn in \((.*?)\)\}", ops_src, re.S).group(1)
        fixkit = set(re.findall(r"[a-z_]+", registry))
        export_src = (SCRIPTS / "blender" / "export.py").read_text(encoding="utf-8")
        exported = {"max_texture"} if '"--max-texture"' in export_src else set()
        ladder = {"engine_side", "tripo_retexture", "tripo_uv", "tripo_decimate", "tripo_rig", "tripo_regenerate"}
        # every tripo_ rung is a step tripo_plan can build
        rung_kind = {"tripo_retexture": "texture", "tripo_regenerate": "generate"}
        plan_src = (SCRIPTS / "tripo_plan.py").read_text(encoding="utf-8")
        kinds = set(re.findall(r'"([a-z_]+)"', re.search(r"KINDS = \((.*?)\)", plan_src, re.S).group(1)))
        for rung in sorted(r for r in ladder if r.startswith("tripo_")):
            self.assertIn(rung_kind.get(rung, rung[len("tripo_"):]), kinds, rung)
        unknown = {c: [o for o in opts if o not in fixkit | exported | ladder]
                   for c, opts in fix_options.items()}
        self.assertEqual({c: o for c, o in unknown.items() if o}, {})
        self.assertEqual(fix_options["TEXTURE_OVERSIZE"], ["max_texture"])
        # M7: the recommended paid rung for UV overlap is the Smart UV step, as fix-tradeoffs.md says
        self.assertEqual(fix_options["UV_OVERLAP"][0], "tripo_uv")

    def test_every_preflight_code_documented(self):
        doc = re.search(r"Codes made here:(.*?)FAKE_FORMAT", PREFLIGHT_PY.read_text(), re.S)
        codes = set(re.findall(r"[A-Z][A-Z_]{3,}", doc.group(1))) | {"FAKE_FORMAT"}
        self.assertGreaterEqual(len(codes), 10)
        text = (REFS / "image-preflight.md").read_text(encoding="utf-8")
        self.assertEqual(sorted(c for c in codes if c not in text), [],
                         "preflight codes missing from image-preflight.md")

    def test_lesson_block_matches_parser(self):
        doc = ast.get_docstring(ast.parse(LESSONS_PY.read_text(encoding="utf-8")))
        block = re.search(r"^  ## L<n>: <title>\n(?:  - .*\n)+", doc + "\n", re.M).group(0)
        block = "\n".join(line[2:] for line in block.splitlines())
        self.assertIn("- source:", block)
        text = (REFS / "lessons-system.md").read_text(encoding="utf-8")
        self.assertIn(block, text, "lessons-system.md must copy the lessons.py block verbatim")


if __name__ == "__main__":
    unittest.main()
