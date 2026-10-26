import torch
import sounddevice as sd
import numpy as np
from threading import Thread
import re
from queue import Queue
import time
import math

# Инициализация модели
device = torch.device('cpu')
model, _ = torch.hub.load(
    repo_or_dir='snakers4/silero-models',
    model='silero_tts',
    language='ru',
    speaker='v3_1_ru'
)
model.to(device)

# Очередь и флаг состояния
speech_queue = Queue()
is_speaking = False

# Словари для преобразования символов
SYMBOLS = {
    '+': 'плюс',
    '-': 'минус',
    '*': 'умножить на',
    '/': 'делить на',
    '=': 'равно',
    '<': 'меньше чем',
    '>': 'больше чем',
    '≤': 'меньше или равно',
    '≥': 'больше или равно',
    '≠': 'не равно',
    '≈': 'приблизительно равно',
    '±': 'плюс минус',
    '%': 'процент',
    '√': 'корень',
    '²': 'в квадрате',
    '³': 'в кубе',
    '^': 'в степени',
    '∠': 'угол',
    'π': 'пи',
    '∞': 'бесконечность',
    '∑': 'сумма',
    '∫': 'интеграл',
    '∂': 'частная производная',
    '∆': 'дельта',
    '∥': 'параллельно',
    '⊥': 'перпендикулярно',
    '°': 'градус',
    '|': 'модуль',
    ':': 'к',
    '÷': 'делить на',
    '×': 'умножить на',
    '~': 'тильда',
    '→': 'стрелка вправо',
    '←': 'стрелка влево',
    '↔': 'стрелка в обе стороны',
    '⇒': 'следовательно',
    '⇔': 'эквивалентно',
    '∀': 'для всех',
    '∃': 'существует',
    '∈': 'принадлежит',
    '∉': 'не принадлежит',
    '∅': 'пустое множество',
    '∪': 'объединение',
    '∩': 'пересечение',
    '⊂': 'подмножество',
    '⊃': 'надмножество',
    '⊆': 'подмножество или равно',
    '⊇': 'надмножество или равно',
    '⊕': 'прямая сумма',
    '⊗': 'тензорное произведение',
    '¬': 'не',
    '∧': 'и',
    '∨': 'или',
    '∴': 'поэтому',
    '∵': 'так как',
}

def format_number(num):
    """Форматирует число или математическое выражение в слова"""
    if isinstance(num, str):
        # Обработка математических выражений
        if any(sym in num for sym in SYMBOLS):
            return format_math_expression(num)
        # Обработка дробей вида a/b
        if '/' in num and len(num.split('/')) == 2:
            return format_fraction(num)
    
    num = str(num).replace(',', '.')
    
    # Преобразование чисел в слова
    units = ['ноль', 'один', 'два', 'три', 'четыре', 
             'пять', 'шесть', 'семь', 'восемь', 'девять']
    teens = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
             'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
    tens = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 
            'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
    hundreds = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
                'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']
    
    if '.' in num:
        integer_part, fractional_part = num.split('.')
        result = f"{format_number(integer_part)} точка"
        for digit in fractional_part:
            result += f" {units[int(digit)]}"
        return result
    
    num = int(num)
    if num < 10:
        return units[num]
    elif 10 <= num < 20:
        return teens[num - 10]
    elif 20 <= num < 100:
        return f"{tens[num // 10]} {units[num % 10] if num % 10 != 0 else ''}".strip()
    elif 100 <= num < 1000:
        return f"{hundreds[num // 100]} {format_number(num % 100)}".strip()
    else:
        # Для больших чисел разбиваем на цифры
        return ' '.join([units[int(d)] for d in str(num)])

def format_fraction(fraction):
    """Форматирует дробь вида a/b"""
    numerator, denominator = fraction.split('/')
    return f"{format_number(numerator)} {format_number(denominator)}-х"

def format_math_expression(expr):
    """Форматирует математическое выражение с символами"""
    # Разбиваем выражение на токены (числа, символы, слова)
    tokens = re.findall(r'(\d+\.?\d*|\S)', expr)
    
    result = []
    for token in tokens:
        if token in SYMBOLS:
            result.append(SYMBOLS[token])
        elif '/' in token and len(token.split('/')) == 2:
            result.append(format_fraction(token))
        elif token.replace('.', '').isdigit():
            result.append(format_number(token))
        else:
            result.append(token)
    
    return ' '.join(result)

def split_long_text(text, max_length=800):
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
    if isinstance(text, (int, float)):
        return format_number(text)
    
    text = str(text)
    
    # Удаление служебных префиксов
    text = re.sub(r'\[Ollama\] Ответ:\s*', '', text)
    
    # Обработка математических выражений в скобках
    text = re.sub(r'\[math\](.*?)\[/math\]', 
                 lambda m: format_math_expression(m.group(1)), text)
    
    # Обработка обычных математических выражений
    def replace_math(match):
        expr = match.group()
        return format_math_expression(expr)
    
    # Регулярное выражение для поиска математических выражений
    math_pattern = r'(?:[+\-*/=<>≤≥≠≈±%√²³^∠π∞∑∫∂∆∥⊥°|:÷×~→←↔⇒⇔∀∃∈∉∅∪∩⊂⊃⊆⊇⊕⊗¬∧∨∴∵]|\d+\.?\d*\/\d+\.?\d*|\d+\.?\d*)'
    text = re.sub(fr'(\b(?:{math_pattern}\s*)+)', replace_math, text)
    
    return text.strip()

def speech_worker():
    global is_speaking
    while True:
        text = speech_queue.get()
        if text is None:
            break
            
        is_speaking = True
        processed_text = preprocess_text(text)
        
        if not processed_text:
            continue
            
        if len(processed_text) > 800:
            chunks = split_long_text(processed_text)
            for chunk in chunks:
                generate_and_play(chunk)
        else:
            generate_and_play(processed_text)
            
        is_speaking = False
        speech_queue.task_done()

def generate_and_play(chunk):
    audio = model.apply_tts(
        text=chunk + " ",
        speaker='xenia',
        sample_rate=48000
    )
    
    silence = np.zeros(int(0.15 * 48000), dtype=np.float32)
    sd.play(np.concatenate([audio, silence]), samplerate=48000)
    sd.wait()

# Запуск фонового потока
speech_thread = Thread(target=speech_worker, daemon=True)
speech_thread.start()

def speak(text):
    """Добавляет текст в очередь для воспроизведения"""
    speech_queue.put(text)

def async_speak(text):
    """Асинхронное воспроизведение"""
    speak(text)
    return speech_thread

def stop_speaking():
    """Остановить текущее воспроизведение"""
    sd.stop()

def is_speaking_now():
    """Проверка, идет ли сейчас воспроизведение"""
    return is_speaking or not speech_queue.empty()