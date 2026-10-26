"""Долгосрочная память: факты о пользователе и суммаризация."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lumi.core.logging import get_logger
from lumi.core.paths import DATA_DIR

logger = get_logger("memory.long_term")


class LongTermMemory:
    """Долгосрочная память: извлечение и хранение фактов о пользователе."""

    def __init__(self, storage_path: Path | None = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.storage_path = storage_path or (DATA_DIR / "facts.json")
        self._facts: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Загружает факты из файла."""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, encoding="utf-8") as f:
                    self._facts = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки фактов: {e}")
            self._facts = []

    def _save(self) -> None:
        """Сохраняет факты в файл."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._facts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения фактов: {e}")

    def add_fact(self, fact: str, category: str = "general") -> str:
        """Добавляет факт о пользователе."""
        for f in self._facts:
            if f["fact"].lower() == fact.lower():
                return f"Факт уже известен: {fact}"
        self._facts.append({
            "fact": fact,
            "category": category,
            "added_at": __import__("datetime").datetime.now().isoformat(),
        })
        self._save()
        return f"Факт запомнен: {fact}"

    def remove_fact(self, fact: str) -> str:
        """Удаляет факт о пользователе."""
        original_len = len(self._facts)
        self._facts = [f for f in self._facts if f["fact"].lower() != fact.lower()]
        if len(self._facts) < original_len:
            self._save()
            return f"Факт удалён: {fact}"
        return f"Факт не найден: {fact}"

    def get_all_facts(self) -> list[dict[str, Any]]:
        """Возвращает все сохранённые факты."""
        return self._facts.copy()

    def get_facts_for_prompt(self) -> str:
        """Возвращает факты в формате для системного промпта."""
        if not self._facts:
            return ""
        lines = ["Известные факты о пользователе:"]
        for f in self._facts:
            lines.append(f"- {f['fact']} ({f['category']})")
        return "\n".join(lines)

    def clear(self) -> None:
        """Очищает все факты."""
        self._facts = []
        self._save()