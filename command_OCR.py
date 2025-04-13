import cv2
import numpy as np
import pyautogui
import easyocr
import pytesseract
import mss
from fuzzywuzzy import fuzz
import time

# Настройка Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class TextFinder:
    def __init__(self):
        self.reader_en = easyocr.Reader(['en'], gpu=True)
        self.cached_img = None
        self.last_update = 0
        self.preprocessed = {}
        self.tesseract_config = r'--oem 1 --psm 7 -l rus'

    def get_screenshot(self, force_update=False):
        if force_update or time.time() - self.last_update > 0.3:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                self.cached_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                self.last_update = time.time()
                self.preprocessed.clear()
        return self.cached_img

    def preprocess_image(self, img, lang):
        if lang not in self.preprocessed:
            small_img = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR)
            if lang == 'ru':
                processed = cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY)
                processed = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            else:
                processed = small_img
            self.preprocessed[lang] = processed
        return self.preprocessed[lang]

    def detect_language(self, text):
        return 'ru' if any(ord('а') <= ord(c) <= ord('я') for c in text.lower()) else 'en'

    def _find_coordinates(self, search_text, threshold):
        """Внутренний метод для поиска координат текста"""
        img = self.get_screenshot()
        lang = self.detect_language(search_text)
        processed_img = self.preprocess_image(img, lang)
        
        results = []
        search_lower = search_text.lower()
        
        if lang == 'en':
            ocr_results = self.reader_en.readtext(
                processed_img,
                decoder='greedy',
                batch_size=4,
                paragraph=False,
                text_threshold=0.4
            )
            for result in ocr_results:
                text = result[1]
                box = [(int(x*2), int(y*2)) for (x, y) in result[0]]
                results.append((text, box))
        else:
            data = pytesseract.image_to_data(
                processed_img,
                config=self.tesseract_config,
                output_type=pytesseract.Output.DICT
            )
            for i in range(len(data['text'])):
                text = data['text'][i]
                if text.strip():
                    x = data['left'][i] * 2
                    y = data['top'][i] * 2
                    w = data['width'][i] * 2
                    h = data['height'][i] * 2
                    box = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                    results.append((text, box))

        best_match = None
        max_similarity = 0
        
        for text, box in results:
            similarity = fuzz.token_set_ratio(search_lower, text.lower())
            if similarity > max_similarity and similarity >= threshold:
                max_similarity = similarity
                best_match = box

        if best_match:
            x = (best_match[0][0] + best_match[2][0]) // 2
            y = (best_match[0][1] + best_match[2][1]) // 2
            return x, y
        return None

# Глобальный экземпляр для всех вызовов
finder = TextFinder()

def move_to_text(text, threshold=50):
    """
    Перемещает курсор к найденному тексту
    :param text: Искомый текст
    :param threshold: Порог совпадения (0-100)
    :return: True если успешно, иначе False
    """
    coords = finder._find_coordinates(text, threshold)
    if coords:
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        return True
    return False

def click_to_text(text, threshold=50, button='left', clicks=1):
    """
    Кликает по найденному тексту
    :param text: Искомый текст
    :param threshold: Порог совпадения (0-100)
    :param button: Кнопка мыши ('left', 'right' или 'middle')
    :param clicks: Количество кликов
    :return: True если успешно, иначе False
    """
    coords = finder._find_coordinates(text, threshold)
    if coords:
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        pyautogui.click(button=button, clicks=clicks)
        time.sleep(0.1)
        return True
    return False

# Пример использования
if __name__ == "__main__":
    # Просто перемещение
    move_to_text("Меню", threshold=70)
    
    # Клик правой кнопкой
    click_to_text("Документ", button='right', clicks=2)