/**
 * Talking objects — Cloudflare Worker.
 *
 *   GET  /device/connect?key=DEVICE_KEY   websocket opened BY the device
 *   POST /mcp                             MCP endpoint (Authorization: Bearer MCP_KEY)
 *   POST /mcp/<MCP_KEY>                   same, for clients that only take a URL
 *   POST /context                         push context to the device (Bearer ADMIN_KEY)
 *   GET  /status                          is the device connected?
 *
 * One Relay per device: ?device=<name> selects it (default "object").
 */

import { handleMcp } from "./mcp";
import type { DeviceAction, DispatchResult } from "./relay";

export { Relay } from "./relay";

export interface Env {
  RELAY: DurableObjectNamespace;
  DEVICE_KEY: string;
  MCP_KEY: string;
  ADMIN_KEY?: string;
}

function bearer(request: Request): string {
  const header = request.headers.get("Authorization") ?? "";
  return header.startsWith("Bearer ") ? header.slice(7) : "";
}

// Constant-time comparison, so response timing does not leak the key.
function same(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const unauthorized = () => new Response("unauthorized", { status: 401 });

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const device = url.searchParams.get("device") || "object";
    const relay = env.RELAY.get(env.RELAY.idFromName(device));
    const internal = (path: string, init?: RequestInit) =>
      relay.fetch(new Request(`https://relay${path}`, init));

    if (url.pathname === "/device/connect") {
      if (!same(url.searchParams.get("key") ?? "", env.DEVICE_KEY)) return unauthorized();
      return relay.fetch(new Request("https://relay/connect", request));
    }

    if (url.pathname === "/mcp" || url.pathname.startsWith("/mcp/")) {
      const key = url.pathname.startsWith("/mcp/") ? url.pathname.slice(5) : bearer(request);
      if (!same(key, env.MCP_KEY)) return unauthorized();
      return handleMcp(request, {
        actions: async () => (await (await internal("/actions")).json()) as DeviceAction[],
        dispatch: async (name, args) =>
          (await (
            await internal("/dispatch", { method: "POST", body: JSON.stringify({ name, args }) })
          ).json()) as DispatchResult,
      });
    }

    if (url.pathname === "/context" && request.method === "POST") {
      if (!env.ADMIN_KEY || !same(bearer(request), env.ADMIN_KEY)) return unauthorized();
      return internal("/context", { method: "POST", body: await request.text() });
    }

    if (url.pathname === "/status") return internal("/status");

    return new Response("talking-objects worker", { status: 200 });
  },
} satisfies ExportedHandler<Env>;
