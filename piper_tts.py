import hashlib
import logging
import re
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
import wave
from io import BytesIO

import numpy as np
import requests
import sounddevice as sd

from app_paths import data_path


logger = logging.getLogger("lumi.piper")
VOICE_REPOSITORY = "rhasspy/piper-voices"
VOICE_API = f"https://huggingface.co/api/models/{VOICE_REPOSITORY}/tree/main"
VOICE_BASE_URL = f"https://huggingface.co/{VOICE_REPOSITORY}/resolve/main"
VOICE_CATALOG = {
    "ru_RU-denis-medium": {
        "label": "Piper — Денис (medium)",
        "path": "ru/ru_RU/denis/medium",
    },
    "ru_RU-dmitri-medium": {
        "label": "Piper — Дмитрий (medium)",
        "path": "ru/ru_RU/dmitri/medium",
    },
    "ru_RU-irina-medium": {
        "label": "Piper — Ирина (medium)",
        "path": "ru/ru_RU/irina/medium",
    },
    "ru_RU-ruslan-medium": {
        "label": "Piper — Руслан (medium)",
        "path": "ru/ru_RU/ruslan/medium",
    },
}
_VOICE_NAME = re.compile(r"^ru_RU-(?:denis|dmitri|irina|ruslan)-medium$")
_MAX_VOICE_FILE_SIZE = 100 * 1024 * 1024
_voice_cache = {}


def voice_directory(voice_name):
    if not _VOICE_NAME.fullmatch(voice_name):
        raise ValueError("Выберите голос Piper из списка.")
    return data_path(Path("piper") / voice_name).parent


def voice_path(voice_name):
    return voice_directory(voice_name) / f"{voice_name}.onnx"


def is_voice_installed(voice_name):
    model = voice_path(voice_name)
    config = model.with_suffix(".onnx.json")
    return model.is_file() and config.is_file()


def installed_voices():
    return [
        voice_name
        for voice_name in VOICE_CATALOG
        if is_voice_installed(voice_name)
    ]


def _download_file(path, metadata, target, progress_callback, progress_start, total):
    expected_size = metadata.get("size")
    lfs = metadata.get("lfs") or {}
    lfs_digest = lfs.get("oid")
    expected_digest = lfs_digest or metadata.get("oid")
    digest_algorithm = "sha256" if lfs_digest else "sha1"
    if (
        not isinstance(expected_size, int)
        or expected_size <= 0
        or expected_size > _MAX_VOICE_FILE_SIZE
        or not isinstance(expected_digest, str)
        or not re.fullmatch(
            r"[0-9a-f]{64}" if digest_algorithm == "sha256" else r"[0-9a-f]{40}",
            expected_digest,
        )
    ):
        raise RuntimeError(f"Нет безопасных метаданных для голоса Piper: {path}")

    temporary = target.with_suffix(target.suffix + ".part")
    hasher = hashlib.new(digest_algorithm)
    if digest_algorithm == "sha1":
        hasher.update(f"blob {expected_size}\0".encode("ascii"))
    downloaded = 0
    url = f"{VOICE_BASE_URL}/{quote(path, safe='/')}"
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(5, 30),
        ) as response:
            response.raise_for_status()
            if not response.url.startswith("https://"):
                raise RuntimeError("Загрузка Piper перенаправлена на небезопасный URL.")
            with temporary.open("wb") as output:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > expected_size or downloaded > _MAX_VOICE_FILE_SIZE:
                        raise RuntimeError("Размер файла голоса Piper превышает предел.")
                    hasher.update(chunk)
                    output.write(chunk)
                    if progress_callback:
                        progress_callback(
                            min(progress_start + downloaded, total),
                            total,
                        )
        if downloaded != expected_size or hasher.hexdigest() != expected_digest:
            raise RuntimeError(f"Проверка целостности файла Piper не пройдена: {path}")
        temporary.replace(target)
        return expected_size
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def install_voice(voice_name, progress_callback=None):
    if not _VOICE_NAME.fullmatch(voice_name):
        raise ValueError("Выберите голос Piper из списка.")
    model_file = f"{voice_name}.onnx"
    config_file = f"{model_file}.json"
    response = requests.get(
        VOICE_API + "/" + VOICE_CATALOG[voice_name]["path"],
        timeout=(5, 15),
    )
    response.raise_for_status()
    files = response.json()
    if not isinstance(files, list):
        raise RuntimeError("Hugging Face вернул некорректный список файлов голоса.")
    metadata = {
        item.get("path", "").rsplit("/", 1)[-1]: item
        for item in files
        if isinstance(item, dict)
    }
    if model_file not in metadata or config_file not in metadata:
        raise RuntimeError("На Hugging Face не найдена полная модель голоса Piper.")
    total = sum(metadata[name].get("size", 0) for name in (model_file, config_file))
    if not 0 < total <= 2 * _MAX_VOICE_FILE_SIZE:
        raise RuntimeError("Размер модели голоса Piper превышает допустимый предел.")

    destination = voice_directory(voice_name)
    destination.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    model_target = destination / model_file
    config_target = destination / config_file
    try:
        downloaded += _download_file(
            f"{VOICE_CATALOG[voice_name]['path']}/{model_file}",
            metadata[model_file],
            model_target,
            progress_callback,
            downloaded,
            total,
        )
        downloaded += _download_file(
            f"{VOICE_CATALOG[voice_name]['path']}/{config_file}",
            metadata[config_file],
            config_target,
            progress_callback,
            downloaded,
            total,
        )
    except Exception:
        model_target.unlink(missing_ok=True)
        config_target.unlink(missing_ok=True)
        raise
    _voice_cache.pop(voice_name, None)
    return model_target


def speak(text, voice_name, should_cancel=None):
    if not is_voice_installed(voice_name):
        raise RuntimeError(
            f"Голос {voice_name} не установлен. Скачайте его в настройках."
        )
    try:
        from piper import PiperVoice
    except ImportError as error:
        raise RuntimeError(
            "Для Piper не установлен пакет piper-tts. "
            "Перезапустите launch.bat для установки зависимостей."
        ) from error

    voice = _voice_cache.get(voice_name)
    if voice is None:
        voice = PiperVoice.load(str(voice_path(voice_name)))
        _voice_cache[voice_name] = voice
    audio_buffer = BytesIO()
    with closing(wave.open(audio_buffer, "wb")) as wav_file:
        voice.synthesize_wav(text, wav_file)
    audio_buffer.seek(0)
    with wave.open(audio_buffer, "rb") as wav_file:
        samples = np.frombuffer(
            wav_file.readframes(wav_file.getnframes()),
            dtype=np.int16,
        )
        if wav_file.getnchannels() > 1:
            samples = samples.reshape(-1, wav_file.getnchannels())
        sample_rate = wav_file.getframerate()
    if should_cancel is not None and should_cancel():
        return
    sd.play(samples, samplerate=sample_rate)
    sd.wait()
