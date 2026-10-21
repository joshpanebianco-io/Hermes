"""Several stored notes go in one request, or every one of them — the
collection DELETE on /api/report and /api/plan (api.py report_delete_many,
plan_delete_many) and the storage calls under them (report.remove_many,
report.remove_all, and stockplan's pair)."""

from __future__ import annotations

from typing import Any

from newsterminal import report as rp
from newsterminal import stockplan as sp

from .test_api_origin import _call
from .test_stockplan import _asgi


def _reports(tmp_path: Any, monkeypatch: Any, n: int = 3) -> list[str]:
    """`n` stored briefs, oldest first, in a scratch directory."""
    monkeypatch.setattr(rp, "REPORTS_DIR", str(tmp_path))
    ids = [f"20261001-09{i:04d}" for i in range(n)]
    for i, rid in enumerate(ids):
        rp._store({
            "id": rid, "et_label": f"t{i}", "model": "m", "format": "brief", "ok": True,
            "report": {"thesis": f"note {i}", "calls": [{"open_bias": "long", "conviction": 3}]},
        })
    return ids


def _plans(tmp_path: Any, monkeypatch: Any, n: int = 3) -> list[str]:
    monkeypatch.setattr(sp, "PLANS_DIR", str(tmp_path))
    ids = [f"20261001-09{i:04d}" for i in range(n)]
    for i, pid in enumerate(ids):
        sp._store({"id": pid, "et_label": f"t{i}", "model": "m",
                   "plan": {"headline": f"plan {i}", "plans": []}})
    return ids


# ------------------------------------------------------------------------- storage


def test_remove_many_takes_only_what_was_asked(tmp_path: Any, monkeypatch: Any) -> None:
    ids = _reports(tmp_path, monkeypatch)
    # A traversal and an id that was never stored both simply do not go.
    gone = rp.remove_many([ids[0], "../outside", ids[2], "20990101-000000"])
    assert gone == [ids[0], ids[2]]
    assert [h["id"] for h in rp.history()] == [ids[1]]


def test_remove_all_empties_the_directory_not_the_list(tmp_path: Any, monkeypatch: Any) -> None:
    ids = _reports(tmp_path, monkeypatch, n=25)
    assert len(rp.history()) == 20  # the list shows twenty; the directory holds twenty-five
    gone = rp.remove_all()
    assert sorted(gone) == sorted(ids)
    assert rp.history() == [] and rp.latest() is None
    # A second pass has nothing to say, and a missing directory is not an error.
    assert rp.remove_all() == []


def test_plans_have_the_same_pair(tmp_path: Any, monkeypatch: Any) -> None:
    ids = _plans(tmp_path, monkeypatch, n=4)
    assert sp.remove_many([ids[1], "nope"]) == [ids[1]]
    assert [h["id"] for h in sp.history()] == [ids[3], ids[2], ids[0]]
    assert sorted(sp.remove_all()) == sorted([ids[0], ids[2], ids[3]])
    assert sp.history() == []


# -------------------------------------------------------------------------- routes


def test_the_report_collection_delete_takes_ids_or_all(tmp_path: Any, monkeypatch: Any) -> None:
    ids = _reports(tmp_path, monkeypatch, n=4)
    # Two by id; a shape that is not an id is dropped before storage sees it.
    code, body = _asgi("DELETE", "/api/report", f"ids={ids[0]}&ids={ids[3]}&ids=..%2Fx")
    assert code == 200
    assert body["deleted"] == [ids[0], ids[3]]
    assert [h["id"] for h in body["history"]] == [ids[2], ids[1]]
    # The newest went, so `latest` moved — the server decides that, not the panel.
    assert body["latest"]["id"] == ids[2]
    # Nothing asked for: nothing goes, and the list comes back as it is.
    code, body = _asgi("DELETE", "/api/report")
    assert code == 200 and body["deleted"] == [] and len(body["history"]) == 2
    # Everything.
    code, body = _asgi("DELETE", "/api/report", "all=1")
    assert code == 200
    assert sorted(body["deleted"]) == sorted([ids[1], ids[2]])
    assert body["history"] == [] and body["latest"] is None


def test_the_plan_collection_delete_matches(tmp_path: Any, monkeypatch: Any) -> None:
    ids = _plans(tmp_path, monkeypatch, n=3)
    code, body = _asgi("DELETE", "/api/plan", f"ids={ids[2]}")
    assert code == 200 and body["deleted"] == [ids[2]] and body["latest"]["id"] == ids[1]
    code, body = _asgi("DELETE", "/api/plan", "all=1")
    assert code == 200 and sorted(body["deleted"]) == [ids[0], ids[1]] and body["history"] == []


def test_a_foreign_page_cannot_delete_everything() -> None:
    assert _call("DELETE", "/api/report", "https://evil.example")[0] == 403
    assert _call("DELETE", "/api/plan", "https://evil.example")[0] == 403
