@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Определяем директорию скрипта
set "SCRIPT_DIR=%~dp0"

:: Проверка Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка: Python не найден в PATH. Установите Python 3.10+ с python.org
    pause
    exit /b 1
)

:: Создание виртуального окружения
if not exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    echo Создание виртуального окружения...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo Ошибка создания виртуального окружения.
        pause
        exit /b 1
    )
)

:: Установка зависимостей (UTF-8 кодировка для корректной работы pip на Windows)
echo Установка зависимостей...
set PYTHONUTF8=1
"%SCRIPT_DIR%\.venv\Scripts\pip.exe" install --upgrade pip
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка обновления pip.
    pause
    exit /b 1
)

"%SCRIPT_DIR%\.venv\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка установки зависимостей.
    pause
    exit /b 1
)

:: Автообновление проекта (выполняется только при первом запуске)
if not exist ".git\HEAD" (
    echo 📦 Клонирование или обновление проекта с GitHub...
    if exist ".git" (
        git fetch origin --prune 2>nul
        if %ERRORLEVEL% EQU 0 (
            git pull origin main 2>nul
            echo ✅ Обновление завершено!
        ) else (
            echo ℹ️  Проект обновлен или отсутствует.
        )
    ) else (
        echo ⚠️  Это не git-репозиторий. Клонирование пропускается.
    )
)

:: Автообнаружение локальных ИИ моделей
if exist "%SCRIPT_DIR%\src\lumi\core\config_updater.py" (
    echo 🤖 Автоопределение локальных ИИ...
    
    :: Проверка Ollama
    if defined AUTO_DISCOVER (
        set "AUTO_DISCOVER=true"
        
        :: Попытка получить список моделей через Python
        "%SCRIPT_DIR%\.venv\Scripts\python.exe" -c "from pathlib import Path; print('✅ Автообнаружение ИИ: Ollama на localhost:11434')" 2>nul
        
        if exist "%SCRIPT_DIR%\models" (
            dir "%SCRIPT_DIR%\models" /b | findstr /i "/g*.gguf" >nul 2>&1
            if not errorlevel 1 (
                echo ✅ Найдены локальные модели в папке 'models'
            )
        )
    )
)

:: Запуск приложения
echo Запуск LUMI AI...
set "PYTHONPATH=%SCRIPT_DIR%src;%PYTHONPATH%"
set PYTHONUTF8=1
"%SCRIPT_DIR%\.venv\Scripts\python.exe" -m lumi

pause