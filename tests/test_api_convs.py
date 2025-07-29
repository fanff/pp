import pytest


@pytest.mark.asyncio
async def test_get_conversations(client):
    client, (alice_token, bob_token, charlie_token) = client
    response = client.get("/conv/", headers={"Authorization": f"Bearer {alice_token}"})

    # Assert the response status code is 200 (OK)
    assert response.status_code == 200

    # Optionally, assert that the response body is a list (if that's expected)
    data = response.json()
    assert isinstance(data, list)

    assert len(data) == 2
    assert data[0]["label"] == "general"
    assert data[1]["label"] == "a_and_b"