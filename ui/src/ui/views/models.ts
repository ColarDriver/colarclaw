import { html, nothing } from "lit";
import type {
  ModelsProviderDraftEntry,
  ModelsProvidersDraft,
} from "../controllers/models-providers.ts";
import type { ModelsProvidersSnapshot } from "../types.ts";

export type ModelsProvidersViewProps = {
  connected: boolean;
  loading: boolean;
  saving: boolean;
  error: string | null;
  snapshot: ModelsProvidersSnapshot | null;
  draft: ModelsProvidersDraft | null;
  newCustomId: string;
  newCustomApi: string;
  onRefresh: () => void;
  onSave: () => void;
  onDefaultsChange: (next: { defaultModel?: string; fallbackText?: string }) => void;
  onRegistryChange: (registryText: string) => void;
  onProviderChange: (
    providerId: string,
    patch: {
      api?: string;
      baseUrl?: string;
      modelsText?: string;
      apiKey?: string;
      apiKeyTouched?: boolean;
    },
  ) => void;
  onDeleteCustom: (providerId: string) => void;
  onNewCustomIdChange: (value: string) => void;
  onNewCustomApiChange: (value: string) => void;
  onAddCustom: () => void;
};

function joinValues(values: string[]): string {
  return values.join(", ");
}

function fallbackText(draft: ModelsProvidersDraft | null): string {
  if (!draft) {
    return "";
  }
  return joinValues(draft.defaults.fallbackModels);
}

function registryText(draft: ModelsProvidersDraft | null): string {
  if (!draft) {
    return "";
  }
  return draft.modelRegistry.join("\n");
}

function buildAliasMap(snapshot: ModelsProvidersSnapshot | null): Record<string, string[]> {
  const map: Record<string, string[]> = {};
  const catalog = snapshot?.catalog?.providers ?? [];
  for (const entry of catalog) {
    if (!entry?.id || !Array.isArray(entry.aliases) || entry.aliases.length === 0) {
      continue;
    }
    map[entry.id] = [...entry.aliases];
  }
  return map;
}

function renderProviderCard(
  entry: ModelsProviderDraftEntry,
  aliases: string[],
  props: ModelsProvidersViewProps,
) {
  const apiInputType = entry.apiKeyTouched ? "password" : "text";
  const apiInputValue = entry.apiKeyTouched ? entry.apiKey : entry.apiKeyPreview;
  const apiPlaceholder = entry.apiKeyTouched
    ? "Paste new API key"
    : entry.apiKeyConfigured
      ? "Configured"
      : "Not configured";
  return html`
    <div class="list-item">
      <div class="list-main">
        <div class="list-title">${entry.label}</div>
        <div class="list-sub">
          <span class="mono">${entry.id}</span>
          ${aliases.length > 0 ? html` · aliases: ${aliases.join(", ")}` : nothing}
          ${
            entry.kind === "custom"
              ? html`
                  · custom
                `
              : html`
                  · builtin
                `
          }
        </div>

        <div class="row" style="margin-top: 10px; gap: 10px; flex-wrap: wrap;">
          <label class="field" style="min-width: 220px; flex: 1;">
            <span>Protocol</span>
            ${
              entry.kind === "custom"
                ? html`
                    <select
                      .value=${entry.api}
                      ?disabled=${props.saving}
                      @change=${(event: Event) =>
                        props.onProviderChange(entry.id, {
                          api: (event.target as HTMLSelectElement).value,
                        })}
                    >
                      ${(
                        props.snapshot?.catalog?.customApis ?? [
                          "openai-completions",
                          "anthropic-messages",
                        ]
                      ).map((api) => html`<option value=${api}>${api}</option>`)}
                    </select>
                  `
                : html`<input .value=${entry.api} disabled />`
            }
          </label>

          <label class="field" style="min-width: 280px; flex: 2;">
            <span>Base URL</span>
            <input
              .value=${entry.baseUrl}
              ?disabled=${props.saving}
              placeholder="https://..."
              @input=${(event: Event) =>
                props.onProviderChange(entry.id, {
                  baseUrl: (event.target as HTMLInputElement).value,
                })}
            />
          </label>
        </div>

        <div class="row" style="margin-top: 10px; gap: 10px; flex-wrap: wrap;">
          <label class="field" style="min-width: 320px; flex: 3;">
            <span>Models (comma-separated)</span>
            <input
              .value=${joinValues(entry.models)}
              ?disabled=${props.saving}
              placeholder="openai/gpt-5.4, openai/gpt-5-mini"
              @input=${(event: Event) =>
                props.onProviderChange(entry.id, {
                  modelsText: (event.target as HTMLInputElement).value,
                })}
            />
          </label>
        </div>

        <div class="row" style="margin-top: 10px; gap: 10px; flex-wrap: wrap; align-items: flex-end;">
          <label class="field" style="min-width: 320px; flex: 3;">
            <span>API Key</span>
            <input
              type=${apiInputType}
              .value=${apiInputValue}
              ?disabled=${props.saving}
              placeholder=${apiPlaceholder}
              autocomplete="off"
              spellcheck="false"
              @focus=${(event: Event) => {
                if (!entry.apiKeyTouched) {
                  const input = event.target as HTMLInputElement;
                  input.select();
                }
              }}
              @input=${(event: Event) =>
                props.onProviderChange(entry.id, {
                  apiKey: (event.target as HTMLInputElement).value,
                  apiKeyTouched: true,
                })}
            />
          </label>
          <button
            class="btn"
            ?disabled=${props.saving}
            @click=${() =>
              props.onProviderChange(entry.id, {
                apiKey: "",
                apiKeyTouched: true,
              })}
          >
            Clear Key
          </button>
          ${
            entry.kind === "custom"
              ? html`
                  <button
                    class="btn danger"
                    ?disabled=${props.saving}
                    @click=${() => props.onDeleteCustom(entry.id)}
                  >
                    Delete
                  </button>
                `
              : nothing
          }
        </div>
        <div class="list-sub" style="margin-top: 6px;">
          ${
            entry.apiKeyTouched
              ? entry.apiKey.trim()
                ? html`
                    API key will be updated after Save & Apply.
                  `
                : html`
                    API key will be cleared after Save & Apply.
                  `
              : entry.apiKeyConfigured
                ? html`Saved key: <span class="mono">${entry.apiKeyPreview || "masked"}</span>
                    (plaintext is hidden for security).`
                : html`
                    No API key saved yet.
                  `
          }
        </div>
      </div>
    </div>
  `;
}

