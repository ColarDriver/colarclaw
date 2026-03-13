from __future__ import annotations

from fastapi import Depends, Request

from ..core.auth import AuthContext, require_auth


def get_container(request: Request):
    return request.app.state.container


def get_auth_context(context: AuthContext = Depends(require_auth)) -> AuthContext:
    return context
