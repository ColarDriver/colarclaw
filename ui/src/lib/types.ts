export type SessionItem = {
  id: string;
  title: string;
  createdAtMs: number;
  updatedAtMs: number;
};

export type MessageItem = {
  id: string;
  sessionId: string;
  role: string;
  text: string;
  createdAtMs: number;
};

export type ToolItem = {
  name: string;
  description: string;
};

export type SettingsState = {
  defaultModel: string;
  fallbackModels: string[];
  toolAllowlist: string[];
  toolDenylist: string[];
  maxToolCallsPerRun: number;
  maxSameToolRepeat: number;
  maxToolCallsPerMinute: number;
  modelRegistry: string[];
  mcpServers: string[];
  skillsEnabled: string[];
};

export type RetrievedContextItem = {
  path: string;
  startLine: number;
  endLine: number;
  score: number;
  snippet: string;
  source: string;
  citation?: string | null;
};

export type ChatRunResult = {
  runId: string;
  sessionId: string;
  text: string;
  tools: Array<{ name: string; args: Record<string, unknown>; result: string }>;
  retrievedContext: RetrievedContextItem[];
  deduplicated?: boolean;
};

export type RuntimeModelItem = {
  key: string;
  provider: string;
  id: string;
  name: string;
  reasoning: boolean;
  contextWindow: number | null;
};

export type RuntimeMcpServerItem = {
  name: string;
  command: string;
  enabled: boolean;
};

export type RuntimeSkillItem = {
  key: string;
  name: string;
  description: string;
};

export type RuntimeConfigState = {
  modelRegistry: RuntimeModelItem[];
  mcpServers: RuntimeMcpServerItem[];
  skillsEnabled: string[];
  skillsAvailable: RuntimeSkillItem[];
  memory: Record<string, unknown>;
};
