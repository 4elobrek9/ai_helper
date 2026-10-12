import logging
import os
import re
import subprocess
import time

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


def _endpoint():
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


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
    if preferred and preferred != AUTO_MODEL and preferred in available:
        if not require_tools or model_supports_tools(preferred):
            return preferred
        logger.warning(
            "Модель Ollama %s не поддерживает инструменты; выбираю инструментальную модель",
            preferred,
        )
    if require_tools:
        tool_models = [name for name in available if model_supports_tools(name)]
        if tool_models:
            return tool_models[0]
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
