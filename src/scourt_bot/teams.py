from __future__ import annotations

from .models import ArticleDraft


class TeamsNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, article: ArticleDraft) -> None:
        raise RuntimeError("Teams 전송은 비활성화되어 있습니다.")
