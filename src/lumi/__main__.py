"""Точка входа в LUMI AI."""

from __future__ import annotations

import sys
import os

from lumi.core.app import get_app, setup_signal_handlers
from lumi.core.logging import setup_logging, get_logger
from lumi.core.paths import ensure_dirs

logger = get_logger("lumi")


def main() -> None:
    """Запуск приложения LUMI AI."""
    try:
        ensure_dirs()
        setup_logging()
        setup_signal_handlers()

        lumi_app = get_app()
        lumi_app.init()

        # Запуск голосового цикла в фоне
        lumi_app.start_voice_loop()

        # Запуск GUI
        from lumi.gui.main import run_app
        run_app(lumi_app)

    except KeyboardInterrupt:
        print("\n👋 LUMI AI остановлен пользователем.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger.exception("Критическая ошибка при запуске")
        sys.exit(1)


if __name__ == "__main__":
    main()