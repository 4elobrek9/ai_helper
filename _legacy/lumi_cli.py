import argparse
import asyncio

from voice_architecture import ConfigLoader, LumiVoiceLoop


def cmd_show_config(path: str):
    cfg = ConfigLoader(path).load()
    for section in ["assistant", "wake_word", "vad", "stt", "tts", "llm", "cache"]:
        print(f"[{section}] {getattr(cfg, section)}")


async def cmd_chat(path: str):
    loader = ConfigLoader(path)
    app = LumiVoiceLoop(loader)
    print("Lumi CLI ready. Type 'exit' to quit.")
    while True:
        text = input("you> ").strip()
        if text.lower() in {"exit", "quit"}:
            break
        answer = await app.handle_text(text)
        print(f"lumi> {answer}")


def main():
    parser = argparse.ArgumentParser(description="Lumi CLI")
    parser.add_argument("--config", default="lumi_config.yaml")
    parser.add_argument("--mode", choices=["show-config", "chat", "voice"], default="chat")
    args = parser.parse_args()

    if args.mode == "show-config":
        cmd_show_config(args.config)
    elif args.mode == "chat":
        asyncio.run(cmd_chat(args.config))
    else:
        asyncio.run(LumiVoiceLoop(ConfigLoader(args.config)).run_forever())


if __name__ == "__main__":
    main()
