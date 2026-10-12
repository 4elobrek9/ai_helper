"""Console chat using the same local computer agent as the GUI."""

from listen import process_text_query


def main():
    print("LUMI — локальный Ollama-агент. Введите 'exit' для выхода.")
    while True:
        try:
            user_input = input("Вы> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if user_input.lower() in {"exit", "quit", "выход"}:
            break
        if not user_input:
            continue
        print("Lumi>", process_text_query(user_input))


if __name__ == "__main__":
    main()
