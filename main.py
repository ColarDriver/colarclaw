from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from src.app import create_app, get_app
from src.core.config import load_settings

# Keep a module-level ASGI symbol for `uvicorn main:app` and tests.
app: FastAPI = get_app()


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env == "dev",
    )


if __name__ == "__main__":
    main()
