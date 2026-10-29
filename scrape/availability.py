"""Arrival calendar from BE_EngineService.asmx/getAvalibility.

The endpoint returns one row per day (open, closed, minimum stay, closed to
arrival or departure). It does not return prices. A check-in is skipped when
``IsAvail`` is false or ``CloseToArrival`` is true. Check-ins after the last
row are not crawled. Any failure leaves the caller on the full date window.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from scrape.http_client import FetchError

AVAILABILITY_URL = "https://m.clubhotels.co.il/BE_EngineService.asmx/getAvalibility"
AVAILABILITY_DAYS = 550

_DATE_RE = re.compile(r"Date\((-?\d+)(?:([+-])(\d{2}):?(\d{2}))?\)")


@dataclass(frozen=True)
class CalendarDay:
    day: date
    is_avail: bool
    min_days: int
    close_to_arrival: bool
    close_to_departure: bool

    @property
    def skip_checkin(self) -> bool:
        return (not self.is_avail) or self.close_to_arrival

    def reason(self) -> str:
        if not self.is_avail and self.close_to_arrival:
            return "calendar: not available and closed to arrival"
        if self.close_to_arrival:
            return "calendar: closed to arrival"
        if not self.is_avail:
            return "calendar: not available"
        return ""


def availability_payload(*, hotel: str, lang: str) -> dict:
    """Body for Club Hotel. ``hotel=1_1`` sends resort id ``1`` and ``wing`` null."""
    resort = hotel.split("_", 1)[0]
    return {
        "hotelID": resort,
        "wing": None,
        "dsn": "",
        "lang": lang,
        "days": AVAILABILITY_DAYS,
        "fromdate": None,
        "enddate": None,
    }


def parse_engine_date(value: str) -> date | None:
    """ASP.NET ``/Date(milliseconds)/``, optionally with a local offset."""
    match = _DATE_RE.search(value or "")
    if match is None:
        return None
    instant = datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc)
    if match.group(2):
        sign = 1 if match.group(2) == "+" else -1
        offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
        instant = instant + (sign * offset)
    return instant.date()


def parse_availability_body(body: str) -> list[CalendarDay] | None:
    """Parsed days, or None when the body is not a usable calendar."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    rows = _rows_from_payload(payload)
    if not rows:
        return None
    days: list[CalendarDay] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = parse_engine_date(str(row.get("DayDate") or ""))
        if day is None:
            continue
        min_days = row.get("MinDays")
        days.append(CalendarDay(
            day=day,
            is_avail=_as_bool(row.get("IsAvail"), default=True),
            min_days=int(min_days) if isinstance(min_days, int) and not isinstance(min_days, bool) else 0,
            close_to_arrival=_as_bool(row.get("CloseToArrival"), default=False),
            close_to_departure=_as_bool(row.get("CloseToDeparture"), default=False),
        ))
    return days or None


def apply_arrival_calendar(
    days: list[date],
    calendar: list[CalendarDay],
) -> tuple[list[date], dict[date, str]]:
    """Drop check-ins after the calendar and mark closed arrival dates.

    A date on or before the last calendar day that the payload does not
    mention is kept and is not marked closed, so it is still fetched.
    """
    if not calendar:
        return list(days), {}
    by_day = {entry.day: entry for entry in calendar}
    last = max(by_day)
    kept = [day for day in days if day <= last]
    closed = {
        day: by_day[day].reason()
        for day in kept
        if day in by_day and by_day[day].skip_checkin
    }
    return kept, closed


def fetch_arrival_calendar(client, *, hotel: str, lang: str) -> list[CalendarDay] | None:
    """One calendar POST. None means the caller should crawl every date."""
    try:
        result = client.post_json(AVAILABILITY_URL, availability_payload(hotel=hotel, lang=lang))
        return parse_availability_body(result.body)
    except (FetchError, OSError, ValueError, TypeError, AttributeError):
        return None


def _rows_from_payload(payload) -> list | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    data = payload.get("d", payload)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = data.get("Availibility", data.get("Availability"))
        if isinstance(rows, list):
            return rows
    return None


def _as_bool(value, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1"}:
            return True
        if lowered in {"false", "0"}:
            return False
    return default
