import flet as ft
import sqlite3
import sounddevice as sd
import math
import os
import sys
import time
import threading
import asyncio
import subprocess
import webbrowser
from pathlib import Path
import app_logging
import listen 
from listen import VoiceAssistant, process_text_query, load_memory
from sintez import set_voice
import ctypes
import logging
from PIL import Image
import pystray
from app_paths import data_path, resource_path
from ollama_models import (
    AUTO_MODEL,
    DEFAULT_CHAT_MODEL,
    MODEL_CATALOG,
    get_model_recommendations,
    list_models,
    model_catalog_options,
    ensure_ollama_running,
    start_model_download,
)
from skills import DEVELOPER_SKILLS, add_user_skill, list_user_skills, remove_user_skill
from piper_tts import VOICE_CATALOG, install_voice, is_voice_installed
import screensage

# ЗАМЕТКИ ДЛЯ БУДУЩЕГО: 
# Дизайн: Living Shard, 400x600. 
# Волны: Теперь строго по центру и активируются ТОЛЬКО кнопкой микрофона.
# Слои: Окна чата и конфига теперь перекрывают все кнопки и отпечаток.
# БД: Авто-миграция и сохранение/загрузка настроек (API, Prompt, Devices, Porcupine).

def init_db():
    conn = sqlite3.connect(data_path("config.db"))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            api_key TEXT,
            prompt TEXT,
            input_device TEXT,
            output_device TEXT,
            porcupine_key TEXT,
            wake_word_engine TEXT,
            ai_provider TEXT,
            tts_engine TEXT,
            ui_language TEXT,
            response_language TEXT,
            ollama_chat_model TEXT,
            ollama_vision_model TEXT,
            screen_monitor TEXT
        )
    """)
    # Проверка и добавление колонок для старых баз данных
    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    if "input_device" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN input_device TEXT")
    if "output_device" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN output_device TEXT")
    if "porcupine_key" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN porcupine_key TEXT")
    if "wake_word_engine" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN wake_word_engine TEXT")
    if "ai_provider" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN ai_provider TEXT")
    if "tts_engine" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN tts_engine TEXT")
    if "ui_language" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN ui_language TEXT")
    if "response_language" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN response_language TEXT")
    if "ollama_chat_model" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN ollama_chat_model TEXT")
    if "ollama_vision_model" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN ollama_vision_model TEXT")
    if "screen_monitor" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN screen_monitor TEXT")
    conn.commit()
    conn.close()

def save_settings(
    api_key, prompt, input_dev, output_dev, porcupine_key, wake_word_engine,
    ai_provider, tts_engine, ui_language, response_language,
    ollama_chat_model, ollama_vision_model, screen_monitor,
):
    conn = sqlite3.connect(data_path("config.db"))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings")
    cursor.execute(
        """INSERT INTO settings (
            api_key, prompt, input_device, output_device, porcupine_key,
            wake_word_engine, ai_provider, tts_engine, ui_language, response_language,
            ollama_chat_model, ollama_vision_model, screen_monitor
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            api_key, prompt, input_dev, output_dev, porcupine_key,
            wake_word_engine, ai_provider, tts_engine, ui_language,
            response_language, ollama_chat_model, ollama_vision_model,
            screen_monitor,
        )
    )
    conn.commit()
    conn.close()

