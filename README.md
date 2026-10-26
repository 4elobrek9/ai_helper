# 💎 LUMI AI — Локальный голосовой ассистент

**LUMI AI** — персональный локальный голосовой ассистент на базе **Ollama**, **faster-whisper**, **Silero TTS** и **desktop-tools**. Полная локальность: все данные остаются на вашем компьютере, нет необходимости в облачных API-ключаях.

Концепция **"Living Shard" (Живой осколок)**: компактное стильное окно, которое всегда под рукой, но не мешает работе.

---

## 🎯 Возможности

| Категория | Возможности |
|-----------|-------------|
| **Голос** | Wake-word (Porcupine), STT (faster-whisper), TTS (Silero), непрерывное прослушивание |
| **LLM** | Локальный Ollama с Mistral как fallback, системные промпты, история чата |
| **Desktop-агент** | Открытие приложений, управление окнами, OCR экрана, буфер обмена, веб-поиск, скриншоты, чтение/запись файлов |
| **Память** | SQLite история чата, долгосрочная память (факты), суммаризация, экспорт |
| **Интерфейс** | Flet UI с тёмной темой, индикаторы состояния, трей, горячие клавиши |
| **Надёжность** | Safe Mode, подтверждение опасных действий, graceful shutdown, ротация логов |

---

## 📁 Структура проекта

```
ai_helper/
├── _legacy/              # Устаревшие файлы (архив)
├── assets/               # Иконы и ресурсы
├── audio/                # Звуковые файлы
├── models/               # Модели wake-word
├── src/
│   └── lumi/
│       ├── __init__.py
│       ├── __main__.py   # Точка входа
│       ├── core/         # Конфиг, пути, логирование, состояние
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── paths.py
│       │   └── state.py
│       ├── gui/          # Flet UI
│       │   ├── main.py
│       │   └── widgets.py
│       ├── voice/        # STT, TTS, wake-word
│       │   ├── stt.py
│       │   ├── tts.py
│       │   └── wake_word.py
│       ├── desktop/      # Инструменты ПК + OCR
│       │   ├── tools.py
│       │   ├── ocr.py
│       │   └── window.py
│       ├── llm/          # LLM провайдеры
│       │   ├── base.py
│       │   ├── ollama.py
│       │   ├── mistral.py
│       │   └── manager.py
│       ├── memory/       # Память чата
│       │   ├── chat_memory.py
│       │   └── long_term.py
│       └── utils/        # Утилиты
├── data/                 # Локальные данные (БД, факты)
├── logs/                 # Логи приложения
├── scripts/              # Вспомогательные скрипты
├── tests/                # Unit-тесты
├── docs/                 # Документация
├── pyproject.toml        # Конфигурация проекта
├── requirements.txt      # Зависимости
├── launch.bat            # Запуск приложения
├── build_exe.py          # Сборка EXE
└── README.md
```

---

## 🚀 Быстрая установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/4elobrek9/ai_helper.git
cd ai_helper
```

### 2. Запуск через launch.bat

Дважды кликните на `launch.bat` — скрипт автоматически:
1. Создаст виртуальное окружение (`.venv`)
2. Установит зависимости из `requirements.txt`
3. Запустит приложение

### 3. Ручной запуск

```bash
# Создать и активировать venv
python -m venv .venv
.venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt

# Запустить
python -m lumi
```

---

## ⚙️ Конфигурация

Основные настройки в `lumi_config.yaml`:

```yaml
assistant:
  name: "Lumi"
  language: "ru-RU"
  system_prompt: "Ты Lumi, дружелюбный голосовой AI-ассистент."
  history_limit: 12

llm:
  provider: "ollama"
  endpoint: "http://localhost:11434"
  model: "llama3:8b"
  temperature: 0.6
  max_tokens: 512

stt:
  engine: "faster-whisper"
  language: "ru"
  model: "small"

tts:
  engine: "silero"
  voice: "xenia"
  rate: 1.0
  volume: 1.0

desktop:
  safe_mode: false
  confirm_dangerous: true
  allowed_apps:
    - notepad
    - calc
    - chrome
```

---

## 🛠 Инструменты desktop-агента

| Инструмент | Описание | Подтверждение |
|------------|----------|---------------|
| `inspect_screen` | OCR текста с экрана | Нет |
| `open_application` | Запуск приложения из белого списка | Нет |
| `click_text` | Клик по найденному тексту на экране | Нет |
| `move_to_text` | Перемещение курсора к тексту | Нет |
| `type_text` | Ввод текста на активное окно | Нет |
| `press_keys` | Горячие клавиши (белый список) | Нет |
| `get_clipboard` / `set_clipboard` | Работа с буфером обмена | Нет |
| `open_url` / `search_web` | Открытие URL и поиск в браузере | Нет |
| `list_running_apps` | Список процессов | Нет |
| `focus_window` / `minimize_window` | Управление окнами | Нет |
| `close_window` | Закрытие окна | **Да** |
| `take_screenshot` | Скриншот экрана | Нет |
| `read_file` / `write_file` | Чтение/запись файлов (разрешённые папки) | **Да** (запись) |

---

## 🧪 Разработка

### Линтинг и форматирование

```bash
# Проверка кода
ruff check src/
ruff format --check src/

# Автоисправление
ruff check --fix src/
ruff format src/
```

### Тесты

```bash
pytest tests/
```

### Сборка EXE

```bash
python build_exe.py
```

---

## 🗺 Roadmap

- [x] Этап 1: Аудит и очистка репозитория
- [x] Этап 2: Архитектура и модульность
- [ ] Этап 3: Улучшение Desktop Tools
- [ ] Этап 4: Голос и UX голосового режима
- [ ] Этап 5: Память и интеллект
- [ ] Этап 6: GUI и UX полировка
- [ ] Этап 7: Надёжность, ошибки, DX
- [ ] Этап 8: Документация и финализация

---

## 📄 Лицензия

MIT — см. [LICENSE](LICENSE).

---

## 🤝 Поддержка

Telegram: [@xxxlhomie](https://t.me/xxxlhomie)  
GitHub: [4elobrek9/ai_helper](https://github.com/4elobrek9/ai_helper)