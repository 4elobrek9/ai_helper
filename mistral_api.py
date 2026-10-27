import json
import logging
import requests
import sqlite3
import os
from contextlib import closing
from app_paths import data_path

# Убрали ключ по умолчанию, теперь если его нет - вернется None
DEFAULT_API_KEY = None
API_URL = 'https://api.mistral.ai/v1/chat/completions'
logger = logging.getLogger("lumi.mistral")

def get_api_key_from_db():
    """Пытается получить API ключ из базы данных конфигурации GUI"""
    db_path = str(data_path('config.db'))
    if not os.path.exists(db_path):
        return DEFAULT_API_KEY
    
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT api_key FROM settings LIMIT 1")
            row = cursor.fetchone()
        
        if row and row[0] and len(row[0].strip()) > 5:
            return row[0].strip()
        return DEFAULT_API_KEY
    except (sqlite3.Error, OSError) as e:
        logger.exception("Не удалось прочитать ключ Mistral")
        return DEFAULT_API_KEY

def chat_with_mistral(prompt, memory=None, on_delta=None, cancel_event=None):
    # Динамически получаем ключ при каждом запросе
    current_api_key = get_api_key_from_db()

    if not current_api_key:
        return {"choices": [{"message": {"content": "ОШИБКА: Не указан API ключ Mistral. Пожалуйста, укажите его в настройках."}}]}

    headers = {
        "Authorization": f"Bearer {current_api_key}",
        'Content-Type': 'application/json'
    }
    messages = [{'role': 'user', 'content': prompt}]
    if memory:
        messages = memory + messages
    data = {
        'model': 'mistral-large-2411',
        'messages': messages,
        'max_tokens': 150,
        'temperature': 0.7
    }
    data["stream"] = True

    try:
        if cancel_event is not None and cancel_event.is_set():
            raise requests.RequestException("Запрос остановлен.")
        response = requests.post(
            API_URL,
            headers=headers,
            json=data,
            timeout=(4, 25),
            stream=True,
        )
        if hasattr(cancel_event, "attach"):
            cancel_event.attach(response)
        try:
            with response:
                response.raise_for_status()
                content_parts = []
                for line in response.iter_lines(decode_unicode=True):
                    if cancel_event is not None and cancel_event.is_set():
                        raise requests.RequestException("Запрос остановлен.")
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    if not line.startswith("data:"):
                        continue
                    event_data = line[5:].strip()
                    if event_data == "[DONE]":
                        break
                    event = json.loads(event_data)
                    delta = (
                        event.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        content_parts.append(delta)
                        if on_delta:
                            on_delta(delta)
                return {
                    "choices": [
                        {"message": {"content": "".join(content_parts).strip()}}
                    ]
                }
        finally:
            if hasattr(cancel_event, "detach"):
                cancel_event.detach(response)
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            raise
        return {"choices": [{"message": {"content": f"Ошибка соединения с API: {e}"}}]}

if __name__ == '__main__':
    prompt = "Hello, how are you?"
    response = chat_with_mistral(prompt)
    logger.info("Тестовый ответ Mistral: %s", response)
