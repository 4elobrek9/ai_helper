import cv2
import numpy as np
import time
import os
import pyautogui
import sys
import subprocess
import speech_recognition as sr
import easyocr
import mss
import pyttsx3
from difflib import SequenceMatcher
from fuzzywuzzy import fuzz
import Levenshtein

# Настройки
ACTIVATION_WORD = "наведи"  # Команда активации
SIMILARITY_THRESHOLD = 0.6   # Порог схожести слов (0-1)
DEBUG_MODE = True            # Режим отладки

class VoiceAssistant:
    def __init__(self):
        # Инициализация синтеза речи
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)
        
        # Инициализация распознавания речи
        self.recognizer = sr.Recognizer()
        self.mic = sr.Microphone()
        
        # Инициализация OCR
        self.reader = easyocr.Reader(['en', 'ru'], gpu=True)
        self.running = True
        
        # Калибровка микрофона
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
        
        self.speak(f"Система готова. Скажите '{ACTIVATION_WORD}' для поиска")

    def speak(self, text):
        """Озвучивание текста"""
        print(f"> {text}")
        self.engine.say(text)
        self.engine.runAndWait()
    
    def listen(self):
        """Слушание команды с микрофона"""
        with self.mic as source:
            print("\nСлушаю...")
            try:
                audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=4)
                text = self.recognizer.recognize_google(audio, language="ru-RU").lower()
                print(f"Распознано: {text}")
                return text
            except sr.WaitTimeoutError:
                if DEBUG_MODE: print("Таймаут ожидания")
                return ""
            except sr.UnknownValueError:
                if DEBUG_MODE: print("Речь не распознана")
                return ""
            except Exception as e:
                print(f"Ошибка: {str(e)}")
                return ""
    
    def text_similarity(self, a, b):
        """Вычисление схожести строк несколькими методами"""
        # 1. Метод Левенштейна (расстояние редактирования)
        lev_score = Levenshtein.ratio(a.lower(), b.lower())
        
        # 2. Коэффициент Жаккара (совпадение множеств символов)
        set_a = set(a.lower())
        set_b = set(b.lower())
        jaccard = len(set_a & set_b) / len(set_a | set_b) if (set_a | set_b) else 0
        
        # 3. Частичное совпадение
        partial_ratio = fuzz.partial_ratio(a.lower(), b.lower()) / 100
        
        # Усредняем результаты
        return (lev_score + jaccard + partial_ratio) / 3
    
    def find_text(self, target):
        """Поиск текста с нечетким соответствием"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Распознавание текста
                results = self.reader.readtext(img, paragraph=False)
                
                best_match = None
                highest_score = 0
                
                for detection in results:
                    text = detection[1]
                    confidence = detection[2]
                    box = detection[0]
                    
                    # Вычисляем схожесть
                    score = self.text_similarity(target, text)
                    
                    if DEBUG_MODE:
                        print(f"Сравниваю: '{target}' с '{text}' -> {score:.2f}")
                    
                    # Если превысили порог и это лучшее совпадение
                    if score > SIMILARITY_THRESHOLD and score > highest_score:
                        highest_score = score
                        best_match = {
                            'text': text,
                            'box': box,
                            'score': score,
                            'position': (
                                (box[0][0] + box[2][0]) // 2 + monitor['left'],
                                (box[0][1] + box[2][1]) // 2 + monitor['top']
                            )
                        }
                
                if best_match:
                    if DEBUG_MODE:
                        print(f"Лучшее совпадение: '{best_match['text']}' ({best_match['score']:.2f})")
                    return best_match['position']
                
        except Exception as e:
            print(f"Ошибка поиска: {str(e)}")
        return None
    
    def run(self):
        """Основной цикл работы"""
        while self.running:
            try:
                command = self.listen()
                
                if command and ACTIVATION_WORD in command:
                    self.speak("Какой текст найти?")
                    target = self.listen()
                    
                    if target:
                        pos = self.find_text(target)
                        if pos:
                            pyautogui.moveTo(*pos, duration=0.3)
                            self.speak(f"Найдено: {target}")
                        else:
                            self.speak("Не удалось найти")
                
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                self.speak("Выключаюсь")
                self.running = False

if __name__ == "__main__":
    # Установка необходимых пакетов
    def install(package):
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    required = [
        'opencv-python', 'easyocr', 'mss', 'pyautogui',
        'SpeechRecognition', 'pyttsx3', 'python-Levenshtein', 'fuzzywuzzy'
    ]
    
    for package in required:
        try:
            __import__(package.split('-')[0])
        except ImportError:
            install(package)
    
    # Особый случай для PyAudio
    try:
        import pyaudio
    except ImportError:
        if sys.platform == 'win32':
            install('pipwin')
            subprocess.check_call([sys.executable, "-m", "pipwin", "install", "pyaudio"])
        else:
            install('pyaudio')
    
    assistant = VoiceAssistant()
    assistant.run()