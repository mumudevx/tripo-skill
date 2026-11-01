#!/usr/bin/env python3
"""Claude Code PreToolUse credit lock for tripo-cli (spec 16.2, K14, B17).

Reads the hook JSON on stdin (`tool_name`, `tool_input.command`, `cwd`) and finds
every tripo call in a Bash command, also behind `rtk`, `env`, `VAR=…`, `cd … &&`,
pipes, `bash -c`, `$(…)`, `npx tripo-cli` and a path to the binary.

  no tripo call, or only free ones   -> exit 0, no output (other hooks decide)
  exactly one paid step              -> permissionDecision "ask" with step, estimate,
                                        balance and label in Turkish
  more than one paid step            -> permissionDecision "deny" (B17)

An unknown tripo subcommand counts as one paid step (a newer CLI may bill it).

The estimate for `make` comes from the same argv run with `--dry-run --json`
inserted right after `make` (20 s timeout); chain steps and other commands are
priced from tripo_plan's table; unknown -> "tahmin yok", never 0. The balance
comes from `tripo balance --json` (5 s timeout). Only the trusted binary ($TRIPO,
else `tripo` on PATH) is run, never a path taken from the command.

TRIPO_GUARD_OFFLINE=1 spawns nothing: TRIPO_GUARD_BALANCE and TRIPO_GUARD_DRYRUN
(raw JSON) stand in for the two CLI calls (tests).
"""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tripo_plan  # noqa: E402

DRY_RUN_TIMEOUT = 20
BALANCE_TIMEOUT = 5
B17 = "Her ücretli adım ayrı komut olmalı (B17)"
NO_ESTIMATE = "tahmin yok"

# ---------- shell ----------

PUNCT = "();<>|&\n`"
SEPARATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "\n", "(", ")", "`", "$"}
REDIRECTS = {">", ">>", "<", "<<", "<<<", ">&", "<&", "&>", "&>>", ">|", "<>"}
ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "time",
            "command", "exec", "builtin", "nohup", "noglob"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SHELL_LONG_VALUE_OPTS = {"--rcfile", "--init-file"}
NPX = {"npx", "bunx"}
# wrapper -> its options that take a value
WRAPPER_VALUE_OPTS = {"env": {"-u", "-C", "-S"}, "sudo": {"-u", "-g", "-C", "-h", "-p"},
                      "nice": {"-n"}, "timeout": {"-s", "-k"},
                      "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"}}


class ParseError(Exception):
    pass


def _lex(command):
    lex = shlex.shlex(command.replace("\\\n", ""), posix=True, punctuation_chars=PUNCT)
    lex.whitespace = " \t\r"  # a newline separates commands
    lex.whitespace_split = True
    lex.commenters = ""  # comments only add false positives, never hide a call
    try:
        return list(lex)
    except ValueError as e:
        raise ParseError(str(e)) from None


HEREDOC_DELIM_RE = re.compile(r"""(-?)[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|(\\?)([^\s;&|<>()'"`]+))""")


