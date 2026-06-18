from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings


class AutoWriterRunner:
    def __init__(self, settings: Settings):
        if settings.auto_writer_dir is None:
            raise ValueError("AUTO_WRITER_PROJECT_DIR 이 설정되지 않았습니다.")
        self.settings = settings
        self.project_dir = settings.auto_writer_dir

    def run(self, source_text: str) -> dict:
        if not self.project_dir.exists():
            raise FileNotFoundError(f"Auto-Writer 폴더를 찾지 못했습니다: {self.project_dir}")

        source_path = self._write_source(source_text)
        env = os.environ.copy()
        env.setdefault("GEMINI_MODEL_LABEL", "Pro")

        completed = subprocess.run(
            [
                "node",
                "src/index.js",
                "run",
                "--mode",
                self.settings.auto_writer_mode,
                "--channel",
                "scourt",
                "--source",
                str(source_path),
            ],
            cwd=str(self.project_dir),
            env=env,
            text=True,
            capture_output=True,
            timeout=1800,
            check=False,
        )

        if completed.returncode != 0:
            stderr = completed.stderr.strip()[-2000:]
            stdout = completed.stdout.strip()[-1000:]
            raise RuntimeError(
                "Auto-Writer 실행 실패"
                + (f"\nSTDERR:\n{stderr}" if stderr else "")
                + (f"\nSTDOUT:\n{stdout}" if stdout else "")
            )

        summary = _parse_last_json(completed.stdout)
        summary["sourcePath"] = str(source_path)
        return summary

    def _write_source(self, source_text: str) -> Path:
        source_dir = self.settings.db_path.parent / "auto_writer_sources"
        source_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(ZoneInfo(self.settings.timezone)).strftime("%Y%m%d-%H%M%S")
        source_path = source_dir / f"scourt-{stamp}.txt"
        source_path.write_text(source_text, encoding="utf-8")
        return source_path


def _parse_last_json(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        return {"status": "completed", "rawOutput": ""}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.rfind("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return {"status": "completed", "rawOutput": text[-2000:]}
