from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scourt_bot import weekly_health
from scourt_bot.config import Settings
from scourt_bot.weekly_health import RunMetrics, WeeklyHealthReporter


class WeeklyHealthTests(unittest.TestCase):
    def _reporter(self) -> WeeklyHealthReporter:
        return WeeklyHealthReporter(
            settings=Settings.load(),
            repository="example/scourt",
            workflow_ref=".github/workflows/scourt-news-bot.yml",
            github_token=None,
            expect_schedule=False,
        )

    @staticmethod
    def _run(*, event: str, conclusion: str | None) -> dict[str, str | int | None]:
        return {
            "id": 1,
            "run_number": 17,
            "event": event,
            "conclusion": conclusion,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "html_url": "https://example.test/runs/17",
        }

    def test_main_prints_report_without_teams_webhook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
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
                        "print_report",
                    ) as print_report:
                        self.assertEqual(weekly_health.main(["--json"]), 0)
                        print_report.assert_called_once()

    def test_manual_workflow_failure_requires_attention(self):
        reporter = self._reporter()
        with patch.object(
            reporter,
            "_fetch_runs",
            return_value=[self._run(event="workflow_dispatch", conclusion="failure")],
        ):
            report = reporter.fetch_report()

        self.assertFalse(report["healthy"])
        self.assertEqual(report["manual_runs"], 1)
        self.assertEqual(report["failed_runs"], 1)
        self.assertIn("워크플로 실패", report["issues"][0])

    def test_no_recent_workflow_runs_requires_attention(self):
        reporter = self._reporter()
        with patch.object(reporter, "_fetch_runs", return_value=[]):
            report = reporter.fetch_report()

        self.assertFalse(report["healthy"])
        self.assertIn("최근 1주간", report["issues"][0])

    def test_schedule_workflow_failure_requires_attention(self):
        reporter = self._reporter()
        with patch.object(
            reporter,
            "_fetch_runs",
            return_value=[self._run(event="schedule", conclusion="failure")],
        ):
            report = reporter.fetch_report()

        self.assertFalse(report["healthy"])
        self.assertEqual(report["failed_runs"], 1)

    def test_in_progress_workflow_is_not_reported_as_failed(self):
        reporter = self._reporter()
        with patch.object(
            reporter,
            "_fetch_runs",
            return_value=[self._run(event="workflow_dispatch", conclusion=None)],
        ):
            report = reporter.fetch_report()

        self.assertTrue(report["healthy"])
        self.assertEqual(report["failed_runs"], 0)
        self.assertEqual(report["in_progress_runs"], 1)

    def test_fetch_runs_follows_pagination_links(self):
        class Response:
            def __init__(self, run_id: int, next_url: str | None):
                self.run_id = run_id
                self.links = {"next": {"url": next_url}} if next_url else {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"workflow_runs": [{"id": self.run_id}]}

        reporter = self._reporter()
        first = Response(1, "https://example.test/page-2")
        second = Response(2, None)
        with patch.object(reporter.session, "get", side_effect=[first, second]) as get:
            runs = reporter._fetch_runs()

        self.assertEqual([run["id"] for run in runs], [1, 2])
        self.assertEqual(get.call_count, 2)

    def test_print_report_writes_text_and_json_without_webhook(self):
        reporter = self._reporter()
        now = datetime.now(timezone.utc)
        report = {
            "healthy": True,
            "issues": [],
            "window_start": now,
            "window_end": now,
            "expected_schedule_runs": None,
            "actual_schedule_runs": 0,
            "manual_runs": 1,
            "successful_runs": 1,
            "failed_runs": 0,
            "in_progress_runs": 0,
            "parsed_logs": 0,
            "bot_failed_runs": 0,
            "total_sent": 0,
            "latest_success": RunMetrics(
                run_id=1,
                run_number=17,
                event="workflow_dispatch",
                conclusion="success",
                created_at=now,
                html_url="https://example.test/runs/17",
            ),
            "workflow_url": "https://example.test/workflows/scourt-news-bot.yml",
        }

        text_output = io.StringIO()
        with contextlib.redirect_stdout(text_output):
            reporter.print_report(report, as_json=False)
        self.assertIn("정상 작동중", text_output.getvalue())
        self.assertIn("최근 정상 실행 URL", text_output.getvalue())

        json_output = io.StringIO()
        with contextlib.redirect_stdout(json_output):
            reporter.print_report(report, as_json=True)
        printed = json.loads(json_output.getvalue())
        self.assertTrue(printed["healthy"])
        self.assertEqual(printed["latest_success"]["run_number"], 17)


if __name__ == "__main__":
    unittest.main()
