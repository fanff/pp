def test_post_message_emits_resync_websocket_event(client):
    client, (alice_token, _bob_token, _charlie_token) = client

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"token": alice_token})

        response = client.post(
            "/usermsg",
            json={"content": "hello over ws", "conversation_id": 1},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert response.status_code == 200
        posted = response.json()
        assert posted["status"] == "ok"

        event = websocket.receive_json()

    assert event == {
        "type": "message.created",
        "conversation_id": 1,
        "change_id": posted["change_id"],
        "message_id": posted["messageid"],
        "sender_id": 1,
        "ts": event["ts"],
        "watermark": posted["change_id"],
    }
    assert "content" not in event


def test_conversation_messages_after_uses_exclusive_change_cursor(client):
    client, (alice_token, _bob_token, _charlie_token) = client
    headers = {"Authorization": f"Bearer {alice_token}"}

    first_response = client.post(
        "/usermsg",
        json={"content": "first", "conversation_id": 1},
        headers=headers,
    )
    second_response = client.post(
        "/usermsg",
        json={"content": "second", "conversation_id": 1},
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_change_id = first_response.json()["change_id"]
    response = client.get(
        f"/conv/1/messages?after={first_change_id}",
        headers=headers,
    )

    assert response.status_code == 200
    messages = response.json()
    assert [message["content"] for message in messages] == ["second"]
    assert messages[0]["change_id"] == second_response.json()["change_id"]
    assert messages[0]["message_id"] == second_response.json()["messageid"]
