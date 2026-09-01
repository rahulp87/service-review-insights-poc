"""
build_review_pack.py
--------------------
Orchestrator. Reads the standardised KPI config + weekly metrics, runs the
analytics and narrative layers, renders the board-ready HTML pack, and
writes a machine-readable JSON summary alongside it.

    python src/build_review_pack.py
        --> output/service_review_pack.html
        --> output/review_summary.json

The point of the POC: one command, one template, one KPI definition file
turns raw operational data into an executive review pack.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from analytics import ReviewAnalysis, load_config, load_data
from charts import line_chart, rag_bar, sparkline
from narrative import NarrativeBuilder

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output"
TPL_DIR = Path(__file__).resolve().parent / "templates"

RAG_STROKE = {"green": "#2f8f5b", "amber": "#c1841c", "red": "#c0392f", "grey": "#8a8f99"}
ACCENT = "#0e7c7b"


def _trend_glyph(trend: str, favourable: bool | None = None) -> str:
    return {"improving": "▲", "deteriorating": "▼", "stable": "–"}.get(trend, "–")


def build_context() -> dict:
    cfg = load_config()
    df = load_data()
    analysis = ReviewAnalysis(df, cfg)
    group = analysis.group_rollup()
    narr = NarrativeBuilder(analysis, group)

    # ---- group scorecard rows (headline KPIs first) -------------------
    scorecard = []
    for kpi in cfg["kpis"]:
        k = group["kpis"][kpi["key"]]
        stroke = RAG_STROKE[k["rag"]]
        scorecard.append({
            "key": kpi["key"],
            "label": k["label"],
            "category": k["category"],
            "headline": k["headline"],
            "q_start": k["fmt"].format(k["q_start"]),
            "current": k["fmt"].format(k["current"]),
            "target": k["fmt"].format(k["target"]),
            "wow": _signed(k, k["wow_delta"]),
            "wow_fav": k["favourable_wow"],
            "q_delta": _signed(k, k["q_delta"]),
            "q_fav": k["favourable_q"],
            "rag": k["rag"],
            "trend": k["trend"],
            "trend_glyph": _trend_glyph(k["trend"]),
            "spark": sparkline(k["series"], width=82, height=26, stroke=stroke, target=k["target"]),
        })

    # ---- per business unit blocks -----------------------------------
    readouts = narr.bu_readouts()
    bu_blocks = []
    for name, bu in analysis.units.items():
        ro = readouts[name]
        sl = bu.kpis["service_level"]
        mini = []
        for key in ("service_level", "asa", "abandon_rate", "aht", "fcr", "csat",
                    "cost_per_contact", "adherence"):
            r = bu.kpis[key]
            mini.append({
                "label": cfg["_kpi_by_key"][key]["label"],
                "short": cfg["_kpi_by_key"][key]["short"],
                "value": r.f(r.current),
                "wow": _signed_kpi(r, r.wow_delta),
                "rag": r.rag,
                "trend_glyph": _trend_glyph(r.trend),
                "trend": r.trend,
                "spark": sparkline(r.series, width=104, height=26,
                                   stroke=RAG_STROKE[r.rag], target=r.target),
            })
        bu_blocks.append({
            "name": name,
            "verdict": ro["verdict"],
            "score": bu.headline_score,
            "readout": ro["text"],
            "rag_counts": bu.rag_counts,
            "rag_bar": rag_bar(bu.rag_counts),
            "volume_handled": bu.volume_handled,
            "mini": mini,
            "sl_chart": line_chart(
                sl.series, analysis.week_labels, stroke=RAG_STROKE[sl.rag],
                fill="rgba(14,124,123,0.10)", target=sl.target, amber=cfg["_kpi_by_key"]["service_level"]["amber"],
                direction=sl.direction, fmt="{:.0f}%",
                title=f"{name} Service Level, 13 weeks",
            ),
        })

    # ---- headline trend charts ------------------------------------
    headline_charts = []
    for key in ("service_level", "asa", "abandon_rate", "cost_per_contact"):
        k = group["kpis"][key]
        kd = cfg["_kpi_by_key"][key]
        headline_charts.append({
            "label": k["label"],
            "current": k["fmt"].format(k["current"]),
            "rag": k["rag"],
            "chart": line_chart(
                k["series"], group["weeks"], stroke=RAG_STROKE[k["rag"]],
                fill="rgba(14,124,123,0.10)",
                target=k["target"], amber=kd.get("amber"),
                direction=k["direction"],
                fmt=("{:.0f}%" if k["unit"] == "%" else "{:.0f}s" if k["unit"] == "s" else "AED {:.0f}"),
                title=f"Group {k['label']}",
            ),
        })

    watch = narr.watch_items()
    recs = narr.recommendations()

    # ---- JSON summary (machine-readable feed for downstream) --------
    summary = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "period": cfg["review"]["period_label"],
        "group": {
            "service_level": round(group["kpis"]["service_level"]["current"], 2),
            "asa": round(group["kpis"]["asa"]["current"], 1),
            "abandon_rate": round(group["kpis"]["abandon_rate"]["current"], 2),
            "csat": round(group["kpis"]["csat"]["current"], 2),
            "cost_per_contact": round(group["kpis"]["cost_per_contact"]["current"], 2),
            "quarter_contacts": group["quarter_contacts"],
        },
        "unit_scores": {n: u.headline_score for n, u in analysis.units.items()},
        "anomaly_count": len(analysis.anomalies),
        "watch_items": [w["title"] for w in watch],
        "recommendations": [r["title"] for r in recs],
    }

    return {
        "cfg": cfg,
        "review": cfg["review"],
        "generated": dt.datetime.now().strftime("%d %B %Y, %H:%M"),
        "bottom_line": narr.bottom_line(),
        "exec_summary": narr.executive_summary(),
        "what_changed": narr.what_changed(),
        "scorecard": scorecard,
        "headline_charts": headline_charts,
        "bu_blocks": bu_blocks,
        "watch": watch,
        "recs": recs,
        "anomaly_count": len(analysis.anomalies),
        "weeks": analysis.week_labels,
        "kpi_defs": cfg["kpis"],
        "group": group,
        "summary_json": summary,
    }


def _signed(k: dict, delta: float) -> str:
    u = k["unit"]
    if u == "%":
        return f"{delta:+.1f}pt"
    if u == "s":
        return f"{delta:+.0f}s"
    if u == "AED":
        return f"{delta:+.2f}"
    return f"{delta:+.1f}"


def _signed_kpi(r, delta: float) -> str:
    if r.unit == "%":
        return f"{delta:+.1f}pt"
    if r.unit == "s":
        return f"{delta:+.0f}s"
    if r.unit == "AED":
        return f"{delta:+.2f}"
    return f"{delta:+.1f}"


def render_pack_html(ctx: dict | None = None) -> tuple[str, dict]:
    """Render the review pack to an HTML string. Returns (html, ctx).

    Pure: writes nothing to disk. Used by the CLI (`main`) and by the
    Streamlit app so both share one rendering path.
    """
    ctx = ctx or build_context()
    env = Environment(
        loader=FileSystemLoader(str(TPL_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["comma"] = lambda v: f"{v:,}"
    tpl = env.get_template("review_pack.html.j2")
    return tpl.render(**ctx), ctx


def main() -> None:
    html, ctx = render_pack_html()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "service_review_pack.html").write_text(html, encoding="utf-8")
    # index.html so static hosts (e.g. Vercel) serve the pack at "/"
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    (OUT_DIR / "review_summary.json").write_text(
        json.dumps(ctx["summary_json"], indent=2), encoding="utf-8"
    )

    # body-only variant for publishing as a hosted Artifact (no <!doctype>/<html>/<head>/<body>)
    body = html
    for cut in ("<!doctype html>", '<html lang="en">', "<head>",
                '<meta charset="utf-8">', '<meta name="viewport" content="width=device-width, initial-scale=1">',
                "</head>", "<body>", "</body>", "</html>"):
        body = body.replace(cut, "", 1)
    (OUT_DIR / "artifact_body.html").write_text(body.strip() + "\n", encoding="utf-8")

    print(f"wrote {OUT_DIR / 'service_review_pack.html'}  ({len(html):,} bytes)")
    print(f"wrote {OUT_DIR / 'index.html'}")
    print(f"wrote {OUT_DIR / 'review_summary.json'}")
    print(f"wrote {OUT_DIR / 'artifact_body.html'}")
    print(f"  anomalies flagged : {ctx['anomaly_count']}")
    print(f"  watch items       : {len(ctx['watch'])}")
    print(f"  recommendations   : {len(ctx['recs'])}")


if __name__ == "__main__":
    main()
