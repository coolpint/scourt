from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scourt_bot.models import ArticleDraft
from scourt_bot.teams import TeamsNotifier


class TeamsTests(unittest.TestCase):
    def test_teams_notifier_is_disabled(self):
        article = ArticleDraft(
            headline="테스트",
            body="본문",
            posted_date="2026-07-09",
            detail_url="https://example.test/detail",
            pdf_url=None,
            collected_at="2026-07-09 00:00:00",
        )

        with self.assertRaisesRegex(RuntimeError, "비활성화"):
            TeamsNotifier("https://example.test/webhook").send(article)


if __name__ == "__main__":
    unittest.main()
