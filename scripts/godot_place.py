#!/usr/bin/env python3
"""Godot placement: measure a placeholder, plan and apply the model swap, check a rig.

  godot_place.py aabb <project> <scene> <node> [--godot BIN]
  godot_place.py plan <project> <asset.json> <model.glb> [--copy-to REL] [--godot BIN]
  godot_place.py apply <project> <asset.json> <model.glb> --expect SHA [--copy-to REL] [--godot BIN]
  godot_place.py rig_accept <project> <model.glb> [--godot BIN]

aabb     {"size", "center", "bottom_center", "yaw_deg", "normalize_target_size", ...} of a node,
         measured headless by scripts/godot/aabb.gd. `size` is in the node's own axes (Godot,
         Y up); `normalize_target_size` is the same size in normalize.py's Blender order
         (gx, gz, gy): pass that one to `normalize.py --target-size`, never `size`.
plan     what apply would do, without writing anything: `copy_to` (from profile naming, or
         --copy-to), `copy_to_exists` and `copy_to_sha256` (a file already at copy_to, which apply
         overwrites), `import_params`, `scene_diff` (unified diff of the scene), `before_after`
         (size / position / yaw of placeholder vs model), `warnings`, `plan_sha256` (covers
         copy_to_exists and copy_to_sha256 too). Warnings: a different file at copy_to, a size
         mismatch (with the normalize.py --target-size X,Y,Z hint, or, when the model already fills
         the placeholder on its fitting axis, the two aspect ratios instead) and every kept
         CollisionShape3D that no longer fits the model (> 25% larger or smaller on an axis; never
         changed automatically). In generator_script mode
         (spec B19) there is no scene diff: `generator_hint` names the generator file and the
         lines that place this asset; the agent edits it and shows that diff.
apply    recomputes the plan, refuses when --expect (required: the plan_sha256 of the plan the
         user approved) does not match its plan_sha256, then copies
         the model, writes the .import params, writes the scene (scene_swap) and runs
         `godot --headless --import`, the generator (generator_script) and every profile
         check_commands entry from the project root. Any failure exits 5 with the output tail.
rig_accept  skeleton count, bones, single root, max skin influences, animations and a humanoid
         bone-name match (reported, not judged); verdict fail (exit 5) when skeletons != 1, the
         skeleton has more than one root bone, or a vertex has more than 4 influences.

Scene swap (spec 16.1, K6): the placeholder node keeps its path, name, type, unique_id, script,
transform, collision and socket children. When it is a MeshInstance3D, its mesh (and skin and
material overrides) moves to a new hidden child `<name>_placeholder`; when it is a container,
its direct visual children are hidden and renamed `<child>_placeholder` (the plan warns about
every project .gd that reaches one of them by name: `$Child`, `get_node("Child")`, `%Child`).
Nothing is deleted.
The model goes in as a child scene instance `Model`, base centre on the placeholder's base centre.

Godot binary: --godot, else $GODOT, else profile engine.binary, else what profile.py detects.
Output: one JSON line. Exit codes: see common.py.
"""
import argparse
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asset_state  # noqa: E402
import common  # noqa: E402
import glbstat  # noqa: E402
import profile as project_profile  # noqa: E402  (scripts/profile.py, not the stdlib module)

HELPERS = Path(__file__).resolve().parent / "godot"
MARK = "TRIPO_JSON:"
IMPORT_PARAMS = {"gltf/embedded_image_handling": 1, "meshes/ensure_tangents": True,
                 "meshes/generate_lods": True, "nodes/apply_root_scale": True}
MESH_KEYS = ("mesh", "skin", "skeleton", "material_override", "material_overlay")
VISUAL_TYPES = {"MeshInstance3D", "MultiMeshInstance3D", "Sprite3D", "AnimatedSprite3D", "Label3D",
                "CSGBox3D", "CSGCylinder3D", "CSGSphere3D", "CSGTorus3D", "CSGPolygon3D",
                "CSGMesh3D", "CSGCombiner3D"}
MAX_INFLUENCES = 4
SIZE_TOLERANCE = 0.10
FIT_TOLERANCE = 0.02        # the model already fills the placeholder on its fitting axis
COLLISION_LARGER = 0.25     # a kept collision this much larger than the model on an axis is flagged
TAIL_LINES = 40
GODOT_TIMEOUT = 900
CHECK_TIMEOUT = 1800


class PlaceError(Exception):
    def __init__(self, code, msg, **extra):
        super().__init__(msg)
        self.code, self.extra = code, extra


# ---------- .tscn text model (lossless: parse(text).render() == text) ----------

SECTION_RE = re.compile(r"\[(gd_scene|gd_resource|ext_resource|sub_resource|node|connection|editable|resource)\b")
PROP_RE = re.compile(r"([A-Za-z_][\w/:.\-]*) = ")


