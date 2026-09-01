"""
charts.py
---------
Tiny dependency-free SVG chart helpers. Everything renders as an inline
<svg> string so the review pack is a single portable file with no JS and
no image assets. Colours are passed in by the caller so the same code
works in light and dark themes.
"""

from __future__ import annotations

from typing import Sequence


def _scale(values: Sequence[float], lo: float, hi: float, a: float, b: float) -> list[float]:
    if hi - lo < 1e-9:
        return [(a + b) / 2 for _ in values]
    return [a + (b - a) * (v - lo) / (hi - lo) for v in values]


def sparkline(
    series: Sequence[float],
    *,
    width: int = 132,
    height: int = 34,
    stroke: str = "#3b82f6",
    target: float | None = None,
    pad: int = 3,
) -> str:
    if not series:
        return ""
    vmin, vmax = min(series), max(series)
    if target is not None:
        vmin, vmax = min(vmin, target), max(vmax, target)
    span = (vmax - vmin) or 1
    vmin -= span * 0.12
    vmax += span * 0.12

    xs = _scale(range(len(series)), 0, len(series) - 1, pad, width - pad)
    ys = _scale(series, vmin, vmax, height - pad, pad)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    last_x, last_y = xs[-1], ys[-1]

    tgt_line = ""
    if target is not None:
        ty = _scale([target], vmin, vmax, height - pad, pad)[0]
        tgt_line = (
            f'<line x1="{pad}" y1="{ty:.1f}" x2="{width - pad}" y2="{ty:.1f}" '
            f'stroke="currentColor" stroke-dasharray="2 2" stroke-width="1" opacity="0.35"/>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'class="spark" role="img" aria-hidden="true">'
        f"{tgt_line}"
        f'<polyline fill="none" stroke="{stroke}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.4" fill="{stroke}"/>'
        f"</svg>"
    )


def line_chart(
    series: Sequence[float],
    week_labels: Sequence[str],
    *,
    width: int = 520,
    height: int = 190,
    stroke: str = "#3b82f6",
    fill: str = "rgba(59,130,246,0.12)",
    target: float | None = None,
    amber: float | None = None,
    direction: str = "higher_better",
    fmt: str = "{:.0f}",
    title: str = "",
) -> str:
    if not series:
        return ""
    m = {"t": 16, "r": 14, "b": 26, "l": 44}
    iw, ih = width - m["l"] - m["r"], height - m["t"] - m["b"]

    marks = list(series)
    for extra in (target, amber):
        if extra is not None:
            marks.append(extra)
    vmin, vmax = min(marks), max(marks)
    span = (vmax - vmin) or 1
    vmin -= span * 0.15
    vmax += span * 0.15

    def X(i: int) -> float:
        return m["l"] + (iw * i / (len(series) - 1) if len(series) > 1 else iw / 2)

    def Y(v: float) -> float:
        return m["t"] + ih * (1 - (v - vmin) / (vmax - vmin))

    pts = [(X(i), Y(v)) for i, v in enumerate(series)]
    line_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (
        f'M {pts[0][0]:.1f},{m["t"] + ih:.1f} '
        + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
        + f' L {pts[-1][0]:.1f},{m["t"] + ih:.1f} Z'
    )

    # y gridlines / labels (4 bands)
    grid = []
    for k in range(5):
        gv = vmin + (vmax - vmin) * k / 4
        gy = Y(gv)
        grid.append(
            f'<line x1="{m["l"]}" y1="{gy:.1f}" x2="{width - m["r"]}" y2="{gy:.1f}" '
            f'class="grid"/>'
            f'<text x="{m["l"] - 6}" y="{gy + 3:.1f}" class="ytick" text-anchor="end">'
            f'{fmt.format(gv)}</text>'
        )

    # target / amber reference lines
    refs = []
    if target is not None:
        ty = Y(target)
        refs.append(
            f'<line x1="{m["l"]}" y1="{ty:.1f}" x2="{width - m["r"]}" y2="{ty:.1f}" '
            f'class="ref-target"/>'
            f'<text x="{width - m["r"]}" y="{ty - 4:.1f}" class="ref-label" '
            f'text-anchor="end">target {fmt.format(target)}</text>'
        )
    if amber is not None:
        ay = Y(amber)
        refs.append(
            f'<line x1="{m["l"]}" y1="{ay:.1f}" x2="{width - m["r"]}" y2="{ay:.1f}" '
            f'class="ref-amber"/>'
        )

    # x labels: first, middle, last
    idxs = sorted({0, len(series) // 2, len(series) - 1})
    xlab = "".join(
        f'<text x="{X(i):.1f}" y="{height - 8}" class="xtick" text-anchor="middle">'
        f"{week_labels[i]}</text>"
        for i in idxs if i < len(week_labels)
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" class="linechart" role="img" '
        f'aria-label="{title}">'
        f'{"".join(grid)}'
        f'<path d="{area}" fill="{fill}" stroke="none"/>'
        f'{"".join(refs)}'
        f'<polyline fill="none" stroke="{stroke}" stroke-width="2.2" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{line_pts}"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.4" fill="{stroke}"/>'
        f"{xlab}"
        f"</svg>"
    )


def rag_bar(counts: dict, *, width: int = 132, height: int = 12) -> str:
    order = [("green", "var(--g)"), ("amber", "var(--a)"), ("red", "var(--r)")]
    total = sum(counts.get(k, 0) for k, _ in order) or 1
    x = 0.0
    rects = []
    for key, col in order:
        w = width * counts.get(key, 0) / total
        if w > 0:
            rects.append(
                f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" '
                f'fill="{col}" rx="1.5"/>'
            )
        x += w
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'class="ragbar" role="img" aria-hidden="true">{"".join(rects)}</svg>'
    )
