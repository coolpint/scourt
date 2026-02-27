from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NoticeSummary:
    notice_id: str
    number: str
    title: str
    posted_date: str
    detail_url: str


@dataclass
class NoticeDetail:
    notice_id: str
    title: str
    body_text: str
    detail_url: str
    attachment_urls: list[str]
    pdf_url: str | None


@dataclass
class PdfResult:
    path: Path
    sha256: str
    text: str


@dataclass
class RunStats:
    scanned: int = 0
    processed: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class ArticleDraft:
    headline: str
    lead: str
    key_points: list[str]
    posted_date: str
    detail_url: str
    pdf_url: str | None
    collected_at: str

    def as_text(self) -> str:
        bullets = "\n".join(f"- {point}" for point in self.key_points) or f"- {self.lead}"
        pdf_url = self.pdf_url or "첨부 PDF 없음"
        return (
            "[대법원 판결 보도자료 기사형 요약]\n\n"
            f"제목: {self.headline}\n\n"
            f"리드\n{self.lead}\n\n"
            f"핵심 내용\n{bullets}\n\n"
            "원문 정보\n"
            f"- 게시일: {self.posted_date}\n"
            f"- 보도자료 상세: {self.detail_url}\n"
            f"- PDF: {pdf_url}\n"
            f"- 수집 시각: {self.collected_at}"
        )
