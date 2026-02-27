from __future__ import annotations

import requests

from .models import ArticleDraft


class TeamsNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.session = requests.Session()

    def send(self, article: ArticleDraft) -> None:
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": article.headline,
            "themeColor": "005A9C",
            "title": "대법원 판결 보도자료 브리핑",
            "sections": [
                {
                    "activityTitle": f"**{article.headline}**",
                    "text": article.body,
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
