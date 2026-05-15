def test_health(client):
    """GET /health returns 200 with status, db, uptime, and version fields."""
    c, _ = client  # client fixture yields (TestClient, tokens)
    response = c.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert "version" in data
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0
