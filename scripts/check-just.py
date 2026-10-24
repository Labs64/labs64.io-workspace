#!/usr/bin/env python3
"""Hold every justfile to the convention of docs/justfiles.md, and every `just <recipe>` to a recipe that exists.

    scripts/check-just.py                      # the labs64.io* repositories cloned next to this workspace
    scripts/check-just.py --repo labs64.io-x   # one of them (repeatable)
    just check-just
    just check-just --fix                      # rewrite every reference to a renamed recipe (just/renamed.just)

A repository adopts the convention by moving its recipes into `just/<group>.just`; from then on its justfiles must:

  - keep only settings, variables, `default`, imports and modules in the root `justfile`;
  - give every public recipe a description and the `[group]` of the file it lives in (the table in docs/justfiles.md);
  - have the reserved `ci` and `doctor`;
  - never give a parameter named `env` a default: a cloud environment is always named on the command line;
  - name private recipes `_…`, except the renamed ones in `just/renamed.just`, which must not outlive their date.

In every repository, adopted or not, a `just <recipe>` in a workflow, a script, a justfile or the documentation must
name a recipe that exists: in that repository, in a module (`just helm-charts <recipe>`), in a repository the same
line names, or anywhere else. A renamed recipe's old name fails with its new one. Needs `just` on the PATH.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ELSEWHERE: set[str] = set()  # recipes of nested justfiles (sub-projects of a module repository)
CONVENTION = HERE.parent / "docs" / "justfiles.md"
RESERVED = ("ci", "doctor")
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
HEADER = re.compile(r"^@?([A-Za-z_][A-Za-z0-9_-]*)(?:\s[^:]*)?:(?!=)")
MOD = re.compile(r"^mod\??\s+([a-z][a-z0-9-]*)\s+['\"]([^'\"]+)['\"]")
TOMBSTONE = re.compile(r"^\s+@just _renamed (\S+) (.+?)\s*$")
REMOVE_AFTER = re.compile(r"Remove this file after (\d{4}-\d{2}-\d{2})")
FLAGS = r"(?:\s+(?:(?:-f|--justfile|-d|--working-directory)\s+\S+|--?[a-z][a-z-]*))*"
WORD = r"([a-z_][a-z0-9_-]*)"
CALL = re.compile(r"^just" + FLAGS + r"\s+" + WORD + r"(?:\s+" + WORD + r")?(?:\s+" + WORD + r")?")
# Where a `just` in code is a command, not a word of a sentence: the start of a line or a `run:`, after a shell
# operator, in a command substitution, after exec/then/do/else, or quoted.
COMMAND = re.compile(r"(?:^\s*(?:-\s+)?(?:run:\s*)?@?|[;&|(]\s*|\$\(\s*|\b(?:exec|then|do|else)\s+|['\"])(?=just\s)")
JSON_CALL = re.compile(r'"just"\s*,\s*"' + WORD + r'"(?:\s*,\s*"' + WORD + r'")?')
MARKUP = (".md", ".ipynb", ".txt")
# Files where a quoted `"just …"` is a command (a hint in an echo, a step); elsewhere it may be a sentence.
SHELL_LIKE = (".sh", ".bash", ".just", ".yml", ".yaml")
SCANNED = MARKUP + SHELL_LIKE + (".py", ".tf", ".tfvars", ".tftpl", ".hcl", ".toml", ".json", ".robot", ".resource", ".gotmpl")
# History is not rewritten: decisions and plans keep the commands of their time.
HISTORY = re.compile(r"(^|/)(rfc|specs|plans|superpowers|_posts)/|changelog", re.IGNORECASE)
# The gate's own tests hold wrong references on purpose (fixtures); nothing else is exempt.
SKIP_PARTS = ("_site/", "node_modules/", ".venv", "vendor/", "package-lock.json", "just/renamed.just",
              "scripts/tests/test_check_just.py")


@dataclass
class Repo:
    name: str
    path: Path
    data: dict
    adopted: bool = False
    public: set[str] = field(default_factory=set)
    private: set[str] = field(default_factory=set)
    renamed: dict[str, str] = field(default_factory=dict)
    mounts: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path, data: dict) -> "Repo":
        repo = cls(path.name, path, data, adopted=(path / "just").is_dir())
        repo.public = {n for n, r in data["recipes"].items() if not r["private"]}
        repo.private = {n for n, r in data["recipes"].items() if r["private"]}
        if repo.adopted:
            for f in sorted((path / "just").glob("*.just")):
                for line in f.read_text().splitlines():
                    m = TOMBSTONE.match(line)
                    if m:
                        repo.renamed[m.group(1)] = m.group(2)
        for line in (path / "justfile").read_text().splitlines():
            m = MOD.match(line)
            if m:
                repo.mounts[m.group(1)] = (path / m.group(2)).resolve().parent
        return repo


def groups_from_convention() -> dict[str, str]:
    """{group: file stem} from the table in docs/justfiles.md: the convention has one owner."""
    groups = {}
    for line in CONVENTION.read_text().splitlines():
        m = re.match(r"^\| `([a-z ]+)` \| `just/([a-z-]+)\.just` \|", line)
        if m:
            groups[m.group(1)] = m.group(2)
    if not groups:
        sys.exit(f"check-just: no group table in {CONVENTION}")
    return groups


def dump(justfile: Path) -> dict:
    proc = subprocess.run(
        ["just", "--justfile", str(justfile), "--working-directory", str(justfile.parent),
         "--dump", "--dump-format", "json"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or "just --dump failed")
    return json.loads(proc.stdout)


def top_level_recipes(lines: list[str]) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(lines, 1):
        if line[:1] in ("", " ", "\t", "#", "[") or re.match(r"^\S+\s*:=", line):
            continue
        if line.startswith(("set ", "import ", "import? ", "mod ", "mod? ", "export ", "alias ")):
            continue
        m = HEADER.match(line)
        if m:
            found.append((number, m.group(1)))
    return found


def check_structure(repo: Repo, groups: dict[str, str], today: dt.date) -> list[str]:
    out = []
    for number, name in top_level_recipes((repo.path / "justfile").read_text().splitlines()):
        if name != "default":
            out.append(f"justfile:{number}: `{name}` belongs in just/<group>.just; the root keeps only `default`")
    files = {}
    stems = set(groups.values()) | {"renamed"}
    for f in sorted((repo.path / "just").glob("*.just")):
        if f.stem not in stems:
            out.append(f"just/{f.name}: not a group file of docs/justfiles.md (or just/renamed.just)")
        for _, name in top_level_recipes(f.read_text().splitlines()):
            files[name] = f.stem
    for name, r in sorted(repo.data["recipes"].items()):
        where = f"just/{files[name]}.just" if name in files else "justfile"
        tagged = [a["group"] for a in r["attributes"] if isinstance(a, dict) and "group" in a]
        if r["private"]:
            if not name.startswith("_") and files.get(name) != "renamed":
                out.append(f"`{name}` ({where}): a private recipe is named `_{name}`")
            continue
        if name == "default":
            continue
        if not NAME.match(name):
            out.append(f"`{name}` ({where}): recipe names are kebab-case")
        if not (r.get("doc") or "").strip():
            out.append(f"`{name}` ({where}): no description (the comment line right above it)")
        if len(tagged) != 1:
            out.append(f"`{name}` ({where}): needs exactly one [group('…')], has {tagged or 'none'}")
        elif tagged[0] not in groups:
            out.append(f"`{name}` ({where}): group `{tagged[0]}` is not one of docs/justfiles.md")
        elif files.get(name) != groups[tagged[0]]:
            out.append(f"`{name}` ({where}): its group `{tagged[0]}` lives in just/{groups[tagged[0]]}.just")
        for p in r["parameters"]:
            if p["name"] == "env" and p["default"] is not None:
                out.append(f"`{name}` ({where}): `env` has a default; a cloud environment is always named explicitly")
    for reserved in RESERVED:
        if reserved not in repo.public:
            out.append(f"no `{reserved}` recipe (reserved, docs/justfiles.md)")
    renamed = repo.path / "just" / "renamed.just"
    if renamed.exists():
        m = REMOVE_AFTER.search(renamed.read_text())
        if not m:
            out.append("just/renamed.just: no 'Remove this file after YYYY-MM-DD' line")
        elif dt.date.fromisoformat(m.group(1)) < today:
            out.append(f"just/renamed.just: its date ({m.group(1)}) has passed; remove the renamed recipes")
        for old in repo.renamed:
            if old in repo.public:
                out.append(f"just/renamed.just: `{old}` is a renamed name and a recipe at the same time")
    return out


def tracked(path: Path) -> list[str]:
    proc = subprocess.run(["git", "-C", str(path), "ls-files"], capture_output=True, text=True)
    return proc.stdout.splitlines()


def scanned(path: Path) -> list[Path]:
    return [path / rel for rel in tracked(path)
            if (rel.endswith(SCANNED) or rel.split("/")[-1].startswith(("justfile", "Dockerfile", ".gitignore")))
            and not HISTORY.search(rel) and not any(part in rel for part in SKIP_PARTS)]


def nested_recipes(path: Path) -> set[str]:
    """The public recipes of a repository's other justfiles (a module's sub-project: `checkout-fe/justfile`)."""
    names = set()
    for rel in tracked(path):
        if rel.endswith("/justfile"):
            try:
                names |= {n for n, r in dump(path / rel)["recipes"].items() if not r["private"]}
            except ValueError:
                pass
    return names


def calls(file: Path) -> list[tuple[int, list[str]]]:
    """(line number, words after `just`) for every recipe call in a code context of the file."""
    try:
        text = file.read_text()
    except (UnicodeDecodeError, OSError):
        return []
    markup = file.name.endswith(MARKUP)
    shell = file.name.endswith(SHELL_LIKE) or file.name.startswith("justfile")
    found = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        spans = re.findall(r"`([^`\n]+)`", line)
        if markup:
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                spans = [line]
        else:
            spans += [line[m.end():] for m in COMMAND.finditer(line) if shell or m.group(0)[-1:] not in "'\""]
            found += [(number, [w for w in m.groups() if w]) for m in JSON_CALL.finditer(line)]
        for span in spans:
            span = span.strip()
            for start in [m.start() for m in re.finditer(r"(?<![\w./-])just\s", span)]:
                m = CALL.match(span[start:])
                if m:
                    found.append((number, [w for w in m.groups() if w]))
    return found


def unavailable_mounts(repos: dict[str, Repo]) -> set[str]:
    """Module names a justfile declares (`mod? ee …`) whose repository is not cloned here.

    CI checks out the public repositories only, so the private EE workspace behind `just ee …` is absent: what lies
    behind such a name cannot be verified, which is not the same as being wrong. The repository that is cloned is
    checked in full wherever it is."""
    return {name for r in repos.values() for name, path in r.mounts.items() if path.name not in repos}


def resolve(words: list[str], line: str, here: Repo | None, repos: dict[str, Repo],
            modules: dict[str, Repo]) -> tuple[str, tuple[str, str] | None] | None:
    """None when the call names a recipe that exists, else (why not, (old, new) when it was renamed)."""
    first = words[0]
    if first.startswith("_") or first in unavailable_mounts(repos):
        return None
    if first in modules:
        repo, rest = modules[first], words[1:]
        while rest and rest[0] in repo.mounts:
            repo, rest = repos.get(repo.mounts[rest[0]].name), rest[1:]
            if repo is None:
                return None  # a module whose repository is not cloned here
        if not rest:
            return None
        if rest[0] in repo.renamed and rest[0] not in repo.public:
            return f"`{rest[0]}` of the {first} module was renamed to `{repo.renamed[rest[0]]}`", (rest[0], repo.renamed[rest[0]])
        if rest[0] not in repo.public:
            return f"the module mounting {repo.name} has no recipe `{rest[0]}`", None
        return None
    named = [repos[n] for n in dict.fromkeys(re.findall(r"labs64\.io(?:-[a-z]+)*", line)) if n in repos]
    if named:
        if any(first in r.public for r in named):
            return None
        for r in named:
            if first in r.renamed:
                return f"was renamed in {r.name} to `just {r.renamed[first]}`", (first, r.renamed[first])
    if here is not None:
        if first in here.renamed and first not in here.public:
            return f"was renamed to `just {here.renamed[first]}`", (first, here.renamed[first])
        if first in here.public or first in here.private:
            return None
    if any(first in r.public for r in repos.values()) or first in ELSEWHERE:
        return None
    renamed = {r.renamed[first] for r in repos.values() if first in r.renamed}
    if len(renamed) == 1:
        new = renamed.pop()
        owner = next(r.name for r in repos.values() if r.renamed.get(first) == new)
        return f"was renamed in {owner} to `just {new}`", (first, new)
    if renamed:
        return f"was renamed differently in several repositories ({', '.join(sorted(renamed))}): name the repository", None
    return "no repository has this recipe", None


def rewrite(line: str, old: str, new: str, modules: dict[str, Repo]) -> str:
    """The line with the renamed recipe of every `just … <old>` (and `"just", "<old>"`) replaced."""
    mods = "|".join(re.escape(m) for m in sorted(modules, key=len, reverse=True)) or "(?!)"
    call = re.compile(r"((?<![\w./-])just" + FLAGS + r"(?:\s+(?:" + mods + r"))*\s+)" + re.escape(old) + r"(?![\w-])")
    line = call.sub(lambda m: m.group(1) + new, line)
    return re.sub(r'("just"\s*,\s*")' + re.escape(old) + r'(")', lambda m: m.group(1) + new + m.group(2), line)


def check_references(repos: dict[str, Repo], scan: list[Path], fix: bool = False) -> list[str]:
    modules = {}
    for r in repos.values():
        for name, path in r.mounts.items():
            if path.name in repos:
                modules.setdefault(name, repos[path.name])
    out = []
    for root in scan:
        here = repos.get(root.name)
        for file in scanned(root):
            lines = None
            changed = False
            for number, words in calls(file):
                lines = lines or file.read_text().split("\n")
                result = resolve(words, lines[number - 1], here, repos, modules)
                if not result:
                    continue
                why, rename = result
                if fix and rename:
                    lines[number - 1] = rewrite(lines[number - 1], *rename, modules)
                    changed = True
                    continue
                out.append(f"{root.name}/{file.relative_to(root)}:{number}: `just {' '.join(words)}`: {why}")
            if changed:
                file.write_text("\n".join(lines))
                print(f"check-just: rewrote renamed recipes in {root.name}/{file.relative_to(root)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(HERE.parents[1]), help="directory holding the clones (default: ..)")
    parser.add_argument("--repo", action="append", default=[], help="check only this clone (repeatable)")
    parser.add_argument("--fix", action="store_true", help="rewrite every reference to a renamed recipe in place")
    parser.add_argument("--today", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    groups = groups_from_convention()

    repos: dict[str, Repo] = {}
    failures: list[str] = []
    for justfile in sorted(root.glob("*/justfile")):
        try:
            repos[justfile.parent.name] = Repo.load(justfile.parent, dump(justfile))
        except ValueError as e:
            failures.append(f"{justfile.parent.name}/justfile: does not parse: {e}")

    selected = args.repo or [p.name for p in sorted(root.glob("labs64.io*")) if (p / ".git").exists()]
    for name in selected:
        ELSEWHERE.update(nested_recipes(root / name))
    adopted = [n for n in selected if n in repos and repos[n].adopted]
    for name in adopted:
        failures += [f"{name}: {f}" for f in check_structure(repos[name], groups, today)]
    failures += check_references(repos, [root / n for n in selected if (root / n / ".git").exists()], fix=args.fix)

    if failures:
        print(f"check-just: {len(failures)} finding(s) (docs/justfiles.md)", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"check-just: clean — {len(adopted)} justfile(s) follow docs/justfiles.md; "
          f"every `just <recipe>` in {len(selected)} repositories exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
