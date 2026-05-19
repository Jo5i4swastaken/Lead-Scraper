"""Single-run always_approve test (T5b).

Per Copy Agent's `agent-rpc.ts` docstring: `always_approve: true` is scoped to
**the current run** (auto-approves further calls to the same tool until run_end).

This script issues ONE start_run with a multi-city prompt so the agent issues
multiple `run_pipeline` calls back-to-back inside a single run. The first call's
approval is answered with `always_approve: true`; subsequent run_pipeline
gates within the same run should NOT fire.

Cost: up to 2 SerpAPI searches if both calls execute.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import websockets

URL = "ws://127.0.0.1:9494/ws"
TIMEOUT_S = 180
EVIDENCE = Path(__file__).parent / "t5b_always_approve_single_run.jsonl"

PROMPT = (
    "Scrape leads for two RGV cities one after the other: first city=McAllen "
    "category=plumbers, then city=Edinburg category=plumbers. Use the "
    "run_pipeline tool for each. Issue both calls in this same run."
)


async def main() -> None:
    events: list[dict] = []
    approvals_sent = 0
    next_id = 1

    async with websockets.connect(URL, max_size=None) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "start_run",
            "params": {"prompt": PROMPT},
        }))
        next_id += 1

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_S)
                msg = json.loads(raw)
                events.append(msg)
                EVIDENCE.write_text("\n".join(json.dumps(e) for e in events) + "\n")

                method = msg.get("method")
                params = msg.get("params", {}) or {}
                fn = params.get("function") if isinstance(params, dict) else None

                if method == "client_request" and fn == "ui.request_tool_approval":
                    request_id = params.get("request_id")
                    approvals_sent += 1
                    # First approval = approve_always; we expect NO further approval
                    # requests after this, but if any DO fire we deny them so we
                    # don't burn budget on a buggy gate behaviour.
                    if approvals_sent == 1:
                        result = {"approved": True, "always_approve": True}
                    else:
                        result = {"approved": False, "always_approve": False}
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": next_id,
                        "method": "client_response",
                        "params": {
                            "request_id": request_id,
                            "ok": True,
                            "result": result,
                        },
                    }))
                    next_id += 1
                elif method == "run_end":
                    break
        except asyncio.TimeoutError:
            events.append({"_harness": "timeout"})
            EVIDENCE.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    # Summary
    tool_calls = [e for e in events if e.get("method") == "tool_called"]
    approval_requests = [
        e for e in events
        if e.get("method") == "client_request"
        and (e.get("params") or {}).get("function") == "ui.request_tool_approval"
    ]
    tool_results = [e for e in events if e.get("method") == "tool_result"]

    print(json.dumps({
        "approvals_sent": approvals_sent,
        "tool_called_count": len(tool_calls),
        "approval_request_count": len(approval_requests),
        "tool_result_count": len(tool_results),
        "tool_called_summary": [
            {"tool": (e.get("params") or {}).get("tool"),
             "input": (e.get("params") or {}).get("input")[:200]}
            for e in tool_calls
        ],
        "approval_request_summary": [
            {"tool": (e.get("params") or {}).get("args", {}).get("tool"),
             "args": (e.get("params") or {}).get("args", {}).get("arguments")}
            for e in approval_requests
        ],
        "tool_result_summary": [
            (e.get("params") or {}).get("output", "")[:200]
            for e in tool_results
        ],
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
