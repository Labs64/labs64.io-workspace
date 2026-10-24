REPOS := "labs64.io-docs labs64.io-tests labs64.io-helm-charts labs64.io-commons labs64.io-authproxy labs64.io-auditflow labs64.io-checkout labs64.io-customer-portal labs64.io-payment-gateway labs64.io"
GITHUB_ORG := "https://github.com/Labs64"
# Ecosystem root: repositories are cloned as siblings of this workspace, not inside it.
ROOT := ".."

# The other repositories, mounted as modules named after the repository without `labs64.io-`: `just helm-charts
# <recipe>` runs in ../labs64.io-helm-charts, `just tests <recipe>` in ../labs64.io-tests. A repository that is not
# cloned is not listed. The optional EE workspace mounts the internal repositories below it the same way.
#
# labs64.io-helm-charts: the local cluster in detail, chart authoring and the chart gates
mod? helm-charts '../labs64.io-helm-charts/justfile'
# labs64.io-tests: one suite, one module or one file of the regression suite; the PSP stub
mod? tests '../labs64.io-tests/justfile'
# Internal repositories and EE modules (the private EE workspace, when it is cloned)
mod? ee '../labs64.io-workspace-ee/justfile'

# List the recipes by group, and the repositories mounted as modules (docs/justfiles.md)
default:
    @echo 'labs64.io-workspace: start here. Other repositories: just helm-charts | just tests | just ee  (docs/justfiles.md)'
    @just --list --unsorted --list-heading ''

# Recipes by group (docs/justfiles.md in labs64.io-workspace): one file per group, in list order.
import 'just/setup.just'
import 'just/repositories.just'
import 'just/local-stack.just'
import 'just/tests.just'
import 'just/quality-gates.just'
import 'just/renamed.just'
