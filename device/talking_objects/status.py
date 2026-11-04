"""Read-only status page on the local network (http://<device>:8081).

No buttons, no sliders, no token: whoever finds the port on the venue Wi-Fi
can look, not change anything. The transcript only appears if
STORE_TRANSCRIPTS=1 was set on purpose.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("talking_objects.status")

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Talking object</title>
<style>
:root{color-scheme:light dark;font:15px/1.5 ui-monospace,Menlo,monospace}
body{margin:0;padding:24px;max-width:720px}
h1{font:600 20px system-ui;margin:0 0 16px}
pre{background:color-mix(in srgb,currentColor 6%,transparent);padding:16px;border-radius:8px;overflow:auto}
</style>
<h1>Talking object · status</h1>
<pre id="s">loading…</pre>
<script>
async function tick(){
  try{const r=await fetch('status.json');document.getElementById('s').textContent=JSON.stringify(await r.json(),null,2)}
  catch(e){document.getElementById('s').textContent='offline'}
}
tick();setInterval(tick,1000);
</script></html>"""


async def serve(app, port: int):
    try:
        from aiohttp import web
    except Exception:
        log.warning("aiohttp missing: no status page")
        return None

    async def page(_request):
        return web.Response(text=PAGE, content_type="text/html")

    async def status(_request):
        return web.Response(text=json.dumps(app.status(), default=list),
                            content_type="application/json")

    web_app = web.Application()
    web_app.add_routes([web.get("/", page), web.get("/status.json", status)])
    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("status page on :%d", port)
    return runner
