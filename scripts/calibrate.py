#!/usr/bin/env python3
"""QA threshold calibration on a local corpus of direct Tripo outputs (dev tool, 0 credits).

    calibrate.py --corpus <dir>... --labels tests/calibration_labels.json
                 [--thresholds scripts/data/qa_thresholds.json] [--cache <json>]
                 [--jobs N] [--max-mb 100] [--timeout 600] [--md <file>]

-> {"ok": true, "thresholds", "corpus": {"found", "measured", "skipped", "failed"},
    "labels": [...], "codes": {CODE: {...}}}

Corpus: every `tripo-out/*/model.glb` under each --corpus dir. Skipped (and listed under
corpus.skipped, also logged to stderr; never a silent cap): a path containing `model_h31`,
a dir holding `job3d.json` (made by another pipeline, K17), a file over --max-mb. Unlabelled models
run `qa.py --symmetric x`, plus `--budget <face_limit>` when the sibling task.json has one.

Labels (tests/calibration_labels.json, "cases"): each case names a `fixture` (tests/
fixtures.json) or a `path`, the qa.py `args`, an optional `yaw` (the model is first turned
by normalize.py into a temp copy, so its left/right lies on world X), and either
`positive` codes (known defects) or `clean: true`, or neither (a defect only the eye can
see; reported, not scored). `agent_eye` lists known defects no code is expected to catch.

Per code the output gives the values on labelled positives and clean cases, whether the
current threshold catches every positive and stays silent on every clean case, the
percentiles over the unlabelled corpus, and a suggested threshold: the midpoint of the gap
between the clean and positive values (geometric when both sides are positive). A code
`ships` (may take severity S2 or higher) only when a gap exists and at least one
positive and one clean case were measured; otherwise it stays `info` and is checked by eye.
TOO_MANY_INFLUENCES is a platform rule (4 weights per vertex) and only has to stay silent.

Exit codes: 0 ok, 2 usage, 3 corpus dir / labels / labelled model not found, 4 a labelled
case failed in Blender (calibration would be incomplete).
"""
import argparse
import json
import math
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bl  # noqa: E402
import common  # noqa: E402

THRESHOLDS = Path(__file__).resolve().parent / "data" / "qa_thresholds.json"
FIXTURES = common.SKILL_ROOT / "tests" / "fixtures.json"
PCTS = (10, 50, 90, 95, 99)
# codes whose limit is a platform fact, not a measured threshold: they ship without labelled
# positives as long as they stay silent on the clean cases
PLATFORM_RULES = {"TOO_MANY_INFLUENCES": "platform rule: 4 bone weights per vertex is the "
                                         "engine skinning default"}

# code -> (metric getter, threshold key, direction). Mirrors scripts/blender/qa.py findings().
# ">" fires above the threshold, "<" below it, "bool" when true, "rule" is computed.


def _get(*keys):
    def get(m):
        for k in keys:
            if not isinstance(m, dict):
                return None
            m = m.get(k)
        return m
    return get


def _loose_parts(m, th):
    """LOOSE_PARTS count from the reported islands. qa.py lists the 32 largest; every
    unlisted island is no bigger than the last listed one, so when that one is already
    under loose_tris_pct, all unlisted islands count too (exact); otherwise they are not
    counted (a lower bound)."""
    tris, isl = m.get("tris") or 0, m.get("islands") or []
    if not tris:
        return None
    small = [i for i in isl[1:] if 100.0 * i["tris"] / tris < th["loose_tris_pct"]]
    extra = max(0, (m.get("island_count") or len(isl)) - len(isl))
    if extra and isl and 100.0 * isl[-1]["tris"] / tris < th["loose_tris_pct"]:
        return len(small) + extra
    return len(small)


def _texture_max(m):
    return max((max(i["w"], i["h"]) for i in m.get("images") or []), default=0)


CODES = {
    "OVER_BUDGET": (None, None, "rule"),
    "NON_MANIFOLD": (_get("nonmanifold_edges"), "nonmanifold_edges_max", ">"),
    "HOLES": (_get("boundary_edges"), "boundary_edges_max", ">"),
    "LOOSE_PARTS": (_loose_parts, "loose_parts_max", ">"),
    "FLIPPED_NORMALS": (_get("flipped_pct"), "flipped_pct_max", ">"),
    "SLIVERS": (_get("sliver_pct"), "sliver_pct_max", ">"),
    "GROUND_SLAB": (_get("ground", "slab"), None, "bool"),
    "NOT_GROUNDED": (_get("ground", "low_band_tris_pct"), "low_band_tris_pct_min", "<"),
    "ASYMMETRY": (_get("asymmetry", "mean_dist_pct"), "asymmetry_pct_max", ">"),
    "BACK_COPY": (_get("back_relief"), "back_relief_max", ">"),
    "UV_OVERLAP": (_get("uv", "overlap_pct"), "uv_overlap_pct_max", ">"),
    "LOW_TEXEL": (_get("texel_density"), "texel_density_min", "<"),
    "PALETTE_DRIFT": (_get("palette", "delta_e_mean"), "palette_delta_e_max", ">"),
    "BAKED_LIGHT": (_get("baked_light", "score"), "baked_light_max", ">"),
    "TOO_MANY_INFLUENCES": (_get("skin", "max_influences"), "influences_max", ">"),
    "MULTI_MATERIAL": (_get("materials"), "materials_max", ">"),
    "TEXTURE_OVERSIZE": (_texture_max, "texture_max_px", ">"),
}


