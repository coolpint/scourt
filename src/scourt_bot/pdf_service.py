from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import requests

from .config import Settings
from .models import PdfResult

LOGGER = logging.getLogger(__name__)

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional at runtime
    pdfplumber = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional at runtime
    PdfReader = None


def _clean(text: str) -> str:
    return " ".join(text.split())


class PdfService:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.settings.user_agent})
        self.settings.pdf_dir.mkdir(parents=True, exist_ok=True)

    def download_and_extract(self, pdf_url: str, notice_id: str) -> PdfResult:
        output_path = self.settings.pdf_dir / f"{notice_id}.pdf"
        sha256 = hashlib.sha256()

        with self.session.get(
            pdf_url,
            timeout=self.settings.timeout_seconds,
            stream=True,
        ) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    sha256.update(chunk)

        text = self._extract_text(output_path)
        return PdfResult(path=output_path, sha256=sha256.hexdigest(), text=text)

    def _extract_text(self, pdf_path: Path, max_pages: int = 8) -> str:
        texts: list[str] = []

        if pdfplumber is not None:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages[:max_pages]:
                        page_text = (page.extract_text() or "").strip()
                        if page_text:
                            texts.append(page_text)
            except Exception as exc:  # pragma: no cover - depends on source PDFs
                LOGGER.warning("pdfplumber 추출 실패 (%s): %s", pdf_path.name, exc)

        if not texts and PdfReader is not None:
            try:
                reader = PdfReader(str(pdf_path))
                for page in reader.pages[:max_pages]:
                    page_text = (page.extract_text() or "").strip()
                    if page_text:
                        texts.append(page_text)
            except Exception as exc:  # pragma: no cover - depends on source PDFs
                LOGGER.warning("pypdf 추출 실패 (%s): %s", pdf_path.name, exc)

        return _clean("\n".join(texts))
