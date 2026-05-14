import pytest


@pytest.mark.asyncio
async def test_non_admin_gets_403(client):
    client, (alice_token, _bob_token, _charlie_token, _diana_token) = client
    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin privileges required"


@pytest.mark.asyncio
async def test_admin_list_all_users(client):
    client, (_alice_token, _bob_token, _charlie_token, diana_token) = client
    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    names = {u["name"] for u in data}
    assert names == {"alice", "bob", "charlie", "diana"}
    diana = next(u for u in data if u["name"] == "diana")
    assert diana["is_admin"] is True
    alice = next(u for u in data if u["name"] == "alice")
    assert alice["is_admin"] is False


@pytest.mark.asyncio
async def test_admin_promote_user(client):
    client, (_alice_token, _bob_token, _charlie_token, diana_token) = client
    # bob is user_id=2
    response = client.post(
        "/admin/users/2/role",
        json={"is_admin": True},
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 200
    assert response.json()["is_admin"] is True

    # verify bob can now call admin endpoints
    bob_token = client.post(
        "/token",
        data={
            "username": "bob",
            "password": "testpassword",
            "grant_type": "password",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()["access_token"]

    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_demote_self(client):
    client, (_alice_token, _bob_token, _charlie_token, diana_token) = client
    # diana is user_id=4
    response = client.post(
        "/admin/users/4/role",
        json={"is_admin": False},
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 200
    assert response.json()["is_admin"] is False

    # subsequent call should get 403
    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_all_convs(client):
    client, (_alice_token, _bob_token, _charlie_token, diana_token) = client
    response = client.get(
        "/admin/conv",
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    labels = {c["label"] for c in data}
    assert labels == {"general", "a_and_b"}
    for c in data:
        assert c["member_count"] >= 2


@pytest.mark.asyncio
async def test_admin_change_conv_role(client):
    client, (_alice_token, bob_token, _charlie_token, diana_token) = client
    # conv 1 ("general") has bob (user_id=2) as member
    response = client.post(
        "/admin/conv/1/members/2/role",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"

    # bob can no longer write in conv 1
    msg_resp = client.post(
        "/usermsg",
        json={"content": "hello", "conversation_id": 1},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert msg_resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_endpoint_404(client):
    client, (_alice_token, _bob_token, _charlie_token, diana_token) = client
    # non-existent user
    response = client.post(
        "/admin/users/9999/role",
        json={"is_admin": True},
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 404

    # non-existent conv
    response = client.post(
        "/admin/conv/9999/members/1/role",
        json={"role": "member"},
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    assert response.status_code == 404

    # user not in conv
    response = client.post(
        "/admin/conv/2/members/3/role",
        json={"role": "member"},
        headers={"Authorization": f"Bearer {diana_token}"},
    )
    # charlie is not in conv 2 (a_and_b)
    assert response.status_code == 404
