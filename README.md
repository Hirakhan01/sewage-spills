# Sewage Spills in England: Did They Really Fall, or Did It Just Stop Raining?

> Analysis of Environment Agency storm overflow data (2020–2025), adjusted for rainfall,
> to test how much of the 2025 fall in sewage spills came from water company action
> and how much came from a dry year.

**Status:** 🚧 In progress. Days 1–2 and the Power BI data model are done; next up is Day 3 (map view).

---

## The question

In 2025, storm overflow spills in England fell by 35% and spill hours nearly halved.
The Environment Agency credited mostly the dry weather; the water industry credited
investment. Nobody has published a neutral, rainfall-adjusted comparison across every
company. This project does that.

## Data sources

| Source | What it gives | Link |
|---|---|---|
| EA EDM Storm Overflow Annual Returns (2020–2025) | Spill counts and hours per overflow per year | [environment.data.gov.uk](https://environment.data.gov.uk/dataset/21e15f12-0df8-4bfc-b763-45226c16a8ac) |
| EA Rainfall API | 15-minute rainfall from ~1,000 gauges | [api.gov.uk/ea/rainfall](https://api.gov.uk/ea/rainfall/) |

Data is not committed to this repo. To reproduce:
1. Download the six yearly zips (2020–2025) and the Long-term Trends zip from the EA link above.
2. Put them, still zipped, in `data/raw/`.

## How to run

```bash
pip install -r requirements.txt
python src/day1_clean_edm.py data/raw data/clean
python src/day2_trends_league.py
```

Day 1 writes `data/clean/edm_annual_2020_2025.csv`. Day 2 writes the summary tables to
`outputs/tables/` and the charts to `outputs/figures/`.

## Power BI model

The report is in `powerbi/sewage-spills.pbip`, a Power BI project you can open in Power BI
Desktop. It loads the Day 1 and Day 2 CSVs, so run both scripts first.

It's a star schema: shared **Dim Company** and **Dim Year** tables filter the overflow-level
fact table, the EA long-term series, the like-for-like comparison and the EA reconciliation.
It has 24 measures, each with a description.

📄 **[docs/data_model.md](docs/data_model.md)** documents every table, relationship and
measure (with its DAX), the data-quality fixes made while building the model, and how the
measures were validated.

## Understanding the data

<!-- Fill in from the EA README guide (Day 1, Step 3) -->

- **How a spill is counted (12/24-hour rule):** _TODO_
- **EDM operation %:** _TODO_
- **How missing / no-data overflows are marked:** _TODO_

## Data dictionary (`data/clean/edm_annual_2020_2025.csv`)

| Column | Meaning | Source |
|---|---|---|
| `year` | Reporting year | File name |
| `water_company` | Water and sewerage company | Company sheet |
| `site_name` | Overflow site name (EA consents database) | Annual return |
| `permit_ref` / `activity_ref` | EA permit and activity references | Annual return |
| `overflow_id` | `permit_ref\|activity_ref` — joins the same overflow across years | Derived |
| `asset_type` | Type of storm discharge asset | Annual return |
| `outlet_ngr` | OS grid reference of the outlet | Annual return |
| `easting` / `northing` | Grid reference converted to coordinates for mapping | Derived |
| `receiving_water` | River / sea the overflow discharges into | Annual return |
| `spill_count` | Spills counted using the 12/24-hour method | Annual return |
| `spill_hours` | Total spill duration in hours | Annual return |
| `edm_operation_pct` | % of the year the monitor was working | Annual return |
| `flag_edm_below_90pct` | Monitor worked < 90% of the year (figures are a floor) | Derived |
| `flag_no_spill_data` | No spill count or duration reported | Derived |

## Decisions log

<!-- Record every judgement call and why. Great interview material. -->

**Cleaning (Day 1)**
- **"N/A" and "not monitored" are treated as missing, not zero.** A spill count of zero
  means no spills; a missing value means we don't know.
- **The 2025 "All WaSC" sheet is skipped.** It repeats every company sheet, so reading it
  as well would count everything twice.
- **Durations are converted to decimal hours.** 2020–2023 returns give hours as numbers.
  From 2024 the EA uses hh:mm:ss, which Excel stores in three different ways.

**Analysis (Day 2)**
- **Companies are compared per overflow, not on raw totals.** Raw totals mostly measure
  company size (Welsh Water has about 120 English overflows, Severn Trent about 2,450).
  This is also how the EA reports its headline average.
- **2024 → 2025 is compared like for like.** Only overflows present in both years, with
  monitors working at least 90% of the time in both, are included, because the set of
  overflows changes every year.

**Power BI model** (details in [docs/data_model.md](docs/data_model.md#data-quality-fixes))
- **The CSV is read with proper quote handling.** Power BI's default setting split rows at
  line breaks inside text fields, which created 23 junk rows.
- **The EA's long-term averages are shown as published,** even where they differ slightly
  from total ÷ overflows.
- **Year-on-year measures are blank unless exactly one year is selected,** rather than
  showing a misleading multi-year figure.

## Limitations

- Spill **duration** is not pollution **volume** — monitors don't measure how much sewage, or what was in it.
- Overflows with monitors working < 90% of the year are undercounted, so totals are a minimum.
- Annual return data is validated; live/near-real-time feeds are provisional and are not used here.

## Project plan

- [x] Day 1 — Combine and clean annual returns
- [x] Day 2 — Trends and per-overflow league table
- [x] Power BI data model: star schema, measures and validation ([docs/data_model.md](docs/data_model.md))
- [ ] Day 3 — Map view
- [ ] Days 4–5 — Rainfall join and dry-day spill detection
- [ ] Day 6 — Data-quality page and key findings
- [ ] Day 7 — Polish and publish

---
*Data: © Environment Agency copyright and/or database right. Contains public sector information licensed under the Open Government Licence v3.0.*
