# tripo-game-assets

A Claude Code skill that turns Godot placeholders into game-ready 3D assets through [tripo-cli](https://www.npmjs.com/package/tripo-cli).

It checks reference images before any credit is spent, then plans and prices one paid Tripo step at a time behind a credit lock. Every result is measured and rendered in headless Blender, and you get free Blender fixes next to paid Tripo fixes. The approved model goes into the Godot scene as a diff, and lessons are recorded per project.

```
Godot placeholder -> reference check -> one paid Tripo step at a time -> Blender QA and fixes
                  -> rig (characters) -> placement in Godot -> lessons
```

The skill's own files are in English. Everything it says to the user is in Turkish.

## What it does

- **Image preflight (0 credits).** Checks the reference images before they go to Tripo and gives a ready fix prompt for each problem.
- **Planning and pricing.** Each step goes through `tripo_plan.py`, which runs the CLI's dry-run. It picks the model, face budget and texture settings from the asset class and the project profile, and shows the estimate next to your balance.
- **Credit lock.** A global `PreToolUse` hook (`scripts/hooks/tripo_guard.py`) opens a permission window for every paid `tripo` command. It denies commands it cannot price, such as loops, wrappers or two paid steps in one command.
- **Automatic QA (0 credits).** Headless Blender measures the triangle budget, normals, UVs, texture size, front axis and back-face copies, and renders a lit sheet the agent looks at.
- **Fix options.** Each finding gets an A option (a Blender recipe, 0 credits) and a B option (a Tripo step, with its price), answered in one batched question such as `1A, 2B, 3 geç`. Fixes are recipes replayed from the frozen raw model, never one-off scripts.
- **Rig and animation.** Tripo rig-check and rig for characters, with a Godot rig acceptance check. You are asked about animation every time.
- **Godot placement.** Normalizes size, yaw and pivot, exports the GLB and shows the scene change as a diff. It is applied only after you approve that diff.
- **Lessons.** Project lessons are written as soon as they are learned. A lesson is promoted to the general file only after you say yes.
- **CLI tracking.** Spots new tripo-cli versions, summarizes the changelog and re-runs golden dry-runs to catch behaviour drift.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.9+
- [tripo-cli](https://www.npmjs.com/package/tripo-cli) (`npm install -g tripo-cli@latest`), signed in with `tripo login`
- Blender, for QA, rendering and fixes (default `/opt/homebrew/bin/blender`)
- Godot 4, for placement and rig checks

## Install

Full steps are in [`docs/install.md`](docs/install.md). In short:

1. Link the repo as a skill: `ln -s <path to this repo> ~/.claude/skills/tripo-game-assets`
2. Copy `lessons/general.example.md` to `lessons/general.md` (gitignored, private to you).
3. Add the credit lock hook to `~/.claude/settings.json` (back up the file first).
4. Check it live: a paid `tripo make ...` must open the permission window, while `--dry-run --json` and `tripo balance` must not.

## Usage

Inside a Godot project, ask Claude Code something like:

- "Bu sahnedeki `Crate` placeholder'ını modele çevir, referans `refs/crate.png`"
- "Bu GLB'yi kontrol et: `raw/chest.glb`"
- "Karakteri rigle ve Godot'ya yerleştir"
- "Tripo kredim ne kadar kaldı?"

You can also call it as `/tripo-game-assets`. The full workflow, approval rules and hard rules are in [`SKILL.md`](SKILL.md).

Project data is stored in `<project>/.claude/tripo/` (`profile.json`, `lessons.md`, `ledger.jsonl`, `assets/<id>.json`). Raw Tripo output is kept frozen and read-only under the project's art source folder.

## Layout

| path | contents |
|---|---|
| `SKILL.md` | the skill itself: phases, approval rules, hard rules, script map |
| `references/` | docs the skill reads per phase (CLI, planning, preflight, QA, fixes, rigging, Godot, lessons) |
| `scripts/` | Python tools; `scripts/blender/` runs inside Blender via `bl.py`, `scripts/godot/` holds headless GDScript helpers |
| `scripts/data/` | prices, budgets and QA thresholds |
| `scripts/hooks/tripo_guard.py` | the credit lock hook |
| `lessons/` | general lessons template |
| `tests/` | unit and integration tests, plus an end-to-end agent check |
| `docs/` | design doc, plan, calibration and e2e records, install guide |
| `_research/` | the research notes behind the design |

## Tests

```
python3 -m unittest
```

The suite takes about 4 minutes. Blender, Godot and tripo tests skip when the binary is missing. Use `REQUIRE_TRIPO=1` before a merge or release so that a missing CLI fails the run. See [`tests/README.md`](tests/README.md).
