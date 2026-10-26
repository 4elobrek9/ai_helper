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
import sqlite3  # Добавлено для чтения конфига
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

# Системный промпт (персона Люмия) - значение по умолчанию
DEFAULT_SYSTEM_PROMPT = "Ответь на русском и достаточно понятно (говори от женского рода милой доброй девушки c интересной жизнью, говори МАКСИМАЛЬНО человечно, тебя зовут Люмия или просто Люми, любишь паучью лилию). При ответе не стоит здороваться или что-то типо того."

def get_system_prompt_from_db():
    """Загружает системный промпт из базы данных GUI"""
    db_path = 'config.db'
    if not os.path.exists(db_path):
        return DEFAULT_SYSTEM_PROMPT
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT prompt FROM settings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        # Если в базе есть промпт и он не пустой, возвращаем его
        if row and row[0] and len(row[0].strip()) > 0:
            return row[0].strip()
        return DEFAULT_SYSTEM_PROMPT
    except Exception as e:
        logger.error(f"Ошибка чтения промпта из БД: {e}")
        return DEFAULT_SYSTEM_PROMPT

def get_porcupine_key_from_db():
    """Загружает Porcupine AccessKey из базы данных"""
    db_path = 'config.db'
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Проверяем наличие колонки (на случай старой БД) - это делается в GUI init_db, тут просто select
        cursor.execute("SELECT porcupine_key FROM settings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row and row[0] and len(row[0].strip()) > 0:
            return row[0].strip()
        return None
    except Exception as e:
        return None

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

# --- Функция для текстового общения (используется в GUI) ---
def process_text_query(text: str) -> str:
    """Обрабатывает текстовый запрос без голосового вывода (для GUI чата)"""
    save_to_memory(text, 'user')
    summarize_hardmemory()
    
    hard_memory = load_hardmemory()
    memory = load_memory()
    current_system_prompt = get_system_prompt_from_db()
    
    full_memory = hard_memory + [{'role': 'system', 'content': current_system_prompt}] + memory
    
    response_text = "..."
    try:
        response = mistral_api.chat_with_mistral(text, full_memory)
        response_text = response['choices'][0]['message']['content'].strip()
        logger.info("Mistral ответил в чат")
    except Exception as e:
        logger.warning(f"Mistral Error: {e}")
        try:
            response_text = ask_ollama(text, full_memory)
        except:
            response_text = "Ошибка: Нейросети недоступны."

    save_to_memory(response_text, 'assistant')
    summarize_hardmemory()
    return response_text

class VoiceAssistant:
    def __init__(self):
        
        pygame.mixer.init()
        # Проверка путей к звукам, чтобы не падало, если файлов нет
        self.sounds = {}
        try:
            self.sounds['start'] = pygame.mixer.Sound('./audio/right.mp3')
            self.sounds['confirm'] = pygame.mixer.Sound('./audio/right.mp3')
            self.sounds['error'] = pygame.mixer.Sound('./audio/lie.mp3')
        except:
            logger.warning("Звуковые файлы не найдены")

        self.pyaudio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 400
        
        # ПОЛУЧЕНИЕ КЛЮЧА ИЗ БД
        pv_access_key = get_porcupine_key_from_db()
        if not pv_access_key:
            logger.error("ОШИБКА: Porcupine AccessKey не найден в настройках! Голосовая активация не будет работать.")
            self.porcupine = None # Флаг, что не работает
        else:
            try:
                self.porcupine = pvporcupine.create(
                    access_key=pv_access_key,
                    keyword_paths=['models/lumia.ppn']
                )
            except Exception as e:
                logger.error(f"Ошибка инициализации Porcupine: {e}")
                self.porcupine = None
        
        self.audio_stream = None 
        
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
        self.is_running = False 
        self.command_timeout = 10
        self.last_activity = 0
        self.microphone = sr.Microphone()

    def start(self):
        if self.porcupine is None:
            logger.error("Невозможно запустить: нет ключа Porcupine")
            speak("Ошибка ключа голосового движка")
            return

        self.is_running = True
        logger.info("🚀 Ассистент запущен!")
        speak("Система готова к работе")

        self.audio_stream = self.pyaudio.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)

        t1 = threading.Thread(target=self._detect_wakeword, daemon=True)
        t2 = threading.Thread(target=self._listen_commands, daemon=True)
        t1.start()
        t2.start()

        if __name__ == "__main__":
            try:
                while self.is_running:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                self.stop()

    def _detect_wakeword(self):
        while self.is_running:
            try:
                if self.audio_stream is None or not self.audio_stream.is_active():
                     time.sleep(0.1)
                     continue

                pcm = self.audio_stream.read(
                    self.porcupine.frame_length, 
                    exception_on_overflow=False
                )
                pcm = np.frombuffer(pcm, dtype=np.int16)
                if self.porcupine.process(pcm) >= 0:
                    logger.info("🔊 Wake word активирована!")
                    self.is_listening = True
                    self.last_activity = time.time()
                    self._play_sound('start')
            except Exception as e:
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
        
        if len(text.split()) >= 2: 
            logger.info(f"Отправка запроса нейросети: {text}")
            speak("Секунду, формулирую мысль")
            
            save_to_memory(text, 'user')
            summarize_hardmemory()
            
            hard_memory = load_hardmemory()
            memory = load_memory()
            current_system_prompt = get_system_prompt_from_db()
            
            full_memory = hard_memory + [{'role': 'system', 'content': current_system_prompt}] + memory
            
            response_text = None
            
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

    def stop(self, text=None):
        summarize_hardmemory() 
        self.is_running = False
        
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                print(f"Ошибка закрытия потока: {e}")
        
        logger.info("🔴 Ассистент остановлен")
        if __name__ == "__main__":
             self.pyaudio.terminate()
             pygame.quit()
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