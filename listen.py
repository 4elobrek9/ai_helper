import os
import re
from pathlib import Path
from app_paths import data_path, resource_path
from ollama_models import AUTO_MODEL, model_supports_tools, resolve_model
import pvporcupine
import pyaudio
import speech_recognition as sr
import threading
from threading import current_thread
import time
import numpy as np
import requests
import pygame
import logging
import sqlite3  # Добавлено для чтения конфига
from sintez import is_speaking_now, speak
from command import get_weather
import mistral_api
from desktop_tools import DESKTOP_TOOLS, execute_desktop_tool

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
    db_path = str(data_path('config.db'))
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
    db_path = str(data_path('config.db'))
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Проверяем наличие колонки (на случай старой БД) - это делается в GUI init_db, тут просто select
        cursor.execute("SELECT porcupine_key, wake_word_engine FROM settings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row and row[1] == "Porcupine" and row[0] and len(row[0].strip()) > 0:
            return row[0].strip()
        return None
    except Exception as e:
        return None

def get_ai_provider_from_db():
    db_path = data_path('config.db')
    if not db_path.exists():
        return "Ollama"
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT ai_provider FROM settings LIMIT 1").fetchone()
        return row[0] if row and row[0] else "Ollama"
    except sqlite3.Error:
        logger.exception("Не удалось прочитать выбранного AI-провайдера")
        return "Ollama"


def get_ollama_model_from_db(vision=False):
    column = "ollama_vision_model" if vision else "ollama_chat_model"
    try:
        with sqlite3.connect(data_path("config.db")) as conn:
            row = conn.execute(f"SELECT {column} FROM settings LIMIT 1").fetchone()
        return row[0] if row and row[0] else AUTO_MODEL
    except sqlite3.Error:
        logger.exception("Не удалось прочитать выбранную модель Ollama")
        return AUTO_MODEL


def _describe_screen_with_vision(image):
    endpoint = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = resolve_model(
        os.environ.get("LUMI_OLLAMA_VISION_MODEL")
        or get_ollama_model_from_db(vision=True),
        vision=True,
    )
    response = requests.post(
        f"{endpoint}/api/chat",
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Опиши кратко видимые окна, элементы интерфейса и важный текст "
                        "на выбранном экране. Не выполняй никаких действий."
                    ),
                    "images": [image],
                }
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 512},
        },
        timeout=(10, 180),
    )
    response.raise_for_status()
    description = (response.json().get("message") or {}).get("content", "").strip()
    if not description:
        raise RuntimeError("Vision-модель не вернула описание экрана.")
    return description


def _parse_serialized_tool_call(content):
    try:
        serialized = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(serialized, dict):
        return None
    name = serialized.get("name")
    arguments = serialized.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    allowed_names = {
        tool["function"]["name"] for tool in DESKTOP_TOOLS
    }
    if name not in allowed_names or not isinstance(arguments, dict):
        return None
    return {"type": "function", "function": {"name": name, "arguments": arguments}}