export function renderModelsProviders(props: ModelsProvidersViewProps) {
  const draft = props.draft;
  const aliasesByProvider = buildAliasMap(props.snapshot);
  const providers = draft?.providers ?? [];
  const builtins = providers.filter((entry) => entry.kind === "builtin");
  const customs = providers.filter((entry) => entry.kind === "custom");

  return html`
    <section class="card">
      <div class="row" style="justify-content: space-between; margin-bottom: 12px;">
        <div>
          <div class="card-title">Models & Providers</div>
          <div class="card-sub">Configure model defaults, registry, and provider credentials.</div>
        </div>
        <div class="row" style="gap: 8px;">
          <button class="btn" ?disabled=${props.loading || props.saving} @click=${props.onRefresh}>
            ${props.loading ? "Loading…" : "Refresh"}
          </button>
          <button class="btn primary" ?disabled=${props.loading || props.saving || !props.connected} @click=${props.onSave}>
            ${props.saving ? "Saving…" : "Save & Apply"}
          </button>
        </div>
      </div>

      ${
        props.error
          ? html`<div class="callout danger" style="margin-bottom: 12px;">${props.error}</div>`
          : nothing
      }

      ${
        !draft
          ? html`
              <div class="muted">Load provider state from gateway to start editing.</div>
            `
          : html`
              <div class="row" style="gap: 12px; flex-wrap: wrap;">
                <label class="field" style="min-width: 280px; flex: 2;">
                  <span>Default Model</span>
                  <input
                    .value=${draft.defaults.defaultModel}
                    ?disabled=${props.saving}
                    placeholder="openai/gpt-5.4"
                    @input=${(event: Event) =>
                      props.onDefaultsChange({
                        defaultModel: (event.target as HTMLInputElement).value,
                      })}
                  />
                </label>
                <label class="field" style="min-width: 280px; flex: 2;">
                  <span>Fallback Models (comma-separated)</span>
                  <input
                    .value=${fallbackText(draft)}
                    ?disabled=${props.saving}
                    placeholder="openai/gpt-5-mini, anthropic/claude-sonnet-4-6"
                    @input=${(event: Event) =>
                      props.onDefaultsChange({
                        fallbackText: (event.target as HTMLInputElement).value,
                      })}
                  />
                </label>
              </div>

              <label class="field" style="margin-top: 12px;">
                <span>Model Registry (one per line)</span>
                <textarea
                  .value=${registryText(draft)}
                  ?disabled=${props.saving}
                  style="min-height: 120px;"
                  @input=${(event: Event) =>
                    props.onRegistryChange((event.target as HTMLTextAreaElement).value)}
                ></textarea>
              </label>

              <div class="card-sub" style="margin-top: 12px; margin-bottom: 8px;">Built-in Providers</div>
              <div class="list">
                ${builtins.map((entry) =>
                  renderProviderCard(entry, aliasesByProvider[entry.id] ?? [], props),
                )}
              </div>

              <div class="card-sub" style="margin-top: 16px; margin-bottom: 8px;">Custom Providers</div>
              <div class="row" style="gap: 10px; flex-wrap: wrap; margin-bottom: 10px;">
                <label class="field" style="min-width: 220px; flex: 2;">
                  <span>Provider ID</span>
                  <input
                    .value=${props.newCustomId}
                    ?disabled=${props.saving}
                    placeholder="my-provider"
                    @input=${(event: Event) =>
                      props.onNewCustomIdChange((event.target as HTMLInputElement).value)}
                  />
                </label>
                <label class="field" style="min-width: 220px; flex: 2;">
                  <span>Protocol</span>
                  <select
                    .value=${props.newCustomApi}
                    ?disabled=${props.saving}
                    @change=${(event: Event) =>
                      props.onNewCustomApiChange((event.target as HTMLSelectElement).value)}
                  >
                    ${(
                      props.snapshot?.catalog?.customApis ?? [
                        "openai-completions",
                        "anthropic-messages",
                      ]
                    ).map((api) => html`<option value=${api}>${api}</option>`)}
                  </select>
                </label>
                <button class="btn" ?disabled=${props.saving} @click=${props.onAddCustom}>Add Custom Provider</button>
              </div>

              <div class="list">
                ${
                  customs.length === 0
                    ? html`
                        <div class="muted">No custom providers configured.</div>
                      `
                    : customs.map((entry) => renderProviderCard(entry, [], props))
                }
              </div>
            `
      }
    </section>
  `;
}
