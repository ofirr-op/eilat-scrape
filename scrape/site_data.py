"""Build the static price page from history snapshots and the current grids.

The page does not scrape. It reads ``output/history/runs/*.csv.gz`` (one file
per finished party × promo run) and, when a grid's ``results.json`` is newer
than those files, that document too. ``output/status.json`` is the workflow's
note about the run in progress or the last failure.

History files already committed for 24–28 Oct 2026 are the seed. They are the
scraper snapshots the old page carried inline, stored in the append-only
format instead of being copied again.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scrape.history import normalize_scraped_at
from scrape.holidays import holidays_between

ISRAEL = ZoneInfo("Asia/Jerusalem")
BOOKING_BASE = "https://m.clubhotels.co.il/BE_Rooms.aspx"

PARTIES = (
    ("2a3c", "שני מבוגרים + 3 ילדים (4, 8, 12)"),
    ("4a1c", "4 מבוגרים + ילד אחד (גיל 8)"),
)
BOARDS = (
    ("RO", "לינה בלבד"),
    ("BB", "ארוחת בוקר"),
    ("HB", "חצי פנסיון"),
)
GRID_ORDER = ("2a3c", "2a3c-mhot", "4a1c", "4a1c-mhot")
GRID_LABELS = {
    "2a3c": "2 מבוגרים + 3 ילדים · בלי קוד",
    "2a3c-mhot": "2 מבוגרים + 3 ילדים · עם קוד mhot",
    "4a1c": "4 מבוגרים + ילד · בלי קוד",
    "4a1c-mhot": "4 מבוגרים + ילד · עם קוד mhot",
}
MONTHS_HE = (
    "ינואר",
    "פברואר",
    "מרץ",
    "אפריל",
    "מאי",
    "יוני",
    "יולי",
    "אוגוסט",
    "ספטמבר",
    "אוקטובר",
    "נובמבר",
    "דצמבר",
)
MONTHS_SHORT = (
    "ינו׳",
    "פבר׳",
    "מרץ",
    "אפר׳",
    "מאי",
    "יוני",
    "יולי",
    "אוג׳",
    "ספט׳",
    "אוק׳",
    "נוב׳",
    "דצמ׳",
)

# results.json lives next to the grid the scraper already writes.
RESULT_PATHS = {
    "2a3c": ("output/eilat/results.json", "2a3c", "none"),
    "2a3c-mhot": ("output/eilat/promo-mhot/results.json", "2a3c", "mhot"),
    "4a1c": ("output/eilat/party-4a1c/results.json", "4a1c", "none"),
    "4a1c-mhot": ("output/eilat/party-4a1c/promo-mhot/results.json", "4a1c", "mhot"),
}


@dataclass
class Snapshot:
    """One finished scrape of one grid."""

    at: str
    party: str
    promo: str
    # (nights, board, rooms, check_in) -> (price or None when unavailable, room)
    cells: dict[tuple[int, str, int, str], tuple[float | None, str]] = field(default_factory=dict)

    @property
    def grid(self) -> str:
        return grid_id(self.party, self.promo)


def grid_id(party: str, promo: str) -> str:
    if party == "2a3c" and promo == "none":
        return "2a3c"
    if party == "2a3c" and promo == "mhot":
        return "2a3c-mhot"
    if party == "4a1c" and promo == "none":
        return "4a1c"
    if party == "4a1c" and promo == "mhot":
        return "4a1c-mhot"
    raise ValueError(f"unknown grid {party}/{promo}")


def parse_grid_id(value: str) -> tuple[str, str]:
    if value == "2a3c":
        return "2a3c", "none"
    if value == "2a3c-mhot":
        return "2a3c", "mhot"
    if value == "4a1c":
        return "4a1c", "none"
    if value == "4a1c-mhot":
        return "4a1c", "mhot"
    raise ValueError(f"unknown grid id {value}")


def israel_label(stamp: str) -> str:
    """``dd/mm HH:MM`` in Israel local time, matching the old page."""
    text = normalize_scraped_at(stamp)
    parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    local = parsed.astimezone(ISRAEL)
    return local.strftime("%d/%m %H:%M")


def israel_clock(stamp: str) -> str:
    text = normalize_scraped_at(stamp)
    parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    return parsed.astimezone(ISRAEL).strftime("%H:%M")


def israel_date(stamp: str) -> str:
    text = normalize_scraped_at(stamp)
    parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    return parsed.astimezone(ISRAEL).strftime("%d/%m/%Y")


def booking_url(check_in: str, nights: int, rooms: int, party: str, *, use_mhot: bool) -> str:
    """Link for the cheaper of the two prices. ``use_mhot`` adds ``promocode=mhot``."""
    check_out = _add_days(check_in, nights)
    query = (
        f"?lang=heb&hotel=1_1&in={check_in}&out={check_out}&rooms={rooms}"
    )
    if party == "4a1c":
        party_q = "&ad1=4&ch1=1&inf1=0" if rooms == 1 else "&ad1=1&ch1=1&inf1=0&ad2=3&ch2=0&inf2=0"
    else:
        party_q = "&ad1=2&ch1=3&inf1=0" if rooms == 1 else "&ad1=1&ch1=2&inf1=0&ad2=1&ch2=1&inf2=0"
    promo = "&promocode=mhot" if use_mhot else ""
    return BOOKING_BASE + query + party_q + promo


def cheaper(none: float | None, mhot: float | None) -> tuple[bool, float] | None:
    """Return ``(use_mhot, total)``. A tie stays on the regular price."""
    if none is None and mhot is None:
        return None
    use_mhot = mhot is not None and (none is None or mhot < none)
    total = mhot if use_mhot else none
    if total is None:
        return None
    return use_mhot, total


def load_history(history_dir: Path) -> list[Snapshot]:
    runs = history_dir / "runs"
    if not runs.is_dir():
        return []
    snapshots: list[Snapshot] = []
    for path in sorted(runs.glob("*.csv.gz")):
        snapshots.append(_snapshot_from_csv(path))
    snapshots.sort(key=lambda snap: (snap.at, snap.grid))
    return snapshots


def load_current_results(repo: Path) -> list[Snapshot]:
    """A grid's results.json, when its ``generated_at`` is not already in history."""
    found: list[Snapshot] = []
    for _grid, (relative, party, promo) in RESULT_PATHS.items():
        path = repo / relative
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        stamp = document.get("generated_at")
        if not stamp:
            continue
        found.append(_snapshot_from_rows(
            normalize_scraped_at(str(stamp)),
            str(document.get("party") or party),
            str(document.get("promo") or promo),
            document.get("results") or [],
        ))
    return found


