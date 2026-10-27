import logging
import copy
import ctypes
import ipaddress
import os
import re
import socket
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path

import pyautogui


logger = logging.getLogger("lumi.desktop")
_BROWSER_PROCESS_NAMES = {
    "browser.exe",
    "brave.exe",
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "opera.exe",
    "vivaldi.exe",
    "arc.exe",
    "waterfox.exe",
    "librewolf.exe",
}

DESKTOP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get current weather for a named city, or determine the city from "
                "the public IP location if none is given. Use for explicit weather questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "maxLength": 100}},
                "required": [],
            },
        },
    },
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
                        "enum": [
                            "browser",
                            "calculator",
                            "notepad",
                            "explorer",
                            "task manager",
                            "steam",
                            "riot games",
                        ],
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_settings",
            "description": "Open a specific Windows Settings page that the user requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["display", "sound", "bluetooth", "network", "apps", "update"],
                    }
                },
                "required": ["section"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "steam_search",
            "description": (
                "Open the requested game or listing search inside the Steam client."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 200}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "steam_launch_game",
            "description": (
                "Launch an installed Steam game by matching its name in local Steam "
                "library manifests. Never install a game or run a command."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 120}},
                "required": ["query"],
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
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": (
                "Open a public web search visibly in the user's default browser. "
                "Use this for general internet searches and summarize the visible results."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 300}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": (
                "Open visible YouTube search results for a query. Afterward use the "
                "returned local OCR text and browser_click a visible video title only "
                "when the user explicitly asks to open a result."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 200}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_search",
            "description": (
                "Search Yandex Market for products in the user's default browser. "
                "This only searches and displays results; never order or purchase."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 200}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": (
                "Open a user-requested public HTTP or HTTPS page visibly in the default browser."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "maxLength": 2000}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_inspect",
            "description": (
                "Bring the user's visible browser forward and inspect its current screen."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": (
                "Click a named visible browser-page control using OCR. "
                "Never click purchase, payment, checkout, sign-in or account controls."
            ),
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 100}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": (
                "Type non-sensitive user-provided text in the focused browser field. "
                "Never enter passwords, payment details, or private credentials."
            ),
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 300}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the visible browser page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "pages": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_key",
            "description": (
                "Perform a safe browser navigation shortcut. Do not submit forms or "
                "confirm purchases."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "back",
                            "forward",
                            "refresh",
                            "find",
                            "address",
                            "new_tab",
                            "close_tab",
                            "next_tab",
                            "previous_tab",
                        ],
                    }
                },
                "required": ["action"],
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
_WINDOWS_SETTINGS = {
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth",
    "network": "ms-settings:network",
    "apps": "ms-settings:appsfeatures",
    "update": "ms-settings:windowsupdate",
}
_KEY_SHORTCUTS = {
    "ctrl+a", "ctrl+c", "ctrl+v", "ctrl+s", "alt+tab", "ctrl+shift+esc", "win+d"
}
_SIMPLE_KEYS = {"enter", "esc", "tab", "space", "up", "down", "left", "right", "home", "end"}


def get_desktop_tools():
    tools = copy.deepcopy(DESKTOP_TOOLS)
    app_tool = next(
        tool for tool in tools
        if tool["function"]["name"] == "open_application"
    )
    from skills import get_user_skill_launchers

    configured_launchers = get_user_skill_launchers()
    app_tool["function"]["parameters"]["properties"]["name"]["enum"].extend(
        name for name in configured_launchers
        if name.casefold() not in _APPLICATIONS
    )
    from default_skills import filter_desktop_tools

    return filter_desktop_tools(tools)


def _browser_window_handle(timeout=5):
    if os.name != "nt":
        return None

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    enum_callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.IsWindow.restype = ctypes.c_bool
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.EnumWindows.argtypes = [
        enum_callback_type,
        ctypes.c_void_p,
    ]
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    process_query_limited_information = 0x1000
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = []

        @enum_callback_type
        def enum_callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            process_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            process = kernel32.OpenProcess(
                process_query_limited_information,
                False,
                process_id.value,
            )
            if not process:
                return True
            try:
                size = ctypes.c_ulong(32768)
                executable = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(
                    process,
                    0,
                    executable,
                    ctypes.byref(size),
                ):
                    if Path(executable.value).name.casefold() in _BROWSER_PROCESS_NAMES:
                        found.append(hwnd)
            finally:
                kernel32.CloseHandle(process)
            return True

        user32.EnumWindows(enum_callback, 0)
        if found:
            return found[0]
        time.sleep(0.15)
    return None


