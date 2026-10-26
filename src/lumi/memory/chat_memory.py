"""История чата на базе SQLite."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from lumi.core.logging import get_logger
from lumi.core.paths import CHAT_DB, DATA_DIR

logger = get_logger("memory.chat")


class ChatMemory:
    """История диалога с хранением в SQLite."""

    def __init__(self, db_path: Path | None = None, max_history: int = 50) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or CHAT_DB
        self.max_history = max_history
        self._init_db()

    def _init_db(self) -> None:
        """Создаёт таблицу истории если не существует."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def add(self, role: str, content: str) -> None:
        """Добавляет сообщение в историю."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)",
                    (role, content, datetime.now().isoformat()),
                )
                conn.commit()
            self._enforce_limit()
        except Exception as e:
            logger.error(f"Ошибка добавления в историю: {e}")

    def get_recent(self, limit: int | None = None) -> list[dict[str, str]]:
        """Возвращает последние сообщения истории."""
        limit = limit or self.max_history
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
        except Exception as e:
            logger.error(f"Ошибка чтения истории: {e}")
            return []

    def clear(self) -> None:
        """Очищает всю историю."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM chat_history")
                conn.commit()
            logger.info("История чата очищена")
        except Exception as e:
            logger.error(f"Ошибка очистки истории: {e}")

    def _enforce_limit(self) -> None:
        """Удаляет старые сообщения超过 max_history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    f"DELETE FROM chat_history WHERE id NOT IN "
                    f"(SELECT id FROM chat_history ORDER BY id DESC LIMIT ?)",
                    (self.max_history,),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка ограничения истории: {e}")

    def export(self, file_path: Path) -> str:
        """Экспортирует историю в JSON-файл."""
        import json
        history = self.get_recent(limit=self.max_history * 2)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            return f"История экспортирована в {file_path}"
        except Exception as e:
            logger.error(f"Ошибка экспорта: {e}")
            return f"Ошибка экспорта: {e}"

    def format_for_llm(self, limit: int | None = None) -> list[dict[str, str]]:
        """Возвращает историю в формате для LLM (system excluded)."""
        return self.get_recent(limit=limit)