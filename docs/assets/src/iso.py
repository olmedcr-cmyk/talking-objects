"""A tiny isometric line-drawing engine for the documentation figures.

It follows Hairline's grammar (https://github.com/lucasmarkes/hairline):
filled plates, thin strokes, one ink for what matters and greys for the
rest. Hairline itself draws interactive figures in the browser; GitHub only
shows static SVG, so these figures are drawn here and written as files.

Coordinates are millimetres: x along the length, y along the depth, z up.
Shapes are painted in the order they are added, so add them back to front.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

C30 = math.cos(math.pi / 6)
S30 = 0.5

THEMES = {
    # The brand's Hairline theme (see the Divina Machina brand book).
    "light": {
        "bg": "#FFFFFF", "plate": "#FFFFFF", "hi": "#30302E", "edge": "#474747",
        "mid": "#C6C5C0", "lo": "#E7E6E1", "text": "#474747", "ink": "#30302E",
    },
    "dark": {
        "bg": "#000000", "plate": "#000000", "hi": "#F2F2F2", "edge": "#C6C5C0",
        "mid": "#474747", "lo": "#1E1E1D", "text": "#C6C5C0", "ink": "#F2F2F2",
    },
}

MONO = "'Roboto Mono', ui-monospace, Menlo, Consolas, monospace"
SANS = "'Bricolage Grotesque', 'Helvetica Neue', Helvetica, Arial, sans-serif"


def _pts(points) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


@dataclass
class Figure:
    width: int
    height: int
    scale: float
    ox: float
    oy: float
    label: str
    parts: list[str] = field(default_factory=list)

    # -- projection ----------------------------------------------------------
    def p(self, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        return (
            self.ox + (x - y) * C30 * self.scale,
            self.oy + (x + y) * S30 * self.scale - z * self.scale,
        )

    def add(self, svg: str) -> None:
        self.parts.append(svg)

    # -- primitives ----------------------------------------------------------
    def poly(self, pts3, cls="face", closed=True) -> None:
        pts = [self.p(*q) for q in pts3]
        tag = "polygon" if closed else "polyline"
        self.add(f'<{tag} class="{cls}" points="{_pts(pts)}"/>')

    def box(self, x, y, z, w, d, h, cls="", hi=False) -> None:
        """A solid block. Visible faces: top, +x (right) and +y (left)."""
        c = "hi" if hi else "edge"
        t = [(x, y, z + h), (x + w, y, z + h), (x + w, y + d, z + h), (x, y + d, z + h)]
        r = [(x + w, y, z), (x + w, y + d, z), (x + w, y + d, z + h), (x + w, y, z + h)]
        f = [(x, y + d, z), (x + w, y + d, z), (x + w, y + d, z + h), (x, y + d, z + h)]
        self.poly(r, f"face side {cls}")
        self.poly(f, f"face side {cls}")
        self.poly(t, f"face top {cls}")
        sil = [(x, y, z + h), (x + w, y, z + h), (x + w, y, z), (x + w, y + d, z),
               (x, y + d, z), (x, y + d, z + h)]
        self.poly(sil, f"sil {c}")

    def ellipse_pts(self, cx, cy, z, r, a0=0.0, a1=2 * math.pi, n=48):
        return [self.p(cx + r * math.cos(a0 + (a1 - a0) * i / n),
                       cy + r * math.sin(a0 + (a1 - a0) * i / n), z) for i in range(n + 1)]

    def cylinder(self, cx, cy, z, r, h, hi=False, cls="") -> None:
        """Vertical cylinder standing on z."""
        c = "hi" if hi else "edge"
        # Silhouette extremes in screen x are at -45° and 135°.
        a0, a1 = -math.pi / 4, 3 * math.pi / 4
        bottom = self.ellipse_pts(cx, cy, z, r, a0, a1)          # front arc
        top = self.ellipse_pts(cx, cy, z + h, r, a1, a0)          # same arc, reversed, on top
        self.add(f'<polygon class="face side {cls}" points="{_pts(bottom + top)}"/>')
        ring = self.ellipse_pts(cx, cy, z + h, r)
        self.add(f'<polygon class="face top {cls}" points="{_pts(ring)}"/>')
        self.add(f'<polyline class="sil {c}" points="{_pts(bottom)}"/>')
        for a in (a0, a1):
            self.add(f'<polyline class="sil {c}" points="{_pts([self.p(cx + r*math.cos(a), cy + r*math.sin(a), z), self.p(cx + r*math.cos(a), cy + r*math.sin(a), z + h)])}"/>')
        self.add(f'<polygon class="sil {c}" points="{_pts(ring)}"/>')

    def disc(self, cx, cy, z, r, cls="line") -> None:
        """A flat circle on a horizontal plane (a hole, a grille)."""
        self.add(f'<polygon class="{cls}" points="{_pts(self.ellipse_pts(cx, cy, z, r))}"/>')

    def disc_x(self, x, cy, cz, r, cls="line", n=40) -> None:
        """A circle on a plane facing +x (a jack on the side of a box)."""
        pts = [self.p(x, cy + r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n))
               for i in range(n + 1)]
        self.add(f'<polygon class="{cls}" points="{_pts(pts)}"/>')

    def rect_x(self, x, y0, y1, z0, z1, cls="line") -> None:
        """A rectangle on a plane facing +x (a port opening)."""
        self.poly([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], cls)

    def rect_y(self, y, x0, x1, z0, z1, cls="line") -> None:
        """A rectangle on a plane facing +y."""
        self.poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], cls)

    def line3(self, pts3, cls="wire") -> None:
        self.poly(pts3, cls, closed=False)

    def top_text(self, x, y, z, text, size=2.2, cls="chip") -> None:
        """Text lying on a horizontal surface, along +x."""
        k = self.scale
        X, Y = self.p(x, y, z)
        self.add(
            f'<text class="{cls}" font-size="{size}" '
            f'transform="matrix({C30*k:.4f} {S30*k:.4f} {-C30*k:.4f} {S30*k:.4f} {X:.2f} {Y:.2f})">{text}</text>'
        )

    # -- annotation (flat, on screen) ----------------------------------------
    def callout(self, at3, y_label: float, index: str, text: str, side: str = "right",
                sub: str = "") -> None:
        """A vertical leader from a point in 3D to a label beside its end.

        The label sits to the right or left of the line, never on it, so a
        leader never crosses its own text.
        """
        ax, ay = self.p(*at3)
        self.add(f'<circle class="dot" cx="{ax:.2f}" cy="{ay:.2f}" r="2.6"/>')
        self.add(f'<line class="leader" x1="{ax:.2f}" y1="{ay:.2f}" x2="{ax:.2f}" y2="{y_label:.2f}"/>')
        self.add(f'<line class="leader" x1="{ax - 4:.2f}" y1="{y_label:.2f}" x2="{ax + 4:.2f}" y2="{y_label:.2f}"/>')
        dx, anchor = (10, "start") if side == "right" else (-10, "end")
        up = y_label < ay  # label above the object: text hangs below the tick
        y = y_label + (16 if up else -8)
        self.add(f'<text class="label" x="{ax + dx:.2f}" y="{y:.2f}" text-anchor="{anchor}">'
                 f'<tspan class="idx">{index}</tspan>  {text}</text>')
        if sub:
            self.add(f'<text class="sub" x="{ax + dx:.2f}" y="{y + 20:.2f}" text-anchor="{anchor}">{sub}</text>')

    def text(self, x, y, text, cls="label", anchor="start") -> None:
        self.add(f'<text class="{cls}" x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}">{text}</text>')

    # -- output --------------------------------------------------------------
    def svg(self, theme: str) -> str:
        t = THEMES[theme]
        style = f"""
