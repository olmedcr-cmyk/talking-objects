"""Draws the documentation figures, in light and dark.

    python3 docs/assets/src/ilustraciones.py

Writes docs/assets/<name>-light.svg and <name>-dark.svg. The positions on the
board are schematic: close to a Raspberry Pi 5, not a mechanical drawing.
"""

from __future__ import annotations

import math
from pathlib import Path

from iso import MONO, Figure

OUT = Path(__file__).resolve().parent.parent

# The 40-pin header, as printed on every Raspberry Pi since the B+.
PINOUT = {
    1: "3V3", 2: "5V", 3: "GPIO2 SDA", 4: "5V", 5: "GPIO3 SCL", 6: "GND",
    7: "GPIO4", 8: "GPIO14 TXD", 9: "GND", 10: "GPIO15 RXD", 11: "GPIO17", 12: "GPIO18",
    13: "GPIO27", 14: "GND", 15: "GPIO22", 16: "GPIO23", 17: "3V3", 18: "GPIO24",
    19: "GPIO10 MOSI", 20: "GND", 21: "GPIO9 MISO", 22: "GPIO25", 23: "GPIO11 SCLK",
    24: "GPIO8 CE0", 25: "GND", 26: "GPIO7 CE1", 27: "GPIO0 ID_SD", 28: "GPIO1 ID_SC",
    29: "GPIO5", 30: "GND", 31: "GPIO6", 32: "GPIO12", 33: "GPIO13", 34: "GND",
    35: "GPIO19", 36: "GPIO16", 37: "GPIO26", 38: "GPIO20", 39: "GND", 40: "GPIO21",
}
# What the kit uses, and for what.
USED = {
    3: "LCD · SDA", 5: "LCD · SCL", 4: "LCD · 5 V", 6: "GND común",
    9: "interruptor · GND", 11: "interruptor", 19: "tira LED · datos",
}

HEADER_X0 = 7.0      # x of pins 1 and 2
PITCH = 2.54
ROW_OUTER = 2.3      # even pins, at the board's edge
ROW_INNER = 4.84     # odd pins, towards the centre


def pin_xy(n: int) -> tuple[float, float]:
    col = (n - 1) // 2
    return HEADER_X0 + col * PITCH, ROW_INNER if n % 2 else ROW_OUTER


def raspberry(f: Figure, *, dongle: bool = True) -> None:
    """A Raspberry Pi 5, schematic, 85 x 56 mm."""
    f.box(0, 0, 0, 85, 56, 1.4)
    for hx, hy in ((3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)):
        f.disc(hx, hy, 1.4, 1.4, "line edge")
        f.disc(hx, hy, 1.4, 2.6, "line")
    # Chips
    f.box(21, 19, 1.4, 14, 14, 1.1)
    f.top_text(23, 27.5, 2.5, "BCM2712", 2.1)
    f.box(38.5, 21, 1.4, 10, 11, 0.9)
    f.top_text(39.7, 27.8, 2.3, "RAM", 2.1)
    f.box(47, 38, 1.4, 8, 8, 0.9)
    f.top_text(48.6, 43.2, 2.3, "RP1", 2.1)
    # 40-pin header: base, then posts from back to front
    f.box(HEADER_X0 - 1.6, 1.0, 1.4, 19 * PITCH + 3.2, 5.1, 2.5)
    for n in sorted(PINOUT, key=lambda n: (pin_xy(n)[1], pin_xy(n)[0])):
        x, y = pin_xy(n)
        used = n in USED
        f.box(x - 0.34, y - 0.34, 3.9, 0.68, 0.68, 5.6 if used else 5.0, hi=used,
              cls="hi-fill" if used else "")
    # Front edge: USB-C power and two micro HDMI
    f.box(8, 50.5, 1.4, 9, 7, 3.2)
    f.rect_y(57.5, 9.2, 15.8, 2.0, 4.0, "line edge")
    for x0 in (22, 35):
        f.box(x0, 51, 1.4, 7.5, 6, 3)
        f.rect_y(57, x0 + 1.2, x0 + 6.3, 2.1, 3.8, "line")
    # Right edge: two USB stacks and Ethernet
    for y0 in (2.5, 20.5):
        f.box(68.5, y0, 1.4, 18.5, 14.5, 15.6)
        for z0 in (3.4, 10.4):
            f.rect_x(87, y0 + 2.2, y0 + 12.3, z0 + 1.4, z0 + 5.6, "line edge")
    f.box(66, 38.5, 1.4, 21, 16, 13.4)
    f.rect_x(87, 41, 52, 3.4, 11.6, "line edge")
    f.rect_x(87, 44.8, 48.2, 11.6, 13.0, "line")
    if dongle:
        # A USB sound card in the top port of the first stack.
        f.box(87, 4.4, 11.6, 25, 10.7, 6.6)
        f.disc_x(112, 7.2, 14.9, 1.75, "line edge")
        f.disc_x(112, 12.3, 14.9, 1.75, "line edge")


