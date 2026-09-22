"""The garage: CRUD, the exactly-one-primary invariant, and the rule-5
guarantee that adding a power-meter bike flips capability_tier on the
very next /api/profile read. See docs/design-docs/sensor-capability-model.md.
"""


def test_first_bike_is_always_primary(client):
    bike = client.post("/api/bikes", json={"nickname": "Tarmac", "kind": "road"}).json()
    assert bike["is_primary"] is True
    assert bike["capability_tier"] == "hr"  # has_hr_monitor defaults True, no power meter yet


def test_second_bike_is_not_primary_by_default(client):
    client.post("/api/bikes", json={"kind": "road"})
    second = client.post("/api/bikes", json={"kind": "mtb"}).json()
    assert second["is_primary"] is False


def test_setting_is_primary_demotes_the_previous_primary(client):
    first = client.post("/api/bikes", json={"kind": "road"}).json()
    second = client.post("/api/bikes", json={"kind": "mtb"}).json()

    updated = client.patch(f"/api/bikes/{second['id']}", json={"is_primary": True}).json()
    assert updated["is_primary"] is True

    refreshed_first = next(b for b in client.get("/api/bikes").json() if b["id"] == first["id"])
    assert refreshed_first["is_primary"] is False


def test_cannot_unset_the_only_primary_bike(client):
    bike = client.post("/api/bikes", json={"kind": "road"}).json()
    response = client.patch(f"/api/bikes/{bike['id']}", json={"is_primary": False})
    assert response.status_code == 400


def test_deleting_the_last_bike_is_refused(client):
    bike = client.post("/api/bikes", json={"kind": "road"}).json()
    response = client.delete(f"/api/bikes/{bike['id']}")
    assert response.status_code == 400
    assert client.get("/api/bikes").json() != []


def test_deleting_the_primary_bike_promotes_another(client):
    primary = client.post("/api/bikes", json={"kind": "road"}).json()
    other = client.post("/api/bikes", json={"kind": "mtb"}).json()

    response = client.delete(f"/api/bikes/{primary['id']}")
    assert response.status_code == 204

    remaining = client.get("/api/bikes").json()
    assert [b["id"] for b in remaining] == [other["id"]]
    assert remaining[0]["is_primary"] is True


def test_update_unknown_bike_is_404(client):
    response = client.patch("/api/bikes/999", json={"nickname": "Ghost"})
    assert response.status_code == 404


def test_adding_a_power_meter_bike_flips_profile_tier_on_next_read(client):
    """Rule 5: sensors are editable, and the tier moves immediately."""
    before = client.get("/api/profile").json()
    assert before["capability_tier"] == "hr"
    assert before["has_power_meter"] is False

    bike = client.post("/api/bikes", json={"kind": "road", "has_power_meter": True}).json()
    assert bike["capability_tier"] == "power"

    after = client.get("/api/profile").json()
    assert after["capability_tier"] == "power"
    assert after["has_power_meter"] is True
    assert "ftp" in after["available_metrics"]

    # Removing it drops back down immediately too.
    client.patch(f"/api/bikes/{bike['id']}", json={"has_power_meter": False})
    reverted = client.get("/api/profile").json()
    assert reverted["capability_tier"] == "hr"
    assert reverted["has_power_meter"] is False


def test_indoor_trainer_is_just_a_bike(client):
    """No separate trainer concept — kind='indoor' plus a power meter is
    a smart trainer, exactly like any other bike."""
    trainer = client.post(
        "/api/bikes", json={"nickname": "Zwift rig", "kind": "indoor", "has_power_meter": True}
    ).json()
    assert trainer["kind"] == "indoor"
    assert trainer["capability_tier"] == "power"


def test_bike_tier_differs_per_bike_within_one_garage(client):
    """core belief 4: a bare bike in a power-tier garage still reads as hr."""
    road = client.post("/api/bikes", json={"kind": "road", "has_power_meter": True}).json()
    gravel = client.post("/api/bikes", json={"kind": "gravel"}).json()

    bikes = {b["id"]: b for b in client.get("/api/bikes").json()}
    assert bikes[road["id"]]["capability_tier"] == "power"
    assert bikes[gravel["id"]]["capability_tier"] == "hr"

    profile = client.get("/api/profile").json()
    assert profile["capability_tier"] == "power"  # garage-level union