def _depth_after(line: str, depth: int, in_str: bool):
    esc = False
    for ch in line:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    return depth, in_str


def parse_attrs(header: str) -> dict:
    """Attributes of a section header line, values kept as raw text (strings unquoted)."""
    inner = header.strip()[1:-1]
    _kind, _, rest = inner.partition(" ")
    attrs, i, n = {}, 0, len(rest)
    while i < n:
        while i < n and rest[i] == " ":
            i += 1
        eq = rest.find("=", i)
        if eq < 0:
            break
        key, j, depth, in_str = rest[i:eq].strip(), eq + 1, 0, False
        while j < n and (in_str or depth or rest[j] != " "):
            depth, in_str = _depth_after(rest[j], depth, in_str)
            j += 1
        val = rest[eq + 1:j]
        attrs[key] = val[1:-1] if len(val) >= 2 and val[0] == val[-1] == '"' else val
        i = j
    return attrs


class Section:
    def __init__(self, header: str, body: list):
        self.header, self.body = header, body
        self.kind = SECTION_RE.match(header).group(1)

    @property
    def attrs(self) -> dict:
        return parse_attrs(self.header)

    def set_attr(self, key: str, value: str, quoted=True) -> None:
        raw = f'"{value}"' if quoted else value
        m = re.search(rf'(?<=[\s\[]){re.escape(key)}=("(?:[^"\\]|\\.)*"|[^\s\]]+)', self.header)
        if not m:
            raise PlaceError(common.EXIT_INTERNAL, f"no {key}= in {self.header.strip()}")
        self.header = self.header[:m.start(1)] + raw + self.header[m.end(1):]

    def props(self):
        """(key, first line index, end index) of every property in the body."""
        out, i, n = [], 0, len(self.body)
        while i < n:
            m = PROP_RE.match(self.body[i])
            if not m:
                i += 1
                continue
            j, (depth, in_str) = i, _depth_after(self.body[i], 0, False)
            while (depth > 0 or in_str) and j + 1 < n:
                j += 1
                depth, in_str = _depth_after(self.body[j], depth, in_str)
            out.append((m.group(1), i, j + 1))
            i = j + 1
        return out

    def get(self, key: str):
        for k, a, b in self.props():
            if k == key:
                return "".join(self.body[a:b]).split(" = ", 1)[1].rstrip("\n")
        return None

    def pop_props(self, want) -> list:
        """Remove the properties for which want(key) is true; return their lines in order."""
        taken, keep, spans = [], [], [(a, b) for k, a, b in self.props() if want(k)]
        for idx, line in enumerate(self.body):
            (taken if any(a <= idx < b for a, b in spans) else keep).append(line)
        self.body = keep
        return taken

    def set_prop(self, key: str, value: str, after=("transform",)) -> None:
        """Replace `key`, or insert it after the first `after` property (else after the last one)."""
        spans = self.props()
        for k, a, b in spans:
            if k == key:
                self.body[a:b] = [f"{key} = {value}\n"]
                return
        at = next((b for k, a, b in spans if k in after), spans[-1][2] if spans else 0)
        self.body.insert(at, f"{key} = {value}\n")


class Node:
    def __init__(self, section: Section):
        self.section = section
        a = section.attrs
        self.name, self.type, self.parent = a.get("name"), a.get("type"), a.get("parent")
        self.unique_id, self.instance = a.get("unique_id"), a.get("instance")

    @property
    def path(self) -> str:
        if self.parent is None:
            return "."
        return self.name if self.parent == "." else f"{self.parent}/{self.name}"


def child_parent_attr(path: str) -> str:
    return "." if path == "." else path


def in_subtree(path: str, top: str) -> bool:
    return top == "." or path == top or path.startswith(top + "/")


def node_arg(node: str) -> str:
    """Node path as the scene file writes it: '.' for the root, no leading './'."""
    node = (node or ".").strip()
    return node[2:] if node.startswith("./") else (node or ".")


