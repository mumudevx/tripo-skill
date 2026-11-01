# Lessons: format, scope, promotion, staleness

When to read this: at session start (read both lesson files), and in phase 9 (end of task: write lessons, offer promotions); also after `cli_watch.py` reports a new CLI or model version.

## 1. Two layers (spec 17.1)

| layer | file | written |
|---|---|---|
| project | `<project>/.claude/tripo/lessons.md` | by default, without asking: project scope, reversible |
| general | `<skill>/lessons/general.md` (user-private, git-ignored; created from `lessons/general.example.md`) | only by `lessons.py promote --approved`, after the user said yes in this session (K4) |

Reading order: at every session start read the project file, then the general file, and apply each lesson in its phase. When they conflict, **the project lesson wins**. A lesson marked `needs_reverify` is read as a warning, never as a rule, until it is confirmed again.

## 2. Block format (exactly what `scripts/lessons.py` parses)

```
## L<n>: <title>
- rule: <one line>
- evidence: <asset, task_id, date>
- scope: project | general
- cli: <tripo-cli version>
- model: <wire model id>
- confidence: <times confirmed>
- status: active | promoted | needs_reverify
- date: <YYYY-MM-DD, last confirmed>
- source: <project L<n>>            (general.md only)
```

- Never hand-write a block: `lessons.py` numbers it, keeps the key order and keeps lines it does not own. A hand-made block that differs from this format is silently skipped by `candidates` and `stale`.
- `cli` is the tripo-cli version (`0.9.0`) and `model` the wire model id (`v3.1-20260211`, `v3.0-20260909` for a rig lesson). A lesson that holds for every version uses `any` for both (also accepted: `-`, `none`, `n/a`); `stale` never marks such a lesson.
- Keep the rule to one line, in English, stated as an instruction ("Generate hard-surface parts without face_limit, then decimate v3.0 + smart_uv").
- Evidence names the asset, the Tripo task id and the date, with the measured number when there is one ("tool_chest, 3f2c..., 2026-11-02: 17430 tris for face_limit 8000").

## 3. Commands

```
python3 scripts/lessons.py add --project <P> --title "<title>" --rule "<rule>" --evidence "<asset, task_id, date>" --cli 0.9.0 --model v3.1-20260211 [--scope general]
python3 scripts/lessons.py candidates --project <P>
python3 scripts/lessons.py promote --project <P> --id <n> --approved
python3 scripts/lessons.py stale --cli <version> --model <wire id> [--model <wire id> ...] [--project <P>]
```

Every command also takes `--state FILE` and `--general FILE` (tests use them so the real skill state is never touched). Output is one JSON line.

- **add** appends a block to the project file. A lesson with the same title is **confirmed** instead: `confidence` + 1, `evidence`, `cli`, `model` and `date` refreshed, `needs_reverify` back to `active`. It also registers the project in `<skill>/.state.json` `projects` (used for the repeat check).
- **candidates** lists the project's `active` lessons that may become general:
  - the title and rule contain no game-specific term: words of `profile.json` `art_style`, words of `naming.model_pattern` (placeholders and extension removed), asset ids (file names under `assets/`), the game's name (`config/name` in `project.godot`, and the folder name), and budget numbers from `profile.json` `budgets`; evidence is not scanned, since it always names an asset;
  - or the same title or rule appears in another registered project's `lessons.md`, even with game terms in it.
  - `excluded` lists the rest with the terms that kept them out.
- **promote** refuses without `--approved` (exit 2) and an unknown id exits 3. It appends the lesson to `general.md` (or confirms the one with the same title there), with `source: <project L<n>>`, and marks the project copy `promoted`.
- **stale** marks `active` lessons `needs_reverify` in `general.md`, in every registered project and in `--project`, when the lesson's `cli` differs from `--cli`, or when its `model` is the same family with another date (`v3.1-20250101` vs `v3.1-20260211`). Lessons of other model families are untouched. `promoted` project copies are skipped (the general copy carries the status).

## 4. When to write a lesson (phase 9)

Write a project lesson, without asking, whenever a step taught something measurable:

- a measured number that differs from the plan (triangles vs `face_limit`, real credits vs estimate, the import price);
- a QA finding that a recipe fixed, and the recipe that did it;
- an image problem that caused a defect (and the prompt that fixed it);
- a first-paid-run answer from `cli-updates.md` section 5 (A-pose vs T-pose, `spec` for Godot, delight effect);
- a user preference that the profile does not hold.

Not a lesson: anything already in `profile.json` (budgets, naming, style), a one-off accident, a fact already in the references.

## 5. Promotion (spec 17.2 rule 2, K4)

At the end of the task, run `candidates` and put every candidate into **one** Turkish message ("Bu dersler genel olsun mu? 1) ... 2) ..."), answered in one reply. Promote only the ones the user approves, with `--approved`. Never promote silently, never promote because a candidate looks general, never ask twice for a lesson the user declined (note the refusal in the asset's `decisions`).

## 6. Staleness (spec 17.2 rule 4)

When `cli_watch.py check` reports a new installed version, or a lesson's model id differs from the one now pinned in the profile, run `stale` with the new CLI version and the current wire ids of every model the skill uses (generation, texture, rig). Marked lessons stay as warnings until a later run confirms them with `add` (same title).

## 7. Lessons vs skill patches (spec 17.3)

A lesson changes what the agent does for one project or user. A change to the skill itself ("add this check to the QA list", "this threshold is wrong", "this reference is out of date") is a **proposal**: write `~/Desktop/tripo-skill/docs/proposals/<YYYY-MM-DD>-<topic>.md` with the reason, the evidence and the diff. It is applied and committed only when the user asks (no AI attribution in the commit).

## 8. Seed lesson

`lessons/general.md` starts with one user-sourced lesson (K16): parts come only from Tripo (`generate_parts`, or one piece + `segment`/`smartsegment`), never from one image and one generation per part, because such parts did not fit together or look like one family. It uses `scope: general`, `cli: any`, `model: any`, `status: active`.
