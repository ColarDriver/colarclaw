import { useState } from "react";
import type { MessageItem } from "../../lib/types";

type ChatPanelProps = {
  activeSessionId: string;
  messages: MessageItem[];
  streamText: string;
  onSend: (text: string) => Promise<void>;
};

export function ChatPanel({ activeSessionId, messages, streamText, onSend }: ChatPanelProps) {
  const [text, setText] = useState("");

  return (
    <section className="panel">
      <h2>Chat</h2>
      <p>Session: {activeSessionId || "-"}</p>
      <div className="chat-log">
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message ${msg.role}`}>
            <strong>{msg.role}</strong>
            <div>{msg.text}</div>
          </div>
        ))}
        {streamText ? (
          <div className="chat-message assistant stream">
            <strong>assistant (stream)</strong>
            <div>{streamText}</div>
          </div>
        ) : null}
      </div>

      <div className="composer">
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Type a message"
          rows={4}
        />
        <button
          onClick={async () => {
            const trimmed = text.trim();
            if (!trimmed) {
              return;
            }
            setText("");
            await onSend(trimmed);
          }}
        >
          Send
        </button>
      </div>
    </section>
  );
}
