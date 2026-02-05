import logging
import os
import threading
import time

import numpy as np
import pyaudio
import pygame
import pvporcupine
import requests
import speech_recognition as sr

import mistral_api
from command import get_weather
from command_OCR import click_to_text, move_to_text
from core.config.settings import get_porcupine_key_from_db, get_system_prompt_from_db
from core.memory.store import load_hardmemory, load_memory, save_to_memory, summarize_hardmemory
from core.voice.engine import speak

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
logger = logging.getLogger('VoiceAI')


def ask_ollama(question: str, full_memory: list) -> str:
    try:
        prompt = ""
        for msg in full_memory:
            if msg['role'] in ('system', 'user'):
                prompt += f"[INST] {msg['content']} [/INST]\n"
            elif msg['role'] == 'assistant':
                prompt += f"{msg['content']}\n"
        prompt += f"[INST] {question} [/INST]"
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3:8b", "prompt": prompt, "stream": False, "options": {"temperature": 0.7, "num_predict": 512}},
            timeout=60,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        logger.error(f"Ошибка запроса к Ollama: {e}")
        return "Не удалось получить ответ от локальной нейросети"


def process_text_query(text: str) -> str:
    save_to_memory(text, 'user')
    summarize_hardmemory()
    full_memory = load_hardmemory() + [{'role': 'system', 'content': get_system_prompt_from_db()}] + load_memory()
    try:
        response = mistral_api.chat_with_mistral(text, full_memory)
        response_text = response['choices'][0]['message']['content'].strip()
    except Exception:
        response_text = ask_ollama(text, full_memory)
    save_to_memory(response_text, 'assistant')
    summarize_hardmemory()
    return response_text


class VoiceAssistant:
    def __init__(self):
        pygame.mixer.init()
        self.sounds = {}
        for key, path in {'start': './audio/right.mp3', 'confirm': './audio/right.mp3', 'error': './audio/lie.mp3'}.items():
            if os.path.exists(path):
                self.sounds[key] = pygame.mixer.Sound(path)

        self.pyaudio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 400
        self.microphone = sr.Microphone()

        pv_access_key = get_porcupine_key_from_db()
        self.porcupine = None
        if pv_access_key:
            try:
                self.porcupine = pvporcupine.create(access_key=pv_access_key, keyword_paths=['models/lumia.ppn'])
            except Exception as e:
                logger.error(f"Ошибка инициализации Porcupine: {e}")

        self.audio_stream = None
        self.command_actions = {"наведи на": self._handle_move, "нажми на": self._handle_click, "кликни на": self._handle_click,
                                "клик по": self._handle_click, "погода": self._weather, "стоп": self.stop, "выход": self.stop}
        self.is_listening = False
        self.is_running = False
        self.command_timeout = 10
        self.last_activity = 0

    def start(self):
        if self.porcupine is None:
            speak("Ошибка ключа голосового движка")
            return
        self.is_running = True
        speak("Система готова к работе")
        self.audio_stream = self.pyaudio.open(rate=self.porcupine.sample_rate, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=self.porcupine.frame_length)
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)
        threading.Thread(target=self._detect_wakeword, daemon=True).start()
        threading.Thread(target=self._listen_commands, daemon=True).start()

    def _detect_wakeword(self):
        while self.is_running:
            try:
                pcm = self.audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
                if self.porcupine.process(np.frombuffer(pcm, dtype=np.int16)) >= 0:
                    self.is_listening = True
                    self.last_activity = time.time()
                    self._play_sound('start')
            except Exception:
                time.sleep(0.1)

    def _listen_commands(self):
        while self.is_running:
            if not self.is_listening:
                time.sleep(0.1)
                continue
            if time.time() - self.last_activity > self.command_timeout:
                self.is_listening = False
                continue
            with self.microphone as source:
                try:
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    text = self.recognizer.recognize_google(audio, language="ru-RU").lower()
                    self._process_command(text)
                    self.last_activity = time.time()
                except Exception:
                    continue

    def _process_command(self, text):
        for cmd, action in self.command_actions.items():
            if f" {cmd} " in f" {text} " or text.startswith(cmd + " ") or text.endswith(" " + cmd) or text == cmd:
                action(text)
                return
        if len(text.split()) < 2:
            speak("Повторите, пожалуйста")
            return
        speak("Секунду, формулирую мысль")
        save_to_memory(text, 'user')
        summarize_hardmemory()
        full_memory = load_hardmemory() + [{'role': 'system', 'content': get_system_prompt_from_db()}] + load_memory()
        try:
            response = mistral_api.chat_with_mistral(text, full_memory)
            response_text = response['choices'][0]['message']['content'].strip()
        except Exception:
            response_text = ask_ollama(text, full_memory)
        if response_text.strip():
            speak(response_text)
            save_to_memory(response_text, 'assistant')
            summarize_hardmemory()

    def _handle_move(self, text):
        for prefix in ["наведи на", "наведи курсор на", "перемести на"]:
            if prefix in text and not move_to_text(text.split(prefix)[-1].strip(), threshold=70):
                self._play_sound('error')

    def _handle_click(self, text):
        for prefix in ["нажми на", "кликни на", "клик по", "нажми", "кликни", "клик"]:
            if prefix in text and not click_to_text(text.split(prefix)[-1].strip(), clicks=2):
                self._play_sound('error')

    def _weather(self, text=None):
        try:
            weather = get_weather()
            speak(f"Сейчас {weather['temp']}, {weather.get('description', '')}")
        except Exception:
            speak("Не удалось получить погоду")
            self._play_sound('error')

    def _play_sound(self, name):
        if name in self.sounds:
            self.sounds[name].play()

    def stop(self, text=None):
        summarize_hardmemory()
        self.is_running = False
        if self.audio_stream is not None:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
