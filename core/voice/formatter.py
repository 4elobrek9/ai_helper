import re

SYMBOLS = {
    '+': 'плюс', '-': 'минус', '*': 'умножить на', '/': 'делить на', '=': 'равно',
    '<': 'меньше чем', '>': 'больше чем', '≤': 'меньше или равно', '≥': 'больше или равно',
    '≠': 'не равно', '≈': 'приблизительно равно', '±': 'плюс минус', '%': 'процент',
    '√': 'корень', '²': 'в квадрате', '³': 'в кубе', '^': 'в степени', '∠': 'угол',
    'π': 'пи', '∞': 'бесконечность', '∑': 'сумма', '∫': 'интеграл', '∂': 'частная производная',
    '∆': 'дельта', '∥': 'параллельно', '⊥': 'перпендикулярно', '°': 'градус', '|': 'модуль',
    ':': 'к', '÷': 'делить на', '×': 'умножить на', '~': 'тильда', '→': 'стрелка вправо',
    '←': 'стрелка влево', '↔': 'стрелка в обе стороны', '⇒': 'следовательно', '⇔': 'эквивалентно',
    '∀': 'для всех', '∃': 'существует', '∈': 'принадлежит', '∉': 'не принадлежит',
    '∅': 'пустое множество', '∪': 'объединение', '∩': 'пересечение', '⊂': 'подмножество',
    '⊃': 'надмножество', '⊆': 'подмножество или равно', '⊇': 'надмножество или равно',
    '⊕': 'прямая сумма', '⊗': 'тензорное произведение', '¬': 'не', '∧': 'и', '∨': 'или',
    '∴': 'поэтому', '∵': 'так как',
}


def format_number(num):
    if isinstance(num, str):
        if any(sym in num for sym in SYMBOLS):
            return format_math_expression(num)
        if '/' in num and len(num.split('/')) == 2:
            return format_fraction(num)
    num = str(num).replace(',', '.')
    units = ['ноль', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
    teens = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
    tens = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
    hundreds = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']
    if '.' in num:
        integer_part, fractional_part = num.split('.')
        return f"{format_number(integer_part)} точка" + ''.join(f" {units[int(d)]}" for d in fractional_part)
    value = int(num)
    if value < 10:
        return units[value]
    if value < 20:
        return teens[value - 10]
    if value < 100:
        return f"{tens[value // 10]} {units[value % 10] if value % 10 != 0 else ''}".strip()
    if value < 1000:
        return f"{hundreds[value // 100]} {format_number(value % 100)}".strip()
    return ' '.join([units[int(d)] for d in str(value)])


def format_fraction(fraction):
    numerator, denominator = fraction.split('/')
    return f"{format_number(numerator)} {format_number(denominator)}-х"


def format_math_expression(expr):
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
    chunks, current_chunk = [], ""
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
    text = re.sub(r'\[Ollama\] Ответ:\s*', '', str(text))
    text = re.sub(r'\[math\](.*?)\[/math\]', lambda m: format_math_expression(m.group(1)), text)

    def replace_math(match):
        return format_math_expression(match.group())

    math_pattern = r'(?:[+\-*/=<>≤≥≠≈±%√²³^∠π∞∑∫∂∆∥⊥°|:÷×~→←↔⇒⇔∀∃∈∉∅∪∩⊂⊃⊆⊇⊕⊗¬∧∨∴∵]|\d+\.?\d*\/\d+\.?\d*|\d+\.?\d*)'
    text = re.sub(fr'(\b(?:{math_pattern}\s*)+)', replace_math, text)
    return text.strip()
