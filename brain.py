# ai_test.py
import requests
import logging
from g4f.client import Client  # Резервный вариант
from sintez import *

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('AITest')

def ask_ai(question: str, use_ollama: bool = True) -> str:
    """
    Задаёт вопрос нейросети (Ollama или GPT4Free)
    
    :param question: Текст вопроса
    :param use_ollama: Приоритетно использовать локальную Ollama
    :return: Ответ нейросети или сообщение об ошибке
    """
    if use_ollama:
        try:
            return ask_ollama(question)
        except Exception as e:
            logger.warning(f"Ollama не сработала: {e}.")

def ask_ollama(question: str) -> str:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3",
            "prompt": f"[INST] ответь максимально развёнуто на русском языке на мой вопрос чтобы я всё понял , вопрос: {question} [/INST]",
            "stream": False,
            "options": {"temperature": 0.5}
        },
        timeout=20
    )
    
    if response.status_code != 200:
        raise ConnectionError(f"HTTP {response.status_code}: {response.text}")
    
    result = response.json()
    return result.get("response", "").split("[/INST]")[-1].strip()


if __name__ == "__main__":
    while True:
        question = input("\nВаш вопрос (или 'exit'): ")
        if question.lower() == 'exit':
            break
        text = "\n[Ollama] Ответ:", ask_ollama(question)
        speak(text)
        print("[Автовыбор] Ответ:", ask_ai(question))