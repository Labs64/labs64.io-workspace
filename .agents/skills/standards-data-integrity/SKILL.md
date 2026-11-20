---
name: standards-data-integrity
description: Use when changing a database schema, migration, persistence, retention, cleanup, backup/restore, transaction boundaries, or anything that could lose, duplicate or corrupt data. Part of the Labs64.IO engineering standards.
---

# Standards: Data Integrity & Lifecycle

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Database per service (guardrail 9); persistence responsibilities are explicit
- Respect transaction boundaries and state consistency expectations
- Make schema changes backward-compatible where practical, with safe migrations and a rollback path; remember a store may lag the code writing to it
- Silently losing data is a defect: if a tolerance can drop a value, it is documented and can be turned into a failure
- Handle retention, cleanup, backup and restore explicitly, and know which store is the system of record
