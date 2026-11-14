"""One Telegram message when a holiday price fell since the previous scan.

A line is one grid: party ``2a3c`` or ``4a1c``, promo ``none`` (regular) or
``mhot``. The price of a line on a check-in date is the cheapest available
total on that scan, across nights, board, and room count. The whole-shekel
price (the same rounding the page uses) is compared with the previous
snapshot of that same line. Every date the calendar marks is eligible:
``chag``, ``chol``, ``erev``, ``minor``, and the modern days already painted
on the calendar.

Missing Telegram secrets, an empty drop list, and Telegram errors are logged
and do not fail the caller. A run that published no grids sends nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scrape.holidays import holidays_between
from scrape.site_data import (
    booking_url,
    load_current_results,
    load_history,
    merge_snapshots,
    parse_grid_id,
)

SITE_URL = "https://ofirr-op.github.io/eilat-scrape/"
TELEGRAM_LIMIT = 4096

PARTY_LABELS = {
    "2a3c": "2 מבוגרים + 3 ילדים",
    "4a1c": "4 מבוגרים + ילד",
}
PROMO_LABELS = {
    "none": "בלי קוד",
    "mhot": "עם קוד mhot",
}


class TelegramError(RuntimeError):
    """The Bot API rejected the message, or the request did not complete."""


@dataclass(frozen=True)
class Quote:
    total: float
    nights: int
    rooms: int
    board: str


@dataclass(frozen=True)
class Drop:
    check_in: str
    holiday_name: str
    holiday_kind: str
    party: str
    promo: str
    old: float
    new: float
    nights: int
    rooms: int


def shekels(value: float) -> int:
    """Nearest shekel, half away from zero, matching ``Math.round`` on the page."""
    return int(math.floor(float(value) + 0.5))


def money(amount: int) -> str:
    return f"{amount:,}"


def find_drops(repo: Path, grids: list[str]) -> list[Drop]:
    """Holiday lines whose displayed shekel price is lower than the previous scan."""
    wanted: list[str] = []
    for grid in grids:
        parse_grid_id(grid)
        if grid not in wanted:
            wanted.append(grid)
    if not wanted:
        return []

    snapshots = merge_snapshots(
        load_history(repo / "output" / "history"),
        load_current_results(repo),
    )
    by_grid: dict[str, list] = {}
    for snap in snapshots:
        by_grid.setdefault(snap.grid, []).append(snap)

    pairs = []
    latest_dates: list[str] = []
    for grid in wanted:
        snaps = by_grid.get(grid) or []
        if len(snaps) < 2:
            continue
        previous, latest = snaps[-2], snaps[-1]
        pairs.append((previous, latest))
        latest_dates.extend(check_in for (_n, _b, _r, check_in) in latest.cells)
    if not pairs or not latest_dates:
        return []

    holidays = holidays_between(
        date.fromisoformat(min(latest_dates)),
        date.fromisoformat(max(latest_dates)),
    )
    drops: list[Drop] = []
    for previous, latest in pairs:
        scanned = {check_in for (_n, _b, _r, check_in) in latest.cells}
        for check_in in sorted(scanned):
            holiday = holidays.get(check_in)
            if not holiday or not holiday.get("name"):
                continue
            old = _cheapest(previous, check_in)
            new = _cheapest(latest, check_in)
            if old is None or new is None:
                continue
            if shekels(new.total) >= shekels(old.total):
                continue
            drops.append(Drop(
                check_in=check_in,
                holiday_name=str(holiday["name"]),
                holiday_kind=str(holiday.get("kind") or ""),
                party=latest.party,
                promo=latest.promo,
                old=old.total,
                new=new.total,
                nights=new.nights,
                rooms=new.rooms,
            ))
    drops.sort(key=lambda item: (item.check_in, item.party, item.promo != "none"))
    return drops


def format_message(drops: list[Drop]) -> str:
    """One Hebrew summary. The booking link is the cheapest new price."""
    if not drops:
        return ""
    ordered = sorted(drops, key=lambda item: (item.check_in, item.party, item.promo != "none"))

    def render(shown: list[Drop], omitted: int) -> str:
        parts = ["ירידות מחיר בחגים — מועדון הוטלס אילת", ""]
        parts.extend("• " + _format_drop(item) for item in shown)
        if omitted:
            parts.append(f"… ועוד {omitted} ירידות שלא נכנסו להודעה.")
        parts.extend(["", _booking_block(_cheapest_drop(ordered)), "", f"כל המחירים: {SITE_URL}"])
        return "\n".join(parts)

    shown = ordered
    omitted = 0
    text = render(shown, omitted)
    while len(text) > TELEGRAM_LIMIT and shown:
        shown = shown[:-1]
        omitted += 1
        text = render(shown, omitted)
    if len(text) > TELEGRAM_LIMIT:
        text = text[:TELEGRAM_LIMIT]
    return text


def send_message(token: str, chat_id: str, text: str, *, opener=None) -> None:
    """POST ``sendMessage``. Raises ``TelegramError`` without echoing the token."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=20) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raise TelegramError(f"HTTP {exc.code}") from None
    except TelegramError:
        raise
    except Exception as exc:
        raise TelegramError(_safe(exc, token)) from None
    if status >= 400:
        raise TelegramError(f"HTTP {status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise TelegramError("Telegram returned a response that was not JSON") from None
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = str(payload.get("description") or "") if isinstance(payload, dict) else ""
        raise TelegramError(description or "Telegram rejected the message")


def notify(
    repo: Path,
    grids: list[str],
    *,
    token: str | None = None,
    chat_id: str | None = None,
    send=send_message,
) -> int:
    """Send at most one message. Always returns 0 for a skip or a Telegram failure."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN", "") if token is None else token).strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID", "") if chat_id is None else chat_id).strip()
    if not token or not chat_id:
        print(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set; "
            "skipping the holiday price-drop alert."
        )
        return 0
    if not grids:
        print("No grids were published in this run; skipping the holiday price-drop alert.")
        return 0
    drops = find_drops(repo, grids)
    if not drops:
        print("No holiday price drops; not sending a Telegram message.")
        return 0
    text = format_message(drops)
    try:
        send(token, chat_id, text)
    except Exception as exc:
        print(f"Telegram send failed: {_safe(exc, token)}", file=sys.stderr)
        return 0
    print(f"Sent a Telegram alert for {len(drops)} holiday price drop(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alert Telegram when a holiday price dropped.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--grids", default="", help="Comma-separated grid ids published by this run.")
    args = parser.parse_args(argv)
    try:
        return notify(args.root, _split_grids(args.grids))
    except Exception as exc:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        print(f"Telegram holiday alert failed: {_safe(exc, token)}", file=sys.stderr)
        return 0


def _cheapest(snap, check_in: str) -> Quote | None:
    best: Quote | None = None
    for (nights, board, rooms, when), (price, _room) in snap.cells.items():
        if when != check_in or price is None:
            continue
        quote = Quote(total=price, nights=nights, rooms=rooms, board=board)
        rank = (quote.total, quote.nights, quote.rooms, quote.board)
        if best is None or rank < (best.total, best.nights, best.rooms, best.board):
            best = quote
    return best


def _cheapest_drop(drops: list[Drop]) -> Drop:
    """Lowest new price. A tie stays on the regular line, then the earlier date."""
    return min(drops, key=lambda item: (shekels(item.new), item.promo != "none", item.check_in))


def _format_drop(item: Drop) -> str:
    old = shekels(item.old)
    new = shekels(item.new)
    delta = old - new
    pct = delta / old * 100
    return (
        f"{_hebrew_date(item.check_in)}, {item.holiday_name}, "
        f"{PARTY_LABELS[item.party]}, {PROMO_LABELS[item.promo]}: "
        f"{money(old)} ₪ → {money(new)} ₪ (ירידה של {money(delta)} ₪, {pct:.1f}%)"
    )


def _booking_block(item: Drop) -> str:
    label = "עם mhot" if item.promo == "mhot" else "מחיר רגיל"
    url = booking_url(
        item.check_in,
        item.nights,
        item.rooms,
        item.party,
        use_mhot=item.promo == "mhot",
    )
    return f"להזמנה באתר מועדון הוטלס – {money(shekels(item.new))} ₪ ({label})\n{url}"


def _hebrew_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def _split_grids(value: str) -> list[str]:
    grids: list[str] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        parse_grid_id(part)
        if part not in grids:
            grids.append(part)
    return grids


def _safe(exc: BaseException, token: str) -> str:
    text = str(exc)
    if token:
        text = text.replace(token, "***")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
