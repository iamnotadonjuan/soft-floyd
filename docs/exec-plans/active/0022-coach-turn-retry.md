# Retry a failed coach turn

## Context

The coach can emit an SSE error after the user's message has already been
saved. The chat currently shows the error but offers no action; resending
through the normal composer creates a duplicate user message. The warning
log also omits the traceback behind intermittent failures.

## Design

The stream acknowledges the saved user message before model work. A retry
request names that message and reuses it only while it is the last message
in the account-owned conversation, with no assistant reply after it. A
preflight failure, which never saved a message, can resend normally. The
chat shows a localized Retry button beside a failed turn, disables it
while a turn is active, and leaves the original message visible. The
server logs the exception traceback while returning safe error copy.

## Steps

1. Add a core retry check and stream support for a saved final user message.
2. Extend the REST message request and SSE event with the retry identifier
   and saved-message acknowledgement.
3. Track the failed turn in the chat UI and display Retry beside its error;
   add English and Spanish copy.
4. Document and test retry behavior and failure cases.

## Verification

- Test retry after a failed model call uses one persisted user message and
  produces one assistant reply.
- Test refusal when another message or assistant reply follows, account
  isolation, image preservation, and normal preflight rejection.
- Run Python and web checks; inspect the chat error and Retry state.

## Build status

Implemented on 2026-10-08. `make check` passed (306 Python tests, web lint
and TypeScript; existing web lint warnings remain). Core and REST tests
cover a failed stream, retrying the saved message and image, one resulting
assistant message, stale retry rejection and account isolation. The server
now logs a traceback for unexpected coach failures. A signed-in visual
review remains pending because no local server was running, so this plan
stays active.

Quality self-score: correctness passes automated checks; visual review is
pending. Core owns retry eligibility, REST remains a thin adapter, account
isolation is tested, no sensor rules change, docs and tests are updated,
and the work stayed within this plan. Retry is manual; a tool completed
before a later failure may run again on retry, so review the conversation
before repeating an action that creates or edits a session.
