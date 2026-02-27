from __future__ import annotations

import html as html_lib
import logging
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import Settings
from .models import NoticeDetail, NoticeSummary

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://www.scourt.go.kr"


def _clean(text: str) -> str:
    return " ".join(text.split())


def _extract_seqnum(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    seqnums = query.get("seqnum")
    if seqnums and seqnums[0].strip():
        return seqnums[0].strip()
    return None


class ScourtClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.settings.user_agent,
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    def _get_html(self, url: str, params: dict[str, str] | None = None) -> str:
        response = self.session.get(
            url,
            params=params,
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        return response.content.decode("euc-kr", errors="replace")

    def fetch_news_list(self, page_index: int = 1) -> list[NoticeSummary]:
        params = {"gubun": self.settings.gubun, "pageIndex": str(page_index)}
        html = self._get_html(self.settings.list_url, params=params)
        soup = BeautifulSoup(html, "html.parser")

        notices: list[NoticeSummary] = []
        for row in soup.select("table.tableHor tbody tr"):
            title_link = row.select_one("td.tit a")
            number_cell = row.select_one("td.mhid")
            cells = row.find_all("td")
            if not title_link or not number_cell or len(cells) < 3:
                continue

            href = title_link.get("href", "").strip()
            if not href:
                continue
            detail_url = urljoin(BASE_URL, html_lib.unescape(href))
            notice_id = _extract_seqnum(detail_url)
            if not notice_id:
                LOGGER.warning("seqnum 파싱 실패: %s", detail_url)
                continue

            posted_date = _clean(cells[-1].get_text(" ", strip=True))
            notices.append(
                NoticeSummary(
                    notice_id=notice_id,
                    number=_clean(number_cell.get_text(" ", strip=True)),
                    title=_clean(title_link.get_text(" ", strip=True)),
                    posted_date=posted_date,
                    detail_url=detail_url,
                )
            )

        return notices

    def fetch_notice_detail(self, summary: NoticeSummary) -> NoticeDetail:
        html = self._get_html(summary.detail_url)
        soup = BeautifulSoup(html, "html.parser")

        title = summary.title
        for row in soup.select("table.tableVer tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            if _clean(th.get_text(" ", strip=True)) == "제목":
                title = _clean(td.get_text(" ", strip=True))
                break

        body_cell = soup.select_one("td.contArea")
        body_text = ""
        if body_cell:
            body_text = _clean(body_cell.get_text("\n", strip=True))

        attachment_urls: list[str] = []
        for anchor in soup.select("td.attTxt a"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            attachment_urls.append(urljoin(BASE_URL, html_lib.unescape(href)))

        pdf_url = None
        for attachment_url in attachment_urls:
            lowered = attachment_url.lower()
            if ".pdf" in lowered or "attachdownload" in lowered:
                pdf_url = attachment_url
                break

        return NoticeDetail(
            notice_id=summary.notice_id,
            title=title,
            body_text=body_text,
            detail_url=summary.detail_url,
            attachment_urls=attachment_urls,
            pdf_url=pdf_url,
        )
