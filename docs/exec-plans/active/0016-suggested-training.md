# 0016 — Suggested training and outdoor context

## Context

Training currently requires the rider to drive the session idea even though core already reads recent rides, load and books. The rider also cannot explicitly say where or on what terrain a workout will happen. Done means a rider can ask for a reasoned suggestion, including rest when warranted, and can give honest outdoor context.

## Design

Follow `docs/product-specs/suggested-training.md`, `docs/design-docs/core-beliefs.md`, `sensor-capability-model.md`, and the existing training specs. Keep decisions and account-scoped data assembly in core, with thin REST/MCP adapters. Extend the JSON session request with optional outdoor context, so existing saved rows need no migration. Reuse the current budgeted LLM wrapper and sanitizer.

## Steps

1. Extend session request/edit/prompt types and shared Training fields for outdoor area, terrain and altitude; add explanatory `?` disclosures and translations.
2. Add core suggestion orchestration over recent verified ride context, load, and RAG passages. Return either an unsaved rest result or a saved workout, with evidence and sources.
3. Expose the same operation through REST and MCP; add the Training suggestion mode, evidence display and easy-ride action.
4. Add core and cross-surface tests, run checks, update docs and self-score.

## Verification

- Test outdoor context validation and old saved sessions, rest rules, no data/books, sensor filtering, cost usage and account isolation.
- Test REST/MCP parity and unchanged existing planning contract.
- Run `make check` and web build; review desktop/mobile and EN/ES interactions if a signed-in browser is available.
