"""Автообновление проекта и обнаружение локальных ИИ моделей."""

import subprocess
from pathlib import Path


class GitHubUpdater:
    """Автообновление проекта с GitHub."""

    def __init__(self):
        self.repo_path = Path(__file__).parent.parent.parent

    def is_git_repo(self) -> bool:
        """Проверка git-репозитория."""
        try:
            result = subprocess.run(["git", "rev-parse"], cwd=self.repo_path, capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def fetch_latest(self) -> bool:
        """Fetch'ит новые ветки."""
        if not self.is_git_repo():
            return False
        
        try:
            subprocess.run(["git", "fetch", "--all"], cwd=self.repo_path, timeout=30)
            return True
        except Exception:
            return False


class LocalAIDiscoverer:
    """Автоопределение локальных ИИ моделей и серверов."""

    def __init__(self):
        self.models_dir = Path(__file__).parent.parent.parent / "models" if (Path(__file__).parent.parent.parent / "models").exists() else None

    def discover_all(self) -> list:
        """Сканирование локальных ИИ моделей и серверов."""
        models = []
        
        # Ollama
        ollama_result = self._check_ollama()
        if ollama_result:
            models.append(ollama_result)
            
        # Локальные GGUF модели
        if self.models_dir and self.models_dir.exists():
            models.extend(self._scan_gguf_models())
        
        # LM Studio
        lm_studio_result = self._check_lm_studio()
        if lm_studio_result:
            models.append(lm_studio_result)

        return models

    def _check_ollama(self) -> dict | None:
        """Проверка Ollama сервера."""
        try:
            result = subprocess.run(["curl", "-s", "http://localhost:11434/api/tags"], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                data = eval(result.stdout)
                models_list = data.get("models", [])
                
                if models_list:
                    return {
                        "name": "Ollama",
                        "url": "http://localhost:11434",
                        "available_models": [m["name"].split(":")[0] for m in models_list],
                        "default_model": models_list[0]["name"].split(":")[0],
                        "status": "running"
                    }
        except Exception:
            pass
        
        return None

    def _check_lm_studio(self) -> dict | None:
        """Проверка LM Studio сервера."""
        try:
            result = subprocess.run(["curl", "-s", "http://localhost:1234/api/v1/models"], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return {
                    "name": "LM Studio",
                    "url": "http://localhost:1234",
                    "status": "running"
                }
        except Exception:
            pass
        
        return None

    def _scan_gguf_models(self) -> list:
        """Сканирование папки с GGUF моделями."""
        if not self.models_dir or not self.models_dir.exists():
            return []
        
        gguf_files = list(self.models_dir.glob("*.gguf"))
        models = []
        
        for path in gguf_files:
            models.append({
                "name": f"GGUF: {path.stem}",
                "file": str(path),
                "size_mb": path.stat().st_size / (1024 * 1024),
                "type": "local_file"
            })
        
        return models

    def get_best_llm(self) -> dict | None:
        """Возвращает лучший вариант LLM."""
        models = self.discover_all()
        
        if not models:
            return None
        
        # Приоритет: Ollama > LM Studio > GGUF файлы
        ollama = next((m for m in models if m["name"] == "Ollama"), None)
        if ollama:
            return ollama
        
        lm_studio = next((m for m in models if m["name"] == "LM Studio"), None)
        if lm_studio:
            return lm_studio
        
        # Если есть только локальные файлы GGUF
        if models:
            models.sort(key=lambda x: x.get("size_mb", 0), reverse=True)
            return models[0]
        
        return None

    def get_model_name(self) -> str | None:
        """Получает имя модели по умолчанию для использования."""
        best = self.get_best_llm()
        if best and "available_models" in best:
            return best["available_models"][0]
        elif best and "file" in best:
            parts = Path(best["file"]).stem.split("_")
            return parts[0].replace("Llama", "") + ":7b" if len(parts) > 1 else Path(best["file"]).stem.split("-")[0] + ":7b"
        elif best and "name" in best:
            return "lm-studio-model"
        
        return None


def get_default_llm() -> str | None:
    """Получает модель по умолчанию из автообнаружения."""
    discoverer = LocalAIDiscoverer()
    model_name = discoverer.get_model_name()
    return model_name if model_name else "llama3:8b"

