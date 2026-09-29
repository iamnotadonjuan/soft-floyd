# 0011 — Coach can plan a session and hand over the workout file

## Context

The coach already had a `plan_training_session` tool, but the chat only
showed text: the saved session never reached the UI, so the rider got no
file download or Garmin button, and reopening a conversation lost any link
to it. The tool also let the model silently default the date, minutes and
bike, where the Plan a session form asks for every field.

Done means: a rider asks the coach for a workout, the coach asks for
whatever the form would (date, minutes, indoor/outdoor, discipline, bike
if ambiguous; feel and route idea optional), generates the session, and
the chat shows the same `WorkoutCard` as the Training page — with FIT/ZWO/
ERG downloads and Send to Garmin. The card survives a reload.

## Design

- `coach/tools.py`: `plan_training_session` gains `bike_id`; its
  description tells the model to ask for missing inputs first.
  `ToolResult.training_session_ids` carries the saved session out of the
  tool (also rebuilt in `apps/server/.../mcp_bridge.py`, since the web
  coach runs tools over MCP).
- `coach/prompts.py`: a PLANNING A SESSION section (static prompt).
- `coach/service.py`: `run_turn` emits a `training_session` `CoachEvent`
  per planned session and stores the ids on the assistant `CoachMessage`.
  `MessageOut.training_sessions` resolves them live, dropping deleted ones.
- `CoachMessage.training_session_ids` (JSON) + migration `9d2c41b7a6e3`.
  Not a foreign key: deleting a session just removes the card.
- Web: `Coach.tsx` renders `WorkoutCard` under assistant messages.

No new LLM calls or endpoints: cost and budget behavior are unchanged.

## Result

The prompt tells the coach to infer what it can from the rider's words
(a named climb or route means outdoor, "trainer"/"Zwift" means indoor,
relative dates resolve against today) and to ask only for what is still
missing, saying which fields it assumed. Live testing showed the first
version asked "indoor or outdoor?" even after the rider named Alto de
Patios.

Implemented; `make check` green. The live model's habit of asking for
missing inputs before calling the tool is prompt-driven and has not been
observed against the real OpenAI API.
