"""The dev container's hooks for sibling checkouts: firewall domain lists and agent skills.

Neither hook names a sibling. Each must work when no sibling ships anything.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
FIREWALL = WS / ".devcontainer" / "init-firewall.sh"
SYNC = WS / "scripts" / "sync-skills.sh"


def read_domain_lists(*globs: str) -> subprocess.CompletedProcess:
    """Run only the function, extracted from the script, under the script's own shell options."""
    text = FIREWALL.read_text()
    start = text.index("read_domain_lists() {")
    body = text[start : text.index("\n}\n", start) + 3]
    # The globs go into the script unquoted, as the firewall script writes them: the shell
    # expands them at the call site, and one that matches nothing stays a literal pattern.
    script = "set -euo pipefail\n" + body + "read_domain_lists " + " ".join(globs) + "\n"
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def test_domains_are_read_from_every_matching_file(tmp_path):
    for repo, lines in (("a", "one.example.com\n# comment\n\n  two.example.com  # trailing\n"), ("b", "three.example.com\n")):
        target = tmp_path / repo / ".devcontainer" / "firewall-domains.txt"
        target.parent.mkdir(parents=True)
        target.write_text(lines)
    proc = read_domain_lists(str(tmp_path / "*" / ".devcontainer" / "firewall-domains.txt"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["one.example.com", "two.example.com", "three.example.com"]


def test_no_matching_file_is_not_an_error(tmp_path):
    proc = read_domain_lists(str(tmp_path / "*" / ".devcontainer" / "firewall-domains.txt"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


def test_firewall_script_names_no_internal_host():
    """Cloud control-plane endpoints, a cloud region and private siblings come from sibling lists."""
    text = FIREWALL.read_text()
    assert not re.findall(r'"[a-z0-9.-]+\.amazonaws\.com"', text)
    assert not re.findall(r"\b[a-z]{2}-(?:north|south|east|west|central)[a-z]*-\d\b", text)
    assert "devops" not in text


def test_skills_are_linked_from_sibling_checkouts(tmp_path):
    root = tmp_path / "root"
    (root / "labs64.io-workspace" / "scripts").mkdir(parents=True)
    (root / "labs64.io-workspace" / "scripts" / "sync-skills.sh").write_text(SYNC.read_text())
    for repo, skill in (("labs64.io-workspace", "shared"), ("other", "extra")):
        d = root / repo / ".agents" / "skills" / skill
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {skill}\n---\n")
    home = tmp_path / "home"
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(home / "claude"), "CODEX_HOME": str(home / "codex")}
    proc = subprocess.run(["bash", str(root / "labs64.io-workspace" / "scripts" / "sync-skills.sh")], env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    for tool in ("claude", "codex"):
        assert (home / tool / "skills" / "shared" / "SKILL.md").is_file()
        assert (home / tool / "skills" / "extra" / "SKILL.md").is_file()


def test_a_skill_whose_checkout_went_away_is_unlinked(tmp_path):
    root = tmp_path / "root"
    (root / "labs64.io-workspace" / "scripts").mkdir(parents=True)
    script = root / "labs64.io-workspace" / "scripts" / "sync-skills.sh"
    script.write_text(SYNC.read_text())
    (root / "labs64.io-workspace" / ".agents" / "skills").mkdir(parents=True)
    gone = root / "other" / ".agents" / "skills" / "extra"
    gone.mkdir(parents=True)
    (gone / "SKILL.md").write_text("---\nname: extra\n---\n")
    home = tmp_path / "home"
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(home / "claude"), "CODEX_HOME": str(home / "codex")}
    subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
    assert (home / "claude" / "skills" / "extra").is_symlink()
    (gone / "SKILL.md").unlink()
    gone.rmdir()
    subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
    assert not (home / "claude" / "skills" / "extra").is_symlink()