.face{{fill:{t['plate']};stroke:{t['mid']};stroke-width:.9;stroke-linejoin:round}}
.sil{{fill:none;stroke-width:1.15;stroke-linejoin:round;stroke-linecap:round}}
.sil.edge{{stroke:{t['edge']}}} .sil.hi{{stroke:{t['hi']};stroke-width:1.6}}
.face.hi-fill{{fill:{t['hi']};stroke:{t['hi']}}}
.line{{fill:none;stroke:{t['mid']};stroke-width:.9;stroke-linejoin:round}}
.line.edge{{stroke:{t['edge']}}}
.wire{{fill:none;stroke:{t['edge']};stroke-width:1.2;stroke-linejoin:round;stroke-linecap:round}}
.wire.hi{{stroke:{t['hi']};stroke-width:1.6}}
.ghost{{fill:none;stroke:{t['mid']};stroke-width:.9;stroke-dasharray:3 4}}
.leader{{fill:none;stroke:{t['mid']};stroke-width:1}}
.dot{{fill:{t['hi']}}}
.label{{font:15px {MONO};fill:{t['text']};letter-spacing:.2px}}
.label .idx{{fill:{t['hi']}}}
.sub{{font:13px {MONO};fill:{t['text']};opacity:.8}}
.title{{font:15px {MONO};fill:{t['text']};letter-spacing:.6px}}
.head{{font:26px {SANS};fill:{t['ink']};letter-spacing:-.4px}}
.chip{{font-family:{MONO};fill:{t['edge']}}}
.rule{{stroke:{t['mid']};stroke-width:1}}
.arrow{{fill:none;stroke:{t['hi']};stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}}
"""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-label="{self.label}">\n'
            f'<style>{style}</style>\n<rect width="{self.width}" height="{self.height}" fill="{t["bg"]}"/>\n'
            + "\n".join(self.parts) + "\n</svg>\n"
        )
