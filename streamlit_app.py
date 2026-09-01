"""
streamlit_app.py
================
Interactive front end for the Service Review & Insights POC.

It reuses the same engine as the static board pack — `analytics.py` for the
numbers and `narrative.py` for the commentary — and presents them as a
navigable dashboard. The last tab embeds the exact board-pack HTML and lets
you download it.

Run locally:   streamlit run streamlit_app.py
Deploy:        push to GitHub, then share.streamlit.io -> New app -> pick this file
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from analytics import load_config, load_data, ReviewAnalysis   # noqa: E402
from narrative import NarrativeBuilder                          # noqa: E402
import build_review_pack                                        # noqa: E402

DATA_CSV = ROOT / "data" / "weekly_metrics.csv"

RAG_FG = {"green": "#1f7a48", "amber": "#8a5d0d", "red": "#a12f26", "grey": "#6b7280"}
RAG_BG = {"green": "#e6f2ea", "amber": "#f7efdd", "red": "#f7e4e2", "grey": "#eef0f2"}
RAG_LINE = {"green": "#2f8f5b", "amber": "#bd7f16", "red": "#c0392f", "grey": "#8a8f99"}
TREND_GLYPH = {"improving": "▲", "deteriorating": "▼", "stable": "–"}

st.set_page_config(
    page_title="Group Contact Centre — Service Review",
    page_icon="📊",
    layout="wide",
)


# --------------------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def _config():
    return load_config()


@st.cache_data(show_spinner=False)
def _data(_mtime: float) -> pd.DataFrame:
    return load_data()


@st.cache_data(show_spinner=False)
def _pack_html(_mtime: float) -> str:
    html, _ = build_review_pack.render_pack_html()
    return html


def _mtime() -> float:
    return DATA_CSV.stat().st_mtime if DATA_CSV.exists() else 0.0


if not DATA_CSV.exists():
    runpy.run_path(str(ROOT / "src" / "generate_data.py"), run_name="__main__")

cfg = _config()
review = cfg["review"]
df = _data(_mtime())
analysis = ReviewAnalysis(df, cfg)
group = analysis.group_rollup()
narr = NarrativeBuilder(analysis, group)


# ------------------------------------------------------------------------ helpers
def pill(text: str, rag: str) -> str:
    return (
        f"<span style='background:{RAG_BG[rag]};color:{RAG_FG[rag]};"
        f"font-weight:600;font-size:.72rem;padding:2px 9px;border-radius:999px;"
        f"letter-spacing:.03em'>{text}</span>"
    )


def rag_badge(rag: str) -> str:
    return pill(rag.upper(), rag)


def trend_df(series, labels, target=None):
    d = pd.DataFrame({"week": labels, "value": series, "i": range(len(series))})
    if target is not None:
        d["target"] = target
    return d


def line_chart(series, labels, *, rag="grey", target=None, amber=None, y_title=""):
    import altair as alt

    marks = list(series) + [v for v in (target, amber) if v is not None]
    lo, hi = min(marks), max(marks)
    pad = (hi - lo) * 0.15 or (abs(hi) * 0.1 or 1)
    yscale = alt.Scale(domain=[lo - pad, hi + pad], nice=False, zero=False)
    ax = alt.Axis(labelAngle=0, values=[labels[0], labels[len(labels) // 2], labels[-1]])

    d = trend_df(series, labels, target)
    base = alt.Chart(d).encode(x=alt.X("week:N", sort=list(labels), title=None, axis=ax))
    y = alt.Y("value:Q", title=y_title, scale=yscale)

    area = base.mark_area(opacity=0.12, color=RAG_LINE[rag]).encode(y=y)
    line = base.mark_line(strokeWidth=2.4, color=RAG_LINE[rag]).encode(y=y)
    dot = (base.mark_point(size=48, filled=True, color=RAG_LINE[rag])
           .encode(y=y).transform_filter(alt.datum.i == len(series) - 1))
    layers = [area, line, dot]
    if target is not None:
        layers.append(alt.Chart(pd.DataFrame({"y": [target]}))
                      .mark_rule(strokeDash=[4, 3], color="#0e7c7b")
                      .encode(y=alt.Y("y:Q", scale=yscale)))
    if amber is not None:
        layers.append(alt.Chart(pd.DataFrame({"y": [amber]}))
                      .mark_rule(strokeDash=[2, 3], color="#bd7f16", opacity=0.6)
                      .encode(y=alt.Y("y:Q", scale=yscale)))
    return alt.layer(*layers).properties(height=210).configure_view(strokeOpacity=0)


# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Service Review & Insights")
    st.caption("Proof of concept · synthetic data")
    st.markdown(
        f"**Period**  \n{review['period_label']}  \n\n"
        f"**Prepared for**  \n{review['prepared_for']}  \n\n"
        f"**Prepared by**  \n{review['prepared_by']}"
    )
    st.divider()
    if st.button("↻ Regenerate synthetic data", use_container_width=True):
        runpy.run_path(str(ROOT / "src" / "generate_data.py"), run_name="__main__")
        st.cache_data.clear()
        st.rerun()
    st.caption(
        "The generator seeds five deliberate stories (a Technical Support SL "
        "collapse, a Collections AHT drift, a Retention recovery, a Consumer Care "
        "telephony incident, a strong SME Desk). Every view below is derived, not "
        "hand-written."
    )


# --------------------------------------------------------------------------- header
st.title(review["title"])
st.markdown(
    f"<div style='color:#59616f;margin-top:-8px'>{narr.bottom_line()}</div>",
    unsafe_allow_html=True,
)
st.write("")

g = group["kpis"]
cols = st.columns(4)
_headline = [
    ("Service Level", g["service_level"], "normal"),
    ("Abandonment", g["abandon_rate"], "inverse"),
    ("CSAT", g["csat"], "normal"),
    ("Cost / Contact", g["cost_per_contact"], "inverse"),
]
for col, (name, k, dcolor) in zip(cols, _headline):
    col.metric(
        name,
        k["fmt"].format(k["current"]),
        f"{k['q_delta']:+.2f} vs qtr start" if k["unit"] == "AED"
        else f"{k['q_delta']:+.1f} {'pt' if k['unit'] == '%' else k['unit']} vs qtr start",
        delta_color=dcolor,
    )

st.write("")

tabs = st.tabs([
    "Executive summary", "Group scorecard", "Business units",
    "Watch items", "Actions", "KPI definitions", "Board pack (print view)",
])

# ------------------------------------------------------------- 1 · executive summary
with tabs[0]:
    st.subheader("Bottom line")
    st.markdown(
        f"<div style='border-left:3px solid #0e7c7b;padding:4px 0 4px 16px;"
        f"font-size:1.05rem'>{narr.bottom_line()}</div>",
        unsafe_allow_html=True,
    )
    st.subheader("Executive summary")
    for para in narr.executive_summary():
        st.markdown(para, unsafe_allow_html=True)

    st.subheader("What moved this quarter")
    wc = narr.what_changed()
    wc_df = pd.DataFrame({
        "": [TREND_GLYPH["improving"] if r["favourable"]
             else TREND_GLYPH["deteriorating"] if r["favourable"] is False
             else TREND_GLYPH["stable"] for r in wc],
        "Movement": [r["text"] for r in wc],
    })
    st.dataframe(wc_df, hide_index=True, use_container_width=True)

# ----------------------------------------------------------------- 2 · group scorecard
with tabs[1]:
    st.subheader("Group scorecard")
    st.caption("Volume-weighted across all units · RAG against the standardised target")

    rows = []
    for kpi in cfg["kpis"]:
        k = g[kpi["key"]]
        rows.append({
            "KPI": k["label"],
            "Category": k["category"],
            "Latest": k["fmt"].format(k["current"]),
            "Target": k["fmt"].format(k["target"]),
            "WoW": f"{k['wow_delta']:+.2f}" if k["unit"] == "AED" else f"{k['wow_delta']:+.1f}",
            "Qtr Δ": f"{k['q_delta']:+.2f}" if k["unit"] == "AED" else f"{k['q_delta']:+.1f}",
            "Trend": TREND_GLYPH.get(k["trend"], "–"),
            "RAG": k["rag"].upper(),
            "_rag": k["rag"],
        })
    sc = pd.DataFrame(rows)

    def _style_rag(col):
        return [
            f"background-color:{RAG_BG[r]};color:{RAG_FG[r]};font-weight:600"
            for r in sc["_rag"]
        ]

    styled = (
        sc.drop(columns=["_rag"])
        .style.apply(_style_rag, subset=["RAG"])
    )
    st.dataframe(styled, hide_index=True, use_container_width=True)

    st.subheader("Headline trends · 13 weeks")
    grid = st.columns(2)
    for i, key in enumerate(["service_level", "asa", "abandon_rate", "cost_per_contact"]):
        k = g[key]
        kd = cfg["_kpi_by_key"][key]
        with grid[i % 2]:
            st.markdown(f"**{k['label']}** — {k['fmt'].format(k['current'])} {rag_badge(k['rag'])}",
                        unsafe_allow_html=True)
            st.altair_chart(
                line_chart(k["series"], group["weeks"], rag=k["rag"],
                           target=k["target"], amber=kd.get("amber")),
                use_container_width=True,
            )

# --------------------------------------------------------------- 3 · business units
with tabs[2]:
    st.subheader("Business-unit review")
    st.caption("Ordered by headline-KPI score, weakest last")
    readouts = narr.bu_readouts()
    unit_tabs = st.tabs(list(analysis.units.keys()))
    for utab, (name, bu) in zip(unit_tabs, analysis.units.items()):
        with utab:
            ro = readouts[name]
            top = st.columns([2, 1])
            with top[0]:
                st.markdown(f"### {name}")
                verdict_rag = ("red" if "Escalate" in ro["verdict"]
                               else "amber" if "Watch" in ro["verdict"] else "green")
                st.markdown(pill(ro["verdict"], verdict_rag), unsafe_allow_html=True)
                st.write("")
                st.write(ro["text"])
            with top[1]:
                st.metric("Headline score", f"{bu.headline_score:.0f}/100")
                rc = bu.rag_counts
                st.caption(f"🟢 {rc.get('green',0)}   🟡 {rc.get('amber',0)}   🔴 {rc.get('red',0)}")

            st.divider()
            mcols = st.columns(4)
            keys = ["service_level", "asa", "abandon_rate", "aht",
                    "fcr", "csat", "cost_per_contact", "adherence"]
            for j, key in enumerate(keys):
                r = bu.kpis[key]
                inv = r.direction == "lower_better"
                mcols[j % 4].metric(
                    f"{cfg['_kpi_by_key'][key]['short']} {TREND_GLYPH.get(r.trend,'')}",
                    r.f(r.current),
                    f"{r.wow_delta:+.2f}" if r.unit == "AED" else f"{r.wow_delta:+.1f}{'' if r.unit=='%' else r.unit}",
                    delta_color="inverse" if inv else "normal",
                )

            sl = bu.kpis["service_level"]
            st.altair_chart(
                line_chart(sl.series, analysis.week_labels, rag=sl.rag,
                           target=sl.target,
                           amber=cfg["_kpi_by_key"]["service_level"]["amber"],
                           y_title="Service Level %"),
                use_container_width=True,
            )

# ------------------------------------------------------------------ 4 · watch items
with tabs[3]:
    st.subheader("Watch items & anomalies")
    st.caption(
        f"{len(analysis.anomalies)} statistical anomalies flagged · "
        f"z > {review['anomaly_z_threshold']} vs trailing "
        f"{review['anomaly_baseline_weeks']}-week mean. Only material, adverse "
        f"signals are promoted below."
    )
    watch = narr.watch_items()
    if not watch:
        st.success("No metric breached the anomaly or step-change thresholds this cycle.")
    for w in watch:
        box = st.error if w["severity"] == "high" else st.warning
        box(f"**{w['title']}**  \n{w['detail']}")

    with st.expander(f"All {len(analysis.anomalies)} flagged anomalies"):
        an_df = pd.DataFrame([{
            "Unit": a.business_unit,
            "KPI": a.kpi_label,
            "Week": a.week,
            "Value": a.f(a.value),
            "8-wk mean": a.f(a.baseline_mean),
            "z": round(a.z, 1),
            "Direction": a.direction,
            "Favourable": a.favourable,
        } for a in analysis.anomalies])
        st.dataframe(an_df, hide_index=True, use_container_width=True)

# --------------------------------------------------------------------- 5 · actions
with tabs[4]:
    st.subheader("Recommended actions")
    st.caption("Owner and horizon assigned · tracked to next review")
    for i, r in enumerate(narr.recommendations(), 1):
        with st.container(border=True):
            st.markdown(f"**R{i} · {r['title']}**")
            st.write(r["rationale"])
            st.caption(f"Owner: **{r['owner']}**  ·  Horizon: **{r['horizon']}**")

# ------------------------------------------------------------- 6 · KPI definitions
with tabs[5]:
    st.subheader("Standardised KPI definitions")
    st.caption("Single source of truth (`config/kpi_definitions.yaml`) · applied identically to every unit")
    defs = []
    for k in cfg["kpis"]:
        if k["direction"] == "higher_better":
            rule = f"green ≥ {k['fmt'].format(k['target'])} · red < {k['fmt'].format(k['amber'])}"
            tgt = k["fmt"].format(k["target"])
        elif k["direction"] == "lower_better":
            rule = f"green ≤ {k['fmt'].format(k['target'])} · red > {k['fmt'].format(k['amber'])}"
            tgt = k["fmt"].format(k["target"])
        else:
            rule = "green inside band"
            tgt = f"{k['band_low']}–{k['band_high']}{k['unit']}"
        defs.append({
            "KPI": k["label"], "Definition": " ".join(k["definition"].split()),
            "Target": tgt, "RAG rule": rule,
        })
    st.dataframe(pd.DataFrame(defs), hide_index=True, use_container_width=True)

# ------------------------------------------------------ 7 · board pack (print view)
with tabs[6]:
    st.subheader("Board pack — print view")
    st.caption(
        "The exact HTML pack the pipeline produces (`python build.py`). "
        "Download it and print to PDF for distribution."
    )
    html = _pack_html(_mtime())
    st.download_button(
        "⬇ Download board pack (HTML)", html,
        file_name="service_review_pack.html", mime="text/html",
    )
    components.html(html, height=1500, scrolling=True)
