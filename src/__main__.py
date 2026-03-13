from __future__ import annotations

import uvicorn

from .core.config import load_settings


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
