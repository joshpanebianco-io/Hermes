"""A generation is a job (jobs.py) and an attempt has a wall clock (report._post).

What these guard against, 2026-10-27: a brief took 332s on a crawling free
pool — past the web proxy's window, so the page reported a failure for a note
the collector stored a minute later — and a second generation ran nine minutes
and produced nothing, because the socket timeout never fires while
OpenRouter's keep-alive trickles bytes.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

from newsterminal import jobs
from newsterminal import report as rp

from .test_stockplan import _asgi

# ---------------------------------------------------------------- the wall clock


class _Trickle:
    """A response that keeps the connection alive forever, as OpenRouter does
    while a provider is still writing: an 11-byte whitespace chunk, again and
    again, never the body."""

    def __init__(self) -> None:
        self.closed = False
        self.reads = 0

    def __enter__(self) -> _Trickle:
        return self

    def __exit__(self, *a: Any) -> None:
        self.closed = True

    def read1(self, n: int) -> bytes:
        self.reads += 1
        time.sleep(0.005)
        return b"\n         \n"

    def close(self) -> None:
        self.closed = True


def test_post_abandons_an_answer_still_coming_at_the_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = _Trickle()
    monkeypatch.setattr(rp.urllib.request, "urlopen", lambda req, timeout: r)
    t0 = time.monotonic()
    with pytest.raises(rp.AttemptTimeout, match="abandoned after 0s"):
        rp._post({"model": "m"}, "k", wall_sec=0.1)
    assert time.monotonic() - t0 < 2.0
    assert r.closed and r.reads > 1


class _Whole:
    """A fake with only `read()` — the shape the other tests' fakes have."""

    def __enter__(self) -> _Whole:
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"choices": []}).encode()


def test_post_reads_a_body_that_arrives_in_pieces_and_a_fake_without_read1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Pieces(_Trickle):
        def __init__(self) -> None:
            super().__init__()
            self.parts = [b"\n   \n", b'{"choices"', b": [1]}", b""]

        def read1(self, n: int) -> bytes:
            return self.parts.pop(0)

    monkeypatch.setattr(rp.urllib.request, "urlopen", lambda req, timeout: Pieces())
    assert rp._post({}, "k") == {"choices": [1]}
    monkeypatch.setattr(rp.urllib.request, "urlopen", lambda req, timeout: _Whole())
    assert rp._post({}, "k") == {"choices": []}


# ------------------------------------------------------------- the chain moves on


def _brief() -> dict[str, Any]:
    body = json.dumps({
        "thesis": "NQ holds 30707",
        "calls": [{"book": "NQ", "open_bias": "bullish", "conviction": 3,
                   "rest_of_day": "x", "wrong_if": "y", "why": []}],
        "reads": [{"book": "NQ", "regime": "r"}],
    })
    return {"choices": [{"message": {"content": body}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 1}}


@pytest.fixture
def quick_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(rp, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(rp, "build_facts", lambda *a, **k: {
        "books": ["NQ"], "headlines": [], "snapshot": [], "catalysts": [], "rotation": {},
        "partial": [], "ladders": [], "gamma": [], "as_of": "now"})
    monkeypatch.setattr(rp, "build_digest", lambda *a, **k: {"NQ": {"last": 30707}})


def test_generate_passes_over_a_model_that_crawled_and_takes_the_next(
    quick_report: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def answer(payload: dict[str, Any], key: str) -> dict[str, Any]:
        asked.append(payload["model"])
        if payload["model"] == rp.DEFAULT_MODEL:
            raise rp.AttemptTimeout("abandoned after 240s — the provider was still writing")
        return _brief()

    monkeypatch.setattr(rp, "_post", answer)
    rep = rp.generate({"clock": {}}, asset="NQ")
    assert rep["ok"] is True
    # The crawling model was asked ONCE — not again for its second try, not
    # again in json mode — and the fallback wrote the note.
    assert asked == [rp.DEFAULT_MODEL, rp.FALLBACK_MODELS[0]]
    assert rep["model"] == rp.FALLBACK_MODELS[0]
    assert rep["attempts"][0]["error"].startswith("abandoned after 240s")


# -------------------------------------------------------------------- the runner


def _settle(r: jobs.Runner, job_id: str) -> dict[str, Any] | None:
    for _ in range(300):
        view, result = r.get(job_id)
        if view["state"] != jobs.RUNNING:
            return result
        time.sleep(0.01)
    raise AssertionError("still running")


def test_runner_runs_one_at_a_time_and_keeps_the_answer_for_a_late_poll() -> None:
    gate = threading.Event()
    r = jobs.Runner("note")

    def work() -> dict[str, Any]:
        gate.wait(5)
        return {"ok": True, "id": "a"}

    first = r.start("a", {"model": "m"}, work)
    assert first["state"] == "running" and first["model"] == "m" and "result" not in first
    running = r.running()
    assert running is not None and running["id"] == "a"
    # A second press joins the running job rather than starting another.
    assert r.start("b", {}, work)["id"] == "a"
    view, result = r.get("a")
    assert view["state"] == "running" and result is None
    gate.set()
    assert _settle(r, "a") == {"ok": True, "id": "a"}
    assert r.running() is None
    # The answer is still there for a poll that arrives late...
    assert r.get("a")[1] == {"ok": True, "id": "a"}
    # ...and an id this runner never held is LOST — the collector restarted
    # under it — with a failed note that says so, for the page to show.
    view, lost = r.get("zzz")
    assert view == {"id": "zzz", "state": "lost"}
    assert lost is not None and lost["ok"] is False and "restarted" in lost["error"]


def test_runner_turns_a_crash_into_a_failed_note() -> None:
    r = jobs.Runner("note")

    def work() -> dict[str, Any]:
        raise RuntimeError("boom")

    r.start("c", {"session_label": "Asia"}, work)
    result = _settle(r, "c")
    assert result is not None and result["ok"] is False
    assert "crashed" in result["error"] and "boom" in result["error"]
    assert result["session_label"] == "Asia" and "RuntimeError" in result["raw"]


# -------------------------------------------------------------------- the routes


def test_report_routes_start_a_job_and_hand_the_note_back_by_poll(
    quick_report: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from newsterminal.collector import COLLECTOR

    monkeypatch.setattr(COLLECTOR, "snapshot", lambda: {"clock": {}})
    monkeypatch.setattr(rp, "_post", lambda payload, key, timeout=0: _brief())
    code, body = _asgi("POST", "/api/report", "session=ny&asset=NQ")
    assert code == 200 and body["job"]["state"] in ("running", "done")
    assert body["job"]["session"] == "ny" and body["job"]["asset"] == "NQ"
    jid = body["job"]["id"]
    for _ in range(300):
        code, body = _asgi("GET", f"/api/report/job/{jid}")
        assert code == 200
        if body["job"]["state"] == "done":
            break
        time.sleep(0.01)
    assert body["job"]["state"] == "done"
    assert body["latest"]["ok"] is True and body["latest"]["id"] == jid
    assert body["history"][0]["id"] == jid
    code, feed = _asgi("GET", "/api/report")
    assert code == 200 and feed["job"] is None and feed["latest"]["id"] == jid
    assert _asgi("GET", "/api/report/job/not-an-id")[0] == 422
