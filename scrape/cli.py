"""Command-line entry point."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scrape.availability import apply_arrival_calendar, fetch_arrival_calendar
from scrape.dates import checkin_dates, sample_dates
from scrape.history import append_document
from scrape.http_client import Client
from scrape.parse import best_assignment
from scrape.party import (
    PARTY_PRESETS,
    combo_output_dir,
    occupancy_for,
    selected_parties,
    selected_promos,
)
from scrape.report import build_document, print_summary, write_outputs
from scrape.search import Combination, FetchAttempt, calendar_unavailable, search_stay

# Write a recoverable slice this often so a long run is not only in memory.
CHECKPOINT_EVERY = 20


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        nights = _nights(args.nights)
        room_counts = _rooms(args.rooms)
        parties = selected_parties(args.party)
        promos = selected_promos(args.promo)
        if (args.adults is not None or args.children_ages is not None) and len(parties) != 1:
            raise ValueError("--adults and --children-ages apply to a single --party")
        ages_override = None if args.children_ages is None else _ages(args.children_ages)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    start = date.today() + timedelta(days=1)
    days = checkin_dates(start, args.months)
    client = Client(
        cache_dir=Path(args.cache_dir),
        delay_seconds=args.delay,
        retries=args.retries,
        timeout=args.timeout,
        cache_hours=args.cache_hours,
        refresh=args.refresh,
        transport=args.transport,
    )
    closed: dict[date, str] = {}
    if not args.no_avail_precheck:
        calendar = fetch_arrival_calendar(client, hotel=args.hotel, lang=args.lang)
        if calendar:
            before = len(days)
            last = max(entry.day for entry in calendar)
            days, closed = apply_arrival_calendar(days, calendar)
            dropped = before - len(days)
            days = sample_dates(days, args.max_dates)
            kept = set(days)
            closed = {day: reason for day, reason in closed.items() if day in kept}
            print(
                f"Availability calendar: {len(calendar)} days through {last.isoformat()}; "
                f"skipping {len(closed)} closed check-ins; "
                f"not crawling {dropped} dates after {last.isoformat()}.",
                flush=True,
            )
        else:
            days = sample_dates(days, args.max_dates)
    else:
        days = sample_dates(days, args.max_dates)
    print(
        f"Searching {len(days)} check-in dates × nights {nights} × rooms {room_counts} "
        f"× parties {parties} × promos {promos}",
        flush=True,
    )

    worst = 0
    wrote = False
    for party_id in parties:
        try:
            occupancy = occupancy_for(
                party_id,
                adult_from_age=args.adult_from_age,
                infant_under_age=args.infant_under_age,
                adults=args.adults,
                child_ages=ages_override,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for promo in promos:
            code, did_write = _run_combo(
                args,
                client,
                days,
                nights,
                room_counts,
                party_id,
                promo,
                occupancy,
                closed,
            )
            wrote = wrote or did_write
            worst = max(worst, code)
    if not wrote:
        print("No stays could be fetched.", file=sys.stderr)
        return 1
    return worst


def _run_combo(
    args,
    client: Client,
    days,
    nights,
    room_counts,
    party_id: str,
    promo: str,
    occupancy,
    closed: dict[date, str],
) -> tuple[int, bool]:
    started = datetime.now(timezone.utc)
    out_dir = combo_output_dir(Path(args.output), party_id, promo)
    print(
        f"Party {party_id} promo {promo} started_at {started.isoformat()} → {out_dir}",
        flush=True,
    )
    print(
        f"  {occupancy.adults} adults, {occupancy.children} children, {occupancy.infants} infants "
        f"(ages {list(occupancy.child_ages)})",
        flush=True,
    )
    input_adults = PARTY_PRESETS[party_id][0] if args.adults is None else args.adults
    input_ages = PARTY_PRESETS[party_id][1] if args.children_ages is None else occupancy.child_ages
    if occupancy.adults != input_adults or occupancy.children != len(input_ages) or occupancy.infants:
        print(
            "Some listed ages were reclassified (infant or adult). "
            f"Querying the engine as {occupancy.adults} adults, "
            f"{occupancy.children} children, {occupancy.infants} infants.",
            flush=True,
        )

    results: list[Combination] = []
    failures = 0
    split_stats: dict[str, dict[str, dict]] = {}
    for index, check_in in enumerate(days, start=1):
        if check_in in closed:
            reason = closed[check_in]
            print(
                f"  {party_id}/{promo} {check_in.isoformat()}  calendar  {reason}",
                flush=True,
            )
            for length in nights:
                for room_count in room_counts:
                    results.extend(calendar_unavailable(
                        check_in,
                        length,
                        occupancy,
                        room_count=room_count,
                        hotel=args.hotel,
                        lang=args.lang,
                        promo=promo,
                        reason=reason,
                    ))
            if index % CHECKPOINT_EVERY == 0 and results:
                _checkpoint(
                    args, results, occupancy, nights, room_counts,
                    party_id, promo, started, split_stats, out_dir, index, len(days),
                )
            continue
        for length in nights:
            for room_count in room_counts:
                attempts, rows = search_stay(
                    client,
                    check_in,
                    length,
                    occupancy,
                    room_count=room_count,
                    hotel=args.hotel,
                    lang=args.lang,
                    include_club=args.include_club,
                    promo=promo,
                )
                results.extend(rows)
                for attempt in attempts:
                    _note_split(split_stats, room_count, attempt)
                if not attempts:
                    print(
                        f"  {check_in.isoformat()} +{length}n rooms={room_count}  "
                        f"skipped ({rows[0].reason if rows else 'no split'})",
                        flush=True,
                    )
                    continue
                for attempt in attempts:
                    label = (
                        f"{party_id}/{promo} {check_in.isoformat()} +{length}n rooms={room_count} "
                        f"[{attempt.split.label()}]"
                    )
                    cache = " cache" if attempt.from_cache else ""
                    if attempt.error or attempt.page is None or not attempt.page.offers:
                        failures += 1 if attempt.error else 0
                        reason = attempt.error or (attempt.page.unavailable_reason if attempt.page else "")
                        print(f"  {label}  unavailable{cache}  {reason or ''}", flush=True)
                        continue
                    chosen = best_assignment(
                        attempt.page.offers,
                        attempt.page.availability,
                        include_club=args.include_club,
                        room_count=room_count,
                        board="RO",
                    )
                    if chosen is None:
                        print(f"  {label}  no room-only pair{cache}", flush=True)
                    else:
                        total = sum(offer.total_price for offer in chosen)
                        print(
                            f"  {label}  RO {total:.2f} {chosen[0].currency}  "
                            f"{' + '.join(offer.room_type for offer in chosen)}{cache}",
                            flush=True,
                        )
        if index % CHECKPOINT_EVERY == 0 and results:
            _checkpoint(
                args, results, occupancy, nights, room_counts,
                party_id, promo, started, split_stats, out_dir, index, len(days),
            )

    if not results:
        print(f"No stays could be fetched for {party_id}/{promo}.", file=sys.stderr)
        return 1, False

    document = build_document(
        results,
        occupancy,
        hotel=args.hotel,
        nights=nights,
        room_counts=room_counts,
        months=args.months,
        party=party_id,
        promo=promo,
        started_at=started,
        split_stats=_freeze_split_stats(split_stats),
    )
    paths = write_outputs(document, out_dir)
    partial_dir = out_dir / "partial"
    if partial_dir.is_dir():
        shutil.rmtree(partial_dir)
    print_summary(document)
    _print_split_stats(document.get("split_stats") or {})
    print()
    print(f"started_at: {document.get('started_at')}")
    print(f"generated_at: {document['generated_at']}")
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    if not args.no_history:
        try:
            history_path = append_document(Path(args.history), document)
        except FileExistsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1, True
        print(f"history: {history_path}")
    failed_closed = failures and document["counts"]["available"] == 0
    return (1 if failed_closed else 0), True


def _checkpoint(args, results, occupancy, nights, room_counts, party_id, promo, started, split_stats, out_dir, index, total) -> None:
    partial = build_document(
        results,
        occupancy,
        hotel=args.hotel,
        nights=nights,
        room_counts=room_counts,
        months=args.months,
        party=party_id,
        promo=promo,
        started_at=started,
        split_stats=_freeze_split_stats(split_stats),
    )
    write_outputs(partial, out_dir / "partial")
    print(f"  checkpoint {index}/{total} → {out_dir / 'partial'}", flush=True)


def _note_split(stats: dict[str, dict[str, dict]], room_count: int, attempt: FetchAttempt) -> None:
    bucket = stats.setdefault(str(room_count), {})
    entry = bucket.setdefault(
        attempt.split.label(),
        {"requests": 0, "with_offers": 0, "errors": 0, "room_types": set()},
    )
    entry["requests"] += 1
    if attempt.error:
        entry["errors"] += 1
    if attempt.page is not None and attempt.page.offers:
        entry["with_offers"] += 1
        for offer in attempt.page.offers:
            entry["room_types"].add(offer.room_type)


def _freeze_split_stats(stats: dict[str, dict[str, dict]]) -> dict:
    frozen: dict[str, list[dict]] = {}
    for rooms, splits in stats.items():
        frozen[rooms] = [
            {
                "label": label,
                "requests": entry["requests"],
                "with_offers": entry["with_offers"],
                "errors": entry["errors"],
                "room_types": sorted(entry["room_types"]),
            }
            for label, entry in splits.items()
        ]
    return frozen


def _print_split_stats(stats: dict) -> None:
    if not stats:
        return
    print()
    print("Room types seen per split")
    for rooms, splits in stats.items():
        for entry in splits:
            names = ", ".join(entry["room_types"]) or "—"
            print(
                f"  rooms={rooms}  offers {entry['with_offers']}/{entry['requests']}  "
                f"{entry['label']}"
            )
            print(f"    {names}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrape",
        description=(
            "Find Club Hotel Eilat prices for 2, 3 and 4 nights, each board, "
            "and one or two rooms, for each configured party and promo, from BE_Rooms.aspx."
        ),
    )
    parser.add_argument("--months", type=int, default=6, help="How many months ahead to search (default: 6). Check-in runs from tomorrow through that date.")
    parser.add_argument("--nights", default="2,3,4", help="Comma-separated stay lengths in nights (default: 2,3,4).")
    parser.add_argument("--rooms", default="1,2", help="Comma-separated room counts, each 1 or 2 (default: 1,2). Two rooms split the party so each room has an adult.")
    parser.add_argument(
        "--party",
        action="append",
        default=None,
        help=(
            "Party id: 2a3c (2 adults + children 4, 8, 12) or 4a1c (4 adults + child 8). "
            "Repeat the flag or comma-separate. Omit it, or pass both, to scrape every party."
        ),
    )
    parser.add_argument(
        "--promo",
        action="append",
        default=None,
        help=(
            "Promo id: none (no promocode) or mhot (fetch with promocode=mhot). "
            "Repeat the flag or comma-separate. Omit it to scrape both. Prices are scraped, not calculated."
        ),
    )
    parser.add_argument("--adults", type=int, default=None, help="Override the adult count for a single --party. Default: the party preset (2 for 2a3c, 4 for 4a1c).")
    parser.add_argument("--children-ages", default=None, help="Override child ages for a single --party. Default: 4,8,12 for 2a3c and 8 for 4a1c. Ages under --infant-under-age become infants; ages at or above --adult-from-age become adults.")
    parser.add_argument("--adult-from-age", type=int, default=13, help="Age at which a listed child is priced as an adult (default: 13, so 12 stays a child).")
    parser.add_argument("--infant-under-age", type=int, default=2, help="Ages below this are infants (default: 2, matching the hotel's terms).")
    parser.add_argument("--hotel", default="1_1", help="Booking-engine hotel id, OptimaResortID_Wing (default: 1_1, Club Hotel Eilat).")
    parser.add_argument("--lang", default="heb", help="Booking engine language (default: heb).")
    parser.add_argument("--output", default="output/eilat", help="Base directory. 2a3c/none stays here. Other party × promo grids go in party-* and promo-* subdirectories.")
    parser.add_argument("--history", default="output/history", help="Append each party × promo grid as its own gzipped CSV under runs/ (default: output/history).")
    parser.add_argument("--no-history", action="store_true", help="Do not append this run to the price history.")
    parser.add_argument("--cache-dir", default=".cache", help="Response cache directory (default: .cache).")
    parser.add_argument("--cache-hours", type=float, default=24, help="Reuse cached responses younger than this many hours (default: 24).")
    parser.add_argument("--refresh", action="store_true", help="Ignore the cache and refetch.")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between uncached requests (default: 1.5).")
    parser.add_argument("--retries", type=int, default=4, help="Attempts for timeouts and transient HTTP errors (default: 4).")
    parser.add_argument("--timeout", type=float, default=45, help="Per-request timeout in seconds (default: 45).")
    parser.add_argument("--max-dates", type=int, default=0, help="If set, search this many check-in dates spread across the window instead of every day.")
    parser.add_argument(
        "--no-avail-precheck",
        action="store_true",
        help=(
            "Do not POST getAvalibility before crawling. By default one calendar "
            "request skips check-ins that are closed or closed to arrival, and "
            "does not crawl past the last date it returns. A failed calendar "
            "request keeps the full window."
        ),
    )
    parser.add_argument("--include-club", action="store_true", help="Allow i-club member rates to win. They require a login, so they are excluded by default.")
    parser.add_argument(
        "--transport",
        choices=("auto", "direct", "reader"),
        default="auto",
        help="auto tries the booking site directly, then the r.jina.ai HTML reader if Cloudflare hard-blocks this IP. direct never uses the reader. reader always uses it.",
    )
    return parser


def _nights(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("provide at least one stay length")
    nights = [int(part) for part in parts]
    if any(night < 1 or night > 21 for night in nights):
        raise ValueError("stay lengths must be between 1 and 21 nights")
    return nights


def _rooms(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("provide at least one room count")
    counts = [int(part) for part in parts]
    if any(count not in (1, 2) for count in counts):
        raise ValueError("rooms must be 1 or 2")
    return counts


def _ages(value: str) -> list[int]:
    if not value.strip():
        return []
    return [int(part.strip()) for part in value.split(",") if part.strip()]
