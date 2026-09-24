# Coach Chat

Status: **implemented** (exec-plan 0007). A cycling-only coach the rider
chats with in the web UI. It reasons over their synced rides, profile and
garage, grounds training advice in their imported training books with
citations, and remembers durable facts they share.

The coach is unlocked from the dashboard ("Ask your coach") once a ride
source is connected, meaning a connection with `status == "connected"`.
Until then the button is disabled and the dashboard says to connect
Garmin in Settings. The server does not gate on the connection: with no
rides, the coach's tools simply report that nothing is synced yet.

Scope is cycling and cycling-adjacent topics, and nothing else:
- the rider's rides and performance,
- training, plans, workouts and events,
- bike fit, bikes, equipment and maintenance,
- nutrition, hydration, recovery, strength work and injury prevention, in a cycling context.

Short conversational turns (greetings, thanks, "why?") and requests to
remember or forget something are allowed. Everything else gets a fixed
polite refusal, as do attempts to change the coach's role or reveal its
instructions. A cheap classifier call decides scope before the coach
model runs, so a refused message costs about 100 tokens and never
reaches the tools. The system prompt restates the scope as a second
layer. Medical questions get cycling-safe general guidance and a referral
to a professional.

Data honesty follows `design-docs/sensor-capability-model.md`. The coach
only sees ride data through `rag.service.ride_context`, the per-ride
sensor gate. It also sees `get_training_summary`, which averages HR and
power only over rides whose own FIT data verified the stream. It must say
when a metric is unavailable rather than estimate it. When it recommends
training, it searches the books first and names the book and page. Cited
passages appear as source chips under the reply.

Memory notes are short third-person facts (at most 300 characters, 50
notes in total). The coach saves them with its `remember` tool and removes
them with `forget`. All notes go into every turn's prompt. The rider sees
them under "What the coach remembers" and can delete any of them.

Conversations persist in SQLite, and each one's title is the first
message. Each turn sends the last 12 messages as history. Tool traffic is
not stored: it is rebuilt from live data on every turn.

REST (all under `/api`):
- `GET` and `POST /coach/conversations`
- `GET` and `DELETE /coach/conversations/{id}`
- `POST /coach/conversations/{id}/messages` with `{text}` (at most 4000 characters). It returns `text/event-stream` with these events:
  - `delta` `{text}`
  - `tool_status` `{text}`
  - `sources` `{sources}`
  - `done` `{message}`
  - `error` `{text}`
- `GET /coach/memory` and `DELETE /coach/memory/{id}`
- `GET /training-summary?weeks=`

A turn that can't start is rejected before streaming, with these status codes:
- unknown conversation → 404
- empty or too-long message → 400
- missing `SOFT_FLOYD_OPENAI_API_KEY` → 400
- month-to-date LLM spend at or above `SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD` (default 10) → 402

Failures after streaming starts arrive as an `error` event.

MCP has no chat tool, because an MCP client is already an agent. For
parity it gets the same data and memory:
- `get_training_summary`
- `list_coach_memory`
- `add_coach_memory`
- `delete_coach_memory`
