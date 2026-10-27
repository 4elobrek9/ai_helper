import asyncio
import logging
import webbrowser

import flet as ft

from app_paths import resource_path
from default_skills import DEFAULT_SKILLS, is_skill_enabled, set_skill_enabled
from piper_tts import VOICE_CATALOG, install_voice, is_voice_installed
from skills import add_user_skill, list_user_skills, remove_user_skill
import screensage


logger = logging.getLogger("lumi.skills_window")
CYAN = "#76e9ff"
BACKGROUND = "#0b0e17"


def main(page: ft.Page):
    page.title = "LUMI — Навыки"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BACKGROUND
    page.padding = 20
    page.window.width = 660
    page.window.height = 760
    page.window.min_width = 560
    page.window.min_height = 600
    page.window.resizable = True
    page.window.skip_task_bar = False
    page.window.icon = str(resource_path("app_icon.ico"))
    page.window.prevent_close = True
    window_state = {"closed": False}

    skill_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    status_text = ft.Text(size=12, color="white70")
    progress = ft.ProgressBar(value=0, color=CYAN, bgcolor="white12", visible=False)
    install_button = ft.ElevatedButton(
        "Установить",
        icon=ft.Icons.DOWNLOAD,
        bgcolor="#2388ff",
        color="white",
    )
    launch_button = ft.IconButton(
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        icon_color=CYAN,
        tooltip="Запустить ScreenSage",
    )
    remove_button = ft.IconButton(
        icon=ft.Icons.DELETE_OUTLINE,
        icon_color="white70",
        tooltip="Удалить ScreenSage",
    )
    github_button = ft.TextButton(
        "GitHub",
        icon=ft.Icons.OPEN_IN_NEW,
    )
    autostart_switch = ft.Switch(
        label="Запускать ScreenSage вместе с LUMI",
    )

    def notify(message):
        if window_state["closed"]:
            return
        page.snack_bar = ft.SnackBar(content=ft.Text(message))
        page.snack_bar.open = True
        page.update()

    def show_command_details(_=None):
        def set_command_enabled(event, skill_id):
            try:
                set_skill_enabled(skill_id, event.control.value)
            except Exception:
                logger.exception("Не удалось изменить встроенную команду %s", skill_id)
                notify("Не удалось сохранить настройку команды.")

        command_rows = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(command["name"], weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    command["description"],
                                    color="white60",
                                    size=11,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.Switch(
                            value=is_skill_enabled(command["id"]),
                            on_change=lambda event, skill_id=command["id"]: (
                                set_command_enabled(event, skill_id)
                            ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=10,
                bgcolor="white10",
                border_radius=12,
            )
            for command in DEFAULT_SKILLS
        ]
        dialog = ft.AlertDialog(
            title=ft.Text("Встроенные команды"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Включайте команды по отдельности. Остановка ответа "
                            "и список команд всегда доступны.",
                            color="white60",
                            size=12,
                        ),
                        *command_rows,
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    tight=True,
                ),
                width=500,
                height=500,
            ),
            actions=[ft.TextButton("Закрыть", on_click=lambda _: page.close(dialog))],
        )
        page.open(dialog)

    def refresh():
        skill_list.controls = [
            ft.Text(
                "ВСТРОЕННЫЕ КОМАНДЫ",
                color=CYAN,
                size=11,
                weight=ft.FontWeight.BOLD,
            )
        ]
        skill_list.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "Команды LUMI",
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    "Погода, экран, приложения и клавиатура. "
                                    "Шестерёнка откроет список команд и примеры.",
                                    color="white60",
                                    size=11,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS_OUTLINED,
                            tooltip="Настроить команды",
                            on_click=show_command_details,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=12,
                bgcolor=ft.Colors.with_opacity(0.46, "#23334a"),
                border=ft.border.all(1, "white12"),
                border_radius=16,
            )
        )
        skill_list.controls.append(
            ft.Text(
                "ЧТО НОВОГО · НАВЫКИ ОТ РАЗРАБОТЧИКА",
                color=CYAN,
                size=11,
                weight=ft.FontWeight.BOLD,
            )
        )
        skill_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            "ScreenSage",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Text(
                                            "Локальный инструмент для работы с экраном.",
                                            color="white60",
                                            size=11,
                                        ),
                                    ],
                                    expand=True,
                                ),
                                install_button,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        status_text,
                        progress,
                        ft.Row(
                            [
                                github_button,
                                launch_button,
                                remove_button,
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                        autostart_switch,
                        ft.Text(
                            "Автозапуск выключен по умолчанию. Перед запуском "
                            "стороннего EXE проверьте страницу проекта.",
                            color="white38",
                            size=10,
                        ),
                    ],
                    spacing=8,
                ),
                padding=14,
                bgcolor=ft.Colors.with_opacity(0.5, "#23334a"),
                border=ft.border.all(1, "white18"),
                border_radius=18,
            )
        )

        skill_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Голоса Piper · офлайн", weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Скачайте русскую модель и выберите её в настройках "
                            "LUMI как голос озвучивания.",
                            color="white60",
                            size=11,
                        ),
                        ft.Row(
                            [
                                piper_choice,
                                ft.ElevatedButton(
                                    "Скачать",
                                    icon=ft.Icons.DOWNLOAD,
                                    on_click=install_piper_voice,
                                ),
                            ]
                        ),
                        piper_status,
                        piper_progress,
                        ft.Text(
                            "Файлы модели проверяются по контрольным суммам.",
                            color="white38",
                            size=10,
                        ),
                    ],
                    spacing=8,
                ),
                padding=14,
                bgcolor=ft.Colors.with_opacity(0.5, "#23334a"),
                border=ft.border.all(1, "white18"),
                border_radius=18,
            )
        )

        skill_list.controls.append(
            ft.Row(
                [
                    ft.Text(
                        "НАВЫКИ СООБЩЕСТВА",
                        color=CYAN,
                        size=11,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                        icon_color=CYAN,
                        tooltip="Добавить свой навык",
                        on_click=lambda _: show_editor(True),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        )
        for skill in list_user_skills():
            skill_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        skill["name"],
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        skill["description"],
                                        color="white60",
                                        size=11,
                                    ),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                tooltip="Удалить",
                                on_click=lambda _, skill_id=skill["id"]: delete_skill(
                                    skill_id
                                ),
                            ),
                        ]
                    ),
                    padding=12,
                    bgcolor="white10",
                    border=ft.border.all(1, "white12"),
                    border_radius=16,
                )
            )

        if screensage.is_installed():
            status_text.value = f"Установлен: {screensage.executable_path()}"
            install_button.visible = False
            launch_button.visible = True
            remove_button.visible = True
            github_button.visible = True
            autostart_switch.disabled = False
            autostart_switch.value = screensage.is_autostart_enabled()
        else:
            status_text.value = (
                "EXE скачивается только по кнопке; SHA-256 сверяется "
                "с GitHub Releases."
            )
            install_button.visible = True
            launch_button.visible = False
            remove_button.visible = False
            github_button.visible = False
            autostart_switch.disabled = True
            autostart_switch.value = False
        skill_list.update()

    name_input = ft.TextField(label="Название навыка", max_length=60)
    description_input = ft.TextField(
        label="Описание / инструкции",
        multiline=True,
        min_lines=2,
        max_lines=4,
        max_length=500,
    )
    executable_input = ft.TextField(
        label="Путь к своему .exe (необязательно)",
        hint_text=r"C:\Apps\MyApp\MyApp.exe",
    )
    editor = ft.Column(
        [
            name_input,
            description_input,
            executable_input,
            ft.Row(
                [
                    ft.ElevatedButton("Сохранить", on_click=lambda _: save_skill()),
                    ft.TextButton("Отмена", on_click=lambda _: show_editor(False)),
                ]
            ),
        ],
        visible=False,
    )

    def show_editor(visible):
        editor.visible = visible
        editor.update()

    def save_skill():
        try:
            add_user_skill(
                name_input.value,
                description_input.value,
                executable_input.value,
            )
        except ValueError as error:
            notify(str(error))
            return
        except Exception:
            logger.exception("Не удалось сохранить пользовательский навык")
            notify("Не удалось сохранить навык.")
            return
        name_input.value = ""
        description_input.value = ""
        executable_input.value = ""
        show_editor(False)
        refresh()
        notify("Навык сохранён.")

    def delete_skill(skill_id):
        try:
            remove_user_skill(skill_id)
        except Exception:
            logger.exception("Не удалось удалить пользовательский навык")
            notify("Не удалось удалить навык.")
            return
        refresh()
        notify("Навык удалён.")

    async def install_screensage(_):
        install_button.disabled = True
        progress.visible = True
        progress.value = 0
        status_text.value = "Получаю сведения о релизе ScreenSage…"
        page.update()
        loop = asyncio.get_running_loop()

        def update_progress(downloaded, total):
            fraction = downloaded / total if total else None
            loop.call_soon_threadsafe(
                set_download_progress,
                fraction,
                downloaded,
                total,
            )

        try:
            await asyncio.to_thread(screensage.download_latest, update_progress)
        except Exception as error:
            logger.exception("Не удалось установить ScreenSage")
            status_text.value = f"Ошибка установки: {error}"
            notify(f"Не удалось установить ScreenSage: {error}")
        else:
            status_text.value = "Загрузка завершена, SHA-256 проверен."
            progress.value = 1
            notify("ScreenSage установлен и проверен.")
        finally:
            install_button.disabled = False
            progress.visible = False
            refresh()
            page.update()

    def set_download_progress(fraction, downloaded, total):
        progress.value = fraction
        status_text.value = (
            f"Загрузка ScreenSage: {downloaded / 1024 / 1024:.1f} / "
            f"{total / 1024 / 1024:.1f} МБ"
        )
        progress.update()
        status_text.update()

    def launch_screensage(_):
        try:
            screensage.launch()
        except Exception as error:
            logger.exception("Не удалось запустить ScreenSage")
            notify(f"Не удалось запустить ScreenSage: {error}")

    def remove_screensage(_):
        try:
            screensage.remove()
        except Exception as error:
            logger.exception("Не удалось удалить ScreenSage")
            notify(f"Не удалось удалить ScreenSage: {error}")
            return
        refresh()
        notify("ScreenSage удалён.")

    def open_github(_):
        webbrowser.open(screensage.GITHUB_PAGE)

    def set_autostart(event):
        try:
            screensage.set_autostart_enabled(event.control.value)
        except Exception:
            logger.exception("Не удалось сохранить автозапуск ScreenSage")
            notify("Не удалось сохранить настройку автозапуска.")

    install_button.on_click = install_screensage
    launch_button.on_click = launch_screensage
    remove_button.on_click = remove_screensage
    github_button.on_click = open_github
    autostart_switch.on_change = set_autostart

    def piper_label(voice_name):
        return VOICE_CATALOG[voice_name]["label"]

    piper_choice = ft.Dropdown(
        label="Голос Piper (русский, локально)",
        options=[
            ft.dropdown.Option(key=name, text=piper_label(name))
            for name in VOICE_CATALOG
        ],
        value=next(iter(VOICE_CATALOG)),
        expand=True,
    )
    piper_status = ft.Text(size=11, color="white60")
    piper_progress = ft.ProgressBar(value=0, color=CYAN, visible=False)

    def refresh_piper_status():
        voice_name = piper_choice.value
        if is_voice_installed(voice_name):
            piper_status.value = f"Установлен: {piper_label(voice_name)}"
        else:
            piper_status.value = (
                f"Голос занимает около 63 МБ. Источник: Hugging Face / "
                f"{voice_name}."
            )

    async def install_piper_voice(_):
        voice_name = piper_choice.value
        piper_progress.visible = True
        piper_progress.value = 0
        piper_status.value = "Получаю метаданные целостности голоса…"
        page.update()
        loop = asyncio.get_running_loop()

        def update_progress(downloaded, total):
            if window_state["closed"]:
                return
            try:
                loop.call_soon_threadsafe(
                    set_piper_progress,
                    downloaded / total if total else None,
                    downloaded,
                    total,
                )
            except RuntimeError:
                if not window_state["closed"]:
                    raise

        try:
            await asyncio.to_thread(install_voice, voice_name, update_progress)
        except Exception as error:
            logger.exception("Не удалось установить голос Piper")
            if window_state["closed"]:
                return
            piper_status.value = f"Ошибка установки Piper: {error}"
            notify(f"Не удалось установить голос Piper: {error}")
        else:
            if window_state["closed"]:
                return
            piper_status.value = (
                f"{piper_label(voice_name)} установлен. Выберите его "
                "в настройках LUMI."
            )
            piper_progress.value = 1
            notify("Голос Piper установлен и проверен.")
        finally:
            if not window_state["closed"]:
                piper_progress.visible = False
                piper_progress.update()
                piper_status.update()

    def set_piper_progress(fraction, downloaded, total):
        if window_state["closed"]:
            return
        piper_progress.value = fraction
        piper_status.value = (
            f"Загрузка Piper: {downloaded / 1024 / 1024:.1f} / "
            f"{total / 1024 / 1024:.1f} МБ"
        )
        piper_progress.update()
        piper_status.update()

    piper_choice.on_change = lambda _: refresh_piper_status()
    refresh_piper_status()

    def handle_window_event(event):
        if event.data == "close":
            logger.info("Пользователь закрыл отдельное окно навыков")
            window_state["closed"] = True
            page.window.prevent_close = False
            page.window.destroy()

    page.window.on_event = handle_window_event

    page.add(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "НАВЫКИ LUMI",
                                    size=22,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    "Встроенные команды, навыки сообщества и новые возможности",
                                    color="white60",
                                    size=11,
                                ),
                            ],
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.AUTO_AWESOME, color=CYAN, size=30),
                    ]
                ),
                ft.Divider(color="white12"),
                skill_list,
                editor,
            ],
            expand=True,
            spacing=12,
        )
    )
    refresh()


if __name__ == "__main__":
    ft.app(target=main)
