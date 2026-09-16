# Exec-Plans

An exec-plan is a written plan for a feature or change of meaningful
scope, checked in before the implementation, so any agent (or the next
session of the same agent) can pick it up with full context.

## When to write one

Write an exec-plan for: a new feature, a schema change, anything touching
the sensor capability model or the MCP/REST surface, anything spanning
`packages/core` and both adapters. Skip it for: typo fixes, dependency
bumps, pure refactors with no behavior change, single-file bug fixes.

## Format

`docs/exec-plans/active/NNNN-short-name.md`, numbered sequentially
(`0001-scaffold.md` is the first). Each plan has:

- **Context** — why this change, what prompted it, what "done" means.
- **Design** — the approach, referencing the relevant `design-docs/` and
  `product-specs/` rather than restating them.
- **Steps** — concrete, in the order they'll be done.
- **Verification** — how to prove it works end-to-end (commands, curl
  calls, an MCP tool call, a manual UI check).

## Lifecycle

1. Write it in `active/`, get it reviewed if the change is non-trivial.
2. Implement it, updating the plan file if reality diverges from the
   design (don't leave a stale plan next to different code).
3. When done, move the file to `docs/exec-plans/completed/` verbatim.
4. Record anything deliberately deferred in
   `docs/exec-plans/tech-debt-tracker.md` with a one-line reason.

`docs/exec-plans/active/0001-scaffold.md` is a worked example.
