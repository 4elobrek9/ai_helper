"""Кастомные виджеты для интерфейса LUMI AI."""

from __future__ import annotations

import flet as ft

CYAN = "#00D4FF"
CYAN_GLOW = "#00D4FF40"
DARK_BG = "#0f0f13"
PANEL_BG = "#1a1a24"


def status_indicator(status: str = "Готов", color: str = CYAN) -> ft.Container:
    """Индикатор состояния с пульсацией."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=8, height=8, bgcolor=color, border_radius=4),
                ft.Text(status, size=12, color="white70", weight="w500"),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        ),
        padding=ft.padding.symmetric(horizontal=12, vertical=6),
        bgcolor=PANEL_BG,
        border_radius=20,
        border=ft.border.all(1, color),
    )


def message_bubble(text: str, is_user: bool = False) -> ft.Row:
    """Пузырь сообщения в чате."""
    bubble = ft.Container(
        content=ft.Text(
            text,
            color="white" if is_user else "white80",
            size=13,
            selectable=True,
        ),
        bgcolor="#1a1a24" if is_user else "#2a2a3e",
        padding=12,
        border_radius=ft.border_radius.only(
            top_left=15,
            top_right=15,
            bottom_left=15 if is_user else 0,
            bottom_right=0 if is_user else 15,
        ),
        width=250,
    )
    alignment = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
    return ft.Row(controls=[bubble], alignment=alignment)


def tool_call_widget(tool_name: str, status: str = "Выполняется…") -> ft.Container:
    """Виджет вызова инструмента в чате."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.TUNE, size=16, color=CYAN),
                ft.Text(f"🔧 {tool_name}", size=12, color=CYAN, weight="w500"),
                ft.Text(status, size=11, color="white54"),
            ],
            spacing=6,
        ),
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        bgcolor="#2a2a3e",
        border_radius=10,
        margin=ft.margin.only(left=10, right=10, top=4, bottom=4),
    )