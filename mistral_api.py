"""Compatibility adapter for legacy imports; all completions stay local."""

import desktop_agent


def chat_with_mistral(prompt, memory=None):
    """Return the old response shape while using the configured local Ollama."""
    messages = list(memory or [])
    if not messages or messages[-1].get("content") != prompt:
        messages.append({"role": "user", "content": prompt})
    answer = desktop_agent._ollama_chat(desktop_agent.MAIN_MODEL, messages)
    return {"choices": [{"message": {"content": answer}}]}


if __name__ == "__main__":
    print(chat_with_mistral("Привет"))
