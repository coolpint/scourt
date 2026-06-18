from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .article_writer import ArticleWriter
from .auto_writer import AutoWriterRunner
from .config import Settings
from .models import NoticeDetail, NoticeSummary, RunStats
from .news_research import NewsResearcher
from .pdf_service import PdfService
from .scourt_client import ScourtClient
from .storage import StateStore
from .telegram import TelegramNotifier

LOGGER = logging.getLogger(__name__)


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _notice_id_as_int(notice_id: str) -> int:
    try:
        return int(notice_id)
    except (TypeError, ValueError):
        return 0


def _build_auto_writer_source(
    summary: NoticeSummary,
    detail: NoticeDetail,
    pdf_text: str,
    briefing_text: str,
    related_news_text: str,
) -> str:
    pdf_section = pdf_text.strip() or "첨부 PDF 텍스트를 추출하지 못했습니다."
    return "\n".join(
        [
            "[대법원 보도자료 Auto-Writer 기사 작성 요청]",
            "",
            "목표:",
            "- 아래 대법원 보도자료를 바탕으로 머니앤로 CMS 미승인 기사 초안을 작성한다.",
            "- 단순히 대법원 보도자료만 보지 않는다. 보도자료가 익명화돼 있어도, 이미 오래 언론에서 다뤄진 사건이면 관련 보도 맥락을 반드시 확인해 반영한다.",
            "- 아래 '관련 언론 보도 검색'에 사건명·실명·사회적 맥락이 확인되면, 대법원 자료와 충돌하지 않는 범위에서 '언론 보도에 따르면' 식으로 기사에 자연스럽게 넣는다.",
            "- 예: '학폭 소송 노쇼 변호사' 사건은 대법원 자료상 익명이라도, 관련 보도를 통해 권경애 변호사 사건임을 확인해 배경으로 반영해야 한다.",
            "- 원문과 관련 보도에 없는 의미 부풀리기, 선정적 표현, 과장 표현은 피한다.",
            "- 중요한 법률 쟁점·사건번호·선고일·판결 결과·하급심 경과·당사자/혐의/청구 취지는 사실 체크리스트처럼 빠뜨리지 않는다.",
            "- 기사 말미에는 독자가 확인할 수 있는 원문 링크 정보를 자연스럽게 반영한다.",
            "",
            "AUTO_WRITER_IMAGE_STYLE: 밝은 흰 배경의 흑백 또는 제한색 펜 카툰 일러스트. 법원·판결문·펜·저울 같은 상징 오브제를 단순하게 구성. 사진, 포토리얼, 사진 콜라주, 3D 렌더링 금지. 텍스트·로고·워터마크 금지.",
            "",
            "보도자료 기본 정보:",
            f"- notice_id: {summary.notice_id}",
            f"- 제목: {detail.title}",
            f"- 게시일: {summary.posted_date}",
            f"- 상세 URL: {detail.detail_url}",
            f"- PDF URL: {detail.pdf_url or '첨부 PDF 없음'}",
            "",
            "기존 자동 요약 참고:",
            briefing_text,
            "",
            related_news_text.strip() or "관련 언론 보도 검색 결과 없음",
            "",
            "대법원 상세 페이지 본문:",
            detail.body_text.strip() or "본문 없음",
            "",
            "첨부 PDF 추출 텍스트:",
            pdf_section,
        ]
    )


class ScourtPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ScourtClient(settings)
        self.pdf_service = PdfService(settings)
        self.store = StateStore(settings.db_path)
        self.writer = ArticleWriter(settings)
        self.news_researcher = NewsResearcher(settings)
        self.auto_writer = AutoWriterRunner(settings) if settings.auto_writer_dir else None
        self.notifier = (
            TelegramNotifier(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )
            if settings.telegram_bot_token and settings.telegram_chat_id
            else None
        )

    def run_once(
        self,
        *,
        force: bool = False,
        dry_run: bool = False,
        max_pages: int | None = None,
    ) -> RunStats:
        if not dry_run and self.auto_writer is None:
            raise ValueError("AUTO_WRITER_PROJECT_DIR 이 설정되지 않았습니다.")

        pages = max_pages or self.settings.max_pages
        all_notices = []
        for page_index in range(1, pages + 1):
            notices = self.client.fetch_news_list(page_index=page_index)
            LOGGER.info("목록 수집: page=%s, count=%s", page_index, len(notices))
            if page_index == 1 and not notices:
                raise RuntimeError("첫 목록 페이지에서 공지를 찾지 못했습니다.")
            all_notices.extend(notices)

        deduped = {}
        for notice in all_notices:
            deduped.setdefault(notice.notice_id, notice)

        ordered = sorted(deduped.values(), key=lambda x: _notice_id_as_int(x.notice_id))

        stats = RunStats(scanned=len(ordered))
        now_iso = datetime.now(ZoneInfo(self.settings.timezone)).isoformat()
        last_seen_id = self.store.get_last_seen_notice_id()
        if (
            last_seen_id is None
            and not force
            and self.settings.initial_last_seen_notice_id is not None
        ):
            last_seen_id = self.settings.initial_last_seen_notice_id
            if not dry_run:
                self.store.set_last_seen_notice_id(last_seen_id, now_iso)
            LOGGER.info(
                "초기 워터마크 적용: last_seen_notice_id=%s",
                last_seen_id,
            )
        latest_seen_id = (
            _notice_id_as_int(ordered[-1].notice_id) if ordered else last_seen_id
        )

        if ordered and not force and last_seen_id is not None:
            LOGGER.info(
                "신규 판정 기준: last_seen_notice_id=%s, latest_notice_id=%s",
                last_seen_id,
                latest_seen_id,
            )

        if (
            ordered
            and not dry_run
            and not force
            and self.settings.bootstrap_skip_send
            and last_seen_id is None
        ):
            self.store.set_last_seen_notice_id(latest_seen_id, now_iso)
            stats.skipped = len(ordered)
            LOGGER.warning(
                "초기 기준선 모드: last_seen_notice_id=%s 로 설정하고 이번 실행 전송은 건너뜁니다.",
                latest_seen_id,
            )
            return stats

        if force or last_seen_id is None:
            targets = ordered
        else:
            targets = [
                notice
                for notice in ordered
                if _notice_id_as_int(notice.notice_id) > last_seen_id
            ]

        stats.skipped += max(0, len(ordered) - len(targets))
        if not force:
            LOGGER.info(
                "대상 건수: total=%s, new=%s, old=%s",
                len(ordered),
                len(targets),
                len(ordered) - len(targets),
            )

        for summary in targets:
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

                briefing = self.writer.build(summary, detail, pdf_text)
                related_news = self.news_researcher.collect(summary, detail, pdf_text)
                source_text = _build_auto_writer_source(
                    summary,
                    detail,
                    pdf_text,
                    briefing.as_text(),
                    related_news,
                )
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
                    article_text=source_text,
                    timestamp_iso=now_iso,
                )
                stats.processed += 1

                if dry_run:
                    LOGGER.info("[DRY RUN] Auto-Writer source generated: %s", detail.title)
                    continue

                assert self.auto_writer is not None
                result = self.auto_writer.run(source_text)
                self.store.mark_sent(summary.notice_id, now_iso)
                stats.sent += 1
                if self.notifier is not None:
                    try:
                        self.notifier.send_auto_writer_result(
                            title=detail.title,
                            detail_url=summary.detail_url,
                            pdf_url=detail.pdf_url,
                            result=result,
                        )
                    except Exception:
                        LOGGER.warning(
                            "Telegram 알림 실패: notice_id=%s",
                            summary.notice_id,
                            exc_info=True,
                        )
                LOGGER.info("Auto-Writer 처리 완료: %s (%s)", summary.notice_id, detail.title)

            except Exception:
                stats.failed += 1
                LOGGER.exception("처리 실패: notice_id=%s", summary.notice_id)

        if not force and not dry_run and stats.failed == 0 and latest_seen_id is not None:
            next_seen = latest_seen_id if last_seen_id is None else max(
                last_seen_id, latest_seen_id
            )
            self.store.set_last_seen_notice_id(next_seen, now_iso)
        elif not force and stats.failed > 0:
            LOGGER.warning(
                "처리 실패가 있어 last_seen_notice_id를 전진시키지 않습니다: failed=%s",
                stats.failed,
            )

        return stats
