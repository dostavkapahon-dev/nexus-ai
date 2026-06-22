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

def desktop_connected() -> bool:
    return _desktop_ws is not None


async def send_to_desktop(body: dict, timeout: float = 30.0) -> dict:
    """Send a single command to the desktop agent and await its result.

    Returns the raw result dict from the agent, or raises RuntimeError on
    timeout / disconnection. Reused by both the HTTP endpoint and the
    autonomous browser agent loop.
    """
    if not _desktop_ws:
        raise RuntimeError("Desktop agent not connected. Run desktop_agent.py on your PC.")
    import uuid
    req_id = str(uuid.uuid4())
    body["req_id"] = req_id
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending_results[req_id] = fut
    await _desktop_ws.send_text(json.dumps(body))
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        _pending_results.pop(req_id, None)
        raise RuntimeError("Timeout: desktop agent did not respond in time")


@router.post("/api/desktop/command")
async def send_command(body: dict):
    """Send command to desktop agent and wait for result."""
    try:
        result = await send_to_desktop(body)
        return {"ok": True, "result": result}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/desktop/agent/run")
async def run_browser_agent(body: dict):
    """Run the autonomous vision browser agent on a natural-language task.

    Body: {"task": "...", "start_url": "https://...", "max_steps": 25}
    """
    from core.browser_agent import run_agent

    task = (body.get("task") or "").strip()
    if not task:
        return {"ok": False, "error": "Field 'task' is required."}
    if not desktop_connected():
        return {"ok": False, "error": "Desktop agent not connected. Run desktop_agent.py on your PC."}
    try:
        result = await run_agent(
            task=task,
            start_url=body.get("start_url"),
            max_steps=int(body.get("max_steps", 25)),
        )
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}