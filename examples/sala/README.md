# 03 · Sala

La voz y la luz llenan un espacio. Varias personas a la vez: más teatro que confidencia. Un sensor en la entrada abre la conversación; el modo automático la mantiene en bucle si la sala nunca se vacía.

## Configuración

```ini
TRIGGER_MODE=auto        # conversación en bucle, con descansos
AUTO_PAUSE_S=30
MAX_CALL_SECONDS=300
MIC_DUCK_DB=18           # altavoces grandes, micro de ambiente
LED_COUNT=150
LED_BRIGHTNESS=0.5
```

Para 150 píxeles la fuente de 5 V tiene que dar bastante más corriente: calcula unos 60 mA por píxel a blanco pleno y alimenta la tira por los dos extremos.

## Prompt (esqueleto)

```text
Eres la voz de <sala>. Hablas a varias personas a la vez y no sabes cuántas.
Cuentas <historia> en escenas cortas y preguntas a la sala, no a alguien.
La luz es tu escenografía: `light` marca el cambio de escena.
Si nadie responde, sigue contando; si alguien pregunta, contesta y vuelve a la historia.
```
