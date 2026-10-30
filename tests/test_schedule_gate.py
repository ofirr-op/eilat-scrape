"""The schedule gate skips a backup only when today's scrape is already covered."""

import unittest
from datetime import datetime, timezone

from scrape.schedule_gate import should_skip

NOW = datetime(2026, 10, 30, 8, 43, tzinfo=timezone.utc)  # 10:43 Israel, winter


def _run(run_id, created, *, status="completed", conclusion="success", branch="main", event="schedule"):
    return {
        "databaseId": run_id,
        "createdAt": created,
        "status": status,
        "conclusion": conclusion,
        "headBranch": branch,
        "event": event,
    }


class ScheduleGateTests(unittest.TestCase):
    def test_manual_run_always_proceeds(self):
        runs = [_run(1, "2026-10-30T05:17:00Z")]
        self.assertFalse(should_skip("workflow_dispatch", runs, now=NOW, run_id=9, branch="main"))

    def test_no_earlier_run_today_proceeds(self):
        runs = [_run(1, "2026-10-29T05:17:00Z")]
        self.assertFalse(should_skip("schedule", runs, now=NOW, run_id=9, branch="main"))

    def test_success_today_in_israel_skips(self):
        runs = [_run(1, "2026-10-30T05:17:00Z")]
        self.assertTrue(should_skip("schedule", runs, now=NOW, run_id=9, branch="main"))

    def test_queued_or_in_progress_today_skips(self):
        queued = [_run(1, "2026-10-30T05:17:00Z", status="queued", conclusion=None)]
        running = [_run(2, "2026-10-30T05:20:00Z", status="in_progress", conclusion=None)]
        self.assertTrue(should_skip("schedule", queued, now=NOW, run_id=9, branch="main"))
        self.assertTrue(should_skip("schedule", running, now=NOW, run_id=9, branch="main"))

    def test_failed_or_cancelled_today_does_not_skip(self):
        failed = [_run(1, "2026-10-30T05:17:00Z", conclusion="failure")]
        cancelled = [_run(2, "2026-10-30T05:17:00Z", conclusion="cancelled")]
        self.assertFalse(should_skip("schedule", failed, now=NOW, run_id=9, branch="main"))
        self.assertFalse(should_skip("schedule", cancelled, now=NOW, run_id=9, branch="main"))

    def test_late_utc_evening_that_is_already_today_in_israel_skips(self):
        # 22:30 UTC on the 29th is 00:30 on the 30th in Israel (UTC+2).
        runs = [_run(1, "2026-10-29T22:30:00Z")]
        self.assertTrue(should_skip("schedule", runs, now=NOW, run_id=9, branch="main"))

    def test_previous_israel_evening_does_not_count(self):
        # 20:30 UTC on the 29th is 22:30 on the 29th in Israel.
        runs = [_run(1, "2026-10-29T20:30:00Z")]
        self.assertFalse(should_skip("schedule", runs, now=NOW, run_id=9, branch="main"))

    def test_ignores_this_run_and_other_branches(self):
        runs = [
            _run(9, "2026-10-30T08:43:00Z"),
            _run(3, "2026-10-30T05:17:00Z", branch="some-pr"),
        ]
        self.assertFalse(should_skip("schedule", runs, now=NOW, run_id=9, branch="main"))


if __name__ == "__main__":
    unittest.main()
