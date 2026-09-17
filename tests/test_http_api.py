def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_profile_round_trip_and_tier_flip(client):
    # Default profile has no sensors declared beyond the HR-monitor default.
    initial = client.get("/api/profile").json()
    assert initial["capability_tier"] == "hr"

    payload = {
        "weekly_rides": 4,
        "weekly_hours": 7,
        "primary_discipline": "mtb",
        "goal_text": "climb better",
        "has_power_meter": False,
        "has_hr_monitor": True,
        "has_cadence_sensor": True,
        "lthr": 168,
    }
    updated = client.put("/api/profile", json=payload).json()
    assert updated["weekly_rides"] == 4
    assert updated["goal_text"] == "climb better"
    assert updated["capability_tier"] == "hr"
    assert "ftp" not in updated["available_metrics"]

    # Adding a power meter flips the tier and grows the allowlist.
    powered = client.put("/api/profile", json={"has_power_meter": True, "ftp_watts": 240}).json()
    assert powered["capability_tier"] == "power"
    assert "ftp" in powered["available_metrics"]
    # Prior fields survive the partial update.
    assert powered["goal_text"] == "climb better"

    # GET reflects the same state PUT left behind.
    fetched = client.get("/api/profile").json()
    assert fetched == powered


# Activities/sync REST routes are covered in tests/test_activities_api.py
# now that they're wired to real data (exec-plan 0002) — the old
# "always []" stub test lived here when that was still true.
