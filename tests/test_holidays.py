"""Israeli Jewish holidays baked into the price calendar."""

import unittest
from datetime import date

from scrape.holidays import holidays_between
from scrape.site_data import build_document
from tests.test_site_data import ROOT


class HolidayDateTests(unittest.TestCase):
    def setUp(self):
        self.days = holidays_between(date(2026, 9, 1), date(2027, 10, 1))

    def name(self, iso: str) -> str | None:
        holiday = self.days.get(iso)
        return holiday["name"] if holiday else None

    def test_hanukkah_2026_starts_the_evening_of_4_december(self):
        self.assertEqual(self.name("2026-12-04"), "ערב חנוכה")
        self.assertEqual(self.name("2026-12-05"), "חנוכה")
        self.assertEqual(self.name("2026-12-12"), "חנוכה")
        self.assertIsNone(self.name("2026-12-13"))

    def test_pesach_2027_first_day_is_one_day_in_israel(self):
        self.assertEqual(self.name("2027-04-21"), "ערב פסח")
        self.assertEqual(self.name("2027-04-22"), "פסח")
        self.assertEqual(self.name("2027-04-23"), "חוה״מ פסח")
        self.assertEqual(self.name("2027-04-28"), "שביעי של פסח")
        self.assertIsNone(self.name("2027-04-29"))

    def test_shemini_atzeret_is_not_followed_by_a_diaspora_day(self):
        self.assertEqual(self.name("2026-10-03"), "שמיני עצרת")
        self.assertIsNone(self.name("2026-10-04"))

    def test_shavuot_is_one_day(self):
        self.assertEqual(self.name("2027-06-10"), "ערב שבועות")
        self.assertEqual(self.name("2027-06-11"), "שבועות")
        self.assertIsNone(self.name("2027-06-12"))

    def test_israeli_memorial_and_independence_days(self):
        self.assertEqual(self.name("2027-05-04"), "יום השואה")
        self.assertEqual(self.name("2027-05-11"), "יום הזיכרון")
        self.assertEqual(self.name("2027-05-12"), "יום העצמאות")

    def test_listed_observances_and_nothing_else(self):
        allowed = {
            "ערב ראש השנה", "ראש השנה", "ראש השנה ב׳",
            "ערב יום כיפור", "יום כיפור",
            "ערב סוכות", "סוכות", "חוה״מ סוכות", "הושענא רבה", "שמיני עצרת",
            "ערב חנוכה", "חנוכה",
            "ט״ו בשבט",
            "ערב פורים", "פורים", "שושן פורים",
            "ערב פסח", "פסח", "חוה״מ פסח", "שביעי של פסח",
            "יום השואה", "יום הזיכרון", "יום העצמאות",
            "ל״ג בעומר", "יום ירושלים",
            "ערב שבועות", "שבועות",
            "ערב תשעה באב", "תשעה באב",
        }
        names = {item["name"] for item in self.days.values()}
        self.assertTrue(names, "expected a year of holidays")
        self.assertLessEqual(names, allowed)
        for required in ("ראש השנה", "יום כיפור", "סוכות", "חנוכה", "פורים", "פסח", "שבועות", "תשעה באב"):
            self.assertIn(required, names)

    def test_build_document_includes_hanukkah_when_december_is_on_the_calendar(self):
        document = build_document(ROOT)
        months = {month["key"] for month in document["months"]}
        if "2026-12" not in months:
            self.skipTest("current price window does not show December 2026")
        self.assertEqual(document["holidays"]["2026-12-05"]["name"], "חנוכה")
        self.assertEqual(document["holidays"]["2026-12-04"]["kind"], "erev")


if __name__ == "__main__":
    unittest.main()
