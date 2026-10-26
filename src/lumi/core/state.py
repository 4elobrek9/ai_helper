"""Глобальное состояние приложения LUMI AI."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppState:
    """Состояние приложения: флаги, текущий режим, ссылки на важные объекты."""

    is_running: bool = False
    is_voice_active: bool = False
    is_listening: bool = False
    is_thinking: bool = False
    is_speaking: bool = False
    safe_mode: bool = False

    # Ссылки на основные компоненты
    voice_assistant: Optional[object] = None
    llm_manager: Optional[object] = None
    desktop_tools: Optional[object] = None
    memory_manager: Optional[object] = None
    tts: Optional[object] = None
    stt: Optional[object] = None
    wake_word: Optional[object] = None

    # Блокировка для потокобезопасного изменения состояния
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_voice_state(self, listening: bool, thinking: bool, speaking: bool) -> None:
        """Атомарно устанавливает голосовое состояние."""
        with self._lock:
            self.is_listening = listening
            self.is_thinking = thinking
            self.is_speaking = speaking

    @property
    def status_text(self) -> str:
        """Возвращает текст текущего статуса для отображения в UI."""
        if self.is_listening:
            return "Слушаю…"
        if self.is_thinking:
            return "Думаю…"
        if self.is_speaking:
            return "Говорю…"
        return "Готов"


# Глобальное состояние
app_state = AppState()