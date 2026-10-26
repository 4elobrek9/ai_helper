"""Основное приложение LUMI AI — инициализация и управление компонентами."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Optional

from lumi.core.config import config
from lumi.core.logging import setup_logging, get_logger
from lumi.core.paths import ensure_dirs
from lumi.core.state import app_state
from lumi.llm.manager import LLMManager
from lumi.memory.chat_memory import ChatMemory
from lumi.memory.long_term import LongTermMemory
from lumi.desktop.tools import DesktopTools
from lumi.voice.stt import STTEngine
from lumi.voice.tts import TTSEngine
from lumi.voice.wake_word import WakeWordEngine, ConsoleWakeWordEngine, PorcupineWakeWordEngine

# Автообновление и обнаружение ИИ
from lumi.core.config_updater import GitHubUpdater, LocalAIDiscoverer, get_default_llm

logger = get_logger("app")


class LumiApp:
    """Главный класс приложения LUMI AI."""

    def __init__(self) -> None:
        self._initialized = False
        self._shutdown_event = threading.Event()

        self.llm: Optional[LLMManager] = None
        self.memory: Optional[ChatMemory] = None
        self.long_term: Optional[LongTermMemory] = None
        self.desktop: Optional[DesktopTools] = None
        self.stt: Optional[STTEngine] = None
        self.tts: Optional[TTSEngine] = None
        self.wake_word: Optional[WakeWordEngine] = None

        self._voice_thread: Optional[threading.Thread] = None
        self._voice_running = False

    def init(self) -> None:
        """Инициализирует все компоненты приложения."""
        if self._initialized:
            return

        ensure_dirs()
        setup_logging()
        
        # Автообновление проекта (выполняется один раз при первом запуске)
        updater = GitHubUpdater()
        if updater.is_git_repo():
            try:
                if not updater.fetch_latest():
                    logger.info("ℹ️  Проект уже обновлен или новые ветки отсутствуют.")
            except Exception as e:
                logger.warning(f"Ошибка обновления: {e}")
        
        # Автообнаружение локальных ИИ моделей
        discoverer = LocalAIDiscoverer()
        discovered_models = discoverer.discover_all()
        
        if discovered_models:
            best_llm = discoverer.get_best_llm()
            logger.info(f"✅ Найден локальный ИИ: {best_llm}")
            
            # Если Ollama найден, используем его
            if best_llm and "Ollama" in best_llm["name"]:
                try:
                    llm_model = config.get("llm", "model", "llama3:8b")
                    logger.info(f"Используется модель: {llm_model}")
                except Exception as e:
                    logger.warning(f"Ошибка чтения конфигурации LLM: {e}")
        else:
            logger.warning("ℹ️  Локальные ИИ не обнаружены. Используйте Ollama.")

        logger.info("=" * 60)
        logger.info("LUMI AI — инициализация приложения")
        logger.info("=" * 60)

        # Desktop tools (сначала, т.к. нужен для LLM tool-calling)
        safe_mode = config.get("desktop", "safe_mode", False)
        confirm = config.get("desktop", "confirm_dangerous", True)
        allowed_apps = config.get("desktop", "allowed_apps", [])
        allowed_folders = config.get("desktop", "allowed_folders", [])
        self.desktop = DesktopTools(
            allowed_apps=allowed_apps,
            allowed_folders=allowed_folders,
            confirm_dangerous=confirm,
            safe_mode=safe_mode,
        )
        logger.info(f"Desktop tools инициализированы (safe_mode={safe_mode})")

        # LLM менеджер (с desktop tools для tool-calling)
        self.llm = LLMManager(config.config, desktop_tools=self.desktop)
        logger.info("LLM менеджер инициализирован")

        # Память
        self.memory = ChatMemory(max_history=config.get("memory", "max_history", 50))
        self.long_term = LongTermMemory()
        logger.info("Память инициализирована")

        # STT
        self.stt = STTEngine(
            model_name=config.get("stt", "model", "small"),
            language=config.get("stt", "language", "ru"),
            device=config.get("stt", "device", "cpu"),
            compute_type=config.get("stt", "compute_type", "int8"),
        )
        logger.info("STT инициализирован")

        # TTS
        self.tts = TTSEngine(
            speaker=config.get("tts", "voice", "xenia"),
            sample_rate=config.get("tts", "sample_rate", 48000),
            device=config.get("stt", "device", "cpu"),
            rate=config.get("tts", "rate", 1.0),
            volume=config.get("tts", "volume", 1.0),
        )
        logger.info("TTS инициализирован")

        # Wake word
        ww_engine = config.get("wake_word", "engine", "console")
        if ww_engine == "porcupine":
            self.wake_word = PorcupineWakeWordEngine(
                keyword=config.get("wake_word", "keyword", "Люми"),
                access_key=config.get("wake_word", "access_key", ""),
                model_path=config.get("wake_word", "model_path", "models/lumia.ppn"),
            )
        else:
            self.wake_word = ConsoleWakeWordEngine(
                keyword=config.get("wake_word", "keyword", "Люми"),
            )
        logger.info(f"Wake word движок: {ww_engine}")

        # Состояние приложения
        app_state.is_running = True
        app_state.llm_manager = self.llm
        app_state.memory_manager = self.memory
        app_state.desktop_tools = self.desktop
        app_state.tts = self.tts
        app_state.stt = self.stt
        app_state.wake_word = self.wake_word

        self._initialized = True
        logger.info("LUMI AI полностью инициализирован")

    def start_voice_loop(self) -> None:
        """Запускает голосовой цикл в отдельном потоке."""
        if self._voice_running:
            return
        self._voice_running = True
        self._voice_thread = threading.Thread(target=self._voice_loop, daemon=True)
        self._voice_thread.start()
        logger.info("Голосовой цикл запущен")

    def stop_voice_loop(self) -> None:
        """Останавливает голосовой цикл."""
        self._voice_running = False
        if self._voice_thread and self._voice_thread.is_alive():
            self._voice_thread.join(timeout=5)
        logger.info("Голосовой цикл остановлен")

    def _voice_loop(self) -> None:
        """Основной цикл голосового ассистента."""
        logger.info("Голосовой цикл начат")
        while self._voice_running and not self._shutdown_event.is_set():
            try:
                self._shutdown_event.wait(0.5)
            except Exception as e:
                logger.error(f"Ошибка в голосовом цикле: {e}")
                break

    def speak(self, text: str) -> None:
        """Озвучивает текст через TTS."""
        app_state.set_voice_state(False, False, True)
        if self.tts:
            self.tts.speak(text)
        app_state.set_voice_state(False, False, False)

    def process_text(self, user_text: str) -> str:
        """Обрабатывает текстовый запрос через LLM с памятью и tool-calling."""
        app_state.set_voice_state(False, True, False)

        try:
            system_prompt = config.get("assistant", "system_prompt", "Ты Lumi.")
            history_limit = config.get("assistant", "history_limit", 12)

            tool_instructions = self.llm.get_tool_descriptions_text()
            full_system_prompt = f"{system_prompt}\n\n{tool_instructions}\n\nЕсли нужно использовать инструмент, укажи его в формате: ИНСТРУМЕНТ: аргументы"

            messages = [{"role": "system", "content": full_system_prompt}]

            if self.long_term:
                facts = self.long_term.get_facts_for_prompt()
                if facts:
                    messages.append({"role": "system", "content": facts})

            if self.memory:
                history = self.memory.get_recent(limit=history_limit)
                messages.extend(history)

            messages.append({"role": "user", "content": user_text})

            import asyncio
            answer = asyncio.run(self.llm.complete(messages))

            clean_text, tool_results = self.llm.parse_and_execute_tools(answer)

            if tool_results:
                messages.append({"role": "assistant", "content": answer})
                tool_results_text = "\n".join([
                    f"[Результат {r.name}]: {r.result if r.success else 'Ошибка: ' + r.error}"
                    for r in tool_results
                ])
                messages.append({"role": "system", "content": f"Результаты выполнения инструментов:\n{tool_results_text}\n\nОтветь пользователю на основе этих результатов."})
                answer = asyncio.run(self.llm.complete(messages))
                clean_text = answer

            if self.memory:
                self.memory.add("user", user_text)
                self.memory.add("assistant", clean_text)

            return clean_text
        except Exception as e:
            logger.error(f"Ошибка обработки текста: {e}")
            return f"Ошибка: {e}"
        finally:
            app_state.set_voice_state(False, False, False)

    def shutdown(self) -> None:
        """Корректное завершение работы приложения."""
        logger.info("Начало graceful shutdown...")
        self._shutdown_event.set()

        self.stop_voice_loop()

        if self.tts:
            self.tts.shutdown()
            logger.info("TTS остановлен")

        if self.wake_word and hasattr(self.wake_word, 'release'):
            self.wake_word.release()

        app_state.is_running = False
        logger.info("LUMI AI остановлен")

    def get_state_for_gui(self) -> dict:
        """Возвращает текущее состояние для обновления GUI."""
        import asyncio
        
        async def get_state():
            state = {
                "listening": app_state.is_listening,
                "thinking": False,
                "speaking": False,
            }

            # Проверка TTS через очередь
            if self.tts:
                try:
                    task = asyncio.create_task(self.tts.get_queue_length())
                    q_len = await asyncio.wait_for(task, timeout=0.1)
                    state["speaking"] = bool(q_len > 0)
                except Exception:
                    pass

            # Проверка LLM через HTTP (non-blocking)
            if self.llm and hasattr(self.llm, 'client'):
                try:
                    import httpx
                    task = asyncio.create_task(
                        httpx.get("http://localhost:11434/api/progress?status=processing", timeout=0.1)
                    )
                    await asyncio.wait_for(task, timeout=0.1)
                    state["thinking"] = True
                except Exception:
                    pass

            return state

        import threading
        state = None
        def run_in_thread():
            nonlocal state
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                state = loop.run_until_complete(get_state())
                loop.close()
            except Exception as e:
                logger.debug(f"Ошибка получения состояния GUI: {e}")

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

        return state or {}


# Глобальный экземпляр приложения
app: Optional[LumiApp] = None


def get_app() -> LumiApp:
    """Возвращает глобальный экземпляр приложения."""
    global app
    if app is None:
        app = LumiApp()
    return app


def setup_signal_handlers() -> None:
    """Настраивает обработчики сигналов для graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, завершение...")
        a = get_app()
        if a:
            a.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)