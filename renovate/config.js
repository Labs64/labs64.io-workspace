// Global (self-hosted) Renovate configuration for .github/workflows/renovate.yml.
//
// Repository-level behaviour — managers, grouping, schedules — is NOT here: it lives in the
// shared preset ../default.json, which every repository's renovate.json extends. This file
// only says which repositories the runner visits.
//
// Credentials are injected by the workflow, not written here: the GitHub token, and
// RENOVATE_HOST_RULES for Labs64 Nexus — it is private, so without it Renovate cannot see
// io.labs64 releases (labs64io-parent, auditflow-api) and would never propose them.
module.exports = {
  platform: 'github',
  gitAuthor: 'Labs64 Renovate <info@labs64.io>',
  // Every Labs64.IO ecosystem repository the token can see; a repository opts in by
  // carrying a renovate.json (requireConfig), so nothing else is touched.
  autodiscover: true,
  autodiscoverFilter: ['Labs64/labs64.io', 'Labs64/labs64.io-*'],
  onboarding: false,
  requireConfig: 'required',
};
