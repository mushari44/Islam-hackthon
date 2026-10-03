"""Optional seeker accounts: sign up, sign in on another device, recover, delete. Owner: Eman."""


def new_device(client):
    token = client.post("/api/session").json()["token"]
    return {"X-Seeker": token}, token


def test_account_follows_the_seeker_across_devices(client):
    phone, _ = new_device(client)
    meetup = next(m for m in client.get("/api/meetups").json() if m["registration"] == "required"
                  and m["audience"] == "all" and m["age_group"] == "all")
    client.post(f"/api/meetups/{meetup['id']}/rsvp", json={"nickname": "زائر"}, headers=phone)
    assert client.get("/api/account", headers=phone).json()["account"] is None

    made = client.post("/api/account/signup", json={"username": "salam_1", "password": "long-pass-1"}, headers=phone)
    assert made.status_code == 200 and len(made.json()["recovery_code"]) == 14
    code = made.json()["recovery_code"]
    # the same name can't be taken twice, whatever the case
    other, _ = new_device(client)
    assert client.post("/api/account/signup", json={"username": "SALAM_1", "password": "long-pass-2"},
                       headers=other).status_code == 409

    laptop, laptop_token = new_device(client)
    assert client.post("/api/account/signin", json={"username": "Salam_1", "password": "nope-nope"},
                       headers=laptop).status_code == 403
    signed = client.post("/api/account/signin", json={"username": "salam_1", "password": "long-pass-1"}, headers=laptop)
    assert signed.json()["account"]["username"] == "salam_1"
    # the booking made on the phone shows on the laptop
    mine = {m["id"]: m["my_rsvp"] for m in client.get("/api/meetups", headers=laptop).json()}
    assert mine[meetup["id"]] is not None

    client.post("/api/account/profile", json={"country": "SA", "city": "جدة"}, headers=laptop)
    assert client.get("/api/account", headers=phone).json()["account"]["city"] == "جدة"

    client.post("/api/account/signout", headers=laptop)
    assert client.get("/api/account", headers=laptop).json()["account"] is None
    assert {m["id"]: m["my_rsvp"] for m in client.get("/api/meetups", headers=laptop).json()}[meetup["id"]] is None

    # forgotten password: the recovery code resets it and is replaced
    reset = client.post("/api/account/recover", json={"username": "salam_1", "recovery_code": code.lower(),
                                                      "new_password": "new-pass-22"}, headers=laptop)
    assert reset.status_code == 200 and reset.json()["recovery_code"] != code
    assert client.post("/api/account/recover", json={"username": "salam_1", "recovery_code": code,
                                                     "new_password": "x-x-x-x-x"}, headers=other).status_code == 403
    assert client.post("/api/account/password", json={"password": "new-pass-22", "new_password": "newer-pass-3"},
                       headers=laptop).status_code == 200

    # deleting the account removes its data on every device
    assert client.post("/api/account/delete", json={"password": "wrong"}, headers=laptop).status_code == 403
    assert client.post("/api/account/delete", json={"password": "newer-pass-3"}, headers=laptop).status_code == 200
    assert client.post("/api/account/signin", json={"username": "salam_1", "password": "newer-pass-3"},
                       headers=laptop).status_code == 403
    assert client.get("/api/account", headers=phone).status_code == 401   # the phone's session went with it


def test_signup_rules_and_lockout(client):
    h, _ = new_device(client)
    for bad in ["ab", "has space", "12345", "a" * 25]:
        assert client.post("/api/account/signup", json={"username": bad, "password": "long-pass-1"},
                           headers=h).status_code == 422
    assert client.post("/api/account/signup", json={"username": "short_pw", "password": "short"},
                       headers=h).status_code == 422
    assert client.post("/api/account/signup", json={"username": "نور_الهدى", "password": "long-pass-1"},
                       headers=h).status_code == 200
    other, _ = new_device(client)
    codes = [client.post("/api/account/signin", json={"username": "نور_الهدى", "password": "wrong-pass"},
                         headers=other).status_code for _ in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429


def test_call_room_accepts_a_signed_in_device(client, daai_login):
    phone, _ = new_device(client)
    client.post("/api/account/signup", json={"username": "caller_9", "password": "long-pass-1"}, headers=phone)
    laptop, laptop_token = new_device(client)
    client.post("/api/account/signin", json={"username": "caller_9", "password": "long-pass-1"}, headers=laptop)
    d = daai_login("khalid")
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    call = client.post("/api/calls", json={"lang": "ar"}, headers=laptop).json()
    client.post(f"/api/daai/requests/{call['id']}/accept", headers=d)
    with client.websocket_connect(f"/ws/call/{call['id']}?role=seeker&token={laptop_token}") as ws:
        assert ws.receive_json()["type"] == "joined"
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)


def test_forgot_password_by_email(client, monkeypatch):
    from backend.app.features.auth import mailer
    sent = []
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, body: sent.append((to, body)) or True)

    h, _ = new_device(client)
    assert client.post("/api/account/signup", json={"username": "maily", "password": "long-pass-1", "email": "bad"},
                       headers=h).status_code == 422
    made = client.post("/api/account/signup", json={"username": "maily", "password": "long-pass-1",
                                                    "email": "Maily@Example.com"}, headers=h).json()
    assert made["account"]["email"] == "maily@example.com"
    other, _ = new_device(client)
    assert client.post("/api/account/signup", json={"username": "maily2", "password": "long-pass-1",
                                                    "email": "maily@example.com"}, headers=other).status_code == 409

    # same answer for an unknown account, and nothing is sent
    assert client.post("/api/account/forgot", json={"login": "nobody_here"}).json() == {"via": "email"}
    assert sent == []
    assert client.post("/api/account/forgot", json={"login": "maily@example.com"}).json() == {"via": "email"}
    to, body = sent[-1]
    code = body.split("Your code: ")[1][:6]
    assert to == "maily@example.com" and code.isdigit()

    laptop, _ = new_device(client)
    assert client.post("/api/account/reset", json={"login": "maily", "code": "000000", "new_password": "new-pass-1"},
                       headers=laptop).status_code == 403
    done = client.post("/api/account/reset", json={"login": "maily", "code": code, "new_password": "new-pass-1"},
                       headers=laptop)
    assert done.status_code == 200 and done.json()["account"]["username"] == "maily"
    # the code works once
    assert client.post("/api/account/reset", json={"login": "maily", "code": code, "new_password": "x-new-pass-2"},
                       headers=laptop).status_code == 403
    assert client.post("/api/account/signin", json={"username": "maily", "password": "new-pass-1"},
                       headers=other).status_code == 200


def test_forgot_without_mail_uses_recovery_code(client, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert client.post("/api/account/forgot", json={"login": "anyone"}).json() == {"via": "recovery"}
