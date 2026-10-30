"""One generation at a time, off the request path, polled by id.

WHY A JOB AND NOT A LONG REQUEST. A report or a game plan is written by a
free model and takes one to five minutes. For a year the POST held the
connection open for the whole of that, which meant three timeouts had to
agree — the browser's fetch, the Next proxy's 290s, the collector's own
budget — and whichever gave up first turned a report that was still being
written into "the collector did not answer in time". On 2026-10-27 a brief
took 332s: the collector finished it, stored it, and the page had already
reported a failure (owner: "why is generate analysis not working anymore").

So the POST now starts the work on a thread and answers at once with the
job's id, and the page asks `GET .../job/{id}` every few seconds until the
job is done. No request is ever as long as the generation, a reload in the
middle finds the job still running and picks the clock back up, and a
second press while one is running JOINS it instead of spending a second
model call — one generation at a time, per kind of note, is the whole of
the policy.

The runner holds only the newest job. A finished one stays until the next
starts, so a poll that arrives after the thread has returned still gets its
answer; an id this process does not hold — the collector restarted under a
running generation — comes back LOST, and the page says so rather than
polling for a result that will never arrive.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

RUNNING = "running"
DONE = "done"
LOST = "lost"


class Runner:
    """A single-flight background runner for one kind of note."""

    def __init__(self, noun: str) -> None:
        self._noun = noun
        self._lock = threading.Lock()
        # The newest job, running or finished. `result` is the note the work
        # returned, or the failed envelope a crash became; it is never in the
        # view handed to the page, which reads the note from `latest`.
        self._job: dict[str, Any] | None = None

    def start(
        self, job_id: str, meta: dict[str, Any], work: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        """Run `work` on a thread and return the job's view — or, when one is
        already running, THAT job's view, untouched. `meta` is what the page
        may want to show while it waits (the model, the session, the labels)
        and what a crash envelope carries so the panel can still caption it."""
        with self._lock:
            if self._job is not None and self._job["state"] == RUNNING:
                return self.view(self._job)
            job: dict[str, Any] = {
                "id": job_id,
                "state": RUNNING,
                "started_utc": datetime.now(UTC).isoformat(),
                **meta,
                "result": None,
            }
            self._job = job
            threading.Thread(
                target=self._run, args=(job, work), name=f"{self._noun}-{job_id}", daemon=True
            ).start()
            return self.view(job)

    def _run(self, job: dict[str, Any], work: Callable[[], dict[str, Any]]) -> None:
        try:
            result = work()
        except Exception as e:  # noqa: BLE001 — see below
            # A crash must land as a FAILED NOTE, not as a thread that dies
            # while the page polls a job that will never finish. Before the
            # runner this was a 500 the proxy worded as "collector returned
            # HTTP 500"; the exception itself is more use to whoever reads it.
            result = {
                **{k: v for k, v in job.items() if k not in ("state", "result")},
                "ok": False,
                "created_utc": job["started_utc"],
                "error": f"The {self._noun} generator crashed: {e!r}",
                "raw": traceback.format_exc()[-2000:],
                "attempts": [],
            }
        with self._lock:
            job["result"] = result
            job["state"] = DONE

    def get(self, job_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """(view, result): the result once the job is DONE, the failed
        envelope for an id this runner does not hold (LOST — see the module
        docstring), else None while it runs."""
        with self._lock:
            job = self._job
            if job is None or job["id"] != job_id:
                return {"id": job_id, "state": LOST}, self._lost(job_id)
            return self.view(job), job["result"] if job["state"] == DONE else None

    def _lost(self, job_id: str) -> dict[str, Any]:
        """A failed note for a job this process never held, so the page shows
        it as it shows any failed generation rather than the old note with no
        word on what happened."""
        return {
            "ok": False, "id": job_id, "attempts": [], "raw": None,
            "error": (f"The collector restarted while this {self._noun} was being "
                      "written, so nothing was kept. Press Generate again."),
        }

    def running(self) -> dict[str, Any] | None:
        """The running job's view, for a page that loads mid-generation."""
        with self._lock:
            job = self._job
            return self.view(job) if job is not None and job["state"] == RUNNING else None

    @staticmethod
    def view(job: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in job.items() if k != "result"}
