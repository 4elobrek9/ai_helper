"""Text-to-Speech на базе Silero TTS с кэшированием, сменой голоса и скорости."""

from __future__ import annotations

import logging
import re
import threading
from queue import Queue
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import torch

from lumi.core.logging import get_logger

logger = get_logger("voice.tts")


class TTSEngine:
    """Локальный TTS через Silero с кэшированием модели, голосами и скоростью."""

    SYMBOLS: dict[str, str] = {
        "+": " плюс ",
        "-": " минус ",
        "*": " умножить на ",
        "/": " делить на ",
        "=": " равно ",
        "%": " процент ",
        "√": " корень ",
        "²": " в квадрате ",
        "³": " в кубе ",
        "°": " градус ",
        "π": " пи ",
        "∞": " бесконечность ",
        "≈": " приблизительно равно ",
        "≤": " меньше или равно ",
        "≥": " больше или равно ",
        "≠": " не равно ",
        "±": " плюс минус ",
    }

    def __init__(
        self,
        model_id: str = "v3_1_ru",
        speaker: str = "xenia",
        sample_rate: int = 48000,
        device: str = "cpu",
        rate: float = 1.0,
        volume: float = 1.0,
    ) -> None:
        self.model_id = model_id
        self.speaker = speaker
        self.sample_rate = sample_rate
        self.device = device
        self.rate = rate
        self.volume = volume

        self._model: Optional[object] = None
        self._initialized = False
        self._lock = threading.Lock()

        self._queue: Queue[str] = Queue()
        self._is_speaking = False
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Callback для уведомления о начале/конце речи (микрофон mute)
        self._on_speaking_start: Optional[Callable[[], None]] = None
        self._on_speaking_stop: Optional[Callable[[], None]] = None

        self._init_model()
        self._start_worker()

    def _init_model(self) -> None:
        """Загружает модель Silero TTS (один раз, кэшируется в памяти)."""
        if self._initialized:
            return
        try:
            self._model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker=self.model_id,
            )
            self._model.to(torch.device(self.device))
            self._initialized = True
            logger.info(f"Silero TTS загружен: speaker={self.speaker}, rate={self.sample_rate}")
        except Exception as e:
            logger.error(f"Ошибка загрузки Silero TTS: {e}")
            raise

    def _start_worker(self) -> None:
        """Запускает фоновый поток воспроизведения."""
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker_thread.start()

    def _speech_worker(self) -> None:
        """Фоновый обработчик очереди речи с уведомлениями о начале/конце."""
        while not self._stop_event.is_set():
            try:
                text = self._queue.get(timeout=0.5)
            except Exception:
                continue
            if text is None:
                break
            self._speak_text(text)
            self._queue.task_done()

    def _speak_text(self, text: str) -> None:
        """Воспроизводит один фрагмент текста с уведомлением о состоянии."""
        processed = self.preprocess(text)
        if not processed:
            return

        # Уведомляем о начале речи (для mute микрофона)
        with self._lock:
            self._is_speaking = True
        if self._on_speaking_start:
            try:
                self._on_speaking_start()
            except Exception as e:
                logger.error(f"Ошибка в on_speaking_start: {e}")

        try:
            audio = self._model.apply_tts(
                text=processed + " ",
                speaker=self.speaker,
                sample_rate=self.sample_rate,
            )
            silence = np.zeros(int(0.15 * self.sample_rate), dtype=np.float32)
            sd.play(np.concatenate([audio, silence]), samplerate=self.sample_rate)
            sd.wait()
        except Exception as e:
            logger.error(f"Ошибка воспроизведения TTS: {e}")
        finally:
            # Небольшая задержка после речи перед включением микрофона
            import time
            time.sleep(0.3)

            with self._lock:
                self._is_speaking = False
            if self._on_speaking_stop:
                try:
                    self._on_speaking_stop()
                except Exception as e:
                    logger.error(f"Ошибка в on_speaking_stop: {e}")

    def preprocess(self, text: str) -> str:
        """Предобработка текста: цифры, математика, служебные символы."""
        if not text:
            return ""

        text = str(text)

        # Удаляем служебные маркеры Ollama
        text = re.sub(r"\\[Ollama\\] Ответ:\\s*", "", text)

        # Заменяем математические символы на слова
        for sym, word in self.SYMBOLS.items():
            text = text.replace(sym, word)

        # Обрабатываем простые числа (цифры -> слова)
        text = re.sub(r"\b(\d+)\b", lambda m: self._number_to_words(int(m.group(1))), text)

        return text.strip()

    @staticmethod
    def _number_to_words(n: int) -> str:
        """Преобразует число в слова (упрощённо, до 999)."""
        if n == 0:
            return "ноль"
        units = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
        teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
                 "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
        tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
                "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
        hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
                    "шестьсот", "семьсот", "восемьсот", "девятьсот"]

        result = ""
        if n >= 100:
            result += hundreds[n // 100] + " "
            n %= 100
        if n >= 20:
            result += tens[n // 10]
            if n % 10:
                result += " " + units[n % 10]
        elif n >= 10:
            result += teens[n - 10]
        elif n > 0:
            result += units[n]
        return result.strip()

    def speak(self, text: str) -> None:
        """Добавляет текст в очередь на воспроизведение."""
        if not text or not text.strip():
            return
        self._queue.put(text)

    def stop(self) -> None:
        """Останавливает текущее воспроизведение и очищает очередь."""
        sd.stop()
        with self._lock:
            self._queue.queue.clear()
            self._is_speaking = False

    def is_speaking(self) -> bool:
        """Возвращает True если сейчас идёт воспроизведение."""
        with self._lock:
            return self._is_speaking or not self._queue.empty()

    def set_voice(self, speaker: str) -> None:
        """Меняет голос Silero."""
        self.speaker = speaker
        logger.info(f"Голос изменён на: {speaker}")

    def set_rate(self, rate: float) -> None:
        """Меняет скорость речи."""
        self.rate = rate
        logger.info(f"Скорость речи изменена на: {rate}")

    def set_callbacks(
        self,
        on_speaking_start: Optional[Callable[[], None]] = None,
        on_speaking_stop: Optional[Callable[[], None]] = None,
    ) -> None:
        """Устанавливает callback'и для уведомления о начале/конце речи."""
        self._on_speaking_start = on_speaking_start
        self._on_speaking_stop = on_speaking_stop

    def shutdown(self) -> None:
        """Корректно завершает работу TTS."""
        self.stop()
        self._stop_event.set()
        self._queue.put(None)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2)