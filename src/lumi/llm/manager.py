"""Менеджер LLM-провайдеров с fallback-логикой и tool-calling."""

from __future__ import annotations

import logging
from typing import Any

from lumi.core.logging import get_logger
from lumi.llm.base import LLMProvider
from lumi.llm.mistral import MistralProvider
from lumi.llm.ollama import OllamaProvider
from lumi.llm.tools import ToolRegistry

logger = get_logger("llm.manager")


class LLMManager:
    """Управляет LLM-провайдерами с автоматическим fallback и tool-calling."""

    def __init__(self, config: dict[str, Any], desktop_tools: Any = None) -> None:
        self.config = config
        llm_cfg = config.get("llm", {})

        primary_name = llm_cfg.get("provider", "ollama")
        fallback_name = llm_cfg.get("fallback", "mistral")

        self.primary: LLMProvider = self._build_provider(primary_name, llm_cfg)
        self.fallback: LLMProvider | None = None
        if fallback_name and fallback_name != primary_name:
            fallback_cfg = dict(llm_cfg)
            fallback_cfg["provider"] = fallback_name
            self.fallback = self._build_provider(fallback_name, fallback_cfg)

        self.tool_registry: ToolRegistry | None = None
        if desktop_tools is not None:
            self.tool_registry = ToolRegistry(desktop_tools)

        logger.info(f"LLM Manager инициализирован: primary={primary_name}, fallback={fallback_name}")

    def _build_provider(self, name: str, cfg: dict[str, Any]) -> LLMProvider:
        """Создаёт провайдера по имени."""
        name = name.lower()
        if name == "ollama":
            return OllamaProvider(
                endpoint=cfg.get("endpoint", "http://localhost:11434"),
                model=cfg.get("model", "llama3:8b"),
                temperature=cfg.get("temperature", 0.6),
                max_tokens=cfg.get("max_tokens", 512),
            )
        if name == "mistral":
            return MistralProvider(
                api_key=cfg.get("api_key", ""),
                model=cfg.get("model", "mistral-large-2411"),
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 512),
            )
        raise ValueError(f"Неизвестный LLM-провайдер: {name}")

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Генерирует ответ с fallback на резервного провайдера."""
        last_error: Exception | None = None

        for provider, label in [(self.primary, "primary"), (self.fallback, "fallback")]:
            if provider is None:
                continue
            try:
                if not provider.is_available():
                    logger.warning(f"{label} провайдер недоступен")
                    continue
                result = await provider.complete(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                logger.debug(f"Ответ получен от {label} провайдера")
                return result
            except Exception as e:
                logger.warning(f"{label} провайдер ошибся: {e}")
                last_error = e
                continue

        if last_error:
            raise last_error
        raise RuntimeError("Все LLM-провайдеры недоступны")

    def get_tool_descriptions_text(self) -> str:
        """Возвращает описание инструментов для системного промпта."""
        if self.tool_registry:
            return self.tool_registry.get_tool_descriptions_text()
        return "Инструменты не настроены."

    def parse_and_execute_tools(self, text: str) -> tuple[str, list]:
        """Парсит и выполняет вызовы инструментов из текста LLM.

        Возвращает (очищенный_текст, результаты_выполнения).
        """
        if not self.tool_registry:
            return text, []

        calls = self.tool_registry.parse_tool_calls(text)
        if not calls:
            return text, []

        results = self.tool_registry.execute_all(calls)

        result_parts = []
        for r in results:
            if r.success:
                result_parts.append(f"[Результат {r.name}]: {r.result}")
            else:
                result_parts.append(f"[Ошибка {r.name}]: {r.error}")

        clean_text = text
        for call in calls:
            clean_text = clean_text.replace(call.raw_text, "").strip()

        if result_parts:
            clean_text += "\n\n" + "\n".join(result_parts)

        return clean_text, results