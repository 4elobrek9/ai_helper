"""Speech-to-Text на базе faster-whisper с continuous listening."""

from __future__ import annotations

import logging
import threading
import wave
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from lumi.core.logging import get_logger

logger = get_logger("voice.stt")


class STTEngine:
    """Локальный STT через faster-whisper с поддержкой непрерывного прослушивания."""

    def __init__(
        self,
        model_name: str = "small",
        language: str = "ru",
        device: str = "cpu",
        compute_type: str = "int8",
        sample_rate: int = 16000,
        chunk_duration: float = 5.0,
    ) -> None:
        self.model_name = model_name
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration

        self._model: Optional[object] = None
        self._initialized = False
        self._lock = threading.Lock()

        self._is_listening = False
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_listening = threading.Event()
        self._on_result: Optional[Callable[[str], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None

    def _ensure_loaded(self) -> None:
        """Ленивая загрузка модели."""
        if self._initialized:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._initialized = True
            logger.info(f"STT модель загружена: {self.model_name} ({self.device})")
        except Exception as e:
            logger.error(f"Ошибка загрузки STT модели: {e}")
            raise

    def transcribe(self, audio_path: str) -> str:
        """Распознаёт речь из аудиофайла."""
        self._ensure_loaded()
        try:
            segments, _ = self._model.transcribe(
                audio_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,
            )
            text = "".join(segment.text for segment in segments).strip()
            logger.debug(f"STT результат: {text[:100]}...")
            return text
        except Exception as e:
            logger.error(f"Ошибка распознавания: {e}")
            return ""

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Распознаёт речь из байтов аудио."""
        import tempfile
        import os

        self._ensure_loaded()
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                with wave.open(tmp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_bytes)
                tmp_path = tmp.name
            result = self.transcribe(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return result
        except Exception as e:
            logger.error(f"Ошибка transcribe_bytes: {e}")
            return ""

    def transcribe_numpy(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Распознаёт речь из numpy массива."""
        import tempfile
        import os

        self._ensure_loaded()
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                with wave.open(tmp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes((audio * 32767).astype(np.int16).tobytes())
                tmp_path = tmp.name
            result = self.transcribe(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return result
        except Exception as e:
            logger.error(f"Ошибка transcribe_numpy: {e}")
            return ""

    # ------------------------------------------------------------------
    # Continuous listening
    # ------------------------------------------------------------------

    def start_continuous_listening(
        self,
        on_result: Callable[[str], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Запускает непрерывное прослушивание микрофона в фоновом потоке."""
        if self._is_listening:
            logger.warning("Continuous listening уже запущен")
            return

        self._on_result = on_result
        self._on_error = on_error
        self._stop_listening.clear()
        self._is_listening = True

        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        logger.info("Continuous listening запущен")

    def stop_continuous_listening(self) -> None:
        """Останавливает непрерывное прослушивание."""
        self._is_listening = False
        self._stop_listening.set()
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=5)
        logger.info("Continuous listening остановлен")

    def _listen_loop(self) -> None:
        """Цикл непрерывного прослушивания с обработкой ошибок микрофона."""
        try:
            device_info = sd.query_devices(kind="input")
            logger.info(f"Микрофон: {device_info['name']}")
        except Exception as e:
            logger.error(f"Микрофон недоступен: {e}")
            if self._on_error:
                self._on_error(f"Микрофон недоступен: {e}")
            self._is_listening = False
            return

        chunk_samples = int(self.sample_rate * self.chunk_duration)

        while not self._stop_listening.is_set() and self._is_listening:
            try:
                audio = sd.rec(
                    chunk_samples,
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                )
                sd.wait()

                audio_flat = audio.flatten()
                if np.max(np.abs(audio_flat)) < 0.01:
                    continue

                text = self.transcribe_numpy(audio_flat, self.sample_rate)
                if text and self._on_result:
                    self._on_result(text)

            except Exception as e:
                logger.error(f"Ошибка в цикле прослушивания: {e}")
                if self._on_error:
                    self._on_error(str(e))
                self._stop_listening.wait(0.5)

    def is_available(self) -> bool:
        """Проверяет доступность STT."""
        try:
            self._ensure_loaded()
            return True
        except Exception:
            return False

    def is_listening(self) -> bool:
        """Возвращает True если идёт continuous listening."""
        return self._is_listening