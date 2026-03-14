import { CONTROL_UI_BOOTSTRAP_CONFIG_PATH } from "./compat/gateway/control-ui-contract.js";
import { GATEWAY_EVENT_UPDATE_AVAILABLE } from "./compat/gateway/events.js";
import {
  GATEWAY_CLIENT_MODES,
  GATEWAY_CLIENT_NAMES,
  normalizeGatewayClientMode,
  normalizeGatewayClientName,
  type GatewayClientMode,
  type GatewayClientName,
} from "./compat/gateway/protocol/client-info.js";
import { ConnectErrorDetailCodes } from "./compat/gateway/protocol/connect-error-details.js";
import { normalizeBasePath } from "./navigation.ts";

const UI_RUNTIME_CONTRACTS_PATH = "/v1/runtime/ui-contracts";

export type ConnectErrorDetailCodeName = keyof typeof ConnectErrorDetailCodes;

type UiRuntimeContractsPayload = {
  controlUiBootstrapConfigPath: string;
  gatewayEventUpdateAvailable: string;
  gatewayClientNames: Record<string, string>;
  gatewayClientModes: Record<string, string>;
  connectErrorDetailCodes: Record<string, string>;
};

const CONNECT_ERROR_DETAIL_CODE_KEYS = Object.keys(
  ConnectErrorDetailCodes,
) as ConnectErrorDetailCodeName[];

let runtimeContracts: UiRuntimeContractsPayload = {
  controlUiBootstrapConfigPath: CONTROL_UI_BOOTSTRAP_CONFIG_PATH,
  gatewayEventUpdateAvailable: GATEWAY_EVENT_UPDATE_AVAILABLE,
  gatewayClientNames: { ...GATEWAY_CLIENT_NAMES },
  gatewayClientModes: { ...GATEWAY_CLIENT_MODES },
  connectErrorDetailCodes: { ...ConnectErrorDetailCodes },
};

function normalizeString(value: unknown, fallback: string): string {
  if (typeof value !== "string") {
    return fallback;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeStringRecord(
  value: unknown,
  fallback: Record<string, string>,
): Record<string, string> {
  const merged: Record<string, string> = { ...fallback };
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return merged;
  }
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry !== "string") {
      continue;
    }
    const trimmed = entry.trim();
    if (trimmed.length === 0) {
      continue;
    }
    merged[key] = trimmed;
  }
  return merged;
}

function applyUiRuntimeContracts(value: unknown): void {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return;
  }
  const contracts = value as Partial<UiRuntimeContractsPayload>;
  runtimeContracts = {
    controlUiBootstrapConfigPath: normalizeString(
      contracts.controlUiBootstrapConfigPath,
      CONTROL_UI_BOOTSTRAP_CONFIG_PATH,
    ),
    gatewayEventUpdateAvailable: normalizeString(
      contracts.gatewayEventUpdateAvailable,
      GATEWAY_EVENT_UPDATE_AVAILABLE,
    ),
    gatewayClientNames: normalizeStringRecord(contracts.gatewayClientNames, GATEWAY_CLIENT_NAMES),
    gatewayClientModes: normalizeStringRecord(contracts.gatewayClientModes, GATEWAY_CLIENT_MODES),
    connectErrorDetailCodes: normalizeStringRecord(
      contracts.connectErrorDetailCodes,
      ConnectErrorDetailCodes,
    ),
  };
}

export async function loadUiRuntimeContracts(basePath: string): Promise<void> {
  if (typeof window === "undefined" || typeof fetch !== "function") {
    return;
  }
  const normalizedBasePath = normalizeBasePath(basePath ?? "");
  const url = normalizedBasePath
    ? `${normalizedBasePath}${UI_RUNTIME_CONTRACTS_PATH}`
    : UI_RUNTIME_CONTRACTS_PATH;
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) {
      return;
    }
    const parsed = await response.json();
    const contracts =
      parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as { uiContracts?: unknown }).uiContracts
        : undefined;
    applyUiRuntimeContracts(contracts);
  } catch {
    // Ignore contract bootstrap failures; UI falls back to compat constants.
  }
}

export function getControlUiBootstrapConfigPath(): string {
  return runtimeContracts.controlUiBootstrapConfigPath;
}

export function getGatewayEventUpdateAvailable(): string {
  return runtimeContracts.gatewayEventUpdateAvailable;
}

export function getGatewayClientNameControlUi(): GatewayClientName {
  const raw = runtimeContracts.gatewayClientNames.CONTROL_UI;
  return normalizeGatewayClientName(raw) ?? GATEWAY_CLIENT_NAMES.CONTROL_UI;
}

export function getGatewayClientModeWebchat(): GatewayClientMode {
  const raw = runtimeContracts.gatewayClientModes.WEBCHAT;
  return normalizeGatewayClientMode(raw) ?? GATEWAY_CLIENT_MODES.WEBCHAT;
}

export function getConnectErrorCode(name: ConnectErrorDetailCodeName): string {
  const raw = runtimeContracts.connectErrorDetailCodes[name];
  const fallback = ConnectErrorDetailCodes[name];
  return normalizeString(raw, fallback);
}

export function getConnectErrorCodesSnapshot(): Record<ConnectErrorDetailCodeName, string> {
  const snapshot = {} as Record<ConnectErrorDetailCodeName, string>;
  for (const key of CONNECT_ERROR_DETAIL_CODE_KEYS) {
    snapshot[key] = getConnectErrorCode(key);
  }
  return snapshot;
}
