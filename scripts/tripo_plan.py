#!/usr/bin/env python3
"""Single-step Tripo planner: build one command, validate it with a zero-credit
dry-run, price it.

    tripo_plan.py <step> [--chain <asset.json>] [--build]

<step> is a JSON file, '-' for stdin, or inline JSON starting with '{':

    {"kind": "generate", "label": "mailbox-generate-v01",
     "input": {"images": ["front.png"]}, "model": "tripo-v3.1",
     "params": {"texture_version": "v3.5", "delight": true}}

kind: generate | texture | decimate | uv | segment | smartsegment | complete |
convert | rig_check | rig | retarget | image_to_multiview | edit_multiview.
input: {"images": [...]} | {"prompt": "..."} | {"task": "<task_id|@label>"} | {"file": path}.
model: required for generate, decimate, rig and texture. params: API parameters.
name: overrides --name (default: label). candidates: must be 1.

Prints {"ok", "argv", "ref", "dry_run", "estimate": {"credits", "source"}, "warnings",
"errors", "paid"}; with --build only {"ok", "argv", "ref"} (no CLI call). `ref` is the
@reference of the task the step produces: make names a chain step <name>-<step>.
Exit 0 clean, 2 malformed step, 3 input file not found, 4 tripo CLI missing or
broken, 5 the step breaks a rule (errors is non-empty).

Only `tripo make ... --dry-run --json` and `tripo models --json` are ever run.
The tripo binary is $TRIPO, else `tripo` on PATH.
"""
import argparse
import copy
import functools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PRICES = Path(__file__).resolve().parent / "data" / "prices.json"

KINDS = ("generate", "texture", "decimate", "uv", "segment", "smartsegment", "complete",
         "convert", "rig_check", "rig", "retarget", "image_to_multiview", "edit_multiview")
NEEDS_MODEL = {"generate", "decimate", "rig", "texture"}
# kinds that run as one `tripo make <src> --then <step>` (the only form with a dry-run)
THEN_STEP = {"texture": "texture", "decimate": "decimate", "uv": "uv", "segment": "segment",
             "complete": "complete", "convert": "convert", "rig_check": "rig-check",
             "rig": "rig", "retarget": "retarget"}
# kinds the make chain cannot express: direct commands, no dry-run
DIRECT = {"image_to_multiview": ["generate", "image-to-multiview"],
          "edit_multiview": ["generate", "edit-multiview"],
          "smartsegment": ["mesh", "smartsegment"]}
# kind -> capability prefix in `tripo models --json`
MODEL_CAPABILITY = {"generate": "3d-generation", "texture": "texture", "rig": "rig",
                    "decimate": "decimate", "segment": "segment"}
INPUTS = {"generate": ("images", "prompt"), "image_to_multiview": ("images",),
          "edit_multiview": ("task",), "smartsegment": ("file",)}
THEN_INPUTS = ("task", "file")

RIG_TYPES = ("biped", "quadruped", "hexapod", "octopod", "avian", "serpentine", "aquatic",
             "others")
RIG_SPECS = ("tripo", "mixamo", "actorcore", "unity", "unreal", "vrm")
LOCAL_ONLY = ("orientation", "export_orientation", "auto_size")
QUAD_BLOCKED = ("GLB", "GLTF")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# pricing page: a non-default value of any of these (or any face_limit) bills advanced convert
COMPLEX_CONVERT_DEFAULTS = {"quad": False, "flatten_bottom": False,
                            "flatten_bottom_threshold": 0.01, "texture_size": 4096,
                            "texture_format": "JPEG", "pivot_to_center_bottom": False,
                            "scale_factor": 1}
DRY_RUN_TIMEOUT = 60


class PlanError(Exception):
    """The step cannot be turned into a command (exit 2)."""


class InputNotFound(PlanError):
    """A local input file does not exist (exit 3)."""


class TripoCliError(Exception):
    """The tripo CLI is missing, timed out or printed no usable JSON (exit 4)."""


# ---------- tripo CLI ----------

def tripo_bin():
    """Path of the tripo binary: $TRIPO, else `tripo` on PATH, else None."""
    env = os.environ.get("TRIPO")
    if env:
        return env if os.path.isfile(env) and os.access(env, os.X_OK) else None
    return shutil.which("tripo")


def _run_tripo(args, timeout):
    exe = tripo_bin()
    if exe is None:
        raise TripoCliError("tripo CLI not found: set $TRIPO or put tripo on PATH")
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise TripoCliError(f"tripo {args[0]} timed out after {timeout}s") from None
    except OSError as e:
        raise TripoCliError(f"cannot run {exe}: {e}") from None
    return p.returncode, p.stdout, p.stderr


