"""Decide whether a scheduled scrape should stand down.

GitHub often drops a cron that fires at minute 0, so the workflow has a
primary schedule and two later backups. A backup must not start a second
scrape when one already succeeded, or is still queued or running, on the
same Israel calendar day. A manual ``workflow_dispatch`` always runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ISRAEL = ZoneInfo("Asia/Jerusalem")

# Statuses that mean this workflow run has not finished yet.
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested", "action_required"}


def should_skip(
    event: str,
    runs: list[dict],
    *,
    now: datetime,
    run_id: int | str,
    branch: str,
) -> bool:
    """True when this scheduled run should not scrape.

    ``runs`` is the JSON from ``gh run list``. The current run is ignored.
    Only runs on ``branch`` count, and only if their start falls on today's
    date in Asia/Jerusalem.
    """
    if event != "schedule":
        return False
    today = now.astimezone(ISRAEL).date()
    me = str(run_id)
    for run in runs:
        if str(run.get("databaseId")) == me:
            continue
        if run.get("headBranch") != branch:
            continue
        created = _parse_created(run.get("createdAt"))
        if created is None or created.astimezone(ISRAEL).date() != today:
            continue
        status = run.get("status") or ""
        conclusion = run.get("conclusion") or ""
        if status in ACTIVE or conclusion == "success":
            return True
    return False


def _parse_created(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print true/false: skip this scheduled scrape.")
    parser.add_argument("--event", default="schedule")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--runs-file", type=Path, required=True)
    parser.add_argument("--now", default=None, help="Override the clock, ISO-8601, for tests.")
    args = parser.parse_args(argv)
    runs = json.loads(args.runs_file.read_text(encoding="utf-8"))
    if not isinstance(runs, list):
        print("runs file must be a JSON list", file=sys.stderr)
        return 2
    now = _parse_created(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        print("could not parse --now", file=sys.stderr)
        return 2
    skip = should_skip(args.event, runs, now=now, run_id=args.run_id, branch=args.branch)
    print("true" if skip else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
