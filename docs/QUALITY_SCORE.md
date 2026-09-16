# Quality Self-Score

Before calling a change done, score it against this rubric honestly. If
any answer is "no," either fix it or state explicitly in the exec-plan /
PR why it's deferred — don't silently ship a "no."

1. **Correctness** — Does it do what the exec-plan/spec says, and did you
   run the verification steps (not just read the code)?
2. **Single source of truth** — Is every rule in `packages/core`, called
   (not re-implemented) from both the MCP tool and the REST route where
   applicable? (See ARCHITECTURE.md's load-bearing constraint.)
3. **Sensor honesty** — Does anything in this change compute or display a
   metric using a sensor the rider doesn't have, or that isn't present in
   the specific activity's data? (design-docs/sensor-capability-model.md)
4. **Tests** — Do new core functions have unit tests, and does new
   cross-surface behavior have a test proving MCP and REST agree (like
   `tests/test_mcp_tools.py`)?
5. **Docs kept honest** — If this change adds/removes a capability, is
   `AGENTS.md`'s "Current state" section, the relevant `design-docs/`, or
   `docs/product-specs/index.md` updated to match reality?
6. **Scope discipline** — Did this stay inside the exec-plan's stated
   scope, or did it quietly grow? A larger scope is fine if the plan file
   was updated to say so.
7. **Local-only, single-user** — Nothing here binds beyond `127.0.0.1` or
   adds auth/multi-tenancy without an explicit prior ask.
