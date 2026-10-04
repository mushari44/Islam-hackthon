"""Profile fields (seeker age band and place, da'i gender and place), da'i accounts managed by the reviewer,
and the column migration for databases made before a model gained a field."""
import os

from sqlalchemy import create_engine, inspect, text

from backend.app.core import db as core_db


ABOUT = {"gender": "m", "age_band": "35_44"}     # required at sign-up


def new_device(client):
    return {"X-Seeker": client.post("/api/session").json()["token"]}


def test_seeker_age_band_is_required_and_checked(client):
    h = new_device(client)
    acc = client.post("/api/account/signup", json={"username": "age_test", "password": "long-pass-1", **ABOUT}, headers=h)
    assert acc.json()["account"]["age_band"] == "35_44"
    res = client.post("/api/account/profile", json={"age_band": "25_34", "country": "SA", "city": "الرياض"}, headers=h)
    assert res.json()["account"].items() >= {"age_band": "25_34", "country": "SA", "city": "الرياض"}.items()
    assert client.post("/api/account/profile", json={"age_band": "31"}, headers=h).status_code == 422
    # there is no "prefer not to say": the age band can be changed, not removed
    assert client.post("/api/account/profile", json={"age_band": ""}, headers=h).status_code == 422
    # anonymous use keeps working: no account, nothing asked
    assert client.post("/api/account/profile", json={"age_band": "u18"}, headers=new_device(client)).status_code == 403


def test_daai_edits_gender_and_place(client, daai_login):
    h = daai_login("yusuf")
    res = client.post("/api/daai/profile", headers=h, json={"country": "gb", "city": "London", "gender": "m"})
    assert res.status_code == 200 and res.json()["country"] == "GB" and res.json()["city"] == "London"
    # a new country clears the old city
    assert client.post("/api/daai/profile", headers=h, json={"country": "US"}).json()["city"] == ""
    assert client.post("/api/daai/profile", headers=h, json={"gender": "x"}).status_code == 422
    assert client.post("/api/daai/profile", headers=h, json={"country": "USA"}).status_code == 422
    client.post("/api/daai/profile", headers=h, json={"country": "", "city": ""})


def test_reviewer_manages_daai_accounts(client, daai_login):
    admin = daai_login("reviewer")
    assert client.get("/api/daai/admin/daais", headers=daai_login("khalid")).status_code == 403

    made = client.post("/api/daai/admin/daais", headers=admin, json={
        "username": "Hamza_demo", "password": "first-pass-1", "name": "حمزة (حساب تجريبي)", "gender": "m",
        "languages": ["en"], "country": "GB", "city": "London"})
    assert made.status_code == 200, made.text
    new = made.json()
    assert new["username"] == "hamza_demo" and new["languages"] == ["en"] and new["city"] == "London"
    assert client.post("/api/daai/admin/daais", headers=admin, json={
        "username": "hamza_demo", "password": "first-pass-1", "name": "x y"}).status_code == 409
    assert any(d["id"] == new["id"] for d in client.get("/api/daai/admin/daais", headers=admin).json())

    login = client.post("/api/daai/login", json={"username": "hamza_demo", "password": "first-pass-1"}).json()
    old = {"Authorization": f"Bearer {login['token']}"}
    assert client.get("/api/daai/me", headers=old).status_code == 200

    # a password reset signs the da'i out everywhere
    client.post(f"/api/daai/admin/daais/{new['id']}", headers=admin, json={"password": "second-pass-2"})
    assert client.get("/api/daai/me", headers=old).status_code == 401
    assert client.post("/api/daai/login", json={"username": "hamza_demo", "password": "second-pass-2"}).status_code == 200

    # a disabled account can't sign in, and leaves the directory
    off = client.post(f"/api/daai/admin/daais/{new['id']}", headers=admin, json={"active": False}).json()
    assert off["active"] is False and off["available"] is False
    assert client.post("/api/daai/login", json={"username": "hamza_demo", "password": "second-pass-2"}).status_code == 403
    assert all(d["id"] != new["id"] for d in client.get("/api/daais").json())

    me = client.get("/api/daai/me", headers=admin).json()
    assert client.post(f"/api/daai/admin/daais/{me['id']}", headers=admin, json={"active": False}).status_code == 400


def test_daai_login_is_rate_limited(client):
    for _ in range(5):
        client.post("/api/daai/login", json={"username": "maryam", "password": "wrong"})
    assert client.post("/api/daai/login", json={"username": "maryam",
                                               "password": os.environ["DEMO_PASSWORD"]}).status_code == 429
    from backend.app.features.auth import routes
    routes._failures.pop("daai:maryam", None)


def test_missing_columns_are_added(tmp_path, monkeypatch):
    """A database from before a column existed gets the column (with its default) at start-up."""
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE daai (id INTEGER PRIMARY KEY, username VARCHAR(64), display_name VARCHAR(120),'
                          ' password_hash VARCHAR(256))'))
        conn.execute(text("INSERT INTO daai (id, username, display_name, password_hash) VALUES (1, 'old', 'Old', 'x')"))
    monkeypatch.setattr(core_db, "engine", eng)
    added = core_db.add_missing_columns()
    assert "daai.active" in added and "daai.country" in added
    assert {c["name"] for c in inspect(eng).get_columns("daai")} >= {"active", "country", "token_version"}
    with eng.connect() as conn:
        row = conn.execute(text("SELECT active, country, token_version FROM daai WHERE id = 1")).one()
    assert tuple(row) == (1, "", 0)
    assert core_db.add_missing_columns() == []      # running it again changes nothing


def test_signup_needs_sex_and_age_and_takes_language_and_place(client):
    # the seeker picks their sex and age band: there is no "prefer not to say"
    for missing in ({}, {"gender": "m"}, {"age_band": "18_24"}, {"gender": "", "age_band": "18_24"},
                    {"gender": "m", "age_band": ""}):
        res = client.post("/api/account/signup", headers=new_device(client),
                          json={"username": "missing_1", "password": "long-pass-1", **missing})
        assert res.status_code == 422, missing
    bare = client.post("/api/account/signup", json={"username": "defaults_1", "password": "long-pass-1", **ABOUT},
                       headers=new_device(client)).json()["account"]
    assert {k: bare[k] for k in ("lang", "country", "city", "age_band", "gender")} == \
        {"lang": "ar", "country": "", "city": "", "age_band": "35_44", "gender": "m"}

    h = new_device(client)
    full = client.post("/api/account/signup", headers=h, json={
        "username": "full_1", "password": "long-pass-1", "lang": "en", "country": "gb", "city": " London ",
        "age_band": "18_24", "gender": "f"}).json()["account"]
    assert {k: full[k] for k in ("lang", "country", "city", "age_band", "gender")} == \
        {"lang": "en", "country": "GB", "city": "London", "age_band": "18_24", "gender": "f"}
    assert client.post("/api/account/profile", json={"gender": "m", "lang": "ar"}, headers=h).json()["account"] \
        .items() >= {"gender": "m", "lang": "ar"}.items()
    assert client.post("/api/account/profile", json={"gender": ""}, headers=h).status_code == 422

    for bad in ({"lang": "xx"}, {"gender": "x"}, {"age_band": "30"}, {"country": "G1"}):
        res = client.post("/api/account/signup", headers=new_device(client),
                          json={"username": "bad_1", "password": "long-pass-1", **ABOUT, **bad})
        assert res.status_code == 422, bad
    assert client.post("/api/account/profile", json={"gender": "x"}, headers=h).status_code == 422
