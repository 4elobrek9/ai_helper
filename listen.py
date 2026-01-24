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
import mistral_api

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('VoiceAI')

# Системный промпт (персона Люмия)
SYSTEM_PROMPT = "Ответь на русском и достаточно понятно (говори от женского рода милой доброй девушки c интересной жизнью, говори МАКСИМАЛЬНО человечно, тебя зовут Люмия или просто Люми, любишь паучью лилию). При ответе не стоит здороваться или что-то типо того."

def ask_ollama(question: str, full_memory: list) -> str:
    """Запрос к локальной Ollama с полным контекстом (hardmemory + system + history)"""
    try:
        # Строим prompt в стиле чата для llama3
        prompt = ""
        for msg in full_memory:
            if msg['role'] == 'system':
                prompt += f"[INST] {msg['content']} [/INST]\n"
            elif msg['role'] == 'user':
                prompt += f"[INST] {msg['content']} [/INST]\n"
            elif msg['role'] == 'assistant':
                prompt += f"{msg['content']}\n"
        
        prompt += f"[INST] {question} [/INST]"
        
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3:8b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 512
                }
            },
            timeout=60
        )
        
        if response.status_code != 200:
            raise ConnectionError(f"HTTP {response.status_code}: {response.text}")
        
        result = response.json()
        response_text = result.get("response", "").strip()
        print(f"\n[Нейросеть Ollama] Ответ: {response_text}")
        return response_text
    except Exception as e:
        logger.error(f"Ошибка запроса к Ollama: {e}")
        return "Не удалось получить ответ от локальной нейросети"

