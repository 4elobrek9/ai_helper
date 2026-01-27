import requests
import sqlite3
import os

# Убрали ключ по умолчанию, теперь если его нет - вернется None
DEFAULT_API_KEY = None
API_URL = 'https://api.mistral.ai/v1/chat/completions'

def get_api_key_from_db():
    """Пытается получить API ключ из базы данных конфигурации GUI"""
    db_path = 'config.db'
    if not os.path.exists(db_path):
        return DEFAULT_API_KEY
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT api_key FROM settings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0] and len(row[0].strip()) > 5:
            return row[0].strip()
        return DEFAULT_API_KEY
    except Exception as e:
        print(f"Error loading API key from DB: {e}")
        return DEFAULT_API_KEY

def chat_with_mistral(prompt, memory=None):
    # Динамически получаем ключ при каждом запросе
    current_api_key = get_api_key_from_db()

    if not current_api_key:
        return {"choices": [{"message": {"content": "ОШИБКА: Не указан API ключ Mistral. Пожалуйста, укажите его в настройках."}}]}

    headers = {
        'Authorization': f'Bearer {current_api_key}',
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

    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status() # Проверка на ошибки HTTP
        return response.json()
    except Exception as e:
        return {"choices": [{"message": {"content": f"Ошибка соединения с API: {e}"}}]}

if __name__ == '__main__':
    prompt = "Hello, how are you?"
    response = chat_with_mistral(prompt)
    print(response)