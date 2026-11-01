#!/usr/bin/env python3
"""Provenance record and project asset_log row for one finished asset (spec B14).

  log_asset.py <project> <asset.json> [--create] [--license TEXT] [--cli-version V] [--state FILE]
               [--glb FILE] [--asset-path REL] [--kind K] [--notes TEXT] [--date YYYY-MM-DD]

Writes <art_source>/<kind>/<id>/provenance.json (schema provenance/1): tools, tripo-cli version,
wire model ids, Tripo tasks with credits, sha256 of every input reference (and of --glb, the
shipped model, when given), human edits (the ops of the asset's fix recipe) and the licence text.
`tasks` holds every chain entry that has a `source` or a `task_id`. A user-supplied raw result
(chain entry "source": "user-supplied", made outside this skill) is recorded with the sha256 and
size of its frozen copy (`file`, relative to the asset folder <art_source>/<kind>/<id>/ or to the
project), and `tools` (plus the top-level "generator" key) says it came from outside this skill.
Then appends one row to the project's asset_log in its own format and table:
  grime   | id | class | tool | date | prompt or source | license | notes |   (the "Models" table)
  patina  | asset_path | source_tool | plan/license | generation_date | prompt_ref | human_edited | notes |
  none    no log yet: exit 5 with "create_needed": true; with --create (the user agreed) the
          script creates docs/asset_log.md with the patina columns and adds the row.
Nothing is written unless both the provenance and the log row can be written.
Idempotent: when the log already has a row for this asset (grime: same id; patina: same
asset_path), no second row is added; provenance.json is refreshed and the output says
"already_logged": true.

kind: --kind, else brief.kind, else the asset class (the same folder the raw files use).
CLI version: --cli-version, else <skill>/.state.json cli_version (cli_watch.py), else the
profile's pinned.cli; the source is recorded. Licence: --license, else a Tripo default text
that tells the owner to confirm the terms (profile/1 has no licence key). When no chain entry has
a task_id (only user-supplied raws), the default says the plan and licence are unknown.
Missing inputs (a ref, the recipe, a user-supplied raw file, paths.art_source) stop the script
with exit 3 naming them.
Output: one JSON line. Exit codes: see common.py.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asset_state  # noqa: E402
import common  # noqa: E402

SCHEMA = "provenance/1"
GRIME_COLUMNS = ("id", "class", "tool", "date", "prompt or source", "license", "notes")
PATINA_COLUMNS = ("asset_path", "source_tool", "plan/license", "generation_date", "prompt_ref",
                  "human_edited", "notes")
GENERATOR_USER = "Tripo (user-supplied raw, outside this skill)"
LICENSE_UNKNOWN = "Tripo output supplied by the owner; plan and licence unknown — owner to confirm"
NEW_LOG = ("# Asset log\n\nOne row per generated or licensed asset: evidence for the store AI content "
           "disclosure and for licensing questions.\n\n")


class LogError(Exception):
    def __init__(self, code, msg, **extra):
        super().__init__(msg)
        self.code, self.extra = code, extra


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def project_file(root: Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() else root / p


def rel_or_abs(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def cell(text) -> str:
    """One markdown table cell: no newlines, '|' escaped."""
    return re.sub(r"\s*\n\s*", " ", str(text)).replace("|", r"\|").strip()


def header_cells(line: str) -> list:
    return [c.strip().strip("`").lower() for c in line.strip().strip("|").split("|")]


def find_table(lines: list, columns: tuple, prefer_heading=None):
    """(header index, index after the table's last row) of the first table whose header matches
    `columns`; tables under a heading containing `prefer_heading` win."""
    found, heading = [], ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
        if line.lstrip().startswith("|") and tuple(header_cells(line)) == columns:
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            found.append((heading, i, j))
            i = j
            continue
        i += 1
    if not found:
        return None
    if prefer_heading:
        for heading, start, end in found:
            if prefer_heading in heading:
                return start, end
    return found[0][1], found[0][2]


def load_recipe(root: Path, asset: dict) -> list:
    if not asset.get("recipe"):
        return []
    path = project_file(root, asset["recipe"])
    if not path.is_file():
        raise LogError(common.EXIT_NOT_FOUND, f"recipe {asset['recipe']} not found ({path}); fix the asset's "
                                              f"`recipe` with asset_state.py update")
    try:
        steps = json.loads(path.read_text(encoding="utf-8")).get("steps") or []
    except (ValueError, AttributeError) as e:
        raise LogError(common.EXIT_INTERNAL, f"recipe {path} is not a recipe JSON object: {e}")
    return [{"op": s.get("op"), "params": s.get("params", {})} for s in steps if isinstance(s, dict)]


def task_record(root: Path, asset_dir: Path, e: dict) -> dict:
    """One provenance task: a Tripo step run by the skill, or a user-supplied raw with the hash of
    its frozen copy (`file` is relative to the asset folder, else to the project)."""
    if e.get("source") != "user-supplied":
        rec = {k: e.get(k) for k in ("label", "kind", "model", "task_id", "credits", "status")}
        if e.get("source"):
            rec["source"] = e["source"]
        return rec
    raw = e.get("file")
    if not raw:
        raise LogError(common.EXIT_INTERNAL, f"user-supplied chain entry {e.get('label')!r} has no file")
    cands = [Path(raw).expanduser()] if Path(raw).expanduser().is_absolute() else [asset_dir / raw, root / raw]
    path = next((c for c in cands if c.is_file()), None)
    if path is None:
        raise LogError(common.EXIT_NOT_FOUND, f"user-supplied raw file {raw} not found (looked in "
                                              f"{', '.join(str(c) for c in cands)}); restore the frozen copy",
                       missing=[raw])
    return {"label": e.get("label"), "kind": e.get("kind"), "source": "user-supplied", "file": raw,
            "sha256": sha256_of(path), "bytes": path.stat().st_size, "model": e.get("model"),
            "task_id": e.get("task_id"), "credits": 0, "status": e.get("status")}


def task_text(t: dict) -> str:
    if t.get("source") == "user-supplied":
        extra = "".join(f", {k} {t[k]}" for k in ("model", "task_id") if t.get(k))
        return f"{t['kind']} user-supplied {t['file']} (sha256 {t['sha256'][:12]}{extra}, 0 credits)"
    return f"{t['kind']} {t['model'] or '-'} task {t['task_id']} ({t['credits']} credits)"


def cli_version(a, profile):
    if a.cli_version:
        return a.cli_version, "arg"
    state = common.state_read(a.state).get("cli_version")
    if state:
        return state, "state"
    return profile["pinned"]["cli"], "profile"


def build(a, root: Path, profile: dict, asset: dict) -> dict:
    art = profile["paths"].get("art_source")
    if not art:
        raise LogError(common.EXIT_NOT_FOUND, "profile paths.art_source is not set; set it with `profile.py init "
                                              f"{root} --answers '{{\"paths\": {{\"art_source\": ...}}}}' --force`")
    kind = a.kind or (asset.get("brief") or {}).get("kind") or asset["class"]
    missing = [r for r in asset.get("refs", []) if not project_file(root, r).is_file()]
    if missing:
        raise LogError(common.EXIT_NOT_FOUND, f"reference file(s) not found: {', '.join(missing)}; "
                                              f"restore them or fix the asset's refs", missing=missing)
    inputs = [{"path": r, "sha256": sha256_of(project_file(root, r)),
               "bytes": project_file(root, r).stat().st_size} for r in asset.get("refs", [])]
    output = None
    if a.glb:
        glb = project_file(root, a.glb)
        if not glb.is_file():
            raise LogError(common.EXIT_NOT_FOUND, f"model not found: {a.glb}")
        output = {"path": rel_or_abs(root, glb), "sha256": sha256_of(glb), "bytes": glb.stat().st_size}
    edits = load_recipe(root, asset)
    version, version_src = cli_version(a, profile)
    asset_dir = root / art / kind / asset["id"]
    tasks = [task_record(root, asset_dir, e) for e in asset.get("chain", [])
             if e.get("source") or e.get("task_id")]
    models = list(dict.fromkeys(t["model"] for t in tasks if t["model"]))
    by_skill = [t for t in tasks if t.get("source") != "user-supplied"]
    user = [t for t in tasks if t.get("source") == "user-supplied"]
    tools = (([f"tripo-cli {version}"] if by_skill or not user else [])
             + ([GENERATOR_USER] if user else [])
             + (["Blender (fix recipe)"] if edits else []))
    if a.license:
        license_text = a.license
    elif not any(t.get("task_id") for t in tasks):
        license_text = LICENSE_UNKNOWN
    else:
        license_text = (f"Tripo paid credits (tripo-cli {version}); commercial use per the Tripo terms "
                        f"at generation time; owner to confirm")
    today = a.date or date.today().isoformat()
    prov_path = asset_dir / "provenance.json"
    return {"schema": SCHEMA, "id": asset["id"], "class": asset["class"], "kind": kind, "date": today,
            "tools": tools, "generator": GENERATOR_USER if user else None, "cli_version": version,
            "cli_version_source": version_src, "models": models,
            "tasks": tasks, "credits_total": sum(t["credits"] or 0 for t in tasks), "inputs": inputs,
            "output": output, "prompt": (asset.get("brief") or {}).get("prompt"),
            "human_edits": edits, "recipe": asset.get("recipe"), "license": license_text,
            "license_source": "arg" if a.license else "default", "_path": prov_path}


def row_for(fmt: str, prov: dict, root: Path, asset_path: str, notes: str) -> list:
    tasks = "; ".join(task_text(t) for t in prov["tasks"])
    ops = ", ".join(e["op"] for e in prov["human_edits"])
    prov_rel = rel_or_abs(root, prov["_path"])
    refs = ", ".join(i["path"] for i in prov["inputs"])
    user = any(t.get("source") == "user-supplied" for t in prov["tasks"])
    by_skill = any(t.get("source") != "user-supplied" for t in prov["tasks"])
    if fmt == "grime":
        if user and not by_skill:
            tool = GENERATOR_USER + (f", {' → '.join(prov['models'])}" if prov["models"] else "")
        else:
            tool = "Tripo " + " → ".join(prov["models"] or ["?"]) + f" (tripo-cli {prov['cli_version']})"
            if user:
                tool += f" + {GENERATOR_USER}"
        if ops:
            tool += " + Blender fix recipe"
        source = "; ".join(x for x in (f'"{prov["prompt"]}"' if prov["prompt"] else "",
                                       f"refs: {refs}" if refs else "", tasks) if x)
        extra = "; ".join(x for x in (f"human edits: {ops}" if ops else "no human edits",
                                      f"provenance: {prov_rel}", notes) if x)
        cells = [prov["id"], prov["class"], tool, prov["date"], source or "-", prov["license"], extra]
    else:
        steps = ", ".join(f"`{t['model']}` ({t['kind']})" for t in prov["tasks"] if t["model"])
        base = GENERATOR_USER if user and not by_skill else f"Tripo CLI {prov['cli_version']}"
        if user and by_skill:
            base += f" + {GENERATOR_USER}"
        tool = base + (f", {steps}" if steps else "")
        prompt_ref = "; ".join(x for x in (f"`{prov_rel}`", f"refs: {refs}" if refs else "") if x)
        extra = "; ".join(x for x in (tasks, notes) if x)
        cells = [f"`{asset_path}`", tool, prov["license"], prov["date"], prompt_ref,
                 f"yes ({ops})" if ops else "no", extra or "-"]
    return [cell(c) for c in cells]


def plan_log(a, root: Path, profile: dict):
    """(log path, format, current text or None, warnings) after checking the row can be written."""
    fmt = profile["asset_log_format"]
    rel = profile["paths"].get("asset_log") or "docs/asset_log.md"
    path = root / rel
    if fmt == "none":
        if path.is_file():  # e.g. started by an earlier --create; the profile still says none
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            found = next((f for f, cols in (("patina", PATINA_COLUMNS), ("grime", GRIME_COLUMNS))
                          if find_table(lines, cols)), None)
            if found is None:
                raise LogError(common.EXIT_CHECK, f"{rel} exists in a format this skill does not know; add the row "
                                                  f"by hand or set asset_log_format in the profile")
            return path, found, text, [f"profile asset_log_format is none but {rel} has the {found} columns; "
                                       f"set asset_log_format to {found} in the profile"]
        if path.exists():
            raise LogError(common.EXIT_CHECK, f"{rel} exists and is not a file")
        if not a.create:
            raise LogError(common.EXIT_CHECK, f"the project has no asset log; ask the user, then re-run with "
                                              f"--create to start {rel} (patina columns)", create_needed=True)
        return path, "patina", None, [f"created {rel}; set asset_log_format to patina and paths.asset_log "
                                      f"to {rel} in the profile"]
    if not path.is_file():
        raise LogError(common.EXIT_NOT_FOUND, f"asset log {rel} not found (profile asset_log_format {fmt}); "
                                              f"restore it or re-run profile.py init --force")
    return path, fmt, path.read_text(encoding="utf-8"), []


def existing_row(fmt: str, text, key: str):
    """Cells of the row already logged for `key` (grime: id, patina: asset_path), or None."""
    if text is None or not key:
        return None
    lines = text.splitlines()
    hit = find_table(lines, GRIME_COLUMNS if fmt == "grime" else PATINA_COLUMNS, "model" if fmt == "grime" else None)
    if hit is None:
        return None
    for line in lines[hit[0] + 1:hit[1]]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if cells and set(line.strip()) - set("|-: ") and cells[0].strip("`") == key:
            return cells
    return None


def insert_row(fmt: str, text, row: list) -> str:
    line = "| " + " | ".join(row) + " |"
    if text is None:
        head = "| " + " | ".join(PATINA_COLUMNS) + " |\n|" + "---|" * len(PATINA_COLUMNS) + "\n"
        return NEW_LOG + head + line + "\n"
    lines = text.splitlines()
    columns, prefer = (GRIME_COLUMNS, "model") if fmt == "grime" else (PATINA_COLUMNS, None)
    hit = find_table(lines, columns, prefer)
    if hit is None:
        raise LogError(common.EXIT_CHECK, f"the asset log has no table with the {fmt} columns ({' | '.join(columns)})")
    lines.insert(hit[1], line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        common.fail(common.EXIT_USAGE, f"usage: {message}")


def main(argv) -> int:
    p = Parser(prog="log_asset.py")
    p.add_argument("project")
    p.add_argument("asset")
    p.add_argument("--create", action="store_true", help="start docs/asset_log.md when the project has none")
    p.add_argument("--license")
    p.add_argument("--cli-version")
    p.add_argument("--state", help="skill state file (default <skill>/.state.json)")
    p.add_argument("--glb", help="the shipped model, hashed into provenance")
    p.add_argument("--asset-path", help="model path for the patina asset_path column (default: profile naming)")
    p.add_argument("--kind")
    p.add_argument("--notes", default="")
    p.add_argument("--date")
    a = p.parse_args(argv)
    root = common.require_project(a.project)
    profile = common.load_profile(root)
    asset_file = Path(a.asset).expanduser()
    if not asset_file.is_file():
        common.fail(common.EXIT_NOT_FOUND, f"asset file not found: {a.asset}")
    asset = asset_state.read_asset_file(asset_file)
    for key in ("id", "class"):
        if not asset.get(key):
            common.fail(common.EXIT_CHECK, f"{asset_file} has no {key!r}; it is not a complete asset/1 file")
    try:
        log_path, fmt, text, warnings = plan_log(a, root, profile)
        prov = build(a, root, profile, asset)
        asset_path = a.asset_path or (common.model_dest(profile, asset["id"], asset["class"])
                                      if fmt == "patina" else None)
        row = row_for(fmt, prov, root, asset_path, a.notes)
        logged = existing_row(fmt, text, asset["id"] if fmt == "grime" else asset_path)
        new_text = text if logged else insert_row(fmt, text, row)
    except LogError as e:
        common.fail(e.code, str(e), **e.extra)
    if logged:
        row = logged
        warnings = warnings + [f"{rel_or_abs(root, log_path)} already has a row for this asset; no second row "
                               f"added (edit it by hand if it must change)"]
    prov_path = prov.pop("_path")
    prov["asset_log"] = {"path": rel_or_abs(root, log_path), "format": fmt, "row": row}
    write_text(prov_path, json.dumps(prov, ensure_ascii=False, indent=2) + "\n")
    if not logged:
        write_text(log_path, new_text)
    common.emit({"ok": True, "provenance": str(prov_path), "asset_log": str(log_path), "format": fmt,
                 "created": text is None, "already_logged": bool(logged), "row": row, "warnings": warnings})
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
