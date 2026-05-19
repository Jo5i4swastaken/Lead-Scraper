"""Variant: approve the first tool call, deny subsequent ones.

Used for prompt 4 to verify whether the agent issues a SECOND tool call after the
first succeeds. Spends one real SerpAPI search.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import websockets

URL = "ws://127.0.0.1:9494/ws"
TIMEOUT_S = 180


async def main(prompt: str, out_path: Path, allow_first: bool = True) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    next_req_id = 1
    approval_count = 0

    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": next_req_id,
            "method": "start_run", "params": {"prompt": prompt},
        }))
        next_req_id += 1

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_S)
                msg = json.loads(raw)
                events.append(msg)
                out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")

                method = msg.get("method")
                if method == "client_request":
                    params = msg.get("params", {}) or {}
                    request_id = params.get("request_id") or params.get("id")
                    approve = (approval_count == 0 and allow_first)
                    approval_count += 1
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0", "id": next_req_id,
                        "method": "client_response",
                        "params": {
                            "request_id": request_id,
                            "ok": True,
                            "result": {"approved": approve, "always_approve": False},
                        },
                    }))
                    next_req_id += 1
                elif method == "run_end":
                    break
        except asyncio.TimeoutError:
            events.append({"_harness": "timeout"})
            out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        except websockets.ConnectionClosed as e:
            events.append({"_harness": "closed", "reason": str(e)})
            out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], Path(sys.argv[2])))
