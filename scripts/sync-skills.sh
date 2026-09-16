#!/usr/bin/env bash
# Symlinks each shared skill (.agents/skills/<name>/SKILL.md) individually, by name, into
# Claude Code's and Codex CLI's user-level skills directories ($CLAUDE_CONFIG_DIR/skills,
# $CODEX_HOME/skills).
#
# Each skill is linked on its own because both tools also auto-manage their own content in
# that same directory (Codex writes .system/, .curated/ there). Aliasing the whole directory
# would let that content leak into this repo and make Codex's internal skills visible to
# Claude Code. The target is user-level because neither tool walks up past a repo's own git
# boundary, and neither exposes a persistable config for extra skill-search paths. See
# AGENTS.md's "Skills" section for the full rationale.
#
# Run at devcontainer boot (.devcontainer/post-create.sh) and on demand via `just sync-skills`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$(cd "$SCRIPT_DIR/../.agents/skills" && pwd)"

echo "Syncing shared skills into Claude Code and Codex CLI (user-level)..."
for skills_dir in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "${CODEX_HOME:-$HOME/.codex}/skills"; do
  mkdir -p "$skills_dir"

  # Drop symlinks pointing at shared skills that no longer exist (renamed or removed).
  find "$skills_dir" -maxdepth 1 -type l -print0 | while IFS= read -r -d '' link; do
    case "$(readlink "$link")" in
      "$SKILLS_SRC"/*) [ -e "$link" ] || rm "$link" ;;
    esac
  done

  # Link every shared skill individually, by name. Skips .system/, .curated/ and any other
  # non-skill entries (they hold subdirectories with SKILL.md, not one directly).
  for skill_dir in "$SKILLS_SRC"/*/; do
    [ -f "${skill_dir}SKILL.md" ] || continue
    name="$(basename "$skill_dir")"
    dest="$skills_dir/$name"
    if [ -e "$dest" ]; then
      if [ -L "$dest" ]; then
        case "$(readlink "$dest")" in
          "$SKILLS_SRC"/*) : ;;  # ours from a previous run, safe to relink
          *)
            echo "  Skipping $dest: an unrelated symlink with this name already exists" >&2
            continue
            ;;
        esac
      else
        echo "  Skipping $dest: a personal skill with this name already exists" >&2
        continue
      fi
    fi
    ln -sfn "${skill_dir%/}" "$dest"
  done
done
