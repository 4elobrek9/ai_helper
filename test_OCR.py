import cv2
import numpy as np
import time
import os
import pyautogui
import sys
import subprocess
import speech_recognition as sr
import easyocr
import pyttsx3
import wave
import mss
import struct
from collections import deque

# Настройки
ACTIVATION_WORD = "наведи"  # Упрощенная команда активации
ENERGY_THRESHOLD = 400      # Порог громкости (настраивается автоматически)
DYNAMIC_THRESHOLD = True    # Автоподстройка чувствительности
AMPLIFICATION = 2.0         # Усиление звука

class VoiceAssistant:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.mic = self.init_microphone()
        self.reader = easyocr.Reader(['ru', 'en'], gpu=True)
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)
        self.running = True
        self.audio_history = deque(maxlen=20)
        
        # Калибровка микрофона
        self.calibrate_microphone()
    
    def init_microphone(self):
        """Инициализация микрофона с обработкой ошибок"""
        try:
            return sr.Microphone()
        except AttributeError:
            print("Ошибка микрофона. Проверьте:")
            print("1. Установите PyAudio: pip install pipwin && pipwin install pyaudio")
            print("2. Подключите микрофон")
            sys.exit(1)
    
    def calibrate_microphone(self):
        """Автоматическая калибровка чувствительности микрофона"""
        self.speak("Калибровка микрофона. Пожалуйста, помолчите 3 секунды...")
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=3)
        
        self.speak("Теперь произнесите тестовую фразу...")
        with self.mic as source:
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=3)
                if DYNAMIC_THRESHOLD:
                    self.recognizer.dynamic_energy_threshold = True
                else:
                    # Анализ громкости голоса
                    data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
                    energy = np.average(np.abs(data)) * AMPLIFICATION
                    self.recognizer.energy_threshold = energy
                    print(f"Установлен порог громкости: {energy}")
            except:
                self.recognizer.energy_threshold = ENERGY_THRESHOLD
                print(f"Используется стандартный порог: {ENERGY_THRESHOLD}")
    
    def amplify_audio(self, audio_data):
        """Усиление аудиосигнала"""
        data = np.frombuffer(audio_data, dtype=np.int16)
        amplified = np.clip(data * AMPLIFICATION, -32768, 32767).astype(np.int16)
        return amplified.tobytes()
    
    def listen(self):
        """Улучшенное распознавание с обработкой звука"""
        with self.mic as source:
            print("\nГоворите...")
            try:
                audio = self.recognizer.listen(
                    source, 
                    timeout=3, 
                    phrase_time_limit=5
                )
                
                # Усиление звука
                if AMPLIFICATION != 1.0:
                    audio._data = self.amplify_audio(audio.get_raw_data())
                
                # Сохраняем для анализа
                self.save_audio_sample(audio)
                
                text = self.recognizer.recognize_google(audio, language="ru-RU").lower()
                print(f"Распознано: {text}")
                return text
            except sr.WaitTimeoutError:
                print("Таймаут ожидания")
                return ""
            except sr.UnknownValueError:
                print("Речь не распознана")
                return ""
            except Exception as e:
                print(f"Ошибка: {str(e)}")
                return ""
    
    def save_audio_sample(self, audio):
        """Сохранение аудио для анализа проблем"""
        os.makedirs("audio_debug", exist_ok=True)
        timestamp = int(time.time())
        filename = f"audio_debug/sample_{timestamp}.wav"
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.get_raw_data())
    
    def find_text(self, text_to_find):
        """Поиск текста на экране"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Улучшенное распознавание текста
                results = self.reader.readtext(
                    img,
                    decoder='beamsearch',  # Более точный метод
                    beamWidth=5,
                    batch_size=1,
                    paragraph=False
                )
                
                for detection in results:
                    text = detection[1]
                    confidence = detection[2]
                    
                    # Фильтр по уверенности и совпадению
                    if (confidence > 0.4 and 
                        text_to_find.lower() in text.lower()):
                        box = detection[0]
                        x = (box[0][0] + box[2][0]) // 2 + monitor['left']
                        y = (box[0][1] + box[2][1]) // 2 + monitor['top']
                        return x, y
        except Exception as e:
            print(f"Ошибка поиска: {str(e)}")
        return None
    
    def run(self):
        """Основной цикл работы"""
        self.speak(f"Готов к работе. Скажите '{ACTIVATION_WORD}'")
        
        while self.running:
            try:
                command = self.listen()
                
                if command and ACTIVATION_WORD in command:
                    self.speak("Что найти?")
                    target_command = self.listen()
                    
                    if target_command:
                        pos = self.find_text(target_command)
                        if pos:
                            pyautogui.moveTo(*pos, duration=0.3)
                            self.speak(f"Найдено: {target_command}")
                        else:
                            self.speak("Не нашла")
                
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                self.speak("Выключаюсь")
                self.running = False

if __name__ == "__main__":
    # Проверка зависимостей
    def install(package):
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    required = [
        'opencv-python', 'easyocr', 'mss', 'pyautogui',
        'SpeechRecognition', 'pyttsx3'
    ]
    
    for package in required:
        try:
            __import__(package)
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