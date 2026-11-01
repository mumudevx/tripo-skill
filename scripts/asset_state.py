#!/usr/bin/env python3
"""Per-asset state and the credit ledger under <project>/.claude/tripo/.

  asset_state.py new <project> <id> --class C [--placeholder-scene S --placeholder-node N]
                                    [--brief JSON] [--ref PATH ...] [--confirm-gdignore]
  asset_state.py get <project> <id>
  asset_state.py update <project> <id> [--phase P] [--set KEY=JSON ...] [--append KEY=JSON ...]
                                       [--chain-update LABEL=JSON ...]
  asset_state.py ledger <project> [--asset ID] [--add JSON]

Files: assets/<id>.json (schema asset/1) and ledger.jsonl (append-only, one row per paid step
estimate/result). A file with another schema is never touched or migrated silently: `get` and
`update` exit 5 with "migrate": true (older) so the caller can migrate it deliberately.

chain entries are valid input for `tripo_plan.py --chain`: kind uses the tripo_plan.KINDS spelling
(rig_check, never rig-check) and params is the dict that was passed to the planner.
A raw result the user supplied (no paid step in this session) is a chain entry with
"source": "user-supplied": it needs "file" (the frozen copy under raw/<label>/), its status is
"done", its credits 0 (null is filled in as 0), and task_id stays null unless the user gave it.
It never gets a ledger row. Entries without "source" are Tripo steps run by the skill.
Output: one JSON line. Exit codes: see common.py.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import tripo_plan  # noqa: E402

SCHEMA = "asset/1"
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
PHASES = ("brief", "preflight", "plan", "generate", "qa", "fix", "rig", "place", "lessons", "done")
CHAIN_STATUSES = ("planned", "running", "done", "failed")
CHAIN_KEYS = ("label", "task_id", "kind", "model", "credits", "status", "params")
CHAIN_OPTIONAL = ("source", "file")  # only present when given (user-supplied raw results)
CHAIN_SOURCES = ("tripo", "user-supplied")
SETTABLE = ("phase", "placeholder", "brief", "recipe")
APPENDABLE = ("refs", "qa", "decisions", "chain")
LEDGER_KEYS = ("ts", "asset", "label", "kind", "estimate", "consumed", "task_id")


class UsageError(Exception):
    pass


class NotFound(Exception):
    pass


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _opt_str(v):
    return v is None or (isinstance(v, str) and v != "")


def check_id(asset_id: str) -> str:
    if not ID_RE.fullmatch(asset_id or ""):
        raise UsageError(f"asset id must match [a-z0-9][a-z0-9_-]* (got {asset_id!r})")
    return asset_id


def asset_path(project: Path, asset_id: str) -> Path:
    return common.tripo_dir(project) / "assets" / f"{check_id(asset_id)}.json"


def ledger_path(project: Path) -> Path:
    return common.tripo_dir(project) / "ledger.jsonl"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def kind_of(raw) -> str:
    kind = raw.replace("-", "_") if isinstance(raw, str) else raw
    if kind not in tripo_plan.KINDS:
        raise UsageError(f"kind must be one of {', '.join(tripo_plan.KINDS)} (got {raw!r})")
    return kind


def chain_entry(raw) -> dict:
    """A validated, fully populated chain entry (defaults filled, kind normalised)."""
    if not isinstance(raw, dict):
        raise UsageError("a chain entry must be a JSON object")
    bad = sorted(set(raw) - set(CHAIN_KEYS) - set(CHAIN_OPTIONAL))
    if bad:
        raise UsageError(f"unknown chain keys: {', '.join(bad)} "
                         f"(allowed: {', '.join(CHAIN_KEYS + CHAIN_OPTIONAL)})")
    if not isinstance(raw.get("label"), str) or not raw["label"]:
        raise UsageError("a chain entry needs a label")
    e = {"label": raw["label"], "task_id": raw.get("task_id"), "kind": kind_of(raw.get("kind")),
         "model": raw.get("model"), "credits": raw.get("credits"),
         "status": raw.get("status", "planned"), "params": raw.get("params", {})}
    if not _opt_str(e["task_id"]) or not _opt_str(e["model"]):
        raise UsageError("task_id and model must be a string or null")
    if e["credits"] is not None and not (_num(e["credits"]) and e["credits"] >= 0):
        raise UsageError("credits must be a non-negative number or null")
    if e["status"] not in CHAIN_STATUSES:
        raise UsageError(f"status must be one of {', '.join(CHAIN_STATUSES)} (got {e['status']!r})")
    if not isinstance(e["params"], dict):
        raise UsageError("params must be an object (the dict passed to tripo_plan)")
    if "source" in raw:
        if raw["source"] not in CHAIN_SOURCES:
            raise UsageError(f"source must be one of {', '.join(CHAIN_SOURCES)} (got {raw['source']!r})")
        e["source"] = raw["source"]
    if "file" in raw:
        if not (isinstance(raw["file"], str) and raw["file"]):
            raise UsageError("file must be a path string (the frozen raw copy)")
        e["file"] = raw["file"]
    if e.get("source") == "user-supplied":
        if "file" not in e:
            raise UsageError("a user-supplied chain entry needs file: the frozen copy under raw/<label>/")
        if e["status"] == "planned" and "status" not in raw:
            e["status"] = "done"
        if e["status"] != "done":
            raise UsageError("a user-supplied chain entry is a finished result: status must be done")
        if e["credits"] is None:
            e["credits"] = 0
        if e["credits"] != 0:
            raise UsageError("a user-supplied chain entry cost nothing in this session: credits must be 0")
    return e


def load_asset(project: Path, asset_id: str) -> dict:
    path = asset_path(project, asset_id)
    if not path.is_file():
        raise NotFound(f"no asset {asset_id!r} at {path}; create it with `asset_state.py new`")
    return read_asset_file(path)


def read_asset_file(path: Path) -> dict:
    """An asset/1 file by path. Invalid JSON exits 4, another schema exits 5 (see load_asset)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        common.fail(common.EXIT_INTERNAL, f"{path} is not valid JSON: {e}")
    found = data.get("schema") if isinstance(data, dict) else None
    if found != SCHEMA:
        m = re.fullmatch(r"asset/(\d+)", found) if isinstance(found, str) else None
        newer = bool(m) and int(m.group(1)) > int(SCHEMA.split("/")[1])
        msg = (f"{path} has schema {found!r}, newer than {SCHEMA}; update the skill" if newer else
               f"{path} has schema {found!r}, expected {SCHEMA}; migrate it deliberately "
               f"(the script never rewrites an older file)")
        common.fail(common.EXIT_CHECK, msg, migrate=not newer, found=found, path=str(path))
    return data


