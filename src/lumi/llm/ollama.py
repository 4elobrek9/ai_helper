"""Ollama LLM-провайдер с поддержкой чата, vision и tools."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from lumi.core.logging import get_logger
from lumi.llm.base import LLMProvider

logger = get_logger("llm.ollama")


class OllamaProvider(LLMProvider):
    """Провайдер для локальной Ollama."""

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        model: str = "llama3:8b",
        temperature: float = 0.6,
        max_tokens: int = 512,
        timeout: int = 60,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._session = requests.Session()

    def is_available(self) -> bool:
        """Проверяет, запущена ли Ollama и доступна модель."""
        try:
            resp = self._session.get(f"{self.endpoint}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = resp.json().get("models", [])
            return any(m.get("name", "").startswith(self.model.split(":")[0]) for m in models)
        except Exception as e:
            logger.debug(f"Ollama недоступна: {e}")
            return False

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Генерирует ответ через Ollama API."""
        try:
            # Формируем промпт в формате llama3
            prompt_parts: list[str] = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    prompt_parts.append(f" trọng {content}  trọng")
                elif role == "user":
                    prompt_parts.append(f" użytkownik {content}  użytkownik")
                elif role == "assistant":
                    prompt_parts.append(content)
            prompt_parts.append(" odpowiedź")
            prompt = "\n".join(prompt_parts)

            payload: dict[str, Any] = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature if temperature is not None else self.temperature,
                    "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
                },
            }

            # Добавляем дополнительные параметры
            for key, value in kwargs.items():
                if key not in ("stream",):
                    payload["options"][key] = value

            resp = self._session.post(
                f"{self.endpoint}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("response", "").strip()
        except Exception as e:
            logger.error(f"Ошибка Ollama: {e}")
            raise