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


def _as_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError("SCOURT_INITIAL_LAST_SEEN_NOTICE_ID must be an integer")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
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
    return tuple(sorted(set(hours))) or (0, 3, 6, 9, 12, 15, 18, 21)


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
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    auto_writer_dir: Path | None
    auto_writer_mode: str
    user_agent: str
    bootstrap_skip_send: bool
    initial_last_seen_notice_id: int | None
    news_search_enabled: bool
    news_search_query_limit: int
    news_search_result_limit: int
    news_search_timeout_seconds: int

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
        auto_writer_dir_raw = os.getenv("AUTO_WRITER_PROJECT_DIR")
        auto_writer_dir = Path(auto_writer_dir_raw).expanduser().resolve() if auto_writer_dir_raw else None

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
            schedule_hours=_as_hours(os.getenv("SCOURT_SCHEDULE_HOURS", "0,3,6,9,12,15,18,21")),
            db_path=db_path,
            pdf_dir=pdf_dir,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
            auto_writer_dir=auto_writer_dir,
            auto_writer_mode=os.getenv("AUTO_WRITER_MODE", "live"),
            user_agent=os.getenv(
                "SCOURT_USER_AGENT",
                "scourt-news-bot/0.1 (+https://www.scourt.go.kr)",
            ),
            bootstrap_skip_send=_as_bool(
                os.getenv("SCOURT_BOOTSTRAP_SKIP_SEND"),
                True,
            ),
            initial_last_seen_notice_id=_as_optional_int(
                os.getenv("SCOURT_INITIAL_LAST_SEEN_NOTICE_ID")
            ),
            news_search_enabled=_as_bool(
                os.getenv("SCOURT_NEWS_SEARCH_ENABLED"),
                True,
            ),
            news_search_query_limit=max(
                1, _as_int(os.getenv("SCOURT_NEWS_SEARCH_QUERY_LIMIT", "3"), 3)
            ),
            news_search_result_limit=max(
                1, _as_int(os.getenv("SCOURT_NEWS_SEARCH_RESULT_LIMIT", "8"), 8)
            ),
            news_search_timeout_seconds=max(
                3, _as_int(os.getenv("SCOURT_NEWS_SEARCH_TIMEOUT_SECONDS", "8"), 8)
            ),
        )
