from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scourt_bot import weekly_health


class WeeklyHealthTests(unittest.TestCase):
    def test_main_does_not_require_settings_teams_webhook_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "GITHUB_TOKEN": "dummy-token",
                "SCOURT_ROOT_DIR": temp_dir,
            }
            with patch.dict(os.environ, env, clear=False):
                with patch.object(
                    weekly_health.WeeklyHealthReporter,
                    "fetch_report",
                    return_value={"healthy": True},
                ):
                    with patch.object(
                        weekly_health.WeeklyHealthReporter,
                        "send_report",
                    ) as send_report:
                        self.assertEqual(weekly_health.main(["--dry-run"]), 0)
                        send_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
