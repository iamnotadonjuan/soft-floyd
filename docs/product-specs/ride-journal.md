# Ride Journal

Status: **implemented** (exec-plan 0005). The dashboard shows the rider's
goal, declared sensor capability, and connected-app health beside their
synced rides. The newest ride is prominent; older rides appear in a history
of tiles. Selecting a tile opens an in-app detail view, and returning to
history preserves loaded pages and scroll position.

History covers all rides already stored in Soft Floyd. It does not fetch
older rides from Garmin; historical backfill is a separate feature. The
web loads pages of 20 through `GET /api/activities`, using the last item's
`start_time` and `id` as `before_start_time` and `before_id` for the next
page. Results are ordered by `(start_time DESC, id DESC)`. MCP
`list_activities` accepts the same optional cursor arguments.

Ride detail uses `GET /api/activities/{id}`. It displays recorded distance,
duration, elevation, and sensor values only when that ride's FIT stream
confirms the sensor. Laps appear when present. If the FIT file failed, the
UI identifies the summary-only values and does not claim sensor readings.
Training metrics such as TSS and HR drift are not computed by this feature.

An empty journal directs the rider to connect Garmin from Settings and
explains that the first sync imports the latest ride only. Connection
health and reauthentication states are visible without trying to infer
sync success from activity count.
