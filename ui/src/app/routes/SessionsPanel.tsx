import { useState } from "react";
import type { SessionItem } from "../../lib/types";

type SessionsPanelProps = {
  sessions: SessionItem[];
  activeSessionId: string;
  onCreateSession: (title: string) => Promise<void>;
  onSelectSession: (sessionId: string) => Promise<void>;
};

export function SessionsPanel({
  sessions,
  activeSessionId,
  onCreateSession,
  onSelectSession,
}: SessionsPanelProps) {
  const [title, setTitle] = useState("");

  return (
    <section className="panel">
      <h2>Sessions</h2>
      <div className="row">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="New session title"
        />
        <button
          onClick={async () => {
            const trimmed = title.trim();
            if (!trimmed) {
              return;
            }
            setTitle("");
            await onCreateSession(trimmed);
          }}
        >
          Create
        </button>
      </div>
      <ul className="session-list">
        {sessions.map((session) => (
          <li key={session.id}>
            <button
              className={session.id === activeSessionId ? "session-active" : ""}
              onClick={() => void onSelectSession(session.id)}
            >
              <span>{session.title}</span>
              <small>{new Date(session.updatedAtMs).toLocaleString()}</small>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
