# 05 · Luces y periféricos

Todo lo que el objeto hace con el cuerpo pasa por el **registro de acciones**: una puerta única que valida, aplica cupos y registra. Esta guía explica las dos acciones que trae el kit y cómo añadir más.

## Tira de LED (`light`)

```json
{"color": "blue", "effect": "breathe", "seconds": 6}
```

| Parámetro | Valores |
|---|---|
| `color` | `white`, `warm`, `red`, `green`, `blue`, `amber`, `violet`, `off` |
| `effect` | `solid`, `breathe`, `pulse` |
| `seconds` | de 0,5 a 60; al acabar vuelve a la luz de reposo |

Ajustes en `config.env`: `LED_COUNT`, `LED_BRIGHTNESS` (de 0 a 1) y `LED_IDLE_COLOR` (`R,G,B` u `off`).

Lo eléctrico importa más que el código:

- **Fuente aparte de 5 V** y **masa común** con la Pi.
- **74AHCT125** entre GPIO10 y la entrada de datos. Sin él, la tira funciona a ratos.
- **1000 µF** entre 5 V y GND en la entrada de la tira, y **330 Ω** en serie con los datos.
- Brillo moderado (`0.35` por defecto): menos consumo, menos calor y más vida útil.

Para cambiar la paleta, edita `NAMED_COLORS` en `device/talking_objects/devices/leds.py`. El esquema que ve el agente se actualiza solo.

## Pantalla (`show_message`)

```json
{"text": "TE ESTOY ESCUCHANDO"}
```

Un LCD de 20x4 por I2C. El texto se pasa a mayúsculas, se reparte en cuatro líneas y pierde los acentos, que el juego de caracteres del HD44780 no tiene. Hasta 80 caracteres, cuatro mensajes por conversación y ocho segundos entre uno y otro.

## Cupos

```python
Budget(per_call=4, per_day=200, cooldown_s=8)
```

- `per_call`: veces por conversación; se repone al empezar otra.
- `per_day`: veces al día. Para lo que consume algo, como papel o líquido.
- `cooldown_s`: segundos mínimos entre dos usos.

Si se agota un cupo, la acción se rechaza sin ruido: el agente recibe el motivo y la conversación sigue.

## Añadir un periférico

El patrón siempre es el mismo:

1. Un módulo en `device/talking_objects/devices/` que **degrada a no-op** si falta la librería o el hardware. Que nunca lance una excepción hacia la conversación.
2. Un `validate` que normaliza y recorta los argumentos.
3. Un `register(...)` en `App._register_actions` con descripción, esquema JSON y cupo.
4. Si quieres que reaccione solo, una regla en `rules.toml`.

Ideas que encajan con este patrón:

| Periférico | Cómo se conecta | Librería |
|---|---|---|
| Relé (humo, motor, timbre) | GPIO a un módulo de relé con optoacoplador | `gpiozero.OutputDevice` |
| Servo (un gesto, una mirada) | PWM por hardware o una placa PCA9685 por I2C | `gpiozero.Servo` o `adafruit-circuitpython-servokit` |
| Impresora térmica (un ticket de recuerdo) | Bluetooth LE o USB | `bleak` o `python-escpos` |
| DMX (focos de escena) | Adaptador USB a DMX | `pyftdi` u OLA |
| Sensor de presencia | Salida de contacto al pin del interruptor | El propio `Trigger` |

TeleTUP, la cabina de GAIA, añade así una impresora térmica que imprime un ticket cuando el personaje lo pide, con un cupo por llamada y otro por día.

Siguiente: [06 · Operación](06-operacion.md).
