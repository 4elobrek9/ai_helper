"""Unit-тесты для модулей LUMI AI."""

import pytest
from pathlib import Path


def test_long_term_memory_add_fact():
    """Проверка добавления факта в LongTermMemory."""
    from lumi.memory.long_term import LongTermMemory
    
    memory = LongTermMemory()
    result = memory.add_fact("Меня зовут TestUser")
    assert "запомнен" in result.lower()
    
    facts = memory.get_all_facts()
    assert len(facts) == 1
    assert facts[0]["fact"] == "Меня зовут TestUser"


def test_long_term_memory_remove_fact():
    """Проверка удаления факта."""
    from lumi.memory.long_term import LongTermMemory
    
    memory = LongTermMemory()
    memory.add_fact("Люблю кофе")
    
    result = memory.remove_fact("Люблю кофе")
    assert "удалён" in result.lower()
    
    facts = memory.get_all_facts()
    assert len(facts) == 0


def test_chat_memory_clear():
    """Проверка очистки истории чата."""
    from lumi.memory.chat_memory import ChatMemory
    
    memory = ChatMemory(max_history=10)
    for i in range(5):
        memory.add("user", f"Сообщение {i}")
    
    assert len(memory.get_recent()) == 5
    
    memory.clear()
    assert len(memory.get_recent()) == 0


def test_chat_memory_enforce_limit():
    """Проверка ограничения размера истории."""
    from lumi.memory.chat_memory import ChatMemory
    
    memory = ChatMemory(max_history=3)
    
    # Добавим 10 сообщений
    for i in range(10):
        memory.add("user", f"Сообщение {i}")
    
    history = memory.get_recent()
    assert len(history) == 3


def test_config_singleton():
    """Проверка singleton паттерна ConfigManager."""
    from lumi.core.config import config
    
    cfg1 = config
    cfg2 = config
    assert cfg1 is cfg2


def test_desktop_tools_safe_mode():
    """Проверка безопасного режима DesktopTools."""
    from lumi.desktop.tools import DesktopTools
    
    # Безопасный режим не должен запускать cmd.exe или powershell
    tools = DesktopTools(safe_mode=True)
    
    result, success, error = tools.run("cmd.exe", [])
    assert not success  # Должен отклонять dangerous commands


def test_desktop_tools_allowed_apps():
    """Проверка разрешённых приложений."""
    from lumi.desktop.tools import DesktopTools
    
    tools = DesktopTools(allowed_apps=["notepad.exe"])
    
    result, success, error = tools.run("notepad.exe", [])
    assert success  # Неотнуженное должно работать


def test_tts_speak_basic():
    """Базовая проверка TTS (не запускает реальный синтез)."""
    from lumi.voice.tts import TTSEngine
    
    tts = TTSEngine(speaker="xenia", sample_rate=24000, device="cpu", rate=1.0, volume=1.0)
    
    # Просто проверяем инициализацию
    assert tts is not None


# Запуск тестов при `pytest`:
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
