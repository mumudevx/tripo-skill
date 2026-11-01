# Install

Done once per machine. The skill writes nothing here on its own.

1. Link the skill:
   `ln -s ~/Desktop/tripo-skill ~/.claude/skills/tripo-game-assets`
2. Seed the general lessons (user-private, gitignored): copy `lessons/general.example.md` to `lessons/general.md`, then add the K16 seed lesson in the block format of `references/lessons-system.md` (`cli: any`, `model: any`, `source: user (K16)`).
3. Credit lock: back up `~/.claude/settings.json` to `~/.claude/settings.json.bak-tripo-guard`, then append this entry to the `PreToolUse` group with `"matcher": "Bash"`, after any existing hooks:

   ```json
   {
     "type": "command",
     "command": "f=~/.claude/skills/tripo-game-assets/scripts/hooks/tripo_guard.py; [ -f \"$f\" ] || exit 0; exec python3 \"$f\""
   }
   ```

   The file check matters. A bare `python3 <path>` exits 2 when the path is missing, and Claude Code treats exit 2 as a block, so every Bash call fails until the link exists. Create the symlink (step 1) before adding the hook.
4. Verify live: `tripo make "a crate" --model tripo-v3.1` must open the permission window (deny it); the same command with `--dry-run --json`, and `tripo balance`, must not.
5. `tripo --version` must work in a fresh shell. tripo-cli is a global npm package, so a Node version manager upgrade (mise, nvm) can drop it; reinstall with `npm install -g tripo-cli@latest`.