def merge_snapshots(history: list[Snapshot], current: list[Snapshot]) -> list[Snapshot]:
    """History wins when a results file repeats the same ``generated_at``."""
    seen = {(snap.at, snap.grid) for snap in history}
    extra = [snap for snap in current if (snap.at, snap.grid) not in seen]
    return sorted([*history, *extra], key=lambda snap: (snap.at, snap.grid))


def build_document(repo: Path, *, status_path: Path | None = None) -> dict:
    history = load_history(repo / "output" / "history")
    current = load_current_results(repo)
    snapshots = merge_snapshots(history, current)
    by_grid: dict[str, list[Snapshot]] = {grid: [] for grid in GRID_ORDER}
    for snap in snapshots:
        by_grid.setdefault(snap.grid, []).append(snap)

    latest: dict[str, Snapshot | None] = {
        grid: (rows[-1] if rows else None) for grid, rows in by_grid.items()
    }
    offers: dict[str, list[dict]] = {}
    history_out: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for party, _label in PARTIES:
        for nights in (2, 3, 4):
            for board, _board_label in BOARDS:
                for rooms in (1, 2):
                    key = f"{party}|{nights}|{board}|{rooms}"
                    offers[key] = _offers_for(party, nights, board, rooms, latest)
                    series = _series_for(party, nights, board, rooms, by_grid)
                    if series:
                        history_out[key] = series

    dates = [
        row["date"]
        for rows in offers.values()
        for row in rows
    ]
    if not dates:
        for snap in latest.values():
            if snap is None:
                continue
            dates.extend(check_in for (_n, _b, _r, check_in) in snap.cells)
    first = min(dates) if dates else None
    last = max(dates) if dates else None
    status = _status_block(repo, status_path, by_grid)
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"first": first, "last": last},
        "months": _months(first, last),
        "parties": [{"id": party, "label": label} for party, label in PARTIES],
        "boards": [{"id": code, "label": label} for code, label in BOARDS],
        "splits": {
            "2a3c": "חדר 1: מבוגר + 2 ילדים, חדר 2: מבוגר + ילד",
            "4a1c": "חדר 1: מבוגר + ילד, חדר 2: 3 מבוגרים",
        },
        "status": status,
        "scans": {
            grid: [{"at": snap.at, "label": israel_label(snap.at)} for snap in by_grid.get(grid, [])]
            for grid in GRID_ORDER
        },
        "offers": offers,
        "history": history_out,
        "holidays": _holidays_for_window(first, last),
    }


