"""Shared helpers for every tripo-game-assets script.

Contract: a script prints exactly one JSON line on stdout; logs go to stderr.
Exit codes: 0 ok, 2 usage, 3 input not found, 4 internal error,
5 check failed (the script ran fine, the result is negative).
"""
import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_INTERNAL = 4
EXIT_CHECK = 5

SKILL_ROOT = Path(__file__).resolve().parent.parent


def emit(obj: dict) -> None:
    """Print one JSON line on stdout."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def fail(code: int, msg: str, **extra):
    """Emit {"ok": false, "error": msg, ...extra} and exit with `code`."""
    emit({"ok": False, "error": msg, **extra})
    raise SystemExit(code)


def find_project_root(start: Path):
    """Nearest directory (start itself included) that holds project.godot, or None."""
    p = Path(start).resolve()
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "project.godot").is_file():
            return d
    return None


def require_project(arg) -> Path:
    """The Godot project root at or above `arg`; exit 3 when there is none."""
    start = Path(arg).expanduser()
    root = find_project_root(start) if start.exists() else None
    if root is None:
        fail(EXIT_NOT_FOUND, f"no project.godot at or above {arg}")
    return root


def tripo_dir(project: Path) -> Path:
    """Per-project state directory: <project>/.claude/tripo."""
    return Path(project) / ".claude" / "tripo"


PROFILE_SCHEMA = "profile/1"


def profile_path(project: Path) -> Path:
    return tripo_dir(project) / "profile.json"


def load_profile(project: Path) -> dict:
    """The project's profile.json. A missing, unreadable or foreign-schema profile stops the
    script with a message that names the fix; there is no silent fallback."""
    path = profile_path(project)
    init_cmd = f"python3 {SKILL_ROOT / 'scripts' / 'profile.py'} init {project} --answers <json>"
    if not path.is_file():
        fail(EXIT_NOT_FOUND, f"no profile at {path}; run `{init_cmd}` first "
                             f"(`profile.py detect {project}` proposes the values)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        fail(EXIT_INTERNAL, f"profile {path} is not valid JSON: {e}")
    if not isinstance(data, dict) or data.get("schema") != PROFILE_SCHEMA:
        found = data.get("schema") if isinstance(data, dict) else None
        fail(EXIT_CHECK, f"profile {path} has schema {found!r}, expected {PROFILE_SCHEMA!r}; "
                         f"re-run `{init_cmd} --force`", migrate=True)
    return data


# ---------- <skill>/.state.json ----------
# Shared by cli_watch.py (last_check, cli_version, golden_ok_for) and godot_place.py /
# lessons.py ("projects"). Always read-modify-write; never replace the whole file.

STATE_FILE = SKILL_ROOT / ".state.json"


def state_read(path=None) -> dict:
    """The state dict ({} when the file is missing). A file that is not a JSON object is
    moved to <name>.corrupt (never silently dropped) and treated as empty."""
    path = Path(path or STATE_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError:
        data = None
    if not isinstance(data, dict):
        aside = path.with_name(path.name + ".corrupt")
        os.replace(path, aside)
        sys.stderr.write(f"state file {path} was not a JSON object; kept as {aside}\n")
        return {}
    return data


def _merge(base: dict, updates: dict) -> dict:
    for key, val in updates.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _merge(base[key], val)
        else:
            base[key] = val
    return base


def state_update(updates: dict, path=None) -> dict:
    """Merge `updates` into the state file (nested dicts merge, other values replace) and
    return the new state. The write is atomic."""
    path = Path(path or STATE_FILE)
    state = _merge(state_read(path), updates)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return state
