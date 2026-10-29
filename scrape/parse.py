"""Parse BE_Rooms.aspx HTML into priced offers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html import unescape

ROOM_DATA_RE = re.compile(r'roomData="([^"]*)"')
AVAILABILITY_RE = re.compile(r'id="AvailableRooms" value="([^"]*)"')
NO_RESULTS_RE = re.compile(
    r'<div class="no-results-text">(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
HOTEL_RE = re.compile(
    r'מלון\s*:</span>\s*([^<]+)',
)
TAG_RE = re.compile(r"<[^>]+>")

# Public rate plans. Club rates require an i-club login, so they are not
# bookable from an anonymous search.
CLUB_PRICE_TYPES = {"clubdeal", "clubpricecode"}

# MealPlan on roomData is a separate rate, not an add-on. The live pages
# spell half board with a trailing space ("חצי פנסיון "); names are stripped
# before this lookup. SpecialServices was null on every captured rate.
BOARD_EN = {
    "לינה בלבד": "room only",
    "כולל ארוחת בוקר": "breakfast",
    "חצי פנסיון": "half board",
    "פנסיון מלא": "full board",
    "הכל כלול": "all inclusive",
}
BOARD_CODE = {
    "לינה בלבד": "RO",
    "כולל ארוחת בוקר": "BB",
    "חצי פנסיון": "HB",
    "פנסיון מלא": "FB",
    "הכל כלול": "AI",
}
# Always emit these so a nights × board × rooms grid stays rectangular.
CANONICAL_BOARDS = ("RO", "BB", "HB")
BOARD_ORDER = ("RO", "BB", "HB", "FB", "AI")
BOARD_HE = {code: name for name, code in BOARD_CODE.items()}

CURRENCY_CODES = {
    "₪": "ILS",
    "NIS": "ILS",
    "ILS": "ILS",
    "$": "USD",
    "USD": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
}


@dataclass(frozen=True)
class Offer:
    room_type: str
    room_code: str
    board: str
    board_he: str
    board_en: str
    package_name: str
    total_price: float
    price_before_discount: float | None
    currency: str
    currency_symbol: str
    price_code_type: str
    requires_club: bool
    is_package: bool
    room_number: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SearchPage:
    hotel_name: str | None
    offers: tuple[Offer, ...]
    availability: dict[str, int]
    unavailable_reason: str | None
    blocked: bool

    @property
    def public_offers(self) -> tuple[Offer, ...]:
        return tuple(offer for offer in self.offers if not offer.requires_club)


def is_cloudflare_block(status: int, html: str) -> bool:
    if status not in (403, 503, 429):
        return False
    lowered = html.lower()
    return (
        "attention required" in lowered
        or "cf-error-details" in lowered
        or "just a moment" in lowered
        or "you have been blocked" in lowered
    )


def parse_rooms_html(html: str) -> SearchPage:
    """Pull every `roomData` offer off a booking-engine results page."""
    if is_cloudflare_block(403, html) and "roomData" not in html:
        return SearchPage(None, (), {}, "cloudflare block", True)

    hotel = None
    hotel_match = HOTEL_RE.search(html)
    if hotel_match:
        hotel = _clean(hotel_match.group(1))

    offers: list[Offer] = []
    for raw in ROOM_DATA_RE.findall(html):
        payload = json.loads(unescape(raw))
        offers.append(_offer_from_payload(payload))

    reason = None
    if not offers:
        reason_match = NO_RESULTS_RE.search(html)
        if reason_match:
            reason = _clean(TAG_RE.sub(" ", reason_match.group(1)))
        else:
            reason = "no rooms returned"
    return SearchPage(hotel, tuple(offers), _availability(html), reason, False)


def cheapest_offer(offers: tuple[Offer, ...] | list[Offer], *, include_club: bool) -> Offer | None:
    pool = [
        offer
        for offer in offers
        if offer.total_price > 0 and (include_club or not offer.requires_club)
    ]
    if not pool:
        return None
    return min(pool, key=lambda offer: (offer.total_price, offer.room_type, offer.board_he))


def _offer_from_payload(payload: dict) -> Offer:
    symbol = _clean(str(payload.get("Currency") or ""))
    currency = CURRENCY_CODES.get(symbol, symbol or "ILS")
    board = _clean(str(payload.get("MealPlan") or ""))
    board_code = BOARD_CODE.get(board, board or "UNKNOWN")
    price_type = str(payload.get("PriceCodeType") or "")
    before = payload.get("PriceNoDiscount")
    before_price = float(before) if before else None
    return Offer(
        room_type=_clean(str(payload.get("RoomType") or "")),
        room_code=str(payload.get("RoomCode") or ""),
        board=board_code,
        board_he=board,
        board_en=BOARD_EN.get(board, board),
        package_name=_clean(str(payload.get("PcName") or "")),
        total_price=float(payload.get("Price") or 0),
        price_before_discount=before_price,
        currency=currency,
        currency_symbol=symbol,
        price_code_type=price_type,
        requires_club=price_type.lower() in CLUB_PRICE_TYPES,
        is_package=bool(payload.get("IsPackage")),
        room_number=int(payload.get("RoomNumber") or 1),
    )


def board_names(code: str) -> tuple[str, str]:
    """Return (hebrew, english) for a board code such as ``HB``."""
    hebrew = BOARD_HE.get(code, code)
    return hebrew, BOARD_EN.get(hebrew, code)


def sort_boards(codes: list[str]) -> list[str]:
    order = {code: index for index, code in enumerate(BOARD_ORDER)}
    return sorted(codes, key=lambda code: (order.get(code, len(order)), code))


def best_assignment(
    offers: tuple[Offer, ...] | list[Offer],
    availability: dict[str, int],
    *,
    include_club: bool,
    room_count: int,
    board: str,
) -> tuple[Offer, ...] | None:
    """Cheapest offer per room for one board, without exceeding room inventory.

    ``AvailableRooms`` on the page maps room code to how many of that room
    can still be sold. Two rooms may share a code only when that count is
    at least 2. An empty availability map does not constrain the choice.
    """
    pools: list[list[Offer]] = []
    for number in range(1, room_count + 1):
        pool = [
            offer
            for offer in offers
            if offer.room_number == number
            and offer.board == board
            and offer.total_price > 0
            and (include_club or not offer.requires_club)
        ]
        pool.sort(key=lambda offer: (offer.total_price, offer.room_type, offer.room_code))
        if not pool:
            return None
        pools.append(pool)
    if room_count == 1:
        return (pools[0][0],)
    best: tuple[float, tuple[Offer, ...]] | None = None
    for first in pools[0]:
        for second in pools[1]:
            total = first.total_price + second.total_price
            if best is not None and total >= best[0]:
                continue
            if not _fits((first, second), availability):
                continue
            best = (total, (first, second))
    return None if best is None else best[1]


def _fits(chosen: tuple[Offer, ...], availability: dict[str, int]) -> bool:
    if not availability:
        return True
    needed: dict[str, int] = {}
    for offer in chosen:
        needed[offer.room_code] = needed.get(offer.room_code, 0) + 1
    return all(count <= availability.get(code, 1) for code, count in needed.items())


def _availability(html: str) -> dict[str, int]:
    match = AVAILABILITY_RE.search(html)
    if match is None or not match.group(1).strip():
        return {}
    try:
        payload = json.loads(unescape(match.group(1)))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in payload.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return counts


def _clean(value: str) -> str:
    return unescape(re.sub(r"\s+", " ", value)).strip()
