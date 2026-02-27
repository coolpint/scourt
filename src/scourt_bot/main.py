from __future__ import annotations

import argparse
import logging
import sys
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import Settings
from .pipeline import ScourtPipeline


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _run_job(
    pipeline: ScourtPipeline,
    *,
    force: bool,
    dry_run: bool,
    max_pages: int | None,
) -> None:
    logger = logging.getLogger(__name__)
    stats = pipeline.run_once(force=force, dry_run=dry_run, max_pages=max_pages)
    logger.info(
        "실행 완료: scanned=%s processed=%s sent=%s skipped=%s failed=%s",
        stats.scanned,
        stats.processed,
        stats.sent,
        stats.skipped,
        stats.failed,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scourt-bot",
        description="대법원 보도자료 수집/기사 생성/Teams 전송 봇",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="즉시 1회 실행")
    run_parser.add_argument("--dry-run", action="store_true", help="Teams 전송 없이 실행")
    run_parser.add_argument("--force", action="store_true", help="기존 전송 건도 재전송")
    run_parser.add_argument("--max-pages", type=int, default=None, help="수집 페이지 수")

    schedule_parser = subparsers.add_parser("schedule", help="10시/18시 스케줄 실행")
    schedule_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="스케줄 실행 시 Teams 전송 없이 실행",
    )
    schedule_parser.add_argument("--run-now", action="store_true", help="스케줄 등록 전 1회 즉시 실행")
    schedule_parser.add_argument("--max-pages", type=int, default=None, help="수집 페이지 수")

    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    settings = Settings.load()
    pipeline = ScourtPipeline(settings)

    if args.command == "run":
        _run_job(
            pipeline,
            force=args.force,
            dry_run=args.dry_run,
            max_pages=args.max_pages,
        )
        return 0

    scheduler = BlockingScheduler(timezone=ZoneInfo(settings.timezone))
    schedule_hours = ",".join(str(hour) for hour in settings.schedule_hours)
    scheduler.add_job(
        _run_job,
        trigger="cron",
        hour=schedule_hours,
        minute=0,
        kwargs={
            "pipeline": pipeline,
            "force": False,
            "dry_run": args.dry_run,
            "max_pages": args.max_pages,
        },
        id="scourt_news_job",
        replace_existing=True,
    )

    logging.getLogger(__name__).info(
        "스케줄러 시작: timezone=%s, hour=%s, minute=0",
        settings.timezone,
        schedule_hours,
    )

    if args.run_now:
        _run_job(
            pipeline,
            force=False,
            dry_run=args.dry_run,
            max_pages=args.max_pages,
        )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
