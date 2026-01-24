
import cv2
import numpy as np
import pyautogui
import easyocr
import mss
from fuzzywuzzy import fuzz
import time

class TextFinder:
    def __init__(self):
        self.reader = easyocr.Reader(['ru', 'en'], gpu=True)
        self.cached_img = None
        self.last_update = 0.0
        self.preprocessed = {}

    def get_screenshot(self, force_update: bool = False) -> np.ndarray:
        if force_update or time.time() - self.last_update > 0.3:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                self.cached_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                self.last_update = time.time()
                self.preprocessed.clear()
        return self.cached_img

    def _find_coordinates(self, search_text: str, threshold: int = 50) -> tuple | None:
        img = self.get_screenshot()
        results = self.reader.readtext(
            img,
            decoder='greedy',
            batch_size=4,
            paragraph=False,
            text_threshold=0.4
        )

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
            center_x = int(sum(x_coords) / 4)
            center_y = int(sum(y_coords) / 4)
            return center_x, center_y

        return None

    def get_all_text(self) -> str:
        img = self.get_screenshot(force_update=True)
        results = self.reader.readtext(
            img,
            paragraph=True,
            text_threshold=0.5,
            width_ths=0.7,
            height_ths=0.7
        )

        texts = [res[1] for res in results if res[2] > 0.5]
        full_text = '\n'.join(texts).strip()

        if len(full_text) < 20:
            return "На экране мало текста или он неразборчивый."
        
        return full_text

finder = TextFinder()

def move_to_text(text: str, threshold: int = 50) -> bool:
    coords = finder._find_coordinates(text, threshold)
    if coords:
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        return True
    return False

def click_to_text(text: str, threshold: int = 50, button: str = 'left', clicks: int = 1) -> bool:
    coords = finder._find_coordinates(text, threshold)
    if coords:
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        pyautogui.click(button=button, clicks=clicks)
        time.sleep(0.1)
        return True
    return False

def get_all_screen_text() -> str:
    return finder.get_all_text()