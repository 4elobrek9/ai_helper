import flet as ft
import sqlite3
import sounddevice as sd
import math
import time
import threading
import json
import listen 
from listen import VoiceAssistant, process_text_query, load_memory

# ЗАМЕТКИ ДЛЯ БУДУЩЕГО: 
# Дизайн: Living Shard, 400x600. 
# Волны: Теперь строго по центру и активируются ТОЛЬКО кнопкой микрофона.
# Слои: Окна чата и конфига теперь перекрывают все кнопки и отпечаток.
# БД: Авто-миграция и сохранение/загрузка настроек (API, Prompt, Devices).

def init_db():
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            api_key TEXT,
            prompt TEXT
        )
    """)
    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    if "input_device" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN input_device TEXT")
    if "output_device" not in columns:
        cursor.execute("ALTER TABLE settings ADD COLUMN output_device TEXT")
    if "porcupine_key" not in columns: # Новое поле для ключа Porcupine
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
        # Обработка случая, если в БД меньше колонок (при старой базе)
        return (row[0] if len(row) > 0 else "", 
                row[1] if len(row) > 1 else "", 
                row[2] if len(row) > 2 else None, 
                row[3] if len(row) > 3 else None,
                row[4] if len(row) > 4 else "")
    return ("", "", None, None, "")

def get_audio_devices(kind='input'):
    try:
        devices = sd.query_devices()
        if kind == 'input':
            devs = [d['name'] for d in devices if d['max_input_channels'] > 0]
        else:
            devs = [d['name'] for d in devices if d['max_output_channels'] > 0]
        return list(dict.fromkeys(devs))
    except:
        return ["Default Device"]

voice_assistant_instance = None

def main(page: ft.Page):
    global voice_assistant_instance
    init_db()
    
    page.title = "LUMI AI "
    page.window.width = 400
    page.window.height = 600
    page.window.resizable = False
    page.window.maximizable = False
    page.window.always_on_top = True
    page.window.center() 
    
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

    # --- Волны ---
    class WaveCircle(ft.Container):
        def __init__(self, size=80):
            super().__init__()
            self.width = size; self.height = size
            self.border_radius = size / 2
            self.border = ft.border.all(2, CYAN)
            self.opacity = 0; self.scale = 1
            self.top = CENTER_Y 
            self.left = CENTER_X 
            self.animate_opacity = ft.Animation(1500, ft.AnimationCurve.EASE_OUT)
            self.animate_scale = ft.Animation(1500, ft.AnimationCurve.EASE_OUT)

    wave1 = WaveCircle(); wave2 = WaveCircle()

    def pulse_waves_logic():
        while state["running"]:
            if state["is_voice_active"]:
                wave1.opacity = 0.5; wave1.scale = 3.5; wave1.update()
                time.sleep(0.8)
                wave2.opacity = 0.3; wave2.scale = 4.5; wave2.update()
                time.sleep(1.2)
                wave1.opacity = 0; wave1.scale = 1.0; wave1.update()
                wave2.opacity = 0; wave2.scale = 1.0; wave2.update()
                time.sleep(0.3)
            else:
                if wave1.opacity > 0 or wave2.opacity > 0:
                    wave1.opacity = 0; wave2.opacity = 0
                    wave1.update(); wave2.update()
                time.sleep(0.5)

    # --- Настройки ---
    api_input = ft.TextField(label="MISTRAL API KEY", password=True, can_reveal_password=True, border_color="white24", value=saved_api, text_size=12)
    pv_key_input = ft.TextField(label="PORCUPINE KEY", password=True, can_reveal_password=True, border_color="white24", value=saved_pv_key, text_size=12) # Поле для Porcupine
    prompt_input = ft.TextField(label="SYSTEM PROMPT", multiline=True, min_lines=3, border_color="white24", value=saved_prompt, text_size=12)
    in_dev_dropdown = ft.Dropdown(label="INPUT (MIC)", options=[ft.dropdown.Option(d) for d in get_audio_devices('input')], border_color="white24", value=saved_in, text_size=12)
    out_dev_dropdown = ft.Dropdown(label="OUTPUT (SPEAKERS)", options=[ft.dropdown.Option(d) for d in get_audio_devices('output')], border_color="white24", value=saved_out, text_size=12)

    config_window = ft.Container(
        content=ft.Column([
            ft.Column([
                ft.Row([ft.Text("CORE CONFIG", color=CYAN, weight="bold", size=16), ft.IconButton(ft.Icons.CLOSE, icon_color="white", on_click=lambda _: toggle_config(False))], alignment="spaceBetween"),
                ft.Divider(color="white24"),
                api_input, pv_key_input, prompt_input, in_dev_dropdown, out_dev_dropdown,
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            ft.ElevatedButton("SAVE CONFIG", on_click=lambda _: save_settings(api_input.value, prompt_input.value, in_dev_dropdown.value, out_dev_dropdown.value, pv_key_input.value), bgcolor=CYAN, color="black", width=350, height=45)
        ], opacity=0, animate_opacity=300, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        width=0, height=0, bgcolor="#12121a", border_radius=20, blur=25, 
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black")
    )

    # --- Чат (Telegram Style) ---
    chat_list = ft.Column(spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)
    chat_input = ft.TextField(hint_text="Сообщение...", expand=True, border_color="white24", text_size=14, color="white")
    
    def render_message(role, text):
        is_user = role == 'user'
        # Стиль для сообщения
        return ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(text, color="white" if is_user else "#e0e0e0", size=13),
                    bgcolor="#2b5278" if is_user else "#25252e", # Синий для юзера, серый для бота
                    border_radius=ft.border_radius.only(
                        top_left=15, top_right=15, 
                        bottom_left=15 if is_user else 0, 
                        bottom_right=0 if is_user else 15
                    ),
                    padding=10,
                    constraints=ft.BoxConstraints(max_width=260),
                )
            ],
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
        )

    def load_chat_history():
        chat_list.controls.clear()
        memory = load_memory()
        for msg in memory:
            chat_list.controls.append(render_message(msg['role'], msg['content']))
        # Прокрутка вниз при открытии (немного костыльно, но работает через update)
        chat_list.update()

    def send_chat_message(e):
        txt = chat_input.value
        if not txt: return
        
        # 1. Сразу показать сообщение юзера
        chat_list.controls.append(render_message('user', txt))
        chat_input.value = ""
        chat_input.focus()
        chat_list.update()

        # 2. Обработка в потоке
        def process_response():
            # Показываем индикатор печати (опционально)
            typing_indicator = ft.Row([ft.Text("Lumia печатает...", size=10, color="white54")], alignment="start")
            chat_list.controls.append(typing_indicator)
            page.run_task(lambda: chat_list.update()) # thread-safe update

            # Вызов логики AI
            response = process_text_query(txt)
            
            # Удаляем индикатор и показываем ответ
            chat_list.controls.remove(typing_indicator)
            chat_list.controls.append(render_message('assistant', response))
            page.run_task(lambda: chat_list.update())

        threading.Thread(target=process_response, daemon=True).start()

    chat_window = ft.Container(
        content=ft.Column([
            ft.Column([
                ft.Row([ft.Text("NEURAL CHAT", color=CYAN, weight="bold", size=16), ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: toggle_chat(False))], alignment="spaceBetween"),
                ft.Divider(color="white24"),
            ]),
            # Область сообщений
            ft.Container(content=chat_list, expand=True, padding=5),
            # Область ввода
            ft.Row([chat_input, ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=CYAN, on_click=send_chat_message)], alignment="center")
        ], opacity=0, animate_opacity=300),
        width=0, height=0, bgcolor="#0d0d14", border_radius=20, blur=25,
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black")
    )

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
        config_window.update()

    def toggle_chat(expand):
        state["is_chat_expanded"] = expand
        if expand:
            load_chat_history() # Загружаем историю при открытии
            chat_window.visible = True
            chat_window.width, chat_window.height = 360, 500
            chat_window.top, chat_window.left = 50, 20
            chat_window.content.opacity = 1
        else:
            chat_window.width, chat_window.height = 0, 0
            chat_window.top, chat_window.left = 300, 200
            chat_window.content.opacity = 0
            chat_window.visible = False
        chat_window.update()

    # --- Кнопки вызова ---
    btn_chat = ft.Container(content=ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINED, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, on_click=lambda _: toggle_chat(True))
    
    # Кнопка с подсказкой "МОДЫ"
    btn_tools = ft.Container(content=ft.Icon(ft.Icons.AUTO_FIX_HIGH, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, tooltip="МОДЫ (в разработке)")
    
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
            print("Voice Assistant started from GUI")
        else:
            if voice_assistant_instance:
                voice_assistant_instance.stop()
                voice_assistant_instance = None # Сброс, чтобы пересоздать при следующем запуске (для обновления конфига)
                print("Voice Assistant stopped from GUI")

    btn_mic = ft.Container(content=ft.Icon(ft.Icons.MIC_NONE_ROUNDED, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, on_click=toggle_mic_state)
    btn_cfg = ft.Container(content=ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0, on_click=lambda _: toggle_config(True))

    satellites = [btn_chat, btn_tools, btn_mic, btn_cfg]

    # --- Ядро ---
    core = ft.GestureDetector(
        on_tap=lambda _: toggle_menu(),
        content=ft.Container(
            content=ft.Icon(ft.Icons.FINGERPRINT, size=40, color=CYAN),
            width=80, height=80, bgcolor="#1a1a24", border_radius=40, alignment=ft.alignment.center,
            shadow=ft.BoxShadow(spread_radius=5, blur_radius=25, color=CYAN_GLOW),
            animate_scale=ft.Animation(300, ft.AnimationCurve.BOUNCE_OUT)
        )
    )

    def toggle_menu():
        state["is_menu_open"] = not state["is_menu_open"]
        core.content.scale = 1.2 if state["is_menu_open"] else 1.0
        angles = [270, 0, 90, 180] 
        for i, btn in enumerate(satellites):
            if state["is_menu_open"]:
                angle_rad = math.radians(angles[i])
                btn.top, btn.left = CENTER_Y + 10 + RADIUS * math.sin(angle_rad), CENTER_X + 10 + RADIUS * math.cos(angle_rad)
                btn.scale = 1
            else:
                btn.top, btn.left, btn.scale = CENTER_Y+10, CENTER_X+10, 0
            btn.update()
        core.update()

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
        content=ft.Column([ft.Icon(ft.Icons.SHIELD_OUTLINED, size=60, color=CYAN), ft.Container(height=20), ft.Text("SYNCHRONIZING...", size=14, color=CYAN, weight="bold")], alignment="center", horizontal_alignment="center"),
        width=400, height=600, bgcolor="#0f0f13", animate_opacity=800
    )

    page.add(ft.Stack([main_stack, loading_screen], expand=True))

    def run_loading():
        time.sleep(1.2)
        loading_screen.opacity = 0; loading_screen.update()
        time.sleep(0.8); loading_screen.visible = False
        page.window.always_on_top = False
        main_stack.opacity = 1; page.update()
        threading.Thread(target=pulse_waves_logic, daemon=True).start()

    threading.Thread(target=run_loading, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)