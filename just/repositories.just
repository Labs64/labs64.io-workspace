# Group `repositories` (docs/justfiles.md in labs64.io-workspace). Imported by the justfile.

# Clone all ecosystem repositories (as siblings of this workspace)
[group('repositories')]
clone:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ ! -d "{{ROOT}}/$repo" ]; then
            echo "Cloning $repo..."
            git clone "{{GITHUB_ORG}}/$repo.git" "{{ROOT}}/$repo"
        else
            echo "$repo already exists, skipping."
        fi
    done

# Pull the current branch (rebase, autostash) in every GitHub clone next to this workspace
[group('repositories')]
pull:
    #!/bin/bash
    failed=()
    while read -r dir; do
        name=$(basename "$dir")
        if ! git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
            echo "Skipping $name (current branch has no upstream)."
            continue
        fi
        echo "Pulling $name..."
        git -C "$dir" pull --rebase --autostash || failed+=("$name")
    done < <(bash scripts/github-clones.sh "{{ROOT}}")
    if [ ${#failed[@]} -gt 0 ]; then
        echo >&2
        echo "Pull failed in: ${failed[*]}" >&2
        exit 1
    fi

# Show git status across every GitHub clone next to this workspace
[group('repositories')]
show-repos:
    #!/bin/bash
    while read -r dir; do
        echo "=== $(basename "$dir") ==="
        git -C "$dir" status -s
    done < <(bash scripts/github-clones.sh "{{ROOT}}")

# Show open pull requests across all GitHub clones next to this workspace (incl. private EE repos)
[group('repositories')]
list-prs:
    #!/bin/bash
    if ! command -v gh >/dev/null 2>&1; then
        echo "gh CLI not found" >&2
        exit 1
    fi
    list_prs() {
        local rows
        rows=$(gh pr list --state open --json number,title,headRefName,createdAt,url \
            --template '{{ "{{" }}range .{{ "}}" }}#{{ "{{" }}.number{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.title{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.headRefName{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.createdAt | timefmt "2006-01-02 15:04"{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.url{{ "}}" }}{{ "{{" }}"\n"{{ "}}" }}{{ "{{" }}end{{ "}}" }}')
        if [ -n "$rows" ]; then
            printf 'ID\tTITLE\tBRANCH\tCREATED AT\tLINK\n%s\n' "$rows" | column -t -s $'\t'
        fi
    }
    first=1
    while read -r dir; do
        [ "$first" = 1 ] || echo
        first=0
        echo "=== $(basename "$dir") ==="
        (cd "$dir" && list_prs)
    done < <(bash scripts/github-clones.sh "{{ROOT}}")
