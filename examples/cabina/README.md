# 01 · Cabina

Un teléfono de verdad: se descuelga para hablar y se cuelga para terminar. Es el arquetipo más claro, porque todo el mundo sabe qué hacer con él, y el auricular aísla del ruido de la sala.

## Configuración

```ini
TRIGGER_MODE=gpio
TRIGGER_GPIO=17          # la horquilla: colgado = contacto cerrado
MAX_CALL_SECONDS=420
MIC_DUCK_DB=10           # con auricular hace falta poco
LED_IDLE_COLOR=40,30,20
```

Si la horquilla está cableada al revés (normalmente cerrada), `TRIGGER_INVERT=1`.

## Prompt (esqueleto)

```text
Eres <personaje>, y respondes desde una cabina telefónica en <lugar>.
Quien te habla acaba de descolgar; no sabe quién eres. Preséntate en una frase.
Hablas en frases cortas, como al teléfono. Haces una pregunta cada vez.
Tienes una luz: usa `light` solo cuando cambie el tono de la conversación.
No recuerdas a nadie entre llamadas y no pides datos personales.
Si se despiden, despídete en una frase.
```
