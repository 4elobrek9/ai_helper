"""Small offline text-to-speech adapter used by the voice assistant."""

import logging
import threading
from queue import Queue

logger = logging.getLogger("lumi.tts")
_speech_queue = Queue()
_engine = None
_engine_lock = threading.Lock()


def _speech_worker():
    global _engine
    while True:
        text = _speech_queue.get()
        if text is None:
            _speech_queue.task_done()
            return
        try:
            with _engine_lock:
                if _engine is None:
                    import pyttsx3
                    _engine = pyttsx3.init()
                _engine.say(text)
                _engine.runAndWait()
        except Exception:
            logger.exception("Не удалось озвучить ответ через локальный TTS")
            _engine = None
        finally:
            _speech_queue.task_done()


_speech_thread = threading.Thread(target=_speech_worker, daemon=True)
_speech_thread.start()


def speak(text):
    if text:
        _speech_queue.put(str(text))


def async_speak(text):
    speak(text)
    return _speech_thread


def stop_speaking():
    with _engine_lock:
        if _engine is not None:
            _engine.stop()


def is_speaking_now():
    return not _speech_queue.empty()
