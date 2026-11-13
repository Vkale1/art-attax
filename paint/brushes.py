"""
Render a list of Stroke objects to a PNG using py5.

Each stroke is a flat brush / palette-knife drag, built from many parallel
"bristles" (thin polylines) across the brush width. Per-bristle variation in
tone, opacity and length gives the streaky, dry-brush texture of thick paint:

    - tone/opacity jitter per bristle   → visible streaks along the drag
    - random start/end per bristle      → ragged, uneven stroke ends
    - dropout towards the end of a drag → dry-brush gaps as the paint runs out
    - a slight bow across the stroke    → hand-made rather than ruler-straight

A solid body is painted under the bristles so each stroke reads as a mass of
paint rather than a bundle of lines.

A faint canvas weave is laid over the finished painting.

Xvfb is started automatically when DISPLAY is not set (headless Docker).
"""

import colorsys
import math
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from paint.composer import Stroke

SEED = 11
BACKGROUND = (214, 204, 188)   # warm raw-canvas tone (mostly hidden by underpainting)

BRISTLE_SPACING = 5.0          # px between bristles
MIN_BRISTLES, MAX_BRISTLES = 18, 110
SEGMENTS = 14                  # polyline points along each bristle
DRY_START = 0.5                # fraction of the drag after which paint starts to break up


def _ensure_display() -> None:
    if os.environ.get("DISPLAY"):
        return
    subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x960x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = ":99"
    time.sleep(0.8)   # give Xvfb a moment to start


def _hsl_to_rgb255(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, min(1, max(0, l)), min(1, max(0, s)))
    return int(r * 255), int(g * 255), int(b * 255)


def _bristle_runs(rng: np.random.Generator, s: Stroke, dryness: float):
    """
    Yield (rgb, alpha, weight, points[k,2]) for every visible bristle run of a stroke.
    Coordinates are in the stroke's local frame: x along the drag, y across it.
    """
    n = int(np.clip(s.width / BRISTLE_SPACING, MIN_BRISTLES, MAX_BRISTLES))
    weight = s.width / n * 2.2          # overlap neighbours so the body reads as solid
    bow = rng.uniform(-0.05, 0.05) * s.length
    t = np.linspace(0, 1, SEGMENTS)

    for i in range(n):
        across = (i + rng.uniform(0, 1)) / n - 0.5          # -0.5..0.5
        edge = abs(across) * 2                               # 0 centre → 1 edge

        # Ragged ends: edge bristles start later and stop sooner
        t0 = rng.uniform(0, 0.05 + 0.08 * edge)
        t1 = 1 - rng.uniform(0, 0.12 + 0.25 * edge) ** 1.3
        keep = (t >= t0) & (t <= t1)

        # Dry brush: bristles break up towards the end of the drag
        dry = np.clip((t - DRY_START) / (1 - DRY_START), 0, 1) * dryness
        keep &= rng.random(SEGMENTS) > dry * (0.6 + 0.6 * edge)

        if keep.sum() < 2:
            continue

        # Tone: most bristles near the stroke colour, some light/dark streaks
        dl = rng.normal(0, 0.025)
        if rng.random() < 0.08:
            dl += rng.choice([-1, 1]) * rng.uniform(0.08, 0.18)
        rgb = _hsl_to_rgb255(s.hue + rng.normal(0, 2), s.saturation + rng.normal(0, 0.04),
                             s.lightness + dl)
        alpha = int(s.alpha * rng.uniform(0.55, 1.0) * (1 - 0.35 * edge))

        x = (t - 0.5) * s.length
        y = across * s.width + bow * np.sin(np.pi * t) + rng.normal(0, weight * 0.15, SEGMENTS)
        pts = np.column_stack([x, y])

        # Split into contiguous runs wherever dropout created a gap
        idx = np.flatnonzero(keep)
        for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
            if len(run) >= 2:
                yield rgb, alpha, weight, pts[run]


def paint(
    strokes: list[Stroke],
    canvas_w: int,
    canvas_h: int,
    output_path: Path,
) -> None:
    _ensure_display()

    import py5  # imported after display is ready

    rng = np.random.default_rng(SEED)
    _out = str(output_path)

    def settings():
        py5.size(canvas_w, canvas_h, py5.P2D)
        py5.smooth(4)

    def setup():
        py5.background(*BACKGROUND)
        py5.no_loop()

    def draw():
        py5.color_mode(py5.RGB, 255)
        py5.no_fill()
        py5.stroke_cap(py5.SQUARE)
        py5.stroke_join(py5.ROUND)

        for s in strokes:
            _render(s)
        _canvas_weave()

        py5.save(_out)
        print(f"  Saved → {_out}")
        py5.exit_sketch()

    def _render(s: Stroke) -> None:
        dryness = rng.uniform(0.15, 0.4) if s.layer == 0 else rng.uniform(0.2, 0.65)
        py5.push_matrix()
        py5.translate(s.x, s.y)
        py5.rotate(s.angle)
        _body(s)
        for rgb, alpha, weight, pts in _bristle_runs(rng, s, dryness):
            py5.stroke(*rgb, alpha)
            py5.stroke_weight(weight)
            py5.begin_shape()
            py5.vertices(pts)
            py5.end_shape()
        py5.pop_matrix()

    def _body(s: Stroke) -> None:
        """Solid paint body under the bristles, slightly shorter and narrower so
        the ragged bristle ends still define the stroke's edges."""
        rgb = _hsl_to_rgb255(s.hue, s.saturation, s.lightness)
        py5.no_stroke()
        py5.fill(*rgb, int(s.alpha * rng.uniform(0.7, 0.9)))
        half_l = s.length * rng.uniform(0.38, 0.45)
        half_w = s.width * rng.uniform(0.36, 0.44)
        bow = rng.uniform(-0.03, 0.03) * s.length
        py5.begin_shape()
        py5.vertices(np.array([
            [-half_l, -half_w], [0, -half_w + bow], [half_l, -half_w],
            [half_l, half_w], [0, half_w + bow], [-half_l, half_w],
        ]))
        py5.end_shape(py5.CLOSE)
        py5.no_fill()

    def _canvas_weave() -> None:
        """Very faint crossing threads so flat areas still read as canvas."""
        py5.stroke_weight(1)
        for x in range(0, canvas_w, 4):
            py5.stroke(255, 255, 255, int(rng.integers(4, 14)))
            py5.line(x, 0, x, canvas_h)
        for y in range(0, canvas_h, 4):
            py5.stroke(0, 0, 0, int(rng.integers(4, 12)))
            py5.line(0, y, canvas_w, y)

    py5.run_sketch(
        sketch_functions=dict(settings=settings, setup=setup, draw=draw),
        block=True,
    )