def ask_ollama(full_memory: list, screen_image: str = None, on_delta=None) -> str:
    """Stream a local Ollama conversation and execute its safe desktop tools."""
    endpoint = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = resolve_model(
        os.environ.get(
            "LUMI_OLLAMA_VISION_MODEL" if screen_image else "LUMI_OLLAMA_MODEL"
        )
        or get_ollama_model_from_db(vision=bool(screen_image)),
        vision=bool(screen_image),
        require_tools=not bool(screen_image),
    )
    tools_enabled = not screen_image and model_supports_tools(model)
    messages = [dict(message) for message in full_memory]
    if screen_image:
        messages[-1]["images"] = [screen_image]
    system = next(
        (message for message in messages if message.get("role") == "system"),
        None,
    )
    tool_instructions = (
        "Ты Lumi, помощница, которая умеет работать с компьютером через перечисленные "
        "инструменты. Отвечай по-русски. Если пользователь явно просит открыть приложение, "
        "посмотреть выбранный экран, нажать на видимый элемент, ввести текст или нажать "
        "клавиши — выполни это через подходящий инструмент, а не отказывайся и не давай "
        "инструкцию вместо действия. Сначала используй inspect_screen, если нужно определить "
        "содержимое экрана. Выполняй только действия, о которых попросил пользователь. "
        "Доступны только перечисленные безопасные инструменты; не выдумывай другие действия."
    )
    if system and tools_enabled:
        system["content"] = f"{system.get('content', '')}\n\n{tool_instructions}"
    elif not system and tools_enabled:
        messages.insert(0, {"role": "system", "content": tool_instructions})

    answer_parts = []
    for _ in range(6):
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.4, "num_predict": 768},
        }
        if tools_enabled:
            payload["tools"] = DESKTOP_TOOLS
        with requests.post(
            f"{endpoint}/api/chat",
            json=payload,
            timeout=(10, 180),
            stream=True,
        ) as response:
            response.raise_for_status()
            assistant_message = {"role": "assistant", "content": "", "tool_calls": []}
            buffered_content = ""
            content_stream_started = False
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                event = json.loads(line)
                if error := event.get("error"):
                    raise RuntimeError(f"Ошибка Ollama: {error}")
                chunk = event.get("message") or {}
                content = chunk.get("content") or ""
                if content:
                    assistant_message["content"] += content
                    if on_delta:
                        if content_stream_started:
                            on_delta(content)
                        else:
                            buffered_content += content
                            candidate = buffered_content.lstrip()
                            compact_candidate = re.sub(r"\s+", "", candidate)
                            tool_prefixes = ('{"name"', '{"arguments"')
                            if (
                                any(prefix.startswith(compact_candidate) for prefix in tool_prefixes)
                                or any(compact_candidate.startswith(prefix) for prefix in tool_prefixes)
                            ):
                                continue
                            on_delta(buffered_content)
                            buffered_content = ""
                            content_stream_started = True
                for index, tool_call in enumerate(chunk.get("tool_calls") or []):
                    while len(assistant_message["tool_calls"]) <= index:
                        assistant_message["tool_calls"].append(
                            {"type": "function", "function": {"name": "", "arguments": {}}}
                        )
                    target = assistant_message["tool_calls"][index]["function"]
                    incoming = tool_call.get("function") or {}
                    target["name"] = incoming.get("name") or target["name"]
                    arguments = incoming.get("arguments")
                    if isinstance(arguments, dict):
                        target["arguments"].update(arguments)
                    elif isinstance(arguments, str):
                        try:
                            target["arguments"].update(json.loads(arguments))
                        except json.JSONDecodeError:
                            target["_arguments_fragment"] = (
                                target.get("_arguments_fragment", "") + arguments
                            )

        tool_calls = assistant_message["tool_calls"]
        serialized_tool_call = False
        if not tool_calls and tools_enabled:
            serialized_call = _parse_serialized_tool_call(assistant_message["content"])
            if serialized_call:
                tool_calls = [serialized_call]
                assistant_message["tool_calls"] = tool_calls
                assistant_message["content"] = ""
                serialized_tool_call = True
        if not serialized_tool_call:
            answer_parts.append(assistant_message["content"])
        if not tool_calls:
            if buffered_content and on_delta:
                on_delta(buffered_content)
            answer = "".join(answer_parts)
            if not answer.strip():
                raise RuntimeError("Ollama завершила ответ без текста.")
            print(f"\n[Локальная нейросеть Ollama] Ответ: {answer}")
            return answer

        messages.append({
            key: value for key, value in assistant_message.items()
            if not key.startswith("_")
        })
        for call in tool_calls:
            function = call["function"]
            arguments = function["arguments"]
            if fragment := function.pop("_arguments_fragment", ""):
                try:
                    arguments.update(json.loads(fragment))
                except json.JSONDecodeError as error:
                    raise RuntimeError("Ollama вернула некорректные аргументы инструмента.") from error
            result = execute_desktop_tool(function["name"], arguments)
            tool_message = {
                "role": "tool",
                "name": function["name"],
                "content": result["content"],
            }
            if image := result.get("image"):
                tool_message["content"] += "\n" + _describe_screen_with_vision(image)
            messages.append(tool_message)
    raise RuntimeError("Ollama превысила лимит последовательных вызовов инструментов.")