def parse_kv(raw: str, what: str):
    key, sep, val = raw.partition("=")
    if not sep or not key:
        raise UsageError(f"{what} expects KEY=JSON (got {raw!r})")
    try:
        return key, json.loads(val)
    except ValueError as e:
        raise UsageError(f"{what} {key}: value is not valid JSON: {e}") from None


def _check_phase(phase):
    if phase not in PHASES:
        raise UsageError(f"phase must be one of {', '.join(PHASES)} (got {phase!r})")


def _check_placeholder(v):
    if v is not None and not (isinstance(v, dict) and set(v) == {"scene", "node"}
                              and all(isinstance(x, str) and x for x in v.values())):
        raise UsageError('placeholder must be null or {"scene": str, "node": str}')


def apply_set(asset: dict, key: str, val) -> None:
    top, *rest = key.split(".")
    if top not in SETTABLE:
        raise UsageError(f"cannot set {top!r}; settable: {', '.join(SETTABLE)} "
                         f"(chain/refs/qa/decisions use --append, chain entries --chain-update)")
    if not rest:
        if top == "phase":
            _check_phase(val)
        elif top == "placeholder":
            _check_placeholder(val)
        elif top == "brief" and not isinstance(val, dict):
            raise UsageError("brief must be an object")
        elif top == "recipe" and not _opt_str(val):
            raise UsageError("recipe must be a path string or null")
        asset[top] = val
        return
    if top not in ("brief", "placeholder"):
        raise UsageError(f"{top} has no nested keys")
    node = asset[top]
    for part in rest[:-1]:
        if not isinstance(node, dict) or not isinstance(node.get(part), dict):
            raise UsageError(f"{key}: {part!r} is not an object")
        node = node[part]
    if not isinstance(node, dict):
        raise UsageError(f"{key}: {top} is not an object (set it whole first)")
    node[rest[-1]] = val
    if top == "placeholder":
        _check_placeholder(asset[top])


