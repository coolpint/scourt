from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notices (
                    notice_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    posted_date TEXT NOT NULL,
                    detail_url TEXT NOT NULL,
                    pdf_url TEXT,
                    pdf_hash TEXT,
                    content_hash TEXT NOT NULL,
                    article_text TEXT NOT NULL,
                    sent_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_notice(self, notice_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM notices WHERE notice_id = ?",
                (notice_id,),
            ).fetchone()
            return dict(row) if row else None

    def is_empty(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(1) AS cnt FROM notices").fetchone()
            return int(row["cnt"]) == 0

    def upsert_notice(
        self,
        *,
        notice_id: str,
        title: str,
        posted_date: str,
        detail_url: str,
        pdf_url: str | None,
        pdf_hash: str | None,
        content_hash: str,
        article_text: str,
        timestamp_iso: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notices (
                    notice_id,
                    title,
                    posted_date,
                    detail_url,
                    pdf_url,
                    pdf_hash,
                    content_hash,
                    article_text,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(notice_id) DO UPDATE SET
                    title = excluded.title,
                    posted_date = excluded.posted_date,
                    detail_url = excluded.detail_url,
                    pdf_url = excluded.pdf_url,
                    pdf_hash = excluded.pdf_hash,
                    content_hash = excluded.content_hash,
                    article_text = excluded.article_text,
                    updated_at = excluded.updated_at
                """,
                (
                    notice_id,
                    title,
                    posted_date,
                    detail_url,
                    pdf_url,
                    pdf_hash,
                    content_hash,
                    article_text,
                    timestamp_iso,
                    timestamp_iso,
                ),
            )
            conn.commit()

    def mark_sent(self, notice_id: str, timestamp_iso: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE notices
                SET sent_at = ?, updated_at = ?
                WHERE notice_id = ?
                """,
                (timestamp_iso, timestamp_iso, notice_id),
            )
            conn.commit()