def _last_json(text):
    for line in reversed(text.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


@functools.lru_cache(maxsize=None)
def _models():
    code, out, err = _run_tripo(["models", "--json"], 20)
    data = _last_json(out)
    if code != 0 or not isinstance(data, list):
        raise TripoCliError(f"`tripo models --json` failed (exit {code}): {err.strip()[-300:]}")
    return tuple(data)


def wire_id(kind, model):
    """Wire id for `model` in the capability `kind` uses, via `tripo models --json`; None if unknown."""
    cap = MODEL_CAPABILITY[kind]
    want = str(model).strip().lower()
    for entry in _models():
        if not str(entry.get("capability", "")).startswith(cap):
            continue
        for m in entry.get("models", []):
            if want in [m["id"].lower(), *(a.lower() for a in m.get("aliases", []))]:
                return m["id"]
    return None


def dry_run(argv):
    """Run `argv` (a `tripo make ...` command) with --dry-run. Returns (result, error).
    --dry-run goes right after `make`, so no later token (a value option missing its
    value, `--`) can swallow it and submit a paid task (M1)."""
    if len(argv) < 2 or argv[1] != "make":
        raise ValueError(f"dry_run needs a `tripo make` argv, got {argv[:2]}")
    code, out, err = _run_tripo(["make", "--dry-run", *argv[2:]], DRY_RUN_TIMEOUT)
    data = _last_json(out)
    if code in (0, 2) and isinstance(data, dict) and data.get("dry_run") is True:
        return data, None
    return None, f"tripo dry-run gave no plan (exit {code}): {err.strip()[-300:] or out.strip()[-300:]}"


# ---------- step shape and rules ----------

def _truthy(v):
    return v is True or (isinstance(v, str) and v.strip().lower() == "true")


def _label_ok(label, kind):
    kinds = {re.escape(kind), re.escape(kind.replace("_", "-"))}
    return re.fullmatch(rf"[a-z0-9][a-z0-9_-]*-(?:{'|'.join(kinds)})-v\d{{2,}}", label) is not None


def _local_path(raw, what):
    if not isinstance(raw, str) or not raw.strip():
        raise PlanError(f"{what} must be a non-empty path")
    path = os.path.abspath(os.path.expanduser(raw))
    if not os.path.isfile(path):
        raise InputNotFound(f"{what} not found: {raw}")
    return path


def _shape(step):
    """Deep copy of `step` with defaults filled and paths resolved; raises PlanError."""
    if not isinstance(step, dict):
        raise PlanError("step must be a JSON object")
    s = copy.deepcopy(step)
    kind = s.get("kind")
    if kind not in KINDS:
        raise PlanError(f"kind must be one of {', '.join(KINDS)} (got {kind!r})")
    label = s.get("label")
    if not isinstance(label, str) or not _label_ok(label, kind):
        raise PlanError(f"label is required as <asset>-{kind}-vNN (got {label!r})")
    if s.get("name") is not None and (not isinstance(s["name"], str) or not s["name"].strip()):
        raise PlanError("name must be a non-empty string")
    if kind in NEEDS_MODEL and not (isinstance(s.get("model"), str) and s["model"].strip()):
        raise PlanError(f"{kind} needs an explicit model (B10)")
    if s.get("model") is not None and not isinstance(s["model"], str):
        raise PlanError("model must be a string")
    s["params"] = s.get("params") or {}
    if not isinstance(s["params"], dict):
        raise PlanError("params must be an object")
    bad = [k for k in s["params"] if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(k))]
    if bad:
        raise PlanError(f"params keys must be identifiers (got {bad})")
    cand = s.pop("candidates", s.pop("n", None))
    s["candidates"] = 1 if cand is None else cand
    if not isinstance(s["candidates"], int) or isinstance(s["candidates"], bool):
        raise PlanError("candidates must be an integer")

    inp = s.get("input")
    allowed = INPUTS.get(kind, THEN_INPUTS)
    if not isinstance(inp, dict) or len(inp) != 1 or next(iter(inp)) not in allowed:
        raise PlanError(f"{kind} input must be one of {', '.join('{%r: ...}' % k for k in allowed)}")
    key, val = next(iter(inp.items()))
    if key == "images":
        limit = 1 if kind == "image_to_multiview" else 4
        if not isinstance(val, list) or not 1 <= len(val) <= limit:
            raise PlanError(f"{kind} takes 1-{limit} images")
        s["input"] = {"images": [_local_path(v, "image") for v in val]}
    elif key == "file":
        s["input"] = {"file": _local_path(val, "input file")}
    else:
        if not isinstance(val, str) or not val.strip():
            raise PlanError(f"input {key} must be a non-empty string")
        if key == "task" and any(c.isspace() for c in val.strip()):
            raise PlanError(f"input task must be a task id or @label (got {val!r})")
        if val.strip().startswith("-"):
            raise PlanError(f"input {key} must not start with '-' (got {val!r})")
        s["input"] = {key: val.strip()}
    return s


