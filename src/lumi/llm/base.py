"""Базовый интерфейс для LLM-провайдеров."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Базовый класс для всех LLM-провайдеров."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> str:
        """Генерирует ответ на основе сообщений.

        Args:
            messages: Список сообщений с ролями system/user/assistant.
            temperature: Температура генерации.
            max_tokens: Максимальное количество токенов.
            **kwargs: Дополнительные параметры провайдера.

        Returns:
            Сгенерированный текст ответа.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Проверяет доступность провайдера."""