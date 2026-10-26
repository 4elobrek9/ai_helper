"""Mistral AI LLM-провайдер (fallback, онлайн)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from lumi.core.logging import get_logger
from lumi.llm.base import LLMProvider

logger = get_logger("llm.mistral")


class MistralProvider(LLMProvider):
    """Провайдер для Mistral API (используется как fallback)."""

    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "https://api.mistral.ai/v1/chat/completions",
        model: str = "mistral-large-2411",
        temperature: float = 0.7,
        max_tokens: int = 512,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def is_available(self) -> bool:
        """Проверяет наличие API ключа."""
        return bool(self.api_key and len(self.api_key) > 5)

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Генерирует ответ через Mistral API."""
        if not self.is_available():
            raise ValueError("Mistral API ключ не настроен")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        try:
            resp = requests.post(
                self.endpoint,
                headers=headers,
                json=data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Ошибка Mistral API: {e}")
            raise