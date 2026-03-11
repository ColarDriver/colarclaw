export type ChatEvent =
  | { type: "lifecycle"; phase: "start" | "end"; runId: string; sessionId: string }
  | { type: "delta"; runId: string; sessionId: string; delta: string; text: string }
  | {
      type: "tool_end";
      runId: string;
      sessionId: string;
      name: string;
      args: Record<string, unknown>;
      result: string;
    }
  | { type: "final"; runId: string; sessionId: string; text: string }
  | { type: "error"; message: string }
  | { type: "pong" };

export type WsClientOptions = {
  url: string;
  onEvent: (event: ChatEvent) => void;
};

export class WsClient {
  private socket: WebSocket | null = null;

  constructor(private readonly options: WsClientOptions) {}

  connect(): void {
    this.socket = new WebSocket(this.options.url);
    this.socket.addEventListener("message", (ev) => {
      try {
        const parsed = JSON.parse(String(ev.data)) as ChatEvent;
        this.options.onEvent(parsed);
      } catch {
        // ignore malformed message
      }
    });
  }

  disconnect(): void {
    this.socket?.close();
    this.socket = null;
  }

  sendMessage(sessionId: string, message: string, model?: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("websocket not connected");
    }
    this.socket.send(
      JSON.stringify({
        type: "chat.send",
        sessionId,
        message,
        model,
      }),
    );
  }

  ping(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(JSON.stringify({ type: "ping" }));
  }
}