# --- Функция для текстового общения (используется в GUI) ---
def process_text_query(text: str, screen_image: str = None, on_delta=None) -> str:
    """Обрабатывает текстовый запрос без голосового вывода (для GUI чата)"""
    save_to_memory(text, 'user')
    summarize_hardmemory()
    
    hard_memory = load_hardmemory()
    memory = load_memory()
    current_system_prompt = get_system_prompt_from_db()
    
    full_memory = hard_memory + [{'role': 'system', 'content': current_system_prompt}] + memory
    try:
        if screen_image:
            response_text = ask_ollama(
                full_memory, screen_image=screen_image, on_delta=on_delta
            )
        elif get_ai_provider_from_db().lower().startswith("mistral"):
            try:
                response = mistral_api.chat_with_mistral(full_memory[-1]['content'], full_memory[:-1])
                response_text = response['choices'][0]['message']['content'].strip()
                if not response_text or response_text.startswith(("ОШИБКА:", "Ошибка соединения")):
                    raise RuntimeError(response_text or "Пустой ответ Mistral")
                logger.info("Mistral ответил")
            except Exception as e:
                logger.warning("Mistral недоступен, переключаюсь на Ollama: %s", e)
                response_text = ask_ollama(full_memory, on_delta=on_delta)
        else:
            response_text = ask_ollama(full_memory, on_delta=on_delta)
    except Exception as e:
        logger.exception("Не удалось получить ответ от AI")
        response_text = f"Не удалось получить ответ от локальной нейросети Ollama: {e}"

    save_to_memory(response_text, 'assistant')
    summarize_hardmemory()
    return response_text

