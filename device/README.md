# device

El programa de la Raspberry. Guía completa en [docs/01-raspberry.md](../docs/01-raspberry.md).

```
talking_objects/
├── app.py            # cablea todo y gestiona cada conversación
├── config.py         # config.env -> dataclasses tipadas
├── actions.py        # la puerta única al hardware, con cupos
├── reactor.py        # transcripción -> acciones, según rules.toml
├── link.py           # túnel saliente hacia el Worker (MCP)
├── status.py         # página de estado de solo lectura
├── bus.py            # bus de eventos
├── audio/            # device (hilo dueño), dsp, tonos
├── providers/        # base, vidiv, elevenlabs, failover
└── devices/          # trigger, leds, display
```

```bash
python -m talking_objects --config config.env -v
```