def _focus_browser_window(hwnd=None, *, required=True):
    hwnd = hwnd or _browser_window_handle()
    if hwnd is None:
        if not required:
            logger.warning("Не удалось найти окно браузера для перевода на передний план.")
            return None
        raise RuntimeError(
            "Не нашла окно поддерживаемого браузера. Откройте браузер по умолчанию "
            "и повторите команду."
        )
    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.ShowWindow(hwnd, 9)
    if not user32.SetForegroundWindow(hwnd):
        if required:
            raise RuntimeError("Windows не разрешила переключиться на окно браузера.")
        logger.warning(
            "Страница открыта, но Windows не разрешила вывести браузер на передний план."
        )
        return None
    time.sleep(0.2)
    return hwnd


def _open_default_browser(url, require_window=False):
    if not webbrowser.open(url, new=2):
        raise RuntimeError("Windows не смогла открыть страницу в браузере по умолчанию.")
    if not require_window:
        return None
    hwnd = _browser_window_handle(timeout=5)
    if hwnd is None:
        raise RuntimeError(
            "Страница открыта, но LUMI не распознала окно браузера для управления."
        )
    return hwnd


def _validate_public_url(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("Укажите ссылку длиной до 2000 символов.")
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Можно открывать только публичные ссылки HTTP или HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("Ссылки с именем пользователя или паролем запрещены.")
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Локальные и внутренние адреса не открываются.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved_addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(
                    hostname,
                    None,
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as error:
            raise ValueError("Имя публичного сайта не удалось проверить.") from error
        if not resolved_addresses or any(
            not address.is_global for address in resolved_addresses
        ):
            raise ValueError("Адрес сайта разрешается во внутреннюю или локальную сеть.")
    else:
        if not address.is_global:
            raise ValueError("Локальные и частные IP-адреса не открываются.")
    return parsed.geturl()


def _browser_screenshot():
    from command_OCR import get_screen_image

    return get_screen_image()


def _steam_library_paths():
    candidates = []
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Valve\Steam",
        ) as key:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            candidates.append(Path(steam_path))
    except (ImportError, OSError):
        pass

    program_files = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if program_files:
        candidates.append(Path(program_files) / "Steam")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Steam")

    libraries = set()
    for steam_path in candidates:
        if (steam_path / "steam.exe").is_file():
            libraries.add(steam_path / "steamapps")
        library_file = steam_path / "steamapps" / "libraryfolders.vdf"
        if not library_file.is_file():
            continue
        try:
            contents = library_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.exception("Не удалось прочитать список библиотек Steam: %s", library_file)
            continue
        for library_path in re.findall(r'"path"\s+"([^"]+)"', contents):
            libraries.add(Path(library_path.replace("\\\\", "\\")) / "steamapps")
    return sorted(libraries)


def _find_installed_steam_game(query):
    normalized_query = " ".join(query.casefold().split())
    if not normalized_query:
        return None
    exact_matches = []
    partial_matches = []
    for library in _steam_library_paths():
        try:
            manifests = library.glob("appmanifest_*.acf")
            for manifest in manifests:
                match = re.search(
                    r'"appid"\s+"(\d+)"[\s\S]*?"name"\s+"([^"]+)"',
                    manifest.read_text(encoding="utf-8", errors="replace"),
                )
                if not match:
                    continue
                app_id, name = match.groups()
                normalized_name = " ".join(name.casefold().split())
                if normalized_name == normalized_query:
                    exact_matches.append((app_id, name))
                elif normalized_query in normalized_name or normalized_name in normalized_query:
                    partial_matches.append((app_id, name))
        except OSError:
            logger.exception("Не удалось прочитать установленные игры из %s", library)
    if exact_matches:
        return exact_matches[0]
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        names = ", ".join(name for _, name in partial_matches[:5])
        raise ValueError(
            f"Нашлось несколько похожих игр Steam ({names}). Уточните название."
        )
    return None


def _open_steam_uri(uri):
    if os.name == "nt":
        try:
            os.startfile(uri)
            return
        except OSError as error:
            raise RuntimeError(f"Не удалось передать ссылку Steam Windows: {error}") from error
    if not webbrowser.open(uri):
        raise RuntimeError("Не удалось открыть ссылку Steam.")


def _find_riot_client():
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    candidates = [
        Path(root) / "Riot Games" / "Riot Client" / "RiotClientServices.exe"
        for root in roots
        if root
    ]
    candidates.append(
        Path(os.environ.get("SystemDrive", "C:") + "\\")
        / "Riot Games"
        / "Riot Client"
        / "RiotClientServices.exe"
    )
    return next((path for path in candidates if path.is_file()), None)


def execute_desktop_tool(name, arguments):
    if name == "get_weather":
        city = arguments.get("city")
        if city is not None and (
            not isinstance(city, str) or len(city.strip()) > 100
        ):
            raise ValueError("Название города должно быть не длиннее 100 символов.")
        from command import get_weather

        weather = get_weather(city=city)
        if not isinstance(weather, dict):
            raise RuntimeError("Сервис погоды вернул некорректный ответ.")
        return {
            "content": (
                f"Сейчас в городе {weather['city']}: {weather['temp']} градусов, "
                f"{weather['weather']}."
            )
        }

    if name == "inspect_screen":
        from command_OCR import get_screen_image

        return {
            "content": "Снимок выбранного основного экрана передан vision-модели.",
            "image": get_screen_image(),
        }

    if name == "open_application":
        application = arguments.get("name", "").casefold()
        if application == "browser":
            _open_default_browser("https://www.google.com/")
        elif application == "steam":
            _open_steam_uri("steam://open/main")
        elif application == "riot games":
            executable = _find_riot_client()
            if executable is None:
                raise FileNotFoundError(
                    "Не нашла Riot Client в стандартных папках установки. "
                    "Установите Riot Client или укажите его EXE как пользовательский навык."
                )
            subprocess.Popen(
                [str(executable)],
                cwd=str(executable.parent),
            )
        elif application in _APPLICATIONS:
            subprocess.Popen([_APPLICATIONS[application]])
        else:
            from skills import get_user_skill_launchers

            configured_launchers = get_user_skill_launchers()
            executable = next(
                (
                    Path(path)
                    for skill_name, path in configured_launchers.items()
                    if skill_name.casefold() == application
                ),
                None,
            )
            if (
                executable is None
                or executable.suffix.casefold() != ".exe"
                or not executable.is_file()
            ):
                raise ValueError(
                    "Можно открыть только встроенное приложение или .exe, "
                    "который пользователь явно добавил в навык."
                )
            subprocess.Popen([str(executable)], cwd=str(executable.parent))
        return {"content": f"Открыто приложение: {application}."}

    if name == "open_settings":
        section = arguments.get("section")
        uri = _WINDOWS_SETTINGS.get(section)
        if uri is None:
            raise ValueError("Этот раздел Windows Settings не разрешён.")
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", uri])
        elif not webbrowser.open(uri):
            raise RuntimeError("Не удалось открыть раздел настроек системы.")
        return {"content": f"Открыты системные настройки: {section}."}

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

    if name == "browser_search":
        query = arguments.get("query", "").strip()
        if not query or len(query) > 300:
            raise ValueError("Запрос для поиска должен содержать от 1 до 300 символов.")
        url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query})
        _open_default_browser(url)
        focused = _focus_browser_window(required=False)
        time.sleep(1.5)
        content = f"Открыл видимый поиск Google в браузере по умолчанию: {query}"
        if not focused:
            content += (
                " Не удалось подтвердить, что окно браузера на переднем плане; "
                "проверьте его вручную."
            )
        return {
            "content": content,
            "image": _browser_screenshot() if focused else None,
        }

    if name == "steam_search":
        query = arguments.get("query", "").strip()
        if not query or len(query) > 200:
            raise ValueError("Запрос Steam должен содержать от 1 до 200 символов.")
        url = "https://store.steampowered.com/search/?" + urllib.parse.urlencode(
            {"term": query}
        )
        _open_steam_uri("steam://openurl/" + urllib.parse.quote(url, safe=":/?=&"))
        return {
            "content": (
                f"Открыл страницу поиска магазина Steam по запросу «{query}» "
                "в клиенте Steam."
            )
        }

    if name == "steam_launch_game":
        query = arguments.get("query", "").strip()
        if not query or len(query) > 120:
            raise ValueError("Укажите название игры длиной до 120 символов.")
        match = _find_installed_steam_game(query)
        if match is None:
            return {
                "content": (
                    f"В установленных библиотеках Steam не нашла игру «{query}». "
                    "Ничего не установлено и не запущено."
                )
            }
        app_id, game_name = match
        _open_steam_uri(f"steam://rungameid/{app_id}")
        return {"content": f"Передала Steam запрос на запуск игры «{game_name}»."}

    if name == "youtube_search":
        query = arguments.get("query", "").strip()
        if not query or len(query) > 200:
            raise ValueError("Запрос YouTube должен содержать от 1 до 200 символов.")
        url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
            {"search_query": query}
        )
        _open_default_browser(url)
        focused = _focus_browser_window(required=False)
        time.sleep(2)
        content = (
            f"Открыл видимую страницу результатов YouTube для «{query}». "
            "Результат не запускался автоматически."
        )
        if not focused:
            content += (
                " Не удалось подтвердить, что окно браузера на переднем плане; "
                "проверьте его вручную."
            )
        return {
            "content": content,
            "image": _browser_screenshot() if focused else None,
        }

    if name == "market_search":
        query = arguments.get("query", "").strip()
        if not query or len(query) > 200:
            raise ValueError("Запрос для Яндекс Маркета должен содержать до 200 символов.")
        url = "https://market.yandex.ru/search?" + urllib.parse.urlencode(
            {"text": query}
        )
        _open_default_browser(url)
        focused = _focus_browser_window(required=False)
        time.sleep(2)
        content = (
            f"Открыл визуальные результаты Яндекс Маркета для «{query}». "
            "Ничего не добавлял в корзину и не покупал."
        )
        if not focused:
            content += (
                " Не удалось подтвердить, что окно браузера на переднем плане; "
                "проверьте его вручную."
            )
        return {
            "content": content,
            "image": _browser_screenshot() if focused else None,
        }

    if name == "browser_navigate":
        url = _validate_public_url(arguments.get("url"))
        _open_default_browser(url)
        focused = _focus_browser_window(required=False)
        time.sleep(1.5)
        content = f"Открыл страницу в видимом браузере: {url}"
        if not focused:
            content += (
                " Не удалось подтвердить, что окно браузера на переднем плане; "
                "проверьте его вручную."
            )
        return {
            "content": content,
            "image": _browser_screenshot() if focused else None,
        }

    if name == "browser_inspect":
        _focus_browser_window()
        return {
            "content": "Сделан снимок видимой вкладки браузера для анализа.",
            "image": _browser_screenshot(),
        }

    if name == "browser_click":
        text = arguments.get("text", "").strip()
        if not text or len(text) > 100:
            raise ValueError("Укажите короткую подпись видимого элемента страницы.")
        if any(
            term in text.casefold()
            for term in (
                "купить",
                "оплатить",
                "заказать",
                "корзин",
                "checkout",
                "payment",
                "sign in",
                "log in",
                "войти",
                "оплата",
            )
        ):
            raise ValueError(
                "Операции покупки, оплаты и входа не выполняются автоматически."
            )
        _focus_browser_window()
        from command_OCR import click_to_text

        if not click_to_text(text, threshold=78, clicks=1):
            return {
                "content": f"Не нашла на странице видимый элемент «{text}».",
                "image": _browser_screenshot(),
            }
        time.sleep(0.8)
        return {
            "content": f"Нажала видимый элемент «{text}» в браузере.",
            "image": _browser_screenshot(),
        }

    if name == "browser_type":
        text = arguments.get("text", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 300:
            raise ValueError("Введите обычный текст длиной от 1 до 300 символов.")
        _focus_browser_window()
        import pyperclip

        previous_clipboard = pyperclip.paste()
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        finally:
            pyperclip.copy(previous_clipboard)
        return {
            "content": "Ввела запрошенный текст в активное поле видимого браузера.",
            "image": _browser_screenshot(),
        }

    if name == "browser_scroll":
        direction = arguments.get("direction")
        if direction not in {"up", "down"}:
            raise ValueError("Можно прокрутить страницу только вверх или вниз.")
        pages = arguments.get("pages", 1)
        if not isinstance(pages, int) or not 1 <= pages <= 5:
            raise ValueError("Количество прокруток должно быть от 1 до 5.")
        _focus_browser_window()
        pyautogui.scroll(pages * (5 if direction == "up" else -5))
        return {
            "content": f"Прокрутила страницу {direction} ({pages} шагов).",
            "image": _browser_screenshot(),
        }

    if name == "browser_key":
        action = arguments.get("action")
        shortcuts = {
            "back": ("alt", "left"),
            "forward": ("alt", "right"),
            "refresh": ("ctrl", "r"),
            "find": ("ctrl", "f"),
            "address": ("ctrl", "l"),
            "new_tab": ("ctrl", "t"),
            "close_tab": ("ctrl", "w"),
            "next_tab": ("ctrl", "tab"),
            "previous_tab": ("ctrl", "shift", "tab"),
        }
        keys = shortcuts.get(action)
        if keys is None:
            raise ValueError("Эта команда управления браузером не поддерживается.")
        _focus_browser_window()
        pyautogui.hotkey(*keys)
        return {
            "content": f"Выполнила действие «{action}» в браузере.",
            "image": _browser_screenshot(),
        }

    logger.warning("Модель запросила неизвестный инструмент: %s", name)
    raise ValueError(f"Неизвестный инструмент: {name}")
