"""P1.4b auto-approval verification harness.

Talks to a running `omniagents run -c agents/rgv_lead_scraper/agent.yml --mode server --port 9494`
on ws://127.0.0.1:9494/ws. Verifies the round-5 approval policy:

  * Non-SerpAPI tools (`get_settings_summary`, `read_file`, `list_directory`)
    in `safe_tool_names` -> fire WITHOUT any `client_request` event.
  * SerpAPI-consuming tool (`run_pipeline`) NOT in `safe_tool_names` ->
    emits `client_request` for approval before executing.
  * Sending `always_approve: true` on the first approval suppresses further
    `client_request` events for that same tool within the same WebSocket
    session.

For each test, a fresh WebSocket connection is opened, one or more
`start_run` calls are issued, and every inbound event is captured to JSONL.

Test 5 (always_approve) deliberately reuses one WebSocket connection across
two `start_run` calls to detect session-scoped suppression.

Usage:
    python plan/p14b_evidence/run_tests.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import websockets

URL = "ws://127.0.0.1:9494/ws"
TIMEOUT_S = 90
EVIDENCE_DIR = Path(__file__).parent


def _summarize(events: list[dict]) -> dict[str, Any]:
    tool_calls: list[dict] = []
    client_requests: list[dict] = []
    run_ends: list[dict] = []
    tool_results: list[dict] = []
    for e in events:
        method = e.get("method")
        params = e.get("params", {}) or {}
        if method == "tool_called":
            tool_calls.append({
                "name": params.get("name") or params.get("tool_name"),
                "args": params.get("args") or params.get("arguments"),
            })
        elif method == "client_request":
            client_requests.append({
                "request_id": params.get("request_id") or params.get("id"),
                "tool_name": params.get("tool_name") or params.get("name"),
            })
        elif method == "tool_result":
            tool_results.append({
                "name": params.get("name") or params.get("tool_name"),
                "ok": params.get("ok"),
                "error": params.get("error"),
            })
        elif method == "run_end":
            run_ends.append({"end_reason": params.get("end_reason")})
    return {
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "client_requests": client_requests,
        "run_ends": run_ends,
    }


async def _run_one(
    ws,
    prompt: str,
    request_id_start: int,
    *,
    approval_mode: str = "deny",  # "deny" | "approve_once" | "approve_always"
    events_out: list[dict] | None = None,
) -> tuple[int, list[dict]]:
    """Send one start_run, collect events until run_end."""
    events: list[dict] = events_out if events_out is not None else []
    next_req_id = request_id_start

    await ws.send(json.dumps({
        "jsonrpc": "2.0",
        "id": next_req_id,
        "method": "start_run",
        "params": {"prompt": prompt},
    }))
    next_req_id += 1

    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_S)
        msg = json.loads(raw)
        events.append(msg)

        method = msg.get("method")
        if method == "client_request":
            params = msg.get("params", {}) or {}
            request_id = params.get("request_id") or params.get("id")
            if approval_mode == "deny":
                result = {"approved": False, "always_approve": False}
            elif approval_mode == "approve_once":
                result = {"approved": True, "always_approve": False}
            elif approval_mode == "approve_always":
                result = {"approved": True, "always_approve": True}
            else:
                raise ValueError(f"unknown approval_mode={approval_mode}")
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": next_req_id,
                "method": "client_response",
                "params": {
                    "request_id": request_id,
                    "ok": True,
                    "result": result,
                },
            }))
            next_req_id += 1
        elif method == "run_end":
            break

    return next_req_id, events


async def test_case(
    label: str,
    prompt: str,
    out_path: Path,
    *,
    approval_mode: str = "deny",
) -> dict[str, Any]:
    """One test: open WS, send one start_run, deny any client_request, persist."""
    events: list[dict] = []
    async with websockets.connect(URL, max_size=None) as ws:
        try:
            await _run_one(ws, prompt, 1, approval_mode=approval_mode, events_out=events)
        except asyncio.TimeoutError:
            events.append({"_harness": "timeout", "after_s": TIMEOUT_S})
        except websockets.ConnectionClosed as e:
            events.append({"_harness": "connection_closed", "reason": str(e)})

    out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return {
        "label": label,
        "prompt": prompt,
        "approval_mode": approval_mode,
        "evidence": str(out_path.relative_to(EVIDENCE_DIR.parent.parent)),
        **_summarize(events),
    }


async def test_always_approve(out_path: Path) -> dict[str, Any]:
    """Two start_runs in ONE WebSocket connection. First: approve_always.
    Second: verify NO client_request fires."""
    events: list[dict] = []
    boundary = -1
    async with websockets.connect(URL, max_size=None) as ws:
        try:
            next_id, _ = await _run_one(
                ws,
                "Use the run_pipeline tool to scrape leads for city=McAllen category=plumbers.",
                1,
                approval_mode="approve_always",
                events_out=events,
            )
            boundary = len(events)
            events.append({"_harness": "boundary", "first_run_events": boundary})
            await _run_one(
                ws,
                "Now use the run_pipeline tool to scrape leads for city=Edinburg category=plumbers.",
                next_id,
                approval_mode="deny",  # if always_approve failed, we deny rather than burn budget
                events_out=events,
            )
        except asyncio.TimeoutError:
            events.append({"_harness": "timeout", "after_s": TIMEOUT_S})
        except websockets.ConnectionClosed as e:
            events.append({"_harness": "connection_closed", "reason": str(e)})

    out_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    first = events[:boundary] if boundary > 0 else events
    second = events[boundary + 1:] if boundary > 0 else []
    return {
        "label": "T5_always_approve_session_scope",
        "evidence": str(out_path.relative_to(EVIDENCE_DIR.parent.parent)),
        "first_run": _summarize(first),
        "second_run": _summarize(second),
    }


async def main() -> None:
    results: list[dict[str, Any]] = []

    results.append(await test_case(
        "T1_get_settings_summary",
        "Call the get_settings_summary tool and show me the result. Do not call any other tool.",
        EVIDENCE_DIR / "t1_get_settings_summary.jsonl",
        approval_mode="deny",
    ))

    results.append(await test_case(
        "T2_read_file",
        "Use the read_file tool to read the file at agents/rgv_lead_scraper/agent.yml and "
        "show me what's inside. Do not call any other tool.",
        EVIDENCE_DIR / "t2_read_file.jsonl",
        approval_mode="deny",
    ))

    results.append(await test_case(
        "T3_list_directory",
        "Use the list_directory tool to list the contents of agents/rgv_lead_scraper. "
        "Do not call any other tool.",
        EVIDENCE_DIR / "t3_list_directory.jsonl",
        approval_mode="deny",
    ))

    results.append(await test_case(
        "T4_run_pipeline_gates",
        "Use the run_pipeline tool to scrape city=McAllen category=plumbers.",
        EVIDENCE_DIR / "t4_run_pipeline_gates.jsonl",
        approval_mode="deny",
    ))

    results.append(await test_always_approve(EVIDENCE_DIR / "t5_always_approve.jsonl"))

    (EVIDENCE_DIR / "summary.json").write_text(json.dumps(results, indent=2) + "\n")

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
