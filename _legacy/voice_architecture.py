import asyncio
import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    import yaml
except Exception:
    yaml = None

import requests

logger = logging.getLogger("lumi.voice")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@dataclass
class AssistantConfig:
    assistant: Dict[str, Any] = field(default_factory=lambda: {
        "name": "Lumi",
        "language": "ru-RU",
        "system_prompt": "Ты Lumi — дружелюбный голосовой ассистент.",
        "history_limit": 10,
        "log_dialog": True,
    })
    wake_word: Dict[str, Any] = field(default_factory=lambda: {
        "engine": "porcupine",
        "keyword": "Люми",
        "model_path": "models/lumia.ppn",
        "access_key": "",
    })
    vad: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "engine": "silero-vad",
        "silence_timeout_sec": 1.2,
    })
    stt: Dict[str, Any] = field(default_factory=lambda: {
        "engine": "whisper",
        "language": "ru",
        "model": "small",
    })
    tts: Dict[str, Any] = field(default_factory=lambda: {
        "engine": "pyttsx3",
        "voice": "",
        "rate": 180,
        "volume": 1.0,
    })
    llm: Dict[str, Any] = field(default_factory=lambda: {
        "provider": "ollama",
        "endpoint": "http://localhost:11434",
        "api_key": "",
        "model": "llama3:8b",
        "temperature": 0.6,
        "max_tokens": 512,
    })
    cache: Dict[str, Any] = field(default_factory=lambda: {"enabled": False, "path": ".lumi_cache.json"})


class ConfigLoader:
    def __init__(self, path: str):
        self.path = Path(path)
        self._mtime = 0.0
        self.current = AssistantConfig()

    def load(self) -> AssistantConfig:
        if not self.path.exists():
            self.save_default()
            return self.current
        if self.path.suffix in {".yml", ".yaml"}:
            if yaml is None:
                raise RuntimeError("PyYAML не установлен. Установите pyyaml для YAML-конфига.")
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        else:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        base = AssistantConfig()
        for k in vars(base).keys():
            if k in raw and isinstance(raw[k], dict):
                getattr(base, k).update(raw[k])
        self.current = base
        self._mtime = self.path.stat().st_mtime
        return self.current

    def maybe_reload(self) -> bool:
        if not self.path.exists():
            return False
        new_mtime = self.path.stat().st_mtime
        if new_mtime > self._mtime:
            self.load()
            logger.info("Конфиг перезагружен без рестарта")
            return True
        return False

    def save_default(self) -> None:
        data = {k: getattr(self.current, k) for k in vars(self.current).keys()}
        if self.path.suffix in {".yml", ".yaml"}:
            if yaml is None:
                raise RuntimeError("PyYAML не установлен")
            self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        else:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class STTEngine(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str) -> str: ...


class TTSEngine(ABC):
    @abstractmethod
    async def speak(self, text: str) -> None: ...


class WakeWordEngine(ABC):
    @abstractmethod
    async def wait_for_wake_word(self) -> None: ...


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, history: List[Dict[str, str]], cfg: AssistantConfig) -> str: ...


class PorcupineWakeWordEngine(WakeWordEngine):
    async def wait_for_wake_word(self) -> None:
        # Заглушка для интеграции с pvporcupine/openWakeWord/Snowboy
        await asyncio.sleep(0.1)


class ConsoleWakeWordEngine(WakeWordEngine):
    async def wait_for_wake_word(self) -> None:
        await asyncio.to_thread(input, "[wake-word] Нажмите Enter, чтобы имитировать wake word: ")


class WhisperSTT(STTEngine):
    async def transcribe(self, audio_bytes: bytes, language: str) -> str:
        # Точка расширения для faster-whisper/whisper.cpp
        return (await asyncio.to_thread(input, "[stt] Введите распознанный текст: ")).strip()


class Pyttsx3TTS(TTSEngine):
    def __init__(self, cfg: Dict[str, Any]):
        import pyttsx3

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", cfg.get("rate", 180))
        self.engine.setProperty("volume", cfg.get("volume", 1.0))
        voice = cfg.get("voice")
        if voice:
            self.engine.setProperty("voice", voice)

    async def speak(self, text: str) -> None:
        def run():
            self.engine.say(text)
            self.engine.runAndWait()

        await asyncio.to_thread(run)


class DummyTTS(TTSEngine):
    async def speak(self, text: str) -> None:
        print(f"[tts] {text}")


