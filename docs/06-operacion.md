# 06 · Operación en campo

Un objeto que conversa pasa días solo en una feria, con wifi ajeno y público que lo zarandea. Esta guía es para quien lo monta y lo cuida.

## Servicio

```bash
sudo systemctl start talking-objects     # arrancar
sudo systemctl restart talking-objects   # tras cambiar config.env o rules.toml
journalctl -u talking-objects -f         # ver el registro en vivo
```

El servicio se reinicia solo si el proceso muere y nunca deja de intentarlo, aunque la red tarde en levantar. Si falta el audio, el proceso **no muere**: la página de estado sigue en pie y lo dice, y el objeto rechaza conversaciones con la luz en ámbar.

## Página de estado

`http://<objeto>.local:8081` muestra, de solo lectura:

- estado (`idle`, `connecting`, `talking`) y si hay audio;
- niveles de micrófono y altavoz;
- proveedor en uso, orden actual y si alguno está degradado;
- si el túnel al Worker está conectado;
- cupos usados por cada acción;
- color de la luz y texto de la pantalla.

No tiene botones: quien encuentre el puerto en la red del recinto puede mirar, pero no cambiar nada.

## Antes de abrir

- [ ] `PROVIDER_MODE=vidiv`: una conversación completa. Luego `elevenlabs`: otra. Luego `auto`.
- [ ] La luz responde a una regla del reactor y a una llamada MCP.
- [ ] Volumen y `MIC_DUCK_DB` ajustados con el objeto montado, escuchando de verdad.
- [ ] `STORE_TRANSCRIPTS=0` y el cartel de aviso puesto.
- [ ] Tarjeta de sonido de repuesto y una microSD clonada.

## Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Luz ámbar fija y no conversa | No hay audio: la tarjeta USB no enumeró | `aplay -l`; reconecta la tarjeta y reinicia el servicio |
| El agente se corta a sí mismo | El altavoz entra por el micro | Sube `MIC_DUCK_DB`, separa altavoz y micro o usa auricular |
| Cuesta interrumpir al agente | Ducking demasiado fuerte | Baja `MIC_DUCK_DB` |
| La tira parpadea o muestra colores raros | Falta convertidor de nivel o masa común | 74AHCT125 y GND compartida con la Pi |
| La tira no enciende | SPI apagado | `ls /dev/spidev*`; vuelve a ejecutar `install.sh` y reinicia |
| La pantalla no muestra nada | Dirección I2C equivocada | `sudo i2cdetect -y 1` y corrige `LCD_ADDRESS` |
| Las tools MCP dicen «no está disponible» | El túnel está caído | Revisa `LINK_URL`, la clave y `GET /status` del Worker |
| Siempre contesta ElevenLabs | Vidiv está degradado por fallos seguidos | Revisa el slug y `LIVEKIT_URL`; se recupera solo tras `BREAKER_COOLDOWN_S` |
| El interruptor dispara al revés | Cableado normalmente cerrado | `TRIGGER_INVERT=1` |
| El interruptor se rompió en plena feria | — | `TRIGGER_MODE=auto` hasta poder repararlo |

## Desarrollo

```bash
cd device
.venv/bin/python -m pytest -q        # tests
.venv/bin/ruff check .               # estilo
FAKE_AUDIO=1 TRIGGER_MODE=keyboard .venv/bin/python -m talking_objects -v

cd ../worker
npm test && npm run typecheck
cp .dev.vars.example .dev.vars && npm run dev
```

Con el Worker en `npm run dev` (puerto 8787) y `LINK_URL=ws://127.0.0.1:8787/device/connect?key=change-me-device`, puedes probar todo el circuito MCP sin desplegar nada.
