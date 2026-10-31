"""Importable name for _io.py (`import _io` always yields Python's built-in module).

Usage in any script under scripts/blender/:  import skill_io as sio
Loads _io.py by path and re-exports its public names.
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "tripo_blender_io", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_io.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

args = _mod.args
write = _mod.write
main = _mod.main
load_model = _mod.load_model
clear_scene = _mod.clear_scene
sniff = _mod.sniff