class OllamaProvider(LLMProvider):
    async def complete(self, history: List[Dict[str, str]], cfg: AssistantConfig) -> str:
        llm = cfg.llm
        endpoint = llm["endpoint"].rstrip("/") + "/api/chat"
        payload = {
            "model": llm["model"],
            "messages": history,
            "stream": False,
            "options": {
                "temperature": llm.get("temperature", 0.6),
                "num_predict": llm.get("max_tokens", 512),
            },
        }
        def req():
            r = requests.post(endpoint, json=payload, timeout=90)
            r.raise_for_status()
            return r.json()

        data = await asyncio.to_thread(req)
        msg = data.get("message", {})
        return msg.get("content", "").strip() or "..."


class OpenAICompatibleProvider(LLMProvider):
    async def complete(self, history: List[Dict[str, str]], cfg: AssistantConfig) -> str:
        llm = cfg.llm
        headers = {"Authorization": f"Bearer {llm['api_key']}"}
        payload = {
            "model": llm["model"],
            "messages": history,
            "temperature": llm.get("temperature", 0.6),
            "max_tokens": llm.get("max_tokens", 512),
        }
        endpoint = llm["endpoint"].rstrip("/") + "/v1/chat/completions"

        def req():
            r = requests.post(endpoint, headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            return r.json()

        data = await asyncio.to_thread(req)
        return data["choices"][0]["message"]["content"].strip()


class LumiVoiceLoop:
    def __init__(self, cfg_loader: ConfigLoader):
        self.cfg_loader = cfg_loader
        self.cfg = cfg_loader.load()
        self.history: List[Dict[str, str]] = []
        self.cache: Dict[str, str] = self._load_cache()
        self.wake = self._build_wake_engine()
        self.stt = self._build_stt_engine()
        self.tts = self._build_tts_engine()
        self.llm = self._build_llm_provider()

    def _build_wake_engine(self) -> WakeWordEngine:
        engine = self.cfg.wake_word.get("engine", "console").lower()
        return PorcupineWakeWordEngine() if engine == "porcupine" else ConsoleWakeWordEngine()

    def _build_stt_engine(self) -> STTEngine:
        return WhisperSTT()

    def _build_tts_engine(self) -> TTSEngine:
        engine = self.cfg.tts.get("engine", "pyttsx3").lower()
        if engine == "pyttsx3":
            try:
                return Pyttsx3TTS(self.cfg.tts)
            except Exception as e:
                logger.warning("pyttsx3 недоступен: %s; fallback в DummyTTS", e)
        return DummyTTS()

    def _build_llm_provider(self) -> LLMProvider:
        provider = self.cfg.llm.get("provider", "ollama").lower()
        if provider in {"openai", "anthropic", "yandexgpt", "gigachat", "openai_compatible"}:
            return OpenAICompatibleProvider()
        return OllamaProvider()

    def _load_cache(self) -> Dict[str, str]:
        path = self.cfg.cache.get("path", ".lumi_cache.json")
        if os.path.exists(path):
            try:
                return json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        if self.cfg.cache.get("enabled"):
            path = self.cfg.cache.get("path", ".lumi_cache.json")
            Path(path).write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")

    async def run_forever(self) -> None:
        logger.info("Lumi voice loop started")
        while True:
            self.cfg_loader.maybe_reload()
            self.cfg = self.cfg_loader.current
            await self.wake.wait_for_wake_word()
            logger.info("Wake word detected; listening...")
            user_text = await self.stt.transcribe(b"", self.cfg.stt.get("language", "ru"))
            if not user_text:
                continue
            answer = await self.handle_text(user_text)
            await self.tts.speak(answer)

    async def handle_text(self, user_text: str) -> str:
        cache_key = hashlib.sha256(user_text.strip().lower().encode()).hexdigest()
        if self.cfg.cache.get("enabled") and cache_key in self.cache:
            return self.cache[cache_key]

        system_prompt = self.cfg.assistant.get("system_prompt", "Ты Lumi.")
        history_limit = int(self.cfg.assistant.get("history_limit", 10))
        trimmed = self.history[-history_limit * 2 :]
        messages = [{"role": "system", "content": system_prompt}] + trimmed + [{"role": "user", "content": user_text}]
        answer = await self.llm.complete(messages, self.cfg)

        self.history.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": answer},
        ])

        if self.cfg.assistant.get("log_dialog", True):
            logger.info("USER: %s", user_text)
            logger.info("LUMI: %s", answer)

        if self.cfg.cache.get("enabled"):
            self.cache[cache_key] = answer
            self._save_cache()

        return answer


async def main(config_path: str = "lumi_config.yaml") -> None:
    loader = ConfigLoader(config_path)
    loop = LumiVoiceLoop(loader)
    await loop.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
