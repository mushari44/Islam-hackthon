"""A seeker who left the waiting screen drops out of the da'i's queue, and an abandoned call room is closed.
Owner: Eman. Time is simulated by moving the row's timestamps back."""
import time
from datetime import timedelta

from backend.app.core.db import SessionLocal, utcnow
from backend.app.features.calls.models import CallRequest
from tests.conftest import seeker_headers


def _age(cid: int, **fields: timedelta) -> None:
    """Moves the given timestamp columns of a call this far into the past."""
    with SessionLocal() as db:
        call = db.get(CallRequest, cid)
        for name, ago in fields.items():
            setattr(call, name, utcnow() - ago)
        db.commit()


def _queue_ids(client, d) -> list[int]:
    return [r["id"] for r in client.get("/api/daai/requests", headers=d).json()["waiting"]]


def test_unseen_request_leaves_the_queue_and_cannot_be_accepted(client, caller, daai_login):
    h = seeker_headers(caller)
    d = daai_login("khalid")
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    assert call["id"] in _queue_ids(client, d)

    _age(call["id"], last_seen_at=timedelta(seconds=80))   # the seeker closed the tab 80 s ago
    assert call["id"] not in _queue_ids(client, d)
    res = client.post(f"/api/daai/requests/{call['id']}/accept", headers=d)
    assert res.status_code == 409 and res.json()["detail"] == "seeker left"

    # A reload soon after resumes the request: its poll brings it back to the queue.
    assert client.get(f"/api/calls/{call['id']}", headers=h).json()["status"] == "waiting"
    assert call["id"] in _queue_ids(client, d)

    _age(call["id"], last_seen_at=timedelta(seconds=120))   # gone for good
    assert call["id"] not in _queue_ids(client, d)
    assert client.get(f"/api/calls/{call['id']}", headers=h).json()["status"] == "expired"


def test_call_nobody_is_in_ends_after_five_minutes(client, caller, daai_login):
    h = seeker_headers(caller)
    d = daai_login("khalid")
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    assert client.post(f"/api/daai/requests/{call['id']}/accept", headers=d).status_code == 200
    active = client.get("/api/daai/requests", headers=d).json()["active"]
    assert any(c["id"] == call["id"] for c in active)            # fresh: still the da'i's current call

    # Both people joined and left; the room has been empty for six minutes.
    url = f"/ws/call/{call['id']}"
    with client.websocket_connect(f"{url}?role=seeker&token={caller['_token']}") as ws:
        assert ws.receive_json()["type"] == "joined"
    for _ in range(100):   # the server notes the empty room just after the socket closes
        with SessionLocal() as db:
            if db.get(CallRequest, call["id"]).room_empty_at:
                break
        time.sleep(0.02)
    _age(call["id"], room_empty_at=timedelta(minutes=6))
    active = client.get("/api/daai/requests", headers=d).json()["active"]
    assert all(c["id"] != call["id"] for c in active)
    assert client.get(f"/api/calls/{call['id']}", headers=h).json()["status"] == "ended"


def test_call_with_someone_in_the_room_stays_open(client, caller, daai_login):
    h = seeker_headers(caller)
    d = daai_login("khalid")
    call = client.post("/api/calls", json={"lang": "ar"}, headers=h).json()
    client.post(f"/api/daai/requests/{call['id']}/accept", headers=d)
    _age(call["id"], accepted_at=timedelta(minutes=10), room_empty_at=timedelta(minutes=6))
    url = f"/ws/call/{call['id']}"
    with client.websocket_connect(f"{url}?role=daai&token={d['_token']}") as ws:
        assert ws.receive_json()["type"] == "joined"
        active = client.get("/api/daai/requests", headers=d).json()["active"]
        assert any(c["id"] == call["id"] for c in active)
    client.post(f"/api/daai/calls/{call['id']}/end", json={}, headers=d)
