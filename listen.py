import os
import pvporcupine
import pyaudio
import speech_recognition as sr
import threading
import time
import numpy as np
import requests
import pygame
import logging
from sintez import speak
from command_OCR import move_to_text, click_to_text
from command import get_weather

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('VoiceAI')

def ask_ollama(question: str) -> str:
    """Функция запроса к локальной нейросети"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": f"[INST] Ответь на русском и достаточно понятно (говори от женского рода милой доброй девушки c интересной жизнью, говори МАКСИМАЛЬНО человечно (без имени)) вопрос: {question} [/INST]",
                "stream": False,
                "options": {"temperature": 0.7}
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise ConnectionError(f"HTTP {response.status_code}: {response.text}")
        
        result = response.json()
        response_text = result.get("response", "").split("[/INST]")[-1].strip()
        print(f"\n[Нейросеть] Ответ: {response_text}")
        return response_text
    except Exception as e:
        logger.error(f"Ошибка запроса к Ollama: {e}")
        return "Не удалось получить ответ от нейросети"

class VoiceAssistant:
    def __init__(self):
        
        pygame.mixer.init()
        self.sounds = {
            'start': pygame.mixer.Sound('./audio/right.mp3'),
            'confirm': pygame.mixer.Sound('./audio/right.mp3'),
            'error': pygame.mixer.Sound('./audio/lie.mp3')
        }

        # Инициализация аудио
        self.pyaudio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 400
        

        self.porcupine = pvporcupine.create(
            access_key='eav8QQvpt4NZ8cpyP+51KxTso4LxSXMWzsCqPGHrRUASriXhqAKfLA==',
            keyword_paths=['models/lumia.ppn']
        )
        
        self.audio_stream = self.pyaudio.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )

        # Команды
        self.command_actions = {
            "наведи на": self._handle_move,
            "нажми на": self._handle_click,
            "кликни на": self._handle_click,
            "клик по": self._handle_click,
            "погода": self._weather,
            "стоп": self.stop,
            "выход": self.stop
        }

        # Флаги и настройки
        self.is_listening = False
        self.is_running = True
        self.command_timeout = 15  # Таймаут прослушивания команд
        self.last_activity = 0
        self.microphone = sr.Microphone()

    def start(self):
        """Запуск ассистента"""
        logger.info("🚀 Ассистент запущен!")
        speak("Система готова к работе")

        # Калибровка микрофона
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)

        # Поток для wake word
        threading.Thread(target=self._detect_wakeword, daemon=True).start()
        
        # Поток для команд
        threading.Thread(target=self._listen_commands, daemon=True).start()

        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def _detect_wakeword(self):
        """Обнаружение активационной фразы"""
        while self.is_running:
            try:
                pcm = self.audio_stream.read(
                    self.porcupine.frame_length, 
                    exception_on_overflow=False
                )
                pcm = np.frombuffer(pcm, dtype=np.int16)
                if self.porcupine.process(pcm) >= 0:
                    logger.info("🔊 Wake word активирована!")
                    speak("Слушаю вас")
                    self.is_listening = True
                    self.last_activity = time.time()
            except Exception as e:
                logger.error(f"Ошибка в wake word detection: {e}")
                time.sleep(0.1)

    def _listen_commands(self):
        """Обработка команд с использованием Google Speech-to-Text"""
        while self.is_running:
            if self.is_listening:
                try:
                    
                    if time.time() - self.last_activity > self.command_timeout:
                        self.is_listening = False
                        speak("Режим прослушивания завершен")
                        self.start(self)
                        continue

                    # Используем speech_recognition для захвата аудио
                    with self.microphone as source:
                        logger.info("Слушаю команду...")
                        try:
                            audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                            text = self.recognizer.recognize_google(audio, language="ru-RU").lower()
                            print(f"\n[Распознано] {text}")
                            logger.info(f"Распознано: {text}")
                            self._process_command(text)
                            self.last_activity = time.time()
                        except sr.WaitTimeoutError:
                            continue
                        except sr.UnknownValueError:
                            logger.info("Не удалось распознать речь")
                        except sr.RequestError as e:
                            logger.error(f"Ошибка сервиса распознавания: {e}")
                            speak("Проблемы с интернет-соединением")

                except Exception as e:
                    logger.error(f"Ошибка в обработке команд: {e}")
                    time.sleep(0.1)
            else:
                time.sleep(0.1)

    def _process_command(self, text):
        """Обработка команды"""
        # Сначала проверяем известные команды
        for cmd, action in self.command_actions.items():
            if cmd in text:
                try:
                    action(text)
                    return
                except Exception as e:
                    logger.error(f"Ошибка выполнения команды: {e}")
                    self._play_sound('error')
                    return
        
        # Если команда не найдена - отправляем вопрос нейросети
        if len(text.split()) >= 3:  # Если есть хотя бы 2 слова
            logger.info(f"Отправка запроса нейросети: {text}")
            speak("Секунду, формулирую мысль")
            response = ask_ollama(text)
            speak(response)
        else:
            logger.info("Не распознано значимой команды")
            speak("Повторите, пожалуйста")

    def _handle_move(self, text):
        for prefix in ["наведи на", "наведи курсор на", "перемести на"]:
            if prefix in text:
                target = text.split(prefix)[-1].strip()
                if not move_to_text(target, threshold=70):
                    self._play_sound('error')

    def _handle_click(self, text):
        """Клик по элементу"""
        for prefix in ["нажми на", "кликни на", "клик по"]:
            if prefix in text:
                target = text.split(prefix)[-1].strip()
                if not click_to_text(target, clicks=2):
                    self._play_sound('error')

    def _weather(self, text=None):
        """Прогноз погоды"""
        try:
            weather = get_weather()
            speak(f"Погода: {weather['temp']}")
            logger.info(f"☀️ Погода: {weather['temp']}")
        except Exception as e:
            logger.error(f"Ошибка погоды: {e}")
            self._play_sound('error')

    def _play_sound(self, name):
        """Воспроизведение звукового сигнала"""
        if name in self.sounds:
            self.sounds[name].play()

    def stop(self):
        """Завершение работы"""
        self.is_running = False
        if hasattr(self, 'audio_stream'):
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        self.pyaudio.terminate()
        pygame.quit()
        logger.info("🔴 Ассистент остановлен")
        os._exit(0)

if __name__ == "__main__":
    try:
        assistant = VoiceAssistant()
        assistant.start()
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}")
        os._exit(1)