class Scene:
    def __init__(self, preamble: list, sections: list):
        self.preamble, self.sections = preamble, sections
        self.issued = set()  # unique_ids handed out for sections not inserted yet

    @classmethod
    def parse(cls, text: str) -> "Scene":
        preamble, sections, depth, in_str = [], [], 0, False
        for line in text.splitlines(keepends=True):
            if depth == 0 and not in_str and SECTION_RE.match(line):
                sections.append(Section(line, []))
            elif sections:
                sections[-1].body.append(line)
            else:
                preamble.append(line)
            depth, in_str = _depth_after(line, depth, in_str)
        return cls(preamble, sections)

    def render(self) -> str:
        return "".join(self.preamble) + "".join(s.header + "".join(s.body) for s in self.sections)

    def nodes(self) -> list:
        return [Node(s) for s in self.sections if s.kind == "node"]

    def node(self, path: str):
        return next((n for n in self.nodes() if n.path == path), None)

    def insert_after(self, anchor: Section, new: list) -> None:
        if not anchor.body or anchor.body[-1].strip():
            anchor.body.append("\n")
        idx = self.sections.index(anchor) + 1
        self.sections[idx:idx] = new
        last = self.sections[-1]
        while last.body and not last.body[-1].strip():
            last.body.pop()

    def ext_resource_id(self, res_path: str) -> str:
        """Id of the PackedScene ext_resource for res_path; adds the section when missing."""
        exts = [s for s in self.sections if s.kind == "ext_resource"]
        for s in exts:
            if s.attrs.get("path") == res_path:
                return s.attrs["id"]
        used = {s.attrs.get("id") for s in exts}
        k = len(exts) + 1
        while f"{k}_model" in used:
            k += 1
        eid = f"{k}_model"
        anchor = exts[-1] if exts else self.sections[0]
        self.insert_after(anchor, [Section(f'[ext_resource type="PackedScene" path="{res_path}" id="{eid}"]\n', ["\n"])])
        head = self.sections[0]
        steps = head.attrs.get("load_steps")
        if head.kind == "gd_scene" and steps and steps.isdigit():
            head.set_attr("load_steps", str(int(steps) + 1), quoted=False)
        return eid

    def new_unique_id(self, seed: str):
        used = {n.unique_id for n in self.nodes() if n.unique_id}
        if not used:
            return None  # the scene does not use unique_id; Godot assigns them on save
        used |= self.issued
        val = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % (2 ** 31 - 2) + 1
        while str(val) in used:
            val = val % (2 ** 31 - 2) + 1
        self.issued.add(str(val))
        return str(val)


def unified_diff(old: str, new: str, label: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile=f"a/{label}", tofile=f"b/{label}"))


def _num(v: float) -> str:
    v = round(v, 6)
    if v == int(v):
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")


def transform_text(basis_diag, origin) -> str:
    sx, sy, sz = basis_diag
    vals = (sx, 0, 0, 0, sy, 0, 0, 0, sz, *origin)
    return "Transform3D(" + ", ".join(_num(v) for v in vals) + ")"


def swap_scene(text: str, scene_label: str, node_path: str, res_path: str, model_origin, model_scale,
               renamed=None):
    """(new text, warnings) for the placeholder swap. Raises PlaceError when the node cannot be
    swapped safely. A list passed as `renamed` receives (old name, new name) of every child the
    container swap renames."""
    scene = Scene.parse(text)
    ph = scene.node(node_path)
    if ph is None:
        raise PlaceError(common.EXIT_NOT_FOUND, f"node {node_path!r} not found in {scene_label}")
    if ph.instance:
        raise PlaceError(common.EXIT_CHECK, f"placeholder {node_path!r} is an instanced scene "
                                            f"({ph.instance}); place the model inside that scene instead")
    children = [n for n in scene.nodes() if n.parent == child_parent_attr(ph.path) and n.path != ph.path]
    model = next((n for n in children if n.name == "Model"), None)
    if model is not None:
        ext = re.fullmatch(r'ExtResource\("([^"]+)"\)', model.instance or "")
        target = next((s.attrs.get("path") for s in scene.sections
                       if s.kind == "ext_resource" and ext and s.attrs.get("id") == ext.group(1)), None)
        if target == res_path:
            return text, [f"{node_path} already holds Model -> {res_path}; the scene stays as it is "
                          f"(only the model file and its import settings are updated)"]
        raise PlaceError(common.EXIT_CHECK, f"{node_path} already has a Model child "
                                            f"(instance of {target or model.instance}); remove or rename it first")
    names = {n.name for n in children}
    warnings = []
    parent_attr = child_parent_attr(ph.path)
    subtree = [n for n in scene.nodes() if in_subtree(n.path, ph.path)]
    new_sections = []
    if ph.type == "MeshInstance3D":
        moved = ph.section.pop_props(lambda k: k in MESH_KEYS or k.startswith("surface_material_override/"))
        if not moved:
            raise PlaceError(common.EXIT_CHECK, f"placeholder {node_path!r} is a MeshInstance3D without a mesh")
        if f"{ph.name}_placeholder" in names:
            raise PlaceError(common.EXIT_CHECK, f"{node_path} already has a child {ph.name}_placeholder; "
                                                f"a swap was started before: check the scene by hand")
        uid = scene.new_unique_id(f"{scene_label}:{ph.path}:{ph.name}_placeholder")
        head = f'[node name="{ph.name}_placeholder" type="MeshInstance3D" parent="{parent_attr}"'
        head += f" unique_id={uid}]\n" if uid else "]\n"
        new_sections.append(Section(head, ["visible = false\n", *moved, "\n"]))
    else:
        visuals = [n for n in children if n.type in VISUAL_TYPES and not n.instance
                   and not n.name.endswith("_placeholder")]
        if not visuals:
            raise PlaceError(common.EXIT_CHECK, f"placeholder {node_path!r} ({ph.type}) has no visual child to hide")
        clash = sorted(f"{v.name}_placeholder" for v in visuals if f"{v.name}_placeholder" in names)
        if clash:
            raise PlaceError(common.EXIT_CHECK, f"{node_path} already has {', '.join(clash)}; check the scene by hand")
        for v in visuals:
            old_path, new_name = v.path, f"{v.name}_placeholder"
            new_path = f"{v.parent}/{new_name}" if v.parent != "." else new_name
            v.section.set_attr("name", new_name)
            v.section.set_prop("visible", "false")
            if renamed is not None:
                renamed.append((old_path.rsplit("/", 1)[-1], new_name))
            for n in scene.nodes():
                if n.parent and in_subtree(n.parent, old_path):
                    n.section.set_attr("parent", new_path + n.parent[len(old_path):])
            for s in scene.sections:
                if s.kind == "connection":
                    for key in ("from", "to"):
                        p = s.attrs.get(key)
                        if p and in_subtree(p, old_path) and p != ".":
                            s.set_attr(key, new_path + p[len(old_path):])
            if re.search(rf'NodePath\("[^"]*\b{re.escape(v.name)}\b', text):
                warnings.append(f"a NodePath in {scene_label} may name {v.name!r}, which is now {new_name!r}; check it")
    eid = scene.ext_resource_id(res_path)
    uid = scene.new_unique_id(f"{scene_label}:{ph.path}:Model")
    head = f'[node name="Model" parent="{parent_attr}"' + (f" unique_id={uid}" if uid else "")
    head += f' instance=ExtResource("{eid}")]\n'
    body = []
    if any(abs(v) > 1e-9 for v in model_origin) or any(abs(s - 1) > 1e-9 for s in model_scale):
        body.append(f"transform = {transform_text(model_scale, model_origin)}\n")
    new_sections.append(Section(head, body + ["\n"]))
    anchor = max((n.section for n in subtree), key=scene.sections.index)
    scene.insert_after(anchor, new_sections)
    return scene.render(), warnings


