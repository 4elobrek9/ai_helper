# Как протестировать проект локально

## 1) Быстрая проверка структуры/синтаксиса
```bash
python -m py_compile GUI.py listen.py sintez.py core/gui/app.py core/voice/assistant.py core/voice/formatter.py core/voice/engine.py core/config/settings.py core/memory/store.py build_exe.py
```

## 2) Запуск GUI
```bash
python GUI.py
```

Что проверить руками:
- окно открывается с заголовком `LUMI AI`;
- иконка окна подхватывается (если есть `app_icon.png`/`icon.png`/`images.jpg`);
- в чате можно отправить текст;
- кнопка микрофона запускает/останавливает ассистента.

## 3) Проверка сборки EXE
```bash
python build_exe.py
```

Результат:
- файл `dist/AI_Helper.exe`;
- иконка EXE берётся из `app_icon.ico` (если есть), иначе `app_icon.png`.

## 4) Проверка трея
После запуска GUI сверни окно:
- приложение должно скрыться;
- в трее должна быть иконка;
- из меню трея можно развернуть окно или выйти.

## 5) Минимальный smoke-test голоса
- заполни `PORCUPINE KEY` в настройках;
- нажми "Запустить микрофон";
- проверь, что не возникает ошибок старта аудио.
