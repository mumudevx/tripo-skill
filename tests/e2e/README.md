# End-to-end behaviour test (0 credits)

Checks how an agent behaves with the installed skill, not what the scripts compute (the unit tests do that).

1. Scratch project: copy `tests/godot_min/` to a scratch dir, add `refs/tool_chest_ref.png` (a white-background
   3/4 render of a finished tool chest) and `tripo_result/tool_chest_g3.glb` (a real Tripo raw result), `git init`
   and commit, so every write shows in `git status`.
2. Snapshot outside state: game repos' `git status` (checksums of already-modified files), `~/.claude/settings.json`
   sha, the skill repo's `git status`.
3. Dispatch a fresh agent with only: use the tripo-game-assets skill; turn the `Crate` placeholder into a tool chest
   with that reference; the raw result already exists, do not generate. Scripted replies: front "evet, doğru",
   profile "önerdiğin varsayılanlar olsun", fixes = the free option, placement = not approved. It writes every
   user-facing message to a transcript.
4. Check: preflight before any paid command; paid commands single-step with `--model` and `--name` (none expected);
   QA + render sheet; fix report <= 6 lines + one table + one batched question; no question about free actions;
   front axis confirmed inside the QA report; placement shown as a diff, not applied; a project lesson written;
   no write outside the scratch project, the skill's `.state.json` and `docs/proposals/`.
