"""Shared helpers for every tripo-game-assets script.

Contract: a script prints exactly one JSON line on stdout; logs go to stderr.
Exit codes: 0 ok, 2 usage, 3 input not found, 4 internal error,
5 check failed (the script ran fine, the result is negative).
"""
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_INTERNAL = 4
EXIT_CHECK = 5


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


def tripo_dir(project: Path) -> Path:
    """Per-project state directory: <project>/.claude/tripo."""
    return Path(project) / ".claude" / "tripo"