SCRIPT_SKIP_DIRS = {".godot", ".git", ".claude", ".import", "addons"}
SCRIPT_HITS_SHOWN = 5


def script_refs(root: Path, renamed) -> list:
    """Warnings for project .gd scripts that reach a renamed child by name: `$Old`, `$"Old"`,
    `$Path/Old`, `get_node("Old")` / `get_node_or_null("…/Old")` and `%Old`. A grep, not a parse:
    each hit is a place to check, not proof of a break."""
    if not renamed:
        return []
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SCRIPT_SKIP_DIRS)
        files += [Path(dirpath, f) for f in sorted(filenames) if f.endswith(".gd")]
    out = []
    for old, new in renamed:
        n = re.escape(old)
        pat = re.compile(rf'\$"?(?:[\w/.]*/)?{n}(?![\w])|%"?{n}(?![\w])'
                         rf'|get_node(?:_or_null)?\(\s*["\'](?:[^"\'\n]*/)?{n}["\'/]')
        hits = []
        for f in files:
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            hits += [f"{f.relative_to(root).as_posix()}:{i}" for i, ln in enumerate(lines, 1) if pat.search(ln)]
        if hits:
            more = f" and {len(hits) - SCRIPT_HITS_SHOWN} more" if len(hits) > SCRIPT_HITS_SHOWN else ""
            out.append(f"script(s) reach {old!r} by name ({', '.join(hits[:SCRIPT_HITS_SHOWN])}{more}); the swap "
                       f"renames it to {new!r}, so those lookups would fail: update the scripts (or point them at "
                       f"Model) when applying")
    return out


# ---------- .import ----------

def _import_value(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def patch_import_text(text, params: dict) -> str:
    """The .import file with `params` set in [params]; a minimal scene .import when text is None.
    Every other line is kept."""
    if text is None:
        text = '[remap]\n\nimporter="scene"\nimporter_version=1\n\n[params]\n\n'
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "[params]"), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines += ["[params]\n", "\n"]
        start = len(lines) - 2
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    for key, val in params.items():
        new = f"{key}={_import_value(val)}\n"
        hit = next((i for i in range(start + 1, end) if lines[i].split("=", 1)[0] == key), None)
        if hit is not None:
            lines[hit] = new
        else:
            at = end
            while at > start + 1 and not lines[at - 1].strip():
                at -= 1
            lines.insert(at, new)
            end += 1
    return "".join(lines)


# ---------- GLB bounds (stdlib) ----------

