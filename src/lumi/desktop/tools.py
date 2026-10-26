"""Инструменты управления компьютером (desktop tools) с подтверждением опасных действий."""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

import pyautogui
import pyperclip

from lumi.core.logging import get_logger

logger = get_logger("desktop.tools")


class DesktopTools:
    """Безопасные инструменты управления компьютером с подтверждением опасных действий."""

    DEFAULT_ALLOWED_APPS = [
        "notepad", "calc", "mspaint", "notepad++",
        "chrome", "firefox", "msedge", "explorer",
        "cmd", "powershell", "taskmgr",
    ]

    SAFE_KEY_COMBINATIONS = [
        ("ctrl", "c"), ("ctrl", "v"), ("ctrl", "x"), ("ctrl", "z"), ("ctrl", "y"),
        ("ctrl", "a"), ("ctrl", "s"), ("ctrl", "p"), ("ctrl", "f"),
        ("ctrl", "shift", "esc"), ("alt", "tab"), ("alt", "f4"),
        ("win", "d"), ("win", "l"), ("win", "r"),
        ("f1",), ("f2",), ("f3",), ("f4",), ("f5",),
        ("space",), ("enter",), ("esc",), ("backspace",), ("delete",),
    ]

    def __init__(
        self,
        allowed_apps: list[str] | None = None,
        allowed_folders: list[str] | None = None,
        confirm_dangerous: bool = True,
        safe_mode: bool = False,
    ) -> None:
        self.allowed_apps = allowed_apps or self.DEFAULT_ALLOWED_APPS.copy()
        self.allowed_folders = allowed_folders or [
            str(Path.home() / "Documents"),
            str(Path.home() / "Desktop"),
        ]
        self.confirm_dangerous = confirm_dangerous
        self.safe_mode = safe_mode
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

    def inspect_screen(self) -> str:
        """Делает скриншот экрана и извлекает текст через OCR."""
        try:
            import mss
            import numpy as np

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                img = np.array(sct.grab(monitor))

            from lumi.desktop.ocr import OCREngine
            ocr = OCREngine()
            text = ocr.extract_text(img)
            if not text or len(text.strip()) < 10:
                return "На экране мало текста или он неразборчивый."
            return f"Текст на экране:\n{text[:2000]}"
        except Exception as e:
            logger.error(f"Ошибка inspect_screen: {e}")
            return f"Не удалось осмотреть экран: {e}"

    def open_application(self, app_name: str) -> str:
        """Открывает приложение из белого списка."""
        if self.safe_mode:
            return "Режим Safe Mode: открытие приложений недоступно."

        app_lower = app_name.lower().strip()
        if app_lower not in [a.lower() for a in self.allowed_apps]:
            return f"Приложение '{app_name}' не в белом списке."

        try:
            subprocess.Popen(app_name, shell=True)
            return f"Приложение '{app_name}' запущено."
        except Exception as e:
            logger.error(f"Ошибка запуска {app_name}: {e}")
            return f"Не удалось запустить '{app_name}': {e}"

    def add_allowed_app(self, app_name: str) -> str:
        """Добавляет приложение в белый список."""
        if app_name.lower() not in [a.lower() for a in self.allowed_apps]:
            self.allowed_apps.append(app_name)
            return f"Приложение '{app_name}' добавлено в белый список."
        return f"Приложение '{app_name}' уже в белом списке."

    def click_text(self, text: str, threshold: int = 60) -> str:
        """Ищет текст на экране и кликает по нему."""
        from lumi.desktop.ocr import OCREngine
        ocr = OCREngine()
        coords = ocr.find_text_coordinates(text, threshold=threshold)
        if coords:
            x, y = coords
            pyautogui.click(x, y)
            return f"Клик по тексту '{text}' выполнен."
        return f"Текст '{text}' не найден на экране."

    def move_to_text(self, text: str, threshold: int = 60) -> str:
        """Перемещает курсор к найденному тексту на экране."""
        from lumi.desktop.ocr import OCREngine
        ocr = OCREngine()
        coords = ocr.find_text_coordinates(text, threshold=threshold)
        if coords:
            x, y = coords
            pyautogui.moveTo(x, y, duration=0.2)
            return f"Курсор перемещён к '{text}'."
        return f"Текст '{text}' не найден на экране."

    def type_text(self, text: str) -> str:
        """Печатает текст на активном окне."""
        try:
            pyautogui.write(text, interval=0.01)
            preview = text[:50] + "..." if len(text) > 50 else text
            return f"Текст введён: '{preview}'"
        except Exception as e:
            logger.error(f"Ошибка type_text: {e}")
            return f"Не удалось ввести текст: {e}"

    def press_keys(self, *keys: str) -> str:
        """Нажимает комбинацию клавиш."""
        if self.safe_mode:
            return "Режим Safe Mode: нажатие клавиш недоступно."

        key_tuple = tuple(k.lower() for k in keys)
        if key_tuple not in self.SAFE_KEY_COMBINATIONS:
            return f"Комбинация {keys} не в списке безопасных комбинаций."

        try:
            pyautogui.hotkey(*keys)
            return f"Комбинация '{'+'.join(keys)}' нажата."
        except Exception as e:
            logger.error(f"Ошибка press_keys {keys}: {e}")
            return f"Не удалось нажать клавиши: {e}"

    def get_clipboard(self) -> str:
        """Возвращает содержимое буфера обмена."""
        try:
            return pyperclip.paste()
        except Exception as e:
            logger.error(f"Ошибка get_clipboard: {e}")
            return f"Не удалось получить буфер обмена: {e}"

    def set_clipboard(self, text: str) -> str:
        """Устанавливает текст в буфер обмена."""
        try:
            pyperclip.copy(text)
            return "Текст скопирован в буфер обмена."
        except Exception as e:
            logger.error(f"Ошибка set_clipboard: {e}")
            return f"Не удалось скопировать в буфер: {e}"

    def open_url(self, url: str) -> str:
        """Открывает URL в браузере по умолчанию."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return f"Открыт URL: {url}"
        except Exception as e:
            logger.error(f"Ошибка open_url: {e}")
            return f"Не удалось открыть URL: {e}"

    def search_web(self, query: str) -> str:
        """Ищет запрос в браузере по умолчанию."""
        import urllib.parse
        encoded = urllib.parse.quote(query)
        return self.open_url(f"https://www.google.com/search?q={encoded}")

    def list_running_apps(self) -> str:
        """Список запущенных приложений."""
        if self.safe_mode:
            return "Режим Safe Mode: список приложений недоступен."
        try:
            import psutil
            apps = set()
            for proc in psutil.process_iter(["name"]):
                try:
                    name = proc.info["name"]
                    if name:
                        apps.add(name)
                except Exception:
                    continue
            sorted_apps = sorted(apps)
            return "Запущенные приложения:\n" + "\n".join(sorted_apps[:30])
        except ImportError:
            return "psutil не установлен. Установите: pip install psutil"
        except Exception as e:
            logger.error(f"Ошибка list_running_apps: {e}")
            return f"Ошибка: {e}"

    def focus_window(self, window_title: str) -> str:
        """Переводит фокус на окно по заголовку."""
        if self.safe_mode:
            return "Режим Safe Mode: управление окнами недоступно."
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].activate()
                return f"Окно '{window_title}' сфокусировано."
            return f"Окно '{window_title}' не найдено."
        except ImportError:
            return "pygetwindow не установлен."
        except Exception as e:
            logger.error(f"Ошибка focus_window: {e}")
            return f"Ошибка: {e}"

    def minimize_window(self, window_title: str) -> str:
        """Сворачивает окно по заголовку."""
        if self.safe_mode:
            return "Режим Safe Mode: управление окнами недоступно."
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].minimize()
                return f"Окно '{window_title}' свёрнуто."
            return f"Окно '{window_title}' не найдено."
        except ImportError:
            return "pygetwindow не установлен."
        except Exception as e:
            logger.error(f"Ошибка minimize_window: {e}")
            return f"Ошибка: {e}"

    def close_window(self, window_title: str) -> str:
        """Закрывает окно по заголовку (требует подтверждения)."""
        if self.safe_mode:
            return "Режим Safe Mode: закрытие окон недоступно."
        if self.confirm_dangerous:
            return f"Требуется подтверждение для закрытия окна '{window_title}'."
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(window_title)
            if windows:
                windows[0].close()
                return f"Окно '{window_title}' закрыто."
            return f"Окно '{window_title}' не найдено."
        except ImportError:
            return "pygetwindow не установлен."
        except Exception as e:
            logger.error(f"Ошибка close_window: {e}")
            return f"Ошибка: {e}"

    def take_screenshot(self, filename: str | None = None) -> str:
        """Делает скриншот и сохраняет в файл."""
        try:
            import mss
            from datetime import datetime

            if filename is None:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{ts}.png"

            screenshot_dir = Path.home() / "Pictures" / "LUMI"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            filepath = screenshot_dir / filename

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct.grab(monitor).save(str(filepath))

            return f"Скриншот сохранён: {filepath}"
        except Exception as e:
            logger.error(f"Ошибка take_screenshot: {e}")
            return f"Не удалось сделать скриншот: {e}"

    def read_file(self, file_path: str) -> str:
        """Читает файл только из разрешённых папок."""
        if self.safe_mode:
            return "Режим Safe Mode: чтение файлов недоступно."
        try:
            path = Path(file_path)
            if not self._is_path_allowed(path):
                return f"Доступ к файлу запрещён: {file_path}"
            if not path.exists():
                return f"Файл не найден: {file_path}"
            content = path.read_text(encoding="utf-8")
            return content[:5000]
        except Exception as e:
            logger.error(f"Ошибка read_file: {e}")
            return f"Ошибка чтения файла: {e}"

    def write_file(self, file_path: str, content: str) -> str:
        """Записывает файл только в разрешённые папки (требует подтверждения)."""
        if self.safe_mode:
            return "Режим Safe Mode: запись файлов недоступно."
        if self.confirm_dangerous:
            return f"Требуется подтверждение для записи в файл: {file_path}"
        try:
            path = Path(file_path)
            if not self._is_path_allowed(path):
                return f"Запись в этот путь запрещена: {file_path}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Файл записан: {file_path}"
        except Exception as e:
            logger.error(f"Ошибка write_file: {e}")
            return f"Ошибка записи файла: {e}"

    def _is_path_allowed(self, path: Path) -> bool:
        """Проверяет, находится ли путь в разрешённой папке."""
        try:
            resolved = path.resolve()
            for allowed in self.allowed_folders:
                allowed_path = Path(allowed).resolve()
                if str(resolved).startswith(str(allowed_path)):
                    return True
        except Exception:
            pass
        return False

    def get_tool_descriptions(self) -> dict[str, str]:
        """Возвращает описания всех инструментов для LLM."""
        return {
            "inspect_screen": "Осмотреть экран и прочитать текст с него через OCR",
            "open_application": "Открыть приложение из белого списка",
            "click_text": "Найти текст на экране и кликнуть по нему",
            "move_to_text": "Переместить курсор к тексту на экране",
            "type_text": "Напечатать текст на активном окне",
            "press_keys": "Нажать комбинацию клавиш",
            "get_clipboard": "Получить текст из буфера обмена",
            "set_clipboard": "Скопировать текст в буфер обмена",
            "open_url": "Открыть веб-страницу в браузере",
            "search_web": "Поиск запроса в браузере",
            "list_running_apps": "Список запущенных приложений",
            "focus_window": "Перевести фокус на окно",
            "minimize_window": "Свернуть окно",
            "close_window": "Закрыть окно (требует подтверждения)",
            "take_screenshot": "Сделать скриншот экрана",
            "read_file": "Прочитать файл из разрешённой папки",
            "write_file": "Записать файл в разрешённую папку (требует подтверждения)",
        }