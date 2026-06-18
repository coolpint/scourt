from __future__ import annotations

from typing import Any

import requests


class TelegramNotifier:
    def __init__(self, *, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.session = requests.Session()

    def send_auto_writer_result(
        self,
        *,
        title: str,
        detail_url: str,
        pdf_url: str | None,
        result: dict[str, Any],
    ) -> None:
        cms_status = result.get("cmsStatus") or result.get("status") or "unknown"
        job_id = result.get("jobId") or "unknown"
        output_dir = result.get("outputDir")
        auto_title = result.get("title")

        lines = [
            "대법원 보도자료 Auto-Writer 처리 완료",
            f"제목: {auto_title or title}",
            f"상태: {cms_status}",
            f"작업 ID: {job_id}",
            f"보도자료: {detail_url}",
        ]
        if pdf_url:
            lines.append(f"PDF: {pdf_url}")
        if output_dir:
            lines.append(f"작업 폴더: {output_dir}")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        response = self.session.post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": "\n".join(lines),
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        response.raise_for_status()
