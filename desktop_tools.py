import logging
import subprocess
import time
import webbrowser

import pyautogui


logger = logging.getLogger("lumi.desktop")

DESKTOP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_screen",
            "description": "Look at the user's selected primary screen when asked about its contents.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open an allowed Windows application when the user asks you to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": ["browser", "calculator", "notepad", "explorer", "task manager"],
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_text",
            "description": "Click one visible UI control by its exact text, only when the user asks for that action.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently focused field when the user asks you to enter it.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": "Press one approved key or shortcut when the user asks you to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "enum": [
                            "enter", "esc", "tab", "space", "up", "down", "left", "right",
                            "home", "end", "ctrl+a", "ctrl+c", "ctrl+v", "ctrl+s",
                            "alt+tab", "ctrl+shift+esc", "win+d",
                        ],
                    }
                },
                "required": ["keys"],
            },
        },
    },
]

_APPLICATIONS = {
    "calculator": "calc.exe",
    "notepad": "notepad.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
}
_KEY_SHORTCUTS = {
    "ctrl+a", "ctrl+c", "ctrl+v", "ctrl+s", "alt+tab", "ctrl+shift+esc", "win+d"
}
_SIMPLE_KEYS = {"enter", "esc", "tab", "space", "up", "down", "left", "right", "home", "end"}


def execute_desktop_tool(name, arguments):
    if name == "inspect_screen":
        from command_OCR import get_screen_image

        return {
            "content": "Снимок выбранного основного экрана передан vision-модели.",
            "image": get_screen_image(),
        }

    if name == "open_application":
        application = arguments.get("name", "").casefold()
        if application == "browser":
            webbrowser.open("about:blank")
        elif application in _APPLICATIONS:
            subprocess.Popen([_APPLICATIONS[application]])
        else:
            raise ValueError("Можно открыть только приложение из разрешённого списка.")
        return {"content": f"Открыто приложение: {application}."}

    if name == "click_text":
        text = arguments.get("text", "").strip()
        if not text or len(text) > 120:
            raise ValueError("Для щелчка укажите короткую подпись элемента.")
        from command_OCR import click_to_text

        if not click_to_text(text, threshold=70, clicks=1):
            return {"content": f"Не нашла на экране элемент «{text}»; щелчок не выполнен."}
        return {"content": f"Выполнен один щелчок по «{text}»."}

    if name == "type_text":
        text = arguments.get("text", "")
        if not isinstance(text, str) or not text or len(text) > 500:
            raise ValueError("Можно ввести текст длиной от 1 до 500 символов.")
        import pyperclip

        previous_clipboard = pyperclip.paste()
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)
        finally:
            pyperclip.copy(previous_clipboard)
        return {"content": f"Введён текст ({len(text)} символов)."}

    if name == "press_keys":
        keys = arguments.get("keys", "").casefold()
        if keys in _KEY_SHORTCUTS:
            pyautogui.hotkey(*keys.split("+"))
        elif keys in _SIMPLE_KEYS:
            pyautogui.press(keys)
        else:
            raise ValueError("Эта клавиша или комбинация не разрешена.")
        return {"content": f"Нажата клавиша: {keys}."}

    logger.warning("Модель запросила неизвестный инструмент: %s", name)
    raise ValueError(f"Неизвестный инструмент: {name}")
