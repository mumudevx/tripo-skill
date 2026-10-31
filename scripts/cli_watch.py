#!/usr/bin/env python3
"""tripo-cli version watch: catch a new release, slice its changelog, re-run the golden
dry-runs.

    cli_watch.py check [--update] [--force] [--state FILE] [--golden FILE]

Runs at most once per day (date in <skill>/.state.json) unless --force. Prints one line:

    {"ok", "skipped", "installed", "latest", "updated", "update_available",
     "from", "changelog": [{"version", "items": [str]}], "changelog_missing": bool,
     "changelog_gaps": ["0.7.x", ...], "relevant": ["0.9.0: ...", ...],
     "golden": {"passed": n, "failed": [{"name", "diff": [str]}]}, "golden_ok_for"}

A skipped run prints only {"ok", "skipped": true, "installed", "golden_ok_for", ...} with
an empty changelog and golden null: it needs no CLI at all.

changelog: sections strictly newer than the version last seen (state `cli_version`; the
version the goldens were recorded on when there is none) up to the installed one, oldest
first. Sources, in order: the installed package's CHANGELOG.md (`npm root -g`/tripo-cli,
then the package that holds the tripo binary), then GitHub raw CHANGELOG.md via curl (no
auth; skipped when CLI_WATCH_OFFLINE=1). Versions no source has are reported as
changelog_missing / changelog_gaps; the skill then says "changelog eksik".

relevant: the bullets that mention a parameter from prices.json or one of KEYWORDS.

--update runs `tripo update --yes` when `update --check` reports a newer version (the
user granted this permanently, spec section 15). Without it the watcher only looks.

Golden file (tests/golden_dryruns.json): [{"name", "argv": ["tripo", "make", ...],
"expect": {"valid", "payload_subset", "warnings_contains", "errors_contains", "estimate",
and optionally "warnings_count", "errors_count"}}]. The runner executes `argv` with
`--dry-run --json` appended and nothing else, ever: argv must be a `tripo make` command.
Placeholders in argv are replaced by throw-away files/ids: {png} {png2} {png3} {glb}
{task}. payload_subset maps a step name (text-to-model, image-to-model, decimate, rig...)
to a subset of that step's payload (dicts match recursively, lists and scalars exactly;
the last step with that name is used). estimate is generation_credits_estimate.

Exit codes: 0 ok, 4 tripo CLI missing/broken, 5 at least one golden drifted.
The tripo binary is $TRIPO, else `tripo` on PATH.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import tripo_plan  # noqa: E402

GOLDEN_FILE = common.SKILL_ROOT / "tests" / "golden_dryruns.json"
RECORDED_VERSION = "0.9.0"  # the tripo-cli the goldens were recorded on
GITHUB_CHANGELOG = ("https://raw.githubusercontent.com/vast-enterprise/Tripo-API-CLI/"
                    "HEAD/CHANGELOG.md")
KEYWORDS = ("model", "default", "pbr", "texture", "rig", "decimate", "segment", "dry-run",
            "estimate", "validation", "reject", "exit", "retire", "price", "credit",
            "face_limit")
TIMEOUT = 60

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
GLB = b"glTF\x02\x00\x00\x00" + b"\x00" * 16
TASK_ID = "0d8a7c1e-1111-4222-8333-944455556666"
PLACEHOLDERS = {"{png}": "front.png", "{png2}": "left.png", "{png3}": "back.png",
                "{glb}": "model.glb", "{task}": TASK_ID}


# ---------- changelog ----------

def parse_version(text):
    """(major, minor, patch) from '0.9.0', 'v0.9.0' or '[0.9.0]'; None if it has no x.y.z."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text))
    return tuple(int(g) for g in m.groups()) if m else None


def _sections(text):
    """[(version string, [item, ...])] in file order. A bullet at any depth is one item;
    an indented non-bullet line continues the previous item."""
    out, items, version = [], None, None
    for line in text.splitlines():
        head = re.match(r"##\s+\[?v?(\d+\.\d+\.\d+)", line)
        if head:
            version, items = head.group(1), []
            out.append((version, items))
        elif items is None:
            continue
        elif re.match(r"\s*[-*]\s+\S", line):
            items.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
        elif line.strip() and items and line[:1].isspace():
            items[-1] += " " + line.strip()
    return out


