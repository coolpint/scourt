from __future__ import annotations

import requests

from .models import ArticleDraft


class TeamsNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.session = requests.Session()

    def send(self, article: ArticleDraft) -> None:
        points = article.key_points[:3] or [article.lead]
        points_text = "\n".join(f"{idx}. {value}" for idx, value in enumerate(points, 1))
        detail_md = f"[보도자료 상세 바로가기]({article.detail_url})"
        pdf_md = (
            f"[첨부 PDF 바로가기]({article.pdf_url})" if article.pdf_url else "첨부 PDF 없음"
        )
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": article.headline,
            "themeColor": "005A9C",
            "title": "대법원 판결 보도자료 브리핑",
            "sections": [
                {
                    "activityTitle": f"**{article.headline}**",
                    "activitySubtitle": f"게시일: {article.posted_date}",
                    "text": (
                        f"**리드**\n{article.lead}\n\n"
                        f"**핵심 3포인트**\n{points_text}\n\n"
                        f"{detail_md}\n\n{pdf_md}\n\n"
                        f"수집시각: {article.collected_at}"
                    ),
                    "markdown": True,
                }
            ],
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name": "보도자료 상세 보기",
                    "targets": [{"os": "default", "uri": article.detail_url}],
                }
            ],
        }
        if article.pdf_url:
            payload["potentialAction"].append(
                {
                    "@type": "OpenUri",
                    "name": "첨부 PDF 열기",
                    "targets": [{"os": "default", "uri": article.pdf_url}],
                }
            )
        response = self.session.post(self.webhook_url, json=payload, timeout=15)
        response.raise_for_status()
