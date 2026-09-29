# 0013 — Edit a planned training session

## Context

A planned session was fixed: the rider could regenerate it with the same
inputs, mark it done or skipped, or delete it, but not say "I only have 45
minutes", "make it indoor", "use the gravel bike" or "do it Saturday
instead" — they had to delete it and fill in Plan a session again.

Done means: a rider can edit any input of a session that is still
`planned` — date, available minutes, setting, discipline, bike, route idea,
feel — from the workout card (Training page and coach chat) and by asking
the coach. A date-only edit just moves the session and keeps its workout,
with no AI call. Any other change rebuilds the workout from the edited
request with one AI call, under the same monthly budget as planning.

Out of scope: editing individual workout steps by hand, and editing `done`
or `skipped` sessions.

## Design

- `training/schemas.py`: `SessionChanges`, every `SessionRequest` field
  optional. `sent()` returns the fields the caller actually sent, so an
  explicit `bike_id: null` differs from leaving it out; a null for any other
  field counts as not sent.
- `training/service.py::update_session(session, llm, embedder, id, changes,
  *, budget_usd)`:
  - Only `planned` sessions; otherwise `SessionNotEditableError`.
  - Merges the sent fields into the stored request. No effective change
    returns the session untouched.
  - Date only: moves `planned_date`, refreshes just `intent.off_schedule`
    (`intent.is_off_schedule`, now shared with `recommend_intent`), keeps the
    workout and `garmin_workout_id`, clears `sent_to_garmin_at` so the card
    offers to send again for the new date. Needs no LLM.
  - Anything else: if setting or discipline changed and no bike was sent,
    the old bike is dropped so `_pick_bike` chooses again; then `_build` and
    an overwrite of request, intent, workout, rationale, adjustments,
    sources, with the Garmin ids cleared like `regenerate_session`. Needs an
    LLM (`ValueError` naming `SOFT_FLOYD_OPENAI_API_KEY` without one).
- REST: `PATCH /api/training/sessions/{id}` takes either `{status}` (as
  before) or edit fields, never both (400). 404 unknown, 409 not editable,
  402 over budget, 400 no key or a bad value.
- MCP: `update_training_session(training_session_id, changes)`.
- Coach: tool `update_training_session` (`session_id` plus only the changed
  fields). It returns the session with `training_session_ids`, so the chat
  shows the updated card; not-found, not-editable and over-budget go back to
  the model as `{"error": ...}`. The system prompt has an EDITING A SESSION
  section.
- Web: the plan form's controls moved to `SessionFields.tsx`, shared with the
  new `EditSessionForm.tsx`, which opens from an Edit button on planned
  cards. It sends only what changed, says "Move session" for a date-only edit
  and "Rebuild session" otherwise, and warns when the session was already
  sent to Garmin. It loads the garage itself, so it works in the coach chat
  too. The Training page refreshes its session list after any card change.
- Also fixed while here: date-only strings were parsed as UTC in three
  places (`WorkoutCard`, the session list, the Dashboard tile), so riders
  west of UTC saw a session dated one day early.

No migration: every edited field already lives on `TrainingSession`.

## Steps

Done in this order: `SessionChanges` and `is_off_schedule`; `update_session`
with its tests; REST route; MCP and coach tools with the prompt section;
API types and client; `SessionFields` extraction; `EditSessionForm`, card
wiring and strings; docs.

## Verification

- `make check` (ruff, `pnpm run typecheck`, pytest): green.
- Service tests: date-only move (no AI call, `off_schedule` refreshed,
  workout kept, Garmin id kept, `sent_to_garmin_at` cleared); minutes change
  rebuilds; a discipline change re-picks the bike; an explicit bike is
  honoured; a no-op makes no call; done/skipped raise; over budget leaves
  the session untouched; a move works without an LLM, a rebuild does not.
- REST tests: status-only PATCH unchanged; edits; 400/404/409/422; no-key
  behavior. Coach tool and MCP-vs-REST agreement tests.
- Looked at the edit form in headless Chrome (date-only, minutes change,
  Garmin warning).
- Still to do by hand: edit a real planned session on the Training page and
  in the coach chat; ask the coach "make tomorrow's session 45 minutes"
  and "move it to Saturday" against the real OpenAI API; edit a session that
  was really sent to Garmin.

## Known limitation

The app doesn't store Garmin's scheduled-entry id and has never verified a
live Garmin push, so an edit that rebuilds the workout, or moves the date,
leaves the old copy in Garmin Connect. Deleting it on edit is deferred until
the live push is verified; the form warns instead. See the tech-debt
tracker.
