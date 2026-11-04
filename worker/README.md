# worker

Servidor MCP y relé en Cloudflare Workers. Guía completa en [docs/04-mcp.md](../docs/04-mcp.md).

```
src/
├── index.ts   # rutas y autenticación
├── mcp.ts     # MCP sobre Streamable HTTP (JSON-RPC 2.0)
└── relay.ts   # Durable Object: el websocket de la Pi, las órdenes y sus respuestas
```

```bash
npm install
npm test && npm run typecheck
cp .dev.vars.example .dev.vars && npm run dev     # local, puerto 8787
npx wrangler deploy                               # tras `wrangler secret put` de las tres claves
```