def log(msg):
    sys.stderr.write(f"calibrate: {msg}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------- corpus and labels

def discover(dirs, max_bytes):
    """(found, skipped): every tripo-out/*/model.glb under `dirs`, minus the excluded ones."""
    found, skipped = [], []
    for d in dirs:
        for p in sorted(Path(d).rglob("model.glb")):
            if not p.is_file() or p.parent.parent.name != "tripo-out":
                continue
            reason = None
            if "model_h31" in str(p):
                reason = "model_h31 in path"
            elif (p.parent / "job3d.json").exists():
                reason = "sibling job3d.json (not a direct Tripo output)"
            elif p.stat().st_size > max_bytes:
                reason = f"over {max_bytes / 2**20:g} MB ({p.stat().st_size / 2**20:.1f} MB)"
            if reason:
                log(f"skip {p}: {reason}")
                skipped.append({"path": str(p), "reason": reason})
            else:
                found.append(p)
    return found, skipped


def face_limit(model_path):
    """input.face_limit from the sibling task.json, or None."""
    try:
        task = json.loads((Path(model_path).parent / "task.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lim = (task.get("input") or {}).get("face_limit") if isinstance(task, dict) else None
    return lim if isinstance(lim, int) and lim > 0 else None


def load_labels(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    cases = []
    for c in data["cases"]:
        if "fixture" in c:
            model = fixtures[c["fixture"]]
        else:
            model = c["path"]
        unknown = set(c.get("positive", [])) - set(CODES)
        if unknown:
            raise ValueError(f"label {c['name']}: unknown codes {sorted(unknown)}")
        if c.get("clean") and c.get("positive"):
            raise ValueError(f"label {c['name']}: positive codes and clean: true "
                             "exclude each other")
        cases.append({**c, "model": model, "args": [str(a) for a in c.get("args", [])]})
    return cases


# ---------------------------------------------------------------- measuring

class Cache:
    """qa reports keyed by model path, size, mtime, yaw and args; saved after every run."""

    def __init__(self, path):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.data = {}
        if self.path and self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                log(f"cache {self.path} is not valid JSON; starting empty")

    @staticmethod
    def key(model, args, yaw):
        st = os.stat(model)
        return json.dumps([str(model), st.st_size, st.st_mtime_ns, yaw, list(args)])

    def get(self, key):
        return self.data.get(key)

    def put(self, key, report):
        with self.lock:
            self.data[key] = report
            if self.path:
                tmp = self.path.with_name(self.path.name + ".part")
                tmp.write_text(json.dumps(self.data), encoding="utf-8")
                os.replace(tmp, self.path)


def measure(model, args, yaw, cache, timeout):
    """qa.py report {"metrics", "findings"} for `model` (turned by `yaw` degrees first)."""
    key = cache.key(model, args, yaw)
    hit = cache.get(key)
    if hit is not None:
        return hit
    if yaw:
        with tempfile.TemporaryDirectory(prefix="tripo-calib-") as tmp:
            turned = os.path.join(tmp, "turned.glb")
            bl.run("normalize.py", [str(model), "--out-model", turned, "--yaw", str(yaw)],
                   timeout=timeout)
            r = bl.run("qa.py", [turned, *args], timeout=timeout)
    else:
        r = bl.run("qa.py", [str(model), *args], timeout=timeout)
    report = {"metrics": r["metrics"],
              "findings": [{k: f[k] for k in ("code", "severity", "value", "threshold")}
                           for f in r["findings"]]}
    cache.put(key, report)
    return report


def run_all(jobs, items, cache, timeout):
    """items: [(id, model, args, yaw)] -> {id: report or {"error": ...}}."""
    out = {}
    done = [0]
    lock = threading.Lock()

    def one(item):
        ident, model, args, yaw = item
        try:
            rep = measure(model, args, yaw, cache, timeout)
        except bl.BlenderError as e:
            rep = {"error": f"exit {e.code}: {e.stderr_tail[-300:]}", "code": e.code}
        except FileNotFoundError as e:
            rep = {"error": str(e), "code": common.EXIT_NOT_FOUND}
        with lock:
            done[0] += 1
            log(f"[{done[0]}/{len(items)}] {model}" + (f" FAILED {rep['error']}"
                                                       if "error" in rep else ""))
        return ident, rep

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for ident, rep in ex.map(one, items):
            out[ident] = rep
    return out


# ---------------------------------------------------------------- analysis

def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    v = sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)
    return round(v, 4)


def fires(value, limit, op):
    if value is None:
        return False
    if op == "bool":
        return bool(value)
    return value > limit if op == ">" else value < limit


def midpoint(lo, hi):
    """A threshold inside the open gap (lo, hi): geometric mean when both are positive."""
    if lo > 0 and hi > 0:
        return round(math.sqrt(lo * hi), 4)
    return round((lo + hi) / 2.0, 4)


def has_code(report, code):
    return [f["severity"] for f in report["findings"] if f["code"] == code]


def analyse_code(code, th, labelled, corpus):
    """labelled: [(case, report)]; corpus: [report] (unlabelled)."""
    get, key, op = CODES[code]
    current = th.get(key) if key else None
    res = {"direction": op, "threshold_key": key, "current": current,
           "severity_now": th["severity"][code]}
    pos = [(c, r) for c, r in labelled if code in c.get("positive", [])]
    clean = [(c, r) for c, r in labelled if c.get("clean")]

    if op == "rule":
        # OVER_BUDGET: severity is computed from --budget; check S0/S1 on positives only
        res["current"] = {k: th[k] for k in ("over_budget_s1", "over_budget_s0")}
        res["positives"] = {c["name"]: has_code(r, code) for c, r in pos}
        res["clean"] = {c["name"]: has_code(r, code) for c, r in clean}
        res["catches_all"] = all(s and s[0] in ("S0", "S1") for s in res["positives"].values())
        res["silent_on_clean"] = not any(res["clean"].values())
        ratios = sorted(r["metrics"]["tris"] / r["budget"] for r in corpus if r.get("budget"))
        res["corpus"] = {"n": len(ratios), "measure": "tris / task.json face_limit",
                         **{f"p{p}": percentile(ratios, p) for p in PCTS},
                         "max": round(ratios[-1], 4) if ratios else None,
                         "fire_rate_s1": (round(sum(x > th["over_budget_s1"] for x in ratios)
                                                / len(ratios), 3) if ratios else None)}
        res["suggested"] = res["current"]
        res["ships"] = bool(pos) and res["catches_all"] and res["silent_on_clean"]
        res["reason"] = ("computed rule (S1 above over_budget_s1 x budget, "
                         "S0 above over_budget_s0 x)")
        return res

    def val(r):
        if code == "LOOSE_PARTS":
            return _loose_parts(r["metrics"], th)
        return get(r["metrics"])

    pv = {c["name"]: val(r) for c, r in pos}
    cv = {c["name"]: val(r) for c, r in clean}
    res["positives"] = pv
    res["clean"] = cv
    res["catches_all_now"] = bool(pv) and all(fires(v, current, op) for v in pv.values())
    res["silent_on_clean_now"] = not any(fires(v, current, op) for v in cv.values())

    vals = [] if op == "bool" else sorted(v for v in map(val, corpus) if v is not None)
    corp = {"n": len(vals)}
    if op == "bool":
        flags = [val(r) for r in corpus if val(r) is not None]
        corp = {"n": len(flags), "true": sum(1 for f in flags if f)}
    elif vals:
        corp.update({f"p{p}": percentile(vals, p) for p in PCTS})
        corp.update({"min": round(vals[0], 4), "max": round(vals[-1], 4),
                     "fire_rate_now": round(sum(fires(v, current, op) for v in vals)
                                            / len(vals), 3)})
    res["corpus"] = corp

    pmeas = [v for v in pv.values() if v is not None]
    cmeas = [v for v in cv.values() if v is not None]
    suggested, ships = None, False
    if code in PLATFORM_RULES:
        ships = res["silent_on_clean_now"]
        suggested = current if ships else None
        reason = PLATFORM_RULES[code] + ("" if ships else "; fires on a clean case")
    elif not pv:
        reason = "no labelled positives"
    elif len(pmeas) < len(pv):
        reason = "a labelled positive has no value for this metric"
    elif not cmeas:
        reason = "no labelled clean case measured this metric"
    elif op == "bool":
        ships = all(pmeas) and not any(cmeas)
        reason = "flag set on every positive, clear on every clean case" if ships else \
            "flag misses a positive or is set on a clean case"
    elif op == ">":
        lo, hi = max(cmeas), min(pmeas)
        if hi > lo:
            suggested, ships = midpoint(lo, hi), True
            reason = f"gap: clean max {lo:g} < positive min {hi:g}"
        else:
            reason = f"overlap: positive min {hi:g} <= clean max {lo:g}"
    else:
        lo, hi = max(pmeas), min(cmeas)
        if hi > lo:
            suggested, ships = midpoint(lo, hi), True
            reason = f"gap: positive max {lo:g} < clean min {hi:g}"
        else:
            reason = f"overlap: clean min {hi:g} <= positive max {lo:g}"
    res["suggested"] = suggested
    res["ships"] = ships
    res["reason"] = reason
    if suggested is not None and vals:
        res["corpus"]["fire_rate_suggested"] = round(
            sum(fires(v, suggested, op) for v in vals) / len(vals), 3)
    return res


def markdown(result):
    lines = ["| code | ships | current | suggested | positives | clean | corpus p50 / p90 / p99 "
             "(n) | reason |", "|---|---|---|---|---|---|---|---|"]

    def fmt(d):
        if not d:
            return "-"
        return ", ".join(f"{k} {v}" for k, v in d.items())
    for code, r in result["codes"].items():
        c = r["corpus"]
        dist = (f"{c.get('p50')} / {c.get('p90')} / {c.get('p99')} ({c['n']})"
                if "p50" in c else (f"{c.get('true', 0)} true ({c['n']})" if "true" in c
                                    else f"- ({c['n']})"))
        cur, sug = (fmt(r[k]) if isinstance(r[k], dict) else r[k] for k in ("current", "suggested"))
        lines.append(f"| `{code}` | {'yes' if r['ships'] else 'no'} | {cur} | {sug} | "
                     f"{fmt(r['positives'])} | {fmt(r['clean'])} | {dist} | {r['reason']} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main

class Parser(argparse.ArgumentParser):
    def error(self, message):
        common.fail(common.EXIT_USAGE, f"usage: {message}")


def main(argv):
    p = Parser(prog="calibrate.py")
    p.add_argument("--corpus", nargs="+", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--thresholds", default=str(THRESHOLDS))
    p.add_argument("--cache")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--max-mb", type=float, default=100.0)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--md")
    a = p.parse_args(argv)

    for d in a.corpus:
        if not Path(d).is_dir():
            common.fail(common.EXIT_NOT_FOUND, f"corpus dir not found: {d}")
    for f in (a.labels, a.thresholds):
        if not Path(f).is_file():
            common.fail(common.EXIT_NOT_FOUND, f"file not found: {f}")
    try:
        cases = load_labels(a.labels)
    except (KeyError, ValueError) as e:
        common.fail(common.EXIT_USAGE, f"bad labels file {a.labels}: {e}")
    missing = [c["model"] for c in cases if not Path(c["model"]).is_file()]
    if missing:
        common.fail(common.EXIT_NOT_FOUND, "labelled model not found", missing=missing)
    th = json.loads(Path(a.thresholds).read_text(encoding="utf-8"))["qa"]

    found, skipped = discover(a.corpus, int(a.max_mb * 2**20))
    labelled_paths = {str(Path(c["model"]).resolve()) for c in cases}
    unlabelled = [m for m in found if str(m.resolve()) not in labelled_paths]
    budgets = {str(m): face_limit(m) for m in unlabelled}
    items = [(c["name"], c["model"], c["args"], c.get("yaw")) for c in cases]
    items += [(str(m), str(m), ["--symmetric", "x"] + (["--budget", str(budgets[str(m)])]
                                                        if budgets[str(m)] else []), None)
              for m in unlabelled]
    cache = Cache(a.cache)
    reports = run_all(a.jobs, items, cache, a.timeout)

    bad = {c["name"]: reports[c["name"]] for c in cases if "error" in reports[c["name"]]}
    if bad:
        common.fail(common.EXIT_INTERNAL, "labelled case failed in Blender",
                    failed={k: v["error"] for k, v in bad.items()})
    labelled = [(c, reports[c["name"]]) for c in cases]
    corpus, failed = [], []
    for m in unlabelled:
        r = reports[str(m)]
        if "error" in r:
            failed.append({"path": str(m), "error": r["error"]})
        else:
            corpus.append({**r, "budget": budgets[str(m)]})

    result = {
        "ok": True,
        "thresholds": a.thresholds,
        "corpus": {"dirs": a.corpus, "found": len(found), "labelled_in_corpus":
                   len(found) - len(unlabelled), "measured": len(corpus),
                   "skipped": skipped, "failed": failed},
        "labels": [{"name": c["name"], "positive": c.get("positive", []),
                    "clean": bool(c.get("clean")), "agent_eye": c.get("agent_eye", []),
                    "findings": [[f["code"], f["severity"]] for f in r["findings"]]}
                   for c, r in labelled],
        "codes": {code: analyse_code(code, th, labelled, corpus) for code in CODES},
    }
    if a.md:
        Path(a.md).write_text(markdown(result), encoding="utf-8")
    common.emit(result)
    return common.EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
