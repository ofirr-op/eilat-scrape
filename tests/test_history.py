import gzip
import csv
import hashlib
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scrape.cli import build_parser
from scrape.history import HISTORY_FIELDS, append_document, append_run, iter_rows, normalize_scraped_at
from scrape.history_query import cheapest_observation, format_report, main, stay_rows

ROOT = Path(__file__).resolve().parents[1]
LEGACY_HISTORY = {
    "2026-10-24T074751.745627Z.csv.gz": "58874e3cb33c40b5266db0ab6eb82e6c18a341e6107ee2f970a0578ddfe95473",
    "2026-10-25T070911.684574Z.csv.gz": "6e7a17e8671f8e36c26425b67d5fc7d9d2b6062d70015eaa424ffbdc9b163a3c",
    "2026-10-26T071755.741993Z.csv.gz": "61d9c7f31e9fe3f0ae289b28f2a3cda3532fb733b40912b59479820042fa8866",
}


def _row(check_in, nights, rooms, board, status, total, per_night, room_type):
    return {
        "check_in": check_in,
        "nights": nights,
        "rooms": rooms,
        "board": board,
        "status": status,
        "total_price": total,
        "price_per_night": per_night,
        "room_type": room_type,
        "offers": [{"total_price": 1}],
    }


class HistoryStoreTests(unittest.TestCase):
    def test_timestamp_is_utc_zulu(self):
        stamp = normalize_scraped_at("2026-10-25T07:09:11.684574+00:00")
        self.assertEqual(stamp, "2026-10-25T07:09:11.684574Z")
        aware = datetime(2026, 10, 24, 7, 47, 51, tzinfo=timezone.utc)
        self.assertEqual(normalize_scraped_at(aware), "2026-10-24T07:47:51Z")

    def test_append_is_exclusive_and_drops_offers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = append_run(
                root,
                [_row("2026-11-14", 2, 1, "RO", "available", 1647.059, 823.529, 'סוויטה דלקס, 2 חדרים')],
                scraped_at="2026-10-24T07:47:51.745627+00:00",
            )
            self.assertEqual(first.name, "2026-10-24T074751.745627Z.csv.gz")
            with self.assertRaises(FileExistsError):
                append_run(root, [], scraped_at="2026-10-24T07:47:51.745627Z")
            with gzip.open(first, "rt", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, HISTORY_FIELDS)
                stored = list(reader)
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["scraped_at"], "2026-10-24T07:47:51.745627Z")
            self.assertEqual(stored[0]["total_price"], "1647.06")
            self.assertEqual(stored[0]["price_per_night"], "823.53")
            self.assertEqual(stored[0]["party"], "2a3c")
            self.assertEqual(stored[0]["promo"], "none")
            self.assertNotIn("offers", stored[0])
            self.assertIn("סוויטה", stored[0]["room_type"])

    def test_non_default_party_and_promo_get_a_suffix(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plain = append_run(
                root,
                [_row("2026-11-14", 2, 1, "RO", "available", 100, 50, "suite")],
                scraped_at="2026-10-26T12:00:00Z",
            )
            other = append_run(
                root,
                [_row("2026-11-14", 2, 1, "RO", "available", 90, 45, "suite")],
                scraped_at="2026-10-26T12:00:00Z",
                party="4a1c",
                promo="mhot",
            )
            mhot_only = append_run(
                root,
                [_row("2026-11-14", 2, 1, "RO", "available", 95, 47.5, "suite")],
                scraped_at="2026-10-26T12:00:01Z",
                promo="mhot",
            )
            self.assertEqual(plain.name, "2026-10-26T120000Z.csv.gz")
            self.assertEqual(other.name, "2026-10-26T120000Z-4a1c-mhot.csv.gz")
            self.assertEqual(mhot_only.name, "2026-10-26T120001Z-mhot.csv.gz")
            rows = stay_rows(root, check_in="2026-11-14", nights=2, board="RO", rooms=1, party="4a1c", promo="mhot")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["total_price"], "90.00")
            public = stay_rows(root, check_in="2026-11-14", nights=2, board="RO", rooms=1)
            self.assertEqual([row["total_price"] for row in public], ["100.00"])

    def test_legacy_snapshot_without_columns_reads_as_2a3c_none(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            runs.mkdir()
            path = runs / "2026-10-24T074751.745627Z.csv.gz"
            body = (
                "scraped_at,check_in,nights,rooms,board,status,total_price,price_per_night,room_type\n"
                "2026-10-24T07:47:51.745627Z,2026-11-14,2,1,RO,available,1647.06,823.53,suite\n"
            )
            with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
                handle.write(body)
            before = path.read_bytes()
            rows = list(iter_rows(root))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(rows[0]["party"], "2a3c")
            self.assertEqual(rows[0]["promo"], "none")
            self.assertEqual(
                stay_rows(root, check_in="2026-11-14", nights=2, board="RO", rooms=1),
                rows,
            )
            self.assertEqual(
                stay_rows(root, check_in="2026-11-14", nights=2, board="RO", rooms=1, party="4a1c"),
                [],
            )
            self.assertEqual(
                stay_rows(root, check_in="2026-11-14", nights=2, board="RO", rooms=1, promo="mhot"),
                [],
            )

    def test_committed_history_files_stay_byte_for_byte(self):
        runs = ROOT / "output" / "history" / "runs"
        for name, digest in LEGACY_HISTORY.items():
            path = runs / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                fieldnames = csv.DictReader(handle).fieldnames
            self.assertNotIn("party", fieldnames)
            self.assertNotIn("promo", fieldnames)
        sample = stay_rows(runs.parent, check_in="2026-11-14", nights=2, board="RO", rooms=1)
        self.assertTrue(sample)
        self.assertTrue(all(row["party"] == "2a3c" and row["promo"] == "none" for row in sample))

    def test_unavailable_prices_stay_blank(self):
        with TemporaryDirectory() as tmp:
            path = append_run(
                Path(tmp),
                [_row("2026-10-26", 3, 2, "HB", "unavailable", None, None, "")],
                scraped_at="2026-10-25T07:09:11Z",
            )
            rows = list(iter_rows(path.parent.parent))
            self.assertEqual(rows[0]["status"], "unavailable")
            self.assertEqual(rows[0]["total_price"], "")
            self.assertEqual(rows[0]["price_per_night"], "")
            self.assertEqual(rows[0]["room_type"], "")

    def test_document_uses_generated_at(self):
        with TemporaryDirectory() as tmp:
            path = append_document(
                Path(tmp),
                {
                    "generated_at": "2026-10-25T07:09:11.684574+00:00",
                    "results": [_row("2026-11-14", 2, 1, "HB", "available", "3635.56", "1817.78", "סוויטה דלקס")],
                },
            )
            self.assertTrue(path.name.startswith("2026-10-25T070911.684574Z"))
            stored = list(iter_rows(Path(tmp)))
            self.assertEqual(stored[0]["board"], "HB")
            self.assertEqual(stored[0]["scraped_at"], "2026-10-25T07:09:11.684574Z")


class HistoryQueryTests(unittest.TestCase):
    def _seed(self, root: Path):
        append_run(
            root,
            [
                _row("2026-11-14", 2, 1, "RO", "available", "1700.00", "850.00", "suite"),
                _row("2026-11-14", 2, 1, "BB", "unavailable", None, None, ""),
            ],
            scraped_at="2026-10-25T07:09:11Z",
        )
        append_run(
            root,
            [
                _row("2026-11-14", 2, 1, "RO", "available", "1647.06", "823.53", "deluxe"),
                _row("2026-11-14", 2, 1, "BB", "available", "2229.06", "1114.53", "deluxe"),
            ],
            scraped_at="2026-10-24T07:47:51Z",
        )

    def test_series_is_oldest_first_and_cheapest_is_earliest_tie_break(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            append_run(
                root,
                [_row("2026-11-14", 2, 1, "RO", "available", "1647.06", "823.53", "deluxe again")],
                scraped_at="2026-10-26T08:00:00Z",
            )
            rows = stay_rows(root, check_in="2026-11-14", nights=2, board="RO", rooms=1)
            self.assertEqual([row["scraped_at"] for row in rows], [
                "2026-10-24T07:47:51Z",
                "2026-10-25T07:09:11Z",
                "2026-10-26T08:00:00Z",
            ])
            winner = cheapest_observation(rows)
            assert winner is not None
            self.assertEqual(winner["scraped_at"], "2026-10-24T07:47:51Z")
            self.assertEqual(winner["total_price"], "1647.06")
            report = format_report("2026-11-14", 2, "RO", 1, rows)
            self.assertIn("Cheapest to book: 1647.06 ILS", report)
            self.assertIn("first seen 2026-10-24T07:47:51Z", report)
            self.assertLess(report.index("2026-10-24"), report.index("2026-10-25"))

    def test_unavailable_does_not_win(self):
        rows = [
            {
                "scraped_at": "2026-10-24T07:47:51Z",
                "status": "unavailable",
                "total_price": "",
                "price_per_night": "",
                "room_type": "",
            },
            {
                "scraped_at": "2026-10-25T07:09:11Z",
                "status": "available",
                "total_price": "2229.06",
                "price_per_night": "1114.53",
                "room_type": "deluxe",
            },
        ]
        winner = cheapest_observation(rows)
        assert winner is not None
        self.assertEqual(winner["scraped_at"], "2026-10-25T07:09:11Z")
        report = format_report("2026-11-14", 2, "BB", 1, [rows[0]])
        self.assertIn("no available price", report)

    def test_cli_prints_the_series(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            buffer = StringIO()
            with patch("sys.stdout", buffer):
                code = main([
                    "--history", str(root),
                    "--check-in", "2026-11-14",
                    "--nights", "2",
                    "--board", "RO",
                    "--rooms", "1",
                ])
            self.assertEqual(code, 0)
            text = buffer.getvalue()
            self.assertIn("1647.06", text)
            self.assertIn("1700.00", text)
            self.assertIn("Cheapest to book: 1647.06 ILS", text)

    def test_cli_missing_stay_exits_1(self):
        with TemporaryDirectory() as tmp:
            buffer = StringIO()
            with patch("sys.stdout", buffer):
                code = main([
                    "--history", tmp,
                    "--check-in", "2026-01-01",
                    "--nights", "2",
                    "--board", "HB",
                    "--rooms", "2",
                ])
            self.assertEqual(code, 1)
            self.assertIn("No history rows", buffer.getvalue())

    def test_daily_command_records_history_by_default(self):
        args = build_parser().parse_args(["--output", "output/eilat"])
        self.assertEqual(args.history, "output/history")
        self.assertFalse(args.no_history)
        self.assertIsNone(args.party)
        self.assertIsNone(args.promo)
        skipped = build_parser().parse_args(["--no-history"])
        self.assertTrue(skipped.no_history)
        both = build_parser().parse_args(["--party", "2a3c", "--party", "4a1c", "--promo", "none,mhot"])
        self.assertEqual(both.party, ["2a3c", "4a1c"])
        self.assertEqual(both.promo, ["none,mhot"])
