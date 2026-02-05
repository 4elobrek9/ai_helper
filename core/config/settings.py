import os
import sqlite3

DEFAULT_SYSTEM_PROMPT = (
    "Ответь на русском и достаточно понятно (говори от женского рода милой доброй девушки "
    "c интересной жизнью, говори МАКСИМАЛЬНО человечно, тебя зовут Люмия или просто Люми, "
    "любишь паучью лилию). При ответе не стоит здороваться или что-то типо того."
)
DB_PATH = "config.db"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            api_key TEXT,
            prompt TEXT,
            input_device TEXT,
            output_device TEXT,
            porcupine_key TEXT
        )
        """
    )
    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    for column, sql_type in [
        ("input_device", "TEXT"),
        ("output_device", "TEXT"),
        ("porcupine_key", "TEXT"),
    ]:
        if column not in columns:
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {column} {sql_type}")
    conn.commit()
    conn.close()


def save_settings(api_key, prompt, input_dev, output_dev, porcupine_key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings")
    cursor.execute(
        "INSERT INTO settings (api_key, prompt, input_device, output_device, porcupine_key) VALUES (?, ?, ?, ?, ?)",
        (api_key, prompt, input_dev, output_dev, porcupine_key),
    )
    conn.commit()
    conn.close()


def load_settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT api_key, prompt, input_device, output_device, porcupine_key FROM settings LIMIT 1")
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    if not row:
        return "", "", None, None, ""
    return tuple(value if value is not None else "" for value in row)


def get_system_prompt_from_db() -> str:
    if not os.path.exists(DB_PATH):
        return DEFAULT_SYSTEM_PROMPT
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT prompt FROM settings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row and row[0] and row[0].strip():
            return row[0].strip()
    except Exception:
        pass
    return DEFAULT_SYSTEM_PROMPT


def get_porcupine_key_from_db():
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT porcupine_key FROM settings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row and row[0] and row[0].strip():
            return row[0].strip()
    except Exception:
        return None
    return None
