import sqlite3
from contextlib import closing
from pathlib import Path

from app_paths import data_path


DEVELOPER_SKILLS = (
    {
        "id": "ocr-screen-control",
        "name": "OCR и управление экраном",
        "description": "Локальное чтение текста с экрана и безопасные действия.",
    },
)
RESERVED_SKILL_NAMES = {
    "screensage",
    "calculator",
    "notepad",
    "explorer",
    "task manager",
    "browser",
    "ocr и управление экраном",
}


def list_user_skills():
    with closing(sqlite3.connect(data_path("config.db"))) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                description TEXT NOT NULL,
                launch_path TEXT
            )
            """
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(user_skills)")
        }
        if "launch_path" not in columns:
            connection.execute("ALTER TABLE user_skills ADD COLUMN launch_path TEXT")
        rows = connection.execute(
            "SELECT id, name, description, launch_path FROM user_skills "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "launch_path": row[3],
        }
        for row in rows
    ]


def get_user_skill_prompt():
    skills = list_user_skills()
    if not skills:
        return ""
    entries = "\n".join(
        f"- {skill['name']}: {skill['description']}" for skill in skills
    )
    return (
        "Учитывай следующие инструкции пользовательских навыков, когда они "
        "подходят к запросу. Сами по себе они не дают разрешения выполнять "
        "действия на компьютере:\n"
        f"{entries}"
    )


def get_user_skill_launchers():
    return {
        skill["name"]: skill["launch_path"]
        for skill in list_user_skills()
        if skill["launch_path"]
    }


def add_user_skill(name, description, launch_path=None):
    name = (name or "").strip()
    description = (description or "").strip()
    if not name or len(name) > 60:
        raise ValueError("Название навыка должно содержать от 1 до 60 символов.")
    if not description or len(description) > 500:
        raise ValueError("Описание навыка должно содержать от 1 до 500 символов.")
    if name.casefold() in RESERVED_SKILL_NAMES or any(
        name.casefold() == skill["name"].casefold()
        for skill in DEVELOPER_SKILLS
    ):
        raise ValueError("Это название зарезервировано для каталога разработчика.")
    if name.casefold() == "screensage":
        raise ValueError("Это название зарезервировано для ScreenSage.")
    normalized_path = None
    if launch_path and launch_path.strip():
        candidate = Path(launch_path.strip()).expanduser()
        if not candidate.is_absolute() or candidate.suffix.casefold() != ".exe":
            raise ValueError("Укажите полный путь к Windows-приложению .exe.")
        try:
            normalized_path = str(candidate.resolve(strict=True))
        except OSError as error:
            raise ValueError("Файл приложения не найден.") from error
        if not Path(normalized_path).is_file():
            raise ValueError("Путь должен указывать на файл приложения.")

    with closing(sqlite3.connect(data_path("config.db"))) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                description TEXT NOT NULL,
                launch_path TEXT
            )
            """
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(user_skills)")
        }
        if "launch_path" not in columns:
            connection.execute("ALTER TABLE user_skills ADD COLUMN launch_path TEXT")
        try:
            connection.execute(
                "INSERT INTO user_skills (name, description, launch_path) "
                "VALUES (?, ?, ?)",
                (name, description, normalized_path),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Навык «{name}» уже добавлен.") from error
        connection.commit()


def remove_user_skill(skill_id):
    if not isinstance(skill_id, int) or skill_id <= 0:
        raise ValueError("Не удалось определить навык для удаления.")
    with closing(sqlite3.connect(data_path("config.db"))) as connection:
        result = connection.execute(
            "DELETE FROM user_skills WHERE id = ?", (skill_id,)
        )
        if result.rowcount == 0:
            raise ValueError("Навык уже удалён или не найден.")
        connection.commit()
