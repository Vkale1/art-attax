"""
Render a list of Stroke objects to a PNG using py5.

Brush styles and their visual character:
    wash         — large, semi-transparent ellipse (domain-level washes of colour)
    broad        — thick tapering bezier (phylum)
    medium_broad — mid-weight bezier (class)
    medium       — medium bezier (order)
    medium_fine  — short lighter stroke (family)
    fine         — fine line (genus)
    hair         — hairline (species)

Xvfb is started automatically when DISPLAY is not set (headless Docker).
"""

import colorsys
import math
import os
import subprocess
import time
from pathlib import Path

from paint.composer import Stroke

# ---------------------------------------------------------------------------
# Brush parameter table  (weight=stroke weight px, length=stroke length px,
# alpha=0-255, for wash: ellipse_rx/ry override length)
# ---------------------------------------------------------------------------
_BRUSH = {
    "wash":         dict(weight=0,    length=0,    alpha=30,  ellipse_rx=900, ellipse_ry=650),
    "broad":        dict(weight=300,  length=650,  alpha=120),
    "medium_broad": dict(weight=200,  length=480,  alpha=140),
    "medium":       dict(weight=120,  length=340,  alpha=160),
    "medium_fine":  dict(weight=70,   length=240,  alpha=180),
    "fine":         dict(weight=38,   length=165,  alpha=200),
    "hair":         dict(weight=16,   length=110,  alpha=220),
}
_FALLBACK = _BRUSH["medium"]

BACKGROUND = (245, 240, 228)   # warm off-white


def _ensure_display() -> None:
    if os.environ.get("DISPLAY"):
        return
    proc = subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x960x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = ":99"
    time.sleep(0.8)   # give Xvfb a moment to start


def _hsl_to_rgb255(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def paint(
    strokes: list[Stroke],
    canvas_w: int,
    canvas_h: int,
    output_path: Path,
) -> None:
    _ensure_display()

    import py5  # imported after display is ready

    _strokes = strokes
    _w, _h = canvas_w, canvas_h
    _out = str(output_path)

    def settings():
        py5.size(_w, _h, py5.P2D)

    def setup():
        py5.background(*BACKGROUND)
        py5.no_loop()

    def draw():
        py5.color_mode(py5.RGB, 255)
        for s in _strokes:
            _render(s)
        py5.save(_out)
        print(f"  Saved → {_out}")
        py5.exit_sketch()

    def _render(s: Stroke) -> None:
        params = _BRUSH.get(s.brush_style, _FALLBACK)
        r, g, b = _hsl_to_rgb255(s.hue, s.saturation, s.lightness)
        alpha = params["alpha"]

        if s.brush_style == "wash":
            rx = params["ellipse_rx"] * (0.7 + 0.6 * py5.random(1))
            ry = params["ellipse_ry"] * (0.7 + 0.6 * py5.random(1))
            py5.no_stroke()
            py5.fill(r, g, b, alpha)
            py5.push_matrix()
            py5.translate(s.x, s.y)
            py5.rotate(s.angle)
            py5.ellipse(0, 0, rx * 2, ry * 2)
            py5.pop_matrix()
        else:
            length = params["length"] * (0.6 + 0.8 * py5.random(1))
            weight = params["weight"]

            # Slight lateral wobble for organic feel
            wobble = weight * 1.5
            dx = math.cos(s.angle) * length * 0.5
            dy = math.sin(s.angle) * length * 0.5
            perp_x = -math.sin(s.angle)
            perp_y = math.cos(s.angle)
            cx1 = s.x - dx * 0.5 + perp_x * py5.random(-wobble, wobble)
            cy1 = s.y - dy * 0.5 + perp_y * py5.random(-wobble, wobble)
            cx2 = s.x + dx * 0.5 + perp_x * py5.random(-wobble, wobble)
            cy2 = s.y + dy * 0.5 + perp_y * py5.random(-wobble, wobble)

            py5.no_fill()
            py5.stroke(r, g, b, alpha)
            py5.stroke_weight(weight)
            py5.bezier(
                s.x - dx, s.y - dy,
                cx1, cy1,
                cx2, cy2,
                s.x + dx, s.y + dy,
            )

    py5.run_sketch(
        sketch_functions=dict(settings=settings, setup=setup, draw=draw),
        block=True,
    )
