@echo off
:: Проверка на администратора
NET SESSION >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Запуск от имени администратора...
    powershell -Command "Start-Process '%~f0' -Verb RunAs" -WindowStyle Hidden
    exit /b
)

:: Проверка Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка: Python не установлен или не добавлен в PATH.
    pause
    exit /b
)

:: Проверка llama
where llama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Ошибка: llama не найдена. Убедитесь, что она установлена.
    pause
    exit /b
)

:: Запуск llama serve в скрытом режиме
echo Запуск llama serve в фоне...
start /B llama serve >nul 2>&1

exit