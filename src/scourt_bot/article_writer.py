from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .models import ArticleDraft, NoticeDetail, NoticeSummary

KEYWORDS = ("대법원", "판결", "선고", "사건", "상고", "기각", "인용", "파기", "확정")
CARD_BODY_LIMIT = 1000


def _clean(text: str) -> str:
    return " ".join(text.split())


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    result: list[str] = []
    for chunk in chunks:
        normalized = _clean(chunk)
        if len(normalized) < 16:
            continue
        result.append(normalized)
    return result


def _trim_sentence(text: str, max_len: int = 180) -> str:
    cleaned = _clean(text)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _headline_from_title(title: str) -> str:
    cleaned = _clean(title)
    if cleaned.endswith(" 보도자료"):
        cleaned = cleaned[: -len(" 보도자료")].rstrip()
    if cleaned.endswith("보도자료"):
        cleaned = cleaned[: -len("보도자료")].rstrip()
    return cleaned


def _is_noise(sentence: str) -> bool:
    checks = (
        "공보관실",
        "전화",
        "☎",
        "문의",
        "보도자료",
        "판결 결과 ▣",
        "선고일자",
        "사건개요",
        "쟁점 및 판단",
        "참조조문",
        "참조판례",
        "공소사실의 요지",
        "판단 내용",
        "쟁점(",
        "▣",
        "●",
        "- 2 -",
        "- 3 -",
    )
    if any(token in sentence for token in checks):
        return True

    has_ending = sentence.endswith(
        ("다.", "입니다.", "였습니다.", "하였습니다.", "습니다.", "였음.")
    )
    if len(sentence) < 40 and not has_ending:
        return True
    return False


def _compose_body(primary: list[str], secondary: list[str], limit: int) -> str:
    ordered: list[str] = []
    seen = set()
    source = primary if primary else secondary
    for sentence in source:
        if sentence in seen:
            continue
        seen.add(sentence)
        ordered.append(sentence)
        if len(ordered) >= 6:
            break

    if not ordered:
        return ""

    body_parts: list[str] = []
    for sentence in ordered:
        candidate = " ".join(body_parts + [sentence]).strip()
        if len(candidate) <= limit:
            body_parts.append(sentence)
            continue

        if not body_parts:
            return _trim_sentence(sentence, max_len=limit)
        break

    body = " ".join(body_parts).strip()
    if len(body) > limit:
        body = _trim_sentence(body, max_len=limit)
    return body


def _pick_key_points(text: str, limit: int = 3) -> list[str]:
    candidates = _split_sentences(text)
    if not candidates:
        return []

    scored = []
    for sentence in candidates:
        score = sum(2 for keyword in KEYWORDS if keyword in sentence)
        score += min(len(sentence) // 40, 2)
        scored.append((score, sentence))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[str] = []
    seen = set()
    for _, sentence in scored:
        if _is_noise(sentence):
            continue
        if sentence in seen:
            continue
        selected.append(_trim_sentence(sentence))
        seen.add(sentence)
        if len(selected) == limit:
            break
    return selected


class ArticleWriter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build(
        self,
        summary: NoticeSummary,
        detail: NoticeDetail,
        pdf_text: str,
    ) -> ArticleDraft:
        detail_points = []
        for sentence in _split_sentences(detail.body_text):
            if _is_noise(sentence):
                continue
            detail_points.append(_trim_sentence(sentence))

        pdf_points = _pick_key_points(pdf_text, limit=8)
        body = _compose_body(detail_points, [], CARD_BODY_LIMIT)
        if not body:
            body = _compose_body([], pdf_points, CARD_BODY_LIMIT)
        if not body:
            body = _trim_sentence(detail.body_text or summary.title, max_len=CARD_BODY_LIMIT)

        now_kst = datetime.now(ZoneInfo(self.settings.timezone)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        return ArticleDraft(
            headline=_headline_from_title(detail.title),
            body=body,
            posted_date=summary.posted_date,
            detail_url=detail.detail_url,
            pdf_url=detail.pdf_url,
            collected_at=f"{now_kst} ({self.settings.timezone})",
        )
