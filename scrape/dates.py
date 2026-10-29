"""Check-in windows and guest classification."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


def add_months(day: date, months: int) -> date:
    """Return `day` shifted by `months` calendar months, clamping the day."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def checkin_dates(start: date, months: int) -> list[date]:
    """Every check-in from `start` through `start` plus `months` (inclusive)."""
    if months < 1:
        raise ValueError("months must be at least 1")
    end = add_months(start, months)
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def sample_dates(days: list[date], limit: int) -> list[date]:
    """Evenly keep `limit` dates, always including the first and the last."""
    if limit <= 0 or limit >= len(days):
        return list(days)
    if limit == 1:
        return [days[0]]
    picked: list[date] = []
    seen: set[int] = set()
    last = len(days) - 1
    for step in range(limit):
        index = round(step * last / (limit - 1))
        if index not in seen:
            seen.add(index)
            picked.append(days[index])
    return picked


@dataclass(frozen=True)
class Occupancy:
    """How the booking engine will be queried.

    The engine prices a room by counts (adults, children, infants), not by
    each child's age. Ages are classified with the hotel's own brackets and
    then sent as those counts. See README for the 12-year-old edge.
    """

    adults: int
    children: int
    infants: int
    child_ages: tuple[int, ...]
    adult_from_age: int
    infant_under_age: int

    @property
    def guests(self) -> int:
        return self.adults + self.children + self.infants

    def as_query(self) -> dict[str, int]:
        return {"ad1": self.adults, "ch1": self.children, "inf1": self.infants}


def classify_party(
    adults: int,
    child_ages: list[int],
    *,
    adult_from_age: int = 13,
    infant_under_age: int = 2,
) -> Occupancy:
    """Split listed child ages into infants, children, and extra adults.

    `adults` is the number of adults already counted. A listed age at or
    above `adult_from_age` is moved onto the adult count. A listed age below
    `infant_under_age` is an infant. Everyone else stays a child.
    """
    if adults < 1:
        raise ValueError("at least one adult is required")
    if adult_from_age <= infant_under_age:
        raise ValueError("adult-from-age must be greater than infant-under-age")
    extra_adults = 0
    children = 0
    infants = 0
    for age in child_ages:
        if age < 0 or age > 17:
            raise ValueError(f"child age {age} is out of range 0-17")
        if age < infant_under_age:
            infants += 1
        elif age >= adult_from_age:
            extra_adults += 1
        else:
            children += 1
    return Occupancy(
        adults=adults + extra_adults,
        children=children,
        infants=infants,
        child_ages=tuple(child_ages),
        adult_from_age=adult_from_age,
        infant_under_age=infant_under_age,
    )
