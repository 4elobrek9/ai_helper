# ai_test.py
import logging
import desktop_agent
from sintez import *

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('AITest')

def ask_ai(question: str, use_ollama: bool = True) -> str:
    """Обрабатывает запрос только локальным агентом Ollama."""
    return desktop_agent.run_agent_turn([], question)

def ask_ollama(question: str) -> str:
    return desktop_agent.run_agent_turn([], question)


if __name__ == "__main__":
    while True:
        question = input("\nВаш вопрос (или 'exit'): ")
        if question.lower() == 'exit':
            break
        text = ask_ollama(question)
        speak(text)
        print("[Ollama] Ответ:", text)