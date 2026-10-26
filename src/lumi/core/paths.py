"""Пути к директориям и файлам проекта LUMI AI."""

from pathlib import Path

# Корень проекта (на два уровня выше src/lumi/core)
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

# Директории
SRC_DIR: Path = PROJECT_ROOT / "src"
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
AUDIO_DIR: Path = PROJECT_ROOT / "audio"
MODELS_DIR: Path = PROJECT_ROOT / "models"
DATA_DIR: Path = PROJECT_ROOT / "data"
LOGS_DIR: Path = PROJECT_ROOT / "logs"
SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"
TESTS_DIR: Path = PROJECT_ROOT / "tests"
DOCS_DIR: Path = PROJECT_ROOT / "docs"
LEGACY_DIR: Path = PROJECT_ROOT / "_legacy"

# Файлы конфигурации и данных
CONFIG_FILE: Path = PROJECT_ROOT / "lumi_config.yaml"
CONFIG_DB: Path = DATA_DIR / "config.db"
CHAT_DB: Path = DATA_DIR / "chat.db"
LOG_FILE: Path = LOGS_DIR / "lumi.log"

# Иконки
ICON_FILE: Path = ASSETS_DIR / "icon.png"
APP_ICON_FILE: Path = ASSETS_DIR / "app_icon.png"

# Аудио
START_SOUND: Path = AUDIO_DIR / "right.mp3"
ERROR_SOUND: Path = AUDIO_DIR / "lie.mp3"

# Модели
WAKE_WORD_MODEL: Path = MODELS_DIR / "lumia.ppn"


def ensure_dirs() -> None:
    """Создаёт все необходимые директории."""
    for d in [DATA_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)