def fig_raspberry() -> Figure:
    f = Figure(1200, 900, 6.6, ox=500, oy=270,
               label="Raspberry Pi 5 en isométrico: cabezal de 40 pines con los pines que usa el kit "
                     "resaltados, tarjeta de sonido USB enchufada, alimentación por USB-C")
    f.text(40, 52, "OBJ-01 | RASPBERRY PI 5", "title")
    f.add('<line class="rule" x1="40" y1="72" x2="1160" y2="72"/>')
    raspberry(f)
    # Two short cables leaving the sound card
    for y in (7.2, 12.3):
        f.line3([(112, y, 14.9), (117, y, 14.9), (121, y + 1.5, 11), (123, y + 2, 6)], "wire")
    X, Y = f.p(123, 14.3, 6)
    f.text(X + 6, Y + 30, "al auricular", "sub", "end")
    # Above: points further left get higher labels, so no leader crosses a label
    f.callout((pin_xy(1)[0], pin_xy(1)[1], 9.0), 104, "02", "Pin 1 · lejos de los USB",
              sub="impares por dentro, pares por el borde")
    f.callout(pin_xy(19) + (9.5,), 168, "01", "Cabezal de 40 pines",
              sub="resaltados, los siete que usa el kit")
    f.callout((105, 9.7, 18.2), 236, "03", "Tarjeta de sonido USB", side="left",
              sub="con entrada de micro y de altavoz")
    # Below: points further left get lower labels
    # Below: points further left get lower labels, so no leader crosses a label
    f.callout((12.5, 57.5, 4.6), 850, "04", "USB-C · fuente oficial de 27 W")
    f.callout((25.7, 57, 4.4), 810, "05", "Micro HDMI · no se usan")
    f.text(1160, 52, "Esquema ilustrativo, no un plano mecánico", "sub", "end")
    return f


def handset(f: Figure, x: float, y: float, explode: float) -> dict[str, tuple]:
    """A telephone handset lying face up, with its two capsules lifted out."""
    f.box(x + 16, y - 7, 0, 92, 14, 9)  # the handle between the cups
    ear, mouth = (x, y), (x + 124, y)
    for cx, cy in (ear, mouth):
        f.cylinder(cx, cy, 0, 20, 14)
        for r in (4, 8, 13):
            f.disc(cx, cy, 14, r, "line")
        f.line3([(cx, cy, 14), (cx, cy, 14 + explode)], "ghost")
    # Speaker capsule over the ear cup, electret capsule over the mouth cup
    f.cylinder(ear[0], ear[1], 14 + explode, 13, 6, hi=True)
    f.disc(ear[0], ear[1], 20 + explode, 8, "line edge")
    f.cylinder(mouth[0], mouth[1], 14 + explode, 6, 5, hi=True)
    f.disc(mouth[0], mouth[1], 19 + explode, 3, "line edge")
    return {"ear": (ear[0], ear[1], 20 + explode), "mouth": (mouth[0], mouth[1], 19 + explode),
            "cord": (x + 108, y + 7, 3)}


def coil(a, b, turns: int, r: float = 3.0, n: int = 260):
    """A coiled telephone cord lying on the table from a to b."""
    (ax, ay, az), (bx, by, bz) = a, b
    out = []
    for i in range(n):
        t = i / (n - 1)
        ang = t * 2 * math.pi * turns
        out.append((ax + (bx - ax) * t + r * math.cos(ang),
                    ay + (by - ay) * t + r * math.sin(ang),
                    az + (bz - az) * t + 1.2 + 1.2 * math.sin(ang)))
    return out


