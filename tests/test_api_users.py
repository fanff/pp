import pytest


@pytest.mark.asyncio
async def test_get_users(client):
    client, (alice_token, bob_token, charlie_token) = client
    response = client.get("/users/", headers={"Authorization": f"Bearer {alice_token}"})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    names = {u["name"] for u in data}
    assert names == {"alice", "bob", "charlie"}


@pytest.mark.asyncio
async def test_friend_request_flow(client):
    client, (alice_token, bob_token, charlie_token) = client

    ic_resp = client.post(
        "/invite-codes",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert ic_resp.status_code == 200
    code = ic_resp.json()["code"]

    fr_resp = client.post(
        "/friend-requests",
        json={"invite_code": code},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert fr_resp.status_code == 200
    assert fr_resp.json()["status"] == "pending"
    assert fr_resp.json()["to_user_id"] == 3

    accept_resp = client.post(
        f"/friend-requests/{fr_resp.json()['id']}/accept",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["user_id"] == 1

    friends_resp = client.get(
        "/friends",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert friends_resp.status_code == 200
    friend_ids = {f["user_id"] for f in friends_resp.json()}
    assert 3 in friend_ids