def _rules(step):
    """(shaped step, warnings, errors) for the rules that need no CLI call."""
    s = _shape(step)
    kind, p = s["kind"], s["params"]
    warnings, errors = [], []
    if "model" in p:
        errors.append("-p model= is not allowed: put the model in the step's 'model' key "
                      "(B10; on make it overrides --model and skips validation)")
    if s["candidates"] != 1:
        errors.append(f"candidates={s['candidates']}: -n must be 1, one paid task per approval (B17)")
    if kind == "generate":
        for key in LOCAL_ONLY:
            if key in p:
                del p[key]
                warnings.append(f"{key}: set locally instead (orientation and scale are fixed in "
                                "Blender against the placeholder); removed")
        if _truthy(p.get("generate_parts")):
            if _truthy(p.get("smart_low_poly")):
                errors.append("generate_parts=true cannot be combined with smart_low_poly=true "
                              "(smart_low_poly wins upstream and no parts are produced)")
            for key in ("texture", "pbr"):
                if p.get(key) is not False:
                    p[key] = False
                    warnings.append(f"generate_parts=true: {key}=false is sent explicitly "
                                    "(the server rejects parts with texture/pbr on)")
    if kind == "rig":
        rig_type = p.get("rig_type", "biped")
        if rig_type not in RIG_TYPES:
            errors.append(f"rig_type must be one of {', '.join(RIG_TYPES)} (got {rig_type!r})")
        if "spec" in p:
            if p["spec"] not in RIG_SPECS:
                errors.append(f"spec must be one of {', '.join(RIG_SPECS)} (got {p['spec']!r})")
            if rig_type != "biped":
                errors.append(f"spec={p['spec']!r} only applies to rig_type=biped (got {rig_type!r})")
    return s, warnings, errors


def _quad_errors(s, chain):
    """quad topology earlier in the asset chain (or on this step) + a GLB/GLTF request now."""
    p = s["params"]
    fmt = next((str(p[k]).upper() for k in ("format", "out_format")
                if str(p.get(k, "")).upper() in QUAD_BLOCKED), None)
    if fmt is None:
        return []
    quad, source = False, None
    for entry in chain or []:
        if not isinstance(entry, dict):
            continue
        ep = entry.get("params") or {}
        if entry.get("kind") == "generate" or "quad" in ep:
            quad = _truthy(ep.get("quad"))
            source = entry.get("kind")
    if _truthy(p.get("quad")):
        quad, source = True, "this step"
    if not quad:
        return []
    return [f"{s['kind']} requests {fmt} but the mesh is quad (quad=true on {source}): quad "
            "topology cannot be stored in GLB/GLTF; use FBX"]


# ---------- argv ----------

def _value(v, then):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, str) and v != "":
        if then and any(c in v for c in ",;"):
            raise PlanError(f"--then values cannot contain ',' or ';' (got {v!r})")
        return v
    if isinstance(v, (list, dict)) and not then:
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    raise PlanError(f"cannot pass {v!r} in {'--then' if then else '-p'} "
                    "(--then takes only scalars: lists and objects need a direct command)")


def _then_expr(s):
    pairs = ([("model", s["model"])] if s.get("model") else []) + list(s["params"].items())
    args = ";".join(f"{k}={_value(v, True)}" for k, v in pairs)
    return THEN_STEP[s["kind"]] + (f":{args}" if args else "")


def _pflags(params):
    out = []
    for k, v in params.items():
        out += ["-p", f"{k}={_value(v, False)}"]
    return out


def _src(s):
    inp = s["input"]
    return inp.get("images") or [inp.get("prompt") or inp.get("task") or inp.get("file")]


def _argv(s):
    kind, name = s["kind"], s.get("name") or s["label"]
    n = ["-n", str(s["candidates"])] if s["candidates"] != 1 else []
    if kind == "generate":
        return ["tripo", "make", *_src(s), "--model", s["model"], "--name", name,
                *_pflags(s["params"]), *n, "--json"]
    if kind in THEN_STEP:
        return ["tripo", "make", *_src(s), "--then", _then_expr(s), "--name", name, *n, "--json"]
    model = ["--model", s["model"]] if s.get("model") else []
    return ["tripo", *DIRECT[kind], *_src(s), *model, "--name", name,
            *_pflags(s["params"]), "--json"]


