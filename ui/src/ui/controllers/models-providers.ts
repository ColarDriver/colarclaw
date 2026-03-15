import type { GatewayBrowserClient } from "../gateway.ts";
import type {
  ModelsCatalogProvider,
  ModelsProviderEntry,
  ModelsProviderKind,
  ModelsProvidersSnapshot,
} from "../types.ts";

export type ModelsProviderDraftEntry = {
  id: string;
  label: string;
  kind: ModelsProviderKind;
  api: string;
  baseUrl: string;
  models: string[];
  apiKey: string;
  apiKeyTouched: boolean;
  apiKeyConfigured: boolean;
  apiKeyPreview: string;
};

export type ModelsProvidersDraft = {
  defaults: {
    defaultModel: string;
    fallbackModels: string[];
  };
  modelRegistry: string[];
  providers: ModelsProviderDraftEntry[];
};

export type ModelsProvidersState = {
  client: GatewayBrowserClient | null;
  connected: boolean;
  modelsProvidersLoading: boolean;
  modelsProvidersSaving: boolean;
  modelsProvidersError: string | null;
  modelsProvidersSnapshot: ModelsProvidersSnapshot | null;
  modelsProvidersDraft: ModelsProvidersDraft | null;
};

function normalizeList(values: unknown): string[] {
  if (!Array.isArray(values)) {
    return [];
  }
  const output: string[] = [];
  const seen = new Set<string>();
  for (const item of values) {
    if (typeof item !== "string") {
      continue;
    }
    const value = item.trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    output.push(value);
  }
  return output;
}

function normalizeCatalog(snapshot: ModelsProvidersSnapshot): ModelsCatalogProvider[] {
  const providers = Array.isArray(snapshot.catalog?.providers) ? snapshot.catalog.providers : [];
  return providers
    .filter((entry): entry is ModelsCatalogProvider => {
      return (
        Boolean(entry) &&
        typeof entry.id === "string" &&
        typeof entry.label === "string" &&
        (entry.kind === "builtin" || entry.kind === "custom")
      );
    })
    .toSorted((a, b) => a.label.localeCompare(b.label));
}

function normalizeConfiguredProviders(snapshot: ModelsProvidersSnapshot): ModelsProviderEntry[] {
  const providers = Array.isArray(snapshot.providers) ? snapshot.providers : [];
  return providers.filter(
    (entry): entry is ModelsProviderEntry =>
      Boolean(entry) && typeof entry.id === "string" && typeof entry.label === "string",
  );
}

function buildProviderDraft(
  catalogEntry: ModelsCatalogProvider,
  configured: ModelsProviderEntry | null,
): ModelsProviderDraftEntry {
  return {
    id: catalogEntry.id,
    label: configured?.label ?? catalogEntry.label,
    kind: catalogEntry.kind,
    api: configured?.api?.trim() || catalogEntry.api,
    baseUrl: configured?.baseUrl?.trim() ?? "",
    models: normalizeList(configured?.models),
    apiKey: "",
    apiKeyTouched: false,
    apiKeyConfigured: Boolean(configured?.apiKeyConfigured),
    apiKeyPreview: configured?.apiKeyPreview?.trim() ?? "",
  };
}

export function buildModelsProvidersDraft(snapshot: ModelsProvidersSnapshot): ModelsProvidersDraft {
  const catalogProviders = normalizeCatalog(snapshot);
  const configuredProviders = normalizeConfiguredProviders(snapshot);
  const configuredById = new Map(configuredProviders.map((entry) => [entry.id, entry]));

  const builtins: ModelsProviderDraftEntry[] = catalogProviders.map((entry) =>
    buildProviderDraft(entry, configuredById.get(entry.id) ?? null),
  );

  const customs: ModelsProviderDraftEntry[] = configuredProviders
    .filter((entry) => entry.kind === "custom")
    .toSorted((a, b) => a.id.localeCompare(b.id))
    .map((entry) => ({
      id: entry.id,
      label: entry.label,
      kind: "custom",
      api: entry.api?.trim() || "openai-completions",
      baseUrl: entry.baseUrl?.trim() ?? "",
      models: normalizeList(entry.models),
      apiKey: "",
      apiKeyTouched: false,
      apiKeyConfigured: Boolean(entry.apiKeyConfigured),
      apiKeyPreview: entry.apiKeyPreview?.trim() ?? "",
    }));

  return {
    defaults: {
      defaultModel: snapshot.defaults?.defaultModel?.trim() ?? "",
      fallbackModels: normalizeList(snapshot.defaults?.fallbackModels),
    },
    modelRegistry: normalizeList(snapshot.modelRegistry),
    providers: [...builtins, ...customs],
  };
}

