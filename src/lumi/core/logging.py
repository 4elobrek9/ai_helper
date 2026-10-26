"""Настройка логирования с ротацией логов."""

import logging
import logging.handlers
import sys
from pathlib import Path

from lumi.core.paths import LOGS_DIR, LOG_FILE


def setup_logging(level: int = logging.INFO, log_to_file: bool = True) -> logging.Logger:
    """Настраивает логирование с ротацией файлов.

    Args:
        level: Уровень логирования.
        log_to_file: Писать ли логи в файл.

    Returns:
        Настроенный логгер корневого пакета.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger("lumi")
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Файловый обработчик с ротацией
    if log_to_file:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5 МБ
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Возвращает логгер для указанного модуля."""
    return logging.getLogger(f"lumi.{name}")