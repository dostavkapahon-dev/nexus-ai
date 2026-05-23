"""
Desktop Agent WebSocket bridge.
The local desktop_agent.py connects here and receives commands.
Dashboard sends commands; desktop agent executes them on the user PC.
"""
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional

router = APIRouter(tags=["desktop"])

_desktop_ws: Optional[WebSocket] = None
_pending_results: dict[str, asyncio.Future] = {}

@router.websocket("/ws/desktop")
async def desktop_agent_ws(ws: WebSocket):
    """The local desktop_agent.py connects here."""
    global _desktop_ws
    await ws.accept()
    _desktop_ws = ws
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            req_id = msg.get("req_id")
            if req_id and req_id in _pending_results:
                fut = _pending_results.pop(req_id)
                if not fut.done():
                    fut.set_result(msg)
    except WebSocketDisconnect:
        _desktop_ws = None

@router.get("/api/desktop/status")
async def desktop_status():
    return {"connected": _desktop_ws is not None}

@router.post("/api/desktop/command")
async def send_command(body: dict):
    """Send command to desktop agent and wait for result."""
    if not _desktop_ws:
        return {"ok": False, "error": "Desktop agent not connected. Run desktop_agent.py on your PC."}
    import uuid
    req_id = str(uuid.uuid4())
    body["req_id"] = req_id
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending_results[req_id] = fut
    await _desktop_ws.send_text(json.dumps(body))
    try:
        result = await asyncio.wait_for(fut, timeout=30.0)
        return {"ok": True, "result": result}
    except asyncio.TimeoutError:
        _pending_results.pop(req_id, None)
        return {"ok": False, "error": "Timeout: desktop agent did not respond in 30s"}