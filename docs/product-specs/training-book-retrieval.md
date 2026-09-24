# Training Book Retrieval

Status: implemented in exec-plan 0005. This is a retrieval foundation, not
generated coaching.

The rider imports a local, selectable-text PDF with `soft-floyd books import
PATH --title TITLE [--author AUTHOR]`. Reimporting the same file reports the
existing book. A PDF with no extractable text fails with an actionable error.
The importer checkpoints embedded passages and reports progress. Repeating
the command after an interruption continues from the saved passage. Until
every passage is embedded, the book is excluded from search results.

`get_training_context(query, activity_id?)` on MCP and
`GET /api/training-context?query=...&activity_id=...` on REST return the
same result: up to five book passages with title, author, and PDF page;
the rider's goal and discipline; and the latest ride by default (or the
requested ride). With no ride, `ride` is null. No book passages are returned
until a book is imported.

Ride context includes only sensor-derived values verified in that ride's
FIT data and allowed for the rider. A failed FIT parse exposes only basic
Garmin summary values and clearly says detailed sensor data is unavailable.
Results are source material for later coaching, not a generated assessment.
