"""Глобальные горячие клавиши для LUMI AI через pynput."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from pynput import keyboard

from lumi.core.logging import get_logger

logger = get_logger("voice.hotkeys")


class GlobalHotkeys:
    """Менеджер глобальных горячих клавиш."""

    def __init__(self) -> None:
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Callbacks
        self._on_toggle_window: Optional[Callable[[], None]] = None
        self._on_toggle_listening: Optional[Callable[[], None]] = None
        self._on_stop_speech: Optional[Callable[[], None]] = None

    def set_callbacks(
        self,
        on_toggle_window: Optional[Callable[[], None]] = None,
        on_toggle_listening: Optional[Callable[[], None]] = None,
        on_stop_speech: Optional[Callable[[], None]] = None,
    ) -> None:
        """Устанавливает callback'и для горячих клавиш."""
        self._on_toggle_window = on_toggle_window
        self._on_toggle_listening = on_toggle_listening
        self._on_stop_speech = on_stop_speech

    def start(self) -> None:
        """Запускает прослушивание горячих клавиш в отдельном потоке."""
        with self._lock:
            if self._running:
                logger.warning("Горячие клавиши уже запущены")
                return

            hotkeys = {}
            if self._on_toggle_window:
                hotkeys["<ctrl>+<alt>+l"] = self._safe_call(self._on_toggle_window)
            if self._on_toggle_listening:
                hotkeys["<ctrl>+<alt>+m"] = self._safe_call(self._on_toggle_listening)
            if self._on_stop_speech:
                hotkeys["<ctrl>+<alt>+s"] = self._safe_call(self._on_stop_speech)

            if not hotkeys:
                logger.warning("Нет заданных callback'ов для горячих клавиш")
                return

            self._listener = keyboard.GlobalHotKeys(hotkeys)
            self._listener_thread = threading.Thread(target=self._listener.run, daemon=True)
            self._listener_thread.start()
            self._running = True
            logger.info(f"Горячие клавиши запущены: {list(hotkeys.keys())}")

    def _safe_call(self, func: Optional[Callable[[], None]]) -> Callable[[], None]:
        """Обёртка для безопасного вызова callback'а (перехват исключений)."""
        def wrapper() -> None:
            if func:
                try:
                    func()
                except Exception as e:
                    logger.error(f"Ошибка в callback горячей клавиши: {e}")
        return wrapper

    def stop(self) -> None:
        """Останавливает прослушивание горячих клавиш."""
        with self._lock:
            if self._listener:
                try:
                    self._listener.stop()
                except Exception as e:
                    logger.error(f"Ошибка остановки горячих клавиш: {e}")
                self._listener = None
            self._running = False
            logger.info("Горячие клавиши остановлены")

    def is_running(self) -> bool:
        """Возвращает True если прослушивание активно."""
        return self._running