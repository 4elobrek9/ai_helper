import flet as ft
import sqlite3
import sounddevice as sd
import math

# ПРИМЕЧАНИЕ ДЛЯ БУДУЩЕГО: 
# Дизайн: Футуристичный (Living Shard), вертикальная ориентация.
# Функции: Динамическое позиционирование сателлитов от центра, морфинг чата, конфиг с SQLite.
# Зависимости: flet, sounddevice.

def init_db():
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            api_key TEXT,
            prompt TEXT,
            audio_device TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_settings(api_key, prompt, device):
    conn = sqlite3.connect("config.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings")  # Храним только одну актуальную запись
    cursor.execute("INSERT INTO settings (api_key, prompt, audio_device) VALUES (?, ?, ?)", 
                   (api_key, prompt, device))
    conn.commit()
    conn.close()

def get_audio_devices():
    devices = sd.query_devices()
    input_devices = [d['name'] for d in devices if d['max_input_channels'] > 0]
    return list(set(input_devices)) # Убираем дубликаты

def main(page: ft.Page):
    init_db()
    
    page.title = "AI Helper - Living Shard"
    page.window_width = 450
    page.window_height = 800
    page.bgcolor = "#0f0f13"
    page.window_resizable = False
    page.padding = 0
    
    # Центр экрана для расчетов
    CENTER_X = 225 - 30 # Половина ширины минус половина размера кнопки
    CENTER_Y = 400 - 30 # Половина высоты
    RADIUS = 120

    is_menu_open = False
    is_voice_active = False
    is_chat_expanded = False
    is_config_open = False

    CYAN = "#00ffff"
    CYAN_GLOW = "0x4400ffff"

    # --- Волны (центр) ---
    class WaveCircle(ft.Container):
        def __init__(self, size=80):
            super().__init__()
            self.width = size
            self.height = size
            self.border_radius = size / 2
            self.border = ft.border.all(2, CYAN)
            self.opacity = 0
            self.scale = 1
            self.animate_opacity = ft.Animation(1500, ft.AnimationCurve.EASE_OUT)
            self.animate_scale = ft.Animation(1500, ft.AnimationCurve.EASE_OUT)

    wave1 = WaveCircle()
    wave2 = WaveCircle()

    # --- Окно Настроек (Config) ---
    api_input = ft.TextField(label="API KEY", password=True, can_reveal_password=True, border_color="white24")
    prompt_input = ft.TextField(label="SYSTEM PROMPT", multiline=True, min_lines=3, border_color="white24")
    device_dropdown = ft.Dropdown(label="AUDIO DEVICE", options=[ft.dropdown.Option(d) for d in get_audio_devices()], border_color="white24")

    def handle_save_config(e):
        save_settings(api_input.value, prompt_input.value, device_dropdown.value)
        toggle_config_morph(False)
        page.snack_bar = ft.SnackBar(ft.Text("Настройки сохранены в БД"))
        page.snack_bar.open = True
        page.update()

    config_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("CORE CONFIG", color=CYAN, weight=ft.FontWeight.BOLD),
                ft.IconButton(ft.Icons.CLOSE, icon_color="white", on_click=lambda _: toggle_config_morph(False))
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(color="white24"),
            api_input,
            prompt_input,
            device_dropdown,
            ft.ElevatedButton("SAVE TO DATABASE", on_click=handle_save_config, bgcolor=CYAN, color="black")
        ], opacity=0, animate_opacity=ft.Animation(400), spacing=15),
        width=60, height=60, bgcolor="white10", border_radius=15, blur=15,
        animate_size=ft.Animation(500, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT),
        top=CENTER_Y, left=CENTER_X, visible=False
    )

    def toggle_config_morph(expand):
        nonlocal is_config_open
        is_config_open = expand
        if expand:
            config_panel.width, config_panel.height = 350, 500
            config_panel.top, config_panel.left = 150, 50
            config_panel.bgcolor = "#12121a"
            config_panel.border = ft.border.all(1, CYAN)
            config_panel.content.opacity = 1
        else:
            config_panel.width, config_panel.height = 60, 60
            config_panel.top, config_panel.left = CENTER_Y, CENTER_X - RADIUS
            config_panel.bgcolor = "white10"
            config_panel.content.opacity = 0
            config_panel.visible = False
        config_panel.update()

    # --- Чат ---
    chat_content = ft.Column([
        ft.Row([ft.Text("NEURAL LINK", color=CYAN, weight="bold"), ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: toggle_chat_morph(False))], alignment="spaceBetween"),
        ft.ListView([ft.Text("AI: Link stable.", color=CYAN)], expand=True),
        ft.TextField(hint_text="Type command...", expand=True)
    ], opacity=0, animate_opacity=ft.Animation(400))

    btn_chat = ft.Container(
        content=ft.Stack([ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINED, color="white"), ft.Container(chat_content, visible=False)]),
        width=60, height=60, bgcolor="white10", border_radius=15, blur=15, alignment=ft.alignment.center,
        animate_size=ft.Animation(500, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT),
        top=CENTER_Y, left=CENTER_X, scale=0,
        on_click=lambda _: toggle_chat_morph(True)
    )

    def toggle_chat_morph(expand):
        nonlocal is_chat_expanded
        is_chat_expanded = expand
        if expand:
            btn_chat.width, btn_chat.height = 350, 500
            btn_chat.top, btn_chat.left = 150, 50
            btn_chat.content.controls[0].visible = False
            btn_chat.content.controls[1].visible = True
            chat_content.opacity = 1
        else:
            btn_chat.width, btn_chat.height = 60, 60
            btn_chat.top, btn_chat.left = CENTER_Y - RADIUS, CENTER_X
            btn_chat.content.controls[0].visible = True
            btn_chat.content.controls[1].visible = False
            chat_content.opacity = 0
        btn_chat.update()

    # --- Остальные Кнопки ---
    btn_tools = ft.Container(content=ft.Icon(ft.Icons.AUTO_FIX_HIGH, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT), top=CENTER_Y, left=CENTER_X, scale=0)
    
    btn_mic = ft.Container(content=ft.Icon(ft.Icons.MIC_NONE_ROUNDED, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT), top=CENTER_Y, left=CENTER_X, scale=0)
    
    btn_config_launcher = ft.Container(content=ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="white"), width=60, height=60, bgcolor="white10", border_radius=15, blur=10, animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT), top=CENTER_Y, left=CENTER_X, scale=0, on_click=lambda _: [setattr(config_panel, 'visible', True), toggle_config_morph(True)])

    def toggle_voice(e):
        nonlocal is_voice_active
        is_voice_active = not is_voice_active
        btn_mic.content.color = CYAN if is_voice_active else "white"
        btn_mic.border = ft.border.all(1, CYAN if is_voice_active else "white12")
        wave1.opacity, wave1.scale = (0.5, 2.8) if is_voice_active else (0, 1)
        wave2.opacity, wave2.scale = (0.3, 3.8) if is_voice_active else (0, 1)
        btn_mic.update(); wave1.update(); wave2.update()

    btn_mic.on_click = toggle_voice

    satellites = [btn_chat, btn_tools, btn_mic, btn_config_launcher]

    # --- Ядро ---
    core = ft.GestureDetector(
        on_tap=lambda _: toggle_menu(),
        content=ft.Container(
            content=ft.Icon(ft.Icons.FINGERPRINT, size=40, color=CYAN),
            width=80, height=80, bgcolor="#1a1a24", border_radius=40, alignment=ft.alignment.center,
            shadow=ft.BoxShadow(spread_radius=2, blur_radius=25, color=CYAN_GLOW),
            animate_scale=ft.Animation(300, ft.AnimationCurve.BOUNCE_OUT)
        )
    )

    def toggle_menu():
        nonlocal is_menu_open
        is_menu_open = not is_menu_open
        core.content.scale = 1.2 if is_menu_open else 1.0
        
        # Углы: Верх(270), Право(0), Низ(90), Лево(180)
        angles = [270, 0, 90, 180] 
        
        for i, btn in enumerate(satellites):
            if is_menu_open:
                angle_rad = math.radians(angles[i])
                btn.top = CENTER_Y + RADIUS * math.sin(angle_rad)
                btn.left = CENTER_X + RADIUS * math.cos(angle_rad)
                btn.scale = 1
            else:
                btn.top, btn.left = CENTER_Y, CENTER_X
                btn.scale = 0
            btn.update()
        core.update()

    page.add(ft.Stack([
        # Волны из центра
        ft.Container(wave2, top=CENTER_Y-10, left=CENTER_X-10), 
        ft.Container(wave1, top=CENTER_Y-10, left=CENTER_X-10),
        # Слой кнопок
        btn_chat, btn_tools, btn_mic, btn_config_launcher,
        config_panel,
        # Ядро
        ft.Container(core, top=CENTER_Y-10, left=CENTER_X-10),
        ft.Container(ft.Text("NEURAL SHARD ACTIVE", size=10, color="white24", weight="bold"), bottom=50, left=155)
    ], expand=True))

if __name__ == "__main__":
    ft.app(target=main)