/* @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CONTROL_UI_BOOTSTRAP_CONFIG_PATH } from "./compat/gateway/control-ui-contract.js";
import { GATEWAY_EVENT_UPDATE_AVAILABLE } from "./compat/gateway/events.js";
import { ConnectErrorDetailCodes } from "./compat/gateway/protocol/connect-error-details.js";

describe("runtime-contracts", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses compat defaults before runtime contracts are loaded", async () => {
    const contracts = await import("./runtime-contracts.ts");

    expect(contracts.getControlUiBootstrapConfigPath()).toBe(CONTROL_UI_BOOTSTRAP_CONFIG_PATH);
    expect(contracts.getGatewayEventUpdateAvailable()).toBe(GATEWAY_EVENT_UPDATE_AVAILABLE);
    expect(contracts.getConnectErrorCode("AUTH_TOKEN_MISMATCH")).toBe(
      ConnectErrorDetailCodes.AUTH_TOKEN_MISMATCH,
    );
  });

  it("loads runtime contracts from backend endpoint with basePath", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        uiContracts: {
          controlUiBootstrapConfigPath: "/runtime/control-ui-config.json",
          gatewayEventUpdateAvailable: "runtime.update.available",
          connectErrorDetailCodes: {
            AUTH_TOKEN_MISMATCH: "AUTH_TOKEN_MISMATCH_RUNTIME",
          },
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    const contracts = await import("./runtime-contracts.ts");
    await contracts.loadUiRuntimeContracts("/openclaw/");

    expect(fetchMock).toHaveBeenCalledWith(
      "/openclaw/v1/runtime/ui-contracts",
      expect.objectContaining({ method: "GET" }),
    );
    expect(contracts.getControlUiBootstrapConfigPath()).toBe("/runtime/control-ui-config.json");
    expect(contracts.getGatewayEventUpdateAvailable()).toBe("runtime.update.available");
    expect(contracts.getConnectErrorCode("AUTH_TOKEN_MISMATCH")).toBe(
      "AUTH_TOKEN_MISMATCH_RUNTIME",
    );
    expect(contracts.getConnectErrorCode("AUTH_PASSWORD_MISMATCH")).toBe(
      ConnectErrorDetailCodes.AUTH_PASSWORD_MISMATCH,
    );
  });
});
