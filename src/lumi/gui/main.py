"""Главное окно приложения LUMI AI на базе Flet с визуальными индикаторами состояния."""

from __future__ import annotations

import threading
import time
from typing import Optional, Callable

import flet as ft

from lumi.core.config import config
from lumi.core.logging import get_logger
from lumi.core.paths import ASSETS_DIR, ICON_FILE, ensure_dirs
from lumi.core.state import app_state
from lumi.core.app import LumiApp
from lumi.gui.widgets import status_indicator, message_bubble

logger = get_logger("gui.main")

# Цвета состояний
COLOR_READY = "#00D4FF"      # cyan — Готов
COLOR_LISTENING = "#00FF88"  # green — Слушаю
COLOR_THINKING = "#FFB800"   # orange — Думаю
COLOR_SPEAKING = "#FF0055"   # red — Говорю
COLOR_ERROR = "#FF5555"      # light red — Ошибка


def run_app(lumi_app: Optional[LumiApp] = None) -> None:
    """Запуск Flet-приложения.

    Args:
        lumi_app: Экземпляр LumiApp (если None — создаётся новый).
    """
    ensure_dirs()

    if lumi_app is None:
        from lumi.core.app import get_app
        lumi_app = get_app()

    def main(page: ft.Page) -> None:
        _setup_page(page)
        _build_ui(page, lumi_app)
        page.update()

        # --- Обновление индикатора состояния из LumiApp ---
        def _update_status_indicator(ind, state_data):
            if not state_data or not ind:
                return
            is_listening = state_data.get("listening", False)
            is_thinking = state_data.get("thinking", False)
            is_speaking = state_data.get("speaking", False)

            # Обновляем текст и цвет индикатора
            if is_listening:
                ind.content = ft.Text("Слушаю...", size=24, color=COLOR_LISTENING)
                ind.bgcolor = COLOR_LISTENING
            elif is_thinking:
                ind.content = ft.Text("Думаю...", size=24, color=COLOR_THINKING)
                ind.bgcolor = COLOR_THINKING
            elif is_speaking:
                ind.content = ft.Text("Говорю...", size=24, color=COLOR_SPEAKING)
                ind.bgcolor = COLOR_SPEAKING
            else:
                ind.content = ft.Text("Готов", size=24, color=COLOR_READY)
                ind.bgcolor = COLOR_READY

            ind.update()

        # Периодическое обновление состояния (каждые 300мс)
        last_refresh = time.time()

        def _on_status_tick(e):
            now = time.time()
            if now - last_refresh >= 0.3:
                last_refresh = now
                global status_ind
                if status_ind and lumi_app:
                    try:
                        state_data = lumi_app.get_state_for_gui()
                        _update_status_indicator(status_ind, state_data)
                    except Exception as ex:
                        logger.debug(f"Ошибка обновления статуса: {ex}")

        page.timer.add(ft.Timer(interval=0.3, callback=_on_status_tick)

    ft.app(target=main, assets_dir=str(ASSETS_DIR))


def _setup_page(page: ft.Page) -> None:
    """Настраивает параметры страницы."""
    gui_cfg = config.get_section("gui")
    page.title = "LUMI AI"
    page.window_width = gui_cfg.get("window_width", 400)
    page.window_height = gui_cfg.get("window_height", 600)
    page.window_resizable = False
    page.window_always_on_top = False
    page.padding = 0
    page.spacing = 0
    page.bgcolor = "#0f0f13"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(
        color_scheme_seed=gui_cfg.get("accent_color", "#00D4FF"),
    )
    page.window.prevent_close = True
    page.on_close = lambda e: _on_window_close(page)

    if ICON_FILE.exists():
        page.window.icon = str(ICON_FILE)


def _on_window_close(page: ft.Page) -> None:
    """Скрыть окно вместо выхода (трей)."""
    page.window_hidden = True
    page.update()


def _build_ui(page: ft.Page, lumi_app: LumiApp) -> None:
    """Строит интерфейс главного окна с индикаторами состояния."""
    CYAN = "#00D4FF"
    CENTER_X = 200
    CENTER_Y = 300
    RADIUS = 90
    ANIM_SPEED = 300

    state = {"is_menu_open": False, "is_voice_active": False}

    # --- Индикатор состояния (цветной) ---
    status_ind = status_indicator("Готов", COLOR_READY)
    status_ind.top = 40
    status_ind.left = CENTER_X - 60

    # --- Волны ---
    wave1 = ft.Container(
        width=120, height=120, bgcolor=CYAN, border_radius=60,
        top=CENTER_Y - 60, left=CENTER_X - 60, opacity=0.15,
    )
    wave2 = ft.Container(
        width=80, height=80, bgcolor=CYAN, border_radius=40,
        top=CENTER_Y - 40, left=CENTER_X - 40, opacity=0.08,
    )

    # --- Кнопка ядра (Living Shard) ---
    core_btn = ft.Container(
        content=ft.Icon(ft.Icons.FINGERPRINT, size=40, color=CYAN),
        width=80, height=80, bgcolor="#1a1a24", border_radius=40,
        alignment=ft.alignment.center,
        top=CENTER_Y - 40, left=CENTER_X - 40,
        animate_scale=ft.Animation(300, ft.AnimationCurve.BOUNCE_OUT),
        on_click=lambda _: toggle_menu(),
    )

    # --- Спутниковые кнопки ---
    btn_chat = ft.Container(
        content=ft.Icon(ft.Icons.CHAT_ROUNDED, color="white"),
        width=50, height=50, bgcolor="#1a1a24", border_radius=12,
        top=CENTER_Y + 10, left=CENTER_X + 10, scale=0,
        on_click=lambda _: toggle_chat(True),
    )
    btn_tools = ft.Container(
        content=ft.Icon(ft.Icons.TUNE, color="white"),
        width=50, height=50, bgcolor="#1a1a24", border_radius=12,
        top=CENTER_Y + 10, left=CENTER_X + 10, scale=0,
        on_click=lambda _: None,
    )
    btn_mic = ft.Container(
        content=ft.Icon(ft.Icons.MIC_NONE_ROUNDED, color="white"),
        width=50, height=50, bgcolor="#1a1a24", border_radius=12,
        top=CENTER_Y + 10, left=CENTER_X + 10, scale=0,
        on_click=lambda _: toggle_mic(),
    )
    btn_cfg = ft.Container(
        content=ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="white"),
        width=50, height=50, bgcolor="#1a1a24", border_radius=12,
        top=CENTER_Y + 10, left=CENTER_X + 10, scale=0,
        on_click=lambda _: toggle_config(True),
    )

    satellites = [btn_chat, btn_tools, btn_mic, btn_cfg]

    def toggle_menu():
        import math
        state["is_menu_open"] = not state["is_menu_open"]
        core_btn.scale = 1.2 if state["is_menu_open"] else 1.0
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
        core_btn.update()
        page.update()

    def toggle_mic():
        state["is_voice_active"] = not state["is_voice_active"]
        if state["is_voice_active"]:
            btn_mic.bgcolor = CYAN
            btn_mic.content = ft.Icon(ft.Icons.MIC_ROUNDED, color="#0f0f13")
            _update_status_indicator(status_ind, "Слушаю…", COLOR_LISTENING)
            app_state.set_voice_state(True, False, False)
            lumi_app.tts.set_callbacks(
                on_speaking_start=lambda: _on_tts_start(status_ind),
                on_speaking_stop=lambda: _on_tts_stop(status_ind, state["is_voice_active"]),
            )
        else:
            btn_mic.bgcolor = "#1a1a24"
            btn_mic.content = ft.Icon(ft.Icons.MIC_NONE_ROUNDED, color="white")
            _update_status_indicator(status_ind, "Готов", COLOR_READY)
            app_state.set_voice_state(False, False, False)
        btn_mic.update()
        status_ind.update()
        page.update()

    def toggle_chat(expand: bool):
        if expand:
            chat_window.visible = True
            chat_window.width = 340
            chat_window.height = 520
            chat_window.top = 40
            chat_window.left = 20
        else:
            chat_window.width = 0
            chat_window.height = 0
            chat_window.top = 300
            chat_window.left = 200
            chat_window.visible = False
        page.update()

    def toggle_config(expand: bool):
        if expand:
            config_window.visible = True
            config_window.width = 340
            config_window.height = 520
            config_window.top = 40
            config_window.left = 20
        else:
            config_window.width = 0
            config_window.height = 0
            config_window.top = 300
            config_window.left = 200
            config_window.visible = False
        page.update()

    def _update_status_indicator(ind: ft.Container, text: str, color: str) -> None:
        ind.content = status_indicator(text, color)
        ind.update()

    chat_window = ft.Column(controls=[], expand=True)
    chat_header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE),
            ft.Text("Чат", size=14, weight=ft.FontWeight.W700),
            ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e, c=chat_window: _toggle_chat_helper(c)),
        ]),
        width=config_window.width, bgcolor="#151520", padding=8, border_radius=0, alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    def _toggle_chat_helper(c: ft.Column):
        c.visible = not c.visible
        page.update()

    config_window = ft.Column(controls=[], expand=True)
    cfg_header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.SETTINGS),
            ft.Text("Настройки", size=14, weight=ft.FontWeight.W700),
            ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e, c=config_window: _toggle_chat_helper(c)),
        ]),
        width=config_window.width, bgcolor="#151520", padding=8, border_radius=0, alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    main_col = ft.Column([status_ind, wave1, wave2, core_btn])
    page.add(
        chat_header,
        ft.Container(content=chat_window, expand=True),
        cfg_header,
        ft.Container(content=config_window, expand=True),
        main_col,
    )

    def _on_tts_start(ind: ft.Container) -> None:
        ind.content = status_indicator("Говорю…", COLOR_SPEAKING)
        ind.update()

    def _on_tts_stop(ind: ft.Container, is_active: bool) -> None:
        if not is_active:
            ind.content = status_indicator("Готов", COLOR_READY)
            ind.update()

    # Трей-меню (заглушка для pystray)
    tray_menu = ft.Menu(
        ft.MenuItem("О программе", on_click=lambda e: _show_about()),
        ft.MenuItem("Активировать прослушивание", icon=ft.Icons.MIC_ON, tooltip="Ctrl+Alt+S", on_click=lambda e: toggle_mic() if state["is_voice_active"] else None),
        ft.Divider(),
        ft.MenuItem("Выход", tooltip="Win+Esc или Alt+F4", on_click=lambda e: page.close()),
    )

    def _show_about():
        tray = ft.AlertDialog(
            title=ft.Text("LUMI AI"),
            content=ft.Column([
                ft.Text("Локальный голосовой ассистент на Flet + Ollama", size=10),
                ft.Text("Версия: 0.1.0", size=10),
                ft.Container(
                    content=ft.Markdown("""
**Особенности:**
- 🎤 Голосовое управление (faster-whisper)
- 🗣️ TTS Silero + system speech
- 🖥️ Desktop-агент (открытие приложений, OCR и др.)
- 🔒 Полностью локальный (Ollama, Whisper, Silero)

**Горячие клавиши:**
`Ctrl+Alt+S` — показать/скрыть окно
`Ctrl+Alt+E` — активировать деактивировать прослушивание
`Ctrl+Alt+R` — прервать речь
"""),
                    padding=8, width=300),
            ], scroll=ft.ScrollMode.AUTO),
            actions=[ft.ElevatedButton("OK", on_click=lambda e: page.close())],
        )
        page.open_dialog(tray)

    # Обработчики горячих клавиш (после GUI)
    def _on_hotkey_show():
        page.window_hidden = False
        page.update()

    def _on_hotkey_mic():
        if not state["is_voice_active"]:
            toggle_mic()

    def _on_hotkey_speak_stop():
        import threading
        if app_state.is_speaking and not app_state.is_asking_question:
            tts_instance = getattr(app_state, "tts", None)
            if tts_instance:
                try:
                    tts_instance.queue.clear()
                    tts_instance.shutdown()
                except Exception as e:
                    logger.error("Ошибка остановки TTS:", e)

    # Подписка на состояния (будут доступны после инициализации LumiApp)
    lumi_app = getattr(lumi_app, "_app", None)
    if lumi_app is None:
        from lumi.core.app import get_app
        lumi_app = app_state._app  # fallback

    _attach_hotkeys(lumi_app)

    def _attach_hotkeys(app: LumiApp):
        from pynput import keyboard, mouse
        from pynput.keyboard import Key, Controller
        from datetime import datetime

        global hotkey_controller, global_mouse_controller
        global hotkey_controller, global_mouse_controller  # noqa

        controller = Controller()
        def on_press(key, controller=controller):
            try:
                if key == Key.ctrl_l and controller.press(Key.alt) and controller.press('s'):
                    _on_hotkey_show()
                elif key == Key.ctrl_l and controller.press(Key.alt) and controller.press('e'):
                    _on_hotkey_mic()
                elif key == Key.ctrl_l and controller.press(Key.alt) and controller.press('r'):
                    _on_hotkey_speak_stop()
            except Exception as e:
                logger.debug(f"Ошибка горячих клавиш (press): {e}")

        def on_release(key):
            try:
                if key == Key.ctrl_l or key == Key.alt or key == Key.space:
                    controller.release(key)
            except Exception as e:
                logger.debug(f"Ошибка горячих клавиш (release): {e}")

        hotkey_controller = keyboard.Controller()
        hotkey_controller.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        hotkey_controller.start()

    # Запуск
    main(page)


if __name__ == "__main__":
    run_app()