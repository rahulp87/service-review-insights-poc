"""
narrative.py
------------
The "data storytelling" layer. Given the computed analysis it writes the
plain-English commentary an executive reader expects: a bottom line, an
executive summary, per-unit readouts, watch items and recommended
actions. Rules-based and deterministic — no model calls — so the same
numbers always produce the same narrative.
"""

from __future__ import annotations

from analytics import ReviewAnalysis, KpiResult


# ---------------------------------------------------------------- phrasing
def _dir_word(delta: float, kpi: KpiResult, up="rose", down="fell") -> str:
    return up if delta > 0 else down


def _fmt_delta(kpi: KpiResult, delta: float) -> str:
    unit = "" if kpi.unit in ("%", "s", "AED") else ""
    if kpi.unit == "%":
        return f"{abs(delta):.1f} pts"
    if kpi.unit == "s":
        return f"{abs(delta):.0f}s"
    if kpi.unit == "AED":
        return f"AED {abs(delta):.2f}"
    return f"{abs(delta):.1f}{unit}"


def _good_bad(favourable: bool | None) -> str:
    return "favourable" if favourable else "adverse" if favourable is False else "mixed"


# ------------------------------------------------------------------- engine
class NarrativeBuilder:
    def __init__(self, analysis: ReviewAnalysis, group: dict):
        self.a = analysis
        self.g = group
        self.cfg = analysis.cfg

    # -- bottom line --------------------------------------------------
    def bottom_line(self) -> str:
        reds = [u for u in self.a.units.values() if u.rag_counts.get("red", 0) >= 2]
        sl = self.g["kpis"]["service_level"]
        csat = self.g["kpis"]["csat"]
        cpc = self.g["kpis"]["cost_per_contact"]

        if reds:
            worst = min(self.a.units.values(), key=lambda u: u.headline_score)
            return (
                f"Group service held broadly stable this quarter, but "
                f"<strong>{worst.name}</strong> has moved outside tolerance on "
                f"{worst.rag_counts.get('red', 0)} of its headline KPIs and is dragging "
                f"the group Service Level to {sl['fmt'].format(sl['current'])}. "
                f"It needs a recovery plan before the next Board cycle."
            )
        return (
            f"Group Service Level closed the quarter at {sl['fmt'].format(sl['current'])} "
            f"with CSAT at {csat['fmt'].format(csat['current'])} and cost per contact at "
            f"{cpc['fmt'].format(cpc['current'])} — no unit requires escalation this cycle."
        )

    # -- executive summary -----------------------------------------
    def executive_summary(self) -> list[str]:
        g = self.g
        paras: list[str] = []

        sl = g["kpis"]["service_level"]
        asa = g["kpis"]["asa"]
        ab = g["kpis"]["abandon_rate"]
        move = _dir_word(sl["q_delta"], None)
        paras.append(
            f"Across {g['quarter_contacts']:,} handled voice contacts, group Service Level "
            f"{'improved' if sl['favourable_q'] else 'weakened'} from "
            f"{sl['fmt'].format(sl['q_start'])} to {sl['fmt'].format(sl['current'])} over the "
            f"13 weeks, with ASA at {asa['fmt'].format(asa['current'])} and abandonment at "
            f"{ab['fmt'].format(ab['current'])}. The quarter-end position is "
            f"{'inside' if sl['rag'] == 'green' else 'outside'} the {sl['fmt'].format(sl['target'])} "
            f"access commitment."
        )

        # spread across units
        best = max(self.a.units.values(), key=lambda u: u.headline_score)
        worst = min(self.a.units.values(), key=lambda u: u.headline_score)
        paras.append(
            f"Performance is uneven by unit. <strong>{best.name}</strong> is the strongest "
            f"({best.headline_score:.0f}/100 on headline KPIs), while "
            f"<strong>{worst.name}</strong> is the weakest ({worst.headline_score:.0f}/100). "
            f"The gap between them widened during the quarter and is now the single biggest "
            f"driver of group-level variance."
        )

        # cost & efficiency
        cpc = g["kpis"]["cost_per_contact"]
        aht = g["kpis"]["aht"]
        fcr = g["kpis"]["fcr"]
        paras.append(
            f"On efficiency, AHT {_dir_word(aht['q_delta'], None)} "
            f"{_fmt_delta_group(aht)} and cost per contact is "
            f"{cpc['fmt'].format(cpc['current'])} ({_signed_group(cpc, cpc['q_delta'])} vs "
            f"quarter start). FCR at {fcr['fmt'].format(fcr['current'])} means roughly "
            f"{100 - fcr['current']:.0f}% of contacts still generate a repeat — the largest "
            f"single avoidable-volume opportunity."
        )
        return paras

    # -- what changed this quarter --------------------------------
    def what_changed(self) -> list[dict]:
        rows = []
        for key, k in self.g["kpis"].items():
            if abs(k["q_pct"]) < 3 and k["unit"] != "%":
                continue
            if k["unit"] == "%" and abs(k["q_delta"]) < 1.0:
                continue
            rows.append({
                "label": k["label"],
                "text": (
                    f"{k['label']} moved from {k['fmt'].format(k['q_start'])} to "
                    f"{k['fmt'].format(k['current'])} "
                    f"({_signed_group(k, k['q_delta'])})"
                ),
                "favourable": k["favourable_q"],
                "magnitude": abs(k["q_pct"]),
            })
        rows.sort(key=lambda r: r["magnitude"], reverse=True)
        return rows[:6]

    # -- per business unit readouts ------------------------------
    def bu_readouts(self) -> dict[str, dict]:
        out = {}
        for name, bu in self.a.units.items():
            reds = [k for k in bu.kpis.values() if k.rag == "red"]
            ambers = [k for k in bu.kpis.values() if k.rag == "amber"]
            worsening = [k for k in bu.kpis.values() if k.trend == "deteriorating"]
            improving = [k for k in bu.kpis.values() if k.trend == "improving"]

            sl = bu.kpis["service_level"]
            csat = bu.kpis["csat"]
            bits = [
                f"SL {sl.f(sl.current)} ({_signed(sl, sl.wow_delta)} WoW), "
                f"CSAT {csat.f(csat.current)}."
            ]
            if reds:
                bits.append(
                    "Outside tolerance on " + _join([k.label for k in reds]) + "."
                )
            if worsening:
                bits.append(
                    "Deteriorating trend on " + _join([k.label for k in worsening]) + "."
                )
            if improving and not reds:
                bits.append(
                    "Improving trend on " + _join([k.label for k in improving]) + "."
                )
            if not reds and not ambers:
                bits.append("All KPIs green — hold as the reference model for the group.")

            if reds:
                verdict = "Escalate"
            elif worsening:
                verdict = "Watch"
            elif improving:
                verdict = "On track — improving"
            else:
                verdict = "On track"

            out[name] = {
                "verdict": verdict,
                "text": " ".join(bits),
                "score": bu.headline_score,
                "rag_counts": bu.rag_counts,
            }
        return out

    # -- watch items -------------------------------------------------
    def watch_items(self, limit: int = 6) -> list[dict]:
        """Executive watch list: only *adverse*, *material* signals.

        The anomaly scanner casts a wide net (see `anomaly_count`); this
        method promotes to the Board only the moves that are both bad news
        and large enough to act on, plus any sustained adverse trend.
        """
        items: list[dict] = []
        covered: set[tuple[str, str]] = set()

        # current RAG lookup so we can drop "still-green" wobbles
        rag_of = {
            (n, k.key): k.rag
            for n, bu in self.a.units.items() for k in bu.kpis.values()
        }

        for an in self.a.anomalies:
            if an.favourable:
                continue
            step_pct = 100 * (an.value - an.baseline_mean) / an.baseline_mean if an.baseline_mean else 0
            cur_rag = rag_of.get((an.business_unit, an.kpi_key), "grey")
            material = abs(an.z) >= 3.5 or (abs(step_pct) >= 8.0 and cur_rag != "green")
            if not material:
                continue
            verb = "jumped to" if an.direction == "spike" else "fell to"
            items.append({
                "severity": "high" if abs(an.z) >= 3.5 else "medium",
                "unit": an.business_unit,
                "sort": abs(an.z),
                "title": f"{an.business_unit} — {an.kpi_label} {verb} {an.f(an.value)} (w/e {an.week})",
                "detail": (
                    f"{abs(an.z):.1f}σ below" if an.direction == "drop" and an.z < 0
                    else f"{abs(an.z):.1f}σ from"
                ) + f" the trailing {self.a.baseline_weeks}-week mean of {an.f(an.baseline_mean)}"
                   + f", {step_pct:+.0f}% week-on-week.",
            })
            covered.add((an.business_unit, an.kpi_key))

        for name, bu in self.a.units.items():
            for k in bu.kpis.values():
                if k.trend != "deteriorating" or k.rag not in ("amber", "red"):
                    continue
                if (name, k.key) in covered:
                    continue
                items.append({
                    "severity": "high" if k.rag == "red" else "medium",
                    "unit": name,
                    "sort": 2.0 + (1.0 if k.rag == "red" else 0.0),
                    "title": f"{name} — {k.label} on a sustained adverse trend ({k.f(k.q_start)} → {k.f(k.current)})",
                    "detail": (
                        f"Slope {k.slope_per_wk:+.2f}{k.unit}/week across the quarter "
                        f"(R²={k.slope_r2:.2f}); now rated {k.rag.upper()} against a "
                        f"{k.f(k.target)} target."
                    ),
                })
                covered.add((name, k.key))

        order = {"high": 0, "medium": 1, "low": 2}
        items.sort(key=lambda i: (order.get(i["severity"], 3), -i["sort"]))

        # cap at 3 lines per unit so one unit can't crowd out the list
        per_unit: dict[str, int] = {}
        capped: list[dict] = []
        for it in items:
            n = per_unit.get(it["unit"], 0)
            if n >= 3:
                continue
            per_unit[it["unit"]] = n + 1
            capped.append(it)
        return capped[:limit]

    # -- recommendations -----------------------------------------
    def recommendations(self) -> list[dict]:
        recs: list[dict] = []
        units = self.a.units

        ts = units.get("Technical Support")
        if ts and ts.rag_counts.get("red", 0) >= 1:
            recs.append({
                "title": "Stand up a Technical Support service-recovery cell",
                "rationale": (
                    f"SL has fallen to {ts.kpis['service_level'].f(ts.kpis['service_level'].current)} "
                    f"and abandonment to {ts.kpis['abandon_rate'].f(ts.kpis['abandon_rate'].current)} "
                    "in the last three weeks. Root-cause the split between attrition and the "
                    "platform incident, add interim licensed overflow, and report daily until SL "
                    "is back above target for five consecutive days."
                ),
                "owner": "Head of Technical Support / WFM",
                "horizon": "This week",
            })

        col = units.get("Collections")
        if col and col.kpis["aht"].trend == "deteriorating":
            k = col.kpis["aht"]
            recs.append({
                "title": "Break the Collections AHT drift",
                "rationale": (
                    f"AHT has risen {k.f(k.q_delta)} across the quarter "
                    f"({k.slope_per_wk:+.1f}s/week) with no matching FCR gain — a coaching or "
                    "process signal, not demand. Call-listen the longest 10% of contacts, refresh "
                    "the disclosure script, and set a weekly AHT ceiling per team."
                ),
                "owner": "Collections Ops Manager / QA",
                "horizon": "2–4 weeks",
            })

        sme = units.get("SME Desk")
        if sme and sme.rag_counts.get("red", 0) == 0 and sme.rag_counts.get("amber", 0) <= 1:
            recs.append({
                "title": "Codify the SME Desk operating model as the group standard",
                "rationale": (
                    f"SME Desk is green on {sme.rag_counts.get('green', 0)} KPIs with the highest "
                    "headline score. Document its staffing ratios, coaching cadence and QA rubric "
                    "and pilot them in the weakest unit next quarter."
                ),
                "owner": "Service Review & Insights",
                "horizon": "Next quarter",
            })

        fcr = self.g["kpis"]["fcr"]
        if fcr["current"] < fcr["target"]:
            recs.append({
                "title": "Target the repeat-contact tail to release capacity",
                "rationale": (
                    f"Group FCR is {fcr['fmt'].format(fcr['current'])} against a "
                    f"{fcr['fmt'].format(fcr['target'])} target. Closing half the gap removes "
                    "an estimated 3–5% of offered volume — enough to fund the Technical Support "
                    "overflow above without new headcount. Start with the top 5 repeat drivers by "
                    "contact reason."
                ),
                "owner": "Insights + Journey owners",
                "horizon": "This quarter",
            })

        recs.append({
            "title": "Move all units onto the standardised review template",
            "rationale": (
                "This pack is generated from one KPI definition file and one layout. Retiring the "
                "five bespoke unit decks removes ~2 analyst-days per week and makes cross-unit "
                "comparison automatic."
            ),
            "owner": "Service Review & Insights",
            "horizon": "30 days",
        })
        return recs


# ------------------------------------------------------------- small utils
def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _signed(kpi: KpiResult, delta: float) -> str:
    if kpi.unit == "%":
        return f"{delta:+.1f} pts"
    if kpi.unit == "s":
        return f"{delta:+.0f}s"
    if kpi.unit == "AED":
        return f"{delta:+.2f} AED"
    return f"{delta:+.1f}"


def _signed_group(k: dict, delta: float) -> str:
    if k["unit"] == "%":
        return f"{delta:+.1f} pts"
    if k["unit"] == "s":
        return f"{delta:+.0f}s"
    if k["unit"] == "AED":
        return f"{delta:+.2f} AED"
    return f"{delta:+.1f}"


def _fmt_delta_group(k: dict) -> str:
    d = k["q_delta"]
    if k["unit"] == "%":
        return f"{abs(d):.1f} pts"
    if k["unit"] == "s":
        return f"{abs(d):.0f}s"
    if k["unit"] == "AED":
        return f"AED {abs(d):.2f}"
    return f"{abs(d):.1f}"
