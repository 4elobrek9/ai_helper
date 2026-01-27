import flet as ft
import sqlite3
import sounddevice as sd
import math
import os
import time
import threading
import listen 
from listen import VoiceAssistant, process_text_query, load_memory
import ctypes
from PIL import Image
import pystray

# ЗАМЕТКИ ДЛЯ БУДУЩЕГО: 
# Дизайн: Living Shard, 400x600. 
# Волны: Теперь строго по центру и активируются ТОЛЬКО кнопкой микрофона.
# Слои: Окна чата и конфига теперь перекрывают все кнопки и отпечаток.
# БД: Авто-миграция и сохранение/загрузка настроек (API, Prompt, Devices, Porcupine).

def init_db():
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            api_key TEXT,
            prompt TEXT,
            input_device TEXT,
            output_device TEXT,
            porcupine_key TEXT
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
    conn.commit()
    conn.close()

def save_settings(api_key, prompt, input_dev, output_dev, porcupine_key):
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings")
    cursor.execute("INSERT INTO settings (api_key, prompt, input_device, output_device, porcupine_key) VALUES (?, ?, ?, ?, ?)", 
                   (api_key, prompt, input_dev, output_dev, porcupine_key))
    conn.commit()
    conn.close()

def load_settings():
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT api_key, prompt, input_device, output_device, porcupine_key FROM settings LIMIT 1")
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    if row:
        return (
            row[0] if row[0] is not None else "", 
            row[1] if row[1] is not None else "", 
            row[2] if row[2] is not None else None, 
            row[3] if row[3] is not None else None,
            row[4] if row[4] is not None else ""
        )
    return ("", "", None, None, "")

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

def main(page: ft.Page):
    # --- 2. ПУТЬ К ИКОНКЕ ---
    # Получаем полный абсолютный путь к файлу images.jpg в папке со скриптом
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "images.jpg"))

    # --- 3. НАСТРОЙКА ТРЕЯ (Справа внизу) ---
    def quit_app(icon, item):
        icon.stop()
        page.window.destroy()

    def show_app(icon, item):
        page.window.visible = True
        page.window.minimized = False
        page.update()
        page.window.to_front()

    def setup_tray():
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            menu = pystray.Menu(
                pystray.MenuItem("Развернуть LUMI", show_app, default=True),
                pystray.MenuItem("Выход", quit_app)
            )
            tray = pystray.Icon("LUMI AI", img, "LUMI AI", menu)
            tray.run()

    # Сразу запускаем трей в отдельном потоке
    threading.Thread(target=setup_tray, daemon=True).start()

    # --- 4. ЛОГИКА СВОРАЧИВАНИЯ В ТРЕЙ ---
    def on_window_event(e):
        if e.data == "minimize":
            # Скрываем окно совсем (оно исчезает из панели задач, остается в трее)
            page.window.visible = False
            page.update()
        elif e.data == "restore":
            page.window.visible = True
            page.update()

    page.on_window_event = on_window_event

    # --- Конфигурация окна ---
    page.title = "LUMI AI"
    
    # ПРИНУДИТЕЛЬНАЯ УСТАНОВКА ИКОНКИ ОКНА
    if os.path.exists(icon_path):
        page.window.icon = icon_path  # Для самого окна
    
    page.window.width = 400
    page.window.height = 600
    page.window.resizable = False
    page.window.maximizable = False
    page.window.always_on_top = True

    # --- УСТАНОВКА ИКОНКИ ---
    # Указываем путь к иконке (используем абсолютный путь для надежности)
    icon_path = os.path.join(os.path.dirname(__file__), "images.jpg")
    if os.path.exists(icon_path):
        page.window.icon = icon_path  # Это ставит иконку в окно и таскбар
    # -------------------------
    
    try:
        page.window.center()
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

    saved_api, saved_prompt, saved_in, saved_out, saved_pv_key = load_settings()

    # --- Слой анимации (Волны) ---
    class WaveCircle(ft.Container):
        def __init__(self, size=80):
            super().__init__()
            self.width = size
            self.height = size
            self.border_radius = size / 2
            self.border = ft.border.all(2, CYAN)
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

    def save_and_close(e):
        save_settings(api_input.value, prompt_input.value, in_dev_dropdown.value, out_dev_dropdown.value, pv_key_input.value)
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
    
    def render_message(role, text):
        is_user = role == 'user'
        return ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(text, color="white" if is_user else "#e0e0e0", size=13),
                    bgcolor="#2b5278" if is_user else "#25252e",
                    border_radius=ft.border_radius.only(
                        top_left=15, top_right=15, 
                        bottom_left=15 if is_user else 0, 
                        bottom_right=0 if is_user else 15
                    ),
                    padding=12,
                    width=250 # Использование ширины вместо constraints для фикса вылета
                )
            ],
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
        )

    def load_chat_history():
        chat_list.controls.clear()
        memory = load_memory()
        for msg in memory:
            chat_list.controls.append(render_message(msg['role'], msg['content']))
        chat_list.update()

    def send_chat_message(e):
        text = chat_input.value
        if not text: return
        
        chat_list.controls.append(render_message('user', text))
        chat_input.value = ""
        chat_input.focus()
        chat_list.update()

        def get_ai_response():
            # Заглушка ожидания
            typing_indicator = ft.Row([ft.Text("Люми думает...", size=10, color="white54")], alignment="start")
            chat_list.controls.append(typing_indicator)
            chat_list.update()

            response = process_text_query(text)
            
            chat_list.controls.remove(typing_indicator)
            chat_list.controls.append(render_message('assistant', response))
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
    
    def toggle_mic_state(e):
        global voice_assistant_instance
        state["is_voice_active"] = not state["is_voice_active"]
        
        btn_mic.content.color = CYAN if state["is_voice_active"] else "white"
        btn_mic.bgcolor = "white24" if state["is_voice_active"] else "white10"
        btn_mic.update()

        if state["is_voice_active"]:
            if voice_assistant_instance is None:
                voice_assistant_instance = VoiceAssistant()
            threading.Thread(target=voice_assistant_instance.start, daemon=True).start()
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