def changelog_slice(text, lo, hi):
    """Sections with lo < version <= hi, oldest first: [{"version", "items"}]."""
    low, high = parse_version(lo), parse_version(hi)
    got = {v: i for v, i in _sections(text) if low < parse_version(v) <= high}
    return [{"version": v, "items": got[v]} for v in sorted(got, key=parse_version)]


def missing_series(sections, lo, hi):
    """What no source covered between lo (exclusive) and hi: whole minor series with no
    section ("0.7.x") and the target version itself when it has none."""
    low, high = parse_version(lo), parse_version(hi)
    if not low < high:
        return []
    have = {parse_version(s["version"])[:2] for s in sections}
    gaps = []
    if low[0] == high[0]:
        gaps = [f"{low[0]}.{minor}.x" for minor in range(low[1] + 1, high[1])
                if (low[0], minor) not in have]
    if high not in {parse_version(s["version"]) for s in sections}:
        gaps.append(".".join(map(str, high)))
    return gaps


def keywords():
    """KEYWORDS plus the parameter names prices.json and the convert tier rules key on."""
    addons = tripo_plan.prices()["generate"]["h_series"]["addons"]
    return tuple(dict.fromkeys([*KEYWORDS, *addons, *tripo_plan.COMPLEX_CONVERT_DEFAULTS]))


def is_relevant(item):
    """True when `item` contains a keyword at the start of a word (rig matches 'rigging',
    not 'origin'; underscores and digits count as part of the word)."""
    pattern = r"(?<![A-Za-z0-9])(?:%s)" % "|".join(re.escape(k) for k in keywords())
    return re.search(pattern, item, re.I) is not None


def relevant(sections):
    return [f"{s['version']}: {i}" for s in sections for i in s["items"] if is_relevant(i)]


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _package_changelogs(exe):
    """CHANGELOG.md of the installed tripo-cli: `npm root -g`/tripo-cli, then the package
    that holds the binary (covers installs outside the global npm root)."""
    paths = []
    if shutil.which("npm"):
        try:
            p = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True,
                               timeout=15, stdin=subprocess.DEVNULL)
            if p.returncode == 0 and p.stdout.strip():
                paths.append(Path(p.stdout.strip().splitlines()[-1]) / "tripo-cli" / "CHANGELOG.md")
        except (OSError, subprocess.TimeoutExpired):
            pass
    for parent in Path(os.path.realpath(exe)).parents:
        pkg = parent / "package.json"
        if pkg.is_file():
            try:
                if json.loads(pkg.read_text(encoding="utf-8")).get("name") == "tripo-cli":
                    paths.append(parent / "CHANGELOG.md")
                    break
            except ValueError:
                pass
    return paths