def build(step):
    """Execution argv for one step (rules applied: forced/removed params). Raises PlanError."""
    return _argv(_rules(step)[0])


def _ref(s):
    """@reference of the task this step produces. make names a chain step's history entry
    <name>-<step>; with a file input, plain @<name> would be the import task."""
    name = s.get("name") or s["label"]
    return f"@{name}-{THEN_STEP[s['kind']]}" if s["kind"] in THEN_STEP else f"@{name}"


# ---------- pricing ----------

@functools.lru_cache(maxsize=None)
def prices():
    return json.loads(PRICES.read_text(encoding="utf-8"))


def _generation_price(t, model, params, inp):
    g = t["generate"]
    wire = g["aliases"].get(str(model).strip().lower(), model)
    if "prompt" in inp:
        task = "text_to_model"
    elif inp.get("images"):
        task = "image_to_model" if len(inp["images"]) == 1 else "multiview_to_model"
    else:
        return None
    textured = not (params.get("texture") is False or str(params.get("texture")).lower() == "false")
    tier = "standard" if textured else "none"
    quality = params.get("texture_quality") if textured else None
    if quality is not None and str(quality) not in ("fast", "standard", "detailed", "extreme"):
        return None
    h = g["h_series"]
    if wire in h["models"]:
        add = h["addons"]
        credits = h["base"][task][tier] + add["texture_quality"].get(quality, 0)
        if params.get("geometry_quality") is not None:
            extra = add["geometry_quality"].get(str(params["geometry_quality"]))
            if extra is None and params["geometry_quality"] != "standard":
                return None
            credits += extra or 0
        for key in ("quad", "smart_low_poly", "generate_parts"):
            if _truthy(params.get(key)):
                credits += add[key]
        return credits
    if str(wire).startswith(("P1-", "P2-")) and wire in g:
        if quality in ("detailed", "extreme"):
            return None  # P-series HD/8K texture is not on the pricing page
        if wire.startswith("P2") and _truthy(params.get("quad")):
            return None  # P2 quad add-on is not on the pricing page
        return g[wire][task][tier]
    return None


def _step_price(t, kind, model, params, inp):
    if kind == "generate":
        return _generation_price(t, model, params, inp)
    if kind == "texture":
        return t["texture"].get(str(params.get("texture_quality", "standard")))
    if kind == "convert":
        advanced = "face_limit" in params or any(
            k in params and str(params[k]).upper() != str(dv).upper()
            for k, dv in COMPLEX_CONVERT_DEFAULTS.items())
        return t["convert"]["advanced" if advanced else "basic"]
    if kind == "decimate":
        table = t["decimate"].get(str(model or "v2.0").strip().lower(), {})
        return table.get("quad" if _truthy(params.get("quad")) else "tri")
    if kind == "complete":
        return t["complete"].get(str(params.get("completion_mode", "ai_completion")))
    if kind == "smartsegment":
        src = inp.get("file") or (inp.get("images") or [""])[0]
        default = "image" if Path(str(src)).suffix.lower() in IMAGE_EXTS else "model"
        return t["smartsegment"].get(str(params.get("seg_type") or default))
    if kind == "retarget":
        anims = params.get("animations")
        count = len(anims) if isinstance(anims, list) and anims else \
            1 if isinstance(params.get("animation"), str) else None
        return None if count is None else count * t["retarget_per_animation"]
    if kind == "edit_multiview":
        views = params.get("prompts")
        return len(views) * t["edit_multiview_per_view"] if isinstance(views, list) and views \
            else None
    if kind in ("uv", "segment", "rig_check", "rig", "image_to_multiview"):
        return t[kind]
    return None


def table_price(step):
    """Credits for one step from prices.json; None when unknown (never a guess of 0).

    Needs only kind/model/params/input (no label, no CLI), so the hook can call it.
    A file input to a make step adds an import task, whose price is unknown."""
    t = prices()
    kind = step.get("kind")
    params = step.get("params") or {}
    inp = step.get("input") or {}
    credits = _step_price(t, kind, step.get("model"), params, inp)
    if credits is not None and kind in THEN_STEP and "file" in inp:
        credits = None if t["import"] is None else credits + t["import"]
    return credits


