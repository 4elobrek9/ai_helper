import sqlite3
from contextlib import closing

from app_paths import data_path


DEFAULT_SKILLS = (
    {
        "id": "weather",
        "name": "Погода",
        "description": "Скажи «погода» или «какая погода в Москве».",
    },
    {
        "id": "screen_click_text",
        "name": "Нажать на текст на экране",
        "description": "Скажи «нажми на [надпись]» или «кликни на [надпись]».",
    },
    {
        "id": "screen_read_text",
        "name": "Прочитать текст на экране",
        "description": "Скажи «прочитай текст на экране».",
    },
    {
        "id": "screen_move_cursor",
        "name": "Навести курсор на текст",
        "description": "Скажи «наведи на [надпись]».",
    },
    {
        "id": "screen_vision",
        "name": "Анализ экрана",
        "description": (
            "Скажи «что на экране?», «посмотри на экран» или «прочитай экран»."
        ),
    },
    {
        "id": "open_application",
        "name": "Открыть приложение",
        "description": (
            "Например, скажи «открой блокнот», «запусти калькулятор», "
            "«открой Steam» или «запусти Riot Games»."
        ),
    },
    {
        "id": "type_text",
        "name": "Ввести текст",
        "description": "Попроси ввести указанный текст в активное окно.",
    },
    {
        "id": "press_keys",
        "name": "Нажать клавиши",
        "description": (
            "Поддерживаются Enter, Esc, Tab, стрелки, Ctrl+A/C/V/S, "
            "Alt+Tab и Win+D."
        ),
    },
    {
        "id": "browser_search",
        "name": "Искать в интернете",
        "description": (
            "Ищи в интернете и на YouTube; для сложной просьбы опиши, что искать, "
            "куда перейти и какой результат открыть."
        ),
    },
    {
        "id": "voice_interrupt",
        "name": "Перебивать голосом",
        "description": (
            "Когда LUMI озвучивает ответ, любая распознанная речь остановит текущую "
            "генерацию и запустит обработку новой фразы."
        ),
    },
    {
        "id": "market_search",
        "name": "Искать товары на Яндекс Маркете",
        "description": "Скажи «найди на Яндекс Маркете [товар]» для визуального поиска.",
    },
    {
        "id": "browser_navigate",
        "name": "Открыть страницу в браузере",
        "description": "Попроси открыть публичную страницу по HTTP/HTTPS.",
    },
    {
        "id": "browser_inspect",
        "name": "Прочитать страницу браузера",
        "description": "Попроси посмотреть, что отображено в открытом браузере.",
    },
    {
        "id": "browser_click",
        "name": "Нажать элемент браузера",
        "description": "Назови видимую ссылку или безопасный элемент страницы.",
    },
    {
        "id": "browser_type",
        "name": "Ввести текст в браузере",
        "description": "Попроси ввести текст в уже выбранное поле страницы.",
    },
    {
        "id": "browser_scroll",
        "name": "Прокрутить страницу",
        "description": "Скажи «прокрути страницу вниз» или «прокрути вверх».",
    },
    {
        "id": "browser_key",
        "name": "Управлять вкладкой браузера",
        "description": "Доступны поиск по странице, адресная строка, назад/вперёд и вкладки.",
    },
    {
        "id": "steam_control",
        "name": "Управлять Steam",
        "description": (
            "Открой Steam, найди страницу игры в магазине или запусти уже "
            "установленную игру по точному названию."
        ),
    },
    {
        "id": "system_settings",
        "name": "Открывать настройки Windows",
        "description": (
            "Открой раздел «экран», «звук», «Bluetooth», «сеть», "
            "«установленные приложения» или «обновление Windows»."
        ),
    },
)
_ALWAYS_AVAILABLE_COMMANDS = (
    "Скажи «какие команды есть?» или «что ты умеешь?» — покажу включённые команды.",
    "Скажи «стоп» или «отмена», чтобы немедленно остановить ответ.",
)
_TOOL_GROUPS = {
    "weather": {"get_weather"},
    "screen_read_text": {"read_screen_text"},
    "screen_move_cursor": {"move_to_text"},
    "screen_click_text": {"click_text"},
    "screen_vision": {"inspect_screen"},
    "open_application": {"open_application"},
    "type_text": {"type_text"},
    "press_keys": {"press_keys"},
    "browser_search": {"browser_search", "youtube_search"},
    "market_search": {"market_search"},
    "browser_navigate": {"browser_navigate"},
    "browser_inspect": {"browser_inspect"},
    "browser_click": {"browser_click"},
    "browser_type": {"browser_type"},
    "browser_scroll": {"browser_scroll"},
    "browser_key": {"browser_key"},
    "steam_control": {"steam_search", "steam_launch_game"},
    "system_settings": {"open_settings"},
}


def _connect():
    return closing(sqlite3.connect(data_path("config.db")))


def _ensure_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS default_skills (
            skill_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    existing = {
        skill_id: enabled
        for skill_id, enabled in connection.execute(
            "SELECT skill_id, enabled FROM default_skills"
        ).fetchall()
    }
    legacy_groups = {
        "screen_read_text": "screen_ocr",
        "screen_move_cursor": "screen_ocr",
        "screen_click_text": "screen_ocr",
        "open_application": "desktop_control",
        "type_text": "desktop_control",
        "press_keys": "desktop_control",
    }
    for skill in DEFAULT_SKILLS:
        skill_id = skill["id"]
        if skill_id in existing:
            continue
        legacy_group = legacy_groups.get(skill_id)
        enabled = existing.get(legacy_group, 1)
        connection.execute(
            "INSERT INTO default_skills (skill_id, enabled) VALUES (?, ?)",
            (skill_id, enabled),
        )
    connection.commit()


def enabled_skill_ids():
    with _connect() as connection:
        _ensure_table(connection)
        rows = connection.execute(
            "SELECT skill_id FROM default_skills WHERE enabled = 1"
        ).fetchall()
    return {row[0] for row in rows} | {"assistant_control"}


def is_skill_enabled(skill_id):
    return skill_id in enabled_skill_ids()


def set_skill_enabled(skill_id, enabled):
    if skill_id not in {skill["id"] for skill in DEFAULT_SKILLS}:
        raise ValueError("Неизвестный встроенный навык.")
    with _connect() as connection:
        _ensure_table(connection)
        connection.execute(
            "UPDATE default_skills SET enabled = ? WHERE skill_id = ?",
            (int(bool(enabled)), skill_id),
        )
        connection.commit()


def get_command_help():
    enabled = enabled_skill_ids()
    lines = [
        f"- {skill['name']}: {skill['description']}"
        for skill in DEFAULT_SKILLS
        if skill["id"] in enabled
    ]
    return "\n".join([*lines, *_ALWAYS_AVAILABLE_COMMANDS])


def get_default_skill_prompt():
    return (
        "Встроенные команды LUMI, которые сейчас доступны пользователю:\n"
        f"{get_command_help()}\n"
        "Если пользователь спрашивает о командах или возможностях, перечисли "
        "именно эти команды. Не утверждай, что умеешь выполнять действия, "
        "которых нет в доступных инструментах."
    )


def filter_desktop_tools(tools):
    enabled = enabled_skill_ids()
    allowed_names = set()
    for skill_id, tool_names in _TOOL_GROUPS.items():
        if skill_id in enabled:
            allowed_names.update(tool_names)
    return [
        tool for tool in tools
        if tool["function"]["name"] in allowed_names
    ]