class VoiceAssistant:
    def __init__(self):
        
        pygame.mixer.init()
        self.sounds = {
            'start': pygame.mixer.Sound('./audio/right.mp3'),
            'confirm': pygame.mixer.Sound('./audio/right.mp3'),
            'error': pygame.mixer.Sound('./audio/lie.mp3')
        }

        self.pyaudio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 400
        
        self.porcupine = pvporcupine.create(
            # access_key='eav8QQvpt4NZ8cpyP+51KxTso4LxSXMWzsCqPGHrRUASriXhqAKfLA==',
            keyword_paths=['models/lumia.ppn']
        )
        
        self.audio_stream = self.pyaudio.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )

        # Команды — сделаем проверку более надёжной (cmd in text и cmd является отдельным словом или в начале/конце)
        self.command_actions = {
            "наведи на": self._handle_move,
            "нажми на": self._handle_click,
            "кликни на": self._handle_click,
            "клик по": self._handle_click,
            "погода": self._weather,
            "стоп": self.stop,
            "выход": self.stop
        }

        self.is_listening = False
        self.is_running = True
        self.command_timeout = 10
        self.last_activity = 0
        self.microphone = sr.Microphone()

    def start(self):
        logger.info("🚀 Ассистент запущен!")
        speak("Система готова к работе")

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)

        threading.Thread(target=self._detect_wakeword, daemon=True).start()
        threading.Thread(target=self._listen_commands, daemon=True).start()

        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def _detect_wakeword(self):
        while self.is_running:
            try:
                pcm = self.audio_stream.read(
                    self.porcupine.frame_length, 
                    exception_on_overflow=False
                )
                pcm = np.frombuffer(pcm, dtype=np.int16)
                if self.porcupine.process(pcm) >= 0:
                    logger.info("🔊 Wake word активирована!")
                    self.is_listening = True
                    self.last_activity = time.time()
            except Exception as e:
                logger.error(f"Ошибка в wake word detection: {e}")
                time.sleep(0.1)

    def _listen_commands(self):
        while self.is_running:
            if self.is_listening:
                try:
                    if time.time() - self.last_activity > self.command_timeout:
                        self.is_listening = False
                        continue

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
        """Обработка команды — улучшена проверка команд"""
        # Более надёжная проверка: ищем команды как отдельные слова или префиксы
        matched = False
        for cmd, action in self.command_actions.items():
            if f" {cmd} " in f" {text} " or text.startswith(cmd + " ") or text.endswith(" " + cmd) or text == cmd:
                try:
                    action(text)
                    matched = True
                    return
                except Exception as e:
                    logger.error(f"Ошибка выполнения команды {cmd}: {e}")
                    self._play_sound('error')
                    matched = True
                    return
        
        # Если ни одна команда не сработала и фраза достаточно осмысленная — к нейросети
        if len(text.split()) >= 2:  # снижено до 2 слов, чтобы короткие вопросы тоже обрабатывались
            logger.info(f"Отправка запроса нейросети: {text}")
            speak("Секунду, формулирую мысль")
            
            # Сохраняем пользовательское сообщение
            save_to_memory(text, 'user')
            
            # Обновляем hardmemory (фильтруем важное из всей истории)
            summarize_hardmemory()
            
            # Загружаем контекст: hardmemory (важное) + обычная история
            hard_memory = load_hardmemory()
            memory = load_memory()
            full_memory = hard_memory + [{'role': 'system', 'content': SYSTEM_PROMPT}] + memory
            
            response_text = None
            
            # Mistral (онлайн)
            try:
                response = mistral_api.chat_with_mistral(text, full_memory)
                response_text = response['choices'][0]['message']['content'].strip()
                print(f"\n[Нейросеть Mistral] Ответ: {response_text}")
                logger.info("Использована Mistral API (онлайн)")
                
            except Exception as e:
                logger.warning(f"Ошибка Mistral API: {e}. Переход на локальную Ollama.")
                try:
                    response_text = ask_ollama(text, full_memory)
                    logger.info("Использована локальная Ollama")
                except Exception as ee:
                    logger.error(f"Критическая ошибка Ollama: {ee}")
                    response_text = "Извините, обе нейросети недоступны."

            if response_text and response_text.strip():
                speak(response_text)
                save_to_memory(response_text, 'assistant')
                # Ещё раз обновляем hardmemory после ответа (на случай, если в ответе есть важное)
                summarize_hardmemory()
            else:
                speak("Не удалось получить ответ")

        else:
            logger.info("Не распознано значимой команды")
            speak("Повторите, пожалуйста")

    def _handle_move(self, text):
        for prefix in ["наведи на", "наведи курсор на", "перемести на", "наведи на"]:
            if prefix in text:
                target = text.split(prefix)[-1].strip()
                logger.info(f"Команда: навести курсор на '{target}'")
                if not move_to_text(target, threshold=70):
                    self._play_sound('error')
                return

    def _handle_click(self, text):
        for prefix in ["нажми на", "кликни на", "клик по", "нажми", "кликни", "клик"]:
            if prefix in text:
                target = text.split(prefix)[-1].strip()
                logger.info(f"Команда: клик по '{target}'")
                if not click_to_text(target, clicks=2):
                    self._play_sound('error')
                return

    def _weather(self, text=None):
        logger.info("Команда: погода")
        try:
            weather = get_weather()
            speak(f"Сейчас {weather['temp']}, {weather.get('description', '')}")
            logger.info(f"☀️ Погода: {weather['temp']}")
        except Exception as e:
            logger.error(f"Ошибка погоды: {e}")
            speak("Не удалось получить погоду")
            self._play_sound('error')

    def _play_sound(self, name):
        if name in self.sounds:
            self.sounds[name].play()

    def stop(self):
        summarize_hardmemory()  # Сохраняем важное при выходе
        self.is_running = False
        if hasattr(self, 'audio_stream'):
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        self.pyaudio.terminate()
        pygame.quit()
        logger.info("🔴 Ассистент остановлен")
        os._exit(0)


# Функции работы с памятью
import json
import os

MEMORY_FILE = 'memory.json'
HARDMEMORY_FILE = 'hardmemory.json'

if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

if not os.path.exists(HARDMEMORY_FILE):
    with open(HARDMEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

def save_to_memory(message, role):
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
    except:
        memory = []
    memory.append({'role': role, 'content': message})
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def load_hardmemory():
    try:
        with open(HARDMEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def summarize_hardmemory():
    memory = load_memory()
    # Расширенный список ключевых слов (русский + английский)
    keywords = [
        'important', 'важно', 'запомни', 'remember',
        'age', 'возраст', 'лет',
        'height', 'рост',
        'character', 'характер', 'личность',
        'external parameters', 'внешность', 'внешние параметры', 'appearance'
    ]
    important_info = [
        msg for msg in memory 
        if any(keyword in msg['content'].lower() for keyword in keywords)
    ]
    with open(HARDMEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(important_info, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        assistant = VoiceAssistant()
        assistant.start()
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}")
        os._exit(1)