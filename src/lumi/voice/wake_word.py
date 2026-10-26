"""Wake-word детекция (Porcupine / консольный режим)."""

from __future__ import annotations

import logging
from typing import Optional

from lumi.core.logging import get_logger

logger = get_logger("voice.wake_word")


class WakeWordEngine:
    """Базовый класс для wake-word детекции."""

    def __init__(self, keyword: str = "Люми") -> None:
        self.keyword = keyword

    def detect(self, audio_data: bytes) -> bool:
        """Проверяет наличие wake-word в аудиоданных."""
        return False

    def is_available(self) -> bool:
        """Проверяет доступность движка."""
        return True


class ConsoleWakeWordEngine(WakeWordEngine):
    """Консольный wake-word — для тестирования без Porcupine."""

    def detect(self, audio_data: bytes) -> bool:
        return False


class PorcupineWakeWordEngine(WakeWordEngine):
    """Wake-word через Picovoice Porcupine."""

    def __init__(
        self,
        keyword: str = "Люми",
        access_key: str = "",
        model_path: str = "models/lumia.ppn",
    ) -> None:
        super().__init__(keyword)
        self.access_key = access_key
        self.model_path = model_path
        self._porcupine: Optional[object] = None
        self._initialized = False

    def _ensure_loaded(self) -> None:
        if self._initialized:
            return
        try:
            import pvporcupine
            self._porcupine = pvporcupine.create(
                access_key=self.access_key,
                keyword_paths=[self.model_path],
            )
            self._initialized = True
            logger.info("Porcupine wake-word инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации Porcupine: {e}")
            self._porcupine = None
            self._initialized = True

    def detect(self, audio_data: bytes) -> bool:
        self._ensure_loaded()
        if self._porcupine is None:
            return False
        try:
            import struct
            pcm = struct.unpack(f"h*{len(audio_data) // 2}", audio_data)
            return self._porcupine.process(pcm) >= 0
        except Exception as e:
            logger.error(f"Ошибка детекции wake-word: {e}")
            return False

    def is_available(self) -> bool:
        self._ensure_loaded()
        return self._porcupine is not None

    def release(self) -> None:
        """Освобождает ресурсы Porcupine."""
        if self._porcupine is not None:
            try:
                self._porcupine.delete()
            except Exception:
                pass