def is_paid(step):
    """rig_check on a task is the only free step; a file input adds a paid import task."""
    return step.get("kind") != "rig_check" or "file" in (step.get("input") or {})


def _estimate(s, dry):
    est = (dry or {}).get("generation_credits_estimate")
    if isinstance(est, (int, float)) and not isinstance(est, bool):
        return {"credits": int(est), "source": "dry-run"}
    credits = table_price(s)
    return {"credits": credits, "source": "table" if credits is not None else "none"}


# ---------- check ----------

def _target_payload(s, dry):
    steps = (dry or {}).get("steps") or []
    if s["kind"] == "generate":
        return steps[0].get("payload", {}) if steps else None
    want = THEN_STEP.get(s["kind"])
    hits = [st for st in steps if st.get("name") == want]
    return hits[-1].get("payload", {}) if hits else None


def check(step, chain=None):
    """Validate one step: local rules, the CLI dry-run, the model wire id, and a price.

    `chain` is the asset state chain ([{"kind", "model", "params"}, ...], extra keys
    ignored) used for cross-step rules. Raises PlanError / InputNotFound for a malformed
    step and TripoCliError when the CLI cannot be run."""
    s, warnings, errors = _rules(step)
    argv = _argv(s)
    errors += _quad_errors(s, chain)
    kind, inp = s["kind"], s["input"]

    dry = None
    if argv[1] == "make":
        dry, failure = dry_run(argv)
        if failure:
            errors.append(failure)
        else:
            warnings += dry.get("warnings") or []
            errors += dry.get("errors") or []
    else:
        warnings.append(f"{kind} runs as a direct command, which has no dry-run: "
                        "validated locally only")

    if s.get("model") and kind in MODEL_CAPABILITY:
        wire = wire_id(kind, s["model"])
        payload = _target_payload(s, dry)
        if wire is None:
            errors.append(f"model {s['model']!r} is not a {MODEL_CAPABILITY[kind]} model "
                          "in `tripo models --json`")
        elif payload is None and dry is not None:
            # without the step's payload the B10 check cannot run: never pass silently (M11)
            what = "generation" if kind == "generate" else f"{THEN_STEP.get(kind, kind)!r}"
            errors.append(f"dry-run planned no {what} step: the payload model could not be checked "
                          f"against {wire!r} ({s['model']}, B10)")
        elif payload is not None and payload.get("model") != wire:
            errors.append(f"payload model {payload.get('model')!r} is not the requested "
                          f"{wire!r} ({s['model']})")

    if kind in THEN_STEP and "file" in inp:
        warnings.append("file input: tripo make runs an import task first and its price is "
                        "not published, so the estimate is unknown; it also normalizes scale")
    if "task" in inp and UUID_RE.fullmatch(inp["task"]):
        warnings.append("bare task id: the dry-run cannot check chain legality; prefer @label")

    return {"argv": argv, "ref": _ref(s), "dry_run": dry, "estimate": _estimate(s, dry),
            "warnings": list(dict.fromkeys(warnings)), "errors": list(dict.fromkeys(errors)),
            "paid": is_paid(s)}


# ---------- CLI ----------

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PlanError(f"usage: {message}")


def _read_json(raw, what):
    if raw == "-":
        text = sys.stdin.read()
    elif raw.lstrip().startswith("{"):
        text = raw
    else:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise InputNotFound(f"{what} not found: {raw}")
        text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except ValueError as e:
        raise PlanError(f"{what} is not valid JSON: {e}") from None


def main(argv):
    try:
        p = _Parser(prog="tripo_plan.py", add_help=False)
        p.add_argument("step")
        p.add_argument("--chain")
        p.add_argument("--build", action="store_true")
        a = p.parse_args(argv)
        step = _read_json(a.step, "step")
        if a.build:
            s = _rules(step)[0]
            common.emit({"ok": True, "argv": _argv(s), "ref": _ref(s)})
            return common.EXIT_OK
        chain = None
        if a.chain:
            state = _read_json(a.chain, "chain file")
            chain = state.get("chain") if isinstance(state, dict) else None
            if not isinstance(chain, list):
                raise PlanError('chain file must hold {"chain": [...]}')
        result = check(step, chain)
    except InputNotFound as e:
        common.fail(common.EXIT_NOT_FOUND, str(e))
    except PlanError as e:
        common.fail(common.EXIT_USAGE, str(e))
    except TripoCliError as e:
        common.fail(common.EXIT_INTERNAL, str(e))
    common.emit({"ok": not result["errors"], **result})
    return common.EXIT_CHECK if result["errors"] else common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
