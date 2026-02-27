from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .article_writer import ArticleWriter
from .config import Settings
from .models import RunStats
from .pdf_service import PdfService
from .scourt_client import ScourtClient
from .storage import StateStore
from .teams import TeamsNotifier

LOGGER = logging.getLogger(__name__)


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ScourtPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ScourtClient(settings)
        self.pdf_service = PdfService(settings)
        self.store = StateStore(settings.db_path)
        self.writer = ArticleWriter(settings)
        self.notifier = (
            TeamsNotifier(settings.teams_webhook_url)
            if settings.teams_webhook_url
            else None
        )

    def run_once(
        self,
        *,
        force: bool = False,
        dry_run: bool = False,
        max_pages: int | None = None,
    ) -> RunStats:
        if not dry_run and self.notifier is None:
            raise ValueError("TEAMS_WEBHOOK_URL 이 설정되지 않았습니다.")

        pages = max_pages or self.settings.max_pages
        all_notices = []
        for page_index in range(1, pages + 1):
            notices = self.client.fetch_news_list(page_index=page_index)
            LOGGER.info("목록 수집: page=%s, count=%s", page_index, len(notices))
            all_notices.extend(notices)

        deduped = {}
        for notice in all_notices:
            deduped.setdefault(notice.notice_id, notice)

        ordered = sorted(
            deduped.values(),
            key=lambda x: (x.posted_date, int(x.notice_id)),
        )

        stats = RunStats(scanned=len(ordered))
        now_iso = datetime.now(ZoneInfo(self.settings.timezone)).isoformat()

        for summary in ordered:
            try:
                detail = self.client.fetch_notice_detail(summary)

                pdf_hash = ""
                pdf_text = ""
                if detail.pdf_url:
                    pdf_result = self.pdf_service.download_and_extract(
                        detail.pdf_url,
                        summary.notice_id,
                    )
                    pdf_hash = pdf_result.sha256
                    pdf_text = pdf_result.text
                else:
                    LOGGER.warning("첨부 PDF 없음: notice_id=%s", summary.notice_id)

                article = self.writer.build(summary, detail, pdf_text)
                article_text = article.as_text()
                content_hash = _hash_content(
                    "\n".join([detail.title, detail.body_text, pdf_hash])
                )
                prev = self.store.get_notice(summary.notice_id)

                unchanged = (
                    prev is not None
                    and prev.get("content_hash") == content_hash
                    and prev.get("sent_at")
                    and not force
                )
                if unchanged:
                    stats.skipped += 1
                    continue

                self.store.upsert_notice(
                    notice_id=summary.notice_id,
                    title=detail.title,
                    posted_date=summary.posted_date,
                    detail_url=summary.detail_url,
                    pdf_url=detail.pdf_url,
                    pdf_hash=pdf_hash or None,
                    content_hash=content_hash,
                    article_text=article_text,
                    timestamp_iso=now_iso,
                )
                stats.processed += 1

                if dry_run:
                    LOGGER.info("[DRY RUN] article generated: %s", detail.title)
                    continue

                assert self.notifier is not None
                self.notifier.send(article)
                self.store.mark_sent(summary.notice_id, now_iso)
                stats.sent += 1
                LOGGER.info("Teams 전송 완료: %s (%s)", summary.notice_id, detail.title)

            except Exception:
                stats.failed += 1
                LOGGER.exception("처리 실패: notice_id=%s", summary.notice_id)

        return stats
