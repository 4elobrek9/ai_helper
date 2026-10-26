"""Менеджер конфигурации LUMI AI на базе YAML-файла."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lumi.core.paths import CONFIG_FILE
from lumi.core.logging import get_logger

logger = get_logger("config")


class ConfigManager:
    """Единый менеджер конфигурации с поддержкой горячей перезагрузки."""

    _instance: "ConfigManager | None" = None

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._config_path: Path = CONFIG_FILE
        self._config: dict[str, Any] = {}
        self._mtime: float = 0.0
        self._load()
        self._initialized = True

    def _load(self) -> None:
        """Загружает конфиг из YAML-файла."""
        if not self._config_path.exists():
            logger.warning(f"Конфиг не найден: {self._config_path}, используются значения по умолчанию")
            self._config = self._default_config()
            self._save()
            return

        try:
            with open(self._config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._config = self._merge_with_defaults(raw)
            self._mtime = self._config_path.stat().st_mtime
            logger.info(f"Конфиг загружен: {self._config_path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки конфига: {e}")
            self._config = self._default_config()

    def _default_config(self) -> dict[str, Any]:
        """Возвращает конфиг по умолчанию."""
        return {
            "assistant": {
                "name": "Lumi",
                "language": "ru-RU",
                "system_prompt": "Ты Lumi, дружелюбный голосовой AI-ассистент.",
                "history_limit": 12,
                "log_dialog": True,
            },
            "wake_word": {
                "engine": "console",
                "keyword": "Люми",
                "model_path": "models/lumia.ppn",
                "access_key": "",
            },
            "vad": {
                "enabled": True,
                "engine": "silero-vad",
                "silence_timeout_sec": 1.2,
            },
            "stt": {
                "engine": "faster-whisper",
                "language": "ru",
                "model": "small",
                "device": "cpu",
                "compute_type": "int8",
            },
            "tts": {
                "engine": "silero",
                "voice": "xenia",
                "rate": 1.0,
                "volume": 1.0,
                "sample_rate": 48000,
            },
            "llm": {
                "provider": "ollama",
                "endpoint": "http://localhost:11434",
                "api_key": "",
                "model": "llama3:8b",
                "temperature": 0.6,
                "max_tokens": 512,
                "fallback": "mistral",
            },
            "desktop": {
                "safe_mode": False,
                "confirm_dangerous": True,
                "allowed_apps": [
                    "notepad", "calc", "mspaint", "chrome", "firefox",
                    "edge", "explorer", "cmd", "powershell",
                ],
                "allowed_folders": [],
            },
            "memory": {
                "enabled": True,
                "summarize_threshold": 20,
                "max_history": 50,
            },
            "gui": {
                "theme": "dark",
                "accent_color": "#00D4FF",
                "window_width": 400,
                "window_height": 600,
            },
        }

    def _merge_with_defaults(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Рекурсивно объединяет загруженный конфиг с valeurs по умолчанию."""
        defaults = self._default_config()
        for key, value in raw.items():
            if key in defaults and isinstance(value, dict) and isinstance(defaults[key], dict):
                defaults[key].update(value)
            else:
                defaults[key] = value
        return defaults

    def _save(self) -> None:
        """Сохраняет текущий конфиг в файл."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")

    def maybe_reload(self) -> bool:
        """Перезагружает конфиг если файл изменился."""
        if not self._config_path.exists():
            return False
        try:
            mtime = self._config_path.stat().st_mtime
            if mtime > self._mtime:
                self._load()
                logger.info("Конфиг перезагружен без рестарта")
                return True
        except Exception as e:
            logger.error(f"Ошибка проверки конфига: {e}")
        return False

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Возвращает значение конфига по секции и ключу."""
        return self._config.get(section, {}).get(key, default)

    def get_section(self, section: str) -> dict[str, Any]:
        """Возвращает всю секцию конфига."""
        return self._config.get(section, {})

    def set(self, section: str, key: str, value: Any, save: bool = True) -> None:
        """Устанавливает значение конфига."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        if save:
            self._save()

    @property
    def config(self) -> dict[str, Any]:
        """Возвращает полный конфиг."""
        return self._config


# Глобальный экземпляр
config = ConfigManager()