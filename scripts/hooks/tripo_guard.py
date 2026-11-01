#!/usr/bin/env python3
"""Claude Code PreToolUse credit lock for tripo-cli (spec 16.2, K14, B17).

Reads the hook JSON on stdin (`tool_name`, `tool_input.command`, `cwd`) and finds
every tripo call in a Bash command, also behind `rtk`, `env`, `VAR=…`, `cd … &&`,
pipes, `bash -c`, `$(…)`, `npx tripo-cli` and a path to the binary. Names are
case-folded (APFS runs `TRIPO`). Fail closed: a program the guard does not know
(`mise exec`, `npm exec`, `find -exec`, `caffeinate`, ...) is analysed from its first
tripo word unless it is a read-only tool (READ_ONLY); a `$VAR` program in a command
that mentions tripo, or a shell script file that mentions tripo, asks.

  no tripo call, or only free ones   -> exit 0, no output (other hooks decide)
  exactly one paid step              -> permissionDecision "ask" with step, estimate,
                                        balance and label in Turkish
  more than one paid step            -> permissionDecision "deny" (B17)
  a paid step that runs many times   -> "deny" (B17): a loop body (also zsh
                                        `repeat N`), xargs, parallel,
                                        find -exec, watch, a function called twice,
                                        `batch run`, `ai <request>`

An unknown tripo subcommand counts as one paid step (a newer CLI may bill it), and
so does `tripo mcp` fed through a pipe, file, heredoc or here-string (JSON-RPC can
call tripo_make).

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

# tripo_plan (the only non-stdlib import) loads inside main's try: a broken or
# missing module must turn into an "ask", never into a silent exit 1 (I2).
tripo_plan = None


def _load_plan():
    global tripo_plan
    if tripo_plan is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import tripo_plan as module
        tripo_plan = module
    return tripo_plan


DRY_RUN_TIMEOUT = 20
BALANCE_TIMEOUT = 5
B17 = "Her ücretli adım ayrı komut olmalı (B17)"
NO_ESTIMATE = "tahmin yok"

# ---------- shell ----------

PUNCT = "();<>|&\n`"
SEPARATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "\n", "(", ")", "`", "$"}
REDIRECTS = {">", ">>", "<", "<<", "<<<", ">&", "<&", "&>", "&>>", ">|", "<>"}
STDIN_REDIRECTS = {"<", "<<", "<<<", "<&", "<>"}
OPERATORS = (SEPARATORS | REDIRECTS) - {"$"}
OPERATORS_BY_LEN = sorted(OPERATORS, key=len, reverse=True)
ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "time",
            "exec", "builtin", "nohup", "noglob"}
TRIPO_NAMES = {"tripo", "tripo-cli"}
# programs that never run their arguments: a tripo word after them is text (C1)
READ_ONLY = {"grep", "rg", "echo", "printf", "cat", "less", "more", "head", "tail", "git",
             "gh", "ls", "which", "type", "man", "sed", "awk", "jq", "wc", "sort", "diff"}
SCRIPT_READ_LIMIT = 1 << 20
# a paid call behind these may run many times: one approval would cover N tasks (I1)
LOOP_WORDS = {"while", "until", "for", "select"}
# shell words that may stand before a loop keyword in the same segment (R2)
LEAD_WORDS = {"if", "then", "else", "elif", "do", "time", "!"}
REPEAT_BRACE = object()  # braces entry of a zsh `repeat N { ... }` body
REPEATERS = {"xargs", "parallel", "find", "fd", "watch"}
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
        tokens = list(lex)
    except ValueError as e:
        raise ParseError(str(e)) from None
    out = []
    for t in tokens:  # shlex glues runs of punctuation (");", ")|"): split into operators;
        # "()" stays whole, it marks a function definition
        if t and t not in OPERATORS and t != "()" and all(c in PUNCT for c in t):
            while t:
                op = next((o for o in OPERATORS_BY_LEN if t.startswith(o)), t[0])
                out.append(op)
                t = t[len(op):]
        else:
            out.append(t)
    return out


HEREDOC_DELIM_RE = re.compile(r"""(-?)[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|(\\?)([^\s;&|<>()'"`]+))""")


SUB_MARK = "$__tg_sub{}__"
SUB_RE = re.compile(r"\$__tg_sub(\d+)__")


def _scan(s, i=0, close=False, heredoc_body=False):
    """Walk shell text from `i`, tracking quotes like the shell (I3).

    Cuts heredoc bodies out, and replaces every live command substitution with
    SUB_MARK.format(n): `$(...)` and backticks are live unquoted and inside double
    quotes, literal inside single quotes and inside quoted heredoc bodies. A `$(...)`
    body is matched with its own quote and heredoc tracking, so a quoted heredoc in
    it (`"$(cat <<'EOF' ... EOF)"`) hides its text and parentheses.

    close: stop at the ')' that closes a `$(` and return its index as `end`.
    heredoc_body: `s` is an unquoted heredoc body: quotes are plain characters.
    Returns (end, text, heredocs [(body, quoted delimiter, operator line)], subs).
    An unterminated body or quote runs to the end, as in the shell."""
    out, heredocs, subs, pending = [], [], [], []
    n, q, depth = len(s), None, 0
    while i < n:
        c = s[i]
        if q == "'":
            out.append(c)
            q = None if c == "'" else q
            i += 1
            continue
        if c == "\\":
            out.append(s[i:i + 2])
            i += 2
            continue
        if c == "`" or s.startswith("$(", i):
            if c == "`":
                j = i + 1
                while j < n and s[j] != "`":
                    j += 2 if s[j] == "\\" else 1
                body = s[i + 1:j]
            else:
                j = _scan(s, i + 2, close=True)[0]
                body = s[i + 2:j]
            out.append(SUB_MARK.format(len(subs)))
            subs.append(body)
            i = j + 1
            continue
        if q == '"' or heredoc_body:
            out.append(c)
            q = None if c == q else q
            i += 1
            continue
        if c in "'\"":
            q = c
        elif close and c == "(":
            depth += 1
        elif close and c == ")":
            if depth == 0:
                return i, "".join(out), heredocs, subs
            depth -= 1
        elif s.startswith("<<<", i):
            out.append("<<<")
            i += 3
            continue
        elif s.startswith("<<", i):
            m = HEREDOC_DELIM_RE.match(s, i + 2)
            if m:
                quoted = m.group(2) is not None or m.group(3) is not None or bool(m.group(4))
                delim = next(g for g in (m.group(2), m.group(3), m.group(5)) if g is not None)
                pending.append((m.group(1) == "-", delim, quoted))
                out.append(s[i:m.end()])
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
                    k = s.find("\n", j)
                    k = n if k == -1 else k
                    ln, j = s[j:k], k + 1
                    if (ln.lstrip("\t") if strip_tabs else ln) == delim:
                        break
                    body.append(ln)
                heredocs.append(("\n".join(body), quoted, line))
            pending, i = [], j
            continue
        out.append(c)
        i += 1
    return n, "".join(out), heredocs, subs


def _base(word):
    """Lowercased basename: APFS is case-insensitive, so `TRIPO` runs tripo."""
    return os.path.basename(word).lower()


def _is_tripo_word(word):
    return _base(word) in TRIPO_NAMES or "tripo-cli" in word.lower()


def _feeds_shell(words):
    return any(_base(w) in SHELLS for w in words)


def _segments(tokens, redirects=None, piped=None):
    """Split tokens into simple commands. `redirects` collects (segment index, operator,
    target word) for every redirection, so a here-string fed to a shell and a command
    substitution in a target can be scanned. `piped` collects the index of every
    segment whose stdin is a pipe."""
    seg, out = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in SEPARATORS:
            if seg:
                out.append(seg)
                if t in ("|", "|&") and piped is not None:
                    piped.add(len(out))
            seg = []
        elif t in REDIRECTS:
            if seg and seg[-1].isdigit():
                seg.pop()  # fd number of 2>&1
            if redirects is not None and i + 1 < len(tokens):
                redirects.append((len(out), t, tokens[i + 1]))
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
    command strings to scan as well, script file run by a shell or None, the name of
    a wrapper that runs the command many times (xargs) or None)."""
    i, nested, rep = 0, [], None
    while i < len(argv):
        t = argv[i]
        b = _base(t)
        if ASSIGN_RE.match(t) or t in KEYWORDS:
            i += 1
        elif t == "command":
            i += 1
            while i < len(argv) and argv[i] == "-p":
                i += 1
            if i < len(argv) and argv[i] in ("-v", "-V"):
                return [], nested, None, rep  # a lookup, runs nothing
        elif b == "rtk":
            i += 2 if i + 1 < len(argv) and argv[i + 1] == "proxy" else 1
        elif b in WRAPPER_VALUE_OPTS:
            rep = rep or (b if b in REPEATERS else None)
            i = _skip_opts(argv, i + 1, WRAPPER_VALUE_OPTS[b])
            if b == "timeout" and i < len(argv):
                i += 1  # the duration
        elif b in NPX or (b in ("pnpm", "yarn") and argv[i + 1:i + 2] == ["dlx"]):
            i = _skip_opts(argv, i + (1 if b in NPX else 2), {"-p", "--package"})
            if i < len(argv) and argv[i].split("@")[0].lower() in TRIPO_NAMES:
                return ["tripo", *argv[i + 1:]], nested, None, rep
            return [], nested, None, rep
        elif b in SHELLS:
            # Walk all options like the shell does: -o/+o/-O/+O (also inside
            # combined flags such as -euo) take a value, and with -c anywhere
            # the first non-option argument is the command string; without -c
            # it is a script file.
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
            if j < len(argv):
                if has_c:
                    nested.append(argv[j])
                else:
                    return [], nested, argv[j], rep
            return [], nested, None, rep
        elif t in ("source", ".") and i + 1 < len(argv):
            return [], nested, argv[i + 1], rep
        elif t == "eval":
            nested.append(" ".join(argv[i + 1:]))
            return [], nested, None, rep
        else:
            break
    return argv[i:], nested, None, rep


def _script_mentions_tripo(path, cwd):
    """True when `path` (resolved against cwd) is a readable file that mentions tripo."""
    full = os.path.join(cwd or os.getcwd(), os.path.expanduser(path))
    try:
        with open(full, "rb") as f:
            return b"tripo" in f.read(SCRIPT_READ_LIMIT).lower()
    except OSError:
        return False


def _read_only(argv):
    b = _base(argv[0])
    return b in READ_ONLY or (b.startswith("python") and argv[1:3] == ["-m", "unittest"])


def _call(args, cwd, stdin=False):
    return {"args": args, "cwd": cwd, "stdin": stdin}


def _opaque(why):
    return {"opaque": why}


def tripo_calls(command, cwd=None, _tripo_in=None, _repeat=None):
    """Every tripo call in `command`: [{"args": args after the tripo program, "cwd",
    "repeat"}], plus {"opaque": reason, "repeat"} for a program the guard cannot see
    through (a `$VAR` program or a shell script that mentions tripo): those ask, never
    stay silent. "repeat" names why the call may run many times (a loop body, xargs,
    find -exec, a function called twice) or is None."""
    if _tripo_in is None:
        _tripo_in = "tripo" in command.lower()
    _, command, heredocs, subs = _scan(command)
    tokens = _lex(command)
    calls = []

    def sub(text, at=cwd, repeat=_repeat):
        return tripo_calls(text, at, _tripo_in, repeat)

    for body, quoted, line in heredocs:
        if _feeds_shell(re.split(r"[\s|;&()]+", line)):
            calls += sub(body)  # the shell runs the body
        elif not quoted:
            for s in _scan(body, heredoc_body=True)[3]:  # an unquoted delimiter keeps $(...) live
                calls += sub(s)
    redirects, piped = [], set()
    segments = _segments(tokens, redirects, piped)
    extra = {}  # segment index -> redirect targets
    for idx, op, word in redirects:
        extra.setdefault(idx, []).append(word)
        if op in STDIN_REDIRECTS:
            piped.add(idx)  # stdin comes from a file, heredoc or here-string
        if op == "<<<" and idx < len(segments) and _feeds_shell(segments[idx]):
            calls += sub(word)
    seen_subs = set()

    loop, braces, pending_func, invoked = 0, [], None, {}
    for index, seg in enumerate(segments):
        words, seg, header = seg + extra.get(index, []), list(seg), False
        if pending_func and seg[:1] != ["{"]:
            pending_func = None
        seg_repeat = False  # zsh `repeat N cmd`: this segment runs N times
        while seg:  # control words: track loops and function bodies
            w = seg[0]
            if w in LEAD_WORDS:
                seg.pop(0)  # `then for ...`, `do while ...`: look past it (R2)
            elif w in LOOP_WORDS:
                loop += 1
                if w in ("for", "select"):
                    header = True  # `for x in words`: the words are not a command
                    break
                seg.pop(0)
            elif w == "repeat":  # zsh (the Bash tool runs zsh here)
                seg = seg[2:]
                if seg[:1] == ["{"]:
                    loop += 1
                    braces.append(REPEAT_BRACE)
                    pending_func, seg = None, seg[1:]
                elif seg and seg[0] != "do":
                    seg_repeat = True  # short form
                else:
                    loop += 1  # `repeat N do ... done`, also with `do` on a later segment
            elif w == "done":
                loop = max(0, loop - 1)
                seg.pop(0)
            elif w == "{":
                braces.append(pending_func)
                pending_func = None
                seg.pop(0)
            elif w == "}":
                if braces and braces.pop() is REPEAT_BRACE:
                    loop = max(0, loop - 1)
                seg.pop(0)
            elif w == "function" and len(seg) > 1:
                pending_func, seg = seg[1], seg[2:]
                if seg[:1] == ["()"]:
                    seg.pop(0)
            elif len(seg) > 1 and seg[1] == "()":
                pending_func, seg = seg[0], seg[2:]
            else:
                break
        repeat = _repeat or ("döngü içinde" if loop or seg_repeat else None)
        func = next((f for f in reversed(braces) if isinstance(f, str)), None)
        found = []
        for n in (int(m) for w in words for m in SUB_RE.findall(w)):
            if n < len(subs) and n not in seen_subs:  # $(...) runs where its word is
                seen_subs.add(n)
                found += sub(subs[n], cwd, repeat)
        if not header:
            cwd, more, prog = _segment_calls(seg, cwd, _tripo_in, sub, repeat,
                                             index in piped)
            found += more
        else:
            prog = None
        for call in found:
            if func:
                call["func"] = func
        if prog:
            invoked.setdefault(prog, []).append(repeat)
        calls += found
    for n, body in enumerate(subs):  # a substitution outside every segment word
        if n not in seen_subs:
            calls += sub(body)
    for call in calls:  # a function body runs once per call of the function
        func = call.pop("func", None)
        runs = invoked.get(func, [])
        if func and not call.get("repeat") and (len(runs) > 1 or any(runs)):
            call["repeat"] = f"fonksiyon {func} birden çok kez çağrılıyor"
    return calls


def _segment_calls(seg, cwd, tripo_in, sub, repeat=None, stdin=False):
    """Calls in one simple command (`stdin`: fed by a pipe or redirect). Returns (cwd
    after it, calls, program name)."""
    argv, nested, script, rep = _unwrap(seg)
    repeat = repeat or (f"{rep} ile" if rep else None)
    calls = []
    for body in nested:
        calls += sub(body, cwd, repeat)
    if script is not None and _script_mentions_tripo(script, cwd):
        calls.append(_opaque(f"betik tripo içeriyor ({script})"))
    prog = argv[0] if argv else None
    if prog is None:
        pass
    elif prog == "cd":
        target = argv[1] if len(argv) > 1 else "~"
        if target != "-":
            cwd = os.path.join(cwd or os.getcwd(), os.path.expanduser(target))
    elif _is_tripo_word(prog):
        calls.append(_call(argv[1:], cwd, stdin))
    elif prog.startswith("$") and len(prog) > 1:
        if tripo_in:
            shown = SUB_RE.sub("$(…)", prog)
            calls.append(_opaque(f"program bir değişken ya da komut çıktısı ({shown}), "
                                 "tripo olabilir"))
    elif not _read_only(argv):
        # Fail closed: an unknown runner (mise exec, npm exec, find -exec, caffeinate,
        # watch, ...) is analysed from its first tripo word, or its first shell.
        if _base(prog) in REPEATERS:
            repeat = repeat or f"{_base(prog)} ile"
        for k in range(1, len(argv)):
            if _is_tripo_word(argv[k]):
                args = argv[k + 1:]
                calls.append(_call(args[1:] if args[:1] == ["--"] else args, cwd, stdin))
                break
            if _base(argv[k]) in SHELLS or argv[k] == "eval":
                calls += _segment_calls(argv[k:], cwd, tripo_in, sub, repeat, stdin)[1]
                break
    for call in calls:
        if repeat and not call.get("repeat"):
            call["repeat"] = repeat
    return cwd, calls, prog


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


def _step(what, kind=None, model=None, params=None, inp=None, multi=None):
    """One paid step; `multi` says why it actually starts many paid tasks."""
    return {"what": what, "multi": multi, "plan": None if kind is None else
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


def analyze(args, stdin=False):
    """Classify the args after `tripo`: {"steps": [paid steps], "globals", "make", "label"}.
    `stdin`: the call reads a pipe, file, heredoc or here-string."""
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
    if cmd == "mcp" and stdin:
        # JSON-RPC on stdin can call tripo_make: paid, price unknown (M9)
        steps = [_step("mcp (stdin'den JSON-RPC, tripo_make çağırabilir)")]
    elif cmd in FREE_TOP:
        steps = []
    elif cmd == "make":
        steps = _make_steps(pos, opts)
        out["make"] = rest
    elif cmd == "ai" and pos:
        steps = [_step(f"ai {' '.join(pos)}"[:80], multi="senaryo + zincir çalıştırır")]
    elif cmd in ("redo", "ai"):
        steps = [_step(f"{cmd} {' '.join(pos) or ('@last' if cmd == 'redo' else '')}".strip())]
    elif cmd == "batch" and pos[:1] == ["run"]:
        steps = [_step(f"batch run {' '.join(pos[1:])}".strip(),
                       multi="manifestteki her işi çalıştırır")]
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
    exe = _load_plan().tripo_bin()
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


FREE_DRY_STEPS = {"rig-check"}
FREE_TASK_TYPES = {"animate_prerigcheck"}
IMPORT_STEPS = {"import", "import_model"}


def dry_paid_steps(dry):
    """Names of the paid tasks a make dry-run plans: every step but rig-check, and one
    per extra candidate. tripo-cli updates itself, so a new default chain step shows up
    here before the guard's own parse knows it. The leading import of a local file is
    not counted: it is part of the one step the window shows (R1), and its price is in
    the dry-run estimate."""
    if not isinstance(dry, dict):
        return []
    steps = [st for st in dry.get("steps") or [] if isinstance(st, dict)]
    if steps and (steps[0].get("name") in IMPORT_STEPS
                  or steps[0].get("task_type") in IMPORT_STEPS):
        steps = steps[1:]
    names = [str(st.get("name")) for st in steps
             if st.get("name") not in FREE_DRY_STEPS
             and st.get("task_type") not in FREE_TASK_TYPES]
    cand = dry.get("candidates")
    if isinstance(cand, int) and not isinstance(cand, bool) and cand > 1 and names:
        names += [f"{names[0]} (aday {k})" for k in range(2, cand + 1)]
    return names


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
    _load_plan()
    try:
        calls = tripo_calls(command, cwd)
    except ParseError:
        if "tripo" in command.lower():
            return "ask", "Tripo kredi kilidi: komut ayrıştırılamadı, ücretli olabilir"
        return None
    found, opaque, many = [], [], []
    for call in calls:
        if "opaque" in call:
            opaque.append(call["opaque"])
            if call.get("repeat"):
                many.append(f"{call['opaque']} ({call['repeat']})")
            continue
        info = analyze(call["args"], call.get("stdin", False))
        for step in info["steps"]:
            found.append((step, info, call["cwd"]))
            why = step.get("multi") or call.get("repeat")
            if why:
                many.append(f"{step['what']} ({why})")
    if not found and not opaque:
        return None
    if many:
        return "deny", (f"{B17}: tek onay birden çok ücretli görevi başlatır: "
                        f"{'; '.join(many)}")
    if len(found) > 1:
        names = ", ".join(step["what"] for step, _, _ in found)
        return "deny", f"{B17}: bu komutta {len(found)} ücretli adım var ({names})"
    unseen = f"görülemeyen çağrı: {'; '.join(opaque)} (ücretli olabilir)" if opaque else None
    if not found:
        return "ask", " | ".join(["Tripo kredi kilidi", unseen,
                                  "tripo'yu düz `tripo …` ya da mutlak yolla çalıştır"])
    step, info, call_cwd = found[0]
    dry = make_dry_run(info["globals"], info["make"], call_cwd) \
        if info["make"] is not None else None
    planned = dry_paid_steps(dry)
    if len(planned) > 1:  # the CLI's own plan wins over our parse (M2, K13)
        return "deny", (f"{B17}: dry-run bu komutta {len(planned)} ücretli adım planlıyor "
                        f"({', '.join(planned)})")
    parts = ["Tripo kredi kilidi", f"adım: {step['what']}", estimate_text(step, info, dry),
             balance_text(info["globals"]), f"label: {info['label'] or 'yok'}"]
    if unseen:
        parts.append(unseen)
    return "ask", " | ".join(parts)


SHELL_HINT_RE = re.compile(r"(?:^|[\s;&|(`/])(?:bash|sh|zsh|dash|ksh|source|\.)\s", re.I)


def _worth_parsing(command):
    """Fast path: only a command that mentions tripo, or runs a shell (whose script
    file may call tripo), is parsed."""
    return "tripo" in command.lower() or bool(SHELL_HINT_RE.search(command))


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not _worth_parsing(command):
        return 0
    try:
        _load_plan()
    except BaseException as e:  # SyntaxError, ImportError, a sys.exit at import ...
        print(f"tripo_guard: cannot start: {type(e).__name__}: {e}", file=sys.stderr)
        if "tripo" in command.lower():
            _emit("ask", f"Tripo kredi kilidi başlatılamadı: {type(e).__name__}: {e}"[:300])
        return 0
    try:
        result = decide(command, event.get("cwd"))
    except Exception as e:  # never let a guard bug wave a paid call through
        print(f"tripo_guard: {type(e).__name__}: {e}", file=sys.stderr)
        result = ("ask", f"Tripo kredi kilidi: kilit hatası ({type(e).__name__}), "
                         "komut ücretli olabilir")
    if result:
        _emit(*result)
    return 0


def _emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": reason}}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