function buildApplyPayload(draft: ModelsProvidersDraft) {
  return {
    defaults: {
      defaultModel: draft.defaults.defaultModel.trim(),
      fallbackModels: normalizeList(draft.defaults.fallbackModels),
    },
    modelRegistry: normalizeList(draft.modelRegistry),
    providers: draft.providers.map((entry) => {
      const payload: Record<string, unknown> = {
        id: entry.id,
        kind: entry.kind,
        api: entry.api.trim(),
        baseUrl: entry.baseUrl.trim(),
        models: normalizeList(entry.models),
      };
      if (entry.apiKeyTouched) {
        payload.apiKey = entry.apiKey;
      }
      return payload;
    }),
  };
}

export function cloneModelsProvidersDraft(draft: ModelsProvidersDraft): ModelsProvidersDraft {
  return {
    defaults: {
      defaultModel: draft.defaults.defaultModel,
      fallbackModels: [...draft.defaults.fallbackModels],
    },
    modelRegistry: [...draft.modelRegistry],
    providers: draft.providers.map((entry) => ({
      ...entry,
      models: [...entry.models],
    })),
  };
}

function normalizeSnapshot(payload: unknown): ModelsProvidersSnapshot {
  const candidate = payload as Partial<ModelsProvidersSnapshot>;
  return {
    catalog: {
      providers: Array.isArray(candidate.catalog?.providers) ? candidate.catalog.providers : [],
      customApis: normalizeList(candidate.catalog?.customApis),
    },
    providers: Array.isArray(candidate.providers) ? candidate.providers : [],
    defaults: {
      defaultModel: candidate.defaults?.defaultModel?.trim() ?? "",
      fallbackModels: normalizeList(candidate.defaults?.fallbackModels),
    },
    modelRegistry: normalizeList(candidate.modelRegistry),
  };
}

function looksLikeUrl(value: string): boolean {
  const text = value.trim().toLowerCase();
  if (!text) {
    return false;
  }
  return text.startsWith("http://") || text.startsWith("https://") || text.includes("://");
}

function validateApiKeys(draft: ModelsProvidersDraft): string | null {
  for (const entry of draft.providers) {
    if (!entry.apiKeyTouched) {
      continue;
    }
    const apiKey = entry.apiKey.trim();
    if (!apiKey) {
      continue;
    }
    if (looksLikeUrl(apiKey)) {
      return `API key for provider '${entry.id}' looks like a URL. Please paste only the key.`;
    }
  }
  return null;
}

export async function loadModelsProviders(state: ModelsProvidersState) {
  if (!state.client || !state.connected) {
    return;
  }
  if (state.modelsProvidersLoading) {
    return;
  }
  state.modelsProvidersLoading = true;
  state.modelsProvidersError = null;
  try {
    const response = await state.client.request<ModelsProvidersSnapshot>(
      "models.providers.get",
      {},
    );
    const snapshot = normalizeSnapshot(response);
    state.modelsProvidersSnapshot = snapshot;
    state.modelsProvidersDraft = buildModelsProvidersDraft(snapshot);
  } catch (err) {
    state.modelsProvidersError = String(err);
  } finally {
    state.modelsProvidersLoading = false;
  }
}

export async function saveModelsProviders(state: ModelsProvidersState) {
  if (!state.client || !state.connected || !state.modelsProvidersDraft) {
    return;
  }
  if (state.modelsProvidersSaving) {
    return;
  }
  state.modelsProvidersSaving = true;
  state.modelsProvidersError = null;
  try {
    const validationError = validateApiKeys(state.modelsProvidersDraft);
    if (validationError) {
      state.modelsProvidersError = validationError;
      return;
    }
    const payload = buildApplyPayload(state.modelsProvidersDraft);
    await state.client.request("models.providers.apply", payload);
    await loadModelsProviders(state);
  } catch (err) {
    state.modelsProvidersError = String(err);
  } finally {
    state.modelsProvidersSaving = false;
  }
}

export async function deleteModelsProvider(state: ModelsProvidersState, providerId: string) {
  if (!state.client || !state.connected) {
    return;
  }
  const id = providerId.trim();
  if (!id) {
    return;
  }
  state.modelsProvidersSaving = true;
  state.modelsProvidersError = null;
  try {
    await state.client.request("models.providers.delete", { providerId: id });
    if (state.modelsProvidersSnapshot) {
      state.modelsProvidersSnapshot = {
        ...state.modelsProvidersSnapshot,
        providers: state.modelsProvidersSnapshot.providers.filter((entry) => entry.id !== id),
      };
    }
  } catch (err) {
    state.modelsProvidersError = String(err);
  } finally {
    state.modelsProvidersSaving = false;
  }
}
