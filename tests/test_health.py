def test_health(client):
    """GET /health returns 200 with {"status": "ok"}."""
    c, _ = client  # client fixture yields (TestClient, tokens)
    response = c.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

