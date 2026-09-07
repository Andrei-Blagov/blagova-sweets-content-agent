"""
ASGI / process entrypoint.

  uvicorn main:app --host 0.0.0.0 --port 8090
  python main.py
"""

from __future__ import annotations

import os

from app.api import create_app
from app.config import get_settings

app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    host = os.getenv("APP_HOST", settings.app_host)
    port = int(os.getenv("APP_PORT", str(settings.app_port)))
    uvicorn.run("main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