class VoiceAssistant:
    def __init__(
        self,
        input_device=None,
        on_user_text=None,
        on_response_chunk=None,
        on_response_complete=None,
    ):
        self.on_user_text = on_user_text
        self.on_response_chunk = on_response_chunk
        self.on_response_complete = on_response_complete
        
        pygame.mixer.init()
        # Проверка путей к звукам, чтобы не падало, если файлов нет
        self.sounds = {}
        try:
            self.sounds['start'] = pygame.mixer.Sound(str(resource_path('audio/right.mp3')))
            self.sounds['confirm'] = pygame.mixer.Sound(str(resource_path('audio/right.mp3')))
            self.sounds['error'] = pygame.mixer.Sound(str(resource_path('audio/lie.mp3')))
        except:
            logger.warning("Звуковые файлы не найдены")

        self.pyaudio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self._microphone_calibrated = False
        self._listen_after_speech = 0.0
        
        # ПОЛУЧЕНИЕ КЛЮЧА ИЗ БД
        pv_access_key = get_porcupine_key_from_db()
        if not pv_access_key:
            logger.info("Porcupine не настроен; используется ручной режим без ключа")
            self.porcupine = None
        else:
            try:
                self.porcupine = pvporcupine.create(
                    access_key=pv_access_key,
                    keyword_paths=[str(resource_path('models/lumia.ppn'))]
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
            "что на экране": self._screen,
            "посмотри на экран": self._screen,
            "прочитай экран": self._screen,
            "погода": self._weather,
            "стоп": self.stop,
            "выход": self.stop
        }

        self.is_listening = False
        self.is_running = False 
        self.listener_thread = None
        self.command_timeout = 10
        self.last_activity = 0
        device_index = None
        if input_device:
            try:
                devices = sr.Microphone.list_microphone_names()
                device_index = next(
                    (
                        index for index, name in enumerate(devices)
                        if name.strip() == input_device.strip()
                    ),
                    None,
                )
                if device_index is None:
                    logger.warning(
                        "Выбранный микрофон «%s» не найден; использую системный по умолчанию",
                        input_device,
                    )
            except Exception:
                logger.exception("Не удалось перечислить микрофоны; использую системный")
        self.microphone = sr.Microphone(device_index=device_index)

    def start(self):
        self.is_running = True
        if self.porcupine is not None:
            self.audio_stream = self.pyaudio.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )
            threading.Thread(target=self._detect_wakeword, daemon=True).start()
            logger.info("Голосовой ассистент запущен; ожидаю ключевое слово")
        else:
            self.is_listening = True
            logger.info("Голосовой ассистент запущен в режиме прослушивания без ключевого слова")

        speak("Система готова к работе")
        self.listener_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self.listener_thread.start()

        if __name__ == "__main__":
            try:
                while self.is_running:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                self.stop()

    def _detect_wakeword(self):
        while self.is_running:
            if is_speaking_now():
                time.sleep(0.1)
                continue
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
            if not self.is_listening:
                time.sleep(0.1)
                continue
            if is_speaking_now():
                self._listen_after_speech = time.monotonic() + 1.0
                time.sleep(0.1)
                continue
            if time.monotonic() < self._listen_after_speech:
                time.sleep(0.1)
                continue

            try:
                if self.porcupine and time.time() - self.last_activity > self.command_timeout:
                    self.is_listening = False
                    continue

                with self.microphone as source:
                    if not self._microphone_calibrated:
                        logger.info("Калибрую микрофон по фоновому шуму")
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.7)
                        self._microphone_calibrated = True
                    logger.info("Слушаю команду...")
                    try:
                        audio = self.recognizer.listen(
                            source, timeout=3, phrase_time_limit=12
                        )
                        if not self.is_running:
                            break
                        text = self._transcribe_local(audio).lower()
                        if not self.is_running:
                            break
                        if text:
                            logger.info("Whisper распознала русскую речь: %s", text)
                            self._process_command(text)
                            self.last_activity = time.time()
                        else:
                            logger.info("Whisper не обнаружила речь; продолжаю слушать")
                    except sr.WaitTimeoutError:
                        continue
                    except RuntimeError as e:
                        logger.error("Локальное распознавание речи недоступно: %s", e)
                        speak(str(e))
                        self.is_listening = False
            except Exception:
                logger.exception("Ошибка в обработке голосовой команды")
                time.sleep(0.1)

    def _transcribe_local(self, audio):
        model_name = os.environ.get("LUMI_WHISPER_MODEL", "small")
        model_path = data_path(Path("models") / f"faster-whisper-{model_name}")
        try:
            from faster_whisper import WhisperModel

            if not hasattr(self, "_whisper_model"):
                self._whisper_model = WhisperModel(
                    str(model_path) if model_path.exists() else model_name,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(data_path("models")),
                )
            pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self._whisper_model.transcribe(
                samples,
                language="ru",
                beam_size=5,
                vad_filter=False,
                condition_on_previous_text=False,
                initial_prompt="Разговорная русская речь. Имена: Люми, Люмия.",
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except ImportError as e:
            raise RuntimeError(
                "Для локального распознавания установите faster-whisper "
                "и перезапустите приложение."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Не удалось загрузить локальную модель Whisper ({model_name}): {e}"
            ) from e

    def _process_command(self, text):
        """Run an explicit desktop command or ask the selected local AI."""
        normalized_text = re.sub(r"[^\w\s]", "", text.casefold())
        for cmd, action in self.command_actions.items():
            if f" {cmd} " in f" {normalized_text} " or normalized_text.startswith(cmd + " ") or normalized_text.endswith(" " + cmd) or normalized_text == cmd:
                try:
                    action(text)
                    return
                except Exception:
                    logger.exception("Не удалось выполнить голосовую команду %s", cmd)
                    speak("Не удалось выполнить команду")
                    self._play_sound('error')
                    return
        
        if len(text.split()) >= 2: 
            logger.info(f"Отправка запроса нейросети: {text}")
            speak("Секунду, формулирую мысль")
            if self.on_user_text:
                self.on_user_text(text)
            response = process_text_query(text, on_delta=self.on_response_chunk)
            if not self.is_running:
                return
            if self.on_response_complete:
                self.on_response_complete(response)
            speak(response)

        else:
            logger.info("Не распознано значимой команды")
            speak("Повторите, пожалуйста")

    def _handle_move(self, text):
        from command_OCR import move_to_text

        for prefix in ["наведи на", "наведи курсор на", "перемести на", "наведи на"]:
            if prefix in text:
                target = text.split(prefix)[-1].strip()
                logger.info(f"Команда: навести курсор на '{target}'")
                if not move_to_text(target, threshold=70):
                    self._play_sound('error')
                return

    def _handle_click(self, text):
        from command_OCR import click_to_text

        for prefix in ["нажми на", "кликни на", "клик по", "нажми", "кликни", "клик"]:
            if prefix in text:
                target = text.split(prefix)[-1].strip()
                logger.info(f"Команда: клик по '{target}'")
                if not click_to_text(target, clicks=1):
                    self._play_sound('error')
                return

    def _screen(self, text):
        from command_OCR import get_screen_image

        screen_image = get_screen_image()
        if self.on_user_text:
            self.on_user_text(text)
        answer = process_text_query(
            text,
            screen_image=screen_image,
            on_delta=self.on_response_chunk,
        )
        if not self.is_running:
            return
        if self.on_response_complete:
            self.on_response_complete(answer)
        speak(answer)

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
        self.is_listening = False
        
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                print(f"Ошибка закрытия потока: {e}")

        if self.listener_thread and self.listener_thread is not current_thread():
            self.listener_thread.join(timeout=2)
        
        logger.info("🔴 Ассистент остановлен")
        try:
             self.pyaudio.terminate()
        except Exception:
            logger.exception("Не удалось освободить аудиоустройство")


# Функции работы с памятью
import json
import os

MEMORY_FILE = str(data_path('memory.json'))
HARDMEMORY_FILE = str(data_path('hardmemory.json'))

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