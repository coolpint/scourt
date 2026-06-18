from __future__ import annotations

import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from .config import Settings
from .models import NoticeDetail, NoticeSummary

LOGGER = logging.getLogger(__name__)

STOPWORDS = {
    "대법원",
    "보도자료",
    "판결",
    "선고",
    "사건",
    "관련",
    "대한",
    "청구",
    "원고",
    "피고",
    "상고",
    "기각",
    "확정",
    "파기",
    "환송",
    "손해배상",
    "서울",
    "고등법원",
    "지방법원",
    "자료",
    "첨부",
    "판시",
    "원심",
    "제목",
}

IMPORTANT_TERMS = (
    "학폭",
    "학교폭력",
    "노쇼",
    "권경애",
    "변호사",
    "불출석",
    "손해배상",
    "아동학대",
    "스토킹",
    "중대재해",
    "전세사기",
    "마약",
    "살인",
    "성폭력",
    "횡령",
    "배임",
    "사기",
    "관세",
    "밀수",
)


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published: str
    link: str


def _clean(text: object) -> str:
    return " ".join(html.unescape(str(text or "")).split())


def _strip_press_release_words(title: str) -> str:
    cleaned = re.sub(r"\s*보도자료\s*$", "", _clean(title))
    cleaned = re.sub(r"[\[\]【】()（）]", " ", cleaned)
    return _clean(cleaned)


def _extract_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", text)
    scored: dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        score = 1
        if token in IMPORTANT_TERMS:
            score += 8
        elif any(term in token or token in term for term in IMPORTANT_TERMS):
            score += 4
        if len(token) >= 4:
            score += 1
        scored[token] = scored.get(token, 0) + score
    return [token for token, _ in sorted(scored.items(), key=lambda item: item[1], reverse=True)]


def build_news_queries(summary: NoticeSummary, detail: NoticeDetail, pdf_text: str, limit: int = 3) -> list[str]:
    title = _strip_press_release_words(detail.title or summary.title)
    combined = "\n".join([detail.title, summary.title, detail.body_text, pdf_text[:4000]])
    tokens = _extract_tokens(combined)

    queries: list[str] = []
    if title:
        queries.append(f'"{title}"')

    important = [token for token in tokens if token in IMPORTANT_TERMS or any(term in token or token in term for term in IMPORTANT_TERMS)]
    if important:
        queries.append(" ".join(important[:5] + ["대법원"]))

    if tokens:
        queries.append(" ".join(tokens[:6] + ["대법원", "판결"]))

    deduped: list[str] = []
    seen = set()
    for query in queries:
        normalized = _clean(query)
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
        if len(deduped) >= limit:
            break
    return deduped


class NewsResearcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def collect(self, summary: NoticeSummary, detail: NoticeDetail, pdf_text: str) -> str:
        if not self.settings.news_search_enabled:
            return "관련 보도 검색 비활성화(SCOURT_NEWS_SEARCH_ENABLED=0)."

        queries = build_news_queries(summary, detail, pdf_text, limit=self.settings.news_search_query_limit)
        if not queries:
            return "관련 보도 검색어를 만들지 못했습니다."

        items: list[NewsItem] = []
        seen_titles = set()
        for query in queries:
            try:
                for item in self._search_google_news(query):
                    key = re.sub(r"\s+", " ", item.title).strip()
                    if key in seen_titles:
                        continue
                    seen_titles.add(key)
                    items.append(item)
                    if len(items) >= self.settings.news_search_result_limit:
                        break
            except Exception as exc:  # keep the monitor resilient
                LOGGER.warning("관련 보도 검색 실패: query=%s error=%s", query, exc)
            if len(items) >= self.settings.news_search_result_limit:
                break

        lines = ["관련 언론 보도 검색:"]
        lines.append("- 검색 목적: 대법원 보도자료가 익명화한 사건이 이미 사회적으로 알려진 사건인지 확인하고, 확인되는 경우 기사에 '언론 보도에 따르면/앞서 보도된 바에 따르면' 식으로 반영한다.")
        lines.append("- 주의: 아래 보도 제목/출처만으로 단정하지 말고, 대법원 자료와 충돌하지 않는 범위에서만 배경으로 사용한다.")
        lines.append("- 검색어: " + " / ".join(queries))
        if not items:
            lines.append("- 검색 결과: 주요 관련 보도를 찾지 못했습니다. 이 경우 대법원 보도자료 중심으로 작성하되, 익명 사건명 추정은 하지 않는다.")
            return "\n".join(lines)

        for idx, item in enumerate(items, start=1):
            lines.append(
                f"- [{idx}] {item.title} | {item.source or '출처 미상'} | {item.published or '날짜 미상'} | {item.link}"
            )
        return "\n".join(lines)

    def _search_google_news(self, query: str) -> list[NewsItem]:
        quoted = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={quoted}&hl=ko&gl=KR&ceid=KR:ko"
        response = requests.get(
            url,
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.news_search_timeout_seconds,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items: list[NewsItem] = []
        for node in root.findall("./channel/item")[: self.settings.news_search_result_limit]:
            source = node.find("source")
            items.append(
                NewsItem(
                    title=_clean(node.findtext("title")),
                    source=_clean(source.text if source is not None else ""),
                    published=_clean(node.findtext("pubDate")),
                    link=_clean(node.findtext("link")),
                )
            )
        return items
