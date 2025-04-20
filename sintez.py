import torch
import sounddevice as sd
import numpy as np
from threading import Thread
import re

# Загрузка модели
device = torch.device('cpu')
model, _ = torch.hub.load(
    repo_or_dir='snakers4/silero-models',
    model='silero_tts',
    language='ru',
    speaker='v3_1_ru'
)

def format_number(num):
    """Конвертирует число в проговариваемый формат"""
    num_str = str(num)
    return ' '.join(list(num_str.replace('.', ' точка ')))

def split_long_text(text, max_length=800):
    """Разбивает длинный текст на части по предложениям"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_length:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def preprocess_text(text):
    """Предварительная обработка текста перед озвучиванием"""
    if isinstance(text, (int, float)):
        return format_number(text)
    
    text = str(text)
    
    # Обработка Ollama ответов (удаление метки [Ollama])
    text = re.sub(r'\[Ollama\] Ответ:\s*', '', text)
    
    # Обработка чисел в тексте
    if any(c.isdigit() for c in text):
        parts = []
        for word in re.split(r'(\s|[,.!?])', text):
            if word.replace('.', '').isdigit():
                parts.append(format_number(float(word)))
            else:
                parts.append(word)
        text = ''.join(parts)
    
    return text.strip()

def speak_chunk(chunk):
    """Озвучивает одну часть текста"""
    audio = model.apply_tts(text=chunk + " ", speaker='xenia', sample_rate=48000)
    silence = np.zeros(int(0.15 * 48000), dtype=np.float32)
    sd.play(np.concatenate([audio, silence]), samplerate=48000)
    sd.wait()

def speak(text):
    """Улучшенное произношение с обработкой длинных текстов"""
    processed_text = preprocess_text(text)
    
    if not processed_text:
        return
    
    if len(processed_text) > 800:
        chunks = split_long_text(processed_text)
        for chunk in chunks:
            speak_chunk(chunk)
    else:
        speak_chunk(processed_text)

def async_speak(text):
    """Асинхронное озвучивание текста"""
    thread = Thread(target=speak, args=(text,))
    thread.start()
    return thread
