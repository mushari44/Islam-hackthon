"""Seekers can see the da'i directory, ask for one da'i by name, and call the same da'i again. Owner: Eman."""
from tests.conftest import seeker_headers


def test_directory_lists_callable_daais(client, daai_login):
    d = daai_login("maryam")
    client.post("/api/daai/availability", json={"available": True}, headers=d)
    people = client.get("/api/daais?lang=en&ui=en").json()
    names = {p["name"] for p in people}
    assert "Maryam (demo)" in names and "Reviewer (demo)" not in names     # reviewers don't take calls
    maryam = next(p for p in people if p["name"] == "Maryam (demo)")
    assert maryam["online"] is True and maryam["gender"] == "f" and "bio" in maryam
    assert all("en" in p["languages"] for p in people)
    assert people[0]["online"]                                              # online first


def test_request_a_named_daai_and_call_again(client, seeker, daai_login):
    h = seeker_headers(seeker)
    khalid, maryam = daai_login("khalid"), daai_login("maryam")
    mid = client.get("/api/daai/me", headers=maryam).json()["id"]

    assert client.post("/api/calls", json={"lang": "ar", "daai_id": 99999}, headers=h).status_code == 404
    assert client.post("/api/calls", json={"lang": "ar", "daai_id": mid, "gender_pref": "m"}, headers=h).status_code == 400

    call = client.post("/api/calls", json={"lang": "ar", "daai_id": mid}, headers=h).json()
    assert all(r["id"] != call["id"] for r in client.get("/api/daai/requests", headers=khalid).json()["waiting"])
    assert client.post(f"/api/daai/requests/{call['id']}/accept", headers=khalid).status_code == 404
    mine = client.get("/api/daai/requests", headers=maryam).json()["waiting"]
    assert mine[0]["id"] == call["id"] and mine[0]["for_you"] is True

    assert client.post(f"/api/daai/requests/{call['id']}/accept", headers=maryam).status_code == 200
    assert client.get(f"/api/calls/{call['id']}", headers=h).json()["daai"]["id"] == mid
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=maryam)

    past = client.get("/api/calls", headers=h).json()
    assert [p["daai"]["id"] for p in past] == [mid] and past[0]["lang"] == "ar"
