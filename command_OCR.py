
import cv2
import numpy as np
import pyautogui
import easyocr
import mss
from fuzzywuzzy import fuzz
import time
import base64
from io import BytesIO
from PIL import Image
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS
import sqlite3
from app_paths import data_path


def get_monitors():
    with mss.mss() as sct:
        monitors = []
        for index, monitor in enumerate(sct.monitors[1:], start=1):
            is_primary = (
                monitor["left"] <= 0 < monitor["left"] + monitor["width"]
                and monitor["top"] <= 0 < monitor["top"] + monitor["height"]
            )
            monitors.append({
                "index": index,
                "label": (
                    f"Основной экран {index}" if is_primary
                    else f"Экран {index}"
                ),
                "is_primary": is_primary,
            })
        return monitors


def get_selected_monitor_index():
    monitors = get_monitors()
    if not monitors:
        raise RuntimeError("Система не обнаружила ни одного экрана.")
    primary = next((m for m in monitors if m["is_primary"]), monitors[0])
    try:
        with sqlite3.connect(data_path("config.db")) as conn:
            row = conn.execute(
                "SELECT screen_monitor FROM settings LIMIT 1"
            ).fetchone()
        selected = int(row[0]) if row and row[0] else primary["index"]
    except (sqlite3.Error, TypeError, ValueError):
        selected = primary["index"]
    available = {monitor["index"] for monitor in monitors}
    return selected if selected in available else primary["index"]

class TextFinder:
    def __init__(self):
        self.reader = easyocr.Reader(
            ['ru', 'en'],
            gpu=False,
            model_storage_directory=str(data_path('easyocr')),
        )
        self.cached_img = None
        self.cached_monitor_index = None
        self.last_update = 0.0
        self.preprocessed = {}

    def get_screenshot(self, force_update: bool = False) -> np.ndarray:
        monitor_index = get_selected_monitor_index()
        if (
            force_update
            or monitor_index != self.cached_monitor_index
            or time.time() - self.last_update > 0.3
        ):
            with mss.mss() as sct:
                monitor = sct.monitors[monitor_index]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                self.cached_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                self.cached_monitor_index = monitor_index
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
            with mss.mss() as sct:
                bounds = sct.monitors[get_selected_monitor_index()]
            center_x = int(sum(x_coords) / 4) + bounds["left"]
            center_y = int(sum(y_coords) / 4) + bounds["top"]
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

finder = None


def _get_finder():
    global finder
    if finder is None:
        finder = TextFinder()
    return finder

def move_to_text(text: str, threshold: int = 50) -> bool:
    coords = _get_finder()._find_coordinates(text, threshold)
    if coords:
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        return True
    return False

def click_to_text(text: str, threshold: int = 50, button: str = 'left', clicks: int = 1) -> bool:
    coords = _get_finder()._find_coordinates(text, threshold)
    if coords:
        pyautogui.moveTo(coords[0], coords[1], duration=0.2)
        pyautogui.click(button=button, clicks=clicks)
        time.sleep(0.1)
        return True
    return False

def get_all_screen_text() -> str:
    return _get_finder().get_all_text()


def get_screen_image() -> str:
    with mss.mss() as sct:
        monitor = sct.monitors[get_selected_monitor_index()]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="JPEG", quality=80)
    return base64.b64encode(output.getvalue()).decode("ascii")