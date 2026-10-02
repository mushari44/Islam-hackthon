"""WebRTC signalling relay and in-call chat over WebSocket. Owner: Eman.

The server never touches audio. It forwards offer/answer/ICE messages between
the two people in a call and stores the text chat (CallMessage). Rooms live in
memory, so run a single worker (see README).
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...core.db import SessionLocal, iso, utcnow
from ..auth.public import daai_from_token, seeker_id
from .models import CallMessage, CallRequest

ws_router = APIRouter()

# ---------------------------------------------------------------------------

class Rooms:
    def __init__(self) -> None:
        self.peers: dict[int, dict[str, WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def join(self, cid: int, role: str, ws: WebSocket) -> None:
        async with self.lock:
            room = self.peers.setdefault(cid, {})
            old = room.get(role)
            room[role] = ws
        if old is not None:
            try:
                await old.close(code=4001)
            except RuntimeError:
                pass

    async def leave(self, cid: int, role: str, ws: WebSocket) -> None:
        async with self.lock:
            room = self.peers.get(cid, {})
            if room.get(role) is ws:
                room.pop(role, None)
            if not room:
                self.peers.pop(cid, None)

    async def send_other(self, cid: int, role: str, msg: dict) -> bool:
        other = self.peers.get(cid, {}).get("daai" if role == "seeker" else "seeker")
        if other is None:
            return False
        try:
            await other.send_text(json.dumps(msg))
            return True
        except RuntimeError:
            return False

    def present(self, cid: int) -> list[str]:
        return list(self.peers.get(cid, {}).keys())


rooms = Rooms()
RELAY_TYPES = {"offer", "answer", "ice", "bye", "mute", "ready"}


def _authorize(cid: int, role: str, token: str) -> CallRequest | None:
    db = SessionLocal()
    try:
        call = db.get(CallRequest, cid)
        if not call or call.status != "accepted":
            return None
        if role == "seeker" and call.session_id == seeker_id(token):
            return call
        if role == "daai":
            d = daai_from_token(token, db)
            if d and d.id == call.daai_id:
                return call
        return None
    finally:
        db.close()


@ws_router.websocket("/ws/call/{cid}")
async def call_socket(ws: WebSocket, cid: int, role: str = "seeker", token: str = ""):
    await ws.accept()
    if role not in ("seeker", "daai") or not _authorize(cid, role, token):
        await ws.close(code=4003)  # accepted first so the browser sees 4003, not 1006
        return
    await rooms.join(cid, role, ws)
    present = rooms.present(cid)
    await ws.send_text(json.dumps({"type": "joined", "role": role, "present": present}))
    await rooms.send_other(cid, role, {"type": "peer-joined", "role": role})
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > 64_000:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind in RELAY_TYPES:
                await rooms.send_other(cid, role, msg)
            elif kind == "chat":
                text = str(msg.get("text", ""))[:1000].strip()
                if not text:
                    continue
                db = SessionLocal()
                try:
                    m = CallMessage(call_id=cid, sender=role, text=text)
                    db.add(m)
                    db.commit()
                    out = {"type": "chat", "id": m.id, "sender": role, "text": text, "at": iso(m.created_at)}
                finally:
                    db.close()
                await ws.send_text(json.dumps(out))
                await rooms.send_other(cid, role, out)
            elif kind == "end":
                db = SessionLocal()
                try:
                    call = db.get(CallRequest, cid)
                    if call and call.status == "accepted":
                        call.status, call.ended_at = "ended", utcnow()
                        db.commit()
                finally:
                    db.close()
                await rooms.send_other(cid, role, {"type": "ended", "by": role})
    except WebSocketDisconnect:
        pass
    finally:
        await rooms.leave(cid, role, ws)
        await rooms.send_other(cid, role, {"type": "peer-left", "role": role})
