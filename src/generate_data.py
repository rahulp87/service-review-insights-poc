"""
generate_data.py
----------------
Builds a realistic *synthetic* weekly voice-operations dataset for the POC.

There is no live feed here, so the data is fabricated — but it is fabricated
with intent. Each business unit carries a deliberate "story" the pipeline is
meant to surface on its own:

    Consumer Care     - stable, healthy; one abandonment spike (system incident)
    SME Desk          - quietly the strongest performer all quarter
    Technical Support - sharp Service Level / ASA collapse in the last 3 weeks
                        (attrition + an unplanned outage)
    Collections       - AHT drifting up week after week (coaching / process gap)
    Retention         - CSAT and FCR improving steadily off a low base

Output: data/weekly_metrics.csv  (one row per business unit per ISO week)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(20260927)
WEEKS = 17                       # 4 weeks of run-in history + 13-week quarter
QUARTER_START_IDX = 4
END_DATE = pd.Timestamp("2026-09-27")
WEEK_ENDS = [END_DATE - pd.Timedelta(weeks=(WEEKS - 1 - i)) for i in range(WEEKS)]

OUT = Path(__file__).resolve().parents[1] / "data" / "weekly_metrics.csv"


def _noise(scale, size=WEEKS):
    return RNG.normal(0, scale, size)


def _clip(a, lo, hi):
    return np.clip(a, lo, hi)


def build_unit(name: str) -> pd.DataFrame:
    t = np.arange(WEEKS)

    # ---- baseline volume (offered contacts / week) ----------------------
    base_vol = {
        "Consumer Care": 20800, "SME Desk": 6100, "Technical Support": 11200,
        "Collections": 8700, "Retention": 4300,
    }[name]
    seasonal = 1 + 0.05 * np.sin(t / 2.3)
    offered = base_vol * seasonal * (1 + _noise(0.03))

    # ---- start every unit from a sensible profile ----------------------
    service_level = 82 + _noise(2.0)
    asa = 26 + _noise(4.0)
    abandon = 4.6 + _noise(0.6)
    aht = 355 + _noise(12)
    fcr = 79 + _noise(1.5)
    csat = 86 + _noise(1.4)
    occupancy = 85 + _noise(2.5)
    adherence = 91 + _noise(1.8)
    forecast_acc = 92.5 + _noise(1.6)

    # ================= per-unit deliberate stories =====================
    if name == "SME Desk":
        service_level += 4.5
        asa -= 6
        abandon -= 1.6
        fcr += 3.0
        csat += 3.2
        aht -= 15

    if name == "Technical Support":
        # gentle erosion all quarter, then a 3-week cliff (attrition + outage)
        drift = -0.35 * np.maximum(t - QUARTER_START_IDX, 0)
        service_level += drift
        asa += -0.9 * drift
        cliff = np.where(t >= WEEKS - 3, np.linspace(0, 1, WEEKS), 0.0)
        service_level -= 22 * np.where(t >= WEEKS - 3, (t - (WEEKS - 4)) / 3.0, 0)
        asa += 55 * np.where(t >= WEEKS - 3, (t - (WEEKS - 4)) / 3.0, 0)
        abandon += 6.5 * np.where(t >= WEEKS - 3, (t - (WEEKS - 4)) / 3.0, 0)
        adherence -= 7 * np.where(t >= WEEKS - 3, (t - (WEEKS - 4)) / 3.0, 0)
        csat -= 5 * np.where(t >= WEEKS - 3, (t - (WEEKS - 4)) / 3.0, 0)

    if name == "Collections":
        # AHT creeps ~3s/week from the start of the quarter
        aht += 3.1 * np.maximum(t - QUARTER_START_IDX, 0)
        occupancy += 0.25 * np.maximum(t - QUARTER_START_IDX, 0)

    if name == "Retention":
        # improving off a weak base
        ramp = np.maximum(t - QUARTER_START_IDX, 0)
        csat += 0.55 * ramp - 4
        fcr += 0.5 * ramp - 5
        service_level += 0.3 * ramp - 3

    if name == "Consumer Care":
        # single-week abandonment spike (telephony incident) in week -6
        spike_wk = WEEKS - 6
        abandon[spike_wk] += 9.0
        asa[spike_wk] += 40
        service_level[spike_wk] -= 15

    # ---- derived / bounded -------------------------------------------
    service_level = _clip(service_level, 35, 99)
    asa = _clip(asa, 5, 240)
    abandon = _clip(abandon, 0.5, 40)
    aht = _clip(aht, 240, 620)
    fcr = _clip(fcr, 55, 95)
    csat = _clip(csat, 55, 99)
    repeat_rate = _clip(100 - fcr + _noise(1.2), 3, 45)
    occupancy = _clip(occupancy, 68, 96)
    adherence = _clip(adherence, 70, 99)
    forecast_acc = _clip(forecast_acc, 78, 99)

    handled = offered * (1 - abandon / 100.0)
    # fully-loaded cost per contact: labour driven by AHT + occupancy, plus overhead
    cost_per_contact = (
        (aht / 60.0) * 1.95 / (occupancy / 100.0)          # variable labour
        + 6.2                                              # tech + overhead / contact
        + _noise(0.4)
    )
    cost_per_contact = _clip(cost_per_contact, 9, 40)

    df = pd.DataFrame({
        "week_ending": [d.date().isoformat() for d in WEEK_ENDS],
        "iso_week": [d.isocalendar().week for d in WEEK_ENDS],
        "business_unit": name,
        "contacts_offered": offered.round(0).astype(int),
        "contacts_handled": handled.round(0).astype(int),
        "service_level": service_level.round(2),
        "asa": asa.round(1),
        "abandon_rate": abandon.round(2),
        "aht": aht.round(1),
        "fcr": fcr.round(2),
        "csat": csat.round(2),
        "repeat_rate": repeat_rate.round(2),
        "occupancy": occupancy.round(2),
        "adherence": adherence.round(2),
        "forecast_accuracy": forecast_acc.round(2),
        "cost_per_contact": cost_per_contact.round(3),
    })
    return df


def main() -> None:
    units = ["Consumer Care", "SME Desk", "Technical Support", "Collections", "Retention"]
    out = pd.concat([build_unit(u) for u in units], ignore_index=True)
    out = out.sort_values(["business_unit", "week_ending"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"wrote {len(out):,} rows -> {OUT}")
    print(out.groupby("business_unit").tail(1).to_string(index=False))


if __name__ == "__main__":
    main()
