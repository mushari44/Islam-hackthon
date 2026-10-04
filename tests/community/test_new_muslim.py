""""Became Muslim": the da'i confirms it in a call, the seeker decides whether their groups hear it. Owner: Mushari."""
import itertools

import pytest

from tests.conftest import seeker_headers


def _groups(client, lang):
    return [g for g in client.get("/api/groups").json() if g["lang"] == lang and g["audience"] == "all"]


def _answered_call(client, h, d, end=True):
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    assert client.post(f"/api/daai/requests/{call['id']}/accept", headers=d).status_code == 200
    if end:
        client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)
    return call["id"]


_n = itertools.count(1)


@pytest.fixture()
def member(client, seeker):
    """A seeker in two groups (one Arabic, one English)."""
    h = seeker_headers(seeker)
    ar, en = _groups(client, "ar")[0], _groups(client, "en")[0]
    n = next(_n)
    for g, nick in ((ar, f"طالب_نور{n}"), (en, f"seeker_light{n}")):
        assert client.post(f"/api/groups/{g['id']}/join", json={"nickname": nick, "accept_rules": True},
                           headers=h).status_code == 200
    return h, ar, en


def _messages(client, gid, h):
    return client.get(f"/api/groups/{gid}/messages", headers=h).json()


def test_nothing_is_announced_until_the_seeker_agrees(client, member, daai_login):
    h, ar, en = member
    d = daai_login("khalid")
    cid = _answered_call(client, h, d)
    assert client.get("/api/community/new-muslim", headers=h).json()["status"] == "none"

    assert client.post(f"/api/daai/calls/{cid}/new-muslim", headers=d).json() == {"new_muslim": "pending"}
    assert client.get(f"/api/daai/calls/{cid}", headers=d).json()["new_muslim"] == "pending"
    mine = client.get("/api/community/new-muslim?ui=ar", headers=h).json()
    assert mine["status"] == "pending" and mine["daai"] and len(mine["groups"]) == 2
    assert not any(m["author_type"] == "system" for m in _messages(client, ar["id"], h))

    shared = client.post("/api/community/new-muslim", json={"share": True}, headers=h).json()
    assert shared["status"] == "shared" and shared["announced"] == 2
    welcome_ar = [m for m in _messages(client, ar["id"], h) if m["payload"].get("kind") == "new_muslim"]
    welcome_en = [m for m in _messages(client, en["id"], h) if m["payload"].get("kind") == "new_muslim"]
    assert len(welcome_ar) == 1 and "طالب_نور" in welcome_ar[0]["text"] and "بشرى" in welcome_ar[0]["text"]
    assert len(welcome_en) == 1 and "seeker_light" in welcome_en[0]["text"]

    # once only, and their own posts now carry the badge
    client.post("/api/community/new-muslim", json={"share": True}, headers=h)
    assert len([m for m in _messages(client, ar["id"], h) if m["author_type"] == "system"]) == 1
    post = client.post(f"/api/groups/{ar['id']}/messages", json={"text": "الحمد لله", "lang": "ar"}, headers=h).json()
    assert post["new_muslim"] is True
    assert next(m for m in _messages(client, ar["id"], h) if m["id"] == post["id"])["new_muslim"] is True

    log = client.get("/api/daai/calls", headers=d).json()
    assert next(c for c in log["calls"] if c["id"] == cid)["new_muslim"] == "shared"
    assert log["summary"]["new_muslims"] >= 1

    # taking it back removes the badge and the welcome messages
    assert client.post("/api/community/new-muslim", json={"share": False}, headers=h).json() == {"status": "none"}
    msgs = _messages(client, ar["id"], h)
    assert not any(m["author_type"] == "system" for m in msgs)
    assert next(m for m in msgs if m["id"] == post["id"])["new_muslim"] is False
    assert client.get(f"/api/daai/calls/{cid}", headers=d).json()["new_muslim"] is None


def test_declining_keeps_nothing_about_the_seeker(client, member, daai_login):
    from backend.app.core.db import SessionLocal
    from backend.app.features.community.public import new_muslim_total

    h, ar, _ = member
    d = daai_login("khalid")
    cid = _answered_call(client, h, d, end=False)        # pressed during the call
    with SessionLocal() as db:
        before = new_muslim_total(db)
    client.post(f"/api/daai/calls/{cid}/new-muslim", headers=d)
    client.post("/api/community/new-muslim", json={"share": False}, headers=h)
    assert client.get("/api/community/new-muslim", headers=h).json()["status"] == "none"
    assert client.get(f"/api/daai/calls/{cid}", headers=d).json()["new_muslim"] is None
    assert not any(m["author_type"] == "system" for m in _messages(client, ar["id"], h))
    with SessionLocal() as db:
        assert new_muslim_total(db) == before + 1           # only the anonymous count remains


def test_only_the_calls_daai_can_confirm_and_undo(client, seeker, daai_login):
    h = seeker_headers(seeker)
    d = daai_login("khalid")
    cid = _answered_call(client, h, d)
    assert client.post(f"/api/daai/calls/{cid}/new-muslim", headers=daai_login("yusuf")).status_code == 404
    assert client.post(f"/api/daai/calls/{cid}/new-muslim", headers={}).status_code == 401
    client.post(f"/api/daai/calls/{cid}/new-muslim", headers=d)
    assert client.delete(f"/api/daai/calls/{cid}/new-muslim", headers=d).json() == {"new_muslim": None}
    assert client.get("/api/community/new-muslim", headers=h).json()["status"] == "none"
    # after the seeker answered, the da'i can't take it back
    client.post(f"/api/daai/calls/{cid}/new-muslim", headers=d)
    client.post("/api/community/new-muslim", json={"share": True}, headers=h)
    assert client.delete(f"/api/daai/calls/{cid}/new-muslim", headers=d).status_code == 409


def test_a_waiting_call_cannot_be_marked(client, seeker, daai_login):
    h = seeker_headers(seeker)
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    assert client.post(f"/api/daai/calls/{call['id']}/new-muslim", headers=daai_login("khalid")).status_code == 404
    client.post(f"/api/calls/{call['id']}/cancel", headers=h)
    assert client.post("/api/community/new-muslim", json={"share": True}, headers=h).status_code == 404
