"""A late scrape must deploy the site that is on main, not the queued commit.

Scheduled runs often start hours after GitHub queues them. The publish job
used to copy site/ from that queued SHA, so a run that had been waiting
could overwrite a newer page. The page, the status writer, and the Telegram
script now come from the main checkout. The artifact unpacker stays on the
queued commit, because that is the code that produced the artifacts.
"""

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "scrape.yml"


class PagesSourceTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_price_page_is_built_from_main(self):
        self.assertIn('cp -a "${GITHUB_WORKSPACE}/main/site/." "${GITHUB_WORKSPACE}/_site/"', self.text)
        self.assertNotIn("workflow-src/site", self.text)
        self.assertIn(
            'PYTHONPATH="${GITHUB_WORKSPACE}/main" python -m scrape.site_data build',
            self.text,
        )

    def test_status_and_telegram_use_main_code(self):
        self.assertIn(
            'PYTHONPATH="${GITHUB_WORKSPACE}/main" python -m scrape.site_data mark-running',
            self.text,
        )
        self.assertIn(
            'PYTHONPATH="${GITHUB_WORKSPACE}/main" python -m scrape.site_data mark-finished',
            self.text,
        )
        self.assertIn("PYTHONPATH: ${{ github.workspace }}/main", self.text)
        self.assertNotIn("workflow-src\" python -m scrape.site_data", self.text)
        self.assertNotIn("github.workspace }}/workflow-src", self.text)

    def test_artifact_unpacker_stays_on_the_queued_commit(self):
        self.assertIn(
            'script="${GITHUB_WORKSPACE}/workflow-src/.github/scripts/publish-grids.sh"',
            self.text,
        )
        self.assertLess(
            self.text.index("workflow-src/.github/scripts/publish-grids.sh"),
            self.text.index('"${GITHUB_WORKSPACE}/main/.github/scripts/publish-grids.sh"'),
        )


if __name__ == "__main__":
    unittest.main()
