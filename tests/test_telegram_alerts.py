"""Holiday price-drop detection, the Hebrew Telegram summary, and the quiet skip."""

import contextlib
import csv
import gzip
import io
import json
import os
import unittest
from pathlib import Path

from scrape.history import HISTORY_FIELDS, run_filename
from scrape.telegram_alerts import (
    SITE_URL,
    TELEGRAM_LIMIT,
    Drop,
    find_drops,
    format_message,
    main,
    notify,
    send_message,
)

OLD = "2026-11-01T05:17:00Z"
NEW = "2026-11-14T05:17:00Z"


def _write_run(directory: Path, scraped_at: str, party: str, promo: str, prices: list) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / run_filename(scraped_at, party=party, promo=promo)
    rows = []
    for item in prices:
        check_in, total = item[0], item[1]
        status = item[2] if len(item) > 2 else "available"
        nights = item[3] if len(item) > 3 else 2
        rooms = item[4] if len(item) > 4 else 1
        board = item[5] if len(item) > 5 else "RO"
        amount = "" if total is None else f"{float(total):.2f}"
        per_night = "" if total is None else f"{float(total) / nights:.2f}"
        rows.append({
            "scraped_at": scraped_at,
            "check_in": check_in,
            "nights": str(nights),
            "rooms": str(rooms),
            "board": board,
            "status": status,
            "total_price": amount,
            "price_per_night": per_night,
            "room_type": "" if total is None else "סוויטה",
            "party": party,
            "promo": promo,
        })
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _repo(root: Path) -> None:
    runs = root / "output" / "history" / "runs"
    _write_run(runs, OLD, "2a3c", "none", [
        ("2026-12-05", 2650),  # חנוכה, minor
        ("2026-12-12", 1000),  # חנוכה, rises
        ("2026-12-15", 1000),  # ordinary day, drops
        ("2027-04-21", None, "unavailable"),  # ערב פסח, was unavailable
        ("2027-04-23", 2100),  # חוה״מ פסח, chol
        ("2027-06-11", 2000.40),  # שבועות, same displayed shekel
        ("2026-12-06", 1800),  # left the latest scan
    ])
    _write_run(runs, NEW, "2a3c", "none", [
        ("2026-12-05", 2530),
        ("2026-12-12", 1100),
        ("2026-12-15", 800),
        ("2027-04-21", 900),
        ("2027-04-23", 2000),
        ("2027-06-11", 2000.20),
        ("2027-06-10", 1400),  # ערב שבועות, no previous price
    ])
    _write_run(runs, OLD, "2a3c", "mhot", [("2026-12-04", 1800)])  # ערב חנוכה
    _write_run(runs, NEW, "2a3c", "mhot", [("2026-12-04", 1500)])
    _write_run(runs, OLD, "4a1c", "none", [
        ("2027-04-22", 3000, "available", 2),  # פסח
        ("2027-04-22", 5200, "available", 4),
    ])
    _write_run(runs, NEW, "4a1c", "none", [
        ("2027-04-22", 2700, "available", 2),
        ("2027-04-22", 5000, "available", 4),
    ])
    _write_run(runs, OLD, "4a1c", "mhot", [("2027-05-12", 4000)])  # יום העצמאות
    _write_run(runs, NEW, "4a1c", "mhot", [("2027-05-12", 3600)])


