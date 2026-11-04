/**
 * Relay — the Durable Object where an agent and a device meet.
 *
 * The device sits behind a venue NAT with no public address. It opens an
 * OUTBOUND websocket to this object and keeps it alive. When an agent calls a
 * tool over MCP, the order is pushed down that socket. No open ports, no
 * tunnel software, no own domain.
 *
 * On connect the device announces its actions (name, description, JSON
 * schema). They are stored, so MCP `tools/list` mirrors the real device even
 * while it is briefly offline.
 */

export interface DeviceAction {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

type Pending = { resolve: (r: DispatchResult) => void; timer: ReturnType<typeof setTimeout> };

export interface DispatchResult {
  ok: boolean;
  delivered: boolean;
  error?: string;
}

// How long a tool call waits for the device to accept or refuse the order.
// The device answers as soon as it has validated it: it never waits for the
// hardware, so this only covers the network.
const RESULT_WAIT_MS = 1500;

export class Relay {
  private device: WebSocket | null = null;
  private pending = new Map<string, Pending>();
  private lastSeen = 0;

  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/connect") {
      if (request.headers.get("Upgrade") !== "websocket") {
        return new Response("expected a websocket", { status: 426 });
      }
      const [client, server] = Object.values(new WebSocketPair());
      server.accept();
      // After a reboot the old socket can linger: the newest connection wins.
      try {
        this.device?.close(1000, "replaced by a newer connection");
      } catch {}
      this.device = server;
      this.lastSeen = Date.now();
      server.addEventListener("message", (ev) => this.onMessage(ev.data));
      const drop = () => {
        if (this.device === server) this.device = null;
      };
      server.addEventListener("close", drop);
      server.addEventListener("error", drop);
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === "/actions") {
      return Response.json((await this.state.storage.get<DeviceAction[]>("actions")) ?? []);
    }

    if (url.pathname === "/dispatch" && request.method === "POST") {
      const { name, args } = (await request.json()) as { name: string; args: unknown };
      return Response.json(await this.dispatch({ type: "action", name, args: args ?? {} }));
    }

    if (url.pathname === "/context" && request.method === "POST") {
      const data = await request.json();
      const delivered = this.send({ type: "context", data });
      return Response.json({ ok: delivered, delivered });
    }

    if (url.pathname === "/status") {
      return Response.json({
        connected: this.device !== null,
        lastSeen: this.lastSeen ? new Date(this.lastSeen).toISOString() : null,
      });
    }

    return new Response("not found", { status: 404 });
  }

  private onMessage(raw: unknown) {
    this.lastSeen = Date.now();
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(String(raw));
    } catch {
      return;
    }
    if (message.type === "hello" && Array.isArray(message.actions)) {
      const actions = (message.actions as DeviceAction[]).map(({ name, description, input_schema }) => ({
        name,
        description,
        input_schema,
      }));
      this.state.storage.put("actions", actions);
    } else if (message.type === "result" && typeof message.id === "string") {
      const waiting = this.pending.get(message.id);
      if (waiting) {
        clearTimeout(waiting.timer);
        this.pending.delete(message.id);
        waiting.resolve({
          ok: Boolean(message.ok),
          delivered: true,
          error: message.error ? String(message.error) : undefined,
        });
      }
    }
  }

  private send(message: Record<string, unknown>): boolean {
    if (!this.device) return false;
    try {
      this.device.send(JSON.stringify(message));
      return true;
    } catch {
      this.device = null;
      return false;
    }
  }

  private dispatch(order: Record<string, unknown>): Promise<DispatchResult> {
    const id = crypto.randomUUID();
    if (!this.send({ ...order, id })) {
      return Promise.resolve({ ok: false, delivered: false, error: "the device is not connected" });
    }
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        // Sent but unconfirmed: treat as done, the conversation must go on.
        resolve({ ok: true, delivered: true });
      }, RESULT_WAIT_MS);
      this.pending.set(id, { resolve, timer });
    });
  }
}
