"""Shared test helpers: fixture registry, skip helper, script import path."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures.json"
BLENDER = os.environ.get("BLENDER", "/opt/homebrew/bin/blender")

# make `import common`, `import glbstat`, ... work from any test module
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def fixture(name: str) -> Path:
    """Absolute path registered under `name` in tests/fixtures.json."""
    table = json.loads(FIXTURES.read_text())
    if name not in table or name.startswith("_"):
        raise KeyError(f"unknown fixture {name!r}")
    return Path(table[name])


def skip_if_missing(path) -> None:
    """Skip the running test when a fixture path does not exist on this machine."""
    if not Path(path).exists():
        raise unittest.SkipTest(f"fixture not available: {path}")


def tmpdir(prefix: str = "tripo-test-") -> Path:
    """A fresh temp dir (caller removes it, e.g. via addCleanup(shutil.rmtree, d))."""
    return Path(tempfile.mkdtemp(prefix=prefix))
