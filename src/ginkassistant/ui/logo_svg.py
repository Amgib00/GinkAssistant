"""
Gink's snowflake logo drawn as SVG in separate parts (arms + ringed tips,
outer hexagon, inner hexagon) so the middle can animate while Gink works,
the way Claude's logo does. Measured from the brand artwork; sharp at any size.
"""

import math
LIME, EDGE = "#A8F03C", "#55701F"
C = 512

def pt(r, deg):
    a = math.radians(deg)
    return C + r * math.cos(a), C - r * math.sin(a)

def hexagon(r, rot=90):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(r, rot + 60 * k) for k in range(6)))

def logo_svg(size=96, cls="gink-logo-svg"):
    arms, tips = [], []
    for k in range(6):
        ang = 90 - 60 * k                        # pointy-top: arms at 90, 30, -30, ...
        x0, y0 = pt(135, ang); x1, y1 = pt(310, ang)
        arms.append(f"M{x0:.1f},{y0:.1f}L{x1:.1f},{y1:.1f}")
        bx, by = pt(212, ang)                    # side branches leave the arm here
        for side in (-1, 1):
            tx, ty = pt(278, ang + side * 19.5)
            arms.append(f"M{bx:.1f},{by:.1f}L{tx:.1f},{ty:.1f}")
            tips.append((pt(305, ang + side * 19.5), k))
        tips.append((pt(342, ang), k))
    d = "".join(arms)
    def layer(stroke, w, name):
        circles = "".join(f'<circle class="tip t{k}" cx="{x:.1f}" cy="{y:.1f}" r="26"/>' for (x, y), k in tips)
        return (f'<g class="{name}" fill="none" stroke="{stroke}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">'
                f'<g class="arms"><path d="{d}"/>{circles}</g>'
                f'<polygon class="hex-outer" points="{hexagon(135)}"/>'
                f'<polygon class="hex-inner" points="{hexagon(72)}"/></g>')
    return (f'<svg class="{cls}" viewBox="150 130 724 764" width="{size}" height="{size}" aria-hidden="true">'
            + layer(EDGE, 24.5, "edge") + layer(LIME, 22, "lime") + "</svg>")