def _heredocs(command):
    """Cut heredoc bodies out of `command`, tracking quotes so a '<<' inside a string is not
    an operator. Returns (command without bodies, [(body, quoted delimiter, operator line)]).
    An unterminated body runs to the end, as in the shell."""
    out, bodies, pending = [], [], []
    i, n, q = 0, len(command), None
    while i < n:
        c = command[i]
        if q:
            if c == "\\" and q == '"':
                out.append(command[i:i + 2])
                i += 2
                continue
            q = None if c == q else q
        elif c == "\\":
            out.append(command[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            q = c
        elif command.startswith("<<<", i):
            out.append("<<<")
            i += 3
            continue
        elif command.startswith("<<", i):
            m = HEREDOC_DELIM_RE.match(command, i + 2)
            if m:
                quoted = m.group(2) is not None or m.group(3) is not None or bool(m.group(4))
                delim = next(g for g in (m.group(2), m.group(3), m.group(5)) if g is not None)
                pending.append((m.group(1) == "-", delim, quoted))
                out.append(command[i:m.end()])
                i = m.end()
                continue
        elif c == "\n" and pending:
            text = "".join(out)
            line = text[text.rfind("\n") + 1:]
            out.append("\n")
            j = i + 1
            for strip_tabs, delim, quoted in pending:
                body = []
                while j < n:
                    k = command.find("\n", j)
                    k = n if k == -1 else k
                    ln, j = command[j:k], k + 1
                    if (ln.lstrip("\t") if strip_tabs else ln) == delim:
                        break
                    body.append(ln)
                bodies.append(("\n".join(body), quoted, line))
            pending, i = [], j
            continue
        out.append(c)
        i += 1
    return "".join(out), bodies


def _feeds_shell(words):
    return any(os.path.basename(w) in SHELLS for w in words)


def _substitutions(token):
    """Bodies of $(...) and `...` inside one word (double quotes keep them live)."""
    out = []
    i = token.find("$(")
    while i != -1:
        depth, j = 1, i + 2
        while j < len(token) and depth:
            depth += {"(": 1, ")": -1}.get(token[j], 0)
            j += 1
        out.append(token[i + 2:j - 1 if depth == 0 else j])
        i = token.find("$(", j)
    parts = token.split("`")
    out += parts[1::2]
    return out


def _segments(tokens, herestrings=None):
    """Split tokens into simple commands. `herestrings` collects (segment index, word) for
    every '<<<' so a here-string fed to a shell can be scanned."""
    seg, out = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in SEPARATORS:
            if seg:
                out.append(seg)
            seg = []
        elif t in REDIRECTS:
            if seg and seg[-1].isdigit():
                seg.pop()  # fd number of 2>&1
            if t == "<<<" and herestrings is not None and i + 1 < len(tokens):
                herestrings.append((len(out), tokens[i + 1]))
            i += 1  # the target
        else:
            seg.append(t)
        i += 1
    if seg:
        out.append(seg)
    return out


def _skip_opts(argv, i, value_opts):
    while i < len(argv) and argv[i].startswith("-") and argv[i] != "-":
        flag = argv[i]
        i += 2 if flag in value_opts else 1
    return i


def _unwrap(argv):
    """Drop shell keywords, assignments and wrappers. Returns (program argv, nested
    command strings to scan as well)."""
    i, nested = 0, []
    while i < len(argv):
        t = argv[i]
        if ASSIGN_RE.match(t) or t in KEYWORDS:
            i += 1
        elif t == "rtk":
            i += 2 if i + 1 < len(argv) and argv[i + 1] == "proxy" else 1
        elif t in WRAPPER_VALUE_OPTS:
            i = _skip_opts(argv, i + 1, WRAPPER_VALUE_OPTS[t])
            if t == "timeout" and i < len(argv):
                i += 1  # the duration
        elif t in NPX or (t in ("pnpm", "yarn") and argv[i + 1:i + 2] == ["dlx"]):
            i = _skip_opts(argv, i + (1 if t in NPX else 2), {"-p", "--package"})
            if i < len(argv) and argv[i].split("@")[0] in ("tripo-cli", "tripo"):
                return ["tripo", *argv[i + 1:]], nested
            return [], nested
        elif os.path.basename(t) in SHELLS:
            # Walk all options like the shell does: -o/+o/-O/+O (also inside
            # combined flags such as -euo) take a value, and with -c anywhere
            # the first non-option argument is the command string.
            j, has_c = i + 1, False
            while j < len(argv):
                a = argv[j]
                if a in ("--", "-"):
                    j += 1
                    break
                if a.startswith("--"):
                    j += 2 if a in SHELL_LONG_VALUE_OPTS else 1
                elif a[:1] in "-+" and len(a) > 1:
                    letters = a[1:]
                    has_c = has_c or "c" in letters
                    j += 1 + letters.count("o") + letters.count("O")
                else:
                    break
            if has_c and j < len(argv):
                nested.append(argv[j])
            return [], nested
        elif t == "eval":
            nested.append(" ".join(argv[i + 1:]))
            return [], nested
        else:
            break
    return argv[i:], nested


def tripo_calls(command, cwd=None):
    """[(args after the tripo program, effective cwd)] for every tripo call in `command`."""
    command, heredocs = _heredocs(command)
    tokens = _lex(command)
    calls = []
    for body, quoted, line in heredocs:
        if _feeds_shell(re.split(r"[\s|;&()]+", line)):
            calls += tripo_calls(body, cwd)  # the shell runs the body
        elif not quoted:
            for sub in _substitutions(body):  # an unquoted delimiter keeps $(...) live
                calls += tripo_calls(sub, cwd)
    for tok in tokens:
        for body in _substitutions(tok):
            calls += tripo_calls(body, cwd)
    herestrings = []
    segments = _segments(tokens, herestrings)
    for idx, word in herestrings:
        if idx < len(segments) and _feeds_shell(segments[idx]):
            calls += tripo_calls(word, cwd)
    for seg in segments:
        argv, nested = _unwrap(seg)
        for body in nested:
            calls += tripo_calls(body, cwd)
        if not argv:
            continue
        prog = argv[0]
        if prog == "cd":
            target = argv[1] if len(argv) > 1 else "~"
            if target != "-":
                cwd = os.path.join(cwd or os.getcwd(), os.path.expanduser(target))
        elif os.path.basename(prog) in ("tripo", "tripo-cli"):
            calls.append((argv[1:], cwd))
        elif prog == "node" and len(argv) > 1 and "tripo-cli" in argv[1]:
            calls.append((argv[2:], cwd))
    return calls


# ---------- tripo argv ----------

VALUE_OPTS = {
    "--for", "--then", "--model", "-n", "--candidates", "--seed", "-o", "--out", "--timeout",
    "--name", "-p", "--param", "--profile", "--prompt", "--texture-quality",
    "--texture-alignment", "--format", "--texture-size", "--texture-format", "--face-limit",
    "--fbx-preset", "--export-orientation", "--scale-factor", "--rig-type", "--spec",
    "--out-format", "--completion-mode", "--seg-type", "--granularity", "--hint", "--bbox",
    "--ref-image", "--limit", "--concurrency", "--retries", "--toolset", "--region", "--key",
    "--topic"}
VARIADIC_OPTS = {"--animation"}
CANONICAL = {"--candidates": "-n", "--param": "-p", "--out": "-o", "--help": "-h",
             "--version": "-v"}
# options that never reach the API payload of a direct command
NON_PARAM = {"-n", "-o", "-p", "-h", "-v", "--name", "--timeout", "--notify", "--wait",
             "--download", "--json", "--yes", "--quiet", "--open", "--profile", "--model",
             "--dry-run"}

FREE_TOP = {"docs", "models", "balance", "usage", "whoami", "doctor", "history", "view",
            "config", "update", "completion", "login", "logout", "use", "mcp"}
FREE_SUB = {"task": {"get", "list", "watch"}, "files": {"upload"}, "anim": {"check"}}
PAID_GROUPS = {"generate", "model", "mesh", "anim", "batch"}
PAID_SUB = {"anim": {"rig", "retarget"}, "batch": {"run"}}
DIRECT_KINDS = {
    ("generate", "text-to-model"): "generate", ("generate", "image-to-model"): "generate",
    ("generate", "multiview-to-model"): "generate",
    ("generate", "image-to-multiview"): "image_to_multiview",
    ("generate", "edit-multiview"): "edit_multiview",
    ("model", "texture"): "texture", ("model", "convert"): "convert",
    ("mesh", "segment"): "segment", ("mesh", "complete"): "complete",
    ("mesh", "decimate"): "decimate", ("mesh", "uv"): "uv",
    ("mesh", "smartsegment"): "smartsegment", ("anim", "rig"): "rig",
    ("anim", "retarget"): "retarget"}

THEN_ALIASES = {"check": "rig-check", "rigcheck": "rig-check", "animate": "retarget",
                "lowpoly": "decimate"}
THEN_NAMES = {"texture", "convert", "import", "rig-check", "rig", "retarget", "segment",
              "complete", "decimate", "uv", "edit", "smartsegment"}
THEN_PRIMARY = {"convert": "format", "retarget": "animation", "decimate": "face_limit",
                "texture": "texture_quality", "rig": "rig_type", "segment": "model",
                "smartsegment": "granularity"}
# scenario -> paid steps of its default chain (tripo-cli knowledge/scenarios.js)
SCENARIO_CHAINS = {"game-mobile": ["convert"], "game-pc": ["convert"], "film": [],
                   "print": ["convert"], "ar-web": ["convert"], "anim": ["rig", "retarget"],
                   "toy": []}
MODEL_EXTS = {".glb", ".gltf", ".fbx", ".obj", ".stl"}


def _coerce(raw, lists=False):
    """tripo-cli's value coercion: true/false, integers, decimals, JSON for -p values."""
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d*\.\d+", raw):
        return float(raw)
    if lists and raw[:1] + raw[-1:] in ("[]", "{}"):
        try:
            return json.loads(raw)
        except ValueError:
            pass
    return raw


def scan(tokens):
    """Commander-style scan: (positionals, [(option, value)]). A value option takes the
    next token even when it starts with '-', as commander does."""
    pos, opts, i = [], [], 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            pos += tokens[i + 1:]
            break
        if t.startswith("--") and len(t) > 2:
            name, eq, val = t.partition("=")
            name = CANONICAL.get(name, name)
            if eq:
                opts.append((name, val))
            elif name in VARIADIC_OPTS:
                vals, i = [], i + 1
                while i < len(tokens) and not tokens[i].startswith("-"):
                    vals.append(tokens[i])
                    i += 1
                opts.append((name, vals))
                continue
            elif name in VALUE_OPTS:
                opts.append((name, tokens[i + 1] if i + 1 < len(tokens) else None))
                i += 1
            else:
                opts.append((name, True))
        elif t.startswith("-") and len(t) > 1:
            if t[:2] in VALUE_OPTS:
                if len(t) > 2:
                    opts.append((t[:2], t[2:]))
                else:
                    opts.append((t[:2], tokens[i + 1] if i + 1 < len(tokens) else None))
                    i += 1
            else:
                opts += [(CANONICAL.get("-" + c, "-" + c), True) for c in t[1:]]
        else:
            pos.append(t)
        i += 1
    return pos, opts


def _opt(opts, name):
    vals = [v for k, v in opts if k == name]
    return vals[-1] if vals else None


def _pparams(opts):
    params = {}
    for k, v in opts:
        if k == "-p" and isinstance(v, str) and "=" in v[1:]:
            key, _, raw = v.partition("=")
            params[key.strip()] = _coerce(raw.strip(), lists=True)
    return params


def parse_then(expr):
    """tripo-cli parseThenExpression: [{"name", "args", "known"}]."""
    steps = []
    for part in (p.strip() for p in expr.split(",")):
        if not part:
            continue
        head, _, rest = part.partition(":")
        name = THEN_ALIASES.get(head.strip().lower(), head.strip().lower())
        if name not in THEN_NAMES:
            if "=" in part and steps:
                key, _, raw = part.partition("=")
                steps[-1]["args"][key.strip()] = _coerce(raw.strip())
            else:
                steps.append({"name": name or part, "args": {}, "known": False})
            continue
        args = {}
        for tok in (t.strip() for t in re.split(r"[,;]", rest)):
            if "=" in tok:
                key, _, raw = tok.partition("=")
                args[key.strip()] = _coerce(raw.strip())
            elif tok and name in THEN_PRIMARY:
                args[THEN_PRIMARY[name]] = _coerce(tok)
        steps.append({"name": name, "args": args, "known": True})
    return steps


def _source(positionals):
    """make input -> ("task" | "file" | "generate", tripo_plan input dict)."""
    first = positionals[0] if positionals else ""
    if first.startswith("@") or tripo_plan.UUID_RE.fullmatch(first):
        return "task", {"task": first}
    if Path(first).suffix.lower() in MODEL_EXTS:
        return "file", {"file": first}
    if positionals and all(Path(p).suffix.lower() in tripo_plan.IMAGE_EXTS
                           for p in positionals):
        return "generate", {"images": positionals}
    return "generate", {"prompt": " ".join(positionals)}


def _step(what, kind=None, model=None, params=None, inp=None):
    return {"what": what, "plan": None if kind is None else
            {"kind": kind, "model": model, "params": params or {}, "input": inp or {}}}


def _make_steps(pos, opts):
    kind, inp = _source(pos)
    model, scenario = _opt(opts, "--model"), _opt(opts, "--for")
    steps = []
    if kind == "generate":
        n = _coerce(str(_opt(opts, "-n") or 1))
        label = "generate" if "prompt" in inp else (
            "image-to-model" if len(inp["images"]) == 1 else "multiview-to-model")
        gen = _step(f"make → {label}" + (f" ({model})" if model else ""),
                    "generate", None if scenario else model, _pparams(opts), inp)
        steps += [gen] * (n if isinstance(n, int) and n > 1 else 1)
    then = _opt(opts, "--then")
    if isinstance(then, str):
        chain = parse_then(then)
    elif scenario is not None:
        chain = [{"name": s, "args": {}, "known": False}
                 for s in SCENARIO_CHAINS.get(scenario, [f"--for {scenario}"])]
    else:
        chain = []
    src = pos[0] if pos else "?"
    for st in chain:
        if st["name"] == "rig-check":
            continue
        args = dict(st["args"])
        plan_kind = st["name"].replace("-", "_") if st["known"] else None
        steps.append(_step(f"{st['name']} (make {src})", plan_kind, args.pop("model", None),
                           args, inp))
    if kind == "file" and not steps:
        steps.append(_step(f"import (make {src}, ücreti yayımlanmamış)"))
    return steps


def _direct_params(opts):
    params = {}
    for k, v in opts:
        if k == "--animation":
            if len(v) > 1:
                params["animations"] = v
            elif v:
                params["animation"] = v[0]
        elif k.startswith("--no-"):
            params[k[5:].replace("-", "_")] = False
        elif k.startswith("--") and k not in NON_PARAM:
            params[k[2:].replace("-", "_")] = True if v is True else _coerce(str(v))
    params.update(_pparams(opts))
    return params


def _direct_steps(group, sub, pos, opts):
    kind = DIRECT_KINDS.get((group, sub))
    what = f"{group} {sub}" + (f" {pos[0]}" if pos else "")
    if kind is None:
        return [_step(what)]
    src = pos[0] if pos else "@last"
    if kind == "generate":
        if sub == "text-to-model":
            inp = {"prompt": " ".join(pos)}
        else:
            images = [p for p in pos if Path(p).suffix.lower() in tripo_plan.IMAGE_EXTS]
            inp = {"images": images} if images and len(images) == len(pos) else {}
    elif kind == "smartsegment":
        inp = {"file": src}
    else:
        inp = {"task": src}  # a direct command uploads a file as-is: no import task
    return [_step(what, kind, _opt(opts, "--model"), _direct_params(opts), inp)]


def analyze(args):
    """Classify the args after `tripo`: {"steps": [paid steps], "globals", "make", "label"}."""
    i, glob = 0, []
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-h", "--help", "-v", "--version"):
            return {"steps": []}
        take = 2 if args[i] == "--profile" else 1
        glob += args[i:i + take]
        i += take
    if i == len(args):
        return {"steps": []}  # bare `tripo` prints help when not interactive
    cmd, rest = args[i], args[i + 1:]
    pos, opts = scan(rest)
    keys = {k for k, _ in opts}
    if "-h" in keys or ("--dry-run", True) in opts:
        return {"steps": []}
    out = {"globals": glob, "label": _opt(opts, "--name"), "make": None}
    if cmd in FREE_TOP:
        steps = []
    elif cmd == "make":
        steps = _make_steps(pos, opts)
        out["make"] = rest
    elif cmd in ("redo", "ai"):
        steps = [_step(f"{cmd} {' '.join(pos) or ('@last' if cmd == 'redo' else '')}".strip())]
    elif cmd in FREE_SUB or cmd in PAID_GROUPS:
        if not pos:
            steps = []  # a bare group prints its help
        elif pos[0] in FREE_SUB.get(cmd, ()):
            steps = []
        elif cmd in PAID_SUB and pos[0] not in PAID_SUB[cmd]:
            steps = [_step(f"tanınmayan tripo komutu '{cmd} {pos[0]}' (ücretli olabilir)")]
        elif cmd in PAID_GROUPS:
            steps = _direct_steps(cmd, pos[0], pos[1:], opts)
        else:
            steps = [_step(f"tanınmayan tripo komutu '{cmd} {pos[0]}' (ücretli olabilir)")]
    else:
        steps = [_step(f"tanınmayan tripo komutu '{cmd}' (ücretli olabilir)")]
    out["steps"] = steps
    return out


# ---------- CLI calls ----------

def _offline():
    return os.environ.get("TRIPO_GUARD_OFFLINE") == "1"


def _cli_json(argv, timeout, cwd=None):
    exe = tripo_plan.tripo_bin()
    if exe is None:
        return None
    try:
        p = subprocess.run([exe, *argv], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL,
                           cwd=cwd if cwd and os.path.isdir(cwd) else None)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return tripo_plan._last_json(p.stdout)


def _env_json(name):
    try:
        return json.loads(os.environ.get(name, ""))
    except ValueError:
        return None


def _num(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def balance_text(glob):
    data = _env_json("TRIPO_GUARD_BALANCE") if _offline() else \
        _cli_json([*glob, "balance", "--json"], BALANCE_TIMEOUT)
    try:
        return f"bakiye: {_num(data['balance'])} kredi (donuk {_num(data.get('frozen', 0))})"
    except (TypeError, KeyError, ValueError):
        return "bakiye okunamadı"


def make_dry_run(glob, rest, cwd):
    """The user's make argv as a dry-run. --dry-run goes right after `make`, so no
    later token (a dangling value option, `--`) can swallow it."""
    if _offline():
        return _env_json("TRIPO_GUARD_DRYRUN")
    data = _cli_json([*glob, "make", "--dry-run", "--json", *rest], DRY_RUN_TIMEOUT, cwd)
    return data if isinstance(data, dict) and data.get("dry_run") is True else None


def estimate_text(step, info, dry):
    est = (dry or {}).get("generation_credits_estimate")
    if isinstance(est, (int, float)) and not isinstance(est, bool):
        text = f"tahmini kredi: {_num(est)} (dry-run)"
    else:
        plan = step["plan"]
        credits = tripo_plan.table_price(plan) if plan else None
        if credits is not None:
            text = f"tahmini kredi: {_num(credits)} (fiyat tablosu)"
        elif plan and "file" in plan["input"] and info["make"] is not None:
            base = tripo_plan.table_price({**plan, "input": {"task": "@x"}})
            if base is None:
                text = f"tahmini kredi: {NO_ESTIMATE} (+ import ücreti olabilir)"
            else:
                text = (f"tahmini kredi: {NO_ESTIMATE} ({plan['kind']} {_num(base)}"
                        " + import ücreti olabilir)")
        else:
            text = f"tahmini kredi: {NO_ESTIMATE}"
    errors = (dry or {}).get("errors") or []
    if errors:
        text += f" | dry-run hatası: {'; '.join(map(str, errors))[:200]}"
    return text


# ---------- hook ----------

def decide(command, cwd=None):
    """None (stay silent) or (decision, reason)."""
    try:
        calls = tripo_calls(command, cwd)
    except ParseError:
        if "tripo" in command:
            return "ask", "Tripo kredi kilidi: komut ayrıştırılamadı, ücretli olabilir"
        return None
    found = []
    for args, call_cwd in calls:
        info = analyze(args)
        found += [(step, info, call_cwd) for step in info["steps"]]
    if not found:
        return None
    if len(found) > 1:
        names = ", ".join(step["what"] for step, _, _ in found)
        return "deny", f"{B17}: bu komutta {len(found)} ücretli adım var ({names})"
    step, info, call_cwd = found[0]
    dry = make_dry_run(info["globals"], info["make"], call_cwd) \
        if info["make"] is not None else None
    parts = ["Tripo kredi kilidi", f"adım: {step['what']}", estimate_text(step, info, dry),
             balance_text(info["globals"]), f"label: {info['label'] or 'yok'}"]
    return "ask", " | ".join(parts)


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or "tripo" not in command:
        return 0
    try:
        result = decide(command, event.get("cwd"))
    except Exception as e:  # never let a guard bug wave a paid call through
        print(f"tripo_guard: {type(e).__name__}: {e}", file=sys.stderr)
        result = ("ask", f"Tripo kredi kilidi: kilit hatası ({type(e).__name__}), "
                         "komut ücretli olabilir")
    if result:
        decision, reason = result
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": decision,
            "permissionDecisionReason": reason}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
