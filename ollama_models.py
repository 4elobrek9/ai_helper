import logging
import ctypes
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


logger = logging.getLogger("lumi.ollama")
DEFAULT_CHAT_MODEL = "qwen2.5:3b"
DEFAULT_VISION_MODEL = "qwen2.5vl:3b"
AUTO_MODEL = "Авто"
_VISION_NAME = re.compile(
    r"(?:vision|llava|moondream|qwen[23].*vl|minicpm-v|gemma3)", re.I
)
_EMBEDDING_NAME = re.compile(r"(?:embed|embedding|rerank)", re.I)
_SAFE_MODEL_NAME = re.compile(r"^[\w./:-]+$", re.ASCII)
_model_cache = (0.0, None, None)
_model_capabilities = {}
MODEL_CATALOG = (
    {"name": "qwen2.5:0.5b", "kind": "chat", "vram_gb": 0.5},
    {"name": "qwen2.5:1.5b", "kind": "chat", "vram_gb": 1.2},
    {"name": "qwen2.5:3b", "kind": "chat", "vram_gb": 2.2},
    {"name": "qwen2.5:7b", "kind": "chat", "vram_gb": 4.8},
    {"name": "qwen2.5:14b", "kind": "chat", "vram_gb": 9.2},
    {"name": "qwen2.5:32b", "kind": "chat", "vram_gb": 20.0},
    {"name": "qwen2.5:72b", "kind": "chat", "vram_gb": 45.0},
    {"name": "qwen2.5vl:3b", "kind": "vision", "vram_gb": 3.2},
    {"name": "qwen2.5vl:7b", "kind": "vision", "vram_gb": 6.5},
    {"name": "qwen2.5vl:32b", "kind": "vision", "vram_gb": 22.0},
    {"name": "qwen2.5vl:72b", "kind": "vision", "vram_gb": 48.0},
)


def _endpoint():
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def ensure_ollama_running(timeout=20):
    """Start the local Ollama server when needed and wait for its HTTP API."""
    endpoint = _endpoint()
    parsed_endpoint = urlparse(endpoint)
    if parsed_endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(
            f"OLLAMA_HOST указывает на удалённый сервер ({endpoint}); "
            "автоматически запустить его на этом ПК невозможно."
        )

    api_url = f"{endpoint}/api/tags"
    try:
        response = requests.get(api_url, timeout=1)
        response.raise_for_status()
        logger.info("Локальный сервер Ollama уже запущен: %s", endpoint)
        return
    except requests.RequestException:
        pass

    executable = shutil.which("ollama")
    if executable is None and os.name == "nt":
        candidates = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        if local_app_data:
            candidates.append(
                Path(local_app_data)
                / "Programs"
                / "Ollama"
                / "ollama.exe"
            )
        if program_files:
            candidates.append(
                Path(program_files)
                / "Ollama"
                / "ollama.exe"
            )
        executable = next((str(path) for path in candidates if path.is_file()), None)
    if executable is None:
        raise RuntimeError(
            "Сервер Ollama не отвечает, а исполняемый файл ollama не найден. "
            "Установите Ollama или запустите её вручную."
        )

    logger.info("Запускаю локальный сервер Ollama: %s", executable)
    try:
        process = subprocess.Popen(
            [executable, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise RuntimeError(f"Не удалось запустить сервер Ollama: {error}") from error

    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "Процесс ollama serve завершился при запуске. "
                "Проверьте, не занят ли порт 11434 и доступна ли Ollama."
            )
        try:
            response = requests.get(api_url, timeout=1)
            response.raise_for_status()
            logger.info("Локальный сервер Ollama готов: %s", endpoint)
            return
        except requests.RequestException as error:
            last_error = error
            time.sleep(0.25)

    raise RuntimeError(
        f"Ollama не ответила за {timeout} секунд на {endpoint}: {last_error}"
    )


def get_hardware_profile():
    """Return a lightweight Windows hardware profile for local model suggestions."""
    ram_gb = 0.0
    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                ram_gb = status.total_phys / (1024 ** 3)
        else:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            ram_gb = pages * page_size / (1024 ** 3)
    except (AttributeError, OSError, ValueError):
        logging.getLogger("lumi.ollama").info("Не удалось определить объём RAM")

    vram_gb = 0.0
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=memory.total",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            memory_values = [
                int(value.strip())
                for value in result.stdout.splitlines()
                if value.strip().isdigit()
            ]
            if memory_values:
                vram_gb = max(memory_values) / 1024
        except (OSError, subprocess.SubprocessError, ValueError):
            logging.getLogger("lumi.ollama").info("Не удалось определить видеопамять NVIDIA")

    return {
        "ram_gb": round(ram_gb, 1),
        "vram_gb": round(vram_gb, 1),
        "cpu_threads": os.cpu_count() or 1,
        "cpu": platform.processor() or platform.machine() or "Неизвестно",
    }


