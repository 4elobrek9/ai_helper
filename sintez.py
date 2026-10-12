import logging
import re
from queue import Queue
from threading import Thread

import numpy as np
import sounddevice as sd


logger = logging.getLogger("lumi.tts")
speech_queue = Queue()
is_speaking = False
silero_model = None
system_voice_engine = None
voice_choice = "Silero (Ксения)"


def set_voice(choice):
    global voice_choice
    voice_choice = choice or "Silero (Ксения)"


SYMBOLS = {
    "+": "плюс",
    "-": "минус",
    "*": "умножить на",
    "/": "делить на",
    "=": "равно",
    "<": "меньше чем",
    ">": "больше чем",
    "≤": "меньше или равно",
    "≥": "больше или равно",
    "≠": "не равно",
    "≈": "приблизительно равно",
    "±": "плюс минус",
    "%": "процент",
    "√": "корень",
    "²": "в квадрате",
    "³": "в кубе",
    "^": "в степени",
    "∠": "угол",
    "π": "пи",
    "∞": "бесконечность",
    "∑": "сумма",
    "∫": "интеграл",
    "∂": "частная производная",
    "∆": "дельта",
    "∥": "параллельно",
    "⊥": "перпендикулярно",
    "°": "градус",
    "|": "модуль",
    ":": "к",
    "÷": "делить на",
    "×": "умножить на",
    "~": "тильда",
    "→": "стрелка вправо",
    "←": "стрелка влево",
    "↔": "стрелка в обе стороны",
    "⇒": "следовательно",
    "⇔": "эквивалентно",
    "∀": "для всех",
    "∃": "существует",
    "∈": "принадлежит",
    "∉": "не принадлежит",
    "∅": "пустое множество",
    "∪": "объединение",
    "∩": "пересечение",
    "⊂": "подмножество",
    "⊃": "надмножество",
    "⊆": "подмножество или равно",
    "⊇": "надмножество или равно",
    "⊕": "прямая сумма",
    "⊗": "тензорное произведение",
    "¬": "не",
    "∧": "и",
    "∨": "или",
    "∴": "поэтому",
    "∵": "так как",
}


def format_number(number):
    if isinstance(number, str):
        if any(symbol in number for symbol in SYMBOLS):
            return format_math_expression(number)
        if "/" in number and len(number.split("/")) == 2:
            return format_fraction(number)

    number = str(number).replace(",", ".")
    units = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    teens = [
        "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
        "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
    ]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = [
        "", "сто", "двести", "триста", "четыреста", "пятьсот",
        "шестьсот", "семьсот", "восемьсот", "девятьсот",
    ]

    if "." in number:
        integer_part, fractional_part = number.split(".")
        result = f"{format_number(integer_part)} точка"
        return result + " " + " ".join(units[int(digit)] for digit in fractional_part)

    value = int(number)
    if value < 10:
        return units[value]
    if value < 20:
        return teens[value - 10]
    if value < 100:
        remainder = f" {units[value % 10]}" if value % 10 else ""
        return f"{tens[value // 10]}{remainder}".strip()
    if value < 1000:
        return f"{hundreds[value // 100]} {format_number(value % 100)}".strip()
    return " ".join(units[int(digit)] for digit in str(value))


def format_fraction(fraction):
    numerator, denominator = fraction.split("/")
    return f"{format_number(numerator)} {format_number(denominator)}-х"


def format_math_expression(expression):
    tokens = re.findall(r"(\d+\.?\d*|\S)", expression)
    result = []
    for token in tokens:
        if token in SYMBOLS:
            result.append(SYMBOLS[token])
        elif "/" in token and len(token.split("/")) == 2:
            result.append(format_fraction(token))
        elif token.replace(".", "").isdigit():
            result.append(format_number(token))
        else:
            result.append(token)
    return " ".join(result)


def split_long_text(text, max_length=800):
    chunks = []
    current_chunk = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(current_chunk) + len(sentence) < max_length:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks


def preprocess_text(text):
    if isinstance(text, (int, float)):
        return format_number(text)

    text = re.sub(r"\[Ollama\] Ответ:\s*", "", str(text))
    text = re.sub(
        r"\[math\](.*?)\[/math\]",
        lambda match: format_math_expression(match.group(1)),
        text,
    )
    math_pattern = (
        r"(?:[+\-*/=<>≤≥≠≈±%√²³^∠π∞∑∫∂∆∥⊥°|:÷×~→←↔⇒⇔∀∃∈∉∅∪∩"
        r"⊂⊃⊆⊇⊕⊗¬∧∨∴∵]|\d+\.?\d*/\d+\.?\d*|\d+\.?\d*)"
    )
    return re.sub(
        fr"(\b(?:{math_pattern}\s*)+)",
        lambda match: format_math_expression(match.group()),
        text,
    ).strip()


def _init_silero():
    import torch

    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language="ru",
        speaker="v3_1_ru",
        trust_repo=True,
    )
    model.to(torch.device("cpu"))
    return model


def _init_system_voice():
    import pyttsx3

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    female_voice = next(
        (
            voice
            for voice in voices
            if any(
                marker in f"{voice.id} {voice.name}".casefold()
                for marker in ("female", "zira", "irina", "elena", "milena", "katya", "xenia")
            )
            and (
                not voice.languages
                or any(
                    "ru" in str(language).casefold()
                    for language in voice.languages
                )
            )
        ),
        None,
    )
    if female_voice:
        engine.setProperty("voice", female_voice.id)
        logger.info("Выбран системный голос: %s", female_voice.name)
    else:
        logger.warning("Системный русский женский голос не найден")
    return engine


def _speak_silero(text):
    global silero_model
    if silero_model is None:
        silero_model = _init_silero()
    audio = silero_model.apply_tts(
        text=text + " ",
        speaker="xenia",
        sample_rate=48000,
    )
    samples = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    silence = np.zeros(int(0.15 * 48000), dtype=np.float32)
    sd.play(np.concatenate([samples, silence]), samplerate=48000)
    sd.wait()


def _speak_system(text):
    global system_voice_engine
    if system_voice_engine is None:
        system_voice_engine = _init_system_voice()
    system_voice_engine.say(text)
    system_voice_engine.runAndWait()


def _speech_worker():
    global is_speaking
    while True:
        text = speech_queue.get()
        try:
            if text is None:
                continue

            is_speaking = True
            processed_text = preprocess_text(text)
            if not processed_text:
                continue
            chunks = split_long_text(processed_text) if len(processed_text) > 800 else [processed_text]
            if voice_choice == "Системный женский голос":
                for chunk in chunks:
                    _speak_system(chunk)
            else:
                for chunk in chunks:
                    _speak_silero(chunk)
        except Exception:
            logger.exception("Не удалось озвучить текст выбранным голосом")
        finally:
            is_speaking = False
            speech_queue.task_done()


speech_thread = Thread(target=_speech_worker, daemon=True, name="lumi-tts")
speech_thread.start()


def speak(text):
    """Queue Russian text for local speech synthesis."""
    if text and str(text).strip():
        speech_queue.put(str(text))


def async_speak(text):
    speak(text)
    return speech_thread


def stop_speaking():
    if system_voice_engine is not None:
        system_voice_engine.stop()
    sd.stop()
    while not speech_queue.empty():
        try:
            speech_queue.get_nowait()
            speech_queue.task_done()
        except Exception:
            break


def is_speaking_now():
    return is_speaking or not speech_queue.empty()
