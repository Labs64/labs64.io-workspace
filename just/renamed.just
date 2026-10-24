# Recipes that were renamed. Each old name fails and names its replacement, so muscle memory and old scripts
# get a clear message instead of a different behaviour (docs/justfiles.md in labs64.io-workspace).
# Remove this file after 2027-01-31.

# Fail with the new name of a renamed recipe
[private]
_renamed old +new:
    @echo 'error: `just {{old}}` is now `just {{new}}` (see just/renamed.just).' >&2 && exit 1

[private]
check-release *args:
    @just _renamed check-release check-release-wiring

[private]
otel *args:
    @just _renamed otel up-otel

[private]
pr *args:
    @just _renamed pr list-prs

[private]
verify-deps *args:
    @just _renamed verify-deps check-deps

[private]
verify-process *args:
    @just _renamed verify-process ci
