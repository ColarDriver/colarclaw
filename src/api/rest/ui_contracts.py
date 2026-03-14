from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_auth_context
from ...gateway.protocol import (
    ConnectErrorDetailCodes,
    GATEWAY_CLIENT_MODES,
    GATEWAY_CLIENT_NAMES,
)
from ...schemas.ui_contracts import UiRuntimeContractsView

router = APIRouter(prefix="/v1/runtime", tags=["runtime"])

CONTROL_UI_BOOTSTRAP_CONFIG_PATH = "/__openclaw/control-ui-config.json"
GATEWAY_EVENT_UPDATE_AVAILABLE = "update.available"


def _connect_error_detail_codes() -> dict[str, str]:
    entries: dict[str, str] = {}
    for key, value in vars(ConnectErrorDetailCodes).items():
        if key.isupper() and isinstance(value, str):
            entries[key] = value
    return dict(sorted(entries.items()))


@router.get("/ui-contracts")
async def get_ui_contracts(_auth=Depends(get_auth_context)) -> dict[str, object]:
    view = UiRuntimeContractsView(
        controlUiBootstrapConfigPath=CONTROL_UI_BOOTSTRAP_CONFIG_PATH,
        gatewayEventUpdateAvailable=GATEWAY_EVENT_UPDATE_AVAILABLE,
        gatewayClientNames=dict(GATEWAY_CLIENT_NAMES),
        gatewayClientModes=dict(GATEWAY_CLIENT_MODES),
        connectErrorDetailCodes=_connect_error_detail_codes(),
    )
    return {"uiContracts": view.model_dump()}
