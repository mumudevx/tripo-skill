"""Checks on SKILL.md: frontmatter, size, every script named, carry-forward rules.

The script list is the plan's File Structure (preflight ruling 14 <-> all):
dev tooling such as calibrate.py is not named in SKILL.md.
"""
import re
import unittest

from tests.util import ROOT, SCRIPTS

SKILL = ROOT / "SKILL.md"
MAX_LINES = 250
MAX_DESCRIPTION = 1024

# scripts/ entries of the plan's File Structure (data/*.json are data, not scripts)
FILE_STRUCTURE_SCRIPTS = (
    "common.py", "glbstat.py", "bl.py", "tripo_plan.py", "cli_watch.py",
    "hooks/tripo_guard.py",
    "blender/_io.py", "blender/skill_io.py", "blender/qa.py", "blender/render_sheet.py",
    "blender/fixkit/normals.py", "blender/fixkit/ops.py", "blender/normalize.py",
    "blender/apply_recipe.py", "blender/export.py",
    "preflight_ref.py", "blender/preflight_img.py",
    "profile.py", "asset_state.py", "log_asset.py", "godot_place.py",
    "godot/aabb.gd", "godot/rig_accept.gd", "lessons.py",
)

# rules later tasks' rulings bind into SKILL.md (Task 6 CV5, Task 9 CV1, Task 12 CV3)
CARRY_FORWARD = {
    "session start installs updates": "cli_watch.py check --update",
    "placement always applies the approved plan": "--expect <plan_sha256>",
    "normalize takes the swizzled Godot size": "normalize_target_size",
    "asset folder shared by raw files and provenance": "<art_source>/<kind>/<id>/",
    "lock detection": "tripo_guard",
    "skill patches go to proposals": "docs/proposals/",
    "QA details file": "qa/vNN/report.md",
    "batched question": "1A, 2B, 3 geç",
}


def read_skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict:
    """Top-level `key: value` pairs between the leading '---' fences."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError("SKILL.md must start with a '---' frontmatter fence")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise AssertionError("frontmatter has no closing '---'") from None
    out = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or line[0].isspace():
            raise AssertionError(f"frontmatter line is not 'key: value': {line!r}")
        out[key.strip()] = value.strip()
    return out


class SkillMdTest(unittest.TestCase):
    def test_frontmatter(self):
        meta = frontmatter(read_skill())
        self.assertEqual(meta.get("name"), "tripo-game-assets")
        desc = meta.get("description", "")
        if len(desc) >= 2 and desc[0] == desc[-1] and desc[0] in "\"'":
            desc = desc[1:-1]
        else:
            # a plain YAML scalar must not hold ': ' or start with a YAML indicator
            self.assertNotIn(": ", desc, "unquoted description must not contain ': '")
            self.assertNotIn(" #", desc, "unquoted description must not contain ' #'")
            self.assertFalse(desc[:1] in "!&*>|%@`'\"[{", "description starts with a YAML indicator")
        self.assertTrue(0 < len(desc) <= MAX_DESCRIPTION, f"description is {len(desc)} chars")
        # third person: no "I" / "you" voice
        self.assertIsNone(re.search(r"\b(I|you|your)\b", desc), "description must be third person")
        for trigger in ("placeholder", "Tripo", "GLB", "FBX", "rig", "credit", "CLI"):
            self.assertIn(trigger.lower(), desc.lower(), f"description lacks trigger {trigger!r}")

    def test_line_cap(self):
        n = len(read_skill().splitlines())
        self.assertLessEqual(n, MAX_LINES, f"SKILL.md has {n} lines")

    def test_mentions_every_script(self):
        text = read_skill()
        missing = [s for s in FILE_STRUCTURE_SCRIPTS if s.rsplit("/", 1)[-1] not in text]
        self.assertEqual(missing, [], "scripts not named in SKILL.md")

    def test_listed_scripts_exist(self):
        absent = [s for s in FILE_STRUCTURE_SCRIPTS if not (SCRIPTS / s).is_file()]
        self.assertEqual(absent, [], "File Structure scripts missing from scripts/")

    def test_references_named_exist(self):
        text = read_skill()
        named = set(re.findall(r"\b([a-z][a-z-]+\.md)\b", text)) - {"SKILL.md", "lessons.md",
                                                                      "general.md", "report.md"}
        absent = sorted(n for n in named if not (ROOT / "references" / n).is_file())
        self.assertEqual(absent, [], "SKILL.md names references that do not exist")
        every = sorted(p.name for p in (ROOT / "references").glob("*.md"))
        unnamed = [n for n in every if n not in named]
        self.assertEqual(unnamed, [], "references never pointed to from SKILL.md")

    def test_carry_forward_rules(self):
        text = read_skill()
        missing = [why for why, needle in CARRY_FORWARD.items() if needle not in text]
        self.assertEqual(missing, [], "SKILL.md lacks rules bound by earlier rulings")

    def test_no_higgsfield(self):
        # same rule as tests/test_references.py (K11), applied to SKILL.md itself
        self.assertNotIn("higgsfield", read_skill().lower())


if __name__ == "__main__":
    unittest.main()
