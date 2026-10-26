"""OCR (распознавание текста с экрана) через EasyOCR."""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from lumi.core.logging import get_logger

logger = get_logger("desktop.ocr")


class OCREngine:
    """Движок OCR на базе EasyOCR с кэшированием модели."""

    _instance: Optional["OCREngine"] = None
    _reader: Optional[object] = None
    _initialized = False

    def __new__(cls) -> "OCREngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

    def _ensure_loaded(self) -> None:
        """Ленивая загрузка EasyOCR."""
        if self._reader is not None:
            return
        try:
            import easyocr
            self._reader = easyocr.Reader(["ru", "en"], gpu=False)
            logger.info("EasyOCR инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации EasyOCR: {e}")
            raise

    def extract_text(self, image: np.ndarray) -> str:
        """Извлекает текст из изображения.

        Args:
            image: Изображение в формате BGR (numpy array).

        Returns:
            Распознанный текст.
        """
        self._ensure_loaded()
        try:
            results = self._reader.readtext(image, paragraph=True)
            texts = [res[1] for res in results if res[2] > 0.5]
            return "\n".join(texts).strip()
        except Exception as e:
            logger.error(f"Ошибка OCR: {e}")
            return ""

    def find_text_coordinates(
        self,
        search_text: str,
        image: np.ndarray | None = None,
        threshold: int = 60,
    ) -> Optional[tuple[int, int]]:
        """Ищет текст на изображении и возвращает координаты центра.

        Args:
            search_text: Текст для поиска.
            image: Изображение (если None — делается скриншот).
            threshold: Порог сходства (0-100).

        Returns:
            Координаты (x, y) центра найденного текста или None.
        """
        from fuzzywuzzy import fuzz
        import mss

        self._ensure_loaded()

        if image is None:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                image = np.array(sct.grab(monitor))

        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR) if image.shape[-1] == 4 else image

        try:
            results = self._reader.readtext(image)
            search_lower = search_text.lower()
            best_match = None
            max_similarity = 0

            for result in results:
                text = result[1]
                box = result[0]
                similarity = fuzz.token_set_ratio(search_lower, text.lower())
                if similarity > max_similarity and similarity >= threshold:
                    max_similarity = similarity
                    best_match = box

            if best_match:
                x_coords = [p[0] for p in best_match]
                y_coords = [p[1] for p in best_match]
                return int(sum(x_coords) / 4), int(sum(y_coords) / 4)
        except Exception as e:
            logger.error(f"Ошибка поиска текста: {e}")

        return None