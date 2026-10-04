"""Ask conversations: "New conversation" keeps the old chat, every chat can be reopened or deleted, the model
only sees the open chat, and chats made before signing in move to the account."""
from sqlalchemy import create_engine, inspect, text

from backend.app.core import db as core_db
from backend.app.core.db import SessionLocal
from backend.app.features.rag import routes as rag_routes
from backend.app.features.rag.models import ChatTurn


ABOUT = {"gender": "f", "age_band": "25_34"}     # sex and age band are required at sign-up


def device(client):
    return {"X-Seeker": client.post("/api/session").json()["token"]}


def ask(client, h, question, conv=None):
    data = {"question": question, "lang": "ar"}
    if conv:
        data["conversation_id"] = str(conv)
    res = client.post("/api/ask", data=data, headers=h)
    assert res.status_code == 200, res.text
    return res.json()


def test_new_chat_keeps_the_old_one(client):
    h = device(client)
    first = ask(client, h, "ما معنى التوحيد؟")
    c1 = first["conversation_id"]
    assert ask(client, h, "وما أقسامه؟", c1)["conversation_id"] == c1
    c2 = ask(client, h, "ما الزكاة؟")["conversation_id"]       # "New conversation": no id sent
    assert c2 != c1

    listed = client.get("/api/conversations", headers=h).json()
    assert listed["saved"] is False
    assert [(c["id"], c["title"], c["turns"]) for c in listed["conversations"]] == \
        [(c2, "ما الزكاة؟", 1), (c1, "ما معنى التوحيد؟", 2)]

    opened = client.get(f"/api/conversations/{c1}", headers=h).json()
    assert [t["question"] for t in opened["turns"]] == ["ما معنى التوحيد؟", "وما أقسامه؟"]
    assert opened["turns"][0]["answer"]["turn_id"] == first["turn_id"]
    assert all(t["answer"]["conversation_id"] == c1 for t in opened["turns"])

    # someone else can't read it, and their question with its id starts a chat of their own
    other = device(client)
    assert client.get(f"/api/conversations/{c1}", headers=other).status_code == 404
    assert client.delete(f"/api/conversations/{c1}", headers=other).status_code == 404
    assert ask(client, other, "ما الصلاة؟", c1)["conversation_id"] not in (c1, c2)

    assert client.delete(f"/api/conversations/{c2}", headers=h).json() == {"ok": True}
    assert [c["id"] for c in client.get("/api/conversations", headers=h).json()["conversations"]] == [c1]
    assert client.get(f"/api/conversations/{c2}", headers=h).status_code == 404


def test_the_model_only_sees_the_open_chat(client, monkeypatch):
    seen = []
    real = rag_routes.ask
    monkeypatch.setattr(rag_routes, "ask", lambda ctx: seen.append([m["text"] for m in ctx.history]) or real(ctx))
    h = device(client)
    c1 = ask(client, h, "ما معنى التوحيد؟")["conversation_id"]
    ask(client, h, "ما الزكاة؟")
    ask(client, h, "وما أقسامه؟", c1)
    assert seen[0] == [] and seen[1] == []               # a new chat starts with no context
    assert seen[2][0] == "ما معنى التوحيد؟" and "ما الزكاة؟" not in seen[2]


def test_signing_in_brings_this_browsers_chats(client):
    home = device(client)
    client.post("/api/account/signup", json={"username": "conv_owner", "password": "long-pass-1", **ABOUT}, headers=home)
    mine = ask(client, home, "ما معنى التوحيد؟")["conversation_id"]

    laptop = device(client)
    before = ask(client, laptop, "ما الزكاة؟")["conversation_id"]
    client.post("/api/account/signin", json={"username": "conv_owner", "password": "long-pass-1"}, headers=laptop)
    for h in (laptop, home):
        listed = client.get("/api/conversations", headers=h).json()
        assert listed["saved"] is True
        assert {c["id"] for c in listed["conversations"]} == {mine, before}
    assert client.get(f"/api/conversations/{before}", headers=home).json()["turns"][0]["question"] == "ما الزكاة؟"

    # a browser already signed in to one account brings nothing of that account into another
    client.post("/api/account/signup", json={"username": "conv_other", "password": "long-pass-1", **ABOUT}, headers=device(client))
    client.post("/api/account/signin", json={"username": "conv_other", "password": "long-pass-1"}, headers=home)
    assert client.get("/api/conversations", headers=home).json()["conversations"] == []
    client.post("/api/account/signin", json={"username": "conv_owner", "password": "long-pass-1"}, headers=home)
    assert {c["id"] for c in client.get("/api/conversations", headers=home).json()["conversations"]} == {mine, before}


def test_turns_from_before_conversations_are_gathered(client):
    h = device(client)
    turn = ask(client, h, "ما معنى التوحيد؟")
    db = SessionLocal()
    try:
        row = db.get(ChatTurn, turn["turn_id"])
        sid = row.session_id
        db.add(ChatTurn(session_id=sid, question="سؤال قديم", answer={}))
        db.add(ChatTurn(session_id=sid, question="سؤال قديم آخر", answer={}))
        db.commit()
    finally:
        db.close()
    convs = client.get("/api/conversations", headers=h).json()["conversations"]
    old = [c for c in convs if c["id"] != turn["conversation_id"]]
    assert len(old) == 1 and old[0]["title"] == "سؤال قديم" and old[0]["turns"] == 2


def test_clearing_history_removes_every_chat(client):
    h = device(client)
    ask(client, h, "ما معنى التوحيد؟")
    ask(client, h, "ما الزكاة؟")
    assert client.delete("/api/ask/history", headers=h).json() == {"ok": True}
    assert client.get("/api/conversations", headers=h).json()["conversations"] == []


def test_migration_adds_the_conversation_column_and_its_index(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE chat_turn (id INTEGER PRIMARY KEY, session_id VARCHAR(64), created_at DATETIME,"
                          " question TEXT, lang VARCHAR(8), level VARCHAR(1), kind VARCHAR(24), mode VARCHAR(16),"
                          " answer JSON, helpful BOOLEAN, feedback_reason VARCHAR(64))"))
    monkeypatch.setattr(core_db, "engine", eng)
    assert "chat_turn.conversation_id" in core_db.add_missing_columns()
    assert "ix_chat_turn_conversation_id" in {i["name"] for i in inspect(eng).get_indexes("chat_turn")}
    assert core_db.add_missing_columns() == []
