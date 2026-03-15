import { describe, expect, it, vi } from "vitest";
import type { ModelsProvidersSnapshot } from "../types.ts";
import {
  buildModelsProvidersDraft,
  cloneModelsProvidersDraft,
  loadModelsProviders,
  saveModelsProviders,
  type ModelsProvidersState,
} from "./models-providers.ts";

const snapshot: ModelsProvidersSnapshot = {
  catalog: {
    providers: [
      {
        id: "openai",
        label: "OpenAI",
        kind: "builtin",
        api: "openai-completions",
      },
      {
        id: "anthropic",
        label: "Anthropic",
        kind: "builtin",
        api: "anthropic-messages",
        aliases: ["claude"],
      },
    ],
    customApis: ["openai-completions", "anthropic-messages"],
  },
  providers: [
    {
      id: "openai",
      label: "OpenAI",
      kind: "builtin",
      api: "openai-completions",
      baseUrl: "https://api.openai.com/v1",
      models: ["openai/gpt-5.4"],
      apiKeyConfigured: true,
      apiKeyPreview: "sk-***abc",
    },
    {
      id: "custom-lab",
      label: "custom-lab",
      kind: "custom",
      api: "openai-completions",
      baseUrl: "https://custom.example/v1",
      models: ["custom-lab/model-a"],
      apiKeyConfigured: false,
      apiKeyPreview: "",
    },
  ],
  defaults: {
    defaultModel: "openai/gpt-5.4",
    fallbackModels: ["anthropic/claude-sonnet-4-6"],
  },
  modelRegistry: ["openai/gpt-5.4=GPT 5.4"],
};

describe("models providers controller", () => {
  it("builds draft with builtins and custom providers", () => {
    const draft = buildModelsProvidersDraft(snapshot);
    expect(draft.defaults.defaultModel).toBe("openai/gpt-5.4");
    expect(draft.defaults.fallbackModels).toEqual(["anthropic/claude-sonnet-4-6"]);

    const openai = draft.providers.find((entry) => entry.id === "openai");
    expect(openai).toBeTruthy();
    expect(openai?.kind).toBe("builtin");
    expect(openai?.apiKeyConfigured).toBe(true);
    expect(openai?.apiKey).toBe("");

    const custom = draft.providers.find((entry) => entry.id === "custom-lab");
    expect(custom).toBeTruthy();
    expect(custom?.kind).toBe("custom");
    expect(custom?.baseUrl).toBe("https://custom.example/v1");
  });

  it("clones draft deeply", () => {
    const draft = buildModelsProvidersDraft(snapshot);
    const cloned = cloneModelsProvidersDraft(draft);

    cloned.defaults.defaultModel = "openai/gpt-5-mini";
    const clonedOpenai = cloned.providers.find((entry) => entry.id === "openai");
    clonedOpenai?.models.push("openai/gpt-5-mini");

    expect(draft.defaults.defaultModel).toBe("openai/gpt-5.4");
    const originalOpenai = draft.providers.find((entry) => entry.id === "openai");
    expect(originalOpenai?.models).toEqual(["openai/gpt-5.4"]);
  });

  it("saves with apiKey only when touched", async () => {
    const request = vi.fn().mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce(snapshot);

    const state: ModelsProvidersState = {
      client: { request } as unknown as ModelsProvidersState["client"],
      connected: true,
      modelsProvidersLoading: false,
      modelsProvidersSaving: false,
      modelsProvidersError: null,
      modelsProvidersSnapshot: snapshot,
      modelsProvidersDraft: {
        defaults: {
          defaultModel: "openai/gpt-5.4",
          fallbackModels: ["anthropic/claude-sonnet-4-6"],
        },
        modelRegistry: ["openai/gpt-5.4=GPT 5.4"],
        providers: [
          {
            id: "openai",
            label: "OpenAI",
            kind: "builtin",
            api: "openai-completions",
            baseUrl: "https://api.openai.com/v1",
            models: ["openai/gpt-5.4"],
            apiKey: "",
            apiKeyTouched: false,
            apiKeyConfigured: true,
            apiKeyPreview: "***",
          },
          {
            id: "custom-lab",
            label: "custom-lab",
            kind: "custom",
            api: "openai-completions",
            baseUrl: "https://custom.example/v1",
            models: ["custom-lab/model-a"],
            apiKey: "new-custom-key",
            apiKeyTouched: true,
            apiKeyConfigured: false,
            apiKeyPreview: "",
          },
        ],
      },
    };

    await saveModelsProviders(state);

    expect(request).toHaveBeenCalledWith("models.providers.apply", {
      defaults: {
        defaultModel: "openai/gpt-5.4",
        fallbackModels: ["anthropic/claude-sonnet-4-6"],
      },
      modelRegistry: ["openai/gpt-5.4=GPT 5.4"],
      providers: [
        {
          id: "openai",
          kind: "builtin",
          api: "openai-completions",
          baseUrl: "https://api.openai.com/v1",
          models: ["openai/gpt-5.4"],
        },
        {
          id: "custom-lab",
          kind: "custom",
          api: "openai-completions",
          baseUrl: "https://custom.example/v1",
          models: ["custom-lab/model-a"],
          apiKey: "new-custom-key",
        },
      ],
    });
    expect(request).toHaveBeenCalledWith("models.providers.get", {});
  });

  it("loads snapshot and draft", async () => {
    const state: ModelsProvidersState = {
      client: {
        request: vi.fn().mockResolvedValue(snapshot),
      } as unknown as ModelsProvidersState["client"],
      connected: true,
      modelsProvidersLoading: false,
      modelsProvidersSaving: false,
      modelsProvidersError: null,
      modelsProvidersSnapshot: null,
      modelsProvidersDraft: null,
    };

    await loadModelsProviders(state);

    expect(state.modelsProvidersSnapshot?.defaults.defaultModel).toBe("openai/gpt-5.4");
    expect(state.modelsProvidersDraft?.providers.length).toBeGreaterThanOrEqual(2);
  });

  it("rejects saving when api key looks like a url", async () => {
    const request = vi.fn();
    const state: ModelsProvidersState = {
      client: { request } as unknown as ModelsProvidersState["client"],
      connected: true,
      modelsProvidersLoading: false,
      modelsProvidersSaving: false,
      modelsProvidersError: null,
      modelsProvidersSnapshot: snapshot,
      modelsProvidersDraft: {
        defaults: {
          defaultModel: "openai/gpt-5.4",
          fallbackModels: [],
        },
        modelRegistry: [],
        providers: [
          {
            id: "kimi-coding",
            label: "Kimi Coding",
            kind: "builtin",
            api: "openai-completions",
            baseUrl: "https://api.kimi.com/coding/v1",
            models: ["kimi-coding/k2p5"],
            apiKey: "https://www.kimi.com/code/docs/more/third-party-agents.html",
            apiKeyTouched: true,
            apiKeyConfigured: true,
            apiKeyPreview: "htt***tml",
          },
        ],
      },
    };

    await saveModelsProviders(state);

    expect(request).not.toHaveBeenCalled();
    expect(state.modelsProvidersError).toContain("looks like a URL");
  });
});
