# 02 · Objeto que escucha

Una lámpara, una radio o un busto que de pronto contesta. Un pulsador escondido o un sensor de presencia con salida a contacto inicia la conversación; se termina sola cuando el agente se despide o al llegar al tiempo máximo.

## Configuración

```ini
TRIGGER_MODE=gpio
TRIGGER_INVERT=1         # un pulsador: pulsar = empezar
MAX_CALL_SECONDS=180     # conversaciones cortas: hay cola detrás
MIC_DUCK_DB=16           # altavoz abierto: más ducking
LED_IDLE_COLOR=20,20,24
```

Con altavoz abierto el agente puede oírse a sí mismo: sube `MIC_DUCK_DB` hasta que deje de cortarse, y separa micro y altavoz todo lo que permita el objeto.

## Prompt (esqueleto)

```text
Eres <objeto>, un <lámpara/radio/…> que lleva <tiempo> en <lugar>.
Alguien acaba de tocarte. Te sorprende que te hablen; a ellos, que contestes.
Hablas de lo que has visto desde tu sitio. Frases cortas, mucha curiosidad.
Tu luz es tu forma de respirar: `light` con `breathe` cuando algo te emocione.
Despídete cuando lleves unas cinco intervenciones.
```