def load_settings():
    conn = sqlite3.connect(data_path("config.db"))
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT api_key, prompt, input_device, output_device, porcupine_key,
                      wake_word_engine, ai_provider, tts_engine, ui_language,
                      response_language,
                      ollama_chat_model, ollama_vision_model, screen_monitor
               FROM settings LIMIT 1"""
        )
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    if row:
        return tuple("" if v is None else v for v in row)
    return ("", "", None, None, "", "Ручной режим без ключа", "Ollama (локально)",
            "Silero (Ксения)", "RU", "RU", AUTO_MODEL, AUTO_MODEL, "")

def get_audio_devices(kind='input'):
    try:
        devices = sd.query_devices()
        if kind == 'input':
            devs = [d['name'] for d in devices if d['max_input_channels'] > 0]
        else:
            devs = [d['name'] for d in devices if d['max_output_channels'] > 0]
        return list(dict.fromkeys(devs)) 
    except Exception:
        return ["Default Device"]

voice_assistant_instance = None
skills_window_process = None
chat_window_process = None

try:
    myappid = 'lumi.ai.assistant.2.0' # Любая уникальная строка
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass


def handle_window_event(page, event):
    if event.data in {"close", "minimize"}:
        logging.info("Окно скрывается в системный трей")
        page.window.skip_task_bar = True
        page.window.visible = False
        page.window.always_on_top = False
        page.update()
    elif event.data == "restore":
        page.window.skip_task_bar = False
        page.window.visible = True
        page.window.always_on_top = True
        page.update()
    elif event.data == "blur":
        page.window.always_on_top = False
        page.update()
    elif event.data == "focus":
        page.window.always_on_top = True
        page.update()


def open_skills_window(_=None):
    global skills_window_process
    if skills_window_process is not None and skills_window_process.poll() is None:
        try:
            window_handle = ctypes.windll.user32.FindWindowW(
                None,
                "LUMI — Навыки",
            )
            if window_handle:
                ctypes.windll.user32.ShowWindow(window_handle, 9)
                ctypes.windll.user32.SetForegroundWindow(window_handle)
        except (AttributeError, OSError):
            logging.exception("Не удалось активировать окно навыков")
        return

    if getattr(sys, "frozen", False):
        command = [sys.executable, "--skills-window"]
    else:
        python_executable = Path(sys.executable)
        pythonw = python_executable.with_name("pythonw.exe")
        command = [
            str(pythonw if pythonw.is_file() else python_executable),
            str(Path(__file__).resolve()),
            "--skills-window",
        ]
    try:
        child_environment = os.environ.copy()
        child_environment["LUMI_LOG_NAME"] = "skills"
        skills_window_process = subprocess.Popen(
            command,
            env=child_environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        logging.exception("Не удалось открыть отдельное окно навыков")


def open_chat_window(_=None):
    global chat_window_process
    if chat_window_process is not None and chat_window_process.poll() is None:
        try:
            window_handle = ctypes.windll.user32.FindWindowW(None, "LUMI — Чат")
            if window_handle:
                ctypes.windll.user32.ShowWindow(window_handle, 9)
                ctypes.windll.user32.SetForegroundWindow(window_handle)
        except (AttributeError, OSError):
            logging.exception("Не удалось активировать окно чата")
        return

    if getattr(sys, "frozen", False):
        command = [sys.executable, "--chat-window"]
    else:
        python_executable = Path(sys.executable)
        pythonw = python_executable.with_name("pythonw.exe")
        command = [
            str(pythonw if pythonw.is_file() else python_executable),
            str(Path(__file__).resolve()),
            "--chat-window",
        ]
    try:
        child_environment = os.environ.copy()
        child_environment["LUMI_LOG_NAME"] = "chat"
        chat_window_process = subprocess.Popen(
            command,
            env=child_environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        logging.exception("Не удалось открыть отдельное окно чата")


def main(page: ft.Page):
    init_db()
    icon_path = str(resource_path("app_icon.ico"))

    # --- 3. НАСТРОЙКА ТРЕЯ (Справа внизу) ---
    def stop_child_window(process, name):
        if process is None or process.poll() is not None:
            return
        try:
            logging.info("Завершаю отдельное окно %s (PID %s)", name, process.pid)
            window_title = {"чата": "LUMI — Чат", "навыков": "LUMI — Навыки"}.get(name)
            if window_title and os.name == "nt":
                hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
                if hwnd:
                    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
                    try:
                        process.wait(timeout=2)
                        return
                    except subprocess.TimeoutExpired:
                        pass
            process.terminate()
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logging.warning("Окно %s не завершилось штатно; завершаю процесс", name)
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                logging.exception("Не удалось завершить окно %s", name)
        except (OSError, subprocess.SubprocessError):
            logging.exception("Не удалось завершить окно %s", name)

    def shutdown_app():
        global chat_window_process, skills_window_process
        if voice_assistant_instance is not None:
            try:
                voice_assistant_instance.stop()
            except Exception:
                logging.exception("Не удалось остановить голосовой движок при выходе")
        stop_child_window(chat_window_process, "чата")
        stop_child_window(skills_window_process, "навыков")
        page.window.prevent_close = False
        page.window.destroy()

    def quit_app(icon, item):
        logging.info("Запрошен полный выход LUMI из системного трея")
        icon.stop()
        try:
            page.run_thread(shutdown_app)
        except Exception:
            logging.exception("Не удалось запланировать завершение LUMI")
            shutdown_app()

    def show_app(icon, item):
        page.window.skip_task_bar = False
        page.window.visible = True
        page.window.minimized = False
        page.window.always_on_top = True
        page.update()
        page.window.to_front()

    def setup_tray():
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Не найден файл иконки приложения: {icon_path}")
        img = Image.open(icon_path)
        menu = pystray.Menu(
            pystray.MenuItem("Развернуть LUMI", show_app, default=True),
            pystray.MenuItem("Выход", quit_app)
        )
        tray = pystray.Icon("LUMI AI", img, "LUMI AI", menu)
        tray.run()

    # Сразу запускаем трей в отдельном потоке
    def start_tray():
        try:
            setup_tray()
        except Exception:
            logging.exception("Не удалось запустить значок LUMI в системном трее")

    threading.Thread(target=start_tray, daemon=True).start()

    # --- 4. ЛОГИКА СВОРАЧИВАНИЯ В ТРЕЙ ---
    def on_window_event(e):
        handle_window_event(page, e)

    page.window.on_event = on_window_event

    # --- Конфигурация окна ---
    page.title = "LUMI AI"
    page.window.prevent_close = True
    if os.path.exists(icon_path):
        page.window.icon = icon_path
    
    page.window.width = 400
    page.window.height = 600
    page.window.min_width = 400
    page.window.max_width = 400
    page.window.min_height = 600
    page.window.max_height = 600
    page.window.resizable = False
    page.window.maximizable = False
    page.window.always_on_top = True

    try:
        if hasattr(page.window, "center"):
            page.run_task(page.window.center)
    except Exception:
        pass
    
    page.bgcolor = "#0b0e17"
    page.padding = 0

    CYAN = "#00ffff"
    CYAN_GLOW = "0x4400ffff"
    CENTER_X = 200 - 40 
    CENTER_Y = 300 - 40 
    RADIUS = 110        
    ANIM_SPEED = 500

    state = {
        "is_menu_open": False,
        "is_voice_active": False,
        "is_chat_expanded": False,
        "is_config_open": False,
        "is_skills_open": False,
        "running": True
    }
    state["voice_preparing"] = True
    state["voice_preparation_error"] = None

    (
        saved_api, saved_prompt, saved_in, saved_out, saved_pv_key, saved_wake,
        saved_ai, saved_tts, saved_ui_lang, saved_rsp_lang,
        saved_chat_model, saved_vision_model, saved_monitor,
    ) = load_settings()
    set_voice(saved_tts)

    # --- Слой анимации (Волны) ---
    class WaveCircle(ft.Container):
        def __init__(self, size=80):
            super().__init__()
            self.width = size
            self.height = size
            self.border_radius = size / 2
            self.border = ft.border.Border(
                top=ft.BorderSide(2, CYAN),
                right=ft.BorderSide(2, CYAN),
                bottom=ft.BorderSide(2, CYAN),
                left=ft.BorderSide(2, CYAN),
            )
            self.opacity = 0
            self.scale = 1
            self.top = CENTER_Y 
            self.left = CENTER_X 
            self.animate_opacity = ft.Animation(1500, ft.AnimationCurve.EASE_OUT)
            self.animate_scale = ft.Animation(1500, ft.AnimationCurve.EASE_OUT)

    wave1 = WaveCircle()
    wave2 = WaveCircle()

    def pulse_waves_logic():
        while state["running"]:
            if state["is_voice_active"]:
                wave1.opacity = 0.5
                wave1.scale = 3.5
                wave1.update()
                time.sleep(0.8)
                wave2.opacity = 0.3
                wave2.scale = 4.5
                wave2.update()
                time.sleep(1.2)
                wave1.opacity = 0
                wave1.scale = 1.0
                wave2.opacity = 0
                wave2.scale = 1.0
                wave1.update()
                wave2.update()
                time.sleep(0.3)
            else:
                if wave1.opacity > 0 or wave2.opacity > 0:
                    wave1.opacity = 0
                    wave2.opacity = 0
                    wave1.update()
                    wave2.update()
                time.sleep(0.5)

    # --- Элементы управления настройками ---
    api_input = ft.TextField(label="MISTRAL API KEY", password=True, can_reveal_password=True, border_color="white24", value=saved_api, text_size=12)
    pv_key_input = ft.TextField(label="PORCUPINE KEY", password=True, can_reveal_password=True, border_color="white24", value=saved_pv_key, text_size=12)
    prompt_input = ft.TextField(label="SYSTEM PROMPT", multiline=True, min_lines=3, border_color="white24", value=saved_prompt, text_size=12)
    in_dev_dropdown = ft.Dropdown(label="INPUT (MIC)", options=[ft.dropdown.Option(d) for d in get_audio_devices('input')], border_color="white24", value=saved_in, text_size=12)
    out_dev_dropdown = ft.Dropdown(label="OUTPUT (SPEAKERS)", options=[ft.dropdown.Option(d) for d in get_audio_devices('output')], border_color="white24", value=saved_out, text_size=12)
    wake_options = [
        "Ручной режим без ключа",
        "Локальное слово «Люми»",
        "Porcupine",
    ]
    wake_word_dropdown = ft.Dropdown(label="АКТИВАЦИЯ ГОЛОСА", options=[ft.dropdown.Option(d) for d in wake_options], border_color="white24", value=saved_wake if saved_wake in wake_options else wake_options[0], text_size=12)
    ai_options = ["Ollama (локально)", "Mistral API"]
    selected_ai = saved_ai if saved_ai in ai_options else "Ollama (локально)"
    ai_provider_dropdown = ft.Dropdown(label="AI PROVIDER", options=[ft.dropdown.Option(d) for d in ai_options], border_color="white24", value=selected_ai, text_size=12)
    model_recommendations = get_model_recommendations()
    hardware_profile = model_recommendations["profile"]
    chat_model_dropdown = ft.Dropdown(
        label="МОДЕЛЬ ДЛЯ ЧАТА",
        options=[
            ft.dropdown.Option(AUTO_MODEL),
            *[
                ft.dropdown.Option(key=option["name"], text=option["label"])
                for option in model_catalog_options("chat")
            ],
            *(
                [ft.dropdown.Option(saved_chat_model)]
                if saved_chat_model
                and saved_chat_model != AUTO_MODEL
                and saved_chat_model not in {
                    model["name"] for model in MODEL_CATALOG
                }
                else []
            ),
        ],
        value=(
            saved_chat_model
            if saved_chat_model and saved_chat_model != AUTO_MODEL
            else model_recommendations["chat_model"]
        ),
        border_color="white24",
        text_size=12,
    )
    vision_model_dropdown = ft.Dropdown(
        label="VISION-МОДЕЛЬ ДЛЯ АНАЛИЗА ЭКРАНА",
        options=[
            ft.dropdown.Option(AUTO_MODEL),
            *[
                ft.dropdown.Option(key=option["name"], text=option["label"])
                for option in model_catalog_options("vision")
            ],
            *(
                [ft.dropdown.Option(saved_vision_model)]
                if saved_vision_model
                and saved_vision_model != AUTO_MODEL
                and saved_vision_model not in {
                    model["name"] for model in MODEL_CATALOG
                }
                else []
            ),
        ],
        value=(
            saved_vision_model
            if saved_vision_model and saved_vision_model != AUTO_MODEL
            else model_recommendations["vision_model"] or AUTO_MODEL
        ),
        border_color="white24",
        text_size=12,
    )
    hardware_summary = ft.Text(
        (
            f"ПК: {hardware_profile['ram_gb']:g} ГБ RAM · "
            f"{hardware_profile['cpu_threads']} потоков CPU"
            + (
                f" · NVIDIA {hardware_profile['vram_gb']:g} ГБ VRAM"
                if hardware_profile["vram_gb"]
                else ""
            )
            + (
                "\nМало ресурсов: для чата предпочтителен Mistral API. "
                "Локально попробуйте qwen2.5:1.5b."
                if model_recommendations["prefer_cloud"]
                else (
                    f"\nДля чата: {model_recommendations['chat_model']}."
                    + (
                        f" Для экрана: {model_recommendations['vision_model']}."
                        if model_recommendations["vision_model"]
                        else "\nVision-модели на этом ПК могут работать медленно."
                    )
                )
            )
        ),
        size=11,
        color="#b8c4d8",
    )
    ollama_status = ft.Text(
        "Ищем установленные модели Ollama…",
        size=10,
        color="white54",
    )
    tts_options = [
        ft.dropdown.Option("Silero (Ксения)"),
        ft.dropdown.Option("Системный женский голос"),
        *[
            ft.dropdown.Option(
                key=f"piper:{voice_name}",
                text=voice_details["label"],
            )
            for voice_name, voice_details in VOICE_CATALOG.items()
        ],
    ]
    tts_engine_dropdown = ft.Dropdown(
        label="ГОЛОС ОТВЕТА",
        options=tts_options,
        border_color="white24",
        value=(
            saved_tts
            if saved_tts in [option.key for option in tts_options]
            else "Silero (Ксения)"
        ),
        text_size=12,
    )
    piper_voice_dropdown = ft.Dropdown(
        label="ГОЛОС PIPER ДЛЯ ЗАГРУЗКИ",
        options=[
            ft.dropdown.Option(key=name, text=details["label"])
            for name, details in VOICE_CATALOG.items()
        ],
        value=next(iter(VOICE_CATALOG)),
        border_color="white24",
        text_size=12,
    )
    piper_download_status = ft.Text(size=10, color="white54")
    piper_download_progress = ft.ProgressBar(
        value=0,
        color=CYAN,
        bgcolor="white12",
        visible=False,
    )
    ui_lang_dropdown = ft.Dropdown(label="UI LANGUAGE", options=[ft.dropdown.Option(d) for d in ["RU", "EN"]], border_color="white24", value=saved_ui_lang or "RU", text_size=12)
    response_lang_dropdown = ft.Dropdown(label="AI RESPONSE LANGUAGE", options=[ft.dropdown.Option(d) for d in ["RU", "EN"]], border_color="white24", value=saved_rsp_lang or "RU", text_size=12)
    from command_OCR import get_monitors
    available_monitors = get_monitors()
    primary_monitor = next(
        (monitor for monitor in available_monitors if monitor["is_primary"]),
        available_monitors[0] if available_monitors else {"index": 1, "label": "Экран 1"},
    )
    screen_monitor_dropdown = ft.Dropdown(
        label="ЭКРАН ДЛЯ АНАЛИЗА И УПРАВЛЕНИЯ",
        options=[
            ft.dropdown.Option(
                key=str(monitor["index"]),
                text=monitor["label"],
            )
            for monitor in available_monitors
        ] or [ft.dropdown.Option(key="1", text="Экран 1")],
        value=(
            saved_monitor
            if saved_monitor in {str(monitor["index"]) for monitor in available_monitors}
            else str(primary_monitor["index"])
        ),
        border_color="white24",
        text_size=12,
    )

    def show_config_message(message):
        page.snack_bar = ft.SnackBar(content=ft.Text(message))
        page.snack_bar.open = True
        page.update()

    def refresh_piper_status(_=None):
        voice_name = piper_voice_dropdown.value
        piper_download_status.value = (
            "Установлен"
            if is_voice_installed(voice_name)
            else "Не установлен · около 63 МБ"
        )
        piper_download_status.update()

    def update_piper_progress(fraction, downloaded, total):
        piper_download_progress.value = fraction
        piper_download_status.value = (
            f"Загрузка Piper: {downloaded / 1024 / 1024:.1f} / "
            f"{total / 1024 / 1024:.1f} МБ"
        )
        piper_download_progress.update()
        piper_download_status.update()

    async def download_piper_voice(_):
        voice_name = piper_voice_dropdown.value
        piper_download_progress.visible = True
        piper_download_progress.value = 0
        piper_download_status.value = "Получаю метаданные целостности голоса…"
        page.update()
        loop = asyncio.get_running_loop()

        def progress_callback(downloaded, total):
            loop.call_soon_threadsafe(
                update_piper_progress,
                downloaded / total if total else None,
                downloaded,
                total,
            )

        try:
            await asyncio.to_thread(install_voice, voice_name, progress_callback)
        except Exception as error:
            logging.exception("Не удалось установить голос Piper")
            piper_download_status.value = f"Ошибка установки: {error}"
            show_config_message(f"Не удалось установить голос Piper: {error}")
        else:
            tts_engine_dropdown.value = f"piper:{voice_name}"
            tts_engine_dropdown.update()
            piper_download_progress.value = 1
            piper_download_status.value = "Голос установлен и проверен."
            show_config_message(
                "Голос Piper установлен. Нажмите SAVE CONFIG, чтобы выбрать его."
            )
        finally:
            piper_download_progress.visible = False
            piper_download_progress.update()
            piper_download_status.update()
    piper_voice_dropdown.on_change = refresh_piper_status

    def move_panel(panel, event):
        if not panel.visible:
            return
        panel.top = min(80, max(0, panel.top + event.delta_y))
        panel.left = min(40, max(0, panel.left + event.delta_x))
        panel.update()

    def panel_header(title, drag_handler, close_handler):
        drag_region = ft.GestureDetector(
            content=ft.Container(
                content=ft.Text(title, color=CYAN, weight="bold", size=16),
                padding=ft.padding.symmetric(vertical=8, horizontal=4),
                expand=True,
            ),
            mouse_cursor=ft.MouseCursor.MOVE,
            on_pan_update=drag_handler,
        )
        return ft.Row(
            [
                drag_region,
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_color="white",
                    tooltip="Закрыть вкладку",
                    on_click=close_handler,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def refresh_ollama_models(e=None, notify=True):
        try:
            chat_models, vision_models = list_models(refresh=True)
        except Exception as error:
            ollama_status.value = f"Ollama пока недоступна: {error}"
            ollama_status.update()
            if notify:
                show_config_message(f"Не удалось получить модели Ollama: {error}")
            return

        chat_options = model_catalog_options("chat", chat_models)
        vision_options = model_catalog_options("vision", vision_models)
        chat_model_dropdown.options = [
            ft.dropdown.Option(AUTO_MODEL),
            *[
                ft.dropdown.Option(key=option["name"], text=option["label"])
                for option in chat_options
            ],
        ]
        vision_model_dropdown.options = [
            ft.dropdown.Option(AUTO_MODEL),
            *[
                ft.dropdown.Option(key=option["name"], text=option["label"])
                for option in vision_options
            ],
        ]
        chat_model_dropdown.update()
        vision_model_dropdown.update()
        ollama_status.value = (
            f"Найдено моделей: {len(chat_models)} для чата, "
            f"{len(vision_models)} с vision."
        )
        ollama_status.update()
        if notify:
            show_config_message(ollama_status.value)

    def download_ollama_model(model_dropdown):
        model_name = (model_dropdown.value or "").strip()
        if not model_name or model_name == AUTO_MODEL:
            show_config_message("Сначала выберите конкретную модель для загрузки.")
            return
        try:
            start_model_download(model_name)
        except (ValueError, OSError) as error:
            show_config_message(f"Не удалось запустить загрузку модели: {error}")
            return
        show_config_message(
            f"Загрузка {model_name} открыта в отдельном окне CMD. "
            "После завершения нажмите «Обновить модели»."
        )

    def save_and_close(e):
        if (
            (tts_engine_dropdown.value or "").startswith("piper:")
            and not is_voice_installed(tts_engine_dropdown.value.partition(":")[2])
        ):
            show_config_message(
                "Сначала скачайте выбранный голос Piper в этом окне настроек."
            )
            return
        save_settings(
            api_input.value, prompt_input.value, in_dev_dropdown.value, out_dev_dropdown.value, pv_key_input.value,
            wake_word_dropdown.value, ai_provider_dropdown.value, tts_engine_dropdown.value,
            ui_lang_dropdown.value, response_lang_dropdown.value,
            chat_model_dropdown.value or AUTO_MODEL, vision_model_dropdown.value or AUTO_MODEL,
            screen_monitor_dropdown.value or str(primary_monitor["index"]),
        )
        set_voice(tts_engine_dropdown.value)
        toggle_config(False)

    config_window = ft.Container(
        content=ft.Column([
            ft.Column([
                panel_header(
                    "CORE CONFIG",
                    lambda event: move_panel(config_window, event),
                    lambda _: toggle_config(False),
                ),
                ft.Divider(color="white24"),
                api_input,
                pv_key_input,
                prompt_input,
                in_dev_dropdown,
                out_dev_dropdown,
                wake_word_dropdown,
                ai_provider_dropdown,
                hardware_summary,
                chat_model_dropdown,
                vision_model_dropdown,
                ollama_status,
                ft.Text(
                    "Модели в списке — от компактных до крупных; рядом указана "
                    "примерная VRAM. Нажмите ⬇ у выбранной модели, чтобы скачать "
                    "её через Ollama. «Авто» выбирает установленную модель.",
                    size=11,
                    color="white54",
                ),
                ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        tooltip="Скачать выбранную модель чата",
                        on_click=lambda _: download_ollama_model(chat_model_dropdown),
                    ),
                ]),
                ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        tooltip="Скачать выбранную vision-модель",
                        on_click=lambda _: download_ollama_model(vision_model_dropdown),
                    ),
                ]),
                ft.OutlinedButton(
                    "Обновить список моделей Ollama",
                    on_click=refresh_ollama_models,
                ),
                screen_monitor_dropdown,
                tts_engine_dropdown,
                piper_voice_dropdown,
                ft.ElevatedButton(
                    "Скачать голос Piper",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=download_piper_voice,
                ),
                piper_download_status,
                piper_download_progress,
                ui_lang_dropdown,
                response_lang_dropdown,
            ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True),
            ft.ElevatedButton("SAVE CONFIG", on_click=save_and_close, bgcolor=CYAN, color="black", width=350, height=45)
        ], opacity=0, animate_opacity=300, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        width=0, height=0,
        bgcolor=ft.Colors.with_opacity(0.82, "#171b28"),
        border=ft.border.all(1, "white24"),
        border_radius=24, blur=30,
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black"),
        padding=20
    )

    # --- Элементы управления чатом ---
    chat_list = ft.Column(spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)
    chat_input = ft.TextField(hint_text="Напишите сообщение...", expand=True, border_color="white24", text_size=14, color="white", on_submit=lambda e: send_chat_message(e))
    voice_stream_state = {"assistant_text": None, "active": False}
    chat_cancel_state = {"event": None}

    def cancel_current_responses():
        cancellation = chat_cancel_state["event"]
        if cancellation is not None:
            cancellation.cancel()
        if voice_assistant_instance is not None:
            voice_assistant_instance.cancel_response()

    chat_cancel_button = ft.IconButton(
        icon=ft.Icons.STOP_CIRCLE_OUTLINED,
        icon_color="#ff7b86",
        tooltip="Остановить ответ",
        disabled=True,
        on_click=lambda _: cancel_current_responses(),
    )
    
    def render_message(role, text):
        is_user = role == 'user'
        message_text = ft.Text(text, color="white" if is_user else "#e0e0e0", size=13)
        bubble = ft.Container(
            content=message_text,
            bgcolor="#2b5278" if is_user else "#25252e",
            border_radius=ft.border_radius.only(
                top_left=15, top_right=15,
                bottom_left=15 if is_user else 0,
                bottom_right=0 if is_user else 15
            ),
            padding=12,
            width=250
        )
        controls = [bubble]
        if not is_user:
            controls.append(
                ft.IconButton(
                    icon=ft.Icons.VOLUME_UP_ROUNDED,
                    icon_color=CYAN,
                    tooltip="Озвучить / Speak",
                    on_click=lambda _: listen.speak(message_text.value)
                )
            )
        return ft.Row(
            controls=controls,
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
        )

    def load_chat_history():
        chat_list.controls.clear()
        memory = load_memory()
        for msg in memory:
            chat_list.controls.append(render_message(msg['role'], msg['content']))
        chat_list.update()

    def show_voice_user_message(text):
        voice_stream_state["active"] = True
        chat_cancel_button.disabled = False
        chat_cancel_button.update()
        chat_list.controls.append(render_message("user", text))
        assistant_message = render_message("assistant", "")
        chat_list.controls.append(assistant_message)
        voice_stream_state["assistant_text"] = assistant_message.controls[0].content
        chat_list.update()

    def show_voice_response_chunk(chunk):
        assistant_text = voice_stream_state["assistant_text"]
        if assistant_text is None:
            return
        assistant_text.value += chunk
        chat_list.update()

    def finish_voice_response(response):
        assistant_text = voice_stream_state["assistant_text"]
        voice_stream_state["active"] = False
        if assistant_text is not None:
            assistant_text.value = response
            voice_stream_state["assistant_text"] = None
            chat_list.update()
        chat_cancel_button.disabled = chat_cancel_state["event"] is None
        chat_cancel_button.update()

    def send_chat_message(e, inspect_screen=False):
        text = "Что сейчас отображено на экране?" if inspect_screen else chat_input.value
        if not text: return
        
        chat_list.controls.append(render_message('user', text))
        chat_input.value = ""
        chat_input.focus()
        chat_list.update()

        cancellation = listen.ResponseCancellation()
        chat_cancel_state["event"] = cancellation
        chat_cancel_button.disabled = False
        chat_cancel_button.update()

        def get_ai_response():
            typing_indicator = ft.Row([ft.Text("Люми думает...", size=10, color="white54")], alignment="start")
            chat_list.controls.append(typing_indicator)
            chat_list.update()
            assistant_text = None

            try:
                screen_image = None
                if inspect_screen:
                    from command_OCR import get_screen_image
                    screen_image = get_screen_image()
                assistant_message = render_message("assistant", "")
                chat_list.controls.remove(typing_indicator)
                chat_list.controls.append(assistant_message)
                assistant_text = assistant_message.controls[0].content
                streamed_parts = []

                def append_response_chunk(chunk):
                    streamed_parts.append(chunk)
                    assistant_text.value += chunk
                    chat_list.update()

                response = process_text_query(
                    text,
                    screen_image=screen_image,
                    on_delta=append_response_chunk,
                    cancel_event=cancellation,
                )
                if not streamed_parts:
                    assistant_text.value = response
                elif "".join(streamed_parts) != response:
                    assistant_text.value = response
            except listen.ResponseCancelled:
                if assistant_text is not None:
                    assistant_text.value = "Ответ остановлен."
            except Exception as error:
                response = f"Не удалось получить ответ: {error}"
                if typing_indicator in chat_list.controls:
                    chat_list.controls.remove(typing_indicator)
                    chat_list.controls.append(render_message("assistant", response))
            finally:
                if chat_cancel_state["event"] is cancellation:
                    chat_cancel_state["event"] = None
                chat_cancel_button.disabled = not voice_stream_state["active"]
                chat_cancel_button.update()
            chat_list.update()

        threading.Thread(target=get_ai_response, daemon=True).start()

    chat_window = ft.Container(
        content=ft.Column([
            ft.Column([
                panel_header(
                    "NEURAL CHAT",
                    lambda event: move_panel(chat_window, event),
                    lambda _: toggle_chat(False),
                ),
                ft.Divider(color="white24"),
            ]),
            chat_list,
            ft.Row([
                chat_input,
                chat_cancel_button,
                ft.IconButton(
                    icon=ft.Icons.VISIBILITY,
                    icon_color=CYAN,
                    tooltip="Спросить об экране",
                    on_click=lambda e: send_chat_message(e, inspect_screen=True),
                ),
                ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=CYAN, on_click=send_chat_message)
            ], alignment="center")
        ], opacity=0, animate_opacity=300),
        width=0, height=0,
        bgcolor=ft.Colors.with_opacity(0.82, "#171b28"),
        border=ft.border.all(1, "white24"),
        border_radius=24, blur=30,
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black"),
        padding=20
    )

    skill_name_input = ft.TextField(
        label="Название навыка",
        max_length=60,
        border_color="white24",
        text_size=12,
        visible=False,
    )
    skill_description_input = ft.TextField(
        label="Описание / инструкции",
        multiline=True,
        min_lines=2,
        max_lines=3,
        max_length=500,
        border_color="white24",
        text_size=12,
        visible=False,
    )
    skill_executable_input = ft.TextField(
        label="Путь к своему .exe (необязательно)",
        hint_text=r"C:\Apps\MyApp\MyApp.exe",
        border_color="white24",
        text_size=12,
        visible=False,
    )
    skills_list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    screensage_status = ft.Text(size=11, color="white54")
    screensage_autostart = ft.Switch(
        label="Запускать вместе с LUMI",
        value=screensage.is_autostart_enabled(),
        disabled=not screensage.is_installed(),
        on_change=lambda e: screensage.set_autostart_enabled(e.control.value),
    )
    add_skill_button = ft.IconButton(
        icon=ft.Icons.ADD_CIRCLE_OUTLINE,
        icon_color=CYAN,
        tooltip="Добавить свой навык",
        on_click=lambda _: show_skill_editor(True),
    )
    skill_form = ft.Column(
        [
            skill_name_input,
            skill_description_input,
            skill_executable_input,
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Добавить",
                        icon=ft.Icons.ADD,
                        on_click=lambda e: add_skill(e),
                        bgcolor="#33465e",
                        color="white",
                    ),
                    ft.TextButton(
                        "Отмена",
                        on_click=lambda _: show_skill_editor(False),
                    ),
                ],
                spacing=8,
            ),
        ],
        spacing=8,
        visible=False,
    )

    def show_skill_editor(visible):
        skill_name_input.visible = visible
        skill_description_input.visible = visible
        skill_executable_input.visible = visible
        skill_form.visible = visible
        add_skill_button.visible = not visible
        skill_name_input.update()
        skill_description_input.update()
        skill_executable_input.update()
        skill_form.update()
        add_skill_button.update()

    def refresh_skills():
        skills_list.controls = [ft.Text("ПРОВЕРЕННЫЕ", color=CYAN, size=10, weight="bold")]
        skills_list.controls.extend([
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(skill["name"], color="white", weight="bold"),
                                ft.Text(
                                    skill["description"],
                                    color="white54",
                                    size=11,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.OutlinedButton("Встроен", disabled=True),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment="center",
                ),
                padding=12,
                bgcolor="white10",
                border=ft.border.all(1, "white12"),
                border_radius=16,
            )
            for skill in DEVELOPER_SKILLS
        ])
        skills_list.controls.append(
            ft.Row(
                [
                    ft.Text("СООБЩЕСТВО", color=CYAN, size=10, weight="bold"),
                    add_skill_button,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment="center",
            )
        )
        for skill in list_user_skills():
            skills_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(skill["name"], color="white", weight="bold"),
                                    ft.Text(
                                        skill["description"],
                                        color="white54",
                                        size=11,
                                    ),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color="white54",
                                tooltip="Удалить навык",
                                on_click=lambda _, skill_id=skill["id"]: delete_skill(
                                    skill_id
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment="center",
                    ),
                    padding=12,
                    bgcolor="white10",
                    border=ft.border.all(1, "white12"),
                    border_radius=16,
                )
            )
        if screensage.is_installed():
            screensage_status.value = (
                f"Установлен: {screensage.executable_path()}"
            )
            screensage_autostart.disabled = False
            screensage_autostart.value = screensage.is_autostart_enabled()
        else:
            screensage_status.value = (
                "Windows EXE скачивается только по кнопке. "
                "SHA-256 сверяется с GitHub Releases."
            )
            screensage_autostart.disabled = True
            screensage_autostart.value = False
        skills_list.controls.insert(
            1 + len(DEVELOPER_SKILLS),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            "ScreenSage",
                                            color="white",
                                            weight="bold",
                                        ),
                                        ft.Text(
                                            "Анализ выделенной области экрана.",
                                            color="white54",
                                            size=11,
                                        ),
                                    ],
                                    expand=True,
                                    spacing=4,
                                ),
                                ft.ElevatedButton(
                                    "Установить",
                                    icon=ft.Icons.DOWNLOAD,
                                    bgcolor="#2388ff",
                                    color="white",
                                    visible=not screensage.is_installed(),
                                    on_click=install_screensage,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        screensage_status,
                        ft.Row(
                            [
                                ft.TextButton(
                                    "GitHub",
                                    icon=ft.Icons.OPEN_IN_NEW,
                                    on_click=lambda _: webbrowser.open(
                                        screensage.GITHUB_PAGE
                                    ),
                                    visible=screensage.is_installed(),
                                ),
                                ft.IconButton(
                                    ft.Icons.PLAY_ARROW_ROUNDED,
                                    icon_color="#59a7ff",
                                    tooltip="Запустить ScreenSage сейчас",
                                    visible=screensage.is_installed(),
                                    on_click=launch_screensage,
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    icon_color="white54",
                                    tooltip="Удалить ScreenSage",
                                    visible=screensage.is_installed(),
                                    on_click=remove_screensage,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                        screensage_autostart,
                        ft.Text(
                            "Файл запускается только вручную или после вашего "
                            "включения автозапуска. Перед запуском изучите проект.",
                            color="white38",
                            size=10,
                        ),
                    ],
                    spacing=6,
                ),
                padding=12,
                bgcolor=ft.Colors.with_opacity(0.48, "#23334a"),
                border=ft.border.all(1, "white24"),
                border_radius=16,
            )
        )
        skills_list.update()

    def add_skill(e):
        try:
            add_user_skill(
                skill_name_input.value,
                skill_description_input.value,
                skill_executable_input.value,
            )
        except ValueError as error:
            show_config_message(str(error))
            return
        except Exception:
            logging.exception("Не удалось сохранить пользовательский навык")
            show_config_message("Не удалось сохранить навык.")
            return
        skill_name_input.value = ""
        skill_description_input.value = ""
        skill_executable_input.value = ""
        show_skill_editor(False)
        refresh_skills()
        show_config_message("Навык сохранён на этом компьютере.")

    def delete_skill(skill_id):
        try:
            remove_user_skill(skill_id)
        except ValueError as error:
            show_config_message(str(error))
            return
        except Exception:
            logging.exception("Не удалось удалить пользовательский навык")
            show_config_message("Не удалось удалить навык.")
            return
        refresh_skills()
        show_config_message("Навык удалён.")

    def install_screensage(e):
        screensage_status.value = "Загружаю и проверяю SHA-256…"
        screensage_status.update()
        e.control.disabled = True
        e.control.update()

        def worker():
            try:
                installed_path = screensage.download_latest()
            except Exception as error:
                logging.exception("Не удалось установить ScreenSage")
                screensage_status.value = f"Ошибка установки: {error}"
            else:
                screensage_status.value = (
                    f"Проверенный файл сохранён: {installed_path}"
                )
            finally:
                refresh_skills()
                page.update()

        threading.Thread(target=worker, daemon=True).start()

    def launch_screensage(e=None):
        try:
            screensage.launch()
        except Exception as error:
            logging.exception("Не удалось запустить ScreenSage")
            show_config_message(f"Не удалось запустить ScreenSage: {error}")

    def remove_screensage(e=None):
        try:
            screensage.remove()
        except Exception as error:
            logging.exception("Не удалось удалить ScreenSage")
            show_config_message(f"Не удалось удалить ScreenSage: {error}")
            return
        refresh_skills()
        show_config_message("ScreenSage удалён.")

    skills_window = ft.Container(
        content=ft.Column(
            [
                panel_header(
                    "НАВЫКИ",
                    lambda event: move_panel(skills_window, event),
                    lambda _: toggle_skills(False),
                ),
                ft.Text(
                    "Ваши локальные навыки и каталог от разработчика.",
                    color="white54",
                    size=11,
                ),
                skills_list,
                ft.Divider(color="white24"),
                skill_form,
                ft.Text(
                    "Навыки добавляют инструкции модели. Можно привязать EXE: "
                    "он откроется только по явной голосовой просьбе. "
                    "Команды экрана/клавиш выполняются только по просьбе.",
                    color="white38",
                    size=10,
                ),
            ],
            spacing=10,
            expand=True,
            opacity=0,
            animate_opacity=300,
        ),
        width=0,
        height=0,
        bgcolor=ft.Colors.with_opacity(0.82, "#171b28"),
        border=ft.border.all(1, "white24"),
        border_radius=24,
        blur=30,
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300,
        left=200,
        visible=False,
        shadow=ft.BoxShadow(blur_radius=50, color="black"),
        padding=18,
    )

    # --- Функции переключения окон ---
    def toggle_config(expand):
        if expand:
            toggle_chat(False)
        state["is_config_open"] = expand
        if expand:
            config_window.visible = True
            config_window.width, config_window.height = 360, 520
            config_window.top, config_window.left = 40, 20
            config_window.content.opacity = 1
        else:
            config_window.width, config_window.height = 0, 0
            config_window.top, config_window.left = 300, 200
            config_window.content.opacity = 0
            config_window.visible = True
        page.update()

    def toggle_chat(expand):
        if expand:
            toggle_config(False)
        state["is_chat_expanded"] = expand
        if expand:
            load_chat_history()
            chat_window.visible = True
            chat_window.width, chat_window.height = 360, 500
            chat_window.top, chat_window.left = 50, 20
            chat_window.content.opacity = 1
        else:
            chat_window.width, chat_window.height = 0, 0
            chat_window.top, chat_window.left = 300, 200
            chat_window.content.opacity = 0
            chat_window.visible = True
        page.update()

    def toggle_skills(expand):
        if expand:
            toggle_config(False)
            toggle_chat(False)
            refresh_skills()
        state["is_skills_open"] = expand
        skills_window.visible = True
        if expand:
            skills_window.width, skills_window.height = 360, 520
            skills_window.top, skills_window.left = 40, 20
            skills_window.content.opacity = 1
        else:
            skills_window.width, skills_window.height = 0, 0
            skills_window.top, skills_window.left = 300, 200
            skills_window.content.opacity = 0
        page.update()

    # --- Кнопки-сателлиты ---
    button_animation = ft.Animation(350, ft.AnimationCurve.EASE_OUT)
    btn_chat = ft.Container(
        content=ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINED, color="white"),
        width=60, height=60, bgcolor="white10", border=ft.border.all(1, "white24"),
        border_radius=18, blur=14, animate_position=button_animation,
        animate_scale=button_animation, top=CENTER_Y+10, left=CENTER_X+10,
        scale=0, on_click=open_chat_window,
    )
    btn_tools = ft.Container(
        content=ft.Icon(ft.Icons.AUTO_FIX_HIGH, color="white"),
        width=60, height=60, bgcolor="white10", border=ft.border.all(1, "white24"),
        border_radius=18, blur=14, animate_position=button_animation,
        animate_scale=button_animation, top=CENTER_Y+10, left=CENTER_X+10,
        scale=0, tooltip="Навыки", on_click=open_skills_window,
    )
    
    def start_voice_assistant(assistant):
        global voice_assistant_instance
        try:
            assistant.start()
        except Exception:
            logging.exception("Не удалось запустить голосовой ввод")
            assistant.stop()
            state["is_voice_active"] = False
            if voice_assistant_instance is assistant:
                voice_assistant_instance = None
            btn_mic.content.color = "white"
            btn_mic.bgcolor = "white10"
            page.update()

    def ensure_local_ollama():
        try:
            ensure_ollama_running()
            refresh_ollama_models(notify=False)
        except Exception as error:
            logging.exception("Не удалось запустить локальный сервер Ollama")
            show_config_message(f"Не удалось запустить Ollama: {error}")

    def toggle_mic_state(e):
        global voice_assistant_instance
        if state["voice_preparing"]:
            show_config_message("Голосовое управление ещё подготавливается.")
            return

        state["is_voice_active"] = not state["is_voice_active"]
        
        btn_mic.content.color = CYAN if state["is_voice_active"] else "white"
        btn_mic.bgcolor = "white24" if state["is_voice_active"] else "white10"
        btn_mic.update()

        if state["is_voice_active"]:
            try:
                if voice_assistant_instance is None:
                    voice_assistant_instance = VoiceAssistant(
                        input_device=in_dev_dropdown.value,
                        on_user_text=show_voice_user_message,
                        on_response_chunk=show_voice_response_chunk,
                        on_response_complete=finish_voice_response,
                    )
                threading.Thread(
                    target=start_voice_assistant,
                    args=(voice_assistant_instance,),
                    daemon=True,
                ).start()
            except Exception:
                logging.exception("Не удалось инициализировать голосовой ввод")
                state["is_voice_active"] = False
                voice_assistant_instance = None
                btn_mic.content.color = "white"
                btn_mic.bgcolor = "white10"
                btn_mic.update()
        else:
            if voice_assistant_instance:
                voice_assistant_instance.stop()
                voice_assistant_instance = None

    btn_mic = ft.Container(
        content=ft.Icon(ft.Icons.MIC_NONE_ROUNDED, color="white"),
        width=60, height=60, bgcolor="white10", border=ft.border.all(1, "white24"),
        border_radius=18, blur=14, animate_position=button_animation,
        animate_scale=button_animation, top=CENTER_Y+10, left=CENTER_X+10,
        scale=0, on_click=toggle_mic_state,
    )
    btn_cfg = ft.Container(
        content=ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="white"),
        width=60, height=60, bgcolor="white10", border=ft.border.all(1, "white24"),
        border_radius=18, blur=14, animate_position=button_animation,
        animate_scale=button_animation, top=CENTER_Y+10, left=CENTER_X+10,
        scale=0, on_click=lambda _: toggle_config(True),
    )

    satellites = [btn_chat, btn_tools, btn_mic, btn_cfg]

    def toggle_menu(e):
        state["is_menu_open"] = not state["is_menu_open"]
        core.content.scale = 1.2 if state["is_menu_open"] else 1.0
        
        # Распределяем кнопки по углам (225, 315, 135, 45 градусов или крестом)
        angles = [270, 0, 90, 180] 
        for i, btn in enumerate(satellites):
            if state["is_menu_open"]:
                angle_rad = math.radians(angles[i])
                btn.top = CENTER_Y + 10 + RADIUS * math.sin(angle_rad)
                btn.left = CENTER_X + 10 + RADIUS * math.cos(angle_rad)
                btn.scale = 1
            else:
                btn.top = CENTER_Y + 10
                btn.left = CENTER_X + 10
                btn.scale = 0
            btn.update()
        core.update()

    core = ft.GestureDetector(
        on_tap=toggle_menu,
        content=ft.Container(
            content=ft.Icon(ft.Icons.FINGERPRINT, size=40, color=CYAN),
        width=80, height=80,
        bgcolor=ft.Colors.with_opacity(0.72, "#1a2130"),
        border=ft.border.all(1, "white24"),
        border_radius=40, alignment=ft.alignment.center, blur=12,
            shadow=ft.BoxShadow(spread_radius=5, blur_radius=25, color=CYAN_GLOW),
            animate_scale=ft.Animation(300, ft.AnimationCurve.BOUNCE_OUT)
        )
    )

    # --- Стек слоев ---
    main_stack = ft.Stack([
        wave2, wave1,
        btn_tools, btn_mic, btn_chat, btn_cfg,
        ft.Container(core, top=CENTER_Y, left=CENTER_X),
        config_window,
        chat_window,
        ft.Container(ft.Text("LUMI AI 2.0", size=10, color="white24", weight="bold"), bottom=20, left=160)
    ], expand=True, opacity=0, animate_opacity=1000)

    loading_screen = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.SHIELD_OUTLINED, size=60, color=CYAN),
            ft.Container(height=20),
            ft.Text("SYNCHRONIZING...", size=14, color=CYAN, weight="bold")
        ], alignment="center", horizontal_alignment="center"),
        width=400, height=600, bgcolor="#0b0e17", animate_opacity=800
    )

    page.add(ft.Stack([main_stack, loading_screen], expand=True))
    refresh_piper_status()

    def prepare_voice_assistant():
        global voice_assistant_instance
        try:
            voice_assistant_instance = VoiceAssistant(
                input_device=saved_in,
                on_user_text=show_voice_user_message,
                on_response_chunk=show_voice_response_chunk,
                on_response_complete=finish_voice_response,
            )
            voice_assistant_instance.prepare()
            state["voice_preparation_error"] = None
            logging.info("Голосовое управление подготовлено к активации")
        except Exception as error:
            state["voice_preparation_error"] = str(error)
            logging.exception("Не удалось заранее подготовить голосовое управление")
        finally:
            state["voice_preparing"] = False
            btn_mic.tooltip = (
                "Голосовое управление"
                if state["voice_preparation_error"] is None
                else "Подготовка голосового управления не удалась"
            )
            btn_mic.update()

    threading.Thread(
        target=prepare_voice_assistant,
        daemon=True,
        name="voice-assistant-preload",
    ).start()

    def run_loading():
        time.sleep(1.2)
        loading_screen.opacity = 0
        loading_screen.update()
        time.sleep(0.8)
        loading_screen.visible = False
        main_stack.opacity = 1
        page.update()
        threading.Thread(target=pulse_waves_logic, daemon=True).start()

    threading.Thread(target=run_loading, daemon=True).start()

    page.update()
    if screensage.is_autostart_enabled():
        if screensage.is_installed():
            threading.Thread(
                target=launch_screensage,
                daemon=True,
                name="screensage-autostart",
            ).start()
        else:
            screensage.set_autostart_enabled(False)
            logging.warning(
                "Автозапуск ScreenSage отключён: установленный EXE не найден."
            )
    if saved_ai.casefold().startswith("ollama"):
        threading.Thread(
            target=ensure_local_ollama,
            daemon=True,
            name="ollama-server-startup",
        ).start()
    else:
        threading.Thread(
            target=lambda: refresh_ollama_models(notify=False),
            daemon=True,
        ).start()

if __name__ == "__main__":
    if "--skills-window" in sys.argv:
        import skills_window

        ft.app(target=skills_window.main)
    elif "--chat-window" in sys.argv:
        import chat_window

        ft.app(target=chat_window.main)
    else:
        ft.app(target=main)