def fig_audio() -> Figure:
    f = Figure(1200, 860, 2.0, ox=170, oy=360,
               label="Recorrido del audio: auricular despiezado con su altavoz y su cápsula de micrófono, "
                     "cable rizado hasta la tarjeta de sonido USB, Raspberry Pi 5 y agente en la nube")
    f.text(40, 52, "OBJ-02 | EL RECORRIDO DEL AUDIO", "title")
    f.add('<line class="rule" x1="40" y1="72" x2="1160" y2="72"/>')

    # Back to front: the Pi (furthest back), the card, then the handset and its cord
    px, py = 215, -165
    f.box(px, py, 0, 85, 56, 1.4)
    f.box(px + 5.4, py + 1, 1.4, 51.5, 5.1, 2.5)
    for i in range(20):
        f.box(px + 6.7 + i * 2.54, py + 1.9, 3.9, 0.6, 0.6, 4.4)
        f.box(px + 6.7 + i * 2.54, py + 4.4, 3.9, 0.6, 0.6, 4.4)
    f.box(px + 21, py + 19, 1.4, 14, 14, 1.1)
    f.top_text(px + 23, py + 27.5, 2.5, "BCM2712", 2.1)
    f.box(px + 68.5, py + 2.5, 1.4, 18.5, 14.5, 15.6)
    f.box(px + 68.5, py + 20.5, 1.4, 18.5, 14.5, 15.6)
    f.box(px + 66, py + 38.5, 1.4, 21, 16, 13.4)

    cx, cy = 168, -52  # the USB sound card
    # USB cable: along the table in front of the Pi, then up into a port
    f.line3([(cx + 34, cy + 10, 4), (cx + 50, cy + 14, 0), (px + 100, py + 66, 0),
             (px + 100, py + 28, 0), (px + 92, py + 28, 6), (px + 87, py + 28, 6)], "wire")
    f.box(cx, cy, 0, 34, 20, 10)
    f.top_text(cx + 4, cy + 12, 10, "USB AUDIO", 3.4)
    f.disc_x(cx + 34, cy + 6, 5, 2.2, "line edge")
    f.disc_x(cx + 34, cy + 14, 5, 2.2, "line edge")

    h = handset(f, 0, 0, explode=36)
    start = (124 + 14.2, -14.2, 3)  # the right side of the mouth cup
    end = (cx - 14, cy + 10, 2)
    f.line3([start] + coil((start[0] + 3, start[1] - 2, 0), end, turns=7) +
            [(cx - 4, cy + 6, 5), (cx, cy + 6, 5)], "wire")
    f.line3([end, (cx - 4, cy + 14, 5), (cx, cy + 14, 5)], "wire")

    # Labels: points further left get higher rows
    f.callout(h["ear"], 104, "06", "Altavoz del auricular", sub="la respuesta suena aquí")
    f.callout(h["mouth"], 168, "01", "Cápsula de micrófono", sub="electret; si es de carbón, cámbiala")
    f.callout((cx + 17, cy + 4, 10), 232, "02", "Tarjeta de sonido USB",
              sub="micro: rosa · altavoz: verde")
    f.callout((px + 30, py + 3, 8), 296, "03", "Raspberry Pi 5", sub="un hilo es dueño de la tarjeta")

    # The path of a voice, as a flat track
    y0 = 640
    f.add(f'<line class="rule" x1="40" y1="{y0 - 34}" x2="1160" y2="{y0 - 34}"/>')
    steps = [
        ("01", "Hablas", "la cápsula convierte la voz en señal"),
        ("02", "Digital", "la tarjeta la muestrea: 48\u00a0kHz, 16\u00a0bit"),
        ("03", "Ducking", "la Pi baja el micro mientras habla el agente"),
        ("04", "Agente", "Vidiv primero, ElevenLabs de reserva"),
        ("05", "Analógica", "la tarjeta convierte la respuesta"),
        ("06", "Escuchas", "suena en el auricular"),
    ]
    w = 1120 / len(steps)
    for i, (idx, head, sub) in enumerate(steps):
        x = 40 + i * w
        f.add(f'<line class="rule" x1="{x:.1f}" y1="{y0 - 34}" x2="{x:.1f}" y2="{y0 + 92}"/>')
        f.add(f'<text class="label" x="{x + 14:.1f}" y="{y0}"><tspan class="idx">{idx}</tspan>  {head}</text>')
        for j, part in enumerate(_wrap(sub, 21)):
            f.add(f'<text class="sub" x="{x + 14:.1f}" y="{y0 + 26 + j * 20}">{part}</text>')
    ya = y0 + 132
    mid = 40 + 3.5 * w
    f.add(f'<polyline class="arrow" points="54,{ya} {mid - 6:.0f},{ya}"/>')
    f.add(f'<polyline class="arrow" points="{mid - 14:.0f},{ya - 5} {mid - 6:.0f},{ya} {mid - 14:.0f},{ya + 5}"/>')
    f.add(f'<polyline class="arrow" points="{mid + 6:.0f},{ya} 1146,{ya}"/>')
    f.add(f'<polyline class="arrow" points="1138,{ya - 5} 1146,{ya} 1138,{ya + 5}"/>')
    f.add(f'<text class="sub" x="54" y="{ya + 26}">ida: tu voz, a 48 kHz</text>')
    f.add(f'<text class="sub" x="{mid + 6:.0f}" y="{ya + 26}">vuelta: la respuesta del agente</text>')
    return f


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(" "), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    return lines + [line]


