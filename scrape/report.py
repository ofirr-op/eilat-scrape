"""CSV, JSON, HTML, and console summaries."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from scrape.dates import Occupancy
from scrape.parse import BOARD_CODE, BOARD_EN, CANONICAL_BOARDS
from scrape.party import DEFAULT_PARTY, DEFAULT_PROMO, two_room_note
from scrape.search import Combination

# Stable column order. New columns are appended in spirit but `rooms` and
# `board` sit next to `nights` because those three are the filter keys.
# Every name that existed in schema 1 is still present.
RESULT_FIELDS = [
    "check_in",
    "check_out",
    "nights",
    "rooms",
    "board",
    "board_he",
    "board_en",
    "status",
    "hotel_name",
    "room_type",
    "package_name",
    "total_price",
    "price_per_night",
    "currency",
    "currency_symbol",
    "room_code",
    "price_code_type",
    "requires_club",
    "offers_count",
    "adults",
    "children",
    "infants",
    "children_ages",
    "split",
    "reason",
    "booking_url",
    "url",
    "party",
    "promo",
]

OFFER_FIELDS = [
    "check_in",
    "check_out",
    "nights",
    "rooms",
    "board",
    "board_he",
    "board_en",
    "room_number",
    "room_type",
    "package_name",
    "total_price",
    "price_per_night",
    "currency",
    "room_code",
    "price_code_type",
    "requires_club",
    "selected",
    "is_cheapest",
    "booking_url",
    "party",
    "promo",
]


PROMO_NOTE = (
    "promo=none is the public rate. Its booking_url has no promocode parameter. "
    "promo=mhot is a separate scrape of the same stays with promocode=mhot on the "
    "fetched URL and on booking_url. The code is not a flat percent off: some package "
    "rates change, list-price rates can stay put, and a room type can disappear, so the "
    "with-code total can be higher than the public total. Do not derive mhot by multiplying."
)


def build_document(
    results: list[Combination],
    occupancy: Occupancy,
    *,
    hotel: str,
    nights: list[int],
    room_counts: list[int],
    months: int,
    party: str = DEFAULT_PARTY,
    promo: str = DEFAULT_PROMO,
    started_at: datetime | None = None,
    split_stats: dict | None = None,
) -> dict:
    rows = [result.to_dict(occupancy, party=party, promo=promo) for result in results]
    available = [row for row in rows if row["status"] == "available" and row["total_price"] is not None]
    available.sort(key=lambda row: (row["total_price"], row["check_in"], row["nights"], row["rooms"], row["board"]))
    by_nights = {str(length): _slim(next((row for row in available if row["nights"] == length), None)) for length in nights}
    by_combination: dict[str, dict | None] = {}
    for length in nights:
        for board in CANONICAL_BOARDS:
            for rooms in room_counts:
                key = f"{length}|{board}|{rooms}"
                match = next(
                    (row for row in available if row["nights"] == length and row["board"] == board and row["rooms"] == rooms),
                    None,
                )
                by_combination[key] = _slim(match)
    document = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "party": party,
        "promo": promo,
        "source": "https://m.clubhotels.co.il/BE_Rooms.aspx",
        "hotel_code": hotel,
        "hotel_name": next((row["hotel_name"] for row in rows if row["hotel_name"]), None),
        "boards": [
            {"code": code, "he": hebrew, "en": BOARD_EN[hebrew]}
            for hebrew, code in BOARD_CODE.items()
            if code in CANONICAL_BOARDS
        ],
        "query": {
            "party": party,
            "promo": promo,
            "months": months,
            "nights": nights,
            "rooms": room_counts,
            "adults": occupancy.adults,
            "children": occupancy.children,
            "infants": occupancy.infants,
            "children_ages": list(occupancy.child_ages),
            "adult_from_age": occupancy.adult_from_age,
            "infant_under_age": occupancy.infant_under_age,
        },
        "counts": {
            "rows": len(rows),
            "stays": len(rows),
            "available": len(available),
            "unavailable": sum(1 for row in rows if row["status"] == "unavailable"),
            "errors": sum(1 for row in rows if row["status"] not in {"available", "unavailable"}),
        },
        "notes": {
            "row": "One result row is one check-in × nights × board × rooms combination for this file's party and promo.",
            "per_night": "price_per_night is total_price / nights for the whole booking, including both rooms when rooms is 2.",
            "half_board": (
                "Half board is a separate MealPlan rate (חצי פנסיון, code HB) on roomData, "
                "with its own total Price. It is not a per-person add-on. SpecialServices was null "
                "on every captured rate. Room only is RO (לינה בלבד) and bed and breakfast is BB (כולל ארוחת בוקר)."
            ),
            "two_rooms": two_room_note(party),
            "promo": PROMO_NOTE,
            "booking_url": (
                "booking_url and url are the BE_Rooms.aspx search that produced the row. "
                "promo=none has no promocode parameter. promo=mhot includes promocode=mhot."
            ),
        },
        "summary": {
            "cheapest_overall": [_slim(row) for row in available[:15]],
            "cheapest_by_nights": by_nights,
            "cheapest_by_combination": by_combination,
        },
        "results": rows,
    }
    if started_at is not None:
        ordered = {}
        for key, value in document.items():
            ordered[key] = value
            if key == "generated_at":
                ordered["started_at"] = started_at.astimezone(timezone.utc).isoformat()
        document = ordered
    if split_stats is not None:
        document["split_stats"] = split_stats
    return document


def stamp_party_promo(document: dict, party: str = DEFAULT_PARTY, promo: str = DEFAULT_PROMO) -> dict:
    """Add party and promo to a grid written before those columns existed.

    Prices, URLs, and generated_at stay as they were. A public 2a3c grid has
    no promocode on its URLs, so promo is ``none``.
    """
    document["schema_version"] = 3
    document["party"] = party
    document["promo"] = promo
    query = document.setdefault("query", {})
    query["party"] = party
    query["promo"] = promo
    notes = document.setdefault("notes", {})
    notes["row"] = "One result row is one check-in × nights × board × rooms combination for this file's party and promo."
    notes["promo"] = PROMO_NOTE
    notes["booking_url"] = (
        "booking_url and url are the BE_Rooms.aspx search that produced the row. "
        "promo=none has no promocode parameter. promo=mhot includes promocode=mhot."
    )

    def stamp(row: dict | None) -> None:
        if not row:
            return
        row["party"] = party
        row["promo"] = promo

    for row in document.get("results") or []:
        stamp(row)
    summary = document.get("summary") or {}
    for row in summary.get("cheapest_overall") or []:
        stamp(row)
    for row in (summary.get("cheapest_by_nights") or {}).values():
        stamp(row)
    for row in (summary.get("cheapest_by_combination") or {}).values():
        stamp(row)
    return document


def write_outputs(document: dict, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / "results.json",
        "csv": output_dir / "results.csv",
        "offers": output_dir / "offers.csv",
        "html": output_dir / "report.html",
    }
    paths["json"].write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_cheapest_csv(document, paths["csv"])
    _write_offers_csv(document, paths["offers"])
    paths["html"].write_text(_html(document), encoding="utf-8")
    return paths


def print_summary(document: dict) -> None:
    counts = document["counts"]
    query = document["query"]
    hotel = document.get("hotel_name") or document["hotel_code"]
    print()
    print(
        f"{hotel} — party {query.get('party', DEFAULT_PARTY)} promo {query.get('promo', DEFAULT_PROMO)} — "
        f"{query['adults']} adults + {query['children']} children + {query['infants']} infants"
    )
    ages = ", ".join(str(age) for age in query["children_ages"]) or "none"
    print(f"Listed child ages: {ages} (adult from {query['adult_from_age']}, infant under {query['infant_under_age']})")
    print(
        f"Rows: {counts['rows']}  "
        f"available: {counts['available']}  "
        f"unavailable: {counts['unavailable']}  "
        f"errors: {counts['errors']}"
    )
    print()
    print("Cheapest total for each nights × board × rooms")
    for key, row in document["summary"]["cheapest_by_combination"].items():
        nights, board, rooms = key.split("|")
        if row is None:
            print(f"  {nights}n {board} rooms={rooms}: no availability")
            continue
        print(f"  {nights}n {board} rooms={rooms}: {_line(row)}")
    print()
    print("Cheapest stays overall")
    overall = document["summary"]["cheapest_overall"]
    if not overall:
        print("  none")
        return
    for index, row in enumerate(overall[:10], start=1):
        print(f"  {index:>2}. {_line(row)}")


def _line(row: dict) -> str:
    split = ""
    if row.get("split"):
        split = "  ·  " + row["split"]["label"]
    return (
        f"{row['check_in']} → {row['check_out']}  "
        f"{row['total_price']:.2f} {row['currency']}  "
        f"({row['price_per_night']:.2f}/night)  "
        f"{row['rooms']} room(s)  {row['board']}  "
        f"{row['room_type']}{split}"
    )


def _write_cheapest_csv(document: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in document["results"]:
            split = row["split"]["label"] if row.get("split") else ""
            writer.writerow({
                "check_in": row["check_in"],
                "check_out": row["check_out"],
                "nights": row["nights"],
                "rooms": row["rooms"],
                "board": row["board"],
                "board_he": row["board_he"],
                "board_en": row["board_en"],
                "status": row["status"],
                "hotel_name": row["hotel_name"] or "",
                "room_type": row["room_type"],
                "package_name": row["package_name"],
                "total_price": _money(row["total_price"]),
                "price_per_night": _money(row["price_per_night"]),
                "currency": row["currency"],
                "currency_symbol": row["currency_symbol"],
                "room_code": row["room_code"],
                "price_code_type": row["price_code_type"],
                "requires_club": row["requires_club"],
                "offers_count": row["offers_count"],
                "adults": row["adults"],
                "children": row["children"],
                "infants": row["infants"],
                "children_ages": ",".join(str(age) for age in row["children_ages"]),
                "split": split,
                "reason": row["reason"] or "",
                "booking_url": row["booking_url"],
                "url": row["url"],
                "party": row.get("party") or DEFAULT_PARTY,
                "promo": row.get("promo") or DEFAULT_PROMO,
            })


def _write_offers_csv(document: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OFFER_FIELDS)
        writer.writeheader()
        for row in document["results"]:
            for offer in row["offers"]:
                writer.writerow({
                    "check_in": row["check_in"],
                    "check_out": row["check_out"],
                    "nights": row["nights"],
                    "rooms": row["rooms"],
                    "board": offer["board"],
                    "board_he": offer["board_he"],
                    "board_en": offer["board_en"],
                    "room_number": offer["room_number"],
                    "room_type": offer["room_type"],
                    "package_name": offer["package_name"],
                    "total_price": _money(offer["total_price"]),
                    "price_per_night": _money(offer["price_per_night"]),
                    "currency": offer["currency"],
                    "room_code": offer["room_code"],
                    "price_code_type": offer["price_code_type"],
                    "requires_club": offer["requires_club"],
                    "selected": offer["selected"],
                    "is_cheapest": offer["selected"],
                    "booking_url": row["booking_url"],
                    "party": row.get("party") or DEFAULT_PARTY,
                    "promo": row.get("promo") or DEFAULT_PROMO,
                })


def _money(value) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def _slim(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "check_in": row["check_in"],
        "check_out": row["check_out"],
        "nights": row["nights"],
        "rooms": row["rooms"],
        "party": row.get("party") or DEFAULT_PARTY,
        "promo": row.get("promo") or DEFAULT_PROMO,
        "board": row["board"],
        "board_he": row["board_he"],
        "board_en": row["board_en"],
        "status": row["status"],
        "total_price": row["total_price"],
        "price_per_night": row["price_per_night"],
        "currency": row["currency"],
        "room_type": row["room_type"],
        "package_name": row["package_name"],
        "split": row["split"],
        "booking_url": row["booking_url"],
    }


def _html(document: dict) -> str:
    query = document["query"]
    counts = document["counts"]
    hotel = escape(document.get("hotel_name") or document["hotel_code"])
    ages = ", ".join(str(age) for age in query["children_ages"]) or "none"
    combo_rows = []
    for key, row in document["summary"]["cheapest_by_combination"].items():
        nights, board, rooms = key.split("|")
        if row is None:
            combo_rows.append(
                f"<tr><td>{nights}</td><td>{escape(board)}</td><td>{rooms}</td><td colspan='4'>unavailable</td></tr>"
            )
            continue
        combo_rows.append(
            "<tr>"
            f"<td>{nights}</td><td>{escape(row['board'])} {escape(row['board_he'])}</td><td>{rooms}</td>"
            f"<td>{row['total_price']:.2f} {escape(row['currency'])}</td>"
            f"<td>{row['price_per_night']:.2f}</td>"
            f"<td>{row['check_in']} → {row['check_out']}</td>"
            f"<td>{escape(row['room_type'])}</td>"
            "</tr>"
        )
    body_rows = []
    ordered = sorted(
        document["results"],
        key=lambda row: (
            row["total_price"] is None,
            row["total_price"] if row["total_price"] is not None else 0,
            row["check_in"],
            row["nights"],
            row["rooms"],
        ),
    )
    for row in ordered:
        if row["total_price"] is None:
            price = "—"
            per = "—"
            room = escape(row["reason"] or row["status"])
        else:
            price = f"{row['total_price']:.2f} {escape(row['currency'])}"
            per = f"{row['price_per_night']:.2f}"
            room = escape(row["room_type"])
        body_rows.append(
            "<tr>"
            f"<td>{row['check_in']}</td>"
            f"<td>{row['check_out']}</td>"
            f"<td>{row['nights']}</td>"
            f"<td>{row['rooms']}</td>"
            f"<td>{escape(row['board'])}</td>"
            f"<td>{escape(row['status'])}</td>"
            f"<td>{price}</td>"
            f"<td>{per}</td>"
            f"<td>{room}</td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Club Hotel Eilat — cheapest stays</title>
<style>
:root {{ color-scheme: light; --ink:#1c1915; --muted:#6b6258; --line:#e4ddd4; --paper:#faf7f2; --card:#fff; --accent:#9a3412; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font:16px/1.45 "Iowan Old Style", Palatino, "Palatino Linotype", serif; color:var(--ink); background:var(--paper); }}
main {{ max-width:1100px; margin:0 auto; padding:32px 20px 64px; }}
h1 {{ font-weight:600; font-size:2rem; margin:0 0 8px; }}
h2 {{ font-size:1.25rem; margin:32px 0 12px; }}
p {{ color:var(--muted); max-width:68ch; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
article {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
article h3 {{ margin:0 0 8px; font-size:0.95rem; letter-spacing:0.04em; text-transform:uppercase; color:var(--accent); }}
article strong {{ display:block; font-size:1.6rem; }}
article span {{ display:block; color:var(--muted); }}
table {{ width:100%; border-collapse:collapse; background:var(--card); font-size:0.92rem; }}
th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:0.75rem; letter-spacing:0.04em; text-transform:uppercase; color:var(--muted); }}
tbody tr:first-child td {{ background:#fff7ed; }}
@media (max-width:720px) {{
  table {{ display:block; overflow-x:auto; }}
}}
</style>
</head>
<body>
<main>
<h1>{hotel}</h1>
<p>Party {escape(str(query.get('party', DEFAULT_PARTY)))}, promo {escape(str(query.get('promo', DEFAULT_PROMO)))}.
{query['adults']} adults, {query['children']} children, {query['infants']} infants.
Child ages used to build that party: {escape(ages)}.
{counts['available']} of {counts['rows']} nights × board × rooms rows had a public price.
promo=none has no promocode on the booking URL. promo=mhot was fetched with promocode=mhot.</p>
<h2>Cheapest of each nights × board × rooms</h2>
<table>
<thead><tr><th>Nights</th><th>Board</th><th>Rooms</th><th>Total</th><th>Per night</th><th>Dates</th><th>Room</th></tr></thead>
<tbody>{''.join(combo_rows)}</tbody>
</table>
<h2>Every combination, cheapest first</h2>
<table>
<thead><tr>
<th>Check-in</th><th>Check-out</th><th>Nights</th><th>Rooms</th><th>Board</th><th>Status</th>
<th>Total</th><th>Per night</th><th>Room</th>
</tr></thead>
<tbody>
{''.join(body_rows)}
</tbody>
</table>
</main>
</body>
</html>
"""
