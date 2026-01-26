import flet as ft
import sqlite3
import sounddevice as sd
import math
import time
import threading

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
    conn.commit()
    conn.close()

def save_settings(api_key, prompt, input_dev, output_dev):
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings")
    cursor.execute("INSERT INTO settings (api_key, prompt, input_device, output_device) VALUES (?, ?, ?, ?)", 
                   (api_key, prompt, input_dev, output_dev))
    conn.commit()
    conn.close()

def load_settings():
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT api_key, prompt, input_device, output_device FROM settings LIMIT 1")
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return row if row else ("", "", None, None)

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

def main(page: ft.Page):
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

    saved_api, saved_prompt, saved_in, saved_out = load_settings()

    # --- Волны (Активация через микрофон) ---
    class WaveCircle(ft.Container):
        def __init__(self, size=80):
            super().__init__()
            self.width = size; self.height = size
            self.border_radius = size / 2
            self.border = ft.border.all(2, CYAN)
            self.opacity = 0; self.scale = 1
            # Точное центрирование под отпечатком (80x80)
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

    # --- Окна (Теперь в отдельных переменных для управления слоями) ---
    api_input = ft.TextField(label="API KEY", password=True, can_reveal_password=True, border_color="white24", value=saved_api)
    prompt_input = ft.TextField(label="SYSTEM PROMPT", multiline=True, min_lines=3, border_color="white24", value=saved_prompt)
    in_dev_dropdown = ft.Dropdown(label="INPUT (MIC)", options=[ft.dropdown.Option(d) for d in get_audio_devices('input')], border_color="white24", value=saved_in)
    out_dev_dropdown = ft.Dropdown(label="OUTPUT (SPEAKERS)", options=[ft.dropdown.Option(d) for d in get_audio_devices('output')], border_color="white24", value=saved_out)

    config_window = ft.Container(
        content=ft.Column([
            ft.Column([
                ft.Row([ft.Text("CORE CONFIG", color=CYAN, weight="bold", size=16), ft.IconButton(ft.Icons.CLOSE, icon_color="white", on_click=lambda _: toggle_config(False))], alignment="spaceBetween"),
                ft.Divider(color="white24"),
                api_input, prompt_input, in_dev_dropdown, out_dev_dropdown,
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            ft.ElevatedButton("SAVE CONFIG", on_click=lambda _: save_settings(api_input.value, prompt_input.value, in_dev_dropdown.value, out_dev_dropdown.value), bgcolor=CYAN, color="black", width=350, height=45)
        ], opacity=0, animate_opacity=300, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        width=0, height=0, bgcolor="#12121a", border_radius=20, blur=25, 
        animate_size=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(ANIM_SPEED, ft.AnimationCurve.DECELERATE),
        top=300, left=200, visible=False, shadow=ft.BoxShadow(blur_radius=50, color="black")
    )

    chat_window = ft.Container(
        content=ft.Column([
            ft.Column([
                ft.Row([ft.Text("NEURAL L1NK", color=CYAN, weight="bold", size=16), ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: toggle_chat(False))], alignment="spaceBetween"),
                ft.Divider(color="white24"),
                ft.Container(content=ft.ListView([ft.Text("AI: Systems ready.", color=CYAN)], spacing=10), height=300),
            ]),
            ft.Row([ft.TextField(hint_text="Enter command...", expand=True, border_color="white24"), ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=CYAN)], alignment="center")
        ], opacity=0, animate_opacity=300, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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
    btn_tools = ft.Container(content=ft.Icon(ft.Icons.AUTO_FIX_HIGH, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ANIM_SPEED, top=CENTER_Y+10, left=CENTER_X+10, scale=0)
    
    def toggle_mic_state(e):
        state["is_voice_active"] = not state["is_voice_active"]
        btn_mic.content.color = CYAN if state["is_voice_active"] else "white"
        btn_mic.bgcolor = "white24" if state["is_voice_active"] else "white10"
        btn_mic.update()

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
        # Слой 1: Волны (под отпечатком)
        wave2, wave1,
        # Слой 2: Кнопки-сателлиты (под отпечатком)
        btn_tools, btn_mic, btn_chat, btn_cfg,
        # Слой 3: Ядро (Отпечаток)
        ft.Container(core, top=CENTER_Y, left=CENTER_X),
        # Слой 4: Полноэкранные Окна (ПОВЕРХ ВСЕГО)
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