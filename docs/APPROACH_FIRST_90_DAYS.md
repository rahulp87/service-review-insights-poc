# How I would run Service Review & Insights — first 90 days

A short note on the operating approach behind the POC. The code shows the
*what*; this is the *how*.

## The problem this role exists to solve

Executives do not need more dashboards. They need a small number of reliable,
comparable, well-argued read-outs that tell them where to spend attention.
Today that typically means five business units producing five differently-shaped
decks, on five cadences, with the analyst time going into assembly rather than
insight. The job is to fix that — make the reporting model standard, make the
build automatic, and spend the freed capacity on the story.

## Days 0–30 — Establish the standard

- **Agree the KPI model.** Lock one definition, one target and one RAG rule per
  metric with Ops, Strategy and Finance. This is `kpi_definitions.yaml` in the
  POC — a real version is signed off, versioned, and owned.
- **Map the data.** Inventory the ACD / WFM / QA / finance sources feeding each
  unit. Identify where definitions silently differ today (AHT with/without ACW,
  abandon thresholds, FCR windows) — that is usually where the "our numbers
  don't match" friction lives.
- **Ship one pack, one unit, end to end** from real data, even if manual, to
  prove the model and get reactions from an actual exec reader.

## Days 30–60 — Automate and widen

- **Stand up the pipeline.** Connectors → validation → KPI layer → pack build,
  on a schedule. Data-quality gates fail loudly rather than publishing a wrong
  number quietly.
- **Roll the template across all units.** Retire the bespoke decks. Every unit
  now gets the same scorecard, the same charts, the same appendix.
- **Add the anomaly + trend scan** and tune thresholds with the unit leads so
  the watch list is trusted, not noise.
- **Introduce structured commentary capture** — unit leads add context against
  flagged items in a fixed format, which flows into the pack instead of a
  separate email thread.

## Days 60–90 — Make it drive action

- **Close the loop on recommendations.** Every pack carries owned actions with
  a horizon; the next pack opens with progress against them.
- **Executive review ritual.** A 30-minute standing session per cycle where the
  pack *is* the agenda. If a slide isn't decision-relevant, it moves to the
  appendix.
- **Publish the efficiency dividend.** Quantify the analyst-days saved by
  standardisation and reinvest them visibly into deeper analysis (repeat-contact
  driver trees, cost-to-serve by journey, forecast bias).

## Principles I would hold to

| Principle | In practice |
|---|---|
| **One bottom line per pack** | The reader should be able to repeat the headline after 20 seconds. |
| **Every number has a target** | A metric with no threshold is trivia, not a KPI. |
| **Standard beats bespoke** | Comparability across units is worth more than a locally-perfect layout. |
| **The narrative is generated, then edited** | Start from the rules-based read-out so the story can't drift from the data; add human judgement on top. |
| **Movement over level** | "78%" matters less than "78%, down 6 points in three weeks, now red." |
| **Surface bad news early and plainly** | Escalations lead the pack; they don't hide in a grid on page 9. |

## Team

The insight professionals on the team should be doing analysis, not assembly.
The pipeline exists so their week goes into *why the number moved and what to
do*, reviewed and coached against a shared QA rubric — with the pack build
itself reduced to a scheduled job anyone can trigger and everyone can trust.
