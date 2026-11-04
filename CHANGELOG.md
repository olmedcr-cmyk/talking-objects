# Cambios

## 0.1.0 · 2026-11-04

Primera versión del kit, extraída de TeleTUP (la cabina de GAIA 2147).

- Dispositivo en Python para Raspberry Pi 5: audio con un hilo dueño de la tarjeta, Vidiv (LiveKit) y ElevenLabs con relevo automático y cortacircuitos, tonos de espera, interruptor por GPIO, teclado o automático, tira WS2812 por SPI, LCD 20x4 por I2C, reactor de reglas, registro de acciones con cupos, túnel saliente y página de estado de solo lectura.
- Worker de Cloudflare: servidor MCP (Streamable HTTP) y relé en un Durable Object; las tools reflejan las acciones que anuncia el dispositivo.
- Seis guías, tres ejemplos de experiencia, CI con tests de dispositivo y Worker.
