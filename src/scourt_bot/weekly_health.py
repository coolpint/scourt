from __future__ import annotations

import argparse
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests
from zoneinfo import ZoneInfo

from .config import Settings

API_BASE = "https://api.github.com"
SUMMARY_RE = re.compile(
    r"실행 완료: scanned=(?P<scanned>\d+) processed=(?P<processed>\d+) "
    r"sent=(?P<sent>\d+) skipped=(?P<skipped>\d+) failed=(?P<failed>\d+)"
)


@dataclass
class RunMetrics:
    run_id: int
    run_number: int
    event: str
    conclusion: str | None
    created_at: datetime
    html_url: str
    scanned: int | None = None
    processed: int | None = None
    sent: int | None = None
    skipped: int | None = None
    failed: int | None = None
    log_found: bool = False


class WeeklyHealthReporter:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: str,
        workflow_ref: str,
        github_token: str,
        webhook_url: str | None,
    ):
        self.settings = settings
        self.repository = repository
        self.workflow_ref = workflow_ref
        self.github_token = github_token
        self.webhook_url = webhook_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "scourt-weekly-health/0.1",
            }
        )
        self.kst = ZoneInfo(self.settings.timezone)

    def fetch_report(self) -> dict[str, Any]:
        now_kst = datetime.now(self.kst)
        since_kst = now_kst - timedelta(days=7)
        since_utc = since_kst.astimezone(timezone.utc)

        runs = self._fetch_runs()
        recent_runs = [
            run
            for run in runs
            if self._parse_utc(run["created_at"]) >= since_utc
        ]
        schedule_runs = [run for run in recent_runs if run.get("event") == "schedule"]
        manual_runs = [run for run in recent_runs if run.get("event") != "schedule"]

        expected_schedule_runs = self._expected_run_count(since_kst, now_kst)
        metrics = [self._collect_run_metrics(run) for run in schedule_runs]

        workflow_failures = [item for item in metrics if item.conclusion != "success"]
        bot_failures = [item for item in metrics if (item.failed or 0) > 0]
        missing_logs = [item for item in metrics if not item.log_found]
        total_sent = sum(item.sent or 0 for item in metrics)
        parsed_metrics = [item for item in metrics if item.log_found]

        issues: list[str] = []
        if len(schedule_runs) != expected_schedule_runs:
            issues.append(
                f"정기 실행 수가 예상 {expected_schedule_runs}회 대비 실제 {len(schedule_runs)}회입니다."
            )
        for item in workflow_failures[:5]:
            issues.append(
                f"워크플로 실패: run #{item.run_number} ({self._fmt_kst(item.created_at)})"
            )
        for item in bot_failures[:5]:
            issues.append(
                f"봇 처리 오류: run #{item.run_number} 에서 failed={item.failed}"
            )
        for item in missing_logs[:5]:
            issues.append(
                f"로그 미확인: run #{item.run_number} ({self._fmt_kst(item.created_at)})"
            )

        latest_success = next(
            (item for item in metrics if item.conclusion == "success"),
            None,
        )
        healthy = not issues

        return {
            "healthy": healthy,
            "issues": issues,
            "window_start": since_kst,
            "window_end": now_kst,
            "expected_schedule_runs": expected_schedule_runs,
            "actual_schedule_runs": len(schedule_runs),
            "manual_runs": len(manual_runs),
            "successful_runs": len([item for item in metrics if item.conclusion == "success"]),
            "failed_runs": len(workflow_failures),
            "parsed_logs": len(parsed_metrics),
            "bot_failed_runs": len(bot_failures),
            "total_sent": total_sent,
            "latest_success": latest_success,
            "workflow_url": f"https://github.com/{self.repository}/actions/workflows/"
            f"{os.path.basename(self.workflow_ref)}",
        }

    def send_report(self, report: dict[str, Any], *, dry_run: bool) -> None:
        title = (
            "대법원 봇 주간 점검: 정상 작동중"
            if report["healthy"]
            else "대법원 봇 주간 점검: 점검 필요"
        )
        body = self._format_body(report)
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": "2E7D32" if report["healthy"] else "C62828",
            "title": title,
            "sections": [
                {
                    "activityTitle": f"**{title}**",
                    "text": body,
                    "markdown": True,
                }
            ],
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name": "워크플로 보기",
                    "targets": [{"os": "default", "uri": report["workflow_url"]}],
                }
            ],
        }

        latest_success = report.get("latest_success")
        if latest_success is not None:
            payload["potentialAction"].append(
                {
                    "@type": "OpenUri",
                    "name": "최근 정상 실행 보기",
                    "targets": [{"os": "default", "uri": latest_success.html_url}],
                }
            )

        if dry_run or not self.webhook_url:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        response = requests.post(self.webhook_url, json=payload, timeout=20)
        response.raise_for_status()

    def _fetch_runs(self) -> list[dict[str, Any]]:
        workflow_ref = quote(self.workflow_ref, safe="")
        url = (
            f"{API_BASE}/repos/{self.repository}/actions/workflows/"
            f"{workflow_ref}/runs?per_page=100"
        )
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data.get("workflow_runs", [])

    def _collect_run_metrics(self, run: dict[str, Any]) -> RunMetrics:
        item = RunMetrics(
            run_id=int(run["id"]),
            run_number=int(run["run_number"]),
            event=run.get("event", ""),
            conclusion=run.get("conclusion"),
            created_at=self._parse_utc(run["created_at"]),
            html_url=run["html_url"],
        )

        artifact = self._find_log_artifact(item.run_id)
        if artifact is None:
            return item

        log_text = self._download_run_log(artifact["archive_download_url"])
        if not log_text:
            return item

        item.log_found = True
        match = SUMMARY_RE.search(log_text)
        if not match:
            return item

        item.scanned = int(match.group("scanned"))
        item.processed = int(match.group("processed"))
        item.sent = int(match.group("sent"))
        item.skipped = int(match.group("skipped"))
        item.failed = int(match.group("failed"))
        return item

    def _find_log_artifact(self, run_id: int) -> dict[str, Any] | None:
        url = f"{API_BASE}/repos/{self.repository}/actions/runs/{run_id}/artifacts"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        artifacts = response.json().get("artifacts", [])
        target_prefix = f"scourt-bot-logs-{run_id}"
        for artifact in artifacts:
            if artifact.get("name") == target_prefix:
                return artifact
        return None

    def _download_run_log(self, archive_url: str) -> str:
        response = self.session.get(archive_url, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                if name.endswith("run.log"):
                    return archive.read(name).decode("utf-8", errors="replace")
        return ""

    def _expected_run_count(self, start_kst: datetime, end_kst: datetime) -> int:
        count = 0
        current_date = start_kst.date()
        while current_date <= end_kst.date():
            for hour in self.settings.schedule_hours:
                slot = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    hour,
                    0,
                    tzinfo=self.kst,
                )
                if start_kst < slot <= end_kst:
                    count += 1
            current_date += timedelta(days=1)
        return count

    def _format_body(self, report: dict[str, Any]) -> str:
        lines = [
            f"기간: {self._fmt_kst(report['window_start'])} ~ {self._fmt_kst(report['window_end'])}",
            f"정기 실행: 예상 {report['expected_schedule_runs']}회 / 확인 {report['actual_schedule_runs']}회",
            f"워크플로 성공: {report['successful_runs']}회 / 실패: {report['failed_runs']}회",
            f"로그 확인: {report['parsed_logs']}회 / 봇 처리 오류 포함 실행: {report['bot_failed_runs']}회",
            f"지난 1주 기사 전송 수: {report['total_sent']}건",
            f"수동 실행 수: {report['manual_runs']}회",
        ]

        latest_success = report.get("latest_success")
        if latest_success is not None:
            lines.append(f"최근 정상 실행: {self._fmt_kst(latest_success.created_at)}")

        if report["healthy"]:
            lines.append("판정: 정상 작동중입니다.")
        else:
            lines.append("판정: 점검이 필요합니다.")
            lines.append("이상 징후:")
            for issue in report["issues"][:6]:
                lines.append(f"- {issue}")

        return "\n".join(lines)

    def _fmt_kst(self, dt: datetime) -> str:
        return dt.astimezone(self.kst).strftime("%Y-%m-%d %H:%M KST")

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scourt-weekly-health",
        description="Inspect weekly GitHub Actions health and send a Teams report.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print Teams payload instead of sending")
    parser.add_argument(
        "--workflow-ref",
        default=os.getenv("SCOURT_MONITORED_WORKFLOW", ".github/workflows/scourt-news-bot.yml"),
        help="Workflow path or ID to inspect",
    )
    parser.add_argument(
        "--repository",
        default=os.getenv("GITHUB_REPOSITORY", "coolpint/scourt"),
        help="GitHub repository in owner/repo form",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = Settings.load()
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise SystemExit("GITHUB_TOKEN is required")

    reporter = WeeklyHealthReporter(
        settings=settings,
        repository=args.repository,
        workflow_ref=args.workflow_ref,
        github_token=github_token,
        webhook_url=settings.teams_webhook_url,
    )
    report = reporter.fetch_report()
    reporter.send_report(report, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