def write_document(repo: Path, dest: Path, *, status_path: Path | None = None) -> dict:
    document = build_document(repo, status_path=status_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return document


def mark_running(status_path: Path, *, started_at: str, grids: list[str], note: str = "") -> dict:
    """Record that this workflow run has started the given grids."""
    started = normalize_scraped_at(started_at)
    previous = _read_status(status_path)
    previous_grids = previous.get("grids") if isinstance(previous.get("grids"), dict) else {}
    out_grids: dict[str, dict] = {}
    for grid in GRID_ORDER:
        prior = previous_grids.get(grid) if isinstance(previous_grids.get(grid), dict) else {}
        if grid in grids:
            out_grids[grid] = {
                "state": "running",
                "started_at": started,
                "finished_at": None,
                "error": None,
                "last_scan_at": prior.get("last_scan_at"),
            }
        else:
            out_grids[grid] = {
                "state": prior.get("state") or "done",
                "started_at": prior.get("started_at"),
                "finished_at": prior.get("finished_at"),
                "error": prior.get("error"),
                "last_scan_at": prior.get("last_scan_at"),
            }
    document = {
        "run_state": "running",
        "started_at": started,
        "finished_at": None,
        "error": None,
        "note": note,
        "grids": out_grids,
    }
    _write_status(status_path, document)
    return document


def mark_finished(
    status_path: Path,
    *,
    finished_at: str,
    grids: list[str],
    failed: dict[str, str],
    started_at: str | None = None,
) -> dict:
    """Close the run. ``failed`` maps a grid id to the reason it produced no file."""
    finished = normalize_scraped_at(finished_at)
    previous = _read_status(status_path)
    previous_grids = previous.get("grids") if isinstance(previous.get("grids"), dict) else {}
    started = started_at or previous.get("started_at") or finished
    started = normalize_scraped_at(str(started))
    out_grids: dict[str, dict] = {}
    reasons: list[str] = []
    for grid in GRID_ORDER:
        prior = previous_grids.get(grid) if isinstance(previous_grids.get(grid), dict) else {}
        if grid not in grids:
            out_grids[grid] = {
                "state": prior.get("state") or "done",
                "started_at": prior.get("started_at"),
                "finished_at": prior.get("finished_at"),
                "error": prior.get("error"),
                "last_scan_at": prior.get("last_scan_at"),
            }
            continue
        if grid in failed:
            reason = (failed[grid].strip() or "הסריקה נכשלה לפני שכתבה תוצאות")[:500]
            reasons.append(f"{GRID_LABELS[grid]}: {reason}")
            out_grids[grid] = {
                "state": "failed",
                "started_at": prior.get("started_at") or started,
                "finished_at": finished,
                "error": reason,
                "last_scan_at": prior.get("last_scan_at"),
            }
        else:
            out_grids[grid] = {
                "state": "done",
                "started_at": prior.get("started_at") or started,
                "finished_at": finished,
                "error": None,
                "last_scan_at": finished,
            }
    document = {
        "run_state": "failed" if reasons else "idle",
        "started_at": started,
        "finished_at": finished,
        "error": "\n".join(reasons) if reasons else None,
        "note": previous.get("note") or "",
        "grids": out_grids,
    }
    _write_status(status_path, document)
    return document


def _offers_for(
    party: str,
    nights: int,
    board: str,
    rooms: int,
    latest: dict[str, Snapshot | None],
) -> list[dict]:
    none_snap = latest.get(grid_id(party, "none"))
    mhot_snap = latest.get(grid_id(party, "mhot"))
    dates: set[str] = set()
    if none_snap:
        dates.update(check_in for (n, b, r, check_in) in none_snap.cells if n == nights and b == board and r == rooms)
    if mhot_snap:
        dates.update(check_in for (n, b, r, check_in) in mhot_snap.cells if n == nights and b == board and r == rooms)
    rows: list[dict] = []
    for check_in in sorted(dates):
        none_cell = _cell(none_snap, nights, board, rooms, check_in)
        mhot_cell = _cell(mhot_snap, nights, board, rooms, check_in)
        # A date missing from the latest snapshot is outside this run, not a current offer.
        if none_cell is None and mhot_cell is None:
            continue
        none_price = none_cell[0] if none_cell else None
        mhot_price = mhot_cell[0] if mhot_cell else None
        chosen = cheaper(none_price, mhot_price)
        if chosen is None:
            continue
        use_mhot, total = chosen
        room_none = none_cell[1] if none_cell and none_price is not None else ""
        room_mhot = mhot_cell[1] if mhot_cell and mhot_price is not None else ""
        rows.append({
            "date": check_in,
            "none": none_price,
            "mhot": mhot_price,
            "room_none": room_none,
            "room_mhot": room_mhot,
            "use_mhot": use_mhot,
            "total": total,
            "per_night": round(total / nights, 2),
            "url": booking_url(check_in, nights, rooms, party, use_mhot=use_mhot),
        })
    return rows


def _series_for(
    party: str,
    nights: int,
    board: str,
    rooms: int,
    by_grid: dict[str, list[Snapshot]],
) -> dict[str, dict[str, list[dict]]]:
    """Check-in → promo → points. ``price`` is null when that scrape found nothing.

    A snapshot that does not mention the date is omitted (the date was outside
    that run). Unavailable stays as a point so the chart can show the gap.
    """
    out: dict[str, dict[str, list[dict]]] = {}
    for promo, name in (("none", "none"), ("mhot", "mhot")):
        snaps = by_grid.get(grid_id(party, promo), [])
        dates = {
            check_in
            for snap in snaps
            for (n, b, r, check_in) in snap.cells
            if n == nights and b == board and r == rooms
        }
        for check_in in sorted(dates):
            points: list[dict] = []
            for snap in snaps:
                cell = snap.cells.get((nights, board, rooms, check_in))
                if cell is None:
                    continue
                price, _room = cell
                points.append({
                    "at": snap.at,
                    "label": israel_label(snap.at),
                    "price": price,
                })
            if points:
                out.setdefault(check_in, {})[name] = points
    return out


def _cell(
    snap: Snapshot | None,
    nights: int,
    board: str,
    rooms: int,
    check_in: str,
) -> tuple[float | None, str] | None:
    if snap is None:
        return None
    return snap.cells.get((nights, board, rooms, check_in))


def _holidays_for_window(first: str | None, last: str | None) -> dict:
    """Israeli Jewish holidays for every day of the months on the calendar."""
    if not first or not last:
        return {}
    start = date(int(first[:4]), int(first[5:7]), 1)
    year, month = int(last[:4]), int(last[5:7])
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return holidays_between(start, end)


def _months(first: str | None, last: str | None) -> list[dict]:
    if not first or not last:
        return []
    year, month = int(first[:4]), int(first[5:7])
    end_y, end_m = int(last[:4]), int(last[5:7])
    months: list[dict] = []
    while (year, month) <= (end_y, end_m):
        key = f"{year:04d}-{month:02d}"
        months.append({
            "key": key,
            "name": f"{MONTHS_HE[month - 1]} {year}",
            "short": f"{MONTHS_SHORT[month - 1]} {str(year)[2:]}",
        })
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


def _status_block(repo: Path, status_path: Path | None, by_grid: dict[str, list[Snapshot]]) -> dict:
    path = status_path or (repo / "output" / "status.json")
    raw = _read_status(path)
    raw_grids = raw.get("grids") if isinstance(raw.get("grids"), dict) else {}
    grids: dict[str, dict] = {}
    for grid in GRID_ORDER:
        snaps = by_grid.get(grid) or []
        last = snaps[-1] if snaps else None
        prior = raw_grids.get(grid) if isinstance(raw_grids.get(grid), dict) else {}
        last_at = last.at if last else prior.get("last_scan_at")
        grids[grid] = {
            "label": GRID_LABELS[grid],
            "state": prior.get("state") or ("done" if last else "idle"),
            "started_at": prior.get("started_at"),
            "finished_at": prior.get("finished_at"),
            "error": prior.get("error"),
            "last_scan_at": last_at,
            "last_scan_label": israel_label(last_at) if last_at else None,
            "last_scan_date": israel_date(last_at) if last_at else None,
        }
        if grids[grid]["state"] == "running" and not raw:
            grids[grid]["state"] = "done"
    run_state = raw.get("run_state") or "idle"
    started = raw.get("started_at")
    return {
        "run_state": run_state,
        "started_at": started,
        "started_label": israel_label(started) if started else None,
        "started_clock": israel_clock(started) if started else None,
        "finished_at": raw.get("finished_at"),
        "error": raw.get("error"),
        "note": raw.get("note") or "",
        "grids": grids,
    }


def _snapshot_from_csv(path: Path) -> Snapshot:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty history file: {path}")
    first = rows[0]
    party = first.get("party") or "2a3c"
    promo = first.get("promo") or "none"
    stamp = first.get("scraped_at") or ""
    return _snapshot_from_rows(normalize_scraped_at(stamp), party, promo, rows)


def _snapshot_from_rows(stamp: str, party: str, promo: str, rows: list[dict]) -> Snapshot:
    snap = Snapshot(at=normalize_scraped_at(stamp), party=party, promo=promo)
    for row in rows:
        check_in = str(row.get("check_in") or "")
        if not check_in:
            continue
        try:
            nights = int(row.get("nights") or 0)
            rooms = int(row.get("rooms") or 0)
        except (TypeError, ValueError):
            continue
        board = str(row.get("board") or "")
        status = str(row.get("status") or "")
        price = _price(row.get("total_price"), status)
        room = str(row.get("room_type") or "") if price is not None else ""
        snap.cells[(nights, board, rooms, check_in)] = (price, room)
    return snap


def _price(value, status: str) -> float | None:
    if status and status != "available":
        return None
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _read_status(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_status(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _add_days(date: str, days: int) -> str:
    year, month, day = (int(part) for part in date.split("-"))
    base = datetime(year, month, day, tzinfo=timezone.utc)
    from datetime import timedelta
    shifted = base + timedelta(days=days)
    return shifted.strftime("%Y-%m-%d")


def _grids_from_args(values: list[str]) -> list[str]:
    grids: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            parse_grid_id(part)
            if part not in grids:
                grids.append(part)
    return grids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Eilat price page data and scan status.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Write site/data.json from history, current results, and status.")
    build.add_argument("--root", type=Path, default=Path("."))
    build.add_argument("--dest", type=Path, default=Path("site/data.json"))
    build.add_argument("--status", type=Path, default=None)

    running = sub.add_parser("mark-running", help="Write output/status.json for a run that just started.")
    running.add_argument("--status", type=Path, required=True)
    running.add_argument("--started-at", required=True)
    running.add_argument("--grids", required=True, help="Comma-separated grid ids.")
    running.add_argument("--note", default="")

    finished = sub.add_parser("mark-finished", help="Write output/status.json after the grids have been merged.")
    finished.add_argument("--status", type=Path, required=True)
    finished.add_argument("--finished-at", required=True)
    finished.add_argument("--started-at", default=None)
    finished.add_argument("--grids", required=True)
    finished.add_argument(
        "--failed",
        action="append",
        default=[],
        help="grid=reason. Repeat for each grid that did not produce results. Use grid=@file to read the reason.",
    )

    args = parser.parse_args(argv)
    if args.command == "build":
        write_document(args.root, args.dest, status_path=args.status)
        return 0
    if args.command == "mark-running":
        mark_running(
            args.status,
            started_at=args.started_at,
            grids=_grids_from_args([args.grids]),
            note=args.note,
        )
        return 0
    failed: dict[str, str] = {}
    for item in args.failed:
        grid, _, reason = item.partition("=")
        grid = grid.strip()
        parse_grid_id(grid)
        reason = reason.strip()
        if reason.startswith("@"):
            reason = Path(reason[1:]).read_text(encoding="utf-8").strip()
        failed[grid] = reason
    mark_finished(
        args.status,
        finished_at=args.finished_at,
        grids=_grids_from_args([args.grids]),
        failed=failed,
        started_at=args.started_at,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
