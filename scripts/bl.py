#!/usr/bin/env python3
"""Blender runner: run a script from scripts/blender/ headless and return its JSON.

    bl.run("qa.py", ["--model", "x.glb"]) -> dict
    bl.py <script> -- <args...>            (CLI: echoes the JSON line)

Blender exits 0 even when a Python script raises, and its stdout is noisy, so:
  - the script writes its result to a temp file passed as `--out`;
  - `--python-exit-code 4` makes uncaught exceptions non-zero;
  - the out file is deleted before the run, so a stale one can never pass for a result;
  - exit != 0 or a missing out file raises BlenderError(code, stderr_tail).
The Blender binary is $BLENDER, else `blender` on PATH.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

BLENDER_DIR = Path(__file__).resolve().parent / "blender"
TAIL_CHARS = 2000
TIMEOUT_CODE = 124  # same convention as coreutils `timeout`
NOT_FOUND_CODE = 127


class BlenderError(Exception):
    """Blender failed: `code` is its exit code, `stderr_tail` the end of its stderr."""

    def __init__(self, code: int, stderr_tail: str):
        super().__init__(f"blender failed (exit {code}): {stderr_tail}")
        self.code = code
        self.stderr_tail = stderr_tail


def _resolve_script(script: str) -> Path:
    """`scripts/blender/<script>` first, then the string as a path (used by tests)."""
    for cand in (BLENDER_DIR / script, Path(script)):
        if cand.is_file():
            return cand.resolve()
    raise FileNotFoundError(f"blender script not found: {script}")


def _tail(text: str) -> str:
    return text.strip()[-TAIL_CHARS:]


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def run(script: str, args: list, timeout: int = 600, out: str = None) -> dict:
    """Run `script` in headless Blender and return the JSON it wrote to --out.

    `out` is for tests: a fixed out path instead of a private temp file.
    """
    script_path = _resolve_script(script)
    blender = os.environ.get("BLENDER") or "blender"
    exe = shutil.which(blender)
    if exe is None:
        raise BlenderError(NOT_FOUND_CODE, f"blender binary not found: {blender} "
                                           "(set $BLENDER or put blender on PATH)")

    own_tmp = out is None
    if own_tmp:
        fd, out = tempfile.mkstemp(prefix="tripo-bl-", suffix=".json")
        os.close(fd)
    out_path = Path(out)
    out_path.unlink(missing_ok=True)

    # Blender ignores PYTHONPATH, so put scripts/blender on sys.path with a --python-expr
    # that runs before the script (this is what makes `import skill_io` work).
    path_expr = f"import sys; sys.path.insert(0, {str(BLENDER_DIR)!r})"
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "4",
           "--python-expr", path_expr, "--python", str(script_path),
           "--", "--out", str(out_path), *map(str, args)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace", start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            proc.communicate()
            raise BlenderError(TIMEOUT_CODE, f"blender timed out after {timeout}s") from None
        if proc.returncode != 0:
            raise BlenderError(proc.returncode, _tail(stderr) or _tail(stdout))
        if not out_path.is_file():
            raise BlenderError(0, "blender exited 0 but wrote no output file "
                                  f"({script_path.name} must end with skill_io.main). "
                                  + (_tail(stderr) or _tail(stdout)))
        try:
            result = json.loads(out_path.read_text())
        except ValueError as e:
            raise BlenderError(0, f"output file is not valid JSON: {e}") from None
        if not isinstance(result, dict):
            raise BlenderError(0, "output file is not a JSON object")
        return result
    finally:
        # never leave a result behind that a later run could mistake for its own
        out_path.unlink(missing_ok=True)


def main(argv: list) -> int:
    if len(argv) < 2 or argv[1] != "--":
        common.fail(common.EXIT_USAGE, "usage: bl.py <script> -- <args...>")
    script, rest = argv[0], argv[2:]
    try:
        result = run(script, rest)
    except FileNotFoundError as e:
        common.fail(common.EXIT_NOT_FOUND, str(e))
    except BlenderError as e:
        common.fail(common.EXIT_INTERNAL, "blender failed", blender_exit=e.code,
                    stderr_tail=e.stderr_tail)
    common.emit(result)
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
