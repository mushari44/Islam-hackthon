"""Accounts, sessions, login and tokens (owner: Eman), plus shared normalisation and health."""
from backend.app.features.auth.security import hash_password, sign, unsign, verify_password
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


def test_update_profile(client, daai_login):
    h = daai_login("maryam")
    before = client.get("/api/daai/me", headers=h).json()
    res = client.post("/api/daai/profile", headers=h, json={"languages": ["en", "ar", "en"], "bio": "  نبذة جديدة  "})
    assert res.status_code == 200
    body = res.json()
    assert body["languages"] == ["en", "ar"] and body["bio"] == "نبذة جديدة"
    assert body["name"] == before["name"]          # fields not sent stay as they were
    # put it back so other tests see the seeded profile
    client.post("/api/daai/profile", headers=h, json={"languages": before["languages"], "bio": before["bio"]})


def test_update_profile_rejects_bad_input(client, daai_login):
    h = daai_login("maryam")
    assert client.post("/api/daai/profile", headers=h, json={"languages": ["xx"]}).status_code == 422
    assert client.post("/api/daai/profile", headers=h, json={"languages": []}).status_code == 422
    assert client.post("/api/daai/profile", headers=h, json={"name": " "}).status_code == 422
    assert client.post("/api/daai/profile", json={"bio": "x"}).status_code == 401
