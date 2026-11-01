#!/usr/bin/env python3
"""Project and general lessons (spec section 17).

  lessons.py add --project P --title T --rule R --evidence E --cli V --model WIRE [--scope S]
  lessons.py candidates --project P
  lessons.py promote --project P --id N --approved
  lessons.py stale --cli V --model WIRE [--model WIRE ...] [--project P]
  every command also takes [--state FILE] [--general FILE]

Files: <project>/.claude/tripo/lessons.md (written without asking: project scope, reversible) and
<skill>/lessons/general.md (user-private, gitignored; written only by `promote --approved`, K4).
Block format (references/lessons-system.md):

  ## L<n>: <title>
  - rule: <one line>
  - evidence: <asset, task_id, date>
  - scope: project | general
  - cli: <tripo-cli version>
  - model: <wire model id>
  - confidence: <times confirmed>
  - status: active | promoted | needs_reverify
  - date: <YYYY-MM-DD, last confirmed>
  - source: <project L<n>>            (general.md only)

add       appends a block; a lesson with the same title is confirmed instead (confidence + 1,
          evidence/cli/model/date refreshed, needs_reverify back to active). Registers the project
          in <skill>/.state.json "projects".
candidates  active project lessons whose title and rule hold no game-specific term (art_style
          words, naming.model_pattern words, asset ids, the game's name, budget numbers), or that
          repeat (same title or rule) in another registered project's lessons.md.
promote   refuses without --approved (exit 2); appends the lesson to general.md (or confirms the
          one with the same title there) and marks the project copy `promoted`.
stale     marks active lessons tied to another tripo-cli version, or to another date of the same
          model family (v3.1-20250101 vs v3.1-20260211), `needs_reverify` in general.md, every
          registered project and --project. They are read as warnings until confirmed again.
Output: one JSON line. Exit codes: see common.py.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

BLOCK_RE = re.compile(r"^## L(\d+): (.*)$")
FIELD_RE = re.compile(r"^- ([a-z_]+): ?(.*)$")
STATUSES = ("active", "promoted", "needs_reverify")
UNTIED = {"", "-", "any", "none", "n/a"}
STOPWORDS = {"and", "the", "with", "style", "for", "from", "into", "very"}
TEMPLATE = common.SKILL_ROOT / "lessons" / "general.example.md"
GENERAL = common.SKILL_ROOT / "lessons" / "general.md"
PROJECT_HEADER = ("# Project lessons\n\nWritten by scripts/lessons.py (block format: references/lessons-system.md). "
                  "Project lessons win over general ones.\n")


class LessonError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ---------- file model (lossless for lines it does not own) ----------

class Block:
    def __init__(self, num: int, title: str, lines: list):
        self.id, self.title, self.lines = num, title, lines

    def get(self, key):
        for ln in self.lines:
            m = FIELD_RE.match(ln.rstrip("\n"))
            if m and m.group(1) == key:
                return m.group(2).strip()
        return None

    def set(self, key, value) -> None:
        new = f"- {key}: {value}\n"
        for i, ln in enumerate(self.lines):
            m = FIELD_RE.match(ln.rstrip("\n"))
            if m and m.group(1) == key:
                self.lines[i] = new
                return
        at = len(self.lines)
        while at > 0 and not self.lines[at - 1].strip():
            at -= 1
        self.lines.insert(at, new)

    def render(self) -> str:
        return f"## L{self.id}: {self.title}\n" + "".join(self.lines)


class LessonFile:
    def __init__(self, path: Path, header: str):
        self.path = path
        text = path.read_text(encoding="utf-8") if path.is_file() else header
        self.preamble, self.blocks = [], []
        for line in text.splitlines(keepends=True):
            m = BLOCK_RE.match(line.rstrip("\n"))
            if m:
                self.blocks.append(Block(int(m.group(1)), m.group(2).strip(), []))
            elif self.blocks:
                self.blocks[-1].lines.append(line)
            else:
                self.preamble.append(line)

    def find(self, num=None, title=None):
        for b in self.blocks:
            if (num is not None and b.id == num) or (title is not None and norm(b.title) == norm(title)):
                return b
        return None

    def append(self, title: str, fields: dict) -> Block:
        if self.blocks and self.blocks[-1].lines and self.blocks[-1].lines[-1].strip():
            self.blocks[-1].lines.append("\n")
        elif not self.blocks and self.preamble and self.preamble[-1].strip():
            self.preamble.append("\n")
        b = Block(max((x.id for x in self.blocks), default=0) + 1, title,
                  [f"- {k}: {v}\n" for k, v in fields.items()])
        self.blocks.append(b)
        return b

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("".join(self.preamble) + "".join(b.render() for b in self.blocks), encoding="utf-8")
        tmp.replace(self.path)


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def project_file(root: Path) -> LessonFile:
    return LessonFile(common.tripo_dir(root) / "lessons.md", PROJECT_HEADER)


def general_file(a) -> LessonFile:
    header = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.is_file() else "# General lessons\n"
    return LessonFile(Path(a.general) if a.general else GENERAL, header)


def registered_projects(a) -> list:
    return [Path(p) for p in common.state_read(a.state).get("projects", []) if isinstance(p, str)]


def lesson_out(b: Block) -> dict:
    return {"id": b.id, "title": b.title, **{k: b.get(k) for k in
            ("rule", "evidence", "scope", "cli", "model", "confidence", "status", "date", "source")}}


# ---------- commands ----------

def cmd_add(a) -> dict:
    root = common.require_project(a.project)
    lf = project_file(root)
    today = date.today().isoformat()
    title = one_line(a.title)
    if not title or not one_line(a.rule):
        raise LessonError(common.EXIT_USAGE, "--title and --rule must not be empty")
    b = lf.find(title=title)
    if b is not None:
        try:
            conf = int(b.get("confidence") or 0) + 1
        except ValueError:
            conf = 1
        for key, val in (("rule", one_line(a.rule)), ("evidence", one_line(a.evidence)), ("cli", one_line(a.cli)),
                         ("model", one_line(a.model)), ("confidence", conf), ("date", today)):
            b.set(key, val)
        if b.get("status") == "needs_reverify":
            b.set("status", "active")
        confirmed = True
    else:
        b = lf.append(title, {"rule": one_line(a.rule), "evidence": one_line(a.evidence), "scope": one_line(a.scope),
                              "cli": one_line(a.cli), "model": one_line(a.model), "confidence": 1,
                              "status": "active", "date": today})
        confirmed = False
    lf.save()
    known = [str(p) for p in registered_projects(a)]
    me = str(root.resolve())
    if me not in known:
        common.state_update({"projects": known + [me]}, path=a.state)
    return {"ok": True, "path": str(lf.path), "id": b.id, "confirmed": confirmed, "lesson": lesson_out(b)}


def game_terms(root: Path, profile: dict) -> list:
    """(term, normalised phrase) pairs that make a lesson game-specific."""
    terms = []
    for w in re.findall(r"[a-z0-9]+", (profile.get("art_style") or "").lower()):
        if len(w) >= 3 and w not in STOPWORDS:
            terms.append((w, w))
    pattern = (profile.get("naming") or {}).get("model_pattern") or ""
    pattern = re.sub(r"\{[^}]*\}", " ", re.sub(r"\.\w+$", "", pattern))  # no placeholders, no extension
    for w in re.findall(r"[a-z0-9]+", pattern.lower()):
        if len(w) >= 3:
            terms.append((w, w))
    for f in sorted((common.tripo_dir(root) / "assets").glob("*.json")):
        terms.append((f.stem, norm(f.stem)))
    m = re.search(r'^config/name="([^"]*)"', (root / "project.godot").read_text(encoding="utf-8", errors="replace"), re.M)
    for name in ((m.group(1) if m else ""), root.name):
        if norm(name):
            terms.append((norm(name), norm(name)))
    for v in (profile.get("budgets") or {}).values():
        terms.append((str(v), str(v)))
    seen, out = set(), []
    for t in terms:
        if t[1] and t[1] not in seen:
            seen.add(t[1])
            out.append(t)
    return out


def cmd_candidates(a) -> dict:
    root = common.require_project(a.project)
    profile = common.load_profile(root)
    terms = game_terms(root, profile)
    others = []
    for p in registered_projects(a):
        if p.resolve() != root.resolve() and (common.tripo_dir(p) / "lessons.md").is_file():
            others.append((p, project_file(p)))
    candidates, excluded = [], []
    for b in project_file(root).blocks:
        if b.get("status") != "active":
            continue
        text = f" {norm(b.title + ' ' + (b.get('rule') or ''))} "
        found = [t for t, phrase in terms if f" {phrase} " in text]
        repeat = next((str(p) for p, lf in others for o in lf.blocks
                       if norm(o.title) == norm(b.title) or (b.get("rule") and norm(o.get("rule")) == norm(b.get("rule")))),
                      None)
        if not found:
            candidates.append({**lesson_out(b), "reason": "no game-specific terms"})
        elif repeat:
            candidates.append({**lesson_out(b), "reason": f"repeats in {repeat}", "terms": found})
        else:
            excluded.append({"id": b.id, "title": b.title, "terms": found})
    return {"ok": True, "project": str(root), "candidates": candidates, "excluded": excluded}


def cmd_promote(a) -> dict:
    if not a.approved:
        raise LessonError(common.EXIT_USAGE, "promote writes the user's general lessons and needs the user's yes: "
                                             "ask first, then pass --approved (K4)")
    root = common.require_project(a.project)
    lf = project_file(root)
    b = lf.find(num=a.id)
    if b is None:
        raise LessonError(common.EXIT_NOT_FOUND, f"no lesson L{a.id} in {lf.path}")
    gf = general_file(a)
    g = gf.find(title=b.title)
    if g is not None:
        try:
            g.set("confidence", int(g.get("confidence") or 0) + 1)
        except ValueError:
            g.set("confidence", 1)
        g.set("date", date.today().isoformat())
        already = True
    else:
        fields = {k: b.get(k) or "-" for k in ("rule", "evidence")}
        fields.update(scope="general", cli=b.get("cli") or "-", model=b.get("model") or "-",
                      confidence=b.get("confidence") or 1, status="active", date=date.today().isoformat(),
                      source=f"{root.name} L{b.id}")
        g = gf.append(b.title, fields)
        already = False
    gf.save()
    b.set("status", "promoted")
    lf.save()
    return {"ok": True, "general": str(gf.path), "general_id": g.id, "already_general": already,
            "project": str(lf.path), "id": b.id}


def family(model: str) -> str:
    m = re.fullmatch(r"(.+)-\d{8}", model or "")
    return m.group(1) if m else (model or "")


def cmd_stale(a) -> dict:
    files = [general_file(a)]
    roots = registered_projects(a)
    if a.project:
        roots.append(common.require_project(a.project))
    seen = set()
    for r in roots:
        key = str(r.resolve())
        if key not in seen and (common.tripo_dir(r) / "lessons.md").is_file():
            seen.add(key)
            files.append(project_file(r))
    current = {family(m): m for m in a.model}
    marked = []
    for lf in files:
        changed = False
        for b in lf.blocks:
            if b.get("status") != "active":
                continue
            why = []
            cli = (b.get("cli") or "").strip()
            if cli.lower() not in UNTIED and cli != a.cli:
                why.append(f"cli {cli} != {a.cli}")
            model = (b.get("model") or "").strip()
            fam = family(model)
            if model.lower() not in UNTIED and fam in current and current[fam] != model:
                why.append(f"model {model} != {current[fam]}")
            if why:
                b.set("status", "needs_reverify")
                marked.append({"file": str(lf.path), "id": b.id, "title": b.title, "why": "; ".join(why)})
                changed = True
        if changed:
            lf.save()
    return {"ok": True, "cli": a.cli, "models": a.model, "files": [str(f.path) for f in files], "marked": marked}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        common.fail(common.EXIT_USAGE, f"usage: {message}")


def main(argv) -> int:
    p = Parser(prog="lessons.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    s = sub.add_parser("add")
    s.add_argument("--project", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--rule", required=True)
    s.add_argument("--evidence", required=True)
    s.add_argument("--cli", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--scope", default="project")
    s = sub.add_parser("candidates")
    s.add_argument("--project", required=True)
    s = sub.add_parser("promote")
    s.add_argument("--project", required=True)
    s.add_argument("--id", required=True, type=int)
    s.add_argument("--approved", action="store_true")
    s = sub.add_parser("stale")
    s.add_argument("--cli", required=True)
    s.add_argument("--model", required=True, action="append")
    s.add_argument("--project")
    for s in sub.choices.values():
        s.add_argument("--state", help="skill state file (default <skill>/.state.json)")
        s.add_argument("--general", help="general lessons file (default <skill>/lessons/general.md)")
    a = p.parse_args(argv)
    try:
        out = {"add": cmd_add, "candidates": cmd_candidates, "promote": cmd_promote, "stale": cmd_stale}[a.cmd](a)
    except LessonError as e:
        common.fail(e.code, str(e))
    common.emit(out)
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
