import unittest
from datetime import date
from pathlib import Path

from scrape.dates import add_months, checkin_dates, classify_party, sample_dates
from scrape.parse import Offer, best_assignment, cheapest_offer, is_cloudflare_block, parse_rooms_html
from scrape.party import candidate_splits, combo_output_dir, occupancy_for, selected_parties, selected_promos
from scrape.search import Combination, rooms_url

FIXTURES = Path(__file__).parent / "fixtures"


class ParseTests(unittest.TestCase):
    def test_available_page_picks_public_room_only_rate(self):
        page = parse_rooms_html((FIXTURES / "available.html").read_text(encoding="utf-8"))
        self.assertEqual(page.hotel_name, "קלאב הוטל אילת")
        self.assertEqual(len(page.offers), 3)
        deluxe = page.offers[0]
        self.assertEqual(deluxe.room_type, 'סוויטה דלקס, 2 חדרים - 50 מ"ר')
        self.assertEqual(deluxe.board, "RO")
        self.assertEqual(deluxe.board_en, "room only")
        self.assertEqual(deluxe.currency, "ILS")
        self.assertAlmostEqual(deluxe.total_price, 2868.29)
        chosen = cheapest_offer(page.offers, include_club=False)
        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertFalse(chosen.requires_club)
        self.assertAlmostEqual(chosen.total_price, 2868.29)
        club = cheapest_offer(page.offers, include_club=True)
        assert club is not None
        self.assertAlmostEqual(club.total_price, 2868.29)
        half = page.offers[2]
        self.assertEqual(half.board, "HB")
        self.assertEqual(half.board_he, "חצי פנסיון")
        self.assertEqual(half.board_en, "half board")
        self.assertTrue(half.requires_club)
        self.assertEqual(half.price_before_discount, 14000)

    def test_unavailable_page(self):
        page = parse_rooms_html((FIXTURES / "unavailable.html").read_text(encoding="utf-8"))
        self.assertEqual(page.offers, ())
        self.assertIn("אינו מתאים", page.unavailable_reason or "")
        self.assertIsNone(cheapest_offer(page.offers, include_club=False))

    def test_cloudflare_block_detection(self):
        html = "<title>Attention Required! | Cloudflare</title> you have been blocked"
        self.assertTrue(is_cloudflare_block(403, html))
        self.assertFalse(is_cloudflare_block(200, html))


