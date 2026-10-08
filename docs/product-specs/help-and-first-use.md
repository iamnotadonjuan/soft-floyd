# Help and first-use guide

Status: **implemented** (exec-plan 0015).

## First-open tour

After a new rider completes setup, a short spotlight tour opens on Overview. Six steps point to the rider's goal, Garmin connection status, Training, Coach, Settings, and Help. The tour moves between screens as needed and explains that Coach requires a connected ride source. Riders can go Back or Next, skip at any step, or finish; the tour never changes rider data. Its automatic launch is tied to completing setup, so skipping or finishing closes it without reopening on reload. Existing completed accounts do not get an automatic tour, and any signed-in rider can replay it from Help. The tour is available in English and Spanish and works with keyboard, touch, and narrow screens. If a spotlight target is unavailable, its explanation remains readable in a centered dialog.

After a new rider finishes the existing onboarding summary, the dashboard shows a short, dismissible guide. It points to connecting Garmin, reviewing a synced ride, and planning a session. The guide reflects connection, ride, and session data already loaded by the dashboard; a "Ready" indicator means the prerequisite exists, not that the rider read or completed a workflow. It never blocks navigation. Dismissal is stored in this browser under the signed-in account ID. Existing riders are not interrupted. Help can reopen the guide.

Help is available from the signed-in header and during onboarding. It explains Overview, Training, Coach, Settings, and the next steps after setup. Its FAQ covers Garmin connection and limited history, missing sensors, training load confidence, workout exports, and Coach availability. Content describes only shipped behavior and is translated in English and Spanish.

Each Settings group and the fitness, fatigue, and form tiles have a tappable `?` explanation. These are keyboard-operable disclosures, not hover-only tooltips. Help remains usable without Garmin or any recorded rides. No backend, API, or schema change is involved.

## Acceptance

- Completing new-rider setup starts the tour; skipping or finishing prevents it from reopening automatically on reload. Existing riders can launch it from Help.
- Tour steps stay readable with no Garmin connection or rides, in English and Spanish, on desktop and mobile, and when a spotlight target is missing.
- Keyboard users can move through tour controls and close it with Escape; focus does not move into the underlying page.
- A newly completed onboarding shows the guide; dismissing it persists across reloads for that account in this browser, and Help can reopen it.
- An existing completed account with no guide state sees no automatic guide. One account's dismissal does not affect another.
- Guide actions lead to the relevant screen and do not imply a ride was reviewed merely because it synced.
- FAQ and contextual help work by touch and keyboard in English and Spanish, including empty and disconnected states.
