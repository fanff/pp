import pytest


@pytest.mark.asyncio
async def test_get_users(client):
    client, token = client
    response = client.get("/users/", headers={"Authorization": f"Bearer {token}"})

    # Assert the response status code is 200 (OK)
    assert response.status_code == 200

    # Optionally, assert that the response body is a list (if that's expected)
    data = response.json()
    assert isinstance(data, list)

    assert len(data) == 1  
    assert data[0]["name"] == "testuser"
    assert data[0]["nickname"] == "testuser"