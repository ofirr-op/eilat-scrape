"""Civil dates for the Hebrew calendar.

The day count follows the molad and the four postponements (deḥiyyot), the
same rules used by the Israeli civil calendar. Month numbers are the usual
ones: Nisan is 1, Tishrei is 7, and Adar II in a leap year is 13.
"""

from __future__ import annotations

from datetime import date, timedelta

# Day number of the Hebrew epoch in ``date.toordinal()`` units (1 = 1 Jan 1 CE).
# Chosen so 1 Tishrei 5787 is 12 September 2026.
_EPOCH = -1373428


def is_leap(year: int) -> bool:
    return (7 * year + 1) % 19 < 7


def _elapsed_days(year: int) -> int:
    """Days from the Hebrew epoch until 1 Tishrei of ``year``.

    Includes the four postponements: molad zaken, GaTRaD, BeTUTeKaPOT, and
    lo ADU (Rosh Hashana is not Sunday, Wednesday, or Friday).
    """
    months = (235 * year - 234) // 19
    parts = 204 + 793 * (months % 1080)
    hours = 5 + 12 * months + 793 * (months // 1080) + parts // 1080
    day = 1 + 29 * months + hours // 24
    parts = 1080 * (hours % 24) + parts % 1080
    if (
        parts >= 19440
        or (day % 7 == 2 and parts >= 9924 and not is_leap(year))
        or (day % 7 == 1 and parts >= 16789 and is_leap(year - 1))
    ):
        day += 1
    if day % 7 in (0, 3, 5):
        day += 1
    return day


def year_length(year: int) -> int:
    return _elapsed_days(year + 1) - _elapsed_days(year)


def month_days(year: int, month: int) -> int:
    """Length of a Hebrew month. ``month`` is 1 (Nisan) … 13 (Adar II)."""
    if month in (2, 4, 6, 10, 13):
        return 29
    if month == 12 and not is_leap(year):
        return 29
    length = year_length(year)
    if month == 8 and length % 10 != 5:
        return 29
    if month == 9 and length % 10 == 3:
        return 29
    return 30


def hebrew_to_gregorian(year: int, month: int, day: int) -> date:
    """Gregorian date of Hebrew ``year``-``month``-``day`` (Nisan = 1)."""
    before = _elapsed_days(year)
    # Nisan–Elul belong to the same Hebrew year but fall after Tishrei,
    # so they are counted from the previous Tishrei plus the months in between.
    if month < 7:
        # Tishrei through Adar (or Adar II), then Nisan up to this month.
        last = 14 if is_leap(year) else 13
        for earlier in range(7, last):
            before += month_days(year, earlier)
        for earlier in range(1, month):
            before += month_days(year, earlier)
    else:
        for earlier in range(7, month):
            before += month_days(year, earlier)
    ordinal = _EPOCH + before + day - 1
    return date.fromordinal(ordinal)


def gregorian_to_hebrew(day: date) -> tuple[int, int, int]:
    """Hebrew ``(year, month, day)`` of a Gregorian date. Nisan is month 1."""
    # The Hebrew year that contains this civil date started in the previous autumn.
    guess = day.year + 3761
    for year in (guess, guess - 1, guess + 1):
        start = hebrew_to_gregorian(year, 7, 1)
        nxt = hebrew_to_gregorian(year + 1, 7, 1)
        if start <= day < nxt:
            return _within_year(year, (day - start).days)
    raise ValueError(f"no Hebrew year contains {day.isoformat()}")


def _within_year(year: int, offset: int) -> tuple[int, int, int]:
    months = [7, 8, 9, 10, 11, 12]
    if is_leap(year):
        months.append(13)
    months.extend([1, 2, 3, 4, 5, 6])
    left = offset
    for month in months:
        length = month_days(year, month)
        if left < length:
            return year, month, left + 1
        left -= length
    raise ValueError(f"offset {offset} is outside Hebrew year {year}")


def add_hebrew_days(year: int, month: int, day: int, days: int) -> date:
    return hebrew_to_gregorian(year, month, day) + timedelta(days=days)
