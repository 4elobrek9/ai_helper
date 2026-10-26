"""Система tool-calling для LLM: парсинг, выполнение, логирование, retry."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from lumi.core.logging import get_logger
from lumi.desktop.tools import DesktopTools

logger = get_logger("llm.tools")


@dataclass
class ToolCall:
    """Представление вызова инструмента."""

    name: str
    arguments: dict[str, Any]
    raw_text: str = ""
    call_id: str = field(default_factory=lambda: str(__import__("uuid").uuid4())[:8])


@dataclass
class ToolResult:
    """Результат выполнения инструмента."""

    call_id: str
    name: str
    success: bool
    result: str = ""
    error: str = ""
    executed: bool = False


class ToolRegistry:
    """Реестр инструментов с логированием и retry."""

    def __init__(self, desktop_tools: DesktopTools, max_retries: int = 2) -> None:
        self.desktop = desktop_tools
        self.max_retries = max_retries
        self._handlers: dict[str, Callable[..., str]] = {}
        self._register_builtin_tools()
        self.call_history: list[ToolResult] = []

    def _register_builtin_tools(self) -> None:
        """Регистрирует все встроенные инструменты desktop."""
        tools = {
            "inspect_screen": self.desktop.inspect_screen,
            "open_application": self.desktop.open_application,
            "click_text": self.desktop.click_text,
            "move_to_text": self.desktop.move_to_text,
            "type_text": self.desktop.type_text,
            "press_keys": self.desktop.press_keys,
            "get_clipboard": self.desktop.get_clipboard,
            "set_clipboard": self.desktop.set_clipboard,
            "open_url": self.desktop.open_url,
            "search_web": self.desktop.search_web,
            "list_running_apps": self.desktop.list_running_apps,
            "focus_window": self.desktop.focus_window,
            "minimize_window": self.desktop.minimize_window,
            "close_window": self.desktop.close_window,
            "take_screenshot": self.desktop.take_screenshot,
            "read_file": self.desktop.read_file,
            "write_file": self.desktop.write_file,
        }
        self._handlers.update(tools)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Возвращает схемы всех инструментов для передачи в LLM."""
        descriptions = self.desktop.get_tool_descriptions()
        schemas = []
        for name, desc in descriptions.items():
            schemas.append({
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            })
        return schemas

    def get_tool_descriptions_text(self) -> str:
        """Возвращает текстовое описание всех инструментов для промпта."""
        descriptions = self.desktop.get_tool_descriptions()
        lines = ["Доступные инструменты (используйте формат: ИНСТРУМЕНТ: аргументы):"]
        for name, desc in descriptions.items():
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)

    def parse_tool_calls(self, text: str) -> list[ToolCall]:
        """Парсит вызовы инструментов из текста ответа LLM."""
        calls: list[ToolCall] = []

        pattern = r"<tool_call>\s*\{.*?\}\s*</tool_call>"
        for match in re.finditer(pattern, text, re.DOTALL):
            try:
                data = json.loads(match.group(0).replace("<tool_call>", "").replace("</tool_call>", "").strip())
                calls.append(ToolCall(
                    name=data.get("name", ""),
                    arguments=data.get("arguments", {}),
                    raw_text=match.group(0),
                ))
            except Exception as e:
                logger.warning(f"Ошибка парсинга tool_call XML: {e}")

        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if ":" in line and not line.startswith("http"):
                parts = line.split(":", 1)
                tool_name = parts[0].strip()
                tool_args_str = parts[1].strip() if len(parts) > 1 else ""
                if tool_name in self._handlers:
                    calls.append(ToolCall(
                        name=tool_name,
                        arguments=self._parse_args(tool_args_str),
                        raw_text=line,
                    ))

        seen = set()
        unique = []
        for call in calls:
            if call.call_id not in seen:
                seen.add(call.call_id)
                unique.append(call)

        return unique

    def _parse_args(self, args_str: str) -> dict[str, Any]:
        """Парсит аргументы из строки."""
        if not args_str:
            return {}
        try:
            return json.loads(args_str)
        except Exception:
            result = {}
            for part in args_str.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    result[k.strip()] = v.strip()
            return result

    def execute(self, call: ToolCall) -> ToolResult:
        """Выполняет один вызов инструмента с retry и логированием."""
        result = ToolResult(call_id=call.call_id, name=call.name)

        if call.name not in self._handlers:
            result.error = f"Неизвестный инструмент: {call.name}"
            logger.warning(result.error)
            self.call_history.append(result)
            return result

        handler = self._handlers[call.name]
        last_error = ""

        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"Вызов инструмента [{call.call_id}] {call.name}(args={call.arguments}) попытка {attempt + 1}")
                output = handler(**call.arguments)
                result.success = True
                result.result = output
                result.executed = True
                logger.info(f"Инструмент [{call.call_id}] {call.name} выполнен успешно")
                break
            except TypeError as e:
                last_error = str(e)
                logger.warning(f"Ошибка аргументов [{call.call_id}] {call.name}: {e}")
                if attempt < self.max_retries:
                    continue
                break
            except Exception as e:
                last_error = str(e)
                logger.error(f"Ошибка выполнения [{call.call_id}] {call.name} попытка {attempt + 1}: {e}")
                if attempt < self.max_retries:
                    continue
                break

        if not result.success:
            result.error = last_error or "Неизвестная ошибка"

        self.call_history.append(result)
        return result

    def execute_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Выполняет список вызовов инструментов."""
        return [self.execute(call) for call in calls]

    def get_history(self, limit: int = 50) -> list[ToolResult]:
        """Возвращает историю вызовов инструментов."""
        return self.call_history[-limit:]

    def clear_history(self) -> None:
        """Очищает историю вызовов."""
        self.call_history.clear()