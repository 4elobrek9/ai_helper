import unittest
from unittest.mock import patch

from PIL import Image

import desktop_agent


class DesktopAgentTests(unittest.TestCase):
    def test_extracts_only_supported_execution_blocks(self):
        answer = (
            "I will do this:\n"
            "```python\nprint('one')\n```\n"
            "```javascript\nconsole.log('ignored')\n```\n"
            "```powershell\nWrite-Output 'two'\n```"
        )
        self.assertEqual(
            desktop_agent._extract_code_blocks(answer),
            [("python", "print('one')"), ("powershell", "Write-Output 'two'")],
        )

    def test_detects_actions_and_rejects_read_only_code_for_file_changes(self):
        self.assertFalse(desktop_agent._code_changes_state(
            "content = Path('file.txt').read_text()"
        ))
        self.assertTrue(desktop_agent._code_changes_state(
            "Path('file.txt').write_text('value')"
        ))
        self.assertTrue(desktop_agent._code_changes_state(
            'computer.click_screen("A1")'
        ))
        self.assertTrue(desktop_agent.request_changes_state("создай файл result.txt"))

    def test_normalizes_and_scales_screen_map_coordinates(self):
        image = Image.new("RGB", (1920, 1080))
        screen = desktop_agent._normalize_screen_map(
            {
                "screen_width": 960,
                "screen_height": 540,
                "elements": [{
                    "label": "Search",
                    "bbox": [10, 20, 110, 120],
                    "center": [1000, 1000],
                    "confidence": "invalid",
                    "actionable": True,
                }],
            },
            image,
            960,
            540,
        )
        element = screen["elements"][0]
        self.assertEqual(element["bbox"], [20, 40, 220, 240])
        self.assertEqual(element["center"], [220, 240])
        self.assertEqual(element["confidence"], 0)

    def test_clicks_only_a_current_actionable_screen_label(self):
        old_map = desktop_agent._screen_map.copy()
        desktop_agent._screen_map = {
            "elements": [{
                "id": "A1", "label": "Search", "center": [150, 80],
                "actionable": True,
            }]
        }
        try:
            with patch.object(desktop_agent.COMPUTER.mouse, "click") as click:
                desktop_agent.COMPUTER.click_screen("A1")
            click.assert_called_once_with(150, 80, clicks=1, button="left")
            with self.assertRaises(ValueError):
                desktop_agent.COMPUTER.click_screen("unknown")
        finally:
            desktop_agent._screen_map = old_map

    def test_executes_sequential_steps_and_feeds_back_results(self):
        answers = [
            "```python\nprint('step one')\n```",
            "```powershell\nWrite-Output 'step two'\n```",
            "Выполнено, оба шага проверены.",
        ]
        history = []
        with patch.object(desktop_agent, "_ollama_chat", side_effect=answers) as llm, \
                patch.object(desktop_agent, "_execute", side_effect=[
                    {"ok": True, "returncode": 0, "stdout": "step one", "stderr": ""},
                    {"ok": True, "returncode": 0, "stdout": "step two", "stderr": ""},
                ]) as execute:
            result = desktop_agent.run_agent_turn(history, "Выполни два последовательных шага")

        self.assertIn("Шаг 1: выполнено", result)
        self.assertIn("Шаг 2: выполнено", result)
        self.assertIn("Выполнено", result)
        self.assertEqual(execute.call_count, 2)
        self.assertTrue(any(
            "step one" in message.get("content", "")
            for message in llm.call_args_list[1].args[1]
        ))
        self.assertEqual(history[-1]["role"], "assistant")

    def test_executes_local_python_and_captures_output(self):
        result = desktop_agent._execute("python", "print('local execution works')")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "local execution works")


if __name__ == "__main__":
    unittest.main()
