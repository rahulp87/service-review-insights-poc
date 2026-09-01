"""
analytics.py
------------
Turns the weekly metrics table into everything the review pack needs:
RAG status, week-on-week and quarter movement, trend slopes, anomaly
flags and group roll-ups. No presentation logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------- config
def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config" / "kpi_definitions.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["_kpi_by_key"] = {k["key"]: k for k in cfg["kpis"]}
    return cfg


def load_data(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path) if path else ROOT / "data" / "weekly_metrics.csv"
    df = pd.read_csv(path)
    df["week_ending"] = pd.to_datetime(df["week_ending"])
    return df.sort_values(["business_unit", "week_ending"]).reset_index(drop=True)


# ------------------------------------------------------------------ RAG logic
def rag_status(value: float, kpi: dict) -> str:
    """green / amber / red against the standardised target for this KPI."""
    if value is None or np.isnan(value):
        return "grey"
    direction = kpi["direction"]
    if direction == "higher_better":
        if value >= kpi["target"]:
            return "green"
        if value >= kpi["amber"]:
            return "amber"
        return "red"
    if direction == "lower_better":
        if value <= kpi["target"]:
            return "green"
        if value <= kpi["amber"]:
            return "amber"
        return "red"
    if direction == "band":
        if kpi["band_low"] <= value <= kpi["band_high"]:
            return "green"
        near = 0.05 * (kpi["band_high"] - kpi["band_low"])
        if kpi["band_low"] - near <= value <= kpi["band_high"] + near:
            return "amber"
        return "red"
    return "grey"


def is_favourable(delta: float, kpi: dict) -> bool | None:
    """Is a movement of `delta` good news for this KPI?"""
    if abs(delta) < 1e-9:
        return None
    if kpi["direction"] == "higher_better":
        return delta > 0
    if kpi["direction"] == "lower_better":
        return delta < 0
    return None  # band: direction depends on where you sit


def linreg(y: np.ndarray) -> tuple[float, float]:
    """Return (slope per step, r-squared) for y against 0..n-1."""
    y = np.asarray(y, dtype=float)
    x = np.arange(len(y))
    if len(y) < 3 or np.allclose(y, y[0]):
        return 0.0, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(r2)


# ------------------------------------------------------------- data classes
@dataclass
class KpiResult:
    key: str
    label: str
    unit: str
    fmt: str
    category: str
    headline: bool
    current: float
    prior: float
    q_start: float
    wow_delta: float
    wow_pct: float
    q_delta: float
    q_pct: float
    slope_per_wk: float
    slope_r2: float
    trend: str            # improving | deteriorating | stable
    rag: str
    series: list[float]
    target: float
    direction: str

    def f(self, v: float) -> str:
        try:
            return self.fmt.format(v)
        except Exception:
            return f"{v:.1f}"


@dataclass
class BusinessUnitResult:
    name: str
    latest_week: str
    volume_offered: int
    volume_handled: int
    kpis: dict[str, KpiResult] = field(default_factory=dict)
    rag_counts: dict[str, int] = field(default_factory=dict)
    headline_score: float = 0.0


@dataclass
class Anomaly:
    business_unit: str
    kpi_key: str
    kpi_label: str
    week: str
    value: float
    baseline_mean: float
    baseline_std: float
    z: float
    direction: str        # "spike" | "drop"
    favourable: bool
    fmt: str

    def f(self, v: float) -> str:
        try:
            return self.fmt.format(v)
        except Exception:
            return f"{v:.1f}"


# ----------------------------------------------------------------- analysis
class ReviewAnalysis:
    def __init__(self, df: pd.DataFrame, cfg: dict):
        self.cfg = cfg
        rc = cfg["review"]
        self.quarter_weeks = int(rc["quarter_weeks"])
        self.baseline_weeks = int(rc["anomaly_baseline_weeks"])
        self.z_threshold = float(rc["anomaly_z_threshold"])
        self.step_pct = float(rc["step_change_pct"])

        all_weeks = sorted(df["week_ending"].unique())
        self.q_weeks = all_weeks[-self.quarter_weeks:]
        self.df = df[df["week_ending"].isin(self.q_weeks)].copy()
        self.full_df = df.copy()
        self.week_labels = [pd.Timestamp(w).strftime("%d %b") for w in self.q_weeks]
        self.latest_week = pd.Timestamp(self.q_weeks[-1]).strftime("%d %b %Y")

        self.units: dict[str, BusinessUnitResult] = {}
        self.anomalies: list[Anomaly] = []
        self._run()

    # -- per business unit ------------------------------------------------
    def _unit_kpi(self, g: pd.DataFrame, kpi: dict) -> KpiResult:
        key = kpi["key"]
        series = g[key].to_numpy(dtype=float)
        current, prior, q_start = series[-1], series[-2], series[0]
        wow_delta = current - prior
        wow_pct = 100 * wow_delta / prior if prior else 0.0
        q_delta = current - q_start
        q_pct = 100 * q_delta / q_start if q_start else 0.0
        slope, r2 = linreg(series)

        # trend: needs both a real slope and a reasonable fit
        span = slope * (len(series) - 1)
        rel = abs(span) / (abs(np.mean(series)) + 1e-9)
        if r2 >= 0.35 and rel >= 0.05:
            improving = is_favourable(span, kpi)
            trend = "improving" if improving else "deteriorating" if improving is False else "stable"
        else:
            trend = "stable"

        return KpiResult(
            key=key, label=kpi["label"], unit=kpi["unit"], fmt=kpi["fmt"],
            category=kpi["category"], headline=bool(kpi.get("headline")),
            current=current, prior=prior, q_start=q_start,
            wow_delta=wow_delta, wow_pct=wow_pct, q_delta=q_delta, q_pct=q_pct,
            slope_per_wk=slope, slope_r2=r2, trend=trend,
            rag=rag_status(current, kpi), series=[round(float(v), 3) for v in series],
            target=kpi["target"], direction=kpi["direction"],
        )

    def _detect_anomalies(self, g: pd.DataFrame, kpi: dict) -> None:
        key = kpi["key"]
        s = g[key].to_numpy(dtype=float)
        if len(s) < self.baseline_weeks + 1:
            return
        latest = s[-1]
        baseline = s[-(self.baseline_weeks + 1):-1]
        mu, sd = float(np.mean(baseline)), float(np.std(baseline, ddof=1))
        if sd < 1e-6:
            return
        z = (latest - mu) / sd
        prior = s[-2]
        step_pct = 100 * (latest - prior) / prior if prior else 0.0
        if abs(z) < self.z_threshold and abs(step_pct) < self.step_pct:
            return
        direction = "spike" if latest > mu else "drop"
        fav = is_favourable(latest - mu, kpi)
        self.anomalies.append(Anomaly(
            business_unit=g["business_unit"].iloc[0], kpi_key=key,
            kpi_label=kpi["label"], week=pd.Timestamp(g["week_ending"].iloc[-1]).strftime("%d %b"),
            value=latest, baseline_mean=mu, baseline_std=sd, z=z,
            direction=direction, favourable=bool(fav) if fav is not None else False,
            fmt=kpi["fmt"],
        ))

    def _run(self) -> None:
        for name in self.cfg["business_units"]:
            g_full = self.full_df[self.full_df["business_unit"] == name]
            g = self.df[self.df["business_unit"] == name].sort_values("week_ending")
            if g.empty:
                continue
            bu = BusinessUnitResult(
                name=name,
                latest_week=self.latest_week,
                volume_offered=int(g["contacts_offered"].iloc[-1]),
                volume_handled=int(g["contacts_handled"].iloc[-1]),
            )
            for kpi in self.cfg["kpis"]:
                bu.kpis[kpi["key"]] = self._unit_kpi(g, kpi)
                self._detect_anomalies(
                    g_full[g_full["week_ending"].isin(self.q_weeks)].sort_values("week_ending"),
                    kpi,
                )
            counts = {"green": 0, "amber": 0, "red": 0, "grey": 0}
            for r in bu.kpis.values():
                counts[r.rag] = counts.get(r.rag, 0) + 1
            bu.rag_counts = counts
            hl = [r for r in bu.kpis.values() if r.headline]
            score = np.mean([
                1.0 if r.rag == "green" else 0.5 if r.rag == "amber" else 0.0
                for r in hl
            ]) if hl else 0.0
            bu.headline_score = round(float(score) * 100, 1)
            self.units[name] = bu

        self.anomalies.sort(key=lambda a: abs(a.z), reverse=True)

    # -- group roll-up --------------------------------------------------
    def group_rollup(self) -> dict[str, Any]:
        offered_weight = {"asa", "abandon_rate", "forecast_accuracy"}
        out: dict[str, Any] = {"weeks": self.week_labels, "kpis": {}}
        piv = self.df.copy()
        for kpi in self.cfg["kpis"]:
            key = kpi["key"]
            wcol = "contacts_offered" if key in offered_weight else "contacts_handled"
            weekly = []
            for w in self.q_weeks:
                sub = piv[piv["week_ending"] == w]
                wsum = sub[wcol].sum()
                val = float((sub[key] * sub[wcol]).sum() / wsum) if wsum else float(sub[key].mean())
                weekly.append(val)
            weekly = np.array(weekly)
            current, prior, q_start = weekly[-1], weekly[-2], weekly[0]
            slope, r2 = linreg(weekly)
            span = slope * (len(weekly) - 1)
            rel = abs(span) / (abs(np.mean(weekly)) + 1e-9)
            if r2 >= 0.35 and rel >= 0.05:
                fav = is_favourable(span, kpi)
                trend = "improving" if fav else "deteriorating" if fav is False else "stable"
            else:
                trend = "stable"
            out["kpis"][key] = {
                "label": kpi["label"], "fmt": kpi["fmt"], "headline": bool(kpi.get("headline")),
                "category": kpi["category"], "unit": kpi["unit"],
                "current": current, "prior": prior, "q_start": q_start,
                "wow_delta": current - prior,
                "wow_pct": 100 * (current - prior) / prior if prior else 0.0,
                "q_delta": current - q_start,
                "q_pct": 100 * (current - q_start) / q_start if q_start else 0.0,
                "rag": rag_status(current, kpi), "series": [round(float(v), 3) for v in weekly],
                "trend": trend, "target": kpi["target"], "direction": kpi["direction"],
                "favourable_wow": is_favourable(current - prior, kpi),
                "favourable_q": is_favourable(current - q_start, kpi),
            }
        # group totals
        latest = piv[piv["week_ending"] == self.q_weeks[-1]]
        first = piv[piv["week_ending"] == self.q_weeks[0]]
        out["volume_handled"] = int(latest["contacts_handled"].sum())
        out["volume_offered"] = int(latest["contacts_offered"].sum())
        out["volume_handled_q1"] = int(first["contacts_handled"].sum())
        out["quarter_contacts"] = int(piv["contacts_handled"].sum())
        return out
