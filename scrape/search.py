"""Search check-in dates and expand each page into board rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlencode

from scrape.dates import Occupancy
from scrape.http_client import Client, FetchError
from scrape.parse import (
    CANONICAL_BOARDS,
    Offer,
    SearchPage,
    best_assignment,
    board_names,
    parse_rooms_html,
    sort_boards,
)
from scrape.party import DEFAULT_PROMO, Split, candidate_splits

ROOMS_URL = "https://m.clubhotels.co.il/BE_Rooms.aspx"


@dataclass
class FetchAttempt:
    split: Split
    url: str
    page: SearchPage | None
    transport: str
    from_cache: bool
    error: str | None


@dataclass
class Combination:
    """One nights × board × rooms cell for a single check-in."""

    check_in: date
    check_out: date
    nights: int
    rooms: int
    board: str
    status: str
    reason: str | None
    hotel_name: str | None
    split: Split | None
    chosen: tuple[Offer, ...]
    offers: tuple[Offer, ...]
    url: str
    transport: str
    from_cache: bool

    def to_dict(self, occupancy: Occupancy, *, party: str, promo: str) -> dict:
        hebrew, english = board_names(self.board)
        total = sum(offer.total_price for offer in self.chosen) if self.chosen else None
        per_night = None if total is None else round(total / self.nights, 2)
        currency = self.chosen[0].currency if self.chosen else ""
        symbol = self.chosen[0].currency_symbol if self.chosen else ""
        selected = {id(offer) for offer in self.chosen}
        offer_rows = [_priced(offer, self.nights, selected=id(offer) in selected) for offer in self.offers]
        cheapest = None if not self.chosen else _combined(self.chosen, self.nights)
        return {
            "check_in": self.check_in.isoformat(),
            "check_out": self.check_out.isoformat(),
            "nights": self.nights,
            "rooms": self.rooms,
            "party": party,
            "promo": promo,
            "board": self.board,
            "board_he": hebrew,
            "board_en": english,
            "adults": occupancy.adults,
            "children": occupancy.children,
            "infants": occupancy.infants,
            "children_ages": list(occupancy.child_ages),
            "split": None if self.split is None else self.split.to_dict(),
            "status": self.status,
            "reason": self.reason,
            "hotel_name": self.hotel_name,
            "room_type": " + ".join(offer.room_type for offer in self.chosen),
            "package_name": " + ".join(_unique(offer.package_name for offer in self.chosen)),
            "total_price": total,
            "price_per_night": per_night,
            "currency": currency,
            "currency_symbol": symbol,
            "room_code": "+".join(offer.room_code for offer in self.chosen),
            "price_code_type": "+".join(_unique(offer.price_code_type for offer in self.chosen)),
            "requires_club": any(offer.requires_club for offer in self.chosen) if self.chosen else False,
            "offers_count": len(self.offers),
            "booking_url": self.url,
            "url": self.url,
            "transport": self.transport,
            "from_cache": self.from_cache,
            "cheapest": cheapest,
            "offers": offer_rows,
        }


def rooms_url(
    check_in: date,
    nights: int,
    split: Split,
    *,
    hotel: str,
    lang: str,
    promo: str = DEFAULT_PROMO,
) -> str:
    """Booking URL that was, or will be, fetched.

    ``promo=none`` has no promocode parameter. ``promo=mhot`` appends
    ``promocode=mhot``. The stored ``booking_url`` is this same URL, so each
    row points at the search that produced its price.
    """
    check_out = check_in + timedelta(days=nights)
    pairs = [
        ("lang", lang),
        ("hotel", hotel),
        ("in", check_in.isoformat()),
        ("out", check_out.isoformat()),
        *split.query_pairs(),
    ]
    if promo != DEFAULT_PROMO:
        pairs.append(("promocode", promo))
    return f"{ROOMS_URL}?{urlencode(pairs)}"


def search_stay(
    client: Client,
    check_in: date,
    nights: int,
    occupancy: Occupancy,
    *,
    room_count: int,
    hotel: str,
    lang: str,
    include_club: bool,
    promo: str = DEFAULT_PROMO,
) -> tuple[list[FetchAttempt], list[Combination]]:
    """Fetch every adult-per-room split, then one row per board."""
    check_out = check_in + timedelta(days=nights)
    splits = candidate_splits(occupancy, room_count)
    if not splits:
        empty = _unavailable_grid(
            check_in, check_out, nights, room_count, occupancy,
            reason=(
                f"need at least one adult in each of {room_count} rooms; "
                f"the party has {occupancy.adults}"
            ),
            hotel_name=None,
            url="",
            transport="",
            from_cache=False,
        )
        return [], empty

    attempts: list[FetchAttempt] = []
    for split in splits:
        url = rooms_url(check_in, nights, split, hotel=hotel, lang=lang, promo=promo)
        try:
            fetched = client.get_html(url)
        except FetchError as exc:
            attempts.append(FetchAttempt(split, url, None, "", False, str(exc)))
            continue
        page = parse_rooms_html(fetched.body)
        error = page.unavailable_reason if page.blocked else None
        attempts.append(FetchAttempt(
            split, url, None if page.blocked else page, fetched.transport, fetched.from_cache, error,
        ))
    return attempts, _combinations(check_in, check_out, nights, room_count, attempts, include_club)


def calendar_unavailable(
    check_in: date,
    nights: int,
    occupancy: Occupancy,
    *,
    room_count: int,
    hotel: str,
    lang: str,
    promo: str,
    reason: str,
) -> list[Combination]:
    """Unavailable board rows for a check-in the calendar already closed.

    No rooms page is fetched. ``booking_url`` is the first split that would
    have been requested, including ``promocode`` only when ``promo`` is not
    ``none``.
    """
    check_out = check_in + timedelta(days=nights)
    splits = candidate_splits(occupancy, room_count)
    url = ""
    if splits:
        url = rooms_url(check_in, nights, splits[0], hotel=hotel, lang=lang, promo=promo)
    return _unavailable_grid(
        check_in,
        check_out,
        nights,
        room_count,
        occupancy,
        reason=reason,
        hotel_name=None,
        url=url,
        transport="calendar",
        from_cache=False,
    )


def _combinations(
    check_in: date,
    check_out: date,
    nights: int,
    room_count: int,
    attempts: list[FetchAttempt],
    include_club: bool,
) -> list[Combination]:
    boards = list(CANONICAL_BOARDS)
    for attempt in attempts:
        if attempt.page is None:
            continue
        for offer in attempt.page.offers:
            if offer.board not in boards:
                boards.append(offer.board)
    rows: list[Combination] = []
    for board in sort_boards(boards):
        rows.append(_best_for_board(
            check_in, check_out, nights, room_count, board, attempts, include_club,
        ))
    return rows


def _best_for_board(
    check_in: date,
    check_out: date,
    nights: int,
    room_count: int,
    board: str,
    attempts: list[FetchAttempt],
    include_club: bool,
) -> Combination:
    winner: tuple[float, FetchAttempt, tuple[Offer, ...]] | None = None
    reasons: list[str] = []
    for attempt in attempts:
        if attempt.error:
            reasons.append(attempt.error)
            continue
        page = attempt.page
        if page is None:
            reasons.append("no page")
            continue
        chosen = best_assignment(
            page.offers,
            page.availability,
            include_club=include_club,
            room_count=room_count,
            board=board,
        )
        if chosen is None:
            if page.unavailable_reason and not page.offers:
                reasons.append(page.unavailable_reason)
            else:
                hebrew, english = board_names(board)
                reasons.append(f"no {english} ({hebrew}) rate for this split")
            continue
        total = sum(offer.total_price for offer in chosen)
        if winner is None or total < winner[0]:
            winner = (total, attempt, chosen)
    if winner is None:
        url = attempts[-1].url if attempts else ""
        transport = attempts[-1].transport if attempts else ""
        cached = all(attempt.from_cache for attempt in attempts) if attempts else False
        hotel = next((attempt.page.hotel_name for attempt in attempts if attempt.page and attempt.page.hotel_name), None)
        return Combination(
            check_in, check_out, nights, room_count, board, "unavailable",
            _reason(reasons), hotel, None, (), (), url, transport, cached,
        )
    _, attempt, chosen = winner
    page = attempt.page
    assert page is not None
    visible = page.offers if include_club else page.public_offers
    board_offers = tuple(offer for offer in visible if offer.board == board)
    return Combination(
        check_in, check_out, nights, room_count, board, "available",
        None, page.hotel_name, attempt.split, chosen, board_offers,
        attempt.url, attempt.transport, attempt.from_cache,
    )


def _unavailable_grid(
    check_in: date,
    check_out: date,
    nights: int,
    room_count: int,
    occupancy: Occupancy,
    *,
    reason: str,
    hotel_name: str | None,
    url: str,
    transport: str,
    from_cache: bool,
) -> list[Combination]:
    del occupancy
    return [
        Combination(
            check_in, check_out, nights, room_count, board, "unavailable",
            reason, hotel_name, None, (), (), url, transport, from_cache,
        )
        for board in CANONICAL_BOARDS
    ]


def _priced(offer: Offer, nights: int, *, selected: bool) -> dict:
    data = offer.to_dict()
    data["price_per_night"] = round(offer.total_price / nights, 2)
    data["selected"] = selected
    return data


def _combined(chosen: tuple[Offer, ...], nights: int) -> dict:
    total = sum(offer.total_price for offer in chosen)
    first = chosen[0]
    components = [_priced(offer, nights, selected=True) for offer in chosen]
    combined = dict(components[0])
    combined.update({
        "room_type": " + ".join(offer.room_type for offer in chosen),
        "room_code": "+".join(offer.room_code for offer in chosen),
        "package_name": " + ".join(_unique(offer.package_name for offer in chosen)),
        "total_price": total,
        "price_per_night": round(total / nights, 2),
        "price_before_discount": _sum_optional(offer.price_before_discount for offer in chosen),
        "price_code_type": "+".join(_unique(offer.price_code_type for offer in chosen)),
        "requires_club": any(offer.requires_club for offer in chosen),
        "is_package": any(offer.is_package for offer in chosen),
        "room_number": first.room_number if len(chosen) == 1 else None,
        "selected": True,
        "components": components,
    })
    return combined


def _sum_optional(values) -> float | None:
    numbers = [value for value in values if value]
    if not numbers:
        return None
    return float(sum(numbers))


def _unique(values) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _reason(reasons: list[str]) -> str:
    unique = []
    for reason in reasons:
        text = " ".join(reason.split())
        if text and text not in unique:
            unique.append(text)
    return unique[0] if len(unique) == 1 else "; ".join(unique) if unique else "unavailable"
