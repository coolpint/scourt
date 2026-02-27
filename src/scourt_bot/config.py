from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_hours(value: str) -> tuple[int, ...]:
    raw = [v.strip() for v in value.split(",") if v.strip()]
    hours = []
    for token in raw:
        try:
            hour = int(token)
        except ValueError:
            continue
        if 0 <= hour <= 23:
            hours.append(hour)
    return tuple(sorted(set(hours))) or (10, 18)


@dataclass(frozen=True)
class Settings:
    list_url: str
    gubun: str
    max_pages: int
    timeout_seconds: int
    timezone: str
    schedule_hours: tuple[int, ...]
    db_path: Path
    pdf_dir: Path
    teams_webhook_url: str | None
    user_agent: str

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()

        root = Path(os.getenv("SCOURT_ROOT_DIR", str(Path.cwd()))).resolve()
        db_path = Path(os.getenv("SCOURT_DB_PATH", "data/scourt_news.db"))
        pdf_dir = Path(os.getenv("SCOURT_PDF_DIR", "data/pdfs"))
        if not db_path.is_absolute():
            db_path = root / db_path
        if not pdf_dir.is_absolute():
            pdf_dir = root / pdf_dir

        return cls(
            list_url=os.getenv(
                "SCOURT_LIST_URL",
                "https://www.scourt.go.kr/supreme/news/NewsListAction.work",
            ),
            gubun=os.getenv("SCOURT_GUBUN", "702"),
            max_pages=max(1, _as_int(os.getenv("SCOURT_MAX_PAGES", "2"), 2)),
            timeout_seconds=max(
                5, _as_int(os.getenv("SCOURT_TIMEOUT_SECONDS", "20"), 20)
            ),
            timezone=os.getenv("SCOURT_TIMEZONE", "Asia/Seoul"),
            schedule_hours=_as_hours(os.getenv("SCOURT_SCHEDULE_HOURS", "10,18")),
            db_path=db_path,
            pdf_dir=pdf_dir,
            teams_webhook_url=os.getenv("TEAMS_WEBHOOK_URL") or None,
            user_agent=os.getenv(
                "SCOURT_USER_AGENT",
                "scourt-news-bot/0.1 (+https://www.scourt.go.kr)",
            ),
        )
