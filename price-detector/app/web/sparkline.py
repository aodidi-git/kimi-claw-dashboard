"""Tiny dependency-free inline-SVG sparkline (no charting library)."""
from __future__ import annotations


def sparkline_svg(values: list[float], width: int = 140, height: int = 28,
                  pad: int = 3) -> str:
    """Return an inline SVG polyline for ``values`` (chronological order).

    A flat line is drawn for constant series; an empty/short series yields a
    minimal placeholder. The last point is marked with a small dot.
    """
    pts = [v for v in values if v is not None]
    if not pts:
        return f'<svg width="{width}" height="{height}"></svg>'

    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts)
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    step = inner_w / (n - 1) if n > 1 else 0.0

    coords = []
    for i, v in enumerate(pts):
        x = pad + i * step
        # higher value -> higher on screen (smaller y)
        y = pad + inner_h * (1 - (v - lo) / span)
        coords.append((round(x, 1), round(y, 1)))

    points = " ".join(f"{x},{y}" for x, y in coords)
    lx, ly = coords[-1]
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" role="img">'
        f'<polyline fill="none" stroke="#5b8cff" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{points}"/>'
        f'<circle cx="{lx}" cy="{ly}" r="2.2" fill="#2faf6a"/>'
        f"</svg>"
    )
