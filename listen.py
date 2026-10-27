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
from contextlib import contextmanager
import time
import numpy as np
import requests
import pygame
import logging
import sqlite3  # Добавлено для чтения конфига
import uuid
import app_logging  # Configure shared console and rotating file logs before other imports.
from sintez import is_speaking_now, speak
from command import get_weather
import mistral_api
from desktop_tools import execute_desktop_tool, get_desktop_tools
from default_skills import (
    enabled_skill_ids,
    get_command_help,
    get_default_skill_prompt,
    is_skill_enabled,
)

# Настройка логгера
logger = logging.getLogger('VoiceAI')
_TOOL_ACTION_INTENT = re.compile(
    r"\b(?:найд\w*|поищ\w*|ищ\w*|поиск\w*|откр\w*|открыв|откройте|"
    r"перейд\w*|вбей\w*|напечата\w*|"
    r"посмотр\w*|прочита\w*|прочти|нажм\w*|кликн\w*|введ\w*|"
    r"прокрут\w*|обнов\w*|верн\w*|переключ\w*|закр\w*|запуст\w*|"
    r"навед\w*|выполн\w*|покаж\w*|погод\w*|экран\w*|браузер\w*|"
    r"вкладк\w*|ютуб\w*|youtube\b|видео\w*|сайт\w*|страниц\w*|"
    r"open\b|search\b|find\b|type\b|click\b|scroll\b|navigate\b|"
    r"launch\b|press\b)\b",
    re.IGNORECASE,
)
_ACTION_REQUEST_START = re.compile(
    r"^\s*(?:(?:пожалуйста|эй|люми|можешь|можете)\s+)*"
    r"(?:открой\w*|открыть|перейди\w*|зайди\w*|найди\w*|поищи\w*|"
    r"введи|вбей|набери|напечатай|нажми|кликни|прочитай|посмотри|"
    r"прокрути|закрой|запусти|обнови|open\b|search\b|find\b|click\b|"
    r"type\b|navigate\b|launch\b|press\b)\b",
    re.IGNORECASE,
)
DEFAULT_CONVERSATION_ID = "default"
_whisper_model_lock = threading.Lock()
_whisper_model = None
_whisper_model_name = None

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


def get_wake_word_engine_from_db():
    try:
        with sqlite3.connect(data_path("config.db")) as connection:
            row = connection.execute(
                "SELECT wake_word_engine FROM settings LIMIT 1"
            ).fetchone()
        return row[0] if row and row[0] else "Ручной режим без ключа"
    except sqlite3.Error:
        logger.exception("Не удалось прочитать режим активации голоса")
        return "Ручной режим без ключа"

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


def _describe_screen_with_vision(image, cancel_event=None):
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
        timeout=(5, 45),
    )
    if hasattr(cancel_event, "attach"):
        cancel_event.attach(response)
    try:
        with response:
            response.raise_for_status()
            description = (
                (response.json().get("message") or {}).get("content", "").strip()
            )
    finally:
        if hasattr(cancel_event, "detach"):
            cancel_event.detach(response)
    if not description:
        raise RuntimeError("Vision-модель не вернула описание экрана.")
    return description


def _parse_serialized_tool_call(content, desktop_tools):
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
        tool["function"]["name"] for tool in desktop_tools
    }
    if name not in allowed_names or not isinstance(arguments, dict):
        return None
    return {"type": "function", "function": {"name": name, "arguments": arguments}}


class ResponseCancelled(Exception):
    pass


class ResponseCancellation(threading.Event):
    def __init__(self):
        super().__init__()
        self._response_lock = threading.Lock()
        self._response = None

    def attach(self, response):
        with self._response_lock:
            self._response = response
        if self.is_set():
            response.close()

    def detach(self, response):
        with self._response_lock:
            if self._response is response:
                self._response = None

    def cancel(self):
        self.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            response.close()


def _raise_if_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise ResponseCancelled("Ответ остановлен.")


def _product_research_query(text):
    normalized = text.casefold()
    product = re.search(
        r"\b(телевизор(?:ы|а)?|телик|tv|ноутбук(?:и|а)?|"
        r"смартфон(?:ы|а)?|телефон(?:ы|а)?|монитор(?:ы|а)?|"
        r"видеокарт(?:а|ы|у)|пылесос(?:ы|а)?|холодильник(?:и|а)?|"
        r"стиральн(?:ая|ую)\s+машин(?:а|у)|наушник(?:и|ов)?)\b",
        normalized,
    )
    research_intent = re.search(
        r"\b(найди|подбери|сравни|выбери|лучший|лучшую|лучшее|"
        r"оптимальн\w*|что\s+лучше|посоветуй)\b",
        normalized,
    )
    if not product or not research_intent:
        return None

    product_name = product.group(1)
    if product_name == "телик":
        product_name = "телевизор"
    budget = re.search(
        r"\b(?:до|бюджет(?:е|ом)?|за)\s*(\d{1,3}(?:[ .]\d{3})+|\d{1,6})\s*"
        r"(тыс(?:яч)?|к|₽|руб(?:лей|ля|ль)?)?\b",
        normalized,
    )
    if budget:
        amount = int(re.sub(r"[ .]", "", budget.group(1)))
        unit = (budget.group(2) or "").casefold()
        if unit in {"тыс", "тысяч", "к"}:
            amount *= 1000
        if 1000 <= amount <= 10_000_000:
            return f"{product_name} до {amount} рублей"
    return f"{product_name} {text.strip()}"[:200]