def _github_changelog():
    if os.environ.get("CLI_WATCH_OFFLINE") == "1" or not shutil.which("curl"):
        return None
    try:
        p = subprocess.run(["curl", "-fsSL", "-m", "20", GITHUB_CHANGELOG], capture_output=True,
                           text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 and p.stdout.strip() else None


def gather_changelog(exe, lo, hi):
    """(sections, gaps, sources) for lo < v <= hi from the package, then GitHub."""
    if not parse_version(lo) < parse_version(hi):
        return [], [], []
    found, sources = {}, []

    def take(text, name):
        added = {s["version"]: s for s in changelog_slice(text, lo, hi) if s["version"] not in found}
        if added:
            found.update(added)
            sources.append(name)

    def ordered():
        return sorted(found.values(), key=lambda s: parse_version(s["version"]))

    for path in _package_changelogs(exe):
        text = _read(path)
        if text:
            take(text, str(path))
    if missing_series(ordered(), lo, hi):
        text = _github_changelog()
        if text:
            take(text, GITHUB_CHANGELOG)
    sections = ordered()
    return sections, missing_series(sections, lo, hi), sources


# ---------- tripo CLI ----------

def _run(exe, args, timeout=TIMEOUT, cwd=None):
    p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def _last_json(text):
    for line in reversed(text.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def installed_version(exe):
    code, out, err = _run(exe, ["--version"], 20)
    version = parse_version(out)
    if code != 0 or version is None:
        raise tripo_plan.TripoCliError(f"`tripo --version` failed (exit {code}): "
                                       f"{(err or out).strip()[-200:]}")
    return ".".join(map(str, version))


def update_check(exe):
    """(latest version or None, error or None) from `tripo update --check --json`."""
    try:
        code, out, err = _run(exe, ["update", "--check", "--json"], 45)
    except subprocess.TimeoutExpired:
        return None, "tripo update --check timed out"
    data = _last_json(out)
    if code != 0 or not data or not parse_version(data.get("latest")):
        return None, f"tripo update --check failed (exit {code}): {(err or out).strip()[-200:]}"
    return ".".join(map(str, parse_version(data["latest"]))), None


def run_update(exe):
    """`tripo update --yes --json` (the only install path). Returns an error string or None."""
    try:
        code, out, err = _run(exe, ["update", "--yes", "--json"], 600)
    except subprocess.TimeoutExpired:
        return "tripo update timed out"
    return None if code == 0 else f"tripo update failed (exit {code}): {(err or out).strip()[-300:]}"


# ---------- golden dry-runs ----------

def _prepare(workdir):
    """Create the placeholder files in workdir (idempotent)."""
    workdir = Path(workdir)
    for name, data in (("front.png", PNG), ("left.png", PNG), ("back.png", PNG),
                       ("model.glb", GLB)):
        if not (workdir / name).exists():
            (workdir / name).write_bytes(data)


def _subset(want, got, path):
    """Diff lines where `want` is not contained in `got` (dicts recursive, rest exact)."""
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return [f"{path}: expected an object, got {got!r}"]
        diffs = []
        for key, val in want.items():
            if key not in got:
                diffs.append(f"{path}.{key}: missing (expected {val!r})")
            else:
                diffs += _subset(val, got[key], f"{path}.{key}")
        return diffs
    return [] if want == got else [f"{path}: expected {want!r}, got {got!r}"]


def _step_payload(steps, name):
    hits = [s for s in steps if isinstance(s, dict) and s.get("name") == name]
    return hits[-1].get("payload", {}) if hits else None


def _missing(needles, haystack, what):
    return [f"{what} lacks {n!r} (has {haystack})" for n in needles
            if not any(n in str(h) for h in haystack)]


def compare(expect, dry):
    """Diff lines between a golden's `expect` and a dry-run result (empty = same)."""
    diffs = []
    if dry.get("valid") is not expect.get("valid"):
        diffs.append(f"valid: expected {expect.get('valid')}, got {dry.get('valid')}")
    if "estimate" in expect and dry.get("generation_credits_estimate") != expect["estimate"]:
        diffs.append(f"estimate: expected {expect['estimate']}, "
                     f"got {dry.get('generation_credits_estimate')}")
    steps = dry.get("steps") or []
    for name, want in (expect.get("payload_subset") or {}).items():
        payload = _step_payload(steps, name)
        if payload is None:
            diffs.append(f"step {name!r}: missing (steps: {[s.get('name') for s in steps]})")
        else:
            diffs += _subset(want, payload, name)
    warnings, errors = dry.get("warnings") or [], dry.get("errors") or []
    diffs += _missing(expect.get("warnings_contains") or [], warnings, "warnings")
    diffs += _missing(expect.get("errors_contains") or [], errors, "errors")
    for key, got in (("warnings_count", warnings), ("errors_count", errors)):
        if key in expect and len(got) != expect[key]:
            diffs.append(f"{key}: expected {expect[key]}, got {len(got)}: {got}")
    return diffs


def run_golden(entry, exe, workdir):
    """Run one golden's argv as `<exe> make ... --dry-run --json` in workdir. Returns diff
    lines (empty = pass). Raises ValueError for anything that is not a `tripo make` argv."""
    argv = entry.get("argv")
    if (not isinstance(argv, list) or len(argv) < 3 or not all(isinstance(a, str) for a in argv)
            or argv[0] != "tripo" or argv[1] != "make"):
        raise ValueError(f"golden {entry.get('name')!r}: argv must be ['tripo', 'make', <input>, ...]")
    _prepare(workdir)
    args = []
    for a in argv[1:]:
        for key, val in PLACEHOLDERS.items():
            a = a.replace(key, val)
        args.append(a)
    try:
        code, out, err = _run(exe, [*args, "--dry-run", "--json"], cwd=workdir)
    except subprocess.TimeoutExpired:
        return [f"timed out after {TIMEOUT}s"]
    dry = _last_json(out)
    if dry is None or dry.get("dry_run") is not True:
        return [f"no JSON dry-run result (exit {code}): {(err or out).strip()[-300:]}"]
    diffs = compare(entry.get("expect") or {}, dry)
    if code not in (0, 2):
        diffs.append(f"exit code {code} (a dry-run exits 0 or 2)")
    return diffs


def run_goldens(entries, exe):
    """{"passed": n, "failed": [{"name", "diff": [str]}]} over all entries."""
    workdir = Path(tempfile.mkdtemp(prefix="cli-watch-"))
    try:
        failed = []
        for entry in entries:
            diff = run_golden(entry, exe, workdir)
            if diff:
                failed.append({"name": entry.get("name"), "diff": diff})
        return {"passed": len(entries) - len(failed), "failed": failed}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------- check ----------

def check(state_path=None, force=False, update=False, golden_path=None, today=None):
    """The whole watch; returns (report dict, exit code). Raises TripoCliError."""
    today = today or date.today().isoformat()
    state = common.state_read(state_path)
    if not force and state.get("last_check") == today:
        return {"ok": True, "skipped": True, "installed": state.get("cli_version"),
                "latest": None, "updated": False, "update_available": None,
                "changelog": [], "changelog_missing": False, "changelog_gaps": [],
                "relevant": [], "golden": None,
                "golden_ok_for": state.get("golden_ok_for")}, common.EXIT_OK

    exe = tripo_plan.tripo_bin()
    if exe is None:
        raise tripo_plan.TripoCliError("tripo CLI not found: set $TRIPO or put tripo on PATH")
    before = installed_version(exe)
    latest, check_error = update_check(exe)
    available = None if latest is None else parse_version(latest) > parse_version(before)
    report = {"ok": True, "skipped": False}
    updated = False
    if update and available:
        error = run_update(exe)
        if error:
            report["update_error"] = error
        installed = installed_version(exe)
        updated = installed != before
        available = parse_version(latest) > parse_version(installed)
    else:
        installed = before

    seen = state.get("cli_version") if parse_version(state.get("cli_version")) else RECORDED_VERSION
    sections, gaps, sources = gather_changelog(exe, seen, installed)
    entries = json.loads(Path(golden_path or GOLDEN_FILE).read_text(encoding="utf-8"))
    golden = run_goldens(entries, exe)

    report.update({"installed": installed, "latest": latest, "updated": updated,
                   "update_available": available, "from": seen, "changelog": sections,
                   "changelog_missing": bool(gaps), "changelog_gaps": gaps,
                   "changelog_sources": sources, "relevant": relevant(sections),
                   "golden": golden})
    if check_error:
        report["update_check_error"] = check_error
    update_state = {"last_check": today, "cli_version": installed}
    if not golden["failed"]:
        update_state["golden_ok_for"] = installed
    common.state_update(update_state, path=state_path)
    report["golden_ok_for"] = common.state_read(state_path).get("golden_ok_for")
    report["ok"] = not golden["failed"]
    return report, common.EXIT_CHECK if golden["failed"] else common.EXIT_OK


def main(argv):
    p = argparse.ArgumentParser(prog="cli_watch.py", description="tripo-cli version watch")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="version check, changelog slice, golden dry-runs")
    c.add_argument("--update", action="store_true", help="install the newer version if there is one")
    c.add_argument("--force", action="store_true", help="ignore the once-a-day limit")
    c.add_argument("--state", help="state file (default <skill>/.state.json)")
    c.add_argument("--golden", help="golden file (default tests/golden_dryruns.json)")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return common.EXIT_USAGE if e.code else common.EXIT_OK
    try:
        report, code = check(a.state, a.force, a.update, a.golden)
    except tripo_plan.TripoCliError as e:
        common.fail(common.EXIT_INTERNAL, str(e))
    except FileNotFoundError as e:
        common.fail(common.EXIT_NOT_FOUND, f"file not found: {e.filename}")
    except ValueError as e:
        common.fail(common.EXIT_USAGE, str(e))
    common.emit(report)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
