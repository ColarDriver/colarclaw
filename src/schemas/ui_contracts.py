from __future__ import annotations

from pydantic import BaseModel, Field


class UiRuntimeContractsView(BaseModel):
    controlUiBootstrapConfigPath: str
    gatewayEventUpdateAvailable: str
    gatewayClientNames: dict[str, str] = Field(default_factory=dict)
    gatewayClientModes: dict[str, str] = Field(default_factory=dict)
    connectErrorDetailCodes: dict[str, str] = Field(default_factory=dict)