def get_model_recommendations(profile=None):
    """Suggest Ollama models close to 60% of available VRAM."""
    profile = profile or get_hardware_profile()
    ram_gb = profile["ram_gb"]
    vram_gb = profile["vram_gb"]
    available_memory = vram_gb or max(0, ram_gb - 4)

    def choose(kind):
        target = available_memory * 0.6
        candidates = [
            model for model in MODEL_CATALOG
            if model["kind"] == kind and model["vram_gb"] <= available_memory * 0.75
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda model: (abs(model["vram_gb"] - target), -model["vram_gb"]),
        )["name"]

    chat_model = choose("chat")
    vision_model = choose("vision")
    return {
        "profile": profile,
        "chat_model": chat_model or "qwen2.5:0.5b",
        "vision_model": vision_model,
        "prefer_cloud": ram_gb < 8 and vram_gb < 4,
    }


def model_catalog_options(kind, installed_models=()):
    """Return selectable Ollama models, annotating built-in sizes."""
    by_name = {
        model["name"]: model
        for model in MODEL_CATALOG
        if model["kind"] == kind
    }
    for model_name in installed_models:
        by_name.setdefault(model_name, None)
    return [
        {
            "name": name,
            "label": (
                f"{name} · ≈{details['vram_gb']:g} GB RAM/VRAM"
                if details
                else f"{name} · установлена"
            ),
        }
        for name, details in sorted(
            by_name.items(),
            key=lambda item: (
                _model_rank(item[0]),
                item[0],
            ),
        )
    ]


def list_models(refresh=False):
    """Return installed chat-capable models and the subset that supports images."""
    global _model_cache
    endpoint = _endpoint()
    cached_at, cached_endpoint, cached_models = _model_cache
    if (
        not refresh
        and cached_models is not None
        and endpoint == cached_endpoint
        and time.monotonic() - cached_at < 15
    ):
        return cached_models

    response = requests.get(f"{endpoint}/api/tags", timeout=3)
    response.raise_for_status()
    models = response.json().get("models", [])
    chat_models = []
    vision_models = []

    for model in models:
        name = model.get("name") or model.get("model")
        if not name or _EMBEDDING_NAME.search(name):
            continue

        capabilities = set()
        try:
            details = requests.post(
                f"{endpoint}/api/show",
                json={"model": name},
                timeout=3,
            )
            details.raise_for_status()
            capabilities = {
                str(capability).lower()
                for capability in details.json().get("capabilities", [])
            }
        except requests.RequestException:
            logger.info("Не удалось прочитать возможности модели Ollama %s", name)
        _model_capabilities[(endpoint, name)] = capabilities

        if "embedding" in capabilities and not capabilities.intersection(
            {"completion", "vision", "tools"}
        ):
            continue
        chat_models.append(name)
        if "vision" in capabilities or _VISION_NAME.search(name):
            vision_models.append(name)

    result = (
        sorted(set(chat_models), key=_model_rank),
        sorted(set(vision_models), key=_model_rank),
    )
    _model_cache = (time.monotonic(), endpoint, result)
    return result


def model_supports_tools(model_name):
    key = (_endpoint(), model_name)
    if key not in _model_capabilities:
        response = requests.post(
            f"{key[0]}/api/show",
            json={"model": model_name},
            timeout=3,
        )
        response.raise_for_status()
        _model_capabilities[key] = {
            str(capability).lower()
            for capability in response.json().get("capabilities", [])
        }
    return "tools" in _model_capabilities[key]


def _model_rank(name):
    normalized = name.lower()
    if "qwen" in normalized:
        family = 0
    elif "llama" in normalized:
        family = 1
    elif "gemma" in normalized:
        family = 2
    elif "mistral" in normalized:
        family = 3
    else:
        family = 4
    size = re.search(r":(?:latest|[^:]*?)(\d+(?:\.\d+)?)b(?:[-:]|$)", normalized)
    return (family, float(size.group(1)) if size else 999, normalized)


def resolve_model(preferred, *, vision=False, require_tools=False):
    chat_models, vision_models = list_models()
    available = vision_models if vision else chat_models
    recommended = get_model_recommendations()
    recommended_model = (
        recommended["vision_model"] if vision else recommended["chat_model"]
    )
    if preferred and preferred != AUTO_MODEL and preferred in available:
        if not require_tools or model_supports_tools(preferred):
            return preferred
        logger.warning(
            "Модель Ollama %s не поддерживает инструменты; выбираю инструментальную модель",
            preferred,
        )
    if recommended_model in available:
        if not require_tools or model_supports_tools(recommended_model):
            return recommended_model
    if require_tools:
        tool_models = [name for name in available if model_supports_tools(name)]
        if tool_models:
            return tool_models[0]
        raise RuntimeError(
            "Для действий в браузере и на компьютере нужна локальная модель Ollama "
            "с поддержкой инструментов. Установите совместимую модель и выберите её "
            "в настройках."
        )
    if available:
        return available[0]
    if vision:
        raise RuntimeError(
            "Не найдена локальная vision-модель Ollama. Скачайте её в настройках "
            f"(рекомендуется {DEFAULT_VISION_MODEL}) и обновите список моделей."
        )
    raise RuntimeError(
        "В Ollama нет загруженных языковых моделей. Скачайте модель в настройках "
        f"(рекомендуется {DEFAULT_CHAT_MODEL}) и обновите список моделей."
    )


def start_model_download(model_name):
    model_name = (model_name or "").strip()
    if not _SAFE_MODEL_NAME.fullmatch(model_name):
        raise ValueError("Укажите корректное имя модели Ollama.")
    command = f"ollama pull {model_name}"
    subprocess.Popen(
        ["cmd.exe", "/k", command],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
