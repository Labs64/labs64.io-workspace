#!/usr/bin/env bash
# Copies a developer's own personal skills (real, non-symlinked skill directories in Claude
# Code's or Codex CLI's user-level skills directories) into this repo's .agents/skills/, so
# they can be reviewed and committed as ecosystem-wide skills. Only copies. Never touches or
# removes the source, and never overwrites an existing shared skill.
#
# Run on demand via `just import-skills`, after adding a personal skill locally. Follow up
# with `just sync-skills` once an imported skill has been reviewed/committed, so it starts
# being symlinked back like any other shared skill.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DEST="$(cd "$SCRIPT_DIR/../.agents/skills" && pwd)"

imported=0
for skills_dir in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "${CODEX_HOME:-$HOME/.codex}/skills"; do
  [ -d "$skills_dir" ] || continue

  for skill_dir in "$skills_dir"/*/; do
    [ -d "$skill_dir" ] || continue
    [ -L "${skill_dir%/}" ] && continue          # skip our own shared-skill symlinks
    [ -f "${skill_dir}SKILL.md" ] || continue    # skip .system/, .curated/, non-skill dirs
    name="$(basename "$skill_dir")"
    dest="$SKILLS_DEST/$name"
    if [ -e "$dest" ]; then
      echo "Skipping $name: already exists in .agents/skills/" >&2
      continue
    fi
    echo "Importing $name from $skill_dir..."
    cp -R "${skill_dir%/}" "$dest"
    imported=$((imported + 1))
  done
done

if [ "$imported" -eq 0 ]; then
  echo "No new personal skills found to import."
else
  echo "Imported $imported skill(s) into .agents/skills/. Review, then commit and run 'just sync-skills'."
fi
