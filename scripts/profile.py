#!/usr/bin/env python3
"""Project profile: detect what a Godot project already tells us, then write
<project>/.claude/tripo/profile.json (schema profile/1, see references/profile-schema.md).

  profile.py detect <project>                       proposed profile + "unknown": [keys to ask]
  profile.py init <project> --answers <json|file|-> [--force]

`detect` never writes. `init` merges the answers over the detected values, validates the result
and writes it; it refuses to overwrite an existing profile without --force.
Output: one JSON line. Exit codes: see common.py (2 usage/invalid answers, 3 input not found).

Note: this file shadows the stdlib `profile` module whenever scripts/ is first on sys.path.
Nothing in the skill imports the stdlib one; load this file by path if that ever matters.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

BUDGETS = Path(__file__).resolve().parent / "data" / "budgets.json"
MAC_GODOT = "/Applications/Godot.app/Contents/MacOS/Godot"
RENDERER_FEATURES = {"forward plus": "forward_plus", "mobile": "mobile",
                     "gl compatibility": "gl_compatibility"}
# export_presets.cfg platform name -> budget platform. Web and Quest share the mobile column.
PLATFORM_OF = {"windows desktop": "pc", "macos": "pc", "linux": "pc",
               "android": "mobile", "ios": "mobile", "web": "mobile"}
PLATFORMS = ("pc", "mobile")
ASSET_LOG_FORMATS = ("grime", "patina", "none")
PLACEMENT_MODES = ("scene_swap", "generator_script")
DEFAULT_PINNED = {"cli": "0.9.0", "gen_model": "v3.1-20260211",
                  "texture_model": "v3.0-20250812", "rig_model": "v3.0-20250812"}

# section -> allowed keys (a typo in an answer is an error, never silently dropped)
SECTIONS = {
    "engine": ("name", "version", "binary"),
    "naming": ("model_pattern", "root"),
    "paths": ("art_source", "models", "asset_log"),
    "pinned": tuple(DEFAULT_PINNED),
}
TOP_KEYS = ("schema", "engine", "renderer", "platforms", "art_style", "pbr", "game_camera",
            "texel_density", "budgets", "naming", "paths", "asset_log_format", "placement_mode",
            "pinned", "check_commands")


class AnswerError(Exception):
    pass


def load_budget_table() -> dict:
    return json.loads(BUDGETS.read_text(encoding="utf-8"))["classes"]


def budgets_for(platforms) -> dict:
    """Per class triangle budget for the given platforms (the tightest wins; pc when none)."""
    cols = [p for p in (platforms or ["pc"]) if p in PLATFORMS] or ["pc"]
    return {cls: min(row[c] for c in cols) for cls, row in load_budget_table().items()}


# ---------- detection ----------

def _godot_features(text: str) -> list:
    m = re.search(r"^config/features=PackedStringArray\((.*)\)\s*$", text, re.M)
    return re.findall(r'"([^"]*)"', m.group(1)) if m else []


def detect_engine(root: Path, text: str):
    feats = _godot_features(text)
    version = next((f for f in feats if re.fullmatch(r"\d+\.\d+(\.\d+)?", f)), None)
    m = re.search(r'^renderer/rendering_method="([^"]+)"', text, re.M)
    renderer = m.group(1) if m else next(
        (RENDERER_FEATURES[f.lower()] for f in feats if f.lower() in RENDERER_FEATURES), None)
    return version, renderer


def detect_binary(root: Path):
    """Godot binary: the path scripts/godot_bin.sh pins, else `godot` on PATH, else the macOS app."""
    sh = root / "scripts" / "godot_bin.sh"
    if sh.is_file():
        m = re.search(r"""["'](/[^"'\n]*Godot[^"'\n]*)["']""", sh.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return shutil.which("godot") or (MAC_GODOT if os.access(MAC_GODOT, os.X_OK) else None)


def detect_platforms(root: Path) -> list:
    cfg = root / "export_presets.cfg"
    if not cfg.is_file():
        return []
    names = re.findall(r'^platform="([^"]+)"', cfg.read_text(encoding="utf-8", errors="replace"), re.M)
    found = {PLATFORM_OF[n.lower()] for n in names if n.lower() in PLATFORM_OF}
    return [p for p in PLATFORMS if p in found]


def detect_asset_log(root: Path):
    """(relative path or None, format). An unrecognised existing log gets format 'none'."""
    rel = "docs/asset_log.md"
    path = root / rel
    if not path.is_file():
        return None, "none"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("|"):
            cols = [c.strip().strip("`").lower() for c in line.strip().strip("|").split("|")]
            if "asset_path" in cols:
                return rel, "patina"
            if cols[:2] == ["id", "class"]:
                return rel, "grime"
            break
    return rel, "none"


def detect(root: Path) -> tuple:
    warnings = []
    text = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
    version, renderer = detect_engine(root, text)
    binary = detect_binary(root)

    art_source = None
    for cand in ("art_src", "art_source"):
        if (root / cand).is_dir():
            if (root / cand / ".gdignore").is_file():
                art_source = cand
                break
            warnings.append(f"{cand}/ exists without {cand}/.gdignore: Godot would import it; "
                            f"add the .gdignore or pick another source folder")
    models = "assets/models" if (root / "assets" / "models").is_dir() else None
    log_path, log_format = detect_asset_log(root)

    checks = []
    if (root / "scripts" / "check_import.sh").is_file():
        checks.append("bash scripts/check_import.sh")
    if (root / ".gutconfig.json").is_file():
        checks.append(f"{shlex.quote(binary or 'godot')} --headless --path . -s res://addons/gut/gut_cmdln.gd "
                      f"-gconfig=res://.gutconfig.json -gexit")

    platforms = detect_platforms(root)
    generators = list((root / "scripts" / "dev").glob("generate_*_models.gd"))
    profile = {
        "schema": common.PROFILE_SCHEMA,
        "engine": {"name": "godot", "version": version, "binary": binary},
        "renderer": renderer,
        "platforms": platforms,
        "art_style": None,
        "pbr": False,
        "game_camera": None,
        "texel_density": None,
        "budgets": budgets_for(platforms),
        "naming": {"model_pattern": None, "root": models},
        "paths": {"art_source": art_source, "models": models, "asset_log": log_path},
        "asset_log_format": log_format,
        "placement_mode": "generator_script" if generators else "scene_swap",
        "pinned": dict(DEFAULT_PINNED),
        "check_commands": checks,
    }
    return profile, warnings


def unknown_keys(p: dict) -> list:
    """Keys the project could not tell us and the user has to answer (null or empty values)."""
    checks = [("engine.version", p["engine"]["version"]), ("engine.binary", p["engine"]["binary"]),
              ("renderer", p["renderer"]), ("platforms", p["platforms"]),
              ("art_style", p["art_style"]), ("game_camera", p["game_camera"]),
              ("texel_density", p["texel_density"]), ("naming.model_pattern", p["naming"]["model_pattern"]),
              ("paths.art_source", p["paths"]["art_source"]), ("paths.models", p["paths"]["models"])]
    out = [k for k, v in checks if v is None or v == []]
    if p["paths"]["asset_log"] is not None and p["asset_log_format"] == "none":
        out.append("asset_log_format")
    return out


# ---------- answers ----------

def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _opt_str(v):
    return v is None or (isinstance(v, str) and v != "")


def _rel_path(v):
    if v is None:
        return True
    pure = Path(v) if isinstance(v, str) else None
    return pure is not None and v != "" and not pure.is_absolute() and ".." not in pure.parts


def validate(p: dict) -> None:
    def need(ok, msg):
        if not ok:
            raise AnswerError(msg)

    need(p.get("schema") == common.PROFILE_SCHEMA, f"schema must be {common.PROFILE_SCHEMA!r}")
    need(set(p) == set(TOP_KEYS), f"keys must be exactly {', '.join(TOP_KEYS)}")
    for sec, keys in SECTIONS.items():
        need(isinstance(p[sec], dict) and set(p[sec]) == set(keys),
             f"{sec} must be an object with keys {', '.join(keys)}")
    need(isinstance(p["engine"]["name"], str) and p["engine"]["name"], "engine.name must be a non-empty string")
    for k in ("version", "binary"):
        need(_opt_str(p["engine"][k]), f"engine.{k} must be a string or null")
    need(_opt_str(p["renderer"]), "renderer must be a string or null")
    need(isinstance(p["platforms"], list) and all(x in PLATFORMS for x in p["platforms"]),
         f"platforms must be a list of {', '.join(PLATFORMS)}")
    need(_opt_str(p["art_style"]), "art_style must be a string or null")
    need(isinstance(p["pbr"], bool), "pbr must be true or false")
    cam = p["game_camera"]
    need(cam is None or (isinstance(cam, dict) and set(cam) == {"yaw", "pitch", "fov"}
                         and all(_is_num(v) for v in cam.values())),
         "game_camera must be null or {yaw, pitch, fov} numbers")
    need(p["texel_density"] is None or (_is_num(p["texel_density"]) and p["texel_density"] > 0),
         "texel_density must be a positive number or null")
    need(isinstance(p["budgets"], dict) and p["budgets"] and all(
        isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v > 0
        for k, v in p["budgets"].items()), "budgets must map class names to positive integers")
    for k in ("model_pattern", "root"):
        need(_opt_str(p["naming"][k]), f"naming.{k} must be a string or null")
    for k in SECTIONS["paths"]:
        need(_rel_path(p["paths"][k]), f"paths.{k} must be a relative path inside the project or null")
    need(p["asset_log_format"] in ASSET_LOG_FORMATS, f"asset_log_format must be one of {', '.join(ASSET_LOG_FORMATS)}")
    need(p["placement_mode"] in PLACEMENT_MODES, f"placement_mode must be one of {', '.join(PLACEMENT_MODES)}")
    for k, v in p["pinned"].items():
        need(isinstance(v, str) and v, f"pinned.{k} must be a non-empty string")
    need(isinstance(p["check_commands"], list) and all(isinstance(c, str) and c for c in p["check_commands"]),
         "check_commands must be a list of strings")


def apply_answers(base: dict, answers: dict) -> dict:
    """Merge `answers` over the detected profile. Sections merge key by key, everything else
    replaces. Budgets are re-derived from the final platforms, then explicit answers overlay."""
    if not isinstance(answers, dict):
        raise AnswerError("answers must be a JSON object")
    unknown = sorted(set(answers) - set(TOP_KEYS))
    if unknown:
        raise AnswerError(f"unknown answer keys: {', '.join(unknown)} (allowed: {', '.join(TOP_KEYS)})")
    if "schema" in answers and answers["schema"] != common.PROFILE_SCHEMA:
        raise AnswerError(f"schema must be {common.PROFILE_SCHEMA!r}")
    merged = json.loads(json.dumps(base))
    for key, val in answers.items():
        if key == "budgets":
            continue
        if key in SECTIONS:
            if not isinstance(val, dict):
                raise AnswerError(f"{key} must be an object")
            bad = sorted(set(val) - set(SECTIONS[key]))
            if bad:
                raise AnswerError(f"unknown keys in {key}: {', '.join(bad)}")
            merged[key].update(val)
        else:
            merged[key] = val
    if "platforms" in answers and isinstance(merged["platforms"], list):
        merged["budgets"] = budgets_for(merged["platforms"])
    if "budgets" in answers:
        if not isinstance(answers["budgets"], dict):
            raise AnswerError("budgets must be an object")
        merged["budgets"].update(answers["budgets"])
    if "root" not in answers.get("naming", {}) and merged["naming"]["root"] is None:
        merged["naming"]["root"] = merged["paths"]["models"]
    validate(merged)
    return merged


# ---------- CLI ----------

class Parser(argparse.ArgumentParser):
    def error(self, message):
        common.fail(common.EXIT_USAGE, f"usage: {message}")


def read_answers(raw: str):
    if raw == "-":
        text = sys.stdin.read()
    elif raw.lstrip().startswith("{"):
        text = raw
    else:
        path = Path(raw).expanduser()
        if not path.is_file():
            common.fail(common.EXIT_NOT_FOUND, f"answers file not found: {raw}")
        text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except ValueError as e:
        common.fail(common.EXIT_USAGE, f"answers are not valid JSON: {e}")


def write_profile(path: Path, profile: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main(argv):
    p = Parser(prog="profile.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    d = sub.add_parser("detect")
    d.add_argument("project")
    i = sub.add_parser("init")
    i.add_argument("project")
    i.add_argument("--answers", required=True)
    i.add_argument("--force", action="store_true")
    a = p.parse_args(argv)

    root = common.require_project(a.project)
    profile, warnings = detect(root)
    if a.cmd == "detect":
        common.emit({"ok": True, "project": str(root), "profile": profile,
                     "unknown": unknown_keys(profile), "warnings": warnings})
        return common.EXIT_OK

    path = common.profile_path(root)
    if path.exists() and not a.force:
        common.fail(common.EXIT_USAGE, f"{path} exists; pass --force to overwrite it")
    try:
        profile = apply_answers(profile, read_answers(a.answers))
    except AnswerError as e:
        common.fail(common.EXIT_USAGE, f"invalid answers: {e}")
    write_profile(path, profile)
    common.emit({"ok": True, "project": str(root), "path": str(path), "profile": profile,
                 "unknown": unknown_keys(profile), "warnings": warnings})
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
