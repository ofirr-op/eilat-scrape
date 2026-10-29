"""Print the stored price series for one stay.

    python3 -m scrape.history_query --check-in YYYY-MM-DD --nights N --board RO|BB|HB --rooms 1|2
    python3 -m scrape.history_query --check-in YYYY-MM-DD --nights N --board RO --rooms 1 --party 4a1c --promo mhot

``--party`` defaults to ``2a3c`` and ``--promo`` defaults to ``none``, which is
also how a snapshot that predates those columns is read.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from scrape.history import iter_rows
from scrape.party import DEFAULT_PARTY, DEFAULT_PROMO, PARTY_PRESETS, PROMOS

BOARDS = ("RO", "BB", "HB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scrape.history_query",
        description="Show how one stay's price changed across scrapes, and when it was cheapest to book.",
    )
    parser.add_argument("--history", default="output/history", help="History directory (default: output/history).")
    parser.add_argument("--check-in", required=True, help="Stay check-in date, YYYY-MM-DD.")
    parser.add_argument("--nights", required=True, type=int, help="Stay length in nights.")
    parser.add_argument("--board", required=True, choices=BOARDS, help="RO, BB, or HB.")
    parser.add_argument("--rooms", required=True, type=int, choices=(1, 2), help="1 or 2.")
    parser.add_argument(
        "--party",
        default=DEFAULT_PARTY,
        choices=tuple(PARTY_PRESETS),
        help="Party composition (default: 2a3c). Snapshots with no party column count as 2a3c.",
    )
    parser.add_argument(
        "--promo",
        default=DEFAULT_PROMO,
        choices=PROMOS,
        help="none or mhot (default: none). Snapshots with no promo column count as none.",
    )
    args = parser.parse_args(argv)
    try:
        check_in = date.fromisoformat(args.check_in).isoformat()
    except ValueError:
        print("error: --check-in must be YYYY-MM-DD", file=sys.stderr)
        return 2
    if args.nights < 1:
        print("error: --nights must be at least 1", file=sys.stderr)
        return 2

    rows = stay_rows(
        Path(args.history),
        check_in=check_in,
        nights=args.nights,
        board=args.board,
        rooms=args.rooms,
        party=args.party,
        promo=args.promo,
    )
    print(
        format_report(
            check_in,
            args.nights,
            args.board,
            args.rooms,
            rows,
            party=args.party,
            promo=args.promo,
        ),
        end="",
    )
    return 0 if rows else 1


def stay_rows(
    history_dir: Path,
    *,
    check_in: str,
    nights: int,
    board: str,
    rooms: int,
    party: str = DEFAULT_PARTY,
    promo: str = DEFAULT_PROMO,
) -> list[dict[str, str]]:
    """Observations for one cell, oldest scrape first.

    A row with no party column was stored as the default party. A row with no
    promo column was stored as the public rate.
    """
    matched = [
        row
        for row in iter_rows(history_dir)
        if row.get("check_in") == check_in
        and row.get("nights") == str(nights)
        and row.get("board") == board
        and row.get("rooms") == str(rooms)
        and (row.get("party") or DEFAULT_PARTY) == party
        and (row.get("promo") or DEFAULT_PROMO) == promo
    ]
    matched.sort(key=lambda row: row.get("scraped_at") or "")
    return matched


def cheapest_observation(rows: list[dict[str, str]]) -> dict[str, str] | None:
    """Lowest available total. Ties keep the earliest scrape."""
    best: tuple[float, str, dict[str, str]] | None = None
    for row in rows:
        if row.get("status") != "available":
            continue
        price = _price(row.get("total_price"))
        if price is None:
            continue
        scraped_at = row.get("scraped_at") or ""
        if best is None or price < best[0] or (price == best[0] and scraped_at < best[1]):
            best = (price, scraped_at, row)
    return None if best is None else best[2]


def format_report(
    check_in: str,
    nights: int,
    board: str,
    rooms: int,
    rows: list[dict[str, str]],
    *,
    party: str = DEFAULT_PARTY,
    promo: str = DEFAULT_PROMO,
) -> str:
    room_word = "room" if rooms == 1 else "rooms"
    lines = [
        f"Stay {check_in}, {nights} nights, {board}, {rooms} {room_word}, party {party}, promo {promo}",
        f"observations={len(rows)}",
        "",
    ]
    if not rows:
        lines.append("No history rows for this stay.")
        lines.append("")
        return "\n".join(lines)
    lines.append(
        f"{'scraped_at':<32}  {'status':<12}  {'total_price':>12}  {'price_per_night':>16}  room_type"
    )
    for row in rows:
        lines.append(
            f"{row.get('scraped_at', ''):<32}  "
            f"{row.get('status', ''):<12}  "
            f"{(row.get('total_price') or ''):>12}  "
            f"{(row.get('price_per_night') or ''):>16}  "
            f"{row.get('room_type') or ''}"
        )
    lines.append("")
    winner = cheapest_observation(rows)
    if winner is None:
        lines.append("Cheapest to book: no available price in this history.")
    else:
        lines.append(
            "Cheapest to book: "
            f"{winner['total_price']} ILS "
            f"({winner['price_per_night']}/night), "
            f"first seen {winner['scraped_at']}"
        )
        if winner.get("room_type"):
            lines.append(f"Room: {winner['room_type']}")
    lines.append("")
    return "\n".join(lines)


def _price(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
