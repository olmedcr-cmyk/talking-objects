import { describe, expect, it } from "vitest";
import { handleMcp, type McpBackend } from "../src/mcp";

const backend = (connected = true): McpBackend & { calls: unknown[] } => {
  const calls: unknown[] = [];
  return {
    calls,
    actions: async () => [
      {
        name: "light",
        description: "Change the light.",
        input_schema: { type: "object", properties: { color: { type: "string" } } },
      },
    ],
    dispatch: async (name, args) => {
      calls.push({ name, args });
      return connected ? { ok: true, delivered: true } : { ok: false, delivered: false };
    },
  };
};

const rpc = (body: unknown) =>
  new Request("https://w/mcp", { method: "POST", body: JSON.stringify(body) });

describe("MCP", () => {
  it("initializes and lists the device's actions as tools", async () => {
    const init = await (await handleMcp(rpc({ jsonrpc: "2.0", id: 1, method: "initialize" }), backend())).json();
    expect(init.result.capabilities).toEqual({ tools: {} });

    const list = await (await handleMcp(rpc({ jsonrpc: "2.0", id: 2, method: "tools/list" }), backend())).json();
    expect(list.result.tools).toEqual([
      {
        name: "light",
        description: "Change the light.",
        inputSchema: { type: "object", properties: { color: { type: "string" } } },
      },
    ]);
  });

  it("forwards a tool call to the device", async () => {
    const b = backend();
    const res = await (
      await handleMcp(
        rpc({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "light", arguments: { color: "blue" } } }),
        b,
      )
    ).json();
    expect(b.calls).toEqual([{ name: "light", args: { color: "blue" } }]);
    expect(res.result.content[0].text).toBe("done");
  });

  it("never errors the conversation when the device is offline", async () => {
    const res = await (
      await handleMcp(rpc({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "light" } }), backend(false))
    ).json();
    expect(res.result.isError).toBe(false);
    expect(res.result.content[0].text).toMatch(/not reachable/);
  });

  it("rejects unknown tools and methods, and answers notifications with 202", async () => {
    const unknown = await (
      await handleMcp(rpc({ jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: "fog" } }), backend())
    ).json();
    expect(unknown.error.code).toBe(-32602);
    const method = await (await handleMcp(rpc({ jsonrpc: "2.0", id: 6, method: "resources/list" }), backend())).json();
    expect(method.error.code).toBe(-32601);
    const note = await handleMcp(rpc({ jsonrpc: "2.0", method: "notifications/initialized" }), backend());
    expect(note.status).toBe(202);
  });
});
