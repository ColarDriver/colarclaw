import { getConnectErrorCode, type ConnectErrorDetailCodeName } from "../runtime-contracts.ts";

const AUTH_REQUIRED_CODE_NAMES: ConnectErrorDetailCodeName[] = [
  "AUTH_REQUIRED",
  "AUTH_TOKEN_MISSING",
  "AUTH_PASSWORD_MISSING",
  "AUTH_TOKEN_NOT_CONFIGURED",
  "AUTH_PASSWORD_NOT_CONFIGURED",
];

const AUTH_FAILURE_CODE_NAMES: ConnectErrorDetailCodeName[] = [
  ...AUTH_REQUIRED_CODE_NAMES,
  "AUTH_UNAUTHORIZED",
  "AUTH_TOKEN_MISMATCH",
  "AUTH_PASSWORD_MISMATCH",
  "AUTH_DEVICE_TOKEN_MISMATCH",
  "AUTH_RATE_LIMITED",
  "AUTH_TAILSCALE_IDENTITY_MISSING",
  "AUTH_TAILSCALE_PROXY_MISSING",
  "AUTH_TAILSCALE_WHOIS_FAILED",
  "AUTH_TAILSCALE_IDENTITY_MISMATCH",
];

const INSECURE_CONTEXT_CODE_NAMES: ConnectErrorDetailCodeName[] = [
  "CONTROL_UI_DEVICE_IDENTITY_REQUIRED",
  "DEVICE_IDENTITY_REQUIRED",
];

function matchesErrorCode(
  lastErrorCode: string | null | undefined,
  names: readonly ConnectErrorDetailCodeName[],
): boolean {
  if (!lastErrorCode) {
    return false;
  }
  return names.some((name) => lastErrorCode === getConnectErrorCode(name));
}

/** Whether the overview should show device-pairing guidance for this error. */
export function shouldShowPairingHint(
  connected: boolean,
  lastError: string | null,
  lastErrorCode?: string | null,
): boolean {
  if (connected || !lastError) {
    return false;
  }
  if (lastErrorCode === getConnectErrorCode("PAIRING_REQUIRED")) {
    return true;
  }
  return lastError.toLowerCase().includes("pairing required");
}

export function shouldShowAuthHint(
  connected: boolean,
  lastError: string | null,
  lastErrorCode?: string | null,
): boolean {
  if (connected || !lastError) {
    return false;
  }
  if (matchesErrorCode(lastErrorCode, AUTH_FAILURE_CODE_NAMES)) {
    return true;
  }
  const lower = lastError.toLowerCase();
  return lower.includes("unauthorized") || lower.includes("connect failed");
}

export function shouldShowAuthRequiredHint(
  hasToken: boolean,
  hasPassword: boolean,
  lastErrorCode?: string | null,
): boolean {
  if (matchesErrorCode(lastErrorCode, AUTH_REQUIRED_CODE_NAMES)) {
    return true;
  }
  return !hasToken && !hasPassword;
}

export function shouldShowInsecureContextHint(
  connected: boolean,
  lastError: string | null,
  lastErrorCode?: string | null,
): boolean {
  if (connected || !lastError) {
    return false;
  }
  if (matchesErrorCode(lastErrorCode, INSECURE_CONTEXT_CODE_NAMES)) {
    return true;
  }
  const lower = lastError.toLowerCase();
  return lower.includes("secure context") || lower.includes("device identity required");
}