def ask_ollama(
    full_memory: list,
    screen_image: str = None,
    on_delta=None,
    cancel_event=None,
) -> str:
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
    desktop_tools = get_desktop_tools()
    available_tool_names = {
        tool["function"]["name"] for tool in desktop_tools
    }
    tools_enabled = (
        not screen_image
        and bool(desktop_tools)
        and model_supports_tools(model)
    )
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
        "Открывай приложения только через open_application и только если имя "
        "есть в его разрешённом списке. Дополнительные приложения разрешены "
        "только если пользователь явно добавил их как навык с путём к EXE. "
        "Выполняй запросы-действия "
        "последовательностью перечисленных инструментов; не отвечай только "
        "инструкцией, если действие можно выполнить. Никогда не запускай CMD, "
        "PowerShell, скрипты или произвольные shell-команды. Доступны только "
        "перечисленные инструменты; не выдумывай другие действия."
    )
    if "get_weather" in available_tool_names:
        tool_instructions += " Для вопросов о погоде используй get_weather."
    if "browser_search" in available_tool_names:
        tool_instructions += " Для общего поиска используй browser_search."
    if "youtube_search" in available_tool_names:
        tool_instructions += (
            " Для поиска YouTube-видео используй youtube_search. Если пользователь "
            "просит открыть первое подходящее видео, сначала открой результаты, "
            "проанализируй видимый экран и только затем выбери видимую ссылку на видео."
        )
    if "market_search" in available_tool_names:
        tool_instructions += " Для поиска товаров используй market_search."
    if "steam_search" in available_tool_names:
        tool_instructions += (
            " Для поиска страницы игры именно в клиенте Steam используй steam_search. "
            "Для запуска уже установленной игры используй steam_launch_game только "
            "после явной просьбы пользователя."
        )
    if "steam_launch_game" in available_tool_names:
        tool_instructions += (
            " steam_launch_game запускает только найденную в локальных библиотеках "
            "установленную игру; не пытайся устанавливать игры или выполнять команды."
        )
    if "open_settings" in available_tool_names:
        tool_instructions += (
            " Для открытия системной страницы Windows используй open_settings и "
            "только один из разрешённых разделов."
        )
    if any(name in available_tool_names for name in ("browser_search", "market_search", "steam_search")):
        tool_instructions += (
            " Если пользователь просит сравнить товары и выбрать лучший по бюджету "
            "или характеристикам, действуй как исследователь: открой несколько "
            "релевантных страниц из разных предложений, используй OCR видимого "
            "содержимого, выпиши цену и характеристики, сравни их с критериями и "
            "назови источник/страницу каждого финалиста. Не придумывай отсутствующие "
            "данные и не совершай покупку. Для общего веб-поиска используй Google."
        )
    if "market_search" in available_tool_names:
        tool_instructions += (
            " Для запроса подобрать лучший товар не ограничивайся открытием выдачи: "
            "изучи минимум три разных подходящих предложения в пределах бюджета, "
            "сверь цену и видимые характеристики минимум у трех отдельных "
            "карточек/страниц через OCR, "
            "сравни их и объясни выбор. Если OCR/страницы недоступны, прямо сообщи "
            "об этом и не выдумывай характеристики."
        )
    if any(name.startswith("browser_") for name in available_tool_names):
        tool_instructions += (
            " Поиск и навигация должны быть видимыми в браузере по умолчанию. "
            "После открытия страницы используй возвращённый локальный OCR-текст, "
            "чтобы описать результаты и выбрать видимый элемент. "
            "Можно нажимать видимые безопасные элементы, но нельзя входить в аккаунты, "
            "вводить секреты, совершать покупки, оплачивать или отправлять формы."
        )
    if system and tools_enabled:
        system["content"] = f"{system.get('content', '')}\n\n{tool_instructions}"
    elif not system and tools_enabled:
        messages.insert(0, {"role": "system", "content": tool_instructions})

    answer_parts = []
    executed_tool = False
    latest_user_message = next(
        (
            message.get("content", "")
            for message in reversed(messages)
            if message.get("role") == "user"
        ),
        "",
    )
    shopping_query = _product_research_query(latest_user_message)
    shopping_research_enabled = (
        shopping_query is not None
        and "market_search" in available_tool_names
        and "browser_click" in available_tool_names
    )
    inspected_product_pages = set()
    product_evidence = []
    last_shopping_answer = ""

    def shopping_fallback():
        if len(inspected_product_pages) >= 3:
            evidence = "\n".join(
                f"- {title}: {details[:300]}"
                for title, details in product_evidence
            )
            return (
                "Проверила OCR минимум на трёх страницах, но Ollama не смогла "
                "сформировать надёжный итоговый выбор. Вот распознанные данные:\n"
                f"{evidence}\n"
                "Сравнение выше — только сырой OCR, характеристики могли "
                "распознаться неполно."
            )
        return (
            f"{last_shopping_answer}\n\nНе удалось подтвердить цены и "
            "характеристики минимум у трех отдельных предложений, поэтому "
            "не могу достоверно назвать лучший вариант."
            if last_shopping_answer
            else (
                "Поиск начат, но не удалось проверить цены и характеристики "
                "трёх отдельных предложений. Поэтому не могу достоверно "
                "назвать лучший вариант."
            )
        )

    if shopping_research_enabled:
        _raise_if_cancelled(cancel_event)
        logger.info("Начинаю исследование товара в Яндекс Маркете: %s", shopping_query)
        result = execute_desktop_tool("market_search", {"query": shopping_query})
        tool_content = result["content"]
        if result.get("image"):
            from command_OCR import get_all_screen_text

            screen_text = get_all_screen_text()
            tool_content += (
                "\nРаспознанный локальным OCR текст видимой выдачи:\n"
                f"{screen_text or '(на странице не распознан текст)'}"
            )
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "market_search",
                                "arguments": {"query": shopping_query},
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "name": "market_search",
                    "content": tool_content,
                },
            ]
        )
        executed_tool = True

    for _ in range(12):
        _raise_if_cancelled(cancel_event)
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.35,
                "num_predict": 256,
                "num_ctx": 4096,
            },
        }
        if tools_enabled:
            payload["tools"] = desktop_tools
        response = requests.post(
            f"{endpoint}/api/chat",
            json=payload,
            timeout=(4, 25),
            stream=True,
        )
        if hasattr(cancel_event, "attach"):
            cancel_event.attach(response)
        try:
            with response:
                response.raise_for_status()
                assistant_message = {"role": "assistant", "content": "", "tool_calls": []}
                buffered_content = ""
                content_stream_started = False
                done_reason = None
                for line in response.iter_lines(decode_unicode=True):
                    _raise_if_cancelled(cancel_event)
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    event = json.loads(line)
                    if error := event.get("error"):
                        raise RuntimeError(f"Ошибка Ollama: {error}")
                    if event.get("done"):
                        done_reason = event.get("done_reason")
                    chunk = event.get("message") or {}
                    content = chunk.get("content") or ""
                    if content:
                        assistant_message["content"] += content
                        if on_delta and not shopping_query:
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
        finally:
            if hasattr(cancel_event, "detach"):
                cancel_event.detach(response)

        tool_calls = assistant_message["tool_calls"]
        serialized_tool_call = False
        if not tool_calls and tools_enabled and not executed_tool:
            serialized_call = _parse_serialized_tool_call(
                assistant_message["content"],
                desktop_tools,
            )
            if serialized_call:
                tool_calls = [serialized_call]
                assistant_message["tool_calls"] = tool_calls
                assistant_message["content"] = ""
                serialized_tool_call = True
        if not serialized_tool_call:
            answer_parts.append(assistant_message["content"])
        if not tool_calls and tools_enabled and not executed_tool:
            if _ACTION_REQUEST_START.search(latest_user_message):
                generated_text = assistant_message["content"].strip()
                if generated_text:
                    suffix = (
                        "\n\nКоманда не была выполнена: локальная модель не "
                        "вызвала доступный инструмент."
                    )
                    answer_parts[-1] += suffix
                    if on_delta and content_stream_started:
                        on_delta(suffix)
                    logger.warning(
                        "Ollama ответила текстом вместо вызова инструмента; "
                        "сохраняю ответ без выполнения команды: %s",
                        latest_user_message,
                    )
                else:
                    logger.error(
                        "Ollama не вызвала инструмент и не вернула текст: %s",
                        latest_user_message,
                    )
                    raise RuntimeError(
                        "Локальная модель не вернула ответ и не вызвала "
                        "доступный инструмент."
                    )
        if not tool_calls:
            if shopping_research_enabled and len(inspected_product_pages) < 3:
                last_shopping_answer = assistant_message["content"].strip()
                if answer_parts:
                    answer_parts.pop()
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": assistant_message["content"],
                        },
                        {
                            "role": "user",
                            "content": (
                                "Продолжи исследование товара: пока проверено только "
                                f"{len(inspected_product_pages)} отдельных карточек с "
                                "распознанной ценой. Используй OCR видимой страницы, "
                                "открой через browser_click еще разные подходящие "
                                "товары и проверь их цену и характеристики. Не "
                                "завершай сравнением без фактических данных."
                            ),
                        },
                    ]
                )
                continue
            if buffered_content and on_delta:
                on_delta(buffered_content)
            answer = "".join(answer_parts)
            if not answer.strip():
                logger.error(
                    "Ollama завершила запрос без текста: model=%s, done_reason=%r, "
                    "tool_calls=%d",
                    model,
                    done_reason,
                    len(tool_calls),
                )
                if shopping_query:
                    answer = shopping_fallback()
                    if on_delta:
                        on_delta(answer)
                    return answer
                raise RuntimeError("Ollama завершила ответ без текста.")
            if shopping_query and len(inspected_product_pages) < 3:
                answer += (
                    "\n\nНе удалось подтвердить цены и характеристики минимум у "
                    "трех отдельных предложений; это не подтверждённая рекомендация."
                )
            if shopping_query and on_delta:
                on_delta(answer)
            logger.info("[Локальная нейросеть Ollama] Ответ: %s", answer)
            return answer

        messages.append({
            key: value for key, value in assistant_message.items()
            if not key.startswith("_")
        })
        for call in tool_calls:
            _raise_if_cancelled(cancel_event)
            function = call["function"]
            logger.info("Выполняю инструмент управления: %s", function["name"])
            arguments = function["arguments"]
            if fragment := function.pop("_arguments_fragment", ""):
                try:
                    arguments.update(json.loads(fragment))
                except json.JSONDecodeError as error:
                    raise RuntimeError("Ollama вернула некорректные аргументы инструмента.") from error
            result = execute_desktop_tool(function["name"], arguments)
            executed_tool = True
            tool_message = {
                "role": "tool",
                "name": function["name"],
                "content": result["content"],
            }
            if image := result.get("image"):
                if function["name"].startswith("browser_") or function["name"] == "youtube_search":
                    from command_OCR import get_all_screen_text

                    screen_text = get_all_screen_text()
                    tool_message["content"] += (
                        "\nТекст видимой страницы, распознанный локальным OCR:\n"
                        f"{screen_text}"
                    )
                    if (
                        shopping_query
                        and function["name"] == "browser_click"
                        and screen_text
                        and re.search(
                            r"\d[\d\s.,]{0,12}\s*(?:₽|руб(?:\.|лей|ля)?|р\.)",
                            screen_text,
                            flags=re.IGNORECASE,
                        )
                    ):
                        title = " ".join(
                            arguments.get("text", "").casefold().split()
                        )
                        if title not in inspected_product_pages:
                            inspected_product_pages.add(title)
                            product_evidence.append((title, screen_text))
                else:
                    tool_message["content"] += "\n" + _describe_screen_with_vision(
                        image,
                        cancel_event=cancel_event,
                    )
            messages.append(tool_message)
    if shopping_query:
        answer = shopping_fallback()
        if on_delta:
            on_delta(answer)
        logger.warning("Исследование товара не завершилось за лимит инструментов.")
        return answer
    raise RuntimeError("Ollama превысила лимит последовательных вызовов инструментов.")

