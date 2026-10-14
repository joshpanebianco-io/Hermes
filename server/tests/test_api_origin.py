"""A write from another website is refused before any route runs (api.py
`same_desk_writes`). Driven through the ASGI app, as test_stockplan does —
no httpx in this venv, and no lifespan, so the collector never starts."""

from __future__ import annotations

import asyncio
from typing import Any

from newsterminal import api


def _call(method: str, path: str, origin: str | None) -> tuple[int, bytes]:
    out: dict[str, Any] = {"code": 0, "body": b""}

    async def run() -> None:
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            if msg["type"] == "http.response.start":
                out["code"] = msg["status"]
            elif msg["type"] == "http.response.body":
                out["body"] += msg.get("body", b"")

        headers = [(b"origin", origin.encode())] if origin else []
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": b"", "headers": headers, "client": ("test", 1),
            "server": ("test", 80), "root_path": "",
        }
        await api.app(scope, receive, send)

    asyncio.run(run())
    return out["code"], out["body"]


def test_a_foreign_page_cannot_spend_a_model_call_or_delete_history() -> None:
    refused = (403, b"cross-origin write refused")
    assert _call("POST", "/api/report", "https://evil.example") == refused
    assert _call("DELETE", "/api/plan/x", "http://192.168.1.20:3100")[0] == 403


def test_the_terminal_itself_is_not_refused() -> None:
    # The terminal's own page — the 404 is the route's answer, not the guard's.
    assert _call("DELETE", "/api/report/nonexistent-id", "http://localhost:3100")[0] != 403
    # The Next server's fetch names no origin at all.
    assert _call("DELETE", "/api/report/nonexistent-id", None)[0] != 403
