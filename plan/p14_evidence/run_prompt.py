"""P1.4 prompt validation harness.

Connects to a running `omniagents run -c agents/rgv_lead_scraper/agent.yml --mode server --port 9494`
on ws://127.0.0.1:9494/ws, sends a single prompt via JSON-RPC `start_run`, and records every
inbound event (run_started, message_output, tool_called, client_request, tool_result, run_end)
to a JSONL transcript.

For any `client_request` (approval gate on `run_pipeline` / `run_stage`), this client AUTO-DENIES
with `approved=false`. That captures the agent's tool-call intent (what city/category it would
have used) WITHOUT spending a SerpAPI search.

Usage:
    python run_prompt.py "<prompt>" <out.jsonl>
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import websockets

URL = "ws://127.0.0.1:9494/ws"
TIMEOUT_S = 90  # generous; we'll exit early on run_end


async def main(prompt: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    next_req_id = 1

    async with websockets.connect(URL, max_size=None) as ws:
        # start_run
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": next_req_id,
            "method": "start_run",
            "params": {"prompt": prompt},
        }))
        next_req_id += 1

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_S)
                msg = json.loads(raw)
                events.append(msg)

                # Persist incrementally so partial runs are still inspectable
                out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")

                method = msg.get("method")
                # Server uses JSON-RPC notifications: {"jsonrpc","method","params"}
                if method == "client_request":
                    params = msg.get("params", {}) or {}
                    request_id = params.get("request_id") or params.get("id")
                    # Auto-deny to keep SerpAPI budget intact
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": next_req_id,
                        "method": "client_response",
                        "params": {
                            "request_id": request_id,
                            "ok": True,
                            "result": {"approved": False, "always_approve": False},
                        },
                    }))
                    next_req_id += 1
                elif method == "run_end":
                    break
        except asyncio.TimeoutError:
            events.append({"_harness": "timeout", "after_s": TIMEOUT_S})
            out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        except websockets.ConnectionClosed as e:
            events.append({"_harness": "connection_closed", "reason": str(e)})
            out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], Path(sys.argv[2])))
