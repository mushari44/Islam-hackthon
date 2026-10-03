"""A referral drafted from an Ask chat uses that chat, and the chat then shows which da'i the seeker talked to."""
from tests.conftest import seeker_headers


def test_referral_uses_the_chat_it_came_from(client, seeker, daai_login):
    h = seeker_headers(seeker)
    c1 = client.post("/api/ask", data={"question": "ما معنى التوحيد؟", "lang": "ar"}, headers=h).json()["conversation_id"]
    client.post("/api/ask", data={"question": "ما الزكاة؟", "lang": "ar"}, headers=h)   # a newer, different chat

    draft = client.post("/api/referral/draft", json={"lang": "ar", "conversation_id": c1}, headers=h).json()
    assert draft["card"]["question"] == "ما معنى التوحيد؟"       # template card in offline mode
    # without a chat id (the Talk page), the latest question is used as before
    assert client.post("/api/referral/draft", json={"lang": "ar"}, headers=h).json()["card"]["question"] == "ما الزكاة؟"
    # someone else's chat id is ignored
    other = client.post("/api/session").json()["token"]
    stranger = client.post("/api/referral/draft", json={"lang": "ar", "conversation_id": c1},
                           headers={"X-Seeker": other}).json()
    assert stranger["card"]["question"] == ""

    client.post(f"/api/referral/{draft['id']}/confirm", json={"consent": True, "card": draft["card"]}, headers=h)
    call = client.post("/api/calls", json={"lang": "ar", "referral_id": draft["id"]}, headers=h).json()
    assert client.get("/api/calls/conversations", headers=h).json() == []     # not talked yet
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    client.post(f"/api/daai/requests/{call['id']}/accept", headers=d)
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)

    links = client.get("/api/calls/conversations", headers=h).json()
    assert [(x["conversation_id"], x["call_id"], x["daai"]["callable"]) for x in links] == [(c1, call["id"], True)]
    assert client.get("/api/calls/conversations", headers={"X-Seeker": other}).json() == []
