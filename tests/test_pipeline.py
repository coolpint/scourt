from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scourt_bot.config import Settings
from scourt_bot.models import NoticeDetail, NoticeSummary
from scourt_bot.pipeline import ScourtPipeline


def make_settings(root: Path, *, initial_last_seen_notice_id: int | None = None) -> Settings:
    return Settings(
        list_url="https://example.test/list",
        gubun="702",
        max_pages=1,
        timeout_seconds=5,
        timezone="Asia/Seoul",
        schedule_hours=(10, 18),
        db_path=root / "scourt_news.db",
        pdf_dir=root / "pdfs",
        telegram_bot_token="telegram-token",
        telegram_chat_id="44370045",
        auto_writer_dir=root / "Auto-Writer",
        auto_writer_mode="dry-run",
        user_agent="test",
        bootstrap_skip_send=True,
        initial_last_seen_notice_id=initial_last_seen_notice_id,
        news_search_enabled=False,
        news_search_query_limit=3,
        news_search_result_limit=8,
        news_search_timeout_seconds=8,
    )


def make_summary(notice_id: str) -> NoticeSummary:
    return NoticeSummary(
        notice_id=notice_id,
        number=notice_id,
        title=f"공지 {notice_id}",
        posted_date="2026-04-27",
        detail_url=f"https://example.test/notices/{notice_id}",
    )


def make_detail(summary: NoticeSummary) -> NoticeDetail:
    return NoticeDetail(
        notice_id=summary.notice_id,
        title=summary.title,
        body_text=f"{summary.title} 본문입니다. 대법원 판결 관련 내용입니다.",
        detail_url=summary.detail_url,
        attachment_urls=[],
        pdf_url="https://example.test/notices/sample.pdf",
    )


class FakeClient:
    def __init__(self, summaries: list[NoticeSummary], fail_detail_ids: set[str] | None = None):
        self.summaries = summaries
        self.fail_detail_ids = fail_detail_ids or set()

    def fetch_news_list(self, page_index: int = 1) -> list[NoticeSummary]:
        return self.summaries

    def fetch_notice_detail(self, summary: NoticeSummary) -> NoticeDetail:
        if summary.notice_id in self.fail_detail_ids:
            raise RuntimeError("detail unavailable")
        return make_detail(summary)


class FakePdfService:
    def __init__(self):
        self.downloaded = []

    def download_and_extract(self, pdf_url: str, notice_id: str):
        from scourt_bot.models import PdfResult

        self.downloaded.append((pdf_url, notice_id))
        return PdfResult(
            path=Path(f"/tmp/{notice_id}.pdf"),
            sha256=f"sha-{notice_id}",
            text=f"{notice_id} PDF 본문입니다.",
        )


class FakeNewsResearcher:
    def collect(self, summary: NoticeSummary, detail: NoticeDetail, pdf_text: str) -> str:
        return "관련 언론 보도 검색:\n- [1] 학폭 소송 노쇼 변호사 권경애 사건 관련 보도 | 연합뉴스 | 2026-05-29 | https://example.test/news"


class FakeAutoWriter:
    def __init__(self):
        self.sources = []

    def run(self, source_text: str):
        self.sources.append(source_text)
        return {
            "jobId": "job-1",
            "outputDir": "/tmp/auto-writer/job-1",
            "cmsStatus": "dry-run",
            "title": "오토라이터 초안",
        }


class FakeNotifier:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.sent = []

    def send_auto_writer_result(self, *, title, detail_url, pdf_url, result):
        if self.fail:
            raise RuntimeError("telegram unavailable")
        self.sent.append(
            {
                "title": title,
                "detail_url": detail_url,
                "pdf_url": pdf_url,
                "result": result,
            }
        )


