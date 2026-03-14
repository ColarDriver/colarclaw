from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.rest.chat import router as chat_router
from .api.rest.health import router as health_router
from .api.rest.runtime_config import router as runtime_router
from .api.rest.sessions import router as sessions_router
from .api.rest.settings import router as settings_router
from .api.rest.tools import router as tools_router
from .api.rest.ui_contracts import router as ui_contracts_router
from .api.ws.chat_stream import router as ws_router
from .container import build_container
from .core.config import load_settings
from .core.logging import configure_logging


def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging()

    app = FastAPI(title="OpenClaw Python Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.container = build_container(settings)

    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(tools_router)
    app.include_router(settings_router)
    app.include_router(runtime_router)
    app.include_router(ui_contracts_router)
    app.include_router(ws_router)
    return app


app: FastAPI | None = None


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
