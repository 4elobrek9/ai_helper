import ctypes
import os
import threading

import flet as ft
import pystray
import sounddevice as sd
from PIL import Image

from core.config.settings import init_db, load_settings, save_settings
from listen import VoiceAssistant, load_memory, process_text_query

voice_assistant_instance = None


def _resolve_icon_path() -> str | None:
    for name in ("app_icon.png", "icon.png", "images.jpg"):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", name))
        if os.path.exists(path):
            return path
    return None


def _audio_devices(kind='input'):
    try:
        devices = sd.query_devices()
        key = 'max_input_channels' if kind == 'input' else 'max_output_channels'
        return list(dict.fromkeys([d['name'] for d in devices if d[key] > 0])) or ["Default Device"]
    except Exception:
        return ["Default Device"]


def run_app(page: ft.Page):
    init_db()
    saved_api, saved_prompt, saved_in, saved_out, saved_key = load_settings()
    icon_path = _resolve_icon_path()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('lumi.ai.assistant.2.0')
    except Exception:
        pass

    def show_app(icon=None, item=None):
        page.window.visible = True
        page.window.minimized = False
        page.window.to_front()
        page.update()

    def quit_app(icon=None, item=None):
        if voice_assistant_instance:
            voice_assistant_instance.stop()
        page.window.destroy()

    def setup_tray():
        if not icon_path:
            return
        tray = pystray.Icon("LUMI AI", Image.open(icon_path), "LUMI AI", pystray.Menu(
            pystray.MenuItem("Развернуть LUMI", show_app, default=True), pystray.MenuItem("Выход", quit_app)
        ))
        tray.run()

    threading.Thread(target=setup_tray, daemon=True).start()
    page.on_window_event = lambda e: setattr(page.window, "visible", False) if e.data == "minimize" else show_app()
    page.title, page.bgcolor, page.padding = "LUMI AI", "#0f0f13", 20
    page.window.width, page.window.height, page.window.resizable = 430, 640, False
    if icon_path:
        page.window.icon = icon_path

    api_input = ft.TextField(label="MISTRAL API KEY", value=saved_api, password=True, can_reveal_password=True)
    pv_input = ft.TextField(label="PORCUPINE KEY", value=saved_key, password=True, can_reveal_password=True)
    prompt_input = ft.TextField(label="SYSTEM PROMPT", value=saved_prompt, multiline=True, min_lines=3)
    in_dev = ft.Dropdown(label="INPUT", options=[ft.dropdown.Option(v) for v in _audio_devices('input')], value=saved_in)
    out_dev = ft.Dropdown(label="OUTPUT", options=[ft.dropdown.Option(v) for v in _audio_devices('output')], value=saved_out)

    chat_list = ft.ListView(expand=True, spacing=8)
    chat_input = ft.TextField(hint_text="Напишите сообщение...", expand=True, on_submit=lambda e: send_chat())

    def render_msg(role, text):
        align = ft.CrossAxisAlignment.END if role == 'user' else ft.CrossAxisAlignment.START
        bg = "#2b5278" if role == 'user' else "#25252e"
        return ft.Column([ft.Container(ft.Text(text, size=13), bgcolor=bg, border_radius=10, padding=10)], horizontal_alignment=align)

    def load_chat():
        chat_list.controls = [render_msg(m['role'], m['content']) for m in load_memory()]
        page.update()

    def ask_ai(text):
        chat_list.controls.append(render_msg('assistant', 'Люми думает...'))
        page.update()
        response = process_text_query(text)
        chat_list.controls.pop()
        chat_list.controls.append(render_msg('assistant', response))
        page.update()

    def send_chat():
        text = (chat_input.value or '').strip()
        if not text:
            return
        chat_list.controls.append(render_msg('user', text))
        chat_input.value = ''
        page.update()
        threading.Thread(target=ask_ai, args=(text,), daemon=True).start()

    def save_cfg(e=None):
        save_settings(api_input.value, prompt_input.value, in_dev.value, out_dev.value, pv_input.value)
        page.snack_bar = ft.SnackBar(ft.Text("Настройки сохранены"))
        page.snack_bar.open = True
        page.update()

    def toggle_mic(e=None):
        global voice_assistant_instance
        if voice_assistant_instance is None:
            voice_assistant_instance = VoiceAssistant()
            threading.Thread(target=voice_assistant_instance.start, daemon=True).start()
            mic_btn.text = "Остановить микрофон"
        else:
            voice_assistant_instance.stop()
            voice_assistant_instance = None
            mic_btn.text = "Запустить микрофон"
        page.update()

    mic_btn = ft.ElevatedButton("Запустить микрофон", on_click=toggle_mic)
    cfg = ft.ExpansionTile(title=ft.Text("Core config"), controls=[api_input, pv_input, prompt_input, in_dev, out_dev, ft.ElevatedButton("Сохранить", on_click=save_cfg)])
    chat_panel = ft.Column([ft.Text("Neural chat", size=18, weight=ft.FontWeight.BOLD), chat_list, ft.Row([chat_input, ft.IconButton(ft.Icons.SEND, on_click=lambda e: send_chat())])], expand=True)

    load_chat()
    page.add(ft.Column([ft.Text("LUMI AI", size=28, weight=ft.FontWeight.BOLD), mic_btn, cfg, chat_panel], expand=True))


if __name__ == '__main__':
    ft.app(target=run_app)
