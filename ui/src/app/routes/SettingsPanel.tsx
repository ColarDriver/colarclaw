import { useMemo, useState } from "react";
import type { RuntimeConfigState, SettingsState } from "../../lib/types";

type SettingsPanelProps = {
  settings: SettingsState;
  runtime: RuntimeConfigState | null;
  onSave: (next: Partial<SettingsState>) => Promise<void>;
};

function toCsv(items: string[]): string {
  return items.join(", ");
}

function parseCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function SettingsPanel({ settings, runtime, onSave }: SettingsPanelProps) {
  const [defaultModel, setDefaultModel] = useState(settings.defaultModel);
  const [fallbackModels, setFallbackModels] = useState(toCsv(settings.fallbackModels));
  const [toolAllowlist, setToolAllowlist] = useState(toCsv(settings.toolAllowlist));
  const [toolDenylist, setToolDenylist] = useState(toCsv(settings.toolDenylist));
  const [modelRegistry, setModelRegistry] = useState(toCsv(settings.modelRegistry));
  const [mcpServers, setMcpServers] = useState(toCsv(settings.mcpServers));
  const [skillsEnabled, setSkillsEnabled] = useState(toCsv(settings.skillsEnabled));
  const [maxToolCallsPerRun, setMaxToolCallsPerRun] = useState(String(settings.maxToolCallsPerRun));
  const [maxSameToolRepeat, setMaxSameToolRepeat] = useState(String(settings.maxSameToolRepeat));
  const [maxToolCallsPerMinute, setMaxToolCallsPerMinute] = useState(
    String(settings.maxToolCallsPerMinute),
  );

  const dirty = useMemo(() => {
    return (
      defaultModel !== settings.defaultModel ||
      fallbackModels !== toCsv(settings.fallbackModels) ||
      toolAllowlist !== toCsv(settings.toolAllowlist) ||
      toolDenylist !== toCsv(settings.toolDenylist) ||
      modelRegistry !== toCsv(settings.modelRegistry) ||
      mcpServers !== toCsv(settings.mcpServers) ||
      skillsEnabled !== toCsv(settings.skillsEnabled) ||
      maxToolCallsPerRun !== String(settings.maxToolCallsPerRun) ||
      maxSameToolRepeat !== String(settings.maxSameToolRepeat) ||
      maxToolCallsPerMinute !== String(settings.maxToolCallsPerMinute)
    );
  }, [
    defaultModel,
    fallbackModels,
    toolAllowlist,
    toolDenylist,
    modelRegistry,
    mcpServers,
    skillsEnabled,
    maxToolCallsPerRun,
    maxSameToolRepeat,
    maxToolCallsPerMinute,
    settings,
  ]);

  return (
    <section className="panel">
      <h2>Settings</h2>

      <label>
        Default model
        <input value={defaultModel} onChange={(event) => setDefaultModel(event.target.value)} />
      </label>

      <label>
        Fallback models (comma separated)
        <input value={fallbackModels} onChange={(event) => setFallbackModels(event.target.value)} />
      </label>

      <label>
        Tool allowlist (comma separated)
        <input value={toolAllowlist} onChange={(event) => setToolAllowlist(event.target.value)} />
      </label>

      <label>
        Tool denylist (comma separated)
        <input value={toolDenylist} onChange={(event) => setToolDenylist(event.target.value)} />
      </label>

      <label>
        Max tool calls per run
        <input
          type="number"
          min={1}
          value={maxToolCallsPerRun}
          onChange={(event) => setMaxToolCallsPerRun(event.target.value)}
        />
      </label>

      <label>
        Max same tool repeat
        <input
          type="number"
          min={1}
          value={maxSameToolRepeat}
          onChange={(event) => setMaxSameToolRepeat(event.target.value)}
        />
      </label>

      <label>
        Max tool calls per minute
        <input
          type="number"
          min={1}
          value={maxToolCallsPerMinute}
          onChange={(event) => setMaxToolCallsPerMinute(event.target.value)}
        />
      </label>

      <label>
        Model registry (provider/model=Display Name)
        <input value={modelRegistry} onChange={(event) => setModelRegistry(event.target.value)} />
      </label>

      <label>
        MCP servers (name=command)
        <input value={mcpServers} onChange={(event) => setMcpServers(event.target.value)} />
      </label>

      <label>
        Enabled skills (comma separated keys)
        <input value={skillsEnabled} onChange={(event) => setSkillsEnabled(event.target.value)} />
      </label>

      {runtime ? (
        <div className="panel-muted">
          <strong>Discovered skills:</strong>
          <div>{runtime.skillsAvailable.map((item) => item.key).join(", ") || "(none)"}</div>
        </div>
      ) : null}

      <button
        disabled={!dirty}
        onClick={() =>
          void onSave({
            defaultModel,
            fallbackModels: parseCsv(fallbackModels),
            toolAllowlist: parseCsv(toolAllowlist),
            toolDenylist: parseCsv(toolDenylist),
            maxToolCallsPerRun: Number(maxToolCallsPerRun) || settings.maxToolCallsPerRun,
            maxSameToolRepeat: Number(maxSameToolRepeat) || settings.maxSameToolRepeat,
            maxToolCallsPerMinute: Number(maxToolCallsPerMinute) || settings.maxToolCallsPerMinute,
            modelRegistry: parseCsv(modelRegistry),
            mcpServers: parseCsv(mcpServers),
            skillsEnabled: parseCsv(skillsEnabled),
          })
        }
      >
        Save
      </button>
    </section>
  );
}
