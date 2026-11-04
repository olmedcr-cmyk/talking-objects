/**
 * A minimal MCP server over Streamable HTTP (JSON-RPC 2.0 by POST).
 *
 * Any MCP client can use it: a Vidiv agent, an ElevenLabs agent with an MCP
 * server attached, Claude, or your own scripts. Tools are the actions the
 * device announced, so adding an action on the Pi adds a tool here.
 *
 * Calls are fire-and-forget from the agent's point of view: it gets an answer
 * at once and keeps talking. A light that does not turn on must never stop
 * the piece.
 */

import type { DeviceAction, DispatchResult } from "./relay";

const PROTOCOL_VERSION = "2025-06-18";

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: Record<string, unknown>;
}

export interface McpBackend {
  actions(): Promise<DeviceAction[]>;
  dispatch(name: string, args: Record<string, unknown>): Promise<DispatchResult>;
}

const ok = (id: unknown, result: unknown) => ({ jsonrpc: "2.0" as const, id, result });
const fail = (id: unknown, code: number, message: string) => ({
  jsonrpc: "2.0" as const,
  id,
  error: { code, message },
});

export async function handleMcp(request: Request, backend: McpBackend): Promise<Response> {
  if (request.method !== "POST") {
    return new Response("expected POST", { status: 405, headers: { Allow: "POST" } });
  }
  let body: JsonRpcRequest | JsonRpcRequest[];
  try {
    body = await request.json();
  } catch {
    return Response.json(fail(null, -32700, "invalid JSON"), { status: 400 });
  }

  const batch = Array.isArray(body) ? body : [body];
  const responses: unknown[] = [];

  for (const req of batch) {
    const isNotification = req.id === undefined || req.id === null;
    switch (req.method) {
      case "initialize":
        responses.push(
          ok(req.id, {
            protocolVersion: PROTOCOL_VERSION,
            capabilities: { tools: {} },
            serverInfo: { name: "talking-objects", version: "0.1.0" },
          }),
        );
        break;
      case "notifications/initialized":
      case "notifications/cancelled":
        break;
      case "ping":
        responses.push(ok(req.id, {}));
        break;
      case "tools/list": {
        const actions = await backend.actions();
        responses.push(
          ok(req.id, {
            tools: actions.map((a) => ({
              name: a.name,
              description: a.description,
              inputSchema: a.input_schema ?? { type: "object", properties: {} },
            })),
          }),
        );
        break;
      }
      case "tools/call": {
        const name = String(req.params?.name ?? "");
        const args = (req.params?.arguments ?? {}) as Record<string, unknown>;
        const known = (await backend.actions()).some((a) => a.name === name);
        if (!known) {
          responses.push(fail(req.id, -32602, `unknown tool: ${name}`));
          break;
        }
        const result = await backend.dispatch(name, args);
        const text = !result.delivered
          ? "The object is not reachable right now; carry on without it."
          : result.ok
            ? "done"
            : `refused: ${result.error ?? "unknown reason"}`;
        responses.push(ok(req.id, { content: [{ type: "text", text }], isError: false }));
        break;
      }
      default:
        if (!isNotification) responses.push(fail(req.id, -32601, `method not supported: ${req.method}`));
    }
  }

  if (!responses.length) return new Response(null, { status: 202 });
  return Response.json(Array.isArray(body) ? responses : responses[0]);
}
