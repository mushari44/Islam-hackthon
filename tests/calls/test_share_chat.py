"""A seeker can share one Ask chat with the da'i who takes their call: only with their OK, only that chat,
only as it was when they agreed, and not after they delete it."""
from tests.conftest import seeker_headers, signed_in


def ask(client, h, question, conv=None):
    data = {"question": question, "lang": "ar", **({"conversation_id": str(conv)} if conv else {})}
    return client.post("/api/ask", data=data, headers=h).json()


def request_call(client, h, conv, share_chat, consent=False):
    draft = client.post("/api/referral/draft", json={"lang": "ar", "conversation_id": conv}, headers=h).json()
    ok = client.post(f"/api/referral/{draft['id']}/confirm",
                     json={"consent": consent, "card": draft["card"], "share_chat": share_chat}, headers=h).json()
    call = client.post("/api/calls", json={"lang": "ar", "referral_id": draft["id"]}, headers=h).json()
    return draft, ok, call


def take(client, d, call_id):
    queue = client.get("/api/daai/requests", headers=d).json()["waiting"]
    item = next(r for r in queue if r["id"] == call_id)
    return item, client.post(f"/api/daai/requests/{call_id}/accept", headers=d).json()


def test_shared_chat_reaches_the_daai(client, caller, daai_login):
    h = seeker_headers(caller)
    c1 = ask(client, h, "ما معنى التوحيد؟")["conversation_id"]
    ask(client, h, "وما أقسامه؟", c1)
    ask(client, h, "ما الزكاة؟")                                    # another chat: never shared
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)

    draft, ok, call = request_call(client, h, c1, share_chat=True)
    assert draft["chat_turns"] == 2 and ok["share_chat"] is True and ok["consented"] is False
    ask(client, h, "سؤال بعد طلب الاتصال", c1)                     # asked after agreeing: not shared
    item, view = take(client, d, call["id"])
    assert item["has_chat"] is True and item["has_card"] is False
    assert view["card"] is None
    assert [x["question"] for x in view["chat"]] == ["ما معنى التوحيد؟", "وما أقسامه؟"]
    assert all(set(x) == {"question", "had_image", "created_at", "answer"} for x in view["chat"])
    assert "segments" in view["chat"][0]["answer"] and "trace" not in view["chat"][0]["answer"]

    # the call log offers the conversation again after the call
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)
    logged = next(c for c in client.get("/api/daai/calls", headers=d).json()["calls"] if c["id"] == call["id"])
    assert logged["has_chat"] is True
    assert len(client.get(f"/api/daai/calls/{call['id']}", headers=d).json()["chat"]) == 2
    # deleting the chat takes it away from the da'i too
    client.delete(f"/api/conversations/{c1}", headers=h)
    assert client.get(f"/api/daai/calls/{call['id']}", headers=d).json()["chat"] is None


def test_nothing_is_shared_without_the_seekers_ok(client, caller, daai_login):
    h = seeker_headers(caller)
    c1 = ask(client, h, "ما معنى التوحيد؟")["conversation_id"]
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)

    _, ok, call = request_call(client, h, c1, share_chat=False, consent=True)
    assert ok["share_chat"] is False
    item, view = take(client, d, call["id"])
    assert item["has_chat"] is False and view["chat"] is None and view["card"]
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)
    logged = next(c for c in client.get("/api/daai/calls", headers=d).json()["calls"] if c["id"] == call["id"])
    assert logged["has_chat"] is False

    # another seeker's chat id can't be shared
    other = signed_in(client)
    draft, ok, call = request_call(client, other, c1, share_chat=True)
    assert draft["chat_turns"] == 0 and ok["share_chat"] is False
    _, view = take(client, d, call["id"])
    assert view["chat"] is None
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)
