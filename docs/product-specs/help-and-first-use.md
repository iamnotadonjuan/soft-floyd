# Help and first-use guide

Status: **implemented** (exec-plan 0015).

After a new rider finishes the existing onboarding summary, the dashboard shows a short, dismissible guide. It points to connecting Garmin, reviewing a synced ride, and planning a session. The guide reflects connection, ride, and session data already loaded by the dashboard; a "Ready" indicator means the prerequisite exists, not that the rider read or completed a workflow. It never blocks navigation. Dismissal is stored in this browser under the signed-in account ID. Existing riders are not interrupted. Help can reopen the guide.

Help is available from the signed-in header and during onboarding. It explains Overview, Training, Coach, Settings, and the next steps after setup. Its FAQ covers Garmin connection and limited history, missing sensors, training load confidence, workout exports, and Coach availability. Content describes only shipped behavior and is translated in English and Spanish.

Each Settings group and the fitness, fatigue, and form tiles have a tappable `?` explanation. These are keyboard-operable disclosures, not hover-only tooltips. Help remains usable without Garmin or any recorded rides. No backend, API, or schema change is involved.

## Acceptance

- A newly completed onboarding shows the guide; dismissing it persists across reloads for that account in this browser, and Help can reopen it.
- An existing completed account with no guide state sees no automatic guide. One account's dismissal does not affect another.
- Guide actions lead to the relevant screen and do not imply a ride was reviewed merely because it synced.
- FAQ and contextual help work by touch and keyboard in English and Spanish, including empty and disconnected states.
