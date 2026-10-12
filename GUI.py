import flet as ft
import sqlite3
import sounddevice as sd
import math
import os
import time
import threading
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
    DEFAULT_VISION_MODEL,
    list_models,
    start_model_download,
)

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

try:
    myappid = 'lumi.ai.assistant.2.0' # Любая уникальная строка
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass


def handle_window_event(page, event):
    if event.data == "close":
        logging.info("Окно скрывается в системный трей")
        page.window.visible = False
        page.update()
    elif event.data == "minimize":
        page.window.visible = False
        page.update()
    elif event.data == "restore":
        page.window.visible = True
        page.update()


def main(page: ft.Page):
    init_db()
    icon_path = str(resource_path("app_icon.ico"))

    # --- 3. НАСТРОЙКА ТРЕЯ (Справа внизу) ---
    def quit_app(icon, item):
        icon.stop()
        if voice_assistant_instance is not None:
            voice_assistant_instance.stop()
        page.window.prevent_close = False
        page.window.destroy()

    def show_app(icon, item):
        page.window.visible = True
        page.window.minimized = False
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

    page.on_window_event = on_window_event

    # --- Конфигурация окна ---
    page.title = "LUMI AI"
    page.window.prevent_close = True
    if os.path.exists(icon_path):
        page.window.icon = icon_path
    
    page.window.width = 400
    page.window.height = 600
    page.window.resizable = False
    page.window.maximizable = False
    page.window.always_on_top = True

    try:
        if hasattr(page.window, "center"):
            page.run_task(page.window.center)
    except Exception:
        pass
    
    page.bgcolor = "#0f0f13"
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
        "running": True
    }

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
    wake_word_dropdown = ft.Dropdown(label="АКТИВАЦИЯ ГОЛОСА", options=[ft.dropdown.Option(d) for d in ["Ручной режим без ключа", "Porcupine"]], border_color="white24", value=saved_wake or "Ручной режим без ключа", text_size=12)
    ai_options = ["Ollama (локально)", "Mistral API"]
    selected_ai = saved_ai if saved_ai in ai_options else "Ollama (локально)"
    ai_provider_dropdown = ft.Dropdown(label="AI PROVIDER", options=[ft.dropdown.Option(d) for d in ai_options], border_color="white24", value=selected_ai, text_size=12)
    chat_model_dropdown = ft.Dropdown(
        label="МОДЕЛЬ ДЛЯ ЧАТА",
        options=[ft.dropdown.Option(AUTO_MODEL), ft.dropdown.Option(saved_chat_model)]
        if saved_chat_model and saved_chat_model != AUTO_MODEL
        else [ft.dropdown.Option(AUTO_MODEL)],
        value=saved_chat_model or AUTO_MODEL,
        border_color="white24",
        text_size=12,
    )
    vision_model_dropdown = ft.Dropdown(
        label="VISION-МОДЕЛЬ ДЛЯ АНАЛИЗА ЭКРАНА",
        options=[ft.dropdown.Option(AUTO_MODEL), ft.dropdown.Option(saved_vision_model)]
        if saved_vision_model and saved_vision_model != AUTO_MODEL
        else [ft.dropdown.Option(AUTO_MODEL)],
        value=saved_vision_model or AUTO_MODEL,
        border_color="white24",
        text_size=12,
    )
    chat_download_input = ft.TextField(
        label="Скачать модель для чата",
        value=DEFAULT_CHAT_MODEL,
        border_color="white24",
        text_size=12,
    )
    vision_download_input = ft.TextField(
        label="Скачать модель с поддержкой изображений",
        value=DEFAULT_VISION_MODEL,
        border_color="white24",
        text_size=12,
    )
    tts_options = ["Silero (Ксения)", "Системный женский голос"]
    tts_engine_dropdown = ft.Dropdown(
        label="ГОЛОС ОТВЕТА",
        options=[ft.dropdown.Option(value) for value in tts_options],
        border_color="white24",
        value=saved_tts if saved_tts in tts_options else tts_options[0],
        text_size=12,
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

    def refresh_ollama_models(e=None):
        try:
            chat_models, vision_models = list_models(refresh=True)
        except Exception as error:
            show_config_message(f"Не удалось получить модели Ollama: {error}")
            return

        chat_model_dropdown.options = [
            ft.dropdown.Option(AUTO_MODEL),
            *[ft.dropdown.Option(model) for model in chat_models],
        ]
        vision_model_dropdown.options = [
            ft.dropdown.Option(AUTO_MODEL),
            *[ft.dropdown.Option(model) for model in vision_models],
        ]
        if chat_model_dropdown.value not in [AUTO_MODEL, *chat_models]:
            chat_model_dropdown.value = AUTO_MODEL
        if vision_model_dropdown.value not in [AUTO_MODEL, *vision_models]:
            vision_model_dropdown.value = AUTO_MODEL
        chat_model_dropdown.update()
        vision_model_dropdown.update()
        show_config_message(
            f"Найдено моделей: {len(chat_models)} для чата, "
            f"{len(vision_models)} с vision."
        )

    def download_ollama_model(model_input):
        model_name = (model_input.value or "").strip()
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
                ft.Row([ft.Text("CORE CONFIG", color=CYAN, weight="bold", size=16), ft.IconButton(ft.Icons.CLOSE, icon_color="white", on_click=lambda _: toggle_config(False))], alignment="spaceBetween"),
                ft.Divider(color="white24"),
                api_input,
                pv_key_input,
                prompt_input,
                in_dev_dropdown,
                out_dev_dropdown,
                wake_word_dropdown,
                ai_provider_dropdown,
                chat_model_dropdown,
                vision_model_dropdown,
                ft.Text(
                    "«Авто» выбирает установленную модель. Vision-модель используется "
                    "только для анализа изображения экрана.",
                    size=11,
                    color="white54",
                ),
                ft.Row([
                    chat_download_input,
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        tooltip="Скачать модель в отдельном CMD",
                        on_click=lambda _: download_ollama_model(chat_download_input),
                    ),
                ]),
                ft.Row([
                    vision_download_input,
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        tooltip="Скачать vision-модель в отдельном CMD",
                        on_click=lambda _: download_ollama_model(vision_download_input),
                    ),
                ]),
                ft.OutlinedButton(
                    "Обновить список моделей Ollama",
                    on_click=refresh_ollama_models,
                ),
                screen_monitor_dropdown,
                tts_engine_dropdown,
                ui_lang_dropdown,
                response_lang_dropdown,
            ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True),
            ft.ElevatedButton("SAVE CONFIG", on_click=save_and_close, bgcolor=CYAN, color="black", width=350, height=45)
        ], opacity=0, animate_opacity=300, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        width=0, height=0, bgcolor="#12121a", border_radius=20, blur=25, 
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black"),
        padding=20
    )

    # --- Элементы управления чатом ---
    chat_list = ft.Column(spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)
    chat_input = ft.TextField(hint_text="Напишите сообщение...", expand=True, border_color="white24", text_size=14, color="white", on_submit=lambda e: send_chat_message(e))
    voice_stream_state = {"assistant_text": None}
    
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
        if assistant_text is not None:
            assistant_text.value = response
            voice_stream_state["assistant_text"] = None
            chat_list.update()

    def send_chat_message(e, inspect_screen=False):
        text = "Что сейчас отображено на экране?" if inspect_screen else chat_input.value
        if not text: return
        
        chat_list.controls.append(render_message('user', text))
        chat_input.value = ""
        chat_input.focus()
        chat_list.update()

        def get_ai_response():
            typing_indicator = ft.Row([ft.Text("Люми думает...", size=10, color="white54")], alignment="start")
            chat_list.controls.append(typing_indicator)
            chat_list.update()

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
                )
                if not streamed_parts:
                    assistant_text.value = response
                elif "".join(streamed_parts) != response:
                    assistant_text.value = response
            except Exception as error:
                response = f"Не удалось прочитать экран: {error}"
                if typing_indicator in chat_list.controls:
                    chat_list.controls.remove(typing_indicator)
                    chat_list.controls.append(render_message("assistant", response))
            chat_list.update()

        threading.Thread(target=get_ai_response, daemon=True).start()

    chat_window = ft.Container(
        content=ft.Column([
            ft.Column([
                ft.Row([ft.Text("NEURAL CHAT", color=CYAN, weight="bold", size=16), ft.IconButton(ft.Icons.CLOSE, icon_color="white", on_click=lambda _: toggle_chat(False))], alignment="spaceBetween"),
                ft.Divider(color="white24"),
            ]),
            chat_list,
            ft.Row([
                chat_input,
                ft.IconButton(
                    icon=ft.Icons.VISIBILITY,
                    icon_color=CYAN,
                    tooltip="Спросить об экране",
                    on_click=lambda e: send_chat_message(e, inspect_screen=True),
                ),
                ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=CYAN, on_click=send_chat_message)
            ], alignment="center")
        ], opacity=0, animate_opacity=300),
        width=0, height=0, bgcolor="#0d0d14", border_radius=20, blur=25,
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black"),
        padding=20
    )

    # --- Функции переключения окон ---
    def toggle_config(expand):
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
            config_window.visible = False
        page.update()

    def toggle_chat(expand):
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
            chat_window.visible = False
        page.update()

    # --- Кнопки-сателлиты ---
    btn_chat = ft.Container(content=ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINED, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, on_click=lambda _: toggle_chat(True))
    btn_tools = ft.Container(content=ft.Icon(ft.Icons.AUTO_FIX_HIGH, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, tooltip="MODS (Dev)")
    
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

    def toggle_mic_state(e):
        global voice_assistant_instance
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

    btn_mic = ft.Container(content=ft.Icon(ft.Icons.MIC_NONE_ROUNDED, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, on_click=toggle_mic_state)
    btn_cfg = ft.Container(content=ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, on_click=lambda _: toggle_config(True))

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
            width=80, height=80, bgcolor="#1a1a24", border_radius=40, alignment=ft.alignment.center,
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
        width=400, height=600, bgcolor="#0f0f13", animate_opacity=800
    )

    page.add(ft.Stack([main_stack, loading_screen], expand=True))

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

if __name__ == "__main__":
    ft.app(target=main)
