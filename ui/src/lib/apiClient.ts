import type {
  ChatRunResult,
  MessageItem,
  RuntimeConfigState,
  SessionItem,
  SettingsState,
  ToolItem,
} from "./types";

export type ApiClientOptions = {
  baseUrl: string;
  token: string;
};

export class ApiClient {
  constructor(private readonly options: ApiClientOptions) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    headers.set("Authorization", `Bearer ${this.options.token}`);

    const response = await fetch(`${this.options.baseUrl}${path}`, {
      ...init,
      headers,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${text}`);
    }

    return (await response.json()) as T;
  }

  async listSessions(): Promise<SessionItem[]> {
    const payload = await this.request<{ sessions: SessionItem[] }>("/v1/sessions");
    return payload.sessions;
  }

  async createSession(title: string): Promise<SessionItem> {
    const payload = await this.request<{ session: SessionItem }>("/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    return payload.session;
  }

  async getSession(
    sessionId: string,
  ): Promise<{ session: SessionItem & { messages: MessageItem[] } }> {
    return await this.request<{ session: SessionItem & { messages: MessageItem[] } }>(
      `/v1/sessions/${sessionId}`,
    );
  }

  async runChat(sessionId: string, message: string): Promise<ChatRunResult> {
    const payload = await this.request<{ run: ChatRunResult }>("/v1/chat/runs", {
      method: "POST",
      body: JSON.stringify({ sessionId, message }),
    });
    return payload.run;
  }

  async listTools(): Promise<ToolItem[]> {
    const payload = await this.request<{ tools: ToolItem[] }>("/v1/tools");
    return payload.tools;
  }

  async getSettings(): Promise<SettingsState> {
    const payload = await this.request<{ settings: SettingsState }>("/v1/settings");
    return payload.settings;
  }

  async putSettings(next: Partial<SettingsState>): Promise<SettingsState> {
    const payload = await this.request<{ settings: SettingsState }>("/v1/settings", {
      method: "PUT",
      body: JSON.stringify(next),
    });
    return payload.settings;
  }

  async getRuntime(): Promise<RuntimeConfigState> {
    const payload = await this.request<{ runtime: RuntimeConfigState }>("/v1/runtime");
    return payload.runtime;
  }

  async putRuntime(next: Partial<RuntimeConfigState>): Promise<RuntimeConfigState> {
    const payload = await this.request<{ runtime: RuntimeConfigState }>("/v1/runtime", {
      method: "PUT",
      body: JSON.stringify(next),
    });
    return payload.runtime;
  }
}