def apply_append(asset: dict, key: str, val) -> None:
    if key not in APPENDABLE:
        raise UsageError(f"cannot append to {key!r}; appendable: {', '.join(APPENDABLE)}")
    if key == "chain":
        entry = chain_entry(val)
        if any(e["label"] == entry["label"] for e in asset["chain"]):
            raise UsageError(f"chain label {entry['label']!r} already exists; use --chain-update")
        val = entry
    elif key == "refs" and not (isinstance(val, str) and val):
        raise UsageError("a ref is a path string")
    asset[key].append(val)


def apply_chain_update(asset: dict, label: str, patch) -> None:
    if not isinstance(patch, dict):
        raise UsageError("--chain-update expects LABEL=<JSON object>")
    if "label" in patch:
        raise UsageError("a chain label cannot be changed")
    for i, e in enumerate(asset["chain"]):
        if e["label"] == label:
            asset["chain"][i] = chain_entry({**e, **patch})
            return
    raise NotFound(f"no chain entry labelled {label!r}")


def new_asset(a) -> dict:
    root = common.require_project(a.project)
    profile = common.load_profile(root)  # exits 3 naming `profile.py init` when missing
    asset_id = check_id(a.id)
    if a.cls not in profile["budgets"]:
        raise UsageError(f"unknown class {a.cls!r}; profile classes: {', '.join(profile['budgets'])}")
    if bool(a.placeholder_scene) != bool(a.placeholder_node):
        raise UsageError("--placeholder-scene and --placeholder-node go together")
    brief = json.loads(a.brief) if a.brief else {}
    if not isinstance(brief, dict):
        raise UsageError("--brief must be a JSON object")
    path = asset_path(root, asset_id)
    if path.exists():
        raise UsageError(f"asset {asset_id!r} exists at {path}; use `update`")
    asset = {"schema": SCHEMA, "id": asset_id, "class": a.cls, "phase": "brief",
             "placeholder": ({"scene": a.placeholder_scene, "node": a.placeholder_node}
                             if a.placeholder_scene else None),
             "brief": brief, "refs": list(a.ref or []), "chain": [], "qa": [], "recipe": None,
             "decisions": []}
    # repairs a profile made before init did it; before any write, so a refusal leaves nothing behind
    created = common.ensure_gdignore(root, profile, confirmed=a.confirm_gdignore)
    write_json(path, asset)
    return {"ok": True, "path": str(path), "asset": asset, "created": created,
            "warnings": common.gdignore_warnings(created)}


def update_asset(a) -> dict:
    root = common.require_project(a.project)
    asset = load_asset(root, a.id)
    if a.phase:
        apply_set(asset, "phase", a.phase)
    for raw in a.set or []:
        apply_set(asset, *parse_kv(raw, "--set"))
    for raw in a.append or []:
        apply_append(asset, *parse_kv(raw, "--append"))
    for raw in a.chain_update or []:
        apply_chain_update(asset, *parse_kv(raw, "--chain-update"))
    write_json(asset_path(root, a.id), asset)  # nothing is written when any operation above failed
    return {"ok": True, "path": str(asset_path(root, a.id)), "asset": asset}