def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _node_matrix(node: dict):
    if "matrix" in node:
        m = node["matrix"]  # column-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = node.get("translation", (0, 0, 0))
    qx, qy, qz, qw = node.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = node.get("scale", (1, 1, 1))
    r = [[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
         [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
         [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx], [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz], [0, 0, 0, 1]]


def glb_bounds(path: Path) -> dict:
    """{"size", "bottom_center"} of a GLB in glTF/Godot axes, from POSITION accessor min/max."""
    doc, _blob = glbstat.parse_glb(path.read_bytes())
    nodes, meshes, accessors = doc.get("nodes", []), doc.get("meshes", []), doc.get("accessors", [])
    scenes = doc.get("scenes") or [{"nodes": list(range(len(nodes)))}]
    roots = scenes[doc.get("scene", 0)].get("nodes", [])
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    stack = [(i, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) for i in roots]
    while stack:
        idx, parent = stack.pop()
        node = nodes[idx]
        world = _mat_mul(parent, _node_matrix(node))
        if "mesh" in node:
            for prim in meshes[node["mesh"]].get("primitives", []):
                acc = accessors[prim["attributes"]["POSITION"]]
                if "min" not in acc or "max" not in acc:
                    raise glbstat.GlbError("a POSITION accessor has no min/max")
                for corner in ((x, y, z) for x in (acc["min"][0], acc["max"][0])
                               for y in (acc["min"][1], acc["max"][1]) for z in (acc["min"][2], acc["max"][2])):
                    p = [sum(world[r][c] * corner[c] for c in range(3)) + world[r][3] for r in range(3)]
                    lo, hi = [min(a, b) for a, b in zip(lo, p)], [max(a, b) for a, b in zip(hi, p)]
        stack += [(c, world) for c in node.get("children", [])]
    if lo[0] == math.inf:
        raise glbstat.GlbError("the GLB has no mesh")
    size = [h - l for l, h in zip(lo, hi)]
    return {"size": [round(v, 6) for v in size],
            "bottom_center": [round((lo[0] + hi[0]) / 2, 6), round(lo[1], 6), round((lo[2] + hi[2]) / 2, 6)]}


# ---------- Godot runs ----------

def godot_binary(root: Path, arg=None, profile=None) -> str:
    cand = arg or os.environ.get("GODOT") or ((profile or {}).get("engine") or {}).get("binary") \
        or project_profile.detect_binary(root)
    path = shutil.which(cand) if cand else None
    if not path:
        raise PlaceError(common.EXIT_NOT_FOUND, f"Godot binary not found ({cand!r}); pass --godot, set $GODOT "
                                                f"or set engine.binary in the profile")
    return path


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def run_helper(binary: str, root: Path, helper: str, args: list) -> dict:
    cmd = [binary, "--headless", "--path", str(root), "--script", str(HELPERS / helper), "--", *map(str, args)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=GODOT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise PlaceError(common.EXIT_INTERNAL, f"{helper} timed out after {GODOT_TIMEOUT}s")
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith(MARK)), None)
    if line is None:
        raise PlaceError(common.EXIT_INTERNAL, f"{helper} printed no result (exit {proc.returncode})",
                         tail=_tail(proc.stdout + proc.stderr))
    data = json.loads(line[len(MARK):])
    if "error" in data:
        code = proc.returncode if proc.returncode in (2, 3, 5) else common.EXIT_INTERNAL
        raise PlaceError(code, data["error"])
    return data


def res_path(root: Path, scene: str) -> str:
    if scene.startswith("res://"):
        return scene
    p = Path(scene)
    rel = p.resolve().relative_to(root) if p.is_absolute() else p
    return "res://" + rel.as_posix()


def scene_file(root: Path, res: str) -> Path:
    path = root / res[len("res://"):]
    if not path.is_file():
        raise PlaceError(common.EXIT_NOT_FOUND, f"scene not found: {res} ({path})")
    return path


def measure(binary: str, root: Path, scene: str, node: str) -> dict:
    res = res_path(root, scene)
    scene_file(root, res)
    out = run_helper(binary, root, "aabb.gd", [res, node_arg(node)])
    gx, gy, gz = out["size"]
    out["normalize_target_size"] = [gx, gz, gy]
    return out


# ---------- plan / apply ----------

def load_inputs(a):
    root = common.require_project(a.project)
    profile = common.load_profile(root)
    asset_file = Path(a.asset).expanduser()
    if not asset_file.is_file():
        raise PlaceError(common.EXIT_NOT_FOUND, f"asset file not found: {a.asset}")
    asset = asset_state.read_asset_file(asset_file)
    for key in ("id", "class"):
        if not asset.get(key):
            raise PlaceError(common.EXIT_CHECK, f"{asset_file} has no {key!r}; it is not a complete asset/1 file")
    glb = Path(a.glb).expanduser().resolve()
    if not glb.is_file():
        raise PlaceError(common.EXIT_NOT_FOUND, f"model not found: {a.glb}")
    with open(glb, "rb") as f:
        head = f.read(4096)
    if glbstat.sniff_format(head) != "glb":
        raise PlaceError(common.EXIT_USAGE, f"{glb} is not a GLB (export it with blender/export.py first)")
    return root, profile, asset, glb


def generator_hint(root: Path, scene_res, asset_id: str, model_stem: str) -> dict:
    files = sorted((root / "scripts" / "dev").glob("generate_*_models.gd"))
    rel = [f.relative_to(root).as_posix() for f in files]
    chosen = None
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if scene_res and scene_res in text:
            chosen = f
            break
    if chosen is None:
        chosen = next((f for f in files if re.search(rf'"{re.escape(asset_id)}"',
                                                     f.read_text(encoding="utf-8", errors="replace"))), None)
    if chosen is None:
        return {"file": None, "symbols": [], "candidates": rel}
    lines = chosen.read_text(encoding="utf-8", errors="replace").splitlines()
    consts = set()
    for ln in lines:
        m = re.match(r"\s*const\s+(\w+)\b.*=\s*\"([^\"]*)\"", ln)
        if m and scene_res and m.group(2) == scene_res:
            consts.add(m.group(1))
    needles = [n for n in (scene_res, f'"{asset_id}"', model_stem) if n] + sorted(consts)
    symbols = [{"line": i, "text": ln.strip()} for i, ln in enumerate(lines, 1)
               if any(n in ln for n in needles)][:40]
    return {"file": chosen.relative_to(root).as_posix(), "symbols": symbols, "candidates": rel}


def build_plan(a, root, profile, asset, glb) -> dict:
    warnings = []
    copy_to = a.copy_to or common.model_dest(profile, asset["id"], asset["class"])
    if Path(copy_to).is_absolute() or ".." in Path(copy_to).parts:
        raise PlaceError(common.EXIT_USAGE, f"--copy-to must be a path inside the project (got {copy_to})")
    copy_res = "res://" + Path(copy_to).as_posix()
    mode = profile["placement_mode"]
    ph = asset.get("placeholder")
    if not ph and mode == "scene_swap":
        raise PlaceError(common.EXIT_NOT_FOUND,
                         f"asset {asset['id']!r} has no placeholder; set it with `asset_state.py update {root} "
                         f"{asset['id']} --set 'placeholder={{\"scene\": \"res://...\", \"node\": \"...\"}}'`")
    binary = godot_binary(root, a.godot, profile)
    bounds = glb_bounds(glb)
    glb_sha = hashlib.sha256(glb.read_bytes()).hexdigest()
    dest = root / copy_to
    dest_sha = hashlib.sha256(dest.read_bytes()).hexdigest() if dest.is_file() else None
    if dest.exists() and not dest.is_file():
        raise PlaceError(common.EXIT_CHECK, f"{copy_to} exists and is not a file; pass another --copy-to")
    if dest_sha is not None and dest_sha != glb_sha:
        warnings.append(f"{copy_to} already exists and is a different file (sha256 {dest_sha[:12]}): var olan "
                        f"dosyanın üzerine yazılacak; apply replaces it and nothing rolls back. Pass --copy-to "
                        f"to keep it")
    plan = {"ok": True, "mode": mode, "asset": asset["id"], "glb": str(glb),
            "glb_sha256": glb_sha, "copy_to_exists": dest_sha is not None, "copy_to_sha256": dest_sha,
            "copy_to": copy_to, "copy_to_res": copy_res, "import_file": copy_to + ".import",
            "import_params": dict(IMPORT_PARAMS), "scene": None, "node": None, "scene_diff": None,
            "placeholder": None, "model": bounds, "before_after": None}
    scene_res = res_path(root, ph["scene"]) if ph else None
    if ph:
        node = node_arg(ph["node"])
        m = measure(binary, root, scene_res, node)
        plan.update(scene=scene_res, node=node, placeholder=m)
        scale = [s if s > 1e-9 else 1.0 for s in m["scale"]]
        inv = [1 / s for s in scale]
        origin = [lb - i * b for lb, i, b in zip(m["local_bottom_center"], inv, bounds["bottom_center"])]
        plan["model_transform"] = {"origin": [round(v, 6) for v in origin], "scale": [round(v, 6) for v in inv]}
        plan["before_after"] = {"size": {"before": m["size"], "after": bounds["size"]},
                                "position": {"before": m["bottom_center"], "after": m["bottom_center"]},
                                "yaw": {"before": m["yaw_deg"], "after": m["yaw_deg"]},
                                "normalize_target_size": m["normalize_target_size"]}
        warnings += size_warnings(m, bounds["size"])
        if any(abs(v) > 0.01 * max(bounds["size"]) for v in bounds["bottom_center"]):
            warnings.append(f"model base centre is at {bounds['bottom_center']}, not the origin; "
                            f"the Model offset compensates")
        if mode == "scene_swap":
            path = scene_file(root, scene_res)
            old = path.read_text(encoding="utf-8")
            renamed = []
            new, w = swap_scene(old, scene_res, node, copy_res, origin, inv, renamed=renamed)
            warnings += w + script_refs(root, renamed)
            plan["scene_diff"] = unified_diff(old, new, scene_res)
            plan["_scene_text"] = (path, new)
    else:
        warnings.append("asset has no placeholder: no before/after table; set one to measure the target size")
    if mode == "generator_script":
        plan["generator_hint"] = generator_hint(root, scene_res, asset["id"], Path(copy_to).stem)
        if plan["generator_hint"]["file"] is None:
            warnings.append("no scripts/dev/generate_*_models.gd mentions this scene or asset; "
                            "find the generator by hand")
    plan["warnings"] = warnings
    digest = {k: plan.get(k) for k in ("mode", "copy_to", "copy_to_exists", "copy_to_sha256", "glb_sha256",
                                       "import_params", "scene", "node", "scene_diff", "model_transform")}
    plan["plan_sha256"] = hashlib.sha256(json.dumps(digest, sort_keys=True).encode()).hexdigest()
    return plan


def _aspect(size) -> str:
    big = max(size) or 1.0
    return " : ".join(f"{v / big:.2f}" for v in size)


def _fmt_size(size) -> str:
    return " x ".join(_num(v) for v in size)


def size_warnings(ph: dict, model_size) -> list:
    """Size and collision warnings of a plan. `ph` is the aabb result of the placeholder (Godot
    axes, metres, with its "collisions"); `model_size` is the model's size in the same frame."""
    out = []
    size = ph["size"]
    pairs = [(b, a) for b, a in zip(size, model_size)]
    off = [abs(a - b) / b for b, a in pairs if b > 1e-9]
    if any(o > SIZE_TOLERANCE for o in off):
        ratios = [a / b if b > 1e-9 else 0.0 for b, a in pairs]
        k = max(range(3), key=lambda i: ratios[i])          # the axis a uniform fit is decided by
        fitted = size[k] > 1e-9 and abs(model_size[k] - size[k]) / size[k] <= FIT_TOLERANCE + 1e-9
        if fitted:
            out.append(f"model size {_fmt_size(model_size)} m differs from the placeholder {_fmt_size(size)} m, "
                       f"but it already fills the placeholder on {'xyz'[k]} (uniform scale): the aspect differs, "
                       f"not the scale. Placeholder aspect x:y:z = {_aspect(size)}, model {_aspect(model_size)}. "
                       f"Re-normalizing changes nothing; accept the smaller footprint, fit by another axis "
                       f"(normalize.py --target-height), or resize the placeholder")
        else:
            out.append(f"model size {_fmt_size(model_size)} m differs from the placeholder {_fmt_size(size)} m by "
                       f"more than {int(SIZE_TOLERANCE * 100)}% on an axis; run normalize.py --target-size "
                       f"{','.join(_num(v) for v in ph['normalize_target_size'])} first")
    for col in ph.get("collisions") or []:
        c = col["size"]
        larger = [ax for ax, cv, mv in zip("xyz", c, model_size) if cv > mv * (1 + COLLISION_LARGER)]
        smaller = [ax for ax, cv, mv in zip("xyz", c, model_size) if cv < mv * (1 - FIT_TOLERANCE)]
        if larger or smaller:
            what = "; ".join(x for x in (
                f"larger than the model by more than {int(COLLISION_LARGER * 100)}% on {', '.join(larger)}"
                if larger else "",
                f"smaller than the model on {', '.join(smaller)}" if smaller else "") if x)
            out.append(f"collision {col['path']} ({col['shape']}, {_fmt_size(c)} m) no longer fits the model "
                       f"({_fmt_size(model_size)} m): {what}. The swap keeps it unchanged; resize it by hand "
                       f"after placement")
    return out


def public(plan: dict) -> dict:
    return {k: v for k, v in plan.items() if not k.startswith("_")}


def run_step(cmd, root: Path, timeout: int, shell=False):
    """(ok, output) of one command run from the project root; ERROR lines from Godot count as failure."""
    try:
        proc = subprocess.run(cmd, cwd=root, shell=shell, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return False, f"timed out after {timeout}s\n{(e.stdout or '')}{(e.stderr or '')}"
    out = proc.stdout + proc.stderr
    return proc.returncode == 0, out


def godot_errors(out: str) -> list:
    return [ln for ln in out.splitlines() if re.match(r"\s*(SCRIPT )?ERROR:", ln)]


def apply(a, root, profile, asset, glb) -> int:
    plan = build_plan(a, root, profile, asset, glb)
    if a.expect != plan["plan_sha256"]:
        common.fail(common.EXIT_CHECK, "the plan changed since it was shown (scene, model or profile differ); "
                                       "run plan again and show the new diff", plan=public(plan))
    written = []
    dest = root / plan["copy_to"]
    replaced = dest.exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (replaced and dest.read_bytes() == glb.read_bytes()):
        shutil.copyfile(glb, dest)
        written.append(plan["copy_to"])
    imp = root / plan["import_file"]
    old_imp = imp.read_text(encoding="utf-8") if imp.is_file() else None
    new_imp = patch_import_text(old_imp, IMPORT_PARAMS)
    if new_imp != old_imp:
        imp.write_text(new_imp, encoding="utf-8")
        written.append(plan["import_file"])
    if "_scene_text" in plan:
        path, text = plan["_scene_text"]
        if path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            written.append(path.relative_to(root).as_posix())
    result = {**public(plan), "replaced": replaced, "written": written, "steps": []}

    def failed(step, cmd, out):
        common.fail(common.EXIT_CHECK, f"{step} failed: {cmd}", step=step, tail=_tail(out),
                    **{k: v for k, v in result.items() if k not in ("ok",)})

    binary = godot_binary(root, a.godot, profile)
    steps = [("import", [binary, "--headless", "--path", str(root), "--import"], GODOT_TIMEOUT, False)]
    hint = plan.get("generator_hint") or {}
    if hint.get("file"):
        steps.append(("generator", [binary, "--headless", "--path", str(root), "--script", "res://" + hint["file"]],
                      GODOT_TIMEOUT, False))
    steps += [("check", cmd, CHECK_TIMEOUT, True) for cmd in profile["check_commands"]]
    for step, cmd, timeout, shell in steps:
        ok, out = run_step(cmd, root, timeout, shell)
        errors = godot_errors(out) if step != "check" else []
        shown = cmd if shell else " ".join(map(str, cmd))
        result["steps"].append({"step": step, "cmd": shown, "ok": ok and not errors})
        if not ok or errors:
            failed(step, shown, out)
    common.emit(result)
    return common.EXIT_OK


def rig_accept(a) -> int:
    root = common.require_project(a.project)
    glb = Path(a.glb).expanduser().resolve()
    if not glb.is_file():
        raise PlaceError(common.EXIT_NOT_FOUND, f"model not found: {a.glb}")
    profile = None
    if common.profile_path(root).is_file():
        profile = common.load_profile(root)
    out = run_helper(godot_binary(root, a.godot, profile), root, "rig_accept.gd", [glb])
    reasons = []
    if out["skeletons"] != 1:
        reasons.append(f"{out['skeletons']} skeletons (need exactly 1)")
    single_root = out["skeletons"] >= 1 and out["roots"] == 1
    if out["skeletons"] >= 1 and not single_root:
        reasons.append(f"{out['roots']} root bones (need 1)")
    if out["max_influences"] > MAX_INFLUENCES:
        reasons.append(f"a vertex has {out['max_influences']} bone influences (max {MAX_INFLUENCES})")
    verdict = "fail" if reasons else "pass"
    common.emit({"ok": verdict == "pass", "glb": str(glb), "skeletons": out["skeletons"], "bones": out["bones"],
                 "single_root": single_root, "max_influences": out["max_influences"],
                 "animations": out["animations"], "bonemap_auto": out["bonemap_auto"],
                 "verdict": verdict, "reasons": reasons})
    return common.EXIT_OK if verdict == "pass" else common.EXIT_CHECK


class Parser(argparse.ArgumentParser):
    def error(self, message):
        common.fail(common.EXIT_USAGE, f"usage: {message}")


def main(argv) -> int:
    p = Parser(prog="godot_place.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    s = sub.add_parser("aabb")
    s.add_argument("project")
    s.add_argument("scene")
    s.add_argument("node")
    for name in ("plan", "apply"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("asset")
        s.add_argument("glb")
        s.add_argument("--copy-to")
        if name == "apply":
            s.add_argument("--expect", required=True, help="plan_sha256 of the plan the user approved")
    s = sub.add_parser("rig_accept")
    s.add_argument("project")
    s.add_argument("glb")
    for s in sub.choices.values():
        s.add_argument("--godot", help="Godot binary")
    a = p.parse_args(argv)
    try:
        if a.cmd == "aabb":
            root = common.require_project(a.project)
            profile = common.load_profile(root) if common.profile_path(root).is_file() else None
            common.emit({"ok": True, **measure(godot_binary(root, a.godot, profile), root, a.scene, a.node)})
            return common.EXIT_OK
        if a.cmd == "rig_accept":
            return rig_accept(a)
        inputs = load_inputs(a)
        if a.cmd == "plan":
            common.emit(public(build_plan(a, *inputs)))
            return common.EXIT_OK
        return apply(a, *inputs)
    except PlaceError as e:
        common.fail(e.code, str(e), **e.extra)
    except (glbstat.GlbError, OSError, ValueError, KeyError) as e:
        common.fail(common.EXIT_INTERNAL, f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
