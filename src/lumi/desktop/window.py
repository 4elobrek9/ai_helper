"""Управление окнами Windows (через pywin32 / pygetwindow)."""

from __future__ import annotations

import logging

from lumi.core.logging import get_logger

logger = get_logger("desktop.window")


class WindowManager:
    """Безопасное управление окнами Windows."""

    def __init__(self, confirm_dangerous: bool = True) -> None:
        self.confirm_dangerous = confirm_dangerous

    def list_windows(self) -> list[dict[str, str]]:
        """Возвращает список всех видимых окон."""
        try:
            import pygetwindow as gw
            windows = []
            for w in gw.getAllWindows():
                if w.title.strip():
                    windows.append({
                        "title": w.title,
                        "x": str(w.left),
                        "y": str(w.top),
                        "width": str(w.width),
                        "height": str(w.height),
                    })
            return windows
        except ImportError:
            logger.warning("pygetwindow не установлен")
            return []
        except Exception as e:
            logger.error(f"Ошибка list_windows: {e}")
            return []

    def focus_window(self, title_substring: str) -> str:
        """Переводит фокус на окно по частичному совпадению заголовка."""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title_substring)
            if windows:
                windows[0].activate()
                return f"Окно '{title_substring}' сфокусировано."
            return f"Окно '{title_substring}' не найдено."
        except ImportError:
            return "pygetwindow не установлен."
        except Exception as e:
            logger.error(f"Ошибка focus_window: {e}")
            return f"Ошибка: {e}"

    def minimize_window(self, title_substring: str) -> str:
        """Сворачивает окно по заголовку."""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title_substring)
            if windows:
                windows[0].minimize()
                return f"Окно '{title_substring}' свёрнуто."
            return f"Окно '{title_substring}' не найдено."
        except ImportError:
            return "pygetwindow не установлен."
        except Exception as e:
            logger.error(f"Ошибка minimize_window: {e}")
            return f"Ошибка: {e}"

    def close_window(self, title_substring: str) -> str:
        """Закрывает окно по заголовку (с проверкой на безопасность)."""
        if self.confirm_dangerous:
            return f"Требуется подтверждение для закрытия окна '{title_substring}'."
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title_substring)
            if windows:
                windows[0].close()
                return f"Окно '{title_substring}' закрыто."
            return f"Окно '{title_substring}' не найдено."
        except ImportError:
            return "pygetwindow не установлен."
        except Exception as e:
            logger.error(f"Ошибка close_window: {e}")
            return f"Ошибка: {e}"