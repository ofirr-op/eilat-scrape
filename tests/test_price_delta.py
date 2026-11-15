"""The day card compares each line with the lowest price ever recorded for that date."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "site" / "price_delta.js"


class PriceDeltaTests(unittest.TestCase):
    def setUp(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required to run site/price_delta.js")
        self.node = node

    def run_js(self, body: str):
        program = (
            "const d = require(process.argv[1]);\n"
            "const out = (function () {\n" + body + "\n})();\n"
            "process.stdout.write(JSON.stringify(out));\n"
        )
        result = subprocess.run(
            [self.node, "-e", program, str(SCRIPT)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_rise_from_the_lowest_is_shekels_and_percent(self):
        text = self.run_js(
            """
            return d.formatVersusLow([
              {at: "2026-10-28T06:56:06Z", label: "28/10 08:56", price: 2650},
              {at: "2026-11-14T05:17:00Z", label: "14/11 07:17", price: 2770},
            ]);
            """
        )
        self.assertEqual(
            text,
            "+₪120 (+4.5%) מהמחיר הנמוך ביותר (2,650 ₪, 28/10 08:56)",
        )

    def test_current_low_says_so_for_both_a_single_scan_and_a_return_to_the_low(self):
        single = self.run_js(
            """
            return d.formatVersusLow([
              {at: "2026-11-14T05:17:00Z", label: "14/11 07:17", price: 1579.16},
            ]);
            """
        )
        self.assertIn("המחיר הנמוך ביותר", single)
        self.assertIn("0 ₪, 0%", single)
        self.assertIn("1,579 ₪", single)
        self.assertIn("14/11 07:17", single)

        back = self.run_js(
            """
            return d.formatVersusLow([
              {at: "2026-10-28T06:56:06Z", label: "28/10 08:56", price: 1500},
              {at: "2026-11-01T05:17:00Z", label: "01/11 07:17", price: 1700},
              {at: "2026-11-14T05:17:00Z", label: "14/11 07:17", price: 1500},
            ]);
            """
        )
        self.assertIn("המחיר הנמוך ביותר", back)
        self.assertIn("0 ₪, 0%", back)
        self.assertIn("28/10 08:56", back)

    def test_tied_low_keeps_the_earlier_scan(self):
        text = self.run_js(
            """
            return d.formatVersusLow([
              {at: "2026-11-01T05:17:00Z", label: "01/11 07:17", price: 1500},
              {at: "2026-11-08T05:17:00Z", label: "08/11 07:17", price: 1500},
              {at: "2026-11-14T05:17:00Z", label: "14/11 07:17", price: 1600},
            ]);
            """
        )
        self.assertIn("01/11 07:17", text)
        self.assertNotIn("08/11 07:17", text)
        self.assertIn("+₪100", text)

    def test_unavailable_latest_scan_still_names_the_low(self):
        text = self.run_js(
            """
            return d.formatVersusLow([
              {at: "2026-10-28T06:56:06Z", label: "28/10 08:56", price: 1500},
              {at: "2026-11-14T05:17:00Z", label: "14/11 07:17", price: null},
            ]);
            """
        )
        self.assertIn("לא זמין", text)
        self.assertIn("1,500 ₪", text)
        self.assertIn("28/10 08:56", text)

    def test_arrow_is_up_above_the_low_and_flat_on_it(self):
        kinds = self.run_js(
            """
            return {
              up: d.versusLow([
                {at: "a", label: "01/11 07:17", price: 1000},
                {at: "b", label: "14/11 07:17", price: 1100},
              ]).kind,
              flat: d.versusLow([
                {at: "a", label: "01/11 07:17", price: 1000},
                {at: "b", label: "14/11 07:17", price: 1000},
              ]).kind,
            };
            """
        )
        self.assertEqual(kinds, {"up": "up", "flat": "flat"})


if __name__ == "__main__":
    unittest.main()
