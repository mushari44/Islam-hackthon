"""Recovery codes, signing other devices out on a password change, sliding da'i sessions and the da'i's own
password change. Owner: Eman."""
import os
import time

from backend.app.features.auth import security
from backend.app.features.auth.security import DAAI_TOKEN_TTL, sign, unsign

ABOUT = {"gender": "m", "age_band": "25_34"}


def new_device(client):
    return {"X-Seeker": client.post("/api/session").json()["token"]}


def test_new_recovery_code_replaces_the_old_one(client):
    home = new_device(client)
    first = client.post("/api/account/signup", json={"username": "rec_user", "password": "long-pass-1", **ABOUT},
                        headers=home).json()["recovery_code"]
    assert client.post("/api/account/recovery-code", json={"password": "wrong-pass"}, headers=home).status_code == 403
    made = client.post("/api/account/recovery-code", json={"password": "long-pass-1"}, headers=home)
    assert made.status_code == 200
    code = made.json()["recovery_code"]
    assert code != first and len(code) == 14
    # an anonymous browser can't ask for one
    assert client.post("/api/account/recovery-code", json={"password": "x"}, headers=new_device(client)).status_code == 403

    laptop = new_device(client)
    assert client.post("/api/account/recover", json={"username": "rec_user", "recovery_code": first,
                                                     "new_password": "new-pass-11"}, headers=laptop).status_code == 403
    done = client.post("/api/account/recover", json={"username": "rec_user", "recovery_code": code,
                                                     "new_password": "new-pass-11"}, headers=laptop)
    assert done.status_code == 200 and done.json()["account"]["username"] == "rec_user"
    # the recovery signed the other browsers out; the laptop that used the code is signed in
    assert client.get("/api/account", headers=home).status_code == 401
    assert client.get("/api/account", headers=laptop).json()["account"]["username"] == "rec_user"


def test_changing_the_password_signs_other_devices_out(client):
    home, phone, laptop = new_device(client), new_device(client), new_device(client)
    client.post("/api/account/signup", json={"username": "pw_change", "password": "long-pass-1", **ABOUT}, headers=home)
    client.post("/api/ask", data={"question": "سؤال محفوظ", "lang": "ar"}, headers=home)
    for h in (phone, laptop):
        assert client.post("/api/account/signin", json={"username": "pw_change", "password": "long-pass-1"},
                           headers=h).status_code == 200
    assert client.post("/api/account/password", json={"password": "long-pass-1", "new_password": "long-pass-2"},
                       headers=laptop).status_code == 200
    # this browser stays signed in and still sees the account's data, kept under its home session
    assert client.get("/api/account", headers=laptop).json()["account"]["username"] == "pw_change"
    assert [t["question"] for t in client.get("/api/ask/history", headers=laptop).json()["turns"]] == ["سؤال محفوظ"]
    # the phone is signed out; the home browser's token stops working, as after a normal sign-out
    assert client.get("/api/account", headers=phone).json()["account"] is None
    assert client.get("/api/account", headers=home).status_code == 401
    # signing in again with the new password brings the data back
    again = new_device(client)
    assert client.post("/api/account/signin", json={"username": "pw_change", "password": "long-pass-2"},
                       headers=again).status_code == 200
    assert len(client.get("/api/ask/history", headers=again).json()["turns"]) == 1


def test_daai_session_slides(client, daai_login):
    h = daai_login("reviewer")   # the reviewer's demo login keeps working
    fresh = client.get("/api/daai/me", headers=h).json()
    assert fresh["role"] == "admin" and "token" not in fresh   # a new token is not swapped yet

    me = client.get("/api/daai/me", headers=h).json()
    old = sign({"kind": "daai", "id": me["id"], "v": 0}, ttl=DAAI_TOKEN_TTL // 2 - 60)   # past half its life
    answer = client.get("/api/daai/me", headers={"Authorization": f"Bearer {old}"}).json()
    body = unsign(answer["token"])
    assert body["id"] == me["id"] and body["exp"] > time.time() + DAAI_TOKEN_TTL - 60
    assert client.get("/api/daai/me", headers={"Authorization": f"Bearer {answer['token']}"}).status_code == 200
    assert security.needs_refresh({"exp": time.time() + DAAI_TOKEN_TTL}) is False


def test_daai_changes_own_password(client, daai_login):
    admin = daai_login("reviewer")
    client.post("/api/daai/admin/daais", headers=admin,
                json={"username": "pw_daai", "password": "first-pass-1", "name": "داعية تجربة"})
    tab1 = client.post("/api/daai/login", json={"username": "pw_daai", "password": "first-pass-1"}).json()["token"]
    tab2 = client.post("/api/daai/login", json={"username": "pw_daai", "password": "first-pass-1"}).json()["token"]
    bearer = lambda tok: {"Authorization": f"Bearer {tok}"}   # noqa: E731

    assert client.post("/api/daai/password", json={"password": "nope", "new_password": "second-pass-2"},
                       headers=bearer(tab1)).status_code == 403
    assert client.post("/api/daai/password", json={"password": "first-pass-1", "new_password": "short"},
                       headers=bearer(tab1)).status_code == 422
    done = client.post("/api/daai/password", json={"password": "first-pass-1", "new_password": "second-pass-2"},
                       headers=bearer(tab1))
    assert done.status_code == 200 and done.json()["me"]["username"] == "pw_daai"
    assert client.get("/api/daai/me", headers=bearer(done.json()["token"])).status_code == 200
    assert client.get("/api/daai/me", headers=bearer(tab1)).status_code == 401   # every older token ends
    assert client.get("/api/daai/me", headers=bearer(tab2)).status_code == 401
    assert client.post("/api/daai/login", json={"username": "pw_daai", "password": "second-pass-2"}).status_code == 200

    # the shared sample accounts can't be changed, so the reviewer login keeps working for everyone
    assert client.post("/api/daai/password", json={"password": os.environ["DEMO_PASSWORD"], "new_password": "taken-over-1"},
                       headers=admin).status_code == 403
    assert client.post("/api/daai/login", json={"username": "reviewer", "password": os.environ["DEMO_PASSWORD"]}).status_code == 200
