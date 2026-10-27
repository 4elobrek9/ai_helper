import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_directory():
    if configured_directory := os.environ.get("LUMI_LOG_DIR"):
        return Path(configured_directory)
    app_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    return app_root / "log"


def configure_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(getattr(handler, "_lumi_file_handler", False) for handler in root.handlers):
        return

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    if not any(getattr(handler, "_lumi_console_handler", False) for handler in root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler._lumi_console_handler = True
        root.addHandler(console_handler)

    candidates = [_log_directory()]
    log_name = os.environ.get("LUMI_LOG_NAME", "lumi")
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", log_name):
        log_name = "lumi"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "LumiAI" / "log")

    last_error = None
    for log_directory in dict.fromkeys(candidates):
        try:
            log_directory.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_directory / f"{log_name}.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        except OSError as error:
            last_error = error
            continue

        file_handler.setFormatter(formatter)
        file_handler._lumi_file_handler = True
        root.addHandler(file_handler)
        root.info(
            "Лог приложения сохраняется в %s",
            log_directory / f"{log_name}.log",
        )
        return

    root.error("Не удалось создать файл логов: %s", last_error)


configure_logging()
