import flet as ft
import time

# Примечание для будущего: Пользователь предпочитает футуристичный дизайн (Living Shard).
# Реализована бесшовная трансформация кнопки чата в окно (Morphing UI).
# Исправлена ошибка TypeError путем замены animate_width/height на animate_size.
# Исправлена кликабельность центрального ядра (Fingerprint).

def main(page: ft.Page):
    page.title = "AI Helper - Living Shard"
    page.window_width = 450
    page.window_height = 800
    page.bgcolor = "#0f0f13"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_resizable = False
    page.padding = 0

    # Состояние
    is_menu_open = False
    is_voice_active = False
    is_chat_expanded = False

    CYAN = "#00ffff"
    CYAN_GLOW = "0x4400ffff"

    # --- Звуковые волны ---
    class WaveCircle(ft.Container):
        def __init__(self, size=80, duration=2000):
            super().__init__()
            self.width = size
            self.height = size
            self.border_radius = size / 2
            self.border = ft.border.all(2, CYAN)
            self.opacity = 0
            self.scale = 1
            self.animate_opacity = ft.Animation(duration, ft.AnimationCurve.EASE_OUT)
            self.animate_scale = ft.Animation(duration, ft.AnimationCurve.EASE_OUT)

    wave1 = WaveCircle()
    wave2 = WaveCircle()

    # --- Содержимое чата ---
    chat_content = ft.Column([
        ft.Row([
            ft.Text("NEURAL LINK", color=CYAN, weight=ft.FontWeight.BOLD, size=14),
            ft.IconButton(ft.Icons.CLOSE, icon_color="white", icon_size=18, on_click=lambda _: toggle_chat_morph(False))
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Divider(color="white24", height=1),
        ft.ListView([
            ft.Container(ft.Text("System: Связь установлена.", color=CYAN, size=12), bgcolor="white10", padding=8, border_radius=8),
            ft.Container(ft.Text("AI: Ожидаю ввода директив...", color="white", size=12), bgcolor="white10", padding=8, border_radius=8),
        ], expand=True, spacing=8),
        ft.Row([
            ft.TextField(hint_text="Команда...", border_color="white24", expand=True, text_size=12, height=40),
            ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=CYAN, icon_size=20)
        ])
    ], opacity=0, animate_opacity=ft.Animation(400))

    # Кнопка чата (которая станет окном)
    btn_chat = ft.Container(
        content=ft.Stack([
            ft.Container(
                content=ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINED, color="white", size=24),
                alignment=ft.alignment.center,
                key="icon_box"
            ),
            ft.Container(content=chat_content, key="chat_box", visible=False)
        ]),
        width=60,
        height=60,
        bgcolor="white10",
        border=ft.border.all(1, "white12"),
        border_radius=15,
        blur=15,
        alignment=ft.alignment.center,
        # Заменили animate_width/height на универсальный animate_size
        animate_size=ft.Animation(500, ft.AnimationCurve.DECELERATE),
        animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT),
        animate_scale=ft.Animation(400, ft.AnimationCurve.BOUNCE_OUT),
        scale=0,
        top=370, 
        left=195,
        on_click=lambda _: toggle_chat_morph(True) if not is_chat_expanded else None
    )

    def toggle_chat_morph(expand):
        nonlocal is_chat_expanded
        is_chat_expanded = expand
        
        if expand:
            # Превращаем в окно
            btn_chat.width = 300
            btn_chat.height = 400
            btn_chat.top = 150
            btn_chat.left = 75
            btn_chat.border_radius = 20
            btn_chat.bgcolor = "#12121a"
            btn_chat.border = ft.border.all(1, "cyan24")
            # Скрываем иконку, показываем чат
            btn_chat.content.controls[0].visible = False
            btn_chat.content.controls[1].visible = True
            chat_content.opacity = 1
        else:
            # Возвращаем в кнопку
            dist = 110
            btn_chat.width = 60
            btn_chat.height = 60
            btn_chat.top = 370 - dist
            btn_chat.left = 195
            btn_chat.border_radius = 15
            btn_chat.bgcolor = "white10"
            btn_chat.border = ft.border.all(1, "white12")
            # Скрываем чат, показываем иконку
            btn_chat.content.controls[0].visible = True
            btn_chat.content.controls[1].visible = False
            chat_content.opacity = 0
            
        btn_chat.update()

    # --- Остальные сателлиты ---
    def create_satellite(icon):
        return ft.Container(
            content=ft.IconButton(icon, icon_color="white", icon_size=24),
            width=60, height=60, bgcolor="white10", border=ft.border.all(1, "white12"),
            border_radius=15, blur=10, alignment=ft.alignment.center,
            animate_position=ft.Animation(600, ft.AnimationCurve.ELASTIC_OUT),
            animate_scale=ft.Animation(400, ft.AnimationCurve.BOUNCE_OUT),
            scale=0, top=370, left=195
        )

    btn_tools = create_satellite(ft.Icons.AUTO_FIX_HIGH)
    btn_mic = create_satellite(ft.Icons.MIC_NONE_ROUNDED)
    btn_settings = create_satellite(ft.Icons.SETTINGS_INPUT_COMPONENT)

    # Логика микрофона
    def toggle_voice(e):
        nonlocal is_voice_active
        is_voice_active = not is_voice_active
        btn_mic.content.icon_color = CYAN if is_voice_active else "white"
        btn_mic.border = ft.border.all(1, CYAN if is_voice_active else "white12")
        btn_mic.update()
        
        wave1.opacity, wave1.scale = (0.5, 2.5) if is_voice_active else (0, 1)
        wave2.opacity, wave2.scale = (0.3, 3.5) if is_voice_active else (0, 1)
        wave1.update(); wave2.update()

    btn_mic.content.on_click = toggle_voice

    satellites = [btn_chat, btn_tools, btn_mic, btn_settings]

    # --- Центральное Ядро ---
    core = ft.GestureDetector(
        mouse_cursor=ft.MouseCursor.CLICK,
        on_tap=lambda _: toggle_menu(),
        content=ft.Container(
            content=ft.Container(
                content=ft.Icon(ft.Icons.FINGERPRINT, size=40, color=CYAN),
                width=80, height=80, bgcolor="#1a1a24", border=ft.border.all(1, "white24"),
                border_radius=40, alignment=ft.alignment.center,
                shadow=ft.BoxShadow(spread_radius=2, blur_radius=20, color=CYAN_GLOW),
            ),
            padding=10,
            animate_scale=ft.Animation(300, ft.AnimationCurve.BOUNCE_OUT)
        )
    )

    def toggle_menu():
        nonlocal is_menu_open, is_chat_expanded
        is_menu_open = not is_menu_open
        
        # Если закрываем меню, принудительно сворачиваем чат
        if not is_menu_open and is_chat_expanded:
            toggle_chat_morph(False)
            
        core.content.scale = 1.2 if is_menu_open else 1.0
        dist = 110 
        positions = [(370 - dist, 195), (370, 195 + dist), (370 + dist, 195), (370, 195 - dist)]

        for i, btn in enumerate(satellites):
            if i == 0 and is_chat_expanded: continue
            
            if is_menu_open:
                btn.top, btn.left = positions[i]
                btn.scale, btn.opacity = 1, 1
            else:
                btn.top, btn.left = 370, 195
                btn.scale, btn.opacity = 0, 0
            btn.update()
        core.update()

    instruction = ft.Text("НАЖМИ НА ЯДРО", size=12, color="white24", weight=ft.FontWeight.BOLD)

    layout = ft.Stack([
        ft.Container(wave2, top=370-10, left=195-10), 
        ft.Container(wave1, top=370-10, left=195-10),
        btn_chat, btn_tools, btn_mic, btn_settings,
        ft.Container(core, top=360, left=185),
        ft.Container(instruction, bottom=100, left=160)
    ], expand=True)

    page.add(layout)

if __name__ == "__main__":
    ft.app(target=main)