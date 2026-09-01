# Service Review Insights Lead — Working POC

**A one-command pipeline that turns raw contact-centre operational data into a
board-ready quarterly service review pack.**

Built as a proof of concept for the *Service Review Insights Lead* role
(Dubai, Cloud / DevOps & Infrastructure — data analytics division). It is
deliberately small, readable and self-contained: the goal is to show *how I
think about the job*, not to ship a platform.

---

## What it produces

| Output | File | What it is |
|---|---|---|
| **Executive review pack** | `output/service_review_pack.html` | A single, portable, print-ready HTML board pack — cover, executive summary with auto-written narrative, group KPI scorecard, per-business-unit review, anomaly watch list, recommended actions, and a standardised KPI appendix. Works offline, light/dark, and exports cleanly to PDF. |
| **Machine-readable summary** | `output/review_summary.json` | The same headline numbers, unit scores, anomalies and actions as JSON — so the pack can feed a wiki, an email digest or a dashboard without re-running the analysis. |

Open `output/service_review_pack.html` in any browser to see the result.

---

## How it maps to the job description

> *"Lead the creation of high-impact business review packs and board presentations for senior executives."*
The HTML pack **is** the deliverable — designed to the standard an Operations
Board expects: one bottom line, a RAG scorecard that reads in five seconds,
and every number tied to a target.

> *"Translate raw operational metrics into compelling stories that drive strategic action."*
`narrative.py` is a rules-based storytelling layer. It writes the bottom line,
the executive summary, the per-unit read-outs and the recommended actions
straight from the computed movements — no hand-editing. Deterministic, so the
same data always tells the same story.

> *"Proactively spot trends, anomalies and operational efficiency gains within voice and call centre operations."*
`analytics.py` runs a trailing-baseline z-score + step-change scan every week,
classifies quarter trends by regression slope and fit, and promotes only the
*material, adverse* signals to the Board watch list. The synthetic data hides
five deliberate stories (a Technical Support SL collapse, a Collections AHT
drift, a Retention recovery, a Consumer Care telephony incident, a quietly
strong SME Desk) — the pipeline surfaces all five unaided.

> *"Standardise visual reporting models across all business units to ensure total consistency."*
`config/kpi_definitions.yaml` is the single source of truth: one definition,
one target and one RAG rule per KPI, applied identically to every unit. Change
the target once and every pack, chart and chip updates. Adding a unit is one
line.

> *"Strong background in data visualization, KPI automation and performance reporting frameworks."*
Charts are dependency-free inline SVG (sparklines with target lines, trend
charts with target/amber bands) generated in `charts.py`. The whole pack is
rebuilt with `python src/build_review_pack.py` — no manual step, no Excel.

> *"Manage cross-functional team members while managing multiple reporting schedules simultaneously."*
The design intent: this pipeline replaces five bespoke unit decks with one
templated build an analyst can run on a schedule, freeing the team to work on
the insight rather than the assembly. That case is made explicitly in
recommendation R3 of the pack.

---

## Voice / contact-centre KPIs modelled

Service Level (20s) · Average Speed of Answer · Abandonment Rate ·
Average Handle Time · First Contact Resolution · CSAT · Repeat Contact Rate ·
Occupancy · Schedule Adherence · Forecast Accuracy · Cost per Contact.

Targets and RAG thresholds are industry-standard starting points and live in
the YAML — they are meant to be argued about and tuned with the business.

---

## Running it

```bash
pip install pandas numpy pyyaml jinja2
python src/generate_data.py        # writes data/weekly_metrics.csv (synthetic)
python src/build_review_pack.py     # writes output/service_review_pack.html + .json
```

No API keys, no network calls, no database. Python 3.10+.

### To point it at real data

Replace `data/weekly_metrics.csv` with a weekly export in the same shape
(one row per business unit per week; column names match the KPI keys in the
YAML). Nothing else changes.

---

## Project layout

```
config/kpi_definitions.yaml   Standardised KPI model — targets, RAG rules, definitions
src/generate_data.py          Synthetic weekly data generator (with built-in stories)
src/analytics.py              KPI computation, trend regression, anomaly detection, roll-ups
src/narrative.py              Rules-based executive narrative + recommendations
src/charts.py                 Inline-SVG sparklines and trend charts
src/build_review_pack.py      Orchestrator — renders the HTML pack + JSON summary
src/templates/review_pack.html.j2   The standardised pack layout
docs/APPROACH_FIRST_90_DAYS.md      How I would run this function for real
output/                       Generated pack + summary
```

---

## What this POC is *not*

It is a demonstration, not a product. Real deployment would add: authenticated
data connectors (ACD / WFM / finance), unit tests and data-quality gates,
a scheduled run with alerting, commentary capture from unit leads, and
access-controlled distribution. The point here is the reporting model and the
narrative logic — the parts that actually make a service review useful.

*All data in this repository is synthetic and generated locally.*
