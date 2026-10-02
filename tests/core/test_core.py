"""Shared core: sessions, login, tokens, normalisation."""
from backend.app.core.security import hash_password, sign, unsign, verify_password
from backend.app.core.textnorm import normalize_ar, skeleton


def test_password_and_tokens():
    h = hash_password("secret")
    assert verify_password("secret", h) and not verify_password("nope", h)
    tok = sign({"kind": "daai", "id": 3})
    assert unsign(tok)["id"] == 3
    assert unsign(tok[:-2] + "xx") is None


def test_uthmani_normalisation():
    assert normalize_ar("ٱلصَّلَوٰةَ") == normalize_ar("الصلاة")
    assert normalize_ar("أَدۡرَىٰكَ") == normalize_ar("أدراك")
    assert skeleton("ٱلرَّحۡمَٰنِ") == skeleton("الرحمن")


def test_login(client):
    assert client.post("/api/daai/login", json={"username": "khalid", "password": "wrong"}).status_code == 401


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["ai"] is False and body["corpus"]["quran_verses"] == 6236
