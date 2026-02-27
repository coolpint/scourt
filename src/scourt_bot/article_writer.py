from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .models import ArticleDraft, NoticeDetail, NoticeSummary

KEYWORDS = ("대법원", "판결", "선고", "사건", "상고", "기각", "인용", "파기", "확정")


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
    )
    if any(token in sentence for token in checks):
        return True

    has_ending = sentence.endswith(
        ("다.", "입니다.", "였습니다.", "하였습니다.", "습니다.", "였음.")
    )
    if len(sentence) < 40 and not has_ending:
        return True
    return False


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
        detail_points = [
            _trim_sentence(sentence)
            for sentence in _split_sentences(detail.body_text)
            if not _is_noise(sentence)
        ]
        pdf_points = _pick_key_points(pdf_text, limit=5)

        lead = ""
        for sentence in detail_points:
            if "대법원" in sentence:
                lead = sentence
                break
        if not lead:
            lead = detail_points[0] if detail_points else ""
        if not lead:
            for sentence in pdf_points:
                if "대법원" in sentence:
                    lead = sentence
                    break
        if not lead:
            lead = pdf_points[0] if pdf_points else (detail.body_text or summary.title)
        lead = _clean(lead)

        key_points = list(detail_points[:3])
        for sentence in pdf_points:
            if len(key_points) == 3:
                break
            if sentence in key_points:
                continue
            key_points.append(sentence)

        now_kst = datetime.now(ZoneInfo(self.settings.timezone)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if not key_points:
            key_points = [lead]

        return ArticleDraft(
            headline=_headline_from_title(detail.title),
            lead=lead,
            key_points=key_points[:3],
            posted_date=summary.posted_date,
            detail_url=detail.detail_url,
            pdf_url=detail.pdf_url,
            collected_at=f"{now_kst} ({self.settings.timezone})",
        )
