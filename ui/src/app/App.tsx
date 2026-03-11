import { useEffect, useMemo, useState } from "react";
import { ApiClient } from "../lib/apiClient";
import type {
  MessageItem,
  RuntimeConfigState,
  SessionItem,
  SettingsState,
  ToolItem,
} from "../lib/types";
import { WsClient, type ChatEvent } from "../lib/wsClient";
import { ChatPanel } from "./routes/ChatPanel";
import { SessionsPanel } from "./routes/SessionsPanel";
import { SettingsPanel } from "./routes/SettingsPanel";
import { ToolsPanel } from "./routes/ToolsPanel";

type Tab = "chat" | "sessions" | "tools" | "settings";

const defaultApiBase = import.meta.env.VITE_OPENCLAW_API_BASE ?? "http://127.0.0.1:8788";
const defaultWsBase = import.meta.env.VITE_OPENCLAW_WS_BASE ?? "ws://127.0.0.1:8788/v1/ws/chat";
const defaultToken = import.meta.env.VITE_OPENCLAW_API_TOKEN ?? "openclaw-dev-token";

export function App() {
  const api = useMemo(() => new ApiClient({ baseUrl: defaultApiBase, token: defaultToken }), []);
  const [tab, setTab] = useState<Tab>("chat");
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [settings, setSettings] = useState<SettingsState | null>(null);
  const [runtime, setRuntime] = useState<RuntimeConfigState | null>(null);
  const [status, setStatus] = useState<string>("ready");
  const [streamText, setStreamText] = useState("");
  const [wsEnabled, setWsEnabled] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const [sessionRows, toolRows, runtimeSettings, runtimeConfig] = await Promise.all([
          api.listSessions(),
          api.listTools(),
          api.getSettings(),
          api.getRuntime(),
        ]);
        setSessions(sessionRows);
        setTools(toolRows);
        setSettings(runtimeSettings);
        setRuntime(runtimeConfig);
        if (sessionRows.length > 0) {
          const firstId = sessionRows[0].id;
          setActiveSessionId(firstId);
          const detail = await api.getSession(firstId);
          setMessages(detail.session.messages);
        } else {
          const created = await api.createSession("Main Session");
          setSessions([created]);
          setActiveSessionId(created.id);
          setMessages([]);
        }
      } catch (error) {
        setStatus(`bootstrap failed: ${String(error)}`);
      }
    })();
  }, [api]);

  useEffect(() => {
    if (!wsEnabled) {
      return;
    }
    const ws = new WsClient({
      url: defaultWsBase,
      onEvent: (event: ChatEvent) => {
        if (event.type === "delta") {
          setStreamText(event.text);
          return;
        }
        if (event.type === "final") {
          setStreamText("");
          setMessages((prev) => [
            ...prev,
            {
              id: `assistant-${Date.now()}`,
              sessionId: event.sessionId,
              role: "assistant",
              text: event.text,
              createdAtMs: Date.now(),
            },
          ]);
          return;
        }
        if (event.type === "error") {
          setStatus(`ws error: ${event.message}`);
        }
      },
    });
    ws.connect();
    const timer = window.setInterval(() => ws.ping(), 12_000);
    return () => {
      window.clearInterval(timer);
      ws.disconnect();
    };
  }, [wsEnabled]);

  const refreshSession = async (sessionId: string) => {
    const detail = await api.getSession(sessionId);
    setMessages(detail.session.messages);
  };

  const handleCreateSession = async (title: string) => {
    const created = await api.createSession(title);
    const next = [created, ...sessions];
    setSessions(next);
    setActiveSessionId(created.id);
    setMessages([]);
    setStatus(`created session ${created.id}`);
  };

  const handleSelectSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    await refreshSession(sessionId);
  };

  const handleSend = async (text: string) => {
    if (!activeSessionId) {
      return;
    }
    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        sessionId: activeSessionId,
        role: "user",
        text,
        createdAtMs: Date.now(),
      },
    ]);

    if (wsEnabled) {
      setStatus("ws mode enabled; use REST fallback send disabled in this build");
      return;
    }

    const run = await api.runChat(activeSessionId, text);
    if (run.retrievedContext.length > 0) {
      const top = run.retrievedContext
        .slice(0, 3)
        .map((item) => `${item.path}#L${item.startLine}-${item.endLine}`)
        .join(", ");
      setStatus(`memory hits: ${top}`);
    }
    setMessages((prev) => [
      ...prev,
      {
        id: `assistant-${Date.now()}`,
        sessionId: activeSessionId,
        role: "assistant",
        text: run.text,
        createdAtMs: Date.now(),
      },
    ]);
  };

  const handleSaveSettings = async (next: Partial<SettingsState>) => {
    const updated = await api.putSettings(next);
    setSettings(updated);
    const runtimeUpdated = await api.getRuntime();
    setRuntime(runtimeUpdated);
    setStatus("settings saved");
  };

  return (
    <div className="shell">
      <header className="topbar">
        <h1>OpenClaw React Control</h1>
        <div className="status">{status}</div>
      </header>

      <nav className="tabs">
        <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
          Chat
        </button>
        <button className={tab === "sessions" ? "active" : ""} onClick={() => setTab("sessions")}>
          Sessions
        </button>
        <button className={tab === "tools" ? "active" : ""} onClick={() => setTab("tools")}>
          Tools
        </button>
        <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
          Settings
        </button>
        <label className="ws-toggle">
          <input
            type="checkbox"
            checked={wsEnabled}
            onChange={(e) => setWsEnabled(e.target.checked)}
          />
          WS stream mode
        </label>
      </nav>

      <main className="content">
        {tab === "chat" ? (
          <ChatPanel
            activeSessionId={activeSessionId}
            messages={messages}
            streamText={streamText}
            onSend={handleSend}
          />
        ) : null}

        {tab === "sessions" ? (
          <SessionsPanel
            sessions={sessions}
            activeSessionId={activeSessionId}
            onCreateSession={handleCreateSession}
            onSelectSession={handleSelectSession}
          />
        ) : null}

        {tab === "tools" ? <ToolsPanel tools={tools} /> : null}

        {tab === "settings" && settings ? (
          <SettingsPanel settings={settings} runtime={runtime} onSave={handleSaveSettings} />
        ) : null}
      </main>
    </div>
  );
}
