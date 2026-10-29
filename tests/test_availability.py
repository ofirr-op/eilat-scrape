import json
import unittest
from datetime import date, datetime, timedelta, timezone

from scrape.availability import (
    AVAILABILITY_URL,
    apply_arrival_calendar,
    availability_payload,
    fetch_arrival_calendar,
    parse_availability_body,
    parse_engine_date,
)
from scrape.cli import build_parser
from scrape.http_client import FetchError, FetchResult
from scrape.party import occupancy_for
from scrape.search import calendar_unavailable


def _ms(day: date, hour: int = 10) -> int:
    instant = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
    return int(instant.timestamp() * 1000)


def _row(day: date, *, avail: bool = True, arrival: bool = False, departure: bool = False, min_days: int = 1) -> dict:
    return {
        "DayDate": f"/Date({_ms(day)})/",
        "IsAvail": avail,
        "CloseToArrival": arrival,
        "CloseToDeparture": departure,
        "MinDays": min_days,
    }


class AvailabilityParseTests(unittest.TestCase):
    def test_engine_date_matches_live_stamp(self):
        # First row returned on 2026-10-26: /Date(1793008800000)/ == that UTC date.
        self.assertEqual(parse_engine_date("/Date(1793008800000)/"), date(2026, 10, 26))
        self.assertEqual(parse_engine_date("\\/Date(1793008800000)\\/"), date(2026, 10, 26))

    def test_offset_moves_the_local_date(self):
        stamp = _ms(date(2026, 10, 26), hour=22)
        self.assertEqual(parse_engine_date(f"/Date({stamp})/"), date(2026, 10, 26))
        self.assertEqual(parse_engine_date(f"/Date({stamp}+0300)/"), date(2026, 10, 27))

    def test_wrapped_payload_marks_closed_days_and_drops_the_tail(self):
        open_day = date(2026, 10, 27)
        closed_day = date(2026, 10, 28)
        arrival_day = date(2026, 10, 29)
        last = date(2026, 10, 30)
        body = json.dumps({
            "d": {
                "Availibility": [
                    _row(open_day),
                    _row(closed_day, avail=False),
                    _row(arrival_day, arrival=True),
                    _row(last, avail=False, arrival=True),
                ],
            },
        })
        calendar = parse_availability_body(body)
        assert calendar is not None
        self.assertEqual([entry.day for entry in calendar], [open_day, closed_day, arrival_day, last])
        window = [open_day, closed_day, arrival_day, last, date(2026, 10, 31), date(2026, 11, 1)]
        kept, closed = apply_arrival_calendar(window, calendar)
        self.assertEqual(kept, [open_day, closed_day, arrival_day, last])
        self.assertNotIn(open_day, closed)
        self.assertEqual(closed[closed_day], "calendar: not available")
        self.assertEqual(closed[arrival_day], "calendar: closed to arrival")
        self.assertEqual(closed[last], "calendar: not available and closed to arrival")

    def test_a_gap_inside_the_calendar_is_still_fetched(self):
        first = date(2026, 12, 1)
        last = date(2026, 12, 3)
        calendar = parse_availability_body(json.dumps([_row(first), _row(last)]))
        assert calendar is not None
        kept, closed = apply_arrival_calendar([first, date(2026, 12, 2), last, date(2026, 12, 4)], calendar)
        self.assertEqual(kept, [first, date(2026, 12, 2), last])
        self.assertEqual(closed, {})

    def test_unusable_body_is_not_a_calendar(self):
        self.assertIsNone(parse_availability_body("not json"))
        self.assertIsNone(parse_availability_body('{"d":{"Availibility":[]}}'))
        self.assertIsNone(parse_availability_body("<html>blocked</html>"))

    def test_payload_matches_the_club_hotel_request(self):
        self.assertEqual(
            availability_payload(hotel="1_1", lang="heb"),
            {
                "hotelID": "1",
                "wing": None,
                "dsn": "",
                "lang": "heb",
                "days": 550,
                "fromdate": None,
                "enddate": None,
            },
        )


class AvailabilityFetchTests(unittest.TestCase):
    def test_one_post_parses_the_calendar(self):
        day = date(2026, 11, 1)
        body = json.dumps({"d": {"Availibility": [_row(day, avail=False)]}})

        class Client:
            def __init__(self):
                self.calls = []

            def post_json(self, url, payload):
                self.calls.append((url, payload))
                return FetchResult(url, 200, body, "direct", False)

        client = Client()
        calendar = fetch_arrival_calendar(client, hotel="1_1", lang="heb")
        assert calendar is not None
        self.assertEqual(client.calls, [(AVAILABILITY_URL, availability_payload(hotel="1_1", lang="heb"))])
        self.assertTrue(calendar[0].skip_checkin)

    def test_failure_returns_none(self):
        class Client:
            def post_json(self, url, payload):
                raise FetchError("down")

        self.assertIsNone(fetch_arrival_calendar(Client(), hotel="1_1", lang="heb"))

        class Html:
            def post_json(self, url, payload):
                return FetchResult(url, 200, "<html></html>", "direct", False)

        self.assertIsNone(fetch_arrival_calendar(Html(), hotel="1_1", lang="heb"))


class CalendarRowTests(unittest.TestCase):
    def test_closed_date_is_unavailable_without_a_promocode_on_the_public_rate(self):
        party = occupancy_for("4a1c")
        rows = calendar_unavailable(
            date(2026, 10, 28),
            2,
            party,
            room_count=1,
            hotel="1_1",
            lang="heb",
            promo="none",
            reason="calendar: not available",
        )
        self.assertEqual([row.board for row in rows], ["RO", "BB", "HB"])
        self.assertTrue(all(row.status == "unavailable" for row in rows))
        self.assertTrue(all(row.transport == "calendar" for row in rows))
        self.assertTrue(all(row.reason == "calendar: not available" for row in rows))
        self.assertNotIn("promocode", rows[0].url)
        self.assertIn("ad1=4", rows[0].url)
        self.assertIn("in=2026-10-28", rows[0].url)

    def test_mhot_booking_url_carries_the_code(self):
        party = occupancy_for("2a3c")
        rows = calendar_unavailable(
            date(2026, 10, 28),
            3,
            party,
            room_count=2,
            hotel="1_1",
            lang="heb",
            promo="mhot",
            reason="calendar: closed to arrival",
        )
        self.assertTrue(all(row.url.endswith("&promocode=mhot") for row in rows))
        self.assertEqual(rows[0].check_out, date(2026, 10, 28) + timedelta(days=3))


class PrecheckFlagTests(unittest.TestCase):
    def test_precheck_is_on_unless_disabled(self):
        self.assertFalse(build_parser().parse_args([]).no_avail_precheck)
        self.assertTrue(build_parser().parse_args(["--no-avail-precheck"]).no_avail_precheck)


if __name__ == "__main__":
    unittest.main()
