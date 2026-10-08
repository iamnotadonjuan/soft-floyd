# 0020 — GPT-6 Luna

## Context

GPT-4.1 Mini is missing rider instructions when planning workouts. Switch all chat tasks to GPT-6 Luna while retaining the monthly spend cap and sensor-honest output. Add one-image attachments to coach messages, retained in account-owned conversation history. Done means coach chat, its tools, scope classification, workout generation, rest explanations, and image turns work with Luna and every paid call remains accurately recorded.

## Design

- Use the Responses API with medium reasoning for coach chat, workouts, and rest explanations. Scope classification uses Luna with no reasoning.
- Keep OpenAI transport and pricing in `packages/core/src/soft_floyd_core/llm/client.py`; preserve the core-facing streaming and structured result contracts where possible. Keep the coach tool loop stateless by replaying model output items, including encrypted reasoning, with function outputs.
- Account for cached input, cache writes, and output including reasoning tokens at Luna's published rates. Keep embeddings and the configured $10 monthly default unchanged.
- Follow `docs/design-docs/sensor-capability-model.md` and existing training sanitizer; transport changes do not weaken target gating.
- Accept one validated JPEG, PNG, or WebP image with a text message; persist it on the account-owned coach message and serve it only through an authenticated route. Include recent attached images in coach history so follow-ups can refer to them. Bound image size to 5 MB. See `docs/product-specs/coach-chat.md` for user behavior.

## Steps

1. Switch the shared client and structured generation to Luna Responses, adapting tool definitions, tool outputs, streaming events, and structured output schema.
2. Preserve reasoning items through the coach tool loop and record each response's usage; handle incomplete or refused structured responses explicitly.
3. Add the image input, persistence migration, authenticated image route, and English/Spanish chat controls.
4. Add focused client and image tests for tool continuation, output, cost accounting, validation, and account isolation. Update model documentation and self-score against `docs/QUALITY_SCORE.md`.

## Verification

- Run focused Python tests, then `make check`.
- If an API key is available, exercise one workout and one tool-using coach turn and verify usage records and sensor-safe output.
- Send an image in coach chat, reload the thread, and verify it remains visible and available to a follow-up turn.

## Outcome

- `make check` passed: 297 Python tests, web ESLint (five pre-existing warnings), and TypeScript.
- Alembic migration applied on a temporary database. Live Luna checks passed for structured workout output, a tool-call continuation, and image input.
- Signed-in visual review is deferred until a local browser session with a signed-in account is available; tracked in the tech-debt tracker.