def read_ledger(root: Path) -> list:
    path = ledger_path(root)
    if not path.is_file():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            common.fail(common.EXIT_INTERNAL, f"{path} line {n} is not valid JSON")
    return rows


def ledger(a) -> dict:
    root = common.require_project(a.project)
    if a.add:
        try:
            raw = json.loads(a.add)
        except ValueError as e:
            raise UsageError(f"--add is not valid JSON: {e}") from None
        if not isinstance(raw, dict):
            raise UsageError("--add expects a JSON object")
        bad = sorted(set(raw) - set(LEDGER_KEYS))
        if bad:
            raise UsageError(f"unknown ledger keys: {', '.join(bad)}")
        if not (isinstance(raw.get("label"), str) and raw["label"]):
            raise UsageError("a ledger row needs a label")
        if not _num(raw.get("estimate")) or raw["estimate"] < 0:
            raise UsageError("estimate must be a non-negative number")
        consumed = raw.get("consumed")
        if consumed is not None and not (_num(consumed) and consumed >= 0):
            raise UsageError("consumed must be a non-negative number or null")
        if not _opt_str(raw.get("task_id")):
            raise UsageError("task_id must be a string or null")
        if not asset_path(root, raw.get("asset")).is_file():
            raise NotFound(f"ledger row names asset {raw.get('asset')!r}, which has no asset file")
        chain = load_asset(root, raw["asset"]).get("chain", [])
        if any(e.get("label") == raw["label"] and e.get("source") == "user-supplied" for e in chain):
            raise UsageError(f"{raw['label']!r} is a user-supplied raw result: no credits were spent "
                             f"in this session, so it gets no ledger row")
        row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "asset": raw["asset"], "label": raw["label"], "kind": kind_of(raw.get("kind")),
               "estimate": raw["estimate"], "consumed": consumed, "task_id": raw.get("task_id")}
        path = ledger_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:  # O_APPEND: one write, one line
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        return {"ok": True, "path": str(path), "row": row}
    rows = read_ledger(root)
    if a.asset:
        rows = [r for r in rows if r.get("asset") == check_id(a.asset)]
    latest = {}  # a later row for the same (asset, label) supersedes the earlier one
    for r in rows:
        latest[(r.get("asset"), r.get("label"))] = r
    totals = {"estimate": sum(r.get("estimate") or 0 for r in latest.values()),
              "consumed": sum(r.get("consumed") or 0 for r in latest.values())}
    return {"ok": True, "rows": rows, "totals": totals}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        common.fail(common.EXIT_USAGE, f"usage: {message}")


def main(argv):
    p = Parser(prog="asset_state.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    n = sub.add_parser("new")
    n.add_argument("project")
    n.add_argument("id")
    n.add_argument("--class", dest="cls", required=True)
    n.add_argument("--placeholder-scene")
    n.add_argument("--placeholder-node")
    n.add_argument("--brief")
    n.add_argument("--ref", action="append")
    n.add_argument("--confirm-gdignore", action="store_true")
    g = sub.add_parser("get")
    g.add_argument("project")
    g.add_argument("id")
    u = sub.add_parser("update")
    u.add_argument("project")
    u.add_argument("id")
    u.add_argument("--phase")
    u.add_argument("--set", action="append")
    u.add_argument("--append", action="append")
    u.add_argument("--chain-update", action="append")
    le = sub.add_parser("ledger")
    le.add_argument("project")
    le.add_argument("--asset")
    le.add_argument("--add")
    a = p.parse_args(argv)
    try:
        if a.cmd == "new":
            out = new_asset(a)
        elif a.cmd == "get":
            root = common.require_project(a.project)
            out = {"ok": True, "path": str(asset_path(root, a.id)), "asset": load_asset(root, a.id)}
        elif a.cmd == "update":
            out = update_asset(a)
        else:
            out = ledger(a)
    except NotFound as e:
        common.fail(common.EXIT_NOT_FOUND, str(e))
    except (UsageError, ValueError) as e:
        common.fail(common.EXIT_USAGE, str(e))
    common.emit(out)
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