# --- Функция для текстового общения (используется в GUI) ---
def _run_direct_chat_command(text, cancel_event=None):
    normalized = text.casefold().strip()
    if re.search(
        r"\b(?:какие команды|список команд|что ты умеешь|какие у тебя команды|покажи команды)\b",
        normalized,
    ):
        return f"Сейчас доступны такие команды. {get_command_help()}"

    if re.search(r"\bпогод\w*\b", normalized) and not re.search(
        r"\b(?:google|гугл(?:е|а)?)\b", normalized
    ):
        if not is_skill_enabled("weather"):
            return "Команда погоды отключена в настройках навыков."
        city_match = re.search(
            r"\bв\s+(?:городе\s+)?(.+?)(?=\s+(?:сейчас|сегодня|завтра)\b|[?!.]|$)",
            text,
            flags=re.IGNORECASE,
        )
        city = city_match.group(1).strip() if city_match else None
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool("get_weather", {"city": city})["content"]

    youtube_query = None
    youtube_search_patterns = (
        r"\b(?:найди|поищи|поиск(?:ай)?|введи|вбей|набери)\s+(.+?)\s+"
        r"в\s+поиске\s+(?:youtube|ютубе?)\b",
        r"\b(?:найди|поищи|поиск(?:ай)?|введи|вбей|набери)\s+"
        r"(?:в\s+)?(?:youtube|ютубе?)\s+(?:в\s+поиске\s+)?(.+)",
        r"\b(?:найди|поищи|поиск(?:ай)?|введи|вбей|набери)\s+(.+?)\s+"
        r"(?:в|на)\s+(?:youtube|ютубе?)\b",
        r"\b(?:открой|откройте|открыть|перейди|перейдите|зайди|зайдите)\s+"
        r"(?:мне\s+)?(?:в\s+)?(?:youtube|ютубе?)(?:\.com)?[,:;]?\s+"
        r"(?:и\s+)?(?:найди|поищи|введи|вбей|набери)\s+"
        r"(?:в\s+поиск(?:е)?\s+)?(.+)",
        r"\b(?:открой|откройте|открыть|перейди|перейдите|зайди|зайдите)\s+"
        r"(?:мне\s+)?(?:в\s+)?(?:youtube|ютубе?)(?:\.com)?[,:;]?\s+"
        r"(?:и\s+)?(?:(?:в\s+)?поиск(?:е)?\s+)?"
        r"(?:(?:найди|поищи|введи|вбей|набери)\s+)?(.+)",
        r"\b(?:youtube|ютубе?)\s+поиск(?:е)?\s+(.+)",
    )
    for pattern in youtube_search_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            youtube_query = match.group(1).strip(" \t\r\n.,!?;:")
            if youtube_query:
                break
            youtube_query = None

    if youtube_query is not None:
        if not is_skill_enabled("browser_search"):
            return "Поиск YouTube отключён в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "youtube_search", {"query": youtube_query}
        )["content"]

    google_query = None
    google_search_patterns = (
        r"\b(?:найди|поищи|поиск(?:ай)?|введи|вбей|набери)\s+"
        r"(?:в\s+)?(?:google|гугл(?:е|а)?)(?:\s+в\s+поиске)?\s+(.+)",
        r"\b(?:найди|поищи|поиск(?:ай)?|введи|вбей|набери)\s+(.+?)\s+"
        r"(?:в|на)\s+(?:google|гугл(?:е|а)?)\b",
        r"\b(?:открой|зайди|перейди)\b.*?(?:google|гугл(?:е|а)?)"
        r".*?\b(?:найди|поищи|введи|вбей|набери)\s+(.+)",
    )
    for pattern in google_search_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            google_query = match.group(1).strip(" \t\r\n.,!?;:")
            if google_query:
                break
            google_query = None
    if google_query is not None:
        if not is_skill_enabled("browser_search"):
            return "Поиск в интернете отключён в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "browser_search", {"query": google_query}
        )["content"]

    steam_launch_match = re.search(
        r"\b(?:запусти|открой|играй\s+в)\s+(?:игру\s+)?(.+?)\s+"
        r"(?:в\s+(?:steam|стим(?:е)?)|из\s+(?:steam|стим(?:а)?))\b",
        normalized,
    )
    if steam_launch_match is None:
        steam_launch_match = re.search(
            r"\b(?:в\s+(?:steam|стим(?:е)?)\s+)?"
            r"(?:запусти|открой)\s+игру\s+(.+)",
            normalized,
        )
    if steam_launch_match:
        if not is_skill_enabled("steam_control"):
            return "Управление Steam отключено в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "steam_launch_game",
            {"query": steam_launch_match.group(1).strip(" .!?")},
        )["content"]

    steam_preposed_search = re.search(
        r"\b(?:открой|найди|поищи)\s+(?:мне\s+)?(?:в\s+)?"
        r"(?:steam|стим(?:е)?)\s+(.+)$",
        normalized,
    )
    if steam_preposed_search:
        query = steam_preposed_search.group(1).strip(" .!?")
        if query and is_skill_enabled("steam_control"):
            _raise_if_cancelled(cancel_event)
            return execute_desktop_tool("steam_search", {"query": query})["content"]

    steam_search_match = re.search(
        r"\b(?:найди|поищи|открой)\s+(?:страницу\s+)?(?:игры\s+)?"
        r"(.+?)\s+(?:в\s+)?(?:steam|стим(?:е)?)\b",
        normalized,
    )
    if steam_search_match and re.search(r"\b(?:steam|стим)", normalized):
        query = steam_search_match.group(1).strip(" .!?")
        if query and is_skill_enabled("steam_control"):
            _raise_if_cancelled(cancel_event)
            return execute_desktop_tool("steam_search", {"query": query})["content"]

    open_steam = re.fullmatch(
        r"\s*(?:(?:пожалуйста|люми)\s+)?(?:открой(?:те)?|открыть|запусти(?:те)?)"
        r"\s+(?:мне\s+)?(?:steam|стим)\s*[.!?]*",
        normalized,
    )
    if open_steam:
        if not is_skill_enabled("open_application"):
            return "Открытие приложений отключено в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool("open_application", {"name": "steam"})["content"]

    open_riot = re.fullmatch(
        r"\s*(?:(?:пожалуйста|люми)\s+)?(?:открой(?:те)?|открыть|запусти(?:те)?)"
        r"\s+(?:мне\s+)?(?:riot(?:\s+games)?|riot\s+client)\s*[.!?]*",
        normalized,
    )
    if open_riot:
        if not is_skill_enabled("open_application"):
            return "Открытие приложений отключено в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "open_application", {"name": "riot games"}
        )["content"]

    settings_match = re.search(
        r"\b(?:открой|перейди|покажи)\s+(?:мне\s+)?(?:настройки|настройки Windows)"
        r"(?:\s+(?:экрана|дисплея|звука|bluetooth|сети|приложений|обновлений))?\b",
        normalized,
    )
    if settings_match:
        if not is_skill_enabled("system_settings"):
            return "Открытие настроек Windows отключено в настройках навыков."
        section = "display" if "экран" in normalized or "диспле" in normalized else (
            "sound" if "звук" in normalized else
            "bluetooth" if "bluetooth" in normalized else
            "network" if "сет" in normalized else
            "apps" if "приложен" in normalized else
            "update" if "обновлен" in normalized else "display"
        )
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool("open_settings", {"section": section})["content"]

    if not _TOOL_ACTION_INTENT.search(normalized):
        return None

    if not is_skill_enabled("open_application") and re.search(
        r"\b(?:браузер|интернет|youtube|ютуб)\b", normalized
    ):
        return None

    open_browser = re.fullmatch(
        r"\s*(?:(?:пожалуйста|люми)\s+)?"
        r"(?:открой(?:те)?|открыть|открыв)\s+"
        r"(?:мне\s+)?(?:браузер|интернет)\s*[.!?]*\s*",
        normalized,
    )
    if open_browser:
        if not is_skill_enabled("open_application"):
            return "Команда открытия приложений отключена в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "open_application", {"name": "browser"}
        )["content"]

    open_youtube = re.fullmatch(
        r"\s*(?:(?:пожалуйста|люми)\s+)?"
        r"(?:открой(?:те)?|открыть|открыв|перейди(?:те)?)\s+"
        r"(?:мне\s+)?(?:youtube|ютуб)(?:\.com)?\s*[.!?]*\s*",
        normalized,
    )
    if open_youtube:
        if not is_skill_enabled("browser_navigate"):
            return "Открытие страниц браузера отключено в настройках навыков."
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "browser_navigate", {"url": "https://www.youtube.com/"}
        )["content"]

    market_match = re.search(
        r"(?:найди|поищи|поиск)\s+(?:товар\s+)?(?:на\s+)?"
        r"(?:яндекс\s+)?маркет(?:е)?\s+(.+)$",
        normalized,
    )
    if market_match and is_skill_enabled("market_search"):
        _raise_if_cancelled(cancel_event)
        return execute_desktop_tool(
            "market_search", {"query": market_match.group(1).strip(" .!?")}
        )["content"]

    return None