def fig_pinout() -> Figure:
    f = Figure(1200, 950, 1, 0, 0,
               label="Cabezal de 40 pines de la Raspberry Pi: número y nombre de cada pin, "
                     "con los siete que usa el kit marcados y su función")
    f.text(40, 52, "OBJ-03 | CABEZAL DE 40 PINES", "title")
    f.add('<line class="rule" x1="40" y1="72" x2="1160" y2="72"/>')
    row_h = 36
    top = 120
    cx_odd, cx_even = 560, 640
    for n in range(1, 41):
        r = (n - 1) // 2
        y = top + r * row_h
        odd = n % 2 == 1
        cx = cx_odd if odd else cx_even
        used = n in USED
        name = PINOUT[n]
        power = name in ("3V3", "5V", "GND")
        if used:
            f.add(f'<circle cx="{cx}" cy="{y}" r="11" class="pin-used"/>')
        else:
            shape = (f'<rect x="{cx - 10}" y="{y - 10}" width="20" height="20" class="pin"/>' if n == 1
                     else f'<circle cx="{cx}" cy="{y}" r="10" class="pin{" power" if power else ""}"/>')
            f.add(shape)
        f.add(f'<text class="num{" num-used" if used else ""}" x="{cx}" y="{y + 4.5}" text-anchor="middle">{n}</text>')
        tx = cx - 28 if odd else cx + 28
        anchor = "end" if odd else "start"
        f.add(f'<text class="{"pname-used" if used else "pname"}" x="{tx}" y="{y + 5}" text-anchor="{anchor}">{name}</text>')
        if used:
            fx = 40 if odd else 1160
            lx = tx - 150 if odd else tx + 150
            f.add(f'<line class="leader" x1="{lx}" y1="{y}" x2="{fx + (170 if odd else -170)}" y2="{y}"/>')
            f.add(f'<text class="use" x="{fx}" y="{y + 5}" text-anchor="{"start" if odd else "end"}">{USED[n]}</text>')
    f.add(f'<rect x="{cx_odd - 22}" y="{top - 22}" width="{cx_even - cx_odd + 44}" height="{row_h * 19 + 44}" class="frame"/>')
    yb = top + 19 * row_h + 70
    f.add(f'<line class="rule" x1="40" y1="{yb - 30}" x2="1160" y2="{yb - 30}"/>')
    f.text(40, yb, "Pin 1 (cuadrado) en la esquina opuesta a los USB. Impares por dentro, pares por el borde de la placa.", "sub")
    f.text(40, yb + 24, "Los pines 4 y 2 dan 5 V de la placa: valen para el LCD, no para la tira, que va con su propia fuente.", "sub")
    f.text(40, yb + 48, "Desconecta la alimentación antes de cablear. Un 5 V en un pin de 3,3 V daña la placa.", "sub")
    return f


PINOUT_STYLE = """
.pin{{fill:{plate};stroke:{edge};stroke-width:1.1}}
.pin.power{{stroke-dasharray:2 2}}
.frame{{fill:none;stroke:{mid};stroke-width:1}}
.num{{font:12px {mono};fill:{text}}}
.num-used{{fill:{bg}}}
.pname{{font:14px {mono};fill:{text};opacity:.75}}
.pname-used{{font:14px {mono};fill:{hi}}}
.use{{font:15px {mono};fill:{hi}}}
.pin-used{{fill:{hi}}}
"""


def write(name: str, fig: Figure, extra_style: str = "") -> None:
    from iso import THEMES

    for theme in ("light", "dark"):
        svg = fig.svg(theme)
        if extra_style:
            t = THEMES[theme]
            css = extra_style.format(mono=MONO, **t)
            svg = svg.replace("</style>", css + "</style>", 1)
        (OUT / f"{name}-{theme}.svg").write_text(svg, encoding="utf-8")
        print("wrote", OUT / f"{name}-{theme}.svg")


if __name__ == "__main__":
    write("raspberry", fig_raspberry())
    write("audio", fig_audio())
    write("pines", fig_pinout(), PINOUT_STYLE)
