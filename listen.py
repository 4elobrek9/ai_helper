import sys
import time
import logging
import pygame
import speech_recognition as sr
from command_OCR import move_to_text, click_to_text
from command import *


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('voice_assistant.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class AudioManager:
    def __init__(self):
        pygame.mixer.init()
        self.recognizer = sr.Recognizer()
        self.mic = sr.Microphone()
        self.source = None
        self._init_microphone()
        self.load_sounds()
        self.command_start_time = 0

    def load_sounds(self):
        try:
            self.sounds = {
                'listening': pygame.mixer.Sound('nerd_lst.mp3'),
                'executing': pygame.mixer.Sound('conf.mp3'),
                'waiting': pygame.mixer.Sound('Простите_за_ожидание.wav'),
                'error': pygame.mixer.Sound('error_sound.wav')
            }
        except Exception as e:
            logger.error(f"Ошибка загрузки звуков: {str(e)}")
            self.sounds = None

    def play_sound(self, name):
        if self.sounds and name in self.sounds:
            self.sounds[name].play()

    def _init_microphone(self):
        try:
            self.source = self.mic.__enter__()
            self.recognizer.adjust_for_ambient_noise(self.source, duration=1)
            self.recognizer.pause_threshold = 0.6
            self.recognizer.non_speaking_duration = 0.3
            logger.info("Микрофон инициализирован")
        except Exception as e:
            logger.error(f"Ошибка микрофона: {str(e)}")
            raise

    def __del__(self):
        if self.mic and self.source:
            self.mic.__exit__(None, None, None)

    def extended_listen(self):
        try:
            return self.recognizer.listen(
                self.source,
                timeout=3,
                phrase_time_limit=6
            )
        except Exception as e:
            logger.debug(f"Аудио ошибка: {str(e)}")
            return None

class VoiceAssistant:
    def __init__(self):
        self.audio = AudioManager()
        self.running = True
        self.command_mode = False

    def start(self):
        logger.info("Запуск ассистента...")
        try:
            while self.running:
                self._process_audio()
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.error(f"Критическая ошибка: {str(e)}")
            self.stop()

    def stop(self):
        logger.info("Завершение работы...")
        self.running = False
        sys.exit(0)

    def _process_audio(self):
        audio = self.audio.extended_listen()
        if not audio:
            time.sleep(0.1)
            return

        try:
            text = self.audio.recognizer.recognize_google(audio, language="ru-RU").lower()
            logger.info(f"Распознано: {text}")

            if self.command_mode:
                self._handle_command(text)
                self.command_mode = False
            elif any(w in text for w in {"окей", "хей", "люми", "lumi", "lumia", "lu", "лю"}):
                self._activate_command_mode()

        except sr.UnknownValueError:
            pass
        except Exception as e:
            logger.error(f"Ошибка обработки: {str(e)}")

    def _activate_command_mode(self):
        logger.info("Режим команд активирован")
        self.command_mode = True
        self.audio.play_sound('listening')  # "Слушаю"
        time.sleep(0.3)

    def _handle_command(self, text):
        self.audio.command_start_time = time.time()
        command_actions = {
            "наведи на": self._handle_move,
            "нажми на": self._handle_click,
            "погода": self._weather
        }

        for phrase, action in command_actions.items():
            if phrase in text:
                self._check_delay()
                action(text)
                self.audio.play_sound('executing')  # "Выполняю"
                return

        logger.warning("Неизвестная команда")
        self.audio.play_sound('error')

    def _check_delay(self):
        if time.time() - self.audio.command_start_time > 5:
            self.audio.play_sound('waiting')  # "Простите за ожидание"

    def _handle_move(self, text):
        target = text.split("наведи на")[-1].strip()
        if not move_to_text(target, threshold=70):
            self.audio.play_sound('error')

    def _handle_click(self, text):
        target = text.split("нажми на")[-1].strip()
        if not click_to_text(target, clicks=2):
            self.audio.play_sound('error')
    def _weather(self, text=None):
        try:
            from command import get_weather
            weather = get_weather()
            
            if not weather:
                self.audio.play_sound('error')
                return
                
            temp_text = weather['temp'].replace('−', 'минус ')
            message = (
                f"Сейчас в {weather['city']} {temp_text}. "
                f"{weather['weather'].capitalize()}."
            )
            
            engine = pyttsx3.init()
            engine.say("Обновляю данные о погоде... " + message)
            engine.runAndWait()
            
        except Exception as e:
            logger.error(f"Ошибка погоды: {str(e)}")
            self.audio.play_sound('error')

if __name__ == "__main__":
    VoiceAssistant().start()