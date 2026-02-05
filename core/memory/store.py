import json
import os

MEMORY_FILE = 'memory.json'
HARDMEMORY_FILE = 'hardmemory.json'


def _ensure_files() -> None:
    for file_name in (MEMORY_FILE, HARDMEMORY_FILE):
        if not os.path.exists(file_name):
            with open(file_name, 'w', encoding='utf-8') as f:
                json.dump([], f)


def save_to_memory(message, role):
    _ensure_files()
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
    except Exception:
        memory = []
    memory.append({'role': role, 'content': message})
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def load_memory():
    _ensure_files()
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def load_hardmemory():
    _ensure_files()
    try:
        with open(HARDMEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
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
        msg for msg in memory if any(keyword in msg['content'].lower() for keyword in keywords)
    ]
    with open(HARDMEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(important_info, f, ensure_ascii=False, indent=2)


_ensure_files()
