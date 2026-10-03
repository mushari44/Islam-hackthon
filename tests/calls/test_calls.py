"""Call requests, matching, signalling and the referral card. Owner: Eman."""
from tests.conftest import seeker_headers


def test_referral_needs_consent(client, seeker, daai_login):
    h = seeker_headers(seeker)
    client.post("/api/ask", data={"question": "ما معنى التوحيد؟", "lang": "ar"}, headers=h)
    draft = client.post("/api/referral/draft", json={"lang": "ar"}, headers=h).json()
    assert draft["card"]["question"] == "ما معنى التوحيد؟"     # template card in offline mode
    client.post(f"/api/referral/{draft['id']}/confirm", json={"consent": False, "card": draft["card"]}, headers=h)
    call = client.post("/api/calls", json={"lang": "ar", "referral_id": draft["id"]}, headers=h).json()
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    accepted = client.post(f"/api/daai/requests/{call['id']}/accept", headers=d).json()
    assert accepted["card"] is None                              # no consent, nothing shared
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)


def test_full_call_flow(client, seeker, daai_login):
    h = seeker_headers(seeker)
    draft = client.post("/api/referral/draft", json={"lang": "ar"}, headers=h).json()
    client.post(f"/api/referral/{draft['id']}/confirm", json={"consent": True, "card": {"question": "سؤالي"}}, headers=h)
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    assert client.get("/api/availability").json()["languages"]["ar"]["total"] >= 1

    call = client.post("/api/calls", json={"lang": "ar", "referral_id": draft["id"]}, headers=h).json()
    queue = client.get("/api/daai/requests", headers=d).json()
    assert any(r["id"] == call["id"] and r["has_card"] for r in queue["waiting"])

    accepted = client.post(f"/api/daai/requests/{call['id']}/accept", headers=d).json()
    assert accepted["card"]["question"] == "سؤالي"
    # a second da'i can't take the same request
    other = daai_login("maryam")
    assert client.post(f"/api/daai/requests/{call['id']}/accept", headers=other).status_code == 409

    url = f"/ws/call/{call['id']}"
    with client.websocket_connect(f"{url}?role=seeker&token={seeker['_token']}") as ws1, \
            client.websocket_connect(f"{url}?role=daai&token={d['_token']}") as ws2:
        assert ws1.receive_json()["type"] == "joined"
        assert ws2.receive_json()["present"] == ["seeker", "daai"]
        assert ws1.receive_json()["type"] == "peer-joined"
        ws2.send_json({"type": "offer", "sdp": {"type": "offer", "sdp": "v=0"}})
        assert ws1.receive_json()["type"] == "offer"
        ws1.send_json({"type": "chat", "text": "السلام عليكم"})
        assert ws1.receive_json()["text"] == "السلام عليكم"
        assert ws2.receive_json()["text"] == "السلام عليكم"

    client.post(f"/api/daai/calls/{call['id']}/understood", headers=d)
    client.post(f"/api/daai/calls/{call['id']}/end", json={"reexplain_needed": False, "card_accurate": True}, headers=d)
    assert client.get(f"/api/calls/{call['id']}", headers=h).json()["status"] == "ended"
    stats = client.get("/api/daai/experiment", headers=d).json()
    assert stats["arms"]["model"]["calls"] >= 1 or stats["arms"].get("template", {}).get("calls", 0) >= 1


def test_wrong_people_cannot_join_the_room(client, seeker, daai_login):
    h = seeker_headers(seeker)
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    d = daai_login("khalid")
    client.post(f"/api/daai/requests/{call['id']}/accept", headers=d)
    stranger = client.post("/api/session").json()["token"]
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/call/{call['id']}?role=seeker&token={stranger}") as ws:
            ws.receive_json()
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)


def test_cancel_and_delete_my_data(client, seeker):
    h = seeker_headers(seeker)
    call = client.post("/api/calls", json={"lang": "en"}, headers=h).json()
    assert client.post(f"/api/calls/{call['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.delete("/api/me", headers=h).status_code == 200
    assert client.get(f"/api/calls/{call['id']}", headers=h).status_code == 401


def test_call_log_shows_only_my_ended_calls(client, seeker, daai_login):
    h = seeker_headers(seeker)
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    client.post(f"/api/daai/requests/{call['id']}/accept", headers=d)
    # still in progress: not in the log yet
    assert all(c["id"] != call["id"] for c in client.get("/api/daai/calls", headers=d).json()["calls"])
    client.post(f"/api/daai/calls/{call['id']}/understood", headers=d)
    client.post(f"/api/daai/calls/{call['id']}/end", json={"reexplain_needed": False, "note": "جيد"}, headers=d)

    log = client.get("/api/daai/calls", headers=d).json()
    row = next(c for c in log["calls"] if c["id"] == call["id"])
    assert row["referral_mode"] == "direct" and row["reexplain_needed"] is False and row["note"] == "جيد"
    assert row["duration_seconds"] is not None and row["seconds_to_understand"] is not None
    assert "session_id" not in row                       # nothing that points back to the seeker
    assert log["summary"]["calls"] >= 1 and log["summary"]["no_reexplain"] >= 1
    # another da'i doesn't see it, and the log needs a da'i login
    other = client.get("/api/daai/calls", headers=daai_login("maryam")).json()["calls"]
    assert all(c["id"] != call["id"] for c in other)
    assert client.get("/api/daai/calls").status_code == 401


def test_call_log_is_by_month(client, daai_login):
    d = daai_login("khalid")
    this = client.get("/api/daai/calls", headers=d).json()
    assert this["month"] in this["months"] and all(c["accepted_at"].startswith(this["month"]) for c in this["calls"])
    assert client.get("/api/daai/calls?month=1999-01", headers=d).json()["calls"] == []
    assert client.get("/api/daai/calls?month=soon", headers=d).status_code == 400


def test_rtc_config_accepts_several_turn_urls(client, monkeypatch):
    from backend.app.features.calls import routes
    from dataclasses import replace
    monkeypatch.setattr(routes, "settings", replace(routes.settings, turn_url="turn:a.example:80, turns:a.example:443?transport=tcp",
                                                    turn_username="u", turn_credential="p"))
    turn = client.get("/api/rtc-config").json()["iceServers"][-1]
    assert turn["urls"] == ["turn:a.example:80", "turns:a.example:443?transport=tcp"] and turn["username"] == "u"


def test_only_supported_languages(client, seeker):
    h = seeker_headers(seeker)
    assert client.post("/api/calls", json={"lang": "fr"}, headers=h).status_code == 400
    assert client.post("/api/calls", json={"lang": "en"}, headers=h).status_code == 200
