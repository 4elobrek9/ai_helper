# LUMI AI — Голосовой AI-ассистент на Python + Flet

## 🌟 Что такое LUMI AI?

**LUMI AI** — локальный голосовой AI-ассистент для Windows, написанный на Python с использованием библиотеки `flet`. Приложение полностью работает оффлайн:  
✅ **Ollama** — локальная LLM (запуск моделей через REST API)  
✅ **Faster-whisper** — ASR (распознавание речи в фоне)  
✅ **Silero TTS** + системный speech — синтез речи  
✅ **Desktop Agent** — управление приложениями, OCR, файловая система

---

## 🚀 Быстрый старт

### 1. Установите Python 3.10+
Скачайте с [python.org](https://www.python.org/downloads/) (выбирайте "Add to PATH").

### 2. Запустите `launch.bat`
```bat
cd C:\Users\XXXLHOMIE\.copilot\repos\ai_helper
launch.bat
```

Скрипт:
1. Создаст `.venv`
2. Установит зависимости из `requirements.txt`
3. Запустит приложение

### 3. Первый запуск
- Убедитесь, что **Ollama установлен** ([ollama.com](https://ollama.com)) и сервер запущен (`ollama serve`).
- Подключите микрофон.
- Нажмите на кнопку микрофона в GUI или используйте `Ctrl+Alt+E` для активации прослушивания.

---

## 📁 Структура проекта

```
ai_helper/
├─ src/lumi/
│  ├─ core/          # Ядро: config, logging, paths, state, app
│  ├─ gui/           # Flet GUI: main.py, widgets.py
│  ├─ voice/         # STT (faster-whisper), TTS (Silero), wake_word
│  ├─ desktop/       # Desktop-агент: tools, ocr, window
│  ├─ llm/           # LLM менеджеры: base, ollama, mistral, manager, tools
│  ├─ memory/        # Память: chat_memory, long_term
│  └─ tests/         # Unit-тесты
├─ assets/           # Иконки и ресурсы
├─ scripts/          # Запуск и сборка
├─ docs/             # Документация
├─ _legacy/          # Старый код (для справки)
└─ launch.bat        # Точка входа
```

---

## 🛠️ Ключевые модули

### `core/app.py`
Центральный класс `LumiApp` с инициализацией всех компонентов:
- Desktop tools
- LLM менеджер (Ollama/Mistral)
- Память (ChatMemory + LongTermMemory)
- STT/TTS/WakeWord

### `core/config.py`
Singleton `ConfigManager` с поддержкой горячих перезагрузок. Конфиг хранится в `lumi_config.yaml`.

### `llm/manager.py`
`LLMManager` — объединяет primary/fallback LLM с парсингом tool-calls и выполнением инструментов.

### `llm/tools.py`
`ToolRegistry` — регистрация, описание и вызов десктоп-инструментов (17 утилит).

### `voice/stt.py`
STT-движок на базе `faster-whisper` с ленивой загрузкой модели.

### `voice/tts.py`
TTSEngine — очередь сообщений, предобработка чисел/математики, callbacks для GUI.

### `desktop/tools.py`
DesktopAgent — безопасный выполнение команд с подтверждением опасных действий и белым списком приложений.

---

## 🧪 Тестирование

```bat
cd src/lumi/tests
python -m pytest test_memory.py -v
```

Тесты покрывают:
- Добавление/удаление фактов в `LongTermMemory`
- Ограничение размера истории в `ChatMemory`
- Singleton паттерн для `ConfigManager`
- Безопасный режим `DesktopTools`

---

## 📦 Сборка EXE (PyInstaller)

```bat
python build_exe.py
```

Скрипт создаст `dist/lumi_ai.exe`, используя актуальные data-файлы из `assets/`.

---

## 🎨 Flet GUI

Особенности:
- **Living Shard** дизайн (анимированная сфера)
- Индикаторы состояний (готов, слушаю, думаю, говорю)
- Окна чата и настроек
- Поддержка горячих клавиш (Ctrl+Alt+S/E/R)
- Трей-заглушка с меню

---

## 🐛 Отладка

- Логирование: `logs/app.log` (ротация 5 МБ, 3 бэкапа)
- Конфиг для отладки: `lumi_config.yaml` (добавьте `debug: true`)
- Проверка Ollama: `curl http://localhost:11434/api/tags`

---

## 🔄 Автообновление и обнаружение ИИ

### Автообновление проекта
При каждом запуске `launch.bat` скрипт автоматически:
1. **Проверка обновлений** — fetch'ит новые ветки с GitHub
2. **Pull изменений** — обновляет локальный репозиторий если доступны изменения
3. **Сохраняет текущую ветку** — безопасно работает только в актуальной ветке

### Автоопределение локальных ИИ
Скрипт автоматически обнаруживает:
- 🤖 **Ollama** на localhost:11434
- 🦙 Локальные модели в папке `./models` (GGUF файлы)
- 💻 LM Studio и другие LLM серверы

Приводит статистику доступных моделей для использования.

---

## 📝 Чеклист перед релизой

- [x] Архитектура модульная
- [x] Graceful shutdown
- [x] Desktop tools с подтверждением опасных действий
- [x] Автообновление проекта (GitHub integration)
- [x] Автоопределение локальных ИИ (Ollama, LM Studio, модели GGUF)
- [x] Проверка Ollama при старте PowerShell скриптом
- [ ] Unit-тесты с покрытием >80%
- [ ] Сборка EXE работает
- [ ] Документация в docs/

---

## 📄 Лицензия

MIT License — свободно для использования и модификации.

---

*Последняя синхронизация: 26.10.2026*