"""The page data builder: history series, the cheaper booking link, and scan status."""

import csv
import gzip
import json
import unittest
from pathlib import Path

from scrape.history import HISTORY_FIELDS
from scrape.site_data import (
    booking_url,
    build_document,
    cheaper,
    israel_label,
    mark_finished,
    mark_running,
    write_document,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "output" / "history" / "runs"


def _write_run(directory: Path, name: str, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _row(**overrides) -> dict:
    base = {
        "scraped_at": "2026-10-26T07:17:55.741993Z",
        "check_in": "2026-12-15",
        "nights": "2",
        "rooms": "1",
        "board": "RO",
        "status": "available",
        "total_price": "1579.16",
        "price_per_night": "789.58",
        "room_type": "סוויטה דלקס",
        "party": "2a3c",
        "promo": "none",
    }
    base.update(overrides)
    return base


class BookingTests(unittest.TestCase):
    def test_tie_stays_on_the_regular_price_and_omits_the_code(self):
        chosen = cheaper(100.0, 100.0)
        self.assertEqual(chosen, (False, 100.0))
        url = booking_url("2026-12-15", 2, 1, "2a3c", use_mhot=False)
        self.assertEqual(
            url,
            "https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1"
            "&in=2026-12-15&out=2026-12-17&rooms=1&ad1=2&ch1=3&inf1=0",
        )
        self.assertNotIn("promocode", url)

    def test_mhot_wins_only_when_it_is_strictly_cheaper(self):
        self.assertEqual(cheaper(200.0, 150.0), (True, 150.0))
        self.assertEqual(cheaper(None, 150.0), (True, 150.0))
        self.assertIsNone(cheaper(None, None))
        url = booking_url("2027-01-09", 2, 2, "4a1c", use_mhot=True)
        self.assertIn("&ad1=1&ch1=1&inf1=0&ad2=3&ch2=0&inf2=0", url)
        self.assertTrue(url.endswith("&promocode=mhot"))

    def test_israel_label_is_winter_local_time(self):
        # 28 Oct 2026 is after the clock change, so 06:56 UTC is 08:56 in Israel.
        self.assertEqual(israel_label("2026-10-28T06:56:06.202971Z"), "28/10 08:56")


class BuildTests(unittest.TestCase):
    def test_series_keeps_unavailable_and_skips_dates_outside_a_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "output" / "history" / "runs"
            _write_run(runs, "2026-10-26T071755.741993Z.csv.gz", [
                _row(),
                _row(check_in="2026-12-16", status="unavailable", total_price="", price_per_night="", room_type=""),
            ])
            _write_run(runs, "2026-10-28T065606.202971Z.csv.gz", [
                _row(scraped_at="2026-10-28T06:56:06.202971Z", total_price="1600.00", price_per_night="800.00"),
            ])
            _write_run(runs, "2026-10-28T075151.466994Z-mhot.csv.gz", [
                _row(
                    scraped_at="2026-10-28T07:51:51.466994Z",
                    promo="mhot",
                    total_price="1500.00",
                    price_per_night="750.00",
                    room_type="סוויטה ג'וניור",
                ),
            ])
            document = build_document(root)
            offer = document["offers"]["2a3c|2|RO|1"]
            self.assertEqual(len(offer), 1)
            self.assertEqual(offer[0]["date"], "2026-12-15")
            self.assertTrue(offer[0]["use_mhot"])
            self.assertEqual(offer[0]["total"], 1500.0)
            self.assertTrue(offer[0]["url"].endswith("&promocode=mhot"))
            series = document["history"]["2a3c|2|RO|1"]["2026-12-15"]["none"]
            self.assertEqual([point["price"] for point in series], [1579.16, 1600.0])
            self.assertEqual(series[-1]["label"], "28/10 08:56")
            # 16 Dec was unavailable on the 26th and absent on the 28th: one gap point, not a current offer.
            gap = document["history"]["2a3c|2|RO|1"]["2026-12-16"]["none"]
            self.assertEqual(gap, [{
                "at": "2026-10-26T07:17:55.741993Z",
                "label": "26/10 09:17",
                "price": None,
            }])
            self.assertNotIn("2026-12-16", {row["date"] for row in offer})

    def test_current_results_json_extends_history_without_duplicating_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "output" / "history" / "runs"
            _write_run(runs, "2026-10-28T065606.202971Z.csv.gz", [
                _row(scraped_at="2026-10-28T06:56:06.202971Z"),
            ])
            results = root / "output" / "eilat" / "promo-mhot"
            results.mkdir(parents=True)
            (results / "results.json").write_text(json.dumps({
                "generated_at": "2026-10-29T10:00:00+00:00",
                "party": "2a3c",
                "promo": "mhot",
                "results": [_row(
                    scraped_at="2026-10-29T10:00:00Z",
                    promo="mhot",
                    total_price="1400.00",
                    price_per_night="700.00",
                )],
            }), encoding="utf-8")
            # Same timestamp as the history file: must not create a second point.
            (root / "output" / "eilat" / "results.json").parent.mkdir(parents=True, exist_ok=True)
            (root / "output" / "eilat" / "results.json").write_text(json.dumps({
                "generated_at": "2026-10-28T06:56:06.202971+00:00",
                "party": "2a3c",
                "promo": "none",
                "results": [_row(scraped_at="2026-10-28T06:56:06.202971Z", total_price="9999.00")],
            }), encoding="utf-8")
            document = build_document(root)
            none_points = document["history"]["2a3c|2|RO|1"]["2026-12-15"]["none"]
            self.assertEqual(len(none_points), 1)
            self.assertEqual(none_points[0]["price"], 1579.16)
            mhot_points = document["history"]["2a3c|2|RO|1"]["2026-12-15"]["mhot"]
            self.assertEqual(mhot_points[-1]["price"], 1400.0)
            self.assertEqual(document["offers"]["2a3c|2|RO|1"][0]["use_mhot"], True)

    def test_status_running_then_failed_keeps_the_reason(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "output" / "status.json"
            mark_running(status, started_at="2026-10-29T08:00:14Z", grids=["2a3c", "2a3c-mhot"], note="ידני")
            running = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual(running["run_state"], "running")
            self.assertEqual(running["grids"]["2a3c"]["state"], "running")
            self.assertEqual(running["grids"]["4a1c"]["state"], "done")
            mark_finished(
                status,
                finished_at="2026-10-29T09:10:00Z",
                grids=["2a3c", "2a3c-mhot"],
                failed={"2a3c-mhot": "HTTP 403 from the booking page"},
                started_at="2026-10-29T08:00:14Z",
            )
            done = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual(done["run_state"], "failed")
            self.assertIn("HTTP 403", done["error"])
            self.assertEqual(done["grids"]["2a3c"]["state"], "done")
            self.assertEqual(done["grids"]["2a3c-mhot"]["state"], "failed")
            self.assertEqual(done["grids"]["4a1c"]["state"], "done")
            _write_run(root / "output" / "history" / "runs", "2026-10-28T065606.202971Z.csv.gz", [
                _row(scraped_at="2026-10-28T06:56:06.202971Z"),
            ])
            document = build_document(root)
            self.assertEqual(document["status"]["run_state"], "failed")
            self.assertIn("HTTP 403", document["status"]["error"])
            self.assertEqual(document["status"]["grids"]["2a3c"]["last_scan_label"], "28/10 08:56")


class SeedHistoryTests(unittest.TestCase):
    def test_committed_oct_26_to_28_snapshots_survive_into_the_page(self):
        self.assertTrue(HISTORY.is_dir(), "history seed is missing from the repo")
        names = sorted(path.name for path in HISTORY.glob("*.csv.gz"))
        for expected in (
            "2026-10-26T071755.741993Z.csv.gz",
            "2026-10-26T150422.228713Z-4a1c.csv.gz",
            "2026-10-26T161414.805063Z-4a1c-mhot.csv.gz",
            "2026-10-26T170623.969737Z-mhot.csv.gz",
            "2026-10-27T064106.799861Z.csv.gz",
            "2026-10-28T065606.202971Z.csv.gz",
            "2026-10-28T075151.466994Z-mhot.csv.gz",
            "2026-10-28T091233.531226Z-4a1c.csv.gz",
            "2026-10-28T114822.250961Z-4a1c-mhot.csv.gz",
        ):
            self.assertIn(expected, names)
        document = build_document(ROOT)
        series = document["history"]["2a3c|2|RO|1"]["2026-12-15"]["none"]
        self.assertGreaterEqual(len(series), 3)
        seeded = next(point for point in series if point["at"].startswith("2026-10-28T06:56:06"))
        self.assertEqual(seeded["price"], 1579.16)
        self.assertEqual(seeded["label"], "28/10 08:56")
        self.assertTrue(any(point["label"].startswith("26/10") for point in series))
        # Later scrapes append snapshots; the page's "last scan" is the newest one, not a frozen date.
        self.assertGreaterEqual(document["status"]["grids"]["2a3c"]["last_scan_at"], "2026-10-28T06:56:06.202971Z")
        self.assertGreaterEqual(document["status"]["grids"]["4a1c-mhot"]["last_scan_at"], "2026-10-28T11:48:22.250961Z")


class WriteTests(unittest.TestCase):
    def test_write_document_is_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run(root / "output" / "history" / "runs", "2026-10-28T065606.202971Z.csv.gz", [
                _row(scraped_at="2026-10-28T06:56:06.202971Z"),
            ])
            dest = root / "site" / "data.json"
            write_document(root, dest)
            loaded = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(loaded["window"]["first"], "2026-12-15")
            self.assertEqual(loaded["months"][0]["name"], "דצמבר 2026")


if __name__ == "__main__":
    unittest.main()
