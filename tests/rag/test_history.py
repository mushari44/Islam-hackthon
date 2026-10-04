"""Ask history: a signed-in seeker's chats are saved to the account and come back on another device;
anonymous chats still follow the 24-hour retention."""
from datetime import timedelta

from backend.app.core.db import SessionLocal, utcnow
from backend.app.features.rag.models import ChatTurn, purge_expired


ABOUT = {"gender": "f", "age_band": "25_34"}     # sex and age band are required at sign-up


def device(client):
    return {"X-Seeker": client.post("/api/session").json()["token"]}


def test_signed_in_chats_follow_the_account(client):
    phone = device(client)
    asked = client.post("/api/ask", data={"question": "ما معنى التوحيد؟", "lang": "ar"}, headers=phone).json()
    hist = client.get("/api/ask/history", headers=phone).json()
    assert hist["saved"] is False and [t["turn_id"] for t in hist["turns"]] == [asked["turn_id"]]
    assert hist["turns"][0]["answer"]["kind"] == asked["kind"] and "trace" not in hist["turns"][0]["answer"]

    client.post("/api/account/signup", json={"username": "chat_keeper", "password": "long-pass-1", **ABOUT}, headers=phone)
    laptop = device(client)
    client.post("/api/account/signin", json={"username": "chat_keeper", "password": "long-pass-1"}, headers=laptop)
    client.post("/api/ask", data={"question": "What is zakat?", "lang": "en"}, headers=laptop)
    hist = client.get("/api/ask/history", headers=laptop).json()
    assert hist["saved"] is True
    assert [t["question"] for t in hist["turns"]] == ["ما معنى التوحيد؟", "What is zakat?"]
    assert all(t["answer"]["turn_id"] == t["turn_id"] for t in hist["turns"])
    cited = [t for t in hist["turns"] if t["answer"].get("sources")]
    assert all(set(t["answer"]["cards"]) == set(t["answer"]["sources"]) for t in cited)

    # old turns: anonymous ones expire, the account's are kept
    anon = device(client)
    anon_turn = client.post("/api/ask", data={"question": "ما الصلاة؟", "lang": "ar"}, headers=anon).json()["turn_id"]
    db = SessionLocal()
    try:
        for t in db.query(ChatTurn).all():
            t.created_at = utcnow() - timedelta(days=3)
        db.commit()
        purge_expired(db)
        left = {t.id for t in db.query(ChatTurn).all()}
    finally:
        db.close()
    assert anon_turn not in left
    assert {t["turn_id"] for t in hist["turns"]} <= left

    assert client.delete("/api/ask/history", headers=laptop).json() == {"ok": True}
    assert client.get("/api/ask/history", headers=phone).json()["turns"] == []


def test_old_saved_chats_stay_out_of_a_new_question(client):
    """Saved turns from earlier days show in the history, but aren't fed to the model or the referral card."""
    from backend.app.features.rag.models import recent_turns
    h = device(client)
    client.post("/api/account/signup", json={"username": "old_chats", "password": "long-pass-1", **ABOUT}, headers=h)
    turn = client.post("/api/ask", data={"question": "سؤال قديم", "lang": "ar"}, headers=h).json()["turn_id"]
    db = SessionLocal()
    try:
        row = db.get(ChatTurn, turn)
        row.created_at = utcnow() - timedelta(days=5)
        sid = row.session_id
        db.commit()
        assert recent_turns(db, sid) == []
        assert [t.id for t in recent_turns(db, sid, recent_only=False)] == [turn]
    finally:
        db.close()
    assert [t["turn_id"] for t in client.get("/api/ask/history", headers=h).json()["turns"]] == [turn]