class DropDetectionTests(unittest.TestCase):
    def test_every_marked_holiday_kind_and_nothing_else(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            drops = find_drops(root, ["2a3c", "2a3c-mhot", "4a1c", "4a1c-mhot"])
        by_date = {item.check_in: item for item in drops}
        self.assertEqual(
            set(by_date),
            {"2026-12-04", "2026-12-05", "2027-04-22", "2027-04-23", "2027-05-12"},
        )
        self.assertEqual(
            {item.holiday_kind for item in drops},
            {"erev", "minor", "chag", "chol", "modern"},
        )
        self.assertEqual(by_date["2026-12-05"].holiday_name, "חנוכה")
        self.assertEqual(by_date["2026-12-04"].promo, "mhot")
        self.assertEqual(by_date["2027-04-23"].holiday_name, "חוה״מ פסח")
        self.assertEqual(by_date["2027-05-12"].holiday_name, "יום העצמאות")
        # The cheaper 2-night stay, not the 4-night cell.
        pesach = by_date["2027-04-22"]
        self.assertEqual((pesach.nights, pesach.rooms, pesach.old, pesach.new), (2, 1, 3000.0, 2700.0))
        text = format_message(drops)
        self.assertIn("ירידה של 120 ₪, 4.5%", text)
        self.assertIn("ירידה של 300 ₪, 16.7%", text)
        self.assertIn("04/12/2026, ערב חנוכה, 2 מבוגרים + 3 ילדים, עם קוד mhot", text)
        self.assertIn("05/12/2026, חנוכה, 2 מבוגרים + 3 ילדים, בלי קוד: 2,650 ₪ → 2,530 ₪", text)
        self.assertIn("22/04/2027, פסח, 4 מבוגרים + ילד, בלי קוד", text)
        self.assertNotIn("12/12/2026", text)
        self.assertNotIn("15/12/2026", text)
        self.assertNotIn("21/04/2027", text)
        self.assertNotIn("11/06/2027", text)
        self.assertNotIn("10/06/2027", text)
        self.assertIn("להזמנה באתר מועדון הוטלס – 1,500 ₪ (עם mhot)", text)
        self.assertIn(
            "https://m.clubhotels.co.il/BE_Rooms.aspx?lang=heb&hotel=1_1"
            "&in=2026-12-04&out=2026-12-06&rooms=1&ad1=2&ch1=3&inf1=0&promocode=mhot",
            text,
        )
        self.assertIn(SITE_URL, text)
        self.assertEqual(text.count("להזמנה באתר מועדון הוטלס"), 1)

    def test_only_grids_published_in_this_run_are_compared(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            drops = find_drops(root, ["4a1c"])
        self.assertEqual([item.check_in for item in drops], ["2027-04-22"])

    def test_a_single_snapshot_is_not_a_drop(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run(root / "output" / "history" / "runs", NEW, "2a3c", "none", [("2026-12-05", 1000)])
            self.assertEqual(find_drops(root, ["2a3c"]), [])


class FormatTests(unittest.TestCase):
    def test_tie_on_the_new_price_keeps_the_regular_booking_link(self):
        regular = Drop("2027-04-22", "פסח", "chag", "2a3c", "none", 2000, 1500, 3, 1)
        coded = Drop("2026-12-05", "חנוכה", "minor", "2a3c", "mhot", 2000, 1500, 2, 1)
        text = format_message([coded, regular])
        self.assertIn("להזמנה באתר מועדון הוטלס – 1,500 ₪ (מחיר רגיל)", text)
        self.assertIn("&in=2027-04-22&out=2027-04-25", text)
        self.assertNotIn("promocode", text)

    def test_message_stays_inside_the_telegram_limit(self):
        drops = [
            Drop(
                f"2027-{(index // 28) + 1:02d}-{(index % 28) + 1:02d}",
                "חנוכה " * 6,
                "minor",
                "2a3c",
                "none",
                5000,
                1000,
                2,
                1,
            )
            for index in range(80)
        ]
        text = format_message(drops)
        self.assertLessEqual(len(text), TELEGRAM_LIMIT)
        self.assertIn("שלא נכנסו להודעה", text)
        self.assertIn(SITE_URL, text)


class NotifyTests(unittest.TestCase):
    def test_cli_without_secrets_exits_zero(self):
        saved = {name: os.environ.pop(name, None) for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--root", ".", "--grids", "2a3c"]), 0)
        finally:
            for name, value in saved.items():
                if value is not None:
                    os.environ[name] = value

    def test_missing_secrets_do_not_send(self):
        calls = []

        def send(token, chat_id, text):
            calls.append((token, chat_id, text))

        for token, chat_id in (("", "123"), ("secret", ""), ("  ", "123"), ("secret", "  ")):
            with self.subTest(token=token, chat_id=chat_id):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = notify(Path("."), ["2a3c"], token=token, chat_id=chat_id, send=send)
                self.assertEqual(code, 0)
                self.assertIn("not set", out.getvalue())
        self.assertEqual(calls, [])

    def test_no_drops_does_not_send(self):
        import tempfile
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run(root / "output" / "history" / "runs", OLD, "2a3c", "none", [("2026-12-05", 1000)])
            _write_run(root / "output" / "history" / "runs", NEW, "2a3c", "none", [("2026-12-05", 1200)])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = notify(root, ["2a3c"], token="secret", chat_id="-1001", send=lambda *args: calls.append(args))
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertIn("not sending", out.getvalue())

    def test_a_telegram_error_does_not_fail(self):
        import tempfile

        def send(token, chat_id, text):
            raise OSError(f"https://api.telegram.org/bot{token}/sendMessage timed out")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = notify(root, ["2a3c-mhot"], token="super-secret", chat_id="@club", send=send)
        self.assertEqual(code, 0)
        self.assertNotIn("super-secret", stderr.getvalue())
        self.assertIn("Telegram send failed", stderr.getvalue())

    def test_send_message_posts_the_chat_and_the_text(self):
        seen = {}

        class Response:
            status = 200

            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return Response()

        send_message("token", "@clubhotel", "שלום", opener=opener)
        self.assertEqual(seen["url"], "https://api.telegram.org/bottoken/sendMessage")
        self.assertEqual(seen["body"]["chat_id"], "@clubhotel")
        self.assertEqual(seen["body"]["text"], "שלום")
        self.assertTrue(seen["body"]["disable_web_page_preview"])
        self.assertEqual(seen["timeout"], 20)

    def test_rejected_payload_raises_without_the_token(self):
        class Response:
            status = 200

            def read(self):
                return b'{"ok": false, "description": "chat not found"}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with self.assertRaises(Exception) as caught:
            send_message("token", "-100", "שלום", opener=lambda request, timeout: Response())
        self.assertIn("chat not found", str(caught.exception))
        self.assertNotIn("token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
