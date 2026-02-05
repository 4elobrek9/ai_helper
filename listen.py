from core.memory.store import load_hardmemory, load_memory, save_to_memory, summarize_hardmemory
from core.voice.assistant import VoiceAssistant, ask_ollama, process_text_query

__all__ = [
    'VoiceAssistant',
    'ask_ollama',
    'process_text_query',
    'save_to_memory',
    'load_memory',
    'load_hardmemory',
    'summarize_hardmemory',
]


if __name__ == '__main__':
    assistant = VoiceAssistant()
    assistant.start()
