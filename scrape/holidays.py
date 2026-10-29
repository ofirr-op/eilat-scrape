"""Jewish holidays on the Israeli calendar.

One-day Yom Tov, as kept in Israel. Diaspora second days are not included,
and neither are non-Jewish holidays, the weekly parasha, candle-lighting,
or Rosh Chodesh. Dates come from the Hebrew calendar, so the page does not
call an external service.
"""

from __future__ import annotations

from datetime import date, timedelta

from scrape.hebrew import hebrew_to_gregorian, is_leap

# kind tints the day: chag, chol, minor, modern, erev.
Holiday = dict[str, str]


def holidays_between(start: date, end: date) -> dict[str, Holiday]:
    """Map ``YYYY-MM-DD`` to ``{"name", "kind"}`` for each holiday in the span.

    ``end`` is inclusive. The first name written for a day wins.
    """
    if end < start:
        return {}
    found: dict[str, Holiday] = {}
    # Hebrew years that can touch this civil span.
    for year in range(start.year + 3760, end.year + 3762):
        for holiday_date, holiday in _year_holidays(year):
            if start <= holiday_date <= end:
                found.setdefault(holiday_date.isoformat(), holiday)
    return found


def _put(out: list[tuple[date, Holiday]], when: date, name: str, kind: str) -> None:
    out.append((when, {"name": name, "kind": kind}))


def _year_holidays(year: int) -> list[tuple[date, Holiday]]:
    """Holidays of Hebrew ``year``, from the eve of Rosh Hashana through Elul."""
    out: list[tuple[date, Holiday]] = []

    def on(month: int, day: int, name: str, kind: str) -> date:
        when = hebrew_to_gregorian(year, month, day)
        _put(out, when, name, kind)
        return when

    rosh = on(7, 1, "ראש השנה", "chag")
    _put(out, rosh - timedelta(days=1), "ערב ראש השנה", "erev")
    on(7, 2, "ראש השנה ב׳", "chag")
    on(7, 9, "ערב יום כיפור", "erev")
    on(7, 10, "יום כיפור", "chag")
    on(7, 14, "ערב סוכות", "erev")
    on(7, 15, "סוכות", "chag")
    for day in range(16, 21):
        on(7, day, "חוה״מ סוכות", "chol")
    on(7, 21, "הושענא רבה", "chol")
    on(7, 22, "שמיני עצרת", "chag")

    hanukkah = on(9, 25, "חנוכה", "minor")
    _put(out, hanukkah - timedelta(days=1), "ערב חנוכה", "erev")
    for offset in range(1, 8):
        _put(out, hanukkah + timedelta(days=offset), "חנוכה", "minor")

    on(11, 15, "ט״ו בשבט", "minor")

    adar = 13 if is_leap(year) else 12
    on(adar, 13, "ערב פורים", "erev")
    on(adar, 14, "פורים", "minor")
    on(adar, 15, "שושן פורים", "minor")

    on(1, 14, "ערב פסח", "erev")
    on(1, 15, "פסח", "chag")
    for day in range(16, 21):
        on(1, day, "חוה״מ פסח", "chol")
    on(1, 21, "שביעי של פסח", "chag")
    _put(out, _yom_hashoah(year), "יום השואה", "modern")

    zikaron, atzmaut = _zikaron_atzmaut(year)
    _put(out, zikaron, "יום הזיכרון", "modern")
    _put(out, atzmaut, "יום העצמאות", "modern")
    on(2, 18, "ל״ג בעומר", "minor")
    on(2, 28, "יום ירושלים", "modern")

    on(3, 5, "ערב שבועות", "erev")
    on(3, 6, "שבועות", "chag")

    fast = _tisha_bav(year)
    _put(out, fast - timedelta(days=1), "ערב תשעה באב", "erev")
    _put(out, fast, "תשעה באב", "chag")
    return out


def _yom_hashoah(year: int) -> date:
    """27 Nisan, moved off Friday and Sunday so it does not touch Shabbat."""
    day = hebrew_to_gregorian(year, 1, 27)
    if day.weekday() == 4:  # Friday
        return day - timedelta(days=1)
    if day.weekday() == 6:  # Sunday
        return day + timedelta(days=1)
    return day


def _zikaron_atzmaut(year: int) -> tuple[date, date]:
    """Independence Day and the memorial day before it.

    5 Iyar is moved so Independence Day is not Friday, Saturday, or Monday
    (the memorial day would then fall on Sunday). The memorial day is the
    day before the observed Independence Day.
    """
    atzmaut = hebrew_to_gregorian(year, 2, 5)
    weekday = atzmaut.weekday()
    if weekday == 4:  # Friday → Thursday
        atzmaut -= timedelta(days=1)
    elif weekday == 5:  # Saturday → Thursday
        atzmaut -= timedelta(days=2)
    elif weekday == 0:  # Monday → Tuesday
        atzmaut += timedelta(days=1)
    elif weekday == 6:  # Sunday → Monday
        atzmaut += timedelta(days=1)
    return atzmaut - timedelta(days=1), atzmaut


def _tisha_bav(year: int) -> date:
    """9 Av. When that day is Shabbat the fast is observed on Sunday."""
    day = hebrew_to_gregorian(year, 5, 9)
    if day.weekday() == 5:
        return day + timedelta(days=1)
    return day
