import asyncio
import logging
import sqlite3
import threading

import flet as ft

import listen
import sintez
from app_paths import data_path, resource_path
from command_OCR import get_screen_image


logger = logging.getLogger("lumi.chat_window")
CYAN = "#76e9ff"
BACKGROUND = "#0b0e17"


def main(page: ft.Page):
    def refresh_voice_choice():
        try:
            with sqlite3.connect(data_path("config.db")) as connection:
                row = connection.execute(
                    "SELECT tts_engine FROM settings LIMIT 1"
                ).fetchone()
        except sqlite3.OperationalError:
            logger.exception("Не удалось прочитать выбранный голос для чата")
            return
        sintez.set_voice(row[0] if row and row[0] else "Silero (Ксения)")

    refresh_voice_choice()

    def speak_message(text):
        refresh_voice_choice()
        sintez.speak(text)

    page.title = "LUMI — Чат"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BACKGROUND
    page.padding = 16
    page.window.width = 620
    page.window.height = 680
    page.window.min_width = 460
    page.window.min_height = 500
    page.window.resizable = True
    page.window.skip_task_bar = False
    page.window.icon = str(resource_path("app_icon.ico"))
    page.window.prevent_close = True

    conversation_state = {"id": listen.DEFAULT_CONVERSATION_ID}
    cancel_state = {"event": None}
    window_state = {"closed": False}
    current_history = None
    current_conversation_list = None

    chat_list = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    conversation_list = ft.Column(
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    chat_input = ft.TextField(
        hint_text="Напишите сообщение...",
        expand=True,
        border_color="white24",
        text_size=14,
        color="white",
        on_submit=lambda _: send_message(),
    )
    status_text = ft.Text(size=11, color="white54")
    conversation_title = ft.Text(
        "Голосовой диалог",
        size=17,
        color=CYAN,
        weight=ft.FontWeight.BOLD,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    drawer = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "ЧАТЫ",
                            color=CYAN,
                            weight=ft.FontWeight.BOLD,
                            size=12,
                        ),
                        ft.Container(expand=True),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_color=CYAN,
                            tooltip="Новый чат",
                            on_click=lambda _: create_new_chat(),
                        ),
                    ]
                ),
                conversation_list,
            ],
            expand=True,
        ),
        width=0,
        opacity=0,
        padding=0,
        bgcolor="#151b29",
        border_radius=14,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        animate_size=ft.Animation(240, ft.AnimationCurve.EASE_IN_OUT),
        animate_opacity=ft.Animation(240, ft.AnimationCurve.EASE_IN_OUT),
        animate_offset=ft.Animation(240, ft.AnimationCurve.EASE_IN_OUT),
    )

    def render_message(role, content):
        is_user = role == "user"
        message_text = ft.Text(
            content,
            color="white" if is_user else "#e0e0e0",
            size=13,
            selectable=True,
        )
        bubble = ft.Container(
            content=message_text,
            bgcolor="#2b5278" if is_user else "#25252e",
            border_radius=14,
            padding=12,
            width=440,
        )
        controls = [bubble]
        if not is_user:
            controls.append(
                ft.IconButton(
                    icon=ft.Icons.VOLUME_UP_ROUNDED,
                    icon_color=CYAN,
                    tooltip="Озвучить",
                    on_click=lambda _, text=message_text: speak_message(text.value),
                )
            )
        return ft.Row(
            controls=controls,
            alignment=(
                ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
            ),
        )

    def refresh_history(force=False):
        nonlocal current_history
        history = [
            (message["role"], message["content"])
            for message in listen.load_memory(conversation_state["id"])
        ]
        if not force and history == current_history:
            return
        current_history = history
        chat_list.controls = [
            render_message(role, content) for role, content in history
        ]
        chat_list.update()

    def select_conversation(conversation_id):
        if conversation_id == conversation_state["id"]:
            toggle_drawer(False)
            return
        cancel_response()
        conversation_state["id"] = conversation_id
        conversations = listen.list_conversations()
        selected = next(
            (item for item in conversations if item["id"] == conversation_id),
            None,
        )
        conversation_title.value = (
            selected["title"] if selected else "Новый чат"
        )
        refresh_history(force=True)
        refresh_conversations(force=True)
        toggle_drawer(False)
        page.update()

    def refresh_conversations(force=False):
        nonlocal current_conversation_list
        conversations = listen.list_conversations()
        snapshot = tuple(
            (item["id"], item["title"], item["updated_at"])
            for item in conversations
        )
        if not force and snapshot == current_conversation_list:
            return
        current_conversation_list = snapshot
        conversation_list.controls = []
        for item in conversations:
            conversation_id = item["id"]
            selected = conversation_id == conversation_state["id"]
            if selected and conversation_title.value != item["title"]:
                conversation_title.value = item["title"]
                conversation_title.update()
            title = item["title"] or "Новый чат"
            row_controls = [
                ft.TextButton(
                    content=ft.Text(
                        title,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        color="white",
                    ),
                    expand=True,
                    on_click=lambda _, item_id=conversation_id: (
                        select_conversation(item_id)
                    ),
                    style=ft.ButtonStyle(
                        bgcolor="#315276" if selected else "transparent",
                        alignment=ft.alignment.center_left,
                        padding=10,
                    ),
                )
            ]
            if conversation_id != listen.DEFAULT_CONVERSATION_ID:
                row_controls.append(
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color="white54",
                        icon_size=17,
                        tooltip="Удалить чат",
                        on_click=lambda _, item_id=conversation_id: (
                            confirm_delete_chat(item_id)
                        ),
                    )
                )
            conversation_list.controls.append(ft.Row(row_controls, spacing=2))
        conversation_list.update()

    def toggle_drawer(force=None):
        should_open = drawer.width == 0 if force is None else force
        drawer.width = 258 if should_open else 0
        drawer.opacity = 1 if should_open else 0
        drawer.padding = 10 if should_open else 0
        drawer.offset = (0, 0) if should_open else (-0.12, 0)
        drawer.update()

    def create_new_chat():
        cancel_response()
        conversation_state["id"] = listen.create_conversation()
        conversation_title.value = "Новый чат"
        refresh_history(force=True)
        refresh_conversations(force=True)
        toggle_drawer(False)
        status_text.value = ""
        page.update()

    def clear_current_chat(_=None):
        cancel_response()
        listen.clear_conversation(conversation_state["id"])
        conversation_title.value = (
            "Голосовой диалог"
            if conversation_state["id"] == listen.DEFAULT_CONVERSATION_ID
            else "Новый чат"
        )
        refresh_history(force=True)
        refresh_conversations(force=True)
        page.close(clear_dialog)
        status_text.value = "История чата очищена."
        page.update()

    def confirm_clear_chat(_=None):
        page.open(clear_dialog)

    clear_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Очистить историю?"),
        content=ft.Text("Сообщения в этом чате будут удалены без возможности восстановления."),
        actions=[
            ft.TextButton("Отмена", on_click=lambda _: page.close(clear_dialog)),
            ft.TextButton("Очистить", on_click=clear_current_chat),
        ],
    )

    def confirm_delete_chat(conversation_id):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Удалить чат?"),
            content=ft.Text("Будут удалены чат и все его сообщения."),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.close(dialog)),
                ft.TextButton(
                    "Удалить",
                    on_click=lambda _: delete_chat(conversation_id, dialog),
                ),
            ],
        )
        page.open(dialog)

    def delete_chat(conversation_id, dialog):
        if conversation_state["id"] == conversation_id:
            cancel_response()
        listen.delete_conversation(conversation_id)
        if conversation_state["id"] == conversation_id:
            conversation_state["id"] = listen.DEFAULT_CONVERSATION_ID
            conversation_title.value = "Голосовой диалог"
            refresh_history(force=True)
        page.close(dialog)
        refresh_conversations(force=True)
        page.update()

    async def watch_history():
        while True:
            await asyncio.sleep(1.2)
            refresh_conversations()
            if cancel_state["event"] is None:
                conversations = listen.list_conversations()
                selected = next(
                    (
                        item for item in conversations
                        if item["id"] == conversation_state["id"]
                    ),
                    None,
                )
                if selected:
                    conversation_title.value = selected["title"]
                refresh_history()

    def cancel_response(_=None):
        cancellation = cancel_state["event"]
        if cancellation is not None:
            cancellation.cancel()

    def handle_window_event(event):
        if event.data == "close":
            logger.info("Пользователь закрыл отдельное окно чата")
            window_state["closed"] = True
            cancel_response()
            page.window.prevent_close = False
            page.window.destroy()

    page.window.on_event = handle_window_event

    cancel_button = ft.IconButton(
        icon=ft.Icons.STOP_CIRCLE_OUTLINED,
        icon_color="#ff7b86",
        tooltip="Остановить ответ",
        disabled=True,
        on_click=cancel_response,
    )

    def send_message(_=None, inspect_screen=False):
        text = (
            "Что сейчас отображено на экране?"
            if inspect_screen
            else (chat_input.value or "").strip()
        )
        if not text or cancel_state["event"] is not None:
            return

        chat_input.value = ""
        chat_input.focus()
        cancellation = listen.ResponseCancellation()
        cancel_state["event"] = cancellation
        active_conversation_id = conversation_state["id"]
        chat_list.controls.append(render_message("user", text))
        assistant_message = render_message("assistant", "")
        chat_list.controls.append(assistant_message)
        assistant_text = assistant_message.controls[0].content
        cancel_button.disabled = False
        status_text.value = "LUMI выполняет запрос…"
        page.update()

        def run_query():
            try:
                image = get_screen_image() if inspect_screen else None

                def append_response_chunk(chunk):
                    if window_state["closed"]:
                        return
                    assistant_text.value += chunk
                    chat_list.update()

                response = listen.process_text_query(
                    text,
                    screen_image=image,
                    on_delta=append_response_chunk,
                    cancel_event=cancellation,
                    conversation_id=active_conversation_id,
                )
                if assistant_text.value != response:
                    assistant_text.value = response
                if response.startswith(
                    ("Не удалось получить ответ от локальной нейросети Ollama:", "Ошибка ")
                ):
                    status_text.value = "Команда/запрос завершился ошибкой. Подробности — в log\\lumi.log."
                    logger.error("Ошибка ответа в отдельном чате: %s", response)
                else:
                    status_text.value = ""
                logger.info("Ответ в отдельном чате получен")
            except listen.ResponseCancelled:
                assistant_text.value = "Ответ остановлен."
                status_text.value = "Ответ остановлен."
            except Exception as error:
                logger.exception("Не удалось обработать сообщение отдельного чата")
                assistant_text.value = f"Не удалось получить ответ: {error}"
                status_text.value = f"Ошибка: {error}"
            finally:
                if cancel_state["event"] is cancellation:
                    cancel_state["event"] = None
                if not window_state["closed"]:
                    cancel_button.disabled = True
                    page.update()
                    if active_conversation_id == conversation_state["id"]:
                        refresh_history(force=True)
                    refresh_conversations(force=True)

        threading.Thread(
            target=run_query,
            daemon=True,
            name="lumi-chat-query",
        ).start()

    chat_stage = ft.Container(
        content=chat_list,
        expand=True,
        opacity=1,
        offset=(0, 0),
        animate_opacity=ft.Animation(180, ft.AnimationCurve.EASE_IN_OUT),
        animate_offset=ft.Animation(180, ft.AnimationCurve.EASE_IN_OUT),
    )

    def animate_chat_switch():
        chat_stage.opacity = 0.25
        chat_stage.offset = (0.04, 0)
        chat_stage.update()
        async def finish_transition():
            await asyncio.sleep(0.09)
            chat_stage.opacity = 1
            chat_stage.offset = (0, 0)
            chat_stage.update()

        page.run_task(finish_transition)

    # Animate the existing message surface without reparenting live controls.
    original_select = select_conversation

    def select_conversation(conversation_id):
        original_select(conversation_id)
        animate_chat_switch()

    original_create = create_new_chat

    def create_new_chat():
        original_create()
        animate_chat_switch()

    main_column = ft.Column(
        [
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.MENU,
                        icon_color=CYAN,
                        tooltip="История чатов",
                        on_click=lambda _: toggle_drawer(),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "LUMI · ЧАТ",
                                size=11,
                                color="white54",
                                weight=ft.FontWeight.BOLD,
                            ),
                            conversation_title,
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color="white70",
                        tooltip="Очистить историю этого чата",
                        on_click=confirm_clear_chat,
                    ),
                    cancel_button,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            status_text,
            ft.Divider(color="white12"),
            chat_stage,
            ft.Row(
                [
                    chat_input,
                    ft.IconButton(
                        icon=ft.Icons.VISIBILITY,
                        icon_color=CYAN,
                        tooltip="Спросить об экране",
                        on_click=lambda _: send_message(inspect_screen=True),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.SEND_ROUNDED,
                        icon_color=CYAN,
                        tooltip="Отправить",
                        on_click=send_message,
                    ),
                ]
            ),
        ],
        expand=True,
        spacing=8,
    )

    page.add(ft.Row([drawer, main_column], expand=True, spacing=8))
    refresh_history(force=True)
    refresh_conversations(force=True)
    page.run_task(watch_history)


if __name__ == "__main__":
    ft.app(target=main)