def process_text_query(
    text: str,
    screen_image: str = None,
    on_delta=None,
    cancel_event=None,
    conversation_id=DEFAULT_CONVERSATION_ID,
) -> str:
    """Обрабатывает текстовый запрос без голосового вывода (для GUI чата)"""
    save_to_memory(text, 'user', conversation_id)
    if conversation_id == DEFAULT_CONVERSATION_ID:
        summarize_hardmemory(conversation_id)
    
    hard_memory = (
        load_hardmemory()
        if conversation_id == DEFAULT_CONVERSATION_ID
        else []
    )
    memory = load_memory(conversation_id)
    current_system_prompt = get_system_prompt_from_db()
    from skills import get_user_skill_prompt

    skill_prompt = get_user_skill_prompt()
    if skill_prompt:
        current_system_prompt = f"{current_system_prompt}\n\n{skill_prompt}"
    current_system_prompt = (
        f"{current_system_prompt}\n\n{get_default_skill_prompt()}"
    )
    
    full_memory = [
        {'role': 'system', 'content': current_system_prompt},
        *hard_memory,
        *memory,
    ]
    try:
        try:
            direct_result = _run_direct_chat_command(text, cancel_event)
        except ResponseCancelled:
            raise
        except Exception as error:
            logger.exception("Не удалось выполнить локальную команду")
            direct_result = f"Не удалось выполнить команду: {error}"
        if direct_result is not None:
            response_text = direct_result
            if on_delta:
                on_delta(response_text)
        elif screen_image or _TOOL_ACTION_INTENT.search(text):
            response_text = ask_ollama(
                full_memory,
                screen_image=screen_image,
                on_delta=on_delta,
                cancel_event=cancel_event,
            )
        elif get_ai_provider_from_db().lower().startswith("mistral"):
            try:
                response = mistral_api.chat_with_mistral(
                    full_memory[-1]["content"],
                    full_memory[:-1],
                    on_delta=on_delta,
                    cancel_event=cancel_event,
                )
                response_text = response['choices'][0]['message']['content'].strip()
                if not response_text or response_text.startswith(("ОШИБКА:", "Ошибка соединения")):
                    raise RuntimeError(response_text or "Пустой ответ Mistral")
                logger.info("Mistral ответил")
            except Exception as e:
                if cancel_event is not None and cancel_event.is_set():
                    raise ResponseCancelled("Ответ остановлен.") from e
                logger.warning("Mistral недоступен, переключаюсь на Ollama: %s", e)
                response_text = ask_ollama(
                    full_memory, on_delta=on_delta, cancel_event=cancel_event
                )
        else:
            response_text = ask_ollama(
                full_memory, on_delta=on_delta, cancel_event=cancel_event
            )
    except ResponseCancelled:
        logger.info("Генерация ответа остановлена пользователем")
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            raise ResponseCancelled("Ответ остановлен.") from e
        logger.exception("Не удалось получить ответ от AI")
        response_text = f"Не удалось получить ответ от локальной нейросети Ollama: {e}"

    _raise_if_cancelled(cancel_event)
    save_to_memory(response_text, 'assistant', conversation_id)
    summarize_hardmemory(conversation_id)
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
        self.recognizer.pause_threshold = 0.7
        self.recognizer.phrase_threshold = 0.55
        self.recognizer.non_speaking_duration = 0.3
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.8
        self._microphone_calibrated = False
        self._listen_after_speech = 0.0
        self._wake_stream_lock = threading.Lock()
        self.response_cancel_event = ResponseCancellation()
        self.wake_word_engine = get_wake_word_engine_from_db()
        
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
        self.local_wake_enabled = (
            self.porcupine is None
            and self.wake_word_engine
            in {"Локальное слово «Люми»", "Porcupine"}
        )
        
        self.audio_stream = None 
        
        self.command_actions = {
            "наведи на": self._handle_move,
            "наведи курсор на": self._handle_move,
            "перемести на": self._handle_move,
            "нажми на": self._handle_click,
            "кликни на": self._handle_click,
            "клик по": self._handle_click,
            "щелкни по": self._handle_click,
            "прочитай текст на экране": self._read_screen_text,
            "прочитай текст с экрана": self._read_screen_text,
            "что на экране": self._screen,
            "посмотри на экран": self._screen,
            "прочитай экран": self._screen,
            "погода": self._weather,
            "стоп": self.cancel_response,
            "отмена": self.cancel_response,
            "замолчи": self.cancel_response,
            "выход": self.stop
        }
        self.command_skill_ids = {
            **{
                command: "screen_move_cursor"
                for command in (
                    "наведи на",
                    "наведи курсор на",
                    "перемести на",
                )
            },
            **{
                command: "screen_click_text"
                for command in (
                    "нажми на",
                    "кликни на",
                    "клик по",
                    "щелкни по",
                )
            },
            **{
                command: "screen_read_text"
                for command in (
                    "прочитай текст на экране",
                    "прочитай текст с экрана",
                )
            },
            **{
                command: "screen_vision"
                for command in ("что на экране", "посмотри на экран", "прочитай экран")
            },
            "погода": "weather",
        }

        self.is_listening = False
        self.waiting_for_wake_word = self.local_wake_enabled
        self.is_running = False 
        self.listener_thread = None
        self.wake_thread = None
        self.response_thread = None
        self.response_lock = threading.Lock()
        self.response_active = False
        self._interrupt_command_pending = False
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
        self.pyaudio_device_index = None
        if input_device:
            try:
                self.pyaudio_device_index = next(
                    (
                        index
                        for index in range(self.pyaudio.get_device_count())
                        if self.pyaudio.get_device_info_by_index(index).get(
                            "maxInputChannels", 0
                        ) > 0
                        and self.pyaudio.get_device_info_by_index(index)
                        .get("name", "")
                        .strip()
                        == input_device.strip()
                    ),
                    None,
                )
                if self.pyaudio_device_index is None:
                    logger.warning(
                        "Выбранный микрофон «%s» не найден для wake-word; "
                        "использую устройство по умолчанию",
                        input_device,
                    )
            except Exception:
                logger.exception("Не удалось выбрать микрофон для wake-word")

    def start(self):
        self.is_running = True
        if self.porcupine is not None:
            self.wake_thread = threading.Thread(
                target=self._detect_wakeword,
                daemon=True,
            )
            self.wake_thread.start()
            logger.info("Голосовой ассистент запущен; ожидаю ключевое слово")
        else:
            self.is_listening = True
            if self.local_wake_enabled:
                logger.info("Локальная активация по слову «Люми» (Whisper, без API)")
            else:
                logger.info("Голосовой ассистент запущен в режиме постоянного прослушивания")

        self._play_sound("start")
        self.listener_thread = threading.Thread(target=self._listen_commands, daemon=True)
        self.listener_thread.start()

        if __name__ == "__main__":
            try:
                while self.is_running:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                self.stop()

    def prepare(self):
        """Load speech recognition and calibrate the microphone before activation."""
        self._load_whisper_model()
        if not self._microphone_calibrated:
            with self.microphone as source:
                logger.info("Калибрую микрофон для голосовой активации")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.35)
                self._microphone_calibrated = True

    def _detect_wakeword(self):
        while self.is_running:
            if self.is_listening or is_speaking_now():
                self._close_wake_stream()
                time.sleep(0.1)
                continue
            try:
                with self._wake_stream_lock:
                    if self.audio_stream is None or not self.audio_stream.is_active():
                        stream_options = {
                            "rate": self.porcupine.sample_rate,
                            "channels": 1,
                            "format": pyaudio.paInt16,
                            "input": True,
                            "frames_per_buffer": self.porcupine.frame_length,
                        }
                        if self.pyaudio_device_index is not None:
                            stream_options["input_device_index"] = self.pyaudio_device_index
                        self.audio_stream = self.pyaudio.open(**stream_options)
                    pcm = self.audio_stream.read(
                        self.porcupine.frame_length,
                        exception_on_overflow=False,
                    )
                pcm = np.frombuffer(pcm, dtype=np.int16)
                if self.porcupine.process(pcm) >= 0:
                    logger.info("🔊 Wake word активирована!")
                    self.is_listening = True
                    self.last_activity = time.time()
                    self._play_sound('start')
                    self._close_wake_stream()
            except Exception:
                logger.exception("Ошибка локального обнаружения wake-word")
                self._close_wake_stream()
                time.sleep(0.5)

        self._close_wake_stream()

    def _close_wake_stream(self):
        with self._wake_stream_lock:
            if self.audio_stream is not None:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except Exception:
                    logger.exception("Не удалось закрыть аудиопоток wake-word")
                finally:
                    self.audio_stream = None

    def _listen_commands(self):
        while self.is_running:
            if not self.is_listening:
                time.sleep(0.1)
                continue
            if is_speaking_now() and not self.response_active:
                self._listen_after_speech = time.monotonic() + 1.0
                time.sleep(0.1)
                continue
            if time.monotonic() < self._listen_after_speech:
                time.sleep(0.1)
                continue

            try:
                if (
                    (self.porcupine or self.local_wake_enabled)
                    and not self.response_active
                    and time.time() - self.last_activity > self.command_timeout
                ):
                    if self.local_wake_enabled:
                        self.waiting_for_wake_word = True
                        self.last_activity = time.time()
                        logger.info(
                            "Тишина больше %s секунд; жду ключевое слово «Люми»",
                            self.command_timeout,
                        )
                    else:
                        self.is_listening = False
                        logger.info(
                            "Тишина больше %s секунд; голосовое прослушивание остановлено",
                            self.command_timeout,
                        )
                    continue

                with self.microphone as source:
                    if not self._microphone_calibrated:
                        logger.info("Калибрую микрофон по фоновому шуму")
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.35)
                        self._microphone_calibrated = True
                    logger.info("Слушаю команду...")
                    phrase_time_limit = 2.2 if self.response_active else 8
                    try:
                        audio = self.recognizer.listen(
                            source, timeout=0.8, phrase_time_limit=phrase_time_limit
                        )
                        if not self.is_running:
                            break
                        text = self._transcribe_local(audio).lower()
                        if not self.is_running:
                            break
                        if text:
                            logger.info("Whisper распознала русскую речь: %s", text)
                            if self.response_active:
                                normalized = re.sub(
                                    r"[^\w\s]", " ", text.casefold()
                                ).strip()
                                if re.fullmatch(
                                    r"(?:(?:эй|привет|окей)\s+)?(?:люми\s+)?(?:стоп|отмена|замолчи)(?:\s+(?:стоп|отмена|замолчи))*",
                                    normalized,
                                ):
                                    self.cancel_response()
                                else:
                                    if is_skill_enabled("voice_interrupt"):
                                        with self.response_lock:
                                            queue_interruption = (
                                                not self._interrupt_command_pending
                                            )
                                            self._interrupt_command_pending = True
                                        if queue_interruption:
                                            logger.info(
                                                "Речь распознана во время ответа; "
                                                "останавливаю озвучивание и обрабатываю "
                                                "новую команду: %s",
                                                text,
                                            )
                                            self.cancel_response()
                                            threading.Thread(
                                                target=self._process_after_interruption,
                                                args=(text,),
                                                daemon=True,
                                                name="lumi-voice-interruption",
                                            ).start()
                                    else:
                                        logger.debug(
                                            "Речь во время ответа проигнорирована: %s",
                                            text,
                                        )
                                continue
                            if self.local_wake_enabled and self.waiting_for_wake_word:
                                if self._activate_local_wake_word(text):
                                    self.waiting_for_wake_word = False
                                    self.last_activity = time.time()
                                    self._play_sound("start")
                                    logger.info("Обнаружено локальное слово «Люми»")
                                    remainder = re.sub(
                                        r"^\s*(?:(?:привет|эй|окей)\s+)?(?:люми|люмия)\b[\s,:;.!?-]*",
                                        "",
                                        text,
                                        flags=re.IGNORECASE,
                                    ).strip()
                                    if remainder:
                                        self._process_command(remainder)
                                        self.last_activity = time.time()
                                    else:
                                        self._play_sound("confirm")
                                else:
                                    logger.debug("Wake-word не распознано")
                                continue
                            self._process_command(text)
                            self.last_activity = time.time()
                        else:
                            logger.debug("Whisper не обнаружила речь; продолжаю слушать")
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
        try:
            self._load_whisper_model()
            pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self._whisper_model.transcribe(
                samples,
                language="ru",
                beam_size=1,
                vad_filter=True,
                vad_parameters={
                    "min_speech_duration_ms": 100,
                    "min_silence_duration_ms": 300,
                    "speech_pad_ms": 200,
                },
                condition_on_previous_text=False,
                initial_prompt=(
                    "Разговорная русская речь. Имена: Люми, Люмия. "
                    "Команды: погода, стоп, отмена, прочитай текст на экране, "
                    "нажми на, наведи на, что на экране, какие команды есть."
                ),
            )
            accepted_segments = []
            for segment in segments:
                if getattr(segment, "no_speech_prob", 0.0) >= 0.6:
                    logger.debug(
                        "Whisper отфильтровала фрагмент без речи (вероятность %.2f)",
                        segment.no_speech_prob,
                    )
                    continue
                accepted_segments.append(segment.text.strip())
            return " ".join(accepted_segments).strip()
        except ImportError as e:
            raise RuntimeError(
                "Для локального распознавания установите faster-whisper "
                "и перезапустите приложение."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Не удалось распознать локальную речь: {e}"
            ) from e

    def _load_whisper_model(self):
        global _whisper_model, _whisper_model_name

        if _whisper_model is None:
            with _whisper_model_lock:
                if _whisper_model is None:
                    self._initialize_whisper_model()

        self._whisper_model = _whisper_model
        self._whisper_model_name = _whisper_model_name

    def _initialize_whisper_model(self):
        global _whisper_model, _whisper_model_name

        model_name = os.environ.get("LUMI_WHISPER_MODEL")
        try:
            from faster_whisper import WhisperModel
            from ollama_models import get_hardware_profile

            profile = get_hardware_profile()
            if not model_name:
                model_name = "base" if profile["ram_gb"] < 10 else "small"
            model_path = data_path(
                Path("models") / f"faster-whisper-{model_name}"
            )
            cpu_threads = min(max(1, profile["cpu_threads"] - 1), 8)
            logger.info("Загружаю локальную модель распознавания Whisper: %s", model_name)
            _whisper_model = WhisperModel(
                str(model_path) if model_path.exists() else model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(data_path("models")),
                cpu_threads=cpu_threads,
            )
            _whisper_model_name = model_name
            logger.info("Локальная модель Whisper готова: %s", model_name)
        except ImportError as error:
            raise RuntimeError(
                "Для локального распознавания установите faster-whisper "
                "и перезапустите приложение."
            ) from error
        except Exception as error:
            model_label = model_name or "автоматически выбранная"
            raise RuntimeError(
                f"Не удалось загрузить локальную модель Whisper "
                f"({model_label}): {error}"
            ) from error

    @staticmethod
    def _activate_local_wake_word(text):
        words = re.findall(r"\w+", text.casefold())
        if not words:
            return False
        wake_words = {"люми", "люмия"}
        greetings = {"привет", "эй", "окей"}
        return words[0] in wake_words or (
            len(words) > 1
            and words[0] in greetings
            and words[1] in wake_words
        )

    def cancel_response(self, text=None):
        self.response_cancel_event.cancel()
        try:
            import sintez

            sintez.stop_speaking()
        except Exception:
            logger.exception("Не удалось остановить озвучивание ответа")

    def _process_after_interruption(self, text):
        while self.is_running and self.response_active:
            time.sleep(0.05)
        with self.response_lock:
            self._interrupt_command_pending = False
        if self.is_running:
            self._process_command(text)

    def _process_command(self, text):
        """Run an explicit desktop command or ask the selected local AI."""
        text = re.sub(
            r"^\s*(?:(?:привет|эй|окей)\s+)?(?:люми|люмия)\b[\s,:;.!?-]*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        if not text:
            self.is_listening = True
            self.last_activity = time.time()
            speak("Я слушаю.")
            return

        if re.search(
            r"\b(?:какие команды|список команд|что ты умеешь|какие у тебя команды|покажи команды)\b",
            text.casefold(),
        ):
            answer = f"Сейчас доступны такие команды. {get_command_help()}"
            if self.on_user_text:
                self.on_user_text(text)
            if self.on_response_complete:
                self.on_response_complete(answer)
            speak(answer)
            return

        normalized_text = re.sub(r"[^\w\s]", "", text.casefold())
        for cmd in sorted(self.command_actions, key=len, reverse=True):
            action = self.command_actions[cmd]
            skill_id = self.command_skill_ids.get(cmd)
            if skill_id and skill_id not in enabled_skill_ids():
                speak("Эта команда отключена в настройках навыков.")
                return
            if re.search(rf"(?<!\w){re.escape(cmd)}(?!\w)", normalized_text):
                try:
                    action(text)
                    return
                except Exception:
                    logger.exception("Не удалось выполнить голосовую команду %s", cmd)
                    speak("Не удалось выполнить команду")
                    self._play_sound('error')
                    return
        
        if self._try_direct_desktop_command(text):
            return
        direct_result = _run_direct_chat_command(text)
        if direct_result is not None:
            if self.on_user_text:
                self.on_user_text(text)
            if self.on_response_complete:
                self.on_response_complete(direct_result)
            save_to_memory(text, "user")
            save_to_memory(direct_result, "assistant")
            speak(direct_result)
            return
        if len(text.split()) >= 2:
            self._start_response(text)

        else:
            logger.info("Не распознано значимой команды")
            speak("Повторите, пожалуйста")

    def _try_direct_desktop_command(self, text):
        normalized = text.casefold().strip()

        open_match = re.search(
            r"^(?:пожалуйста\s+)?(?:открой|запусти|открыть)\s+(.+?)\s*$",
            normalized,
        )
        if open_match:
            requested = re.sub(r"[.!?]+$", "", open_match.group(1)).strip()
            applications = {
                "браузер": "browser",
                "интернет": "browser",
                "стим": "steam",
                "steam": "steam",
                "riot": "riot games",
                "riot games": "riot games",
                "riot client": "riot games",
                "калькулятор": "calculator",
                "блокнот": "notepad",
                "проводник": "explorer",
                "диспетчер задач": "task manager",
            }
            application = applications.get(requested)
            if application:
                if not is_skill_enabled("open_application"):
                    speak("Команда открытия приложений отключена в настройках навыков.")
                    return True
                try:
                    execute_desktop_tool("open_application", {"name": application})
                    speak(f"Открываю {requested}.")
                except Exception:
                    logger.exception("Не удалось открыть приложение %s", requested)
                    speak(f"Не удалось открыть {requested}.")
                return True

        press_match = re.search(
            r"^(?:нажми|нажать)(?:\s+клавишу)?\s+([\w+]+)\s*[.!?]*$",
            normalized,
        )
        if press_match:
            if not is_skill_enabled("press_keys"):
                speak("Команда нажатия клавиш отключена в настройках навыков.")
                return True
            key_aliases = {
                "ввод": "enter",
                "энтер": "enter",
                "escape": "esc",
                "эскейп": "esc",
                "пробел": "space",
                "контрол+с": "ctrl+s",
                "контрол+а": "ctrl+a",
                "контрол+в": "ctrl+v",
            }
            key = key_aliases.get(press_match.group(1), press_match.group(1))
            try:
                result = execute_desktop_tool("press_keys", {"keys": key})
                speak(result["content"])
            except ValueError as error:
                logger.info("Отклонена неподдерживаемая клавиша: %s", error)
                speak("Эта клавиша не входит в разрешённый список.")
            return True

        return False

    def _start_response(self, text, screen_image=None):
        with self.response_lock:
            if self.response_active:
                self.cancel_response()
                logger.info("Предыдущая генерация отменяется перед новым запросом")
                return
            self.response_cancel_event.clear()
            self.response_active = True
        self.response_thread = threading.Thread(
            target=self._answer_query,
            args=(text, screen_image),
            daemon=True,
            name="lumi-response",
        )
        self.response_thread.start()

    def _answer_query(self, text, screen_image=None):
        try:
            logger.info("Отправка запроса нейросети: %s", text)
            if self.on_user_text:
                self.on_user_text(text)
            speech_buffer = []

            def on_response_chunk(chunk):
                if self.on_response_chunk:
                    self.on_response_chunk(chunk)
                speech_buffer.append(chunk)
                current = "".join(speech_buffer)
                sentences = re.split(r"(?<=[.!?])\s+", current)
                speech_buffer[:] = sentences[-1:]
                completed = " ".join(part.strip() for part in sentences[:-1]).strip()
                if completed:
                    speak(completed)

            response = process_text_query(
                text,
                screen_image=screen_image,
                on_delta=on_response_chunk,
                cancel_event=self.response_cancel_event,
            )
            if self.response_cancel_event.is_set():
                raise ResponseCancelled("Ответ остановлен.")
            remaining = "".join(speech_buffer).strip()
            if remaining:
                speak(remaining)
            import sintez

            while self.is_running and sintez.is_speaking_now():
                if self.response_cancel_event.wait(0.05):
                    raise ResponseCancelled("Ответ остановлен.")
            if self.on_response_complete:
                self.on_response_complete(response)
        except ResponseCancelled:
            logger.info("Ответ отменён пользователем")
            if self.on_response_complete:
                self.on_response_complete("Ответ остановлен.")
        except Exception:
            logger.exception("Не удалось обработать голосовой запрос")
            if self.on_response_complete:
                self.on_response_complete("Не удалось обработать запрос.")
        finally:
            with self.response_lock:
                self.response_active = False
                if self.is_listening:
                    self.last_activity = time.time()

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
        self._start_response(text, screen_image)

    def _read_screen_text(self, text):
        from command_OCR import get_all_screen_text

        screen_text = get_all_screen_text()
        if self.on_user_text:
            self.on_user_text(text)
        if self.on_response_complete:
            self.on_response_complete(screen_text)
        speak(screen_text)

    def _weather(self, text=None):
        logger.info("Команда: погода")
        try:
            city_match = re.search(
                r"\bв\s+(?:городе\s+)?(.+?)(?=\s+(?:сейчас|сегодня|завтра)\b|[?!.]|$)",
                text or "",
                flags=re.IGNORECASE,
            )
            city = city_match.group(1).strip() if city_match else None
            weather = get_weather(city=city)
            if not weather:
                raise RuntimeError(
                    "Не удалось определить город или получить данные погоды."
                )
            speak(
                f"Сейчас в городе {weather['city']}: "
                f"{weather['temp']} градусов, {weather['weather']}."
            )
            logger.info(f"☀️ Погода: {weather['temp']}")
        except Exception as e:
            logger.error(f"Ошибка погоды: {e}")
            speak("Не удалось получить погоду")
            self._play_sound('error')

    def _play_sound(self, name):
        if name in self.sounds:
            self.sounds[name].play()

    def stop(self, text=None):
        self.cancel_response()
        summarize_hardmemory() 
        self.is_running = False
        self.is_listening = False
        
        self._close_wake_stream()

        if self.wake_thread and self.wake_thread is not current_thread():
            self.wake_thread.join(timeout=2)
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

@contextmanager
def _chat_connection():
    connection = sqlite3.connect(data_path("config.db"), timeout=10)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _ensure_chat_store():
    with _chat_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                    REFERENCES chat_conversations(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS chat_messages_conversation "
            "ON chat_messages(conversation_id, id)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS chat_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO chat_conversations (id, title)
            VALUES (?, ?)
            """,
            (DEFAULT_CONVERSATION_ID, "Голосовой диалог"),
        )
        migrated = connection.execute(
            "SELECT value FROM chat_metadata WHERE key = 'legacy_memory_imported'"
        ).fetchone()
        if not migrated:
            legacy_memory = []
            if Path(MEMORY_FILE).is_file():
                try:
                    with open(MEMORY_FILE, "r", encoding="utf-8") as memory_file:
                        legacy_memory = json.load(memory_file)
                except (OSError, json.JSONDecodeError):
                    logger.exception("Не удалось импортировать старую историю чата")
            if isinstance(legacy_memory, list):
                for message in legacy_memory:
                    if (
                        isinstance(message, dict)
                        and message.get("role") in {"user", "assistant"}
                        and isinstance(message.get("content"), str)
                    ):
                        connection.execute(
                            """
                            INSERT INTO chat_messages (conversation_id, role, content)
                            VALUES (?, ?, ?)
                            """,
                            (
                                DEFAULT_CONVERSATION_ID,
                                message["role"],
                                message["content"],
                            ),
                        )
                if legacy_memory:
                    connection.execute(
                        """
                        UPDATE chat_conversations
                        SET title = 'История до обновления'
                        WHERE id = ?
                        """,
                        (DEFAULT_CONVERSATION_ID,),
                    )
            connection.execute(
                "INSERT INTO chat_metadata (key, value) VALUES "
                "('legacy_memory_imported', '1')"
            )


def create_conversation(title="Новый чат"):
    _ensure_chat_store()
    conversation_id = uuid.uuid4().hex
    with _chat_connection() as connection:
        connection.execute(
            "INSERT INTO chat_conversations (id, title) VALUES (?, ?)",
            (conversation_id, title),
        )
    return conversation_id


def list_conversations():
    _ensure_chat_store()
    with _chat_connection() as connection:
        return [
            {"id": row[0], "title": row[1], "updated_at": row[2]}
            for row in connection.execute(
                """
                SELECT id, title, updated_at
                FROM chat_conversations
                ORDER BY updated_at DESC, created_at DESC
                """
            )
        ]


def clear_conversation(conversation_id):
    _ensure_chat_store()
    with _chat_connection() as connection:
        connection.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        connection.execute(
            """
            UPDATE chat_conversations
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            ("Голосовой диалог" if conversation_id == DEFAULT_CONVERSATION_ID else "Новый чат",
             conversation_id),
        )
    if conversation_id == DEFAULT_CONVERSATION_ID:
        with open(HARDMEMORY_FILE, "w", encoding="utf-8") as memory_file:
            json.dump([], memory_file)


def delete_conversation(conversation_id):
    if conversation_id == DEFAULT_CONVERSATION_ID:
        raise ValueError("Основной голосовой чат нельзя удалить.")
    _ensure_chat_store()
    with _chat_connection() as connection:
        connection.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        connection.execute(
            "DELETE FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        )


def save_to_memory(message, role, conversation_id=DEFAULT_CONVERSATION_ID):
    if role not in {"user", "assistant"}:
        raise ValueError("Роль сообщения должна быть user или assistant.")
    if not isinstance(message, str):
        raise TypeError("Текст сообщения должен быть строкой.")
    _ensure_chat_store()
    with _chat_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if not exists:
            raise ValueError("Чат уже удалён или не существует.")
        is_first_user_message = (
            role == "user"
            and connection.execute(
                "SELECT 1 FROM chat_messages WHERE conversation_id = ? LIMIT 1",
                (conversation_id,),
            ).fetchone()
            is None
        )
        connection.execute(
            """
            INSERT INTO chat_messages (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (conversation_id, role, message),
        )
        if is_first_user_message:
            title = " ".join(message.split())[:48] or "Новый чат"
            connection.execute(
                """
                UPDATE chat_conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title, conversation_id),
            )
        else:
            connection.execute(
                "UPDATE chat_conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conversation_id,),
            )


def load_memory(conversation_id=DEFAULT_CONVERSATION_ID):
    _ensure_chat_store()
    with _chat_connection() as connection:
        return [
            {"role": row[0], "content": row[1]}
            for row in connection.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY id
                """,
                (conversation_id,),
            )
        ]

def load_hardmemory():
    try:
        with open(HARDMEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def summarize_hardmemory(conversation_id=DEFAULT_CONVERSATION_ID):
    if conversation_id != DEFAULT_CONVERSATION_ID:
        return
    memory = load_memory(conversation_id)
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