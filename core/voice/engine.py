from queue import Queue
from threading import Thread

import numpy as np
import sounddevice as sd
import torch

from core.voice.formatter import preprocess_text, split_long_text


device = torch.device('cpu')
model, _ = torch.hub.load(
    repo_or_dir='snakers4/silero-models',
    model='silero_tts',
    language='ru',
    speaker='v3_1_ru'
)
model.to(device)

speech_queue = Queue()
is_speaking = False


def generate_and_play(chunk: str):
    audio = model.apply_tts(text=chunk + " ", speaker='xenia', sample_rate=48000)
    silence = np.zeros(int(0.15 * 48000), dtype=np.float32)
    sd.play(np.concatenate([audio, silence]), samplerate=48000)
    sd.wait()


def speech_worker():
    global is_speaking
    while True:
        text = speech_queue.get()
        if text is None:
            break
        is_speaking = True
        processed_text = preprocess_text(text)
        if processed_text:
            if len(processed_text) > 800:
                for chunk in split_long_text(processed_text):
                    generate_and_play(chunk)
            else:
                generate_and_play(processed_text)
        is_speaking = False
        speech_queue.task_done()


speech_thread = Thread(target=speech_worker, daemon=True)
speech_thread.start()


def speak(text):
    speech_queue.put(text)


def async_speak(text):
    speak(text)
    return speech_thread


def stop_speaking():
    sd.stop()


def is_speaking_now():
    return is_speaking or not speech_queue.empty()
