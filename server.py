"""Iris Agent FastAPI compatibility entry point."""

from dotenv import load_dotenv

from iris_agent.api.app import create_app
from iris_agent.bootstrap import build_application

load_dotenv()
service, sessions, settings = build_application()
app = create_app(service, sessions)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
