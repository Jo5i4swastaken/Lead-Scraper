"""Probe OmniAgents JSON-RPC text-mode WebSocket surface (Phase 1.4c)."""
import asyncio
import json
import uuid

import websockets

URL = "ws://127.0.0.1:9495/ws"


async def call(ws, method, params=None, call_id=None, timeout=20):
    cid = call_id or str(uuid.uuid4())[:8]
    await ws.send(json.dumps({"jsonrpc": "2.0", "id": cid, "method": method, "params": params or {}}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("id") == cid:
            return msg
        m = msg.get("method")
        p = msg.get("params") or {}
        if isinstance(p, dict):
            print(f"  (notif) {m}: keys={list(p.keys())}")
        else:
            print(f"  (notif) {m}: type={type(p).__name__}")


async def drain_until_run_end(ws, label, timeout=60, max_events=80):
    end_reason = None
    final_message = None
    for _ in range(max_events):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"  [{label}] TIMEOUT waiting for event")
            return end_reason, final_message
        msg = json.loads(raw)
        method = msg.get("method") or f"resp:{msg.get('id')}"
        p = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "message_output":
            content = p.get("content") or p.get("message") or p
            txt = (content if isinstance(content, str) else json.dumps(content, default=str))[:300]
            print(f"  [{label}] message_output: {txt}")
            final_message = content
        elif method == "run_end":
            end_reason = p.get("end_reason")
            print(f"  [{label}] run_end end_reason={end_reason}")
            return end_reason, final_message
        elif method in ("tool_called", "tool_result", "run_started"):
            print(f"  [{label}] {method} keys={list(p.keys())}")
        elif method == "token":
            pass
        else:
            print(f"  [{label}] {method} keys={list(p.keys()) if isinstance(p, dict) else type(p).__name__}")
    return end_reason, final_message


async def main():
    print("=== Probe 1: connect & introspect ===")
    async with websockets.connect(URL) as ws:
        r = await call(ws, "get_agent_info")
        print("get_agent_info →", json.dumps(r, default=str)[:400])

        r = await call(ws, "list_sessions")
        sessions = r.get("result") or []
        if isinstance(r.get("error"), dict):
            print("list_sessions ERROR:", r["error"])
        else:
            print(f"list_sessions → {len(sessions)} sessions (showing first 3)")
            for s in sessions[:3]:
                print("    ", json.dumps(s, default=str)[:240])

        # voice-only methods – expect error in text mode
        for m in ("get_session_info",):
            r = await call(ws, m, {"session_id": "probe-nonexistent"})
            print(f"{m}(session_id=probe-nonexistent) →", json.dumps(r, default=str)[:300])

    print("\n=== Probe 2: start run with explicit session_id ===")
    SID = f"probe-{uuid.uuid4().hex[:8]}"
    print(f"using session_id={SID}")
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "s1", "method": "start_run",
            "params": {
                "prompt": "Reply with exactly the word PONG and nothing else. Do not call any tools.",
                "session_id": SID,
            },
        }))
        end_reason, _ = await drain_until_run_end(ws, "run1")
        print(f"  run1 ended: {end_reason}")

    print("\n=== Probe 3: list+history for that session via JSON-RPC ===")
    async with websockets.connect(URL) as ws:
        r = await call(ws, "list_sessions")
        sessions = r.get("result") or []
        match = [s for s in sessions if s.get("id") == SID or s.get("session_id") == SID]
        print(f"list_sessions → {len(sessions)} total; matched probe id: {len(match)}")
        for s in match[:1]:
            print("   probe session row:", json.dumps(s, default=str)[:400])

        r = await call(ws, "get_session_history", {"session_id": SID})
        hist = r.get("result") or []
        if isinstance(r.get("error"), dict):
            print("get_session_history ERROR:", r["error"])
        else:
            print(f"get_session_history({SID}) → {len(hist)} entries")
            for h in hist[:6]:
                print("    ", json.dumps(h, default=str)[:240])

    print("\n=== Probe 4: reconnect with same session_id; verify context preserved ===")
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "s2", "method": "start_run",
            "params": {
                "prompt": "What was the exact one-word reply you just gave in your previous turn? Quote it.",
                "session_id": SID,
            },
        }))
        end_reason, final = await drain_until_run_end(ws, "run2")
        print(f"  run2 ended: {end_reason}")
        print(f"  context-preservation check — final message: {str(final)[:300]}")


asyncio.run(main())
