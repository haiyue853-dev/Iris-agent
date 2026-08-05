from dotenv import load_dotenv

from iris_agent.bootstrap import build_application


def main() -> None:
    load_dotenv()
    application = build_application()
    service = application.agent
    sessions = application.sessions
    session = sessions.create("CLI 会话")
    print("Iris Agent（输入 quit 退出，new 新建会话）")
    while True:
        try:
            text = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            return
        if not text:
            continue
        if text.lower() in {"quit", "exit", "q"}:
            return
        if text.lower() == "new":
            session = sessions.create("CLI 会话")
            print("已创建新会话")
            continue
        print("Iris: ", end="", flush=True)
        for event in service.run(session.id, text):
            if event.type == "text_delta":
                print(event.data.get("content", ""), end="", flush=True)
            elif event.type == "error":
                print(f"\n错误: {event.data.get('message', '')}", end="")
        print()