class PipelineTests(unittest.TestCase):
    def build_pipeline(
        self,
        root: Path,
        summaries: list[NoticeSummary],
        *,
        initial_last_seen_notice_id: int | None = None,
        fail_detail_ids: set[str] | None = None,
    ) -> ScourtPipeline:
        pipeline = ScourtPipeline(
            make_settings(
                root,
                initial_last_seen_notice_id=initial_last_seen_notice_id,
            )
        )
        pipeline.client = FakeClient(summaries, fail_detail_ids=fail_detail_ids)
        pipeline.pdf_service = FakePdfService()
        pipeline.news_researcher = FakeNewsResearcher()  # type: ignore[assignment]
        pipeline.auto_writer = FakeAutoWriter()
        pipeline.notifier = FakeNotifier()
        return pipeline

    def test_initial_last_seen_notice_id_is_used_as_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(
                root,
                [make_summary("100"), make_summary("101")],
                initial_last_seen_notice_id=100,
            )

            stats = pipeline.run_once()

            self.assertEqual(stats.sent, 1)
            self.assertEqual(pipeline.store.get_last_seen_notice_id(), 101)

    def test_failed_run_does_not_advance_last_seen_notice_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(
                root,
                [make_summary("101"), make_summary("102")],
                fail_detail_ids={"101"},
            )
            pipeline.store.set_last_seen_notice_id(100, "2026-04-27T00:00:00+09:00")

            stats = pipeline.run_once()

            self.assertEqual(stats.failed, 1)
            self.assertEqual(stats.sent, 1)
            self.assertEqual(pipeline.store.get_last_seen_notice_id(), 100)

    def test_dry_run_does_not_advance_last_seen_notice_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(root, [make_summary("101")])
            pipeline.store.set_last_seen_notice_id(100, "2026-04-27T00:00:00+09:00")

            stats = pipeline.run_once(dry_run=True)

            self.assertEqual(stats.processed, 1)
            self.assertEqual(pipeline.store.get_last_seen_notice_id(), 100)

    def test_dry_run_does_not_persist_initial_last_seen_notice_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(
                root,
                [make_summary("100"), make_summary("101")],
                initial_last_seen_notice_id=100,
            )

            stats = pipeline.run_once(dry_run=True)

            self.assertEqual(stats.processed, 1)
            self.assertIsNone(pipeline.store.get_last_seen_notice_id())

    def test_pdf_download_is_handed_to_auto_writer_before_telegram_notice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(root, [make_summary("101")])
            pipeline.store.set_last_seen_notice_id(100, "2026-04-27T00:00:00+09:00")

            stats = pipeline.run_once()

            self.assertEqual(stats.processed, 1)
            self.assertEqual(stats.sent, 1)
            self.assertEqual(pipeline.pdf_service.downloaded, [("https://example.test/notices/sample.pdf", "101")])
            self.assertEqual(len(pipeline.auto_writer.sources), 1)
            self.assertIn("101 PDF 본문입니다.", pipeline.auto_writer.sources[0])
            self.assertIn("학폭 소송 노쇼 변호사 권경애 사건 관련 보도", pipeline.auto_writer.sources[0])
        self.assertIn("보도자료 상세: https://example.test/notices/101", pipeline.auto_writer.sources[0])
        self.assertEqual(pipeline.notifier.sent[0]["result"]["cmsStatus"], "dry-run")

    def test_telegram_failure_does_not_retry_completed_auto_writer_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(root, [make_summary("101")])
            pipeline.notifier = FakeNotifier(fail=True)
            pipeline.store.set_last_seen_notice_id(100, "2026-04-27T00:00:00+09:00")

            stats = pipeline.run_once()

            self.assertEqual(stats.failed, 0)
            self.assertEqual(stats.sent, 1)
            self.assertEqual(pipeline.store.get_last_seen_notice_id(), 101)
            self.assertIsNotNone(pipeline.store.get_notice("101")["sent_at"])

    def test_run_requires_telegram_settings_not_teams_webhook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            # 이전 Teams 웹훅 없이도 Telegram + Auto-Writer 설정만 있으면 실행 가능해야 한다.
            pipeline = ScourtPipeline(settings)
            pipeline.client = FakeClient([make_summary("101")])
            pipeline.pdf_service = FakePdfService()
            pipeline.news_researcher = FakeNewsResearcher()  # type: ignore[assignment]
            pipeline.auto_writer = FakeAutoWriter()
            pipeline.notifier = FakeNotifier()
            pipeline.store.set_last_seen_notice_id(100, "2026-04-27T00:00:00+09:00")

            stats = pipeline.run_once()

            self.assertEqual(stats.sent, 1)

    def test_empty_first_page_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = self.build_pipeline(root, [])

            with self.assertRaises(RuntimeError):
                pipeline.run_once(dry_run=True)

    def test_invalid_initial_last_seen_notice_id_fails_fast(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                "os.environ",
                {
                    "SCOURT_ROOT_DIR": temp_dir,
                    "SCOURT_INITIAL_LAST_SEEN_NOTICE_ID": "not-a-number",
                },
            ):
                with self.assertRaisesRegex(ValueError, "must be an integer"):
                    Settings.load()


if __name__ == "__main__":
    unittest.main()