class DateTests(unittest.TestCase):
    def test_six_month_window_is_inclusive(self):
        start = date(2026, 10, 24)
        days = checkin_dates(start, 6)
        self.assertEqual(days[0], start)
        self.assertEqual(days[-1], date(2027, 4, 24))
        self.assertEqual(len(days), (days[-1] - days[0]).days + 1)

    def test_add_months_clamps_short_months(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_sample_keeps_ends(self):
        days = checkin_dates(date(2026, 1, 1), 1)
        sampled = sample_dates(days, 4)
        self.assertEqual(sampled[0], days[0])
        self.assertEqual(sampled[-1], days[-1])
        self.assertEqual(len(sampled), 4)

    def test_default_family_keeps_age_12_as_child(self):
        party = classify_party(2, [4, 8, 12])
        self.assertEqual((party.adults, party.children, party.infants), (2, 3, 0))

    def test_english_widget_counts_age_12_as_adult(self):
        party = classify_party(2, [4, 8, 12], adult_from_age=12)
        self.assertEqual((party.adults, party.children, party.infants), (3, 2, 0))

    def test_infant_bracket(self):
        party = classify_party(2, [1, 4])
        self.assertEqual((party.adults, party.children, party.infants), (2, 1, 1))


class UrlTests(unittest.TestCase):
    def test_rooms_url_uses_engine_counts(self):
        party = classify_party(2, [4, 8, 12])
        split = candidate_splits(party, 1)[0]
        url = rooms_url(date(2026, 11, 15), 3, split, hotel="1_1", lang="heb")
        self.assertIn("https://m.clubhotels.co.il/BE_Rooms.aspx?", url)
        self.assertIn("hotel=1_1", url)
        self.assertIn("in=2026-11-15", url)
        self.assertIn("out=2026-11-18", url)
        self.assertIn("ad1=2", url)
        self.assertIn("ch1=3", url)
        self.assertIn("inf1=0", url)
        self.assertIn("rooms=1", url)

    def test_two_room_url_and_splits(self):
        party = classify_party(2, [4, 8, 12])
        splits = candidate_splits(party, 2)
        self.assertEqual(len(splits), 2)
        self.assertEqual(
            [(room.adults, room.children) for room in splits[0].rooms],
            [(1, 2), (1, 1)],
        )
        self.assertEqual(
            [(room.adults, room.children) for room in splits[1].rooms],
            [(1, 3), (1, 0)],
        )
        url = rooms_url(date(2026, 11, 15), 2, splits[0], hotel="1_1", lang="heb")
        self.assertIn("rooms=2", url)
        self.assertIn("ad1=1", url)
        self.assertIn("ch1=2", url)
        self.assertIn("ad2=1", url)
        self.assertIn("ch2=1", url)
        self.assertIn("out=2026-11-17", url)
        self.assertNotIn("promocode", url)

    def test_4a1c_one_room_and_even_two_room_split(self):
        party = occupancy_for("4a1c")
        self.assertEqual((party.adults, party.children, party.infants), (4, 1, 0))
        self.assertEqual(party.child_ages, (8,))
        one = candidate_splits(party, 1)[0]
        self.assertEqual([(room.adults, room.children, room.infants) for room in one.rooms], [(4, 1, 0)])
        one_url = rooms_url(date(2026, 12, 15), 2, one, hotel="1_1", lang="heb", promo="none")
        self.assertEqual(
            one_url,
            "https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1&in=2026-12-15&out=2026-12-17&rooms=1&ad1=4&ch1=1&inf1=0",
        )
        splits = candidate_splits(party, 2)
        occupancies = [
            [(room.adults, room.children, room.infants) for room in split.rooms]
            for split in splits
        ]
        self.assertIn([(2, 1, 0), (2, 0, 0)], occupancies)
        self.assertIn([(3, 1, 0), (1, 0, 0)], occupancies)
        self.assertIn([(1, 1, 0), (3, 0, 0)], occupancies)
        even = next(split for split in splits if [(room.adults, room.children) for room in split.rooms] == [(2, 1), (2, 0)])
        even_url = rooms_url(date(2026, 12, 15), 2, even, hotel="1_1", lang="heb", promo="mhot")
        self.assertEqual(
            even_url,
            "https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1&in=2026-12-15&out=2026-12-17"
            "&rooms=2&ad1=2&ch1=1&inf1=0&ad2=2&ch2=0&inf2=0&promocode=mhot",
        )

    def test_output_dirs_and_default_selection(self):
        base = Path("output/eilat")
        self.assertEqual(combo_output_dir(base, "2a3c", "none"), base)
        self.assertEqual(combo_output_dir(base, "2a3c", "mhot"), base / "promo-mhot")
        self.assertEqual(combo_output_dir(base, "4a1c", "none"), base / "party-4a1c")
        self.assertEqual(combo_output_dir(base, "4a1c", "mhot"), base / "party-4a1c" / "promo-mhot")
        self.assertEqual(selected_parties(None), ["2a3c", "4a1c"])
        self.assertEqual(selected_parties(["2a3c,4a1c"]), ["2a3c", "4a1c"])
        self.assertEqual(selected_parties(["4a1c", "2a3c"]), ["4a1c", "2a3c"])
        self.assertEqual(selected_promos(None), ["none", "mhot"])
        self.assertEqual(selected_promos(["mhot"]), ["mhot"])

    def test_row_url_matches_its_promo(self):
        party = occupancy_for("4a1c")
        split = candidate_splits(party, 1)[0]
        url = rooms_url(date(2026, 12, 15), 2, split, hotel="1_1", lang="heb", promo="mhot")
        combo = Combination(
            check_in=date(2026, 12, 15),
            check_out=date(2026, 12, 17),
            nights=2,
            rooms=1,
            board="RO",
            status="unavailable",
            reason="none",
            hotel_name=None,
            split=None,
            chosen=(),
            offers=(),
            url=url,
            transport="direct",
            from_cache=False,
        )
        row = combo.to_dict(party, party="4a1c", promo="mhot")
        self.assertEqual(row["party"], "4a1c")
        self.assertEqual(row["promo"], "mhot")
        self.assertEqual(row["adults"], 4)
        self.assertEqual(row["children"], 1)
        self.assertIn("promocode=mhot", row["booking_url"])
        self.assertEqual(row["booking_url"], row["url"])
        self.assertNotIn("promocode", rooms_url(date(2026, 12, 15), 2, split, hotel="1_1", lang="heb"))


def _offer(room_number, code, price, board="RO"):
    return Offer(
        room_type=f"room {code}",
        room_code=code,
        board=board,
        board_he="לינה בלבד",
        board_en="room only",
        package_name="deal",
        total_price=price,
        price_before_discount=None,
        currency="ILS",
        currency_symbol="₪",
        price_code_type="pricecode",
        requires_club=False,
        is_package=False,
        room_number=room_number,
    )


class AssignmentTests(unittest.TestCase):
    def test_same_room_code_needs_two_left(self):
        offers = [
            _offer(1, "10", 100),
            _offer(1, "11", 200),
            _offer(2, "10", 100),
            _offer(2, "11", 150),
        ]
        chosen = best_assignment(offers, {"10": 1, "11": 5}, include_club=False, room_count=2, board="RO")
        assert chosen is not None
        self.assertEqual(sum(offer.total_price for offer in chosen), 250)
        self.assertEqual({offer.room_code for offer in chosen}, {"10", "11"})


if __name__ == "__main__":
    unittest.main()
