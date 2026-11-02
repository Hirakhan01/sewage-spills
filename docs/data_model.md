# Data model: `powerbi/sewage-spills.pbip`

The Power BI semantic model behind the sewage spills report. It is a star schema with two
shared dimensions (company and year) and four imported tables built by the Python pipeline.

```
                 ┌──────────────┐                 ┌───────────┐
                 │ Dim Company  │                 │ Dim Year  │
                 │ (10 rows)    │                 │ 2016–2025 │
                 └──────┬───────┘                 └─────┬─────┘
        ┌───────────────┼──────────────┐     ┌──────────┼───────────────┐
        ▼               ▼              ▼     ▼          ▼               ▼
 like_for_like   Fact Overflow Year   reconciliation_vs_ea      long_term_trends
  _2024_2025    (one row per overflow   (one row per company     _2016_2025
 (per company)       per year)             per year)            (per year, EA)
```

All relationships are one-to-many and filter in one direction, from the Dim table to the
data table. All tables use Import storage mode.

---

## Tables

### Fact Overflow Year

One row per storm overflow per reporting year, 2020–2025 (84,957 rows). Source:
`data/clean/edm_annual_2020_2025.csv`, produced by `src/day1_clean_edm.py`. Renamed from
`edm_annual_2020_2025`.

| Column | Type | Summarize | Hidden | Notes |
|---|---|---|---|---|
| year | Whole number | None | Yes | Joins to Dim Year |
| water_company | Text | None | Yes | Joins to Dim Company |
| site_name | Text | None | | |
| site_name_wasc | Text | None | | Site name as given by the company |
| permit_ref | Text | None | | EA permit reference |
| activity_ref | Text | None | | EA activity reference |
| overflow_id | Text | None | Yes | `permit_ref\|activity_ref`; links the same overflow across years |
| asset_type | Text | None | | |
| outlet_ngr | Text | None | | OS grid reference |
| easting | Decimal number | None | | Converted from text. Some rows are 0, not blank; filter these out for maps |
| northing | Decimal number | None | | As easting |
| receiving_water | Text | None | | |
| wfd_waterbody_id | Text | None | | |
| spill_count | Whole number | Sum | | Spills counted with the 12/24-hour method |
| spill_hours | Decimal number | Sum | | Total spill duration (not volume) |
| edm_operation_pct | Decimal number | None | | % of the year the monitor worked (0–100 scale) |
| edm_low_reason | Text | None | | |
| high_spill_reason | Text | None | | |
| flag_site_name_filled | True/False | None | Yes | |
| flag_no_spill_data | True/False | None | | |
| flag_edm_below_90pct | True/False | None | | |
| source_file | Text | None | Yes | Lineage |
| source_sheet | Text | None | Yes | Lineage |

### long_term_trends_2016_2025

One row per year, 2016–2025: the EA's published long-term series. Source:
`outputs/tables/long_term_trends_2016_2025.csv`.

| Column | Type | Summarize | Hidden |
|---|---|---|---|
| year | Whole number | None | Yes |
| overflows_with_data | Whole number | Sum | |
| total_spills | Decimal number | Sum | |
| total_hours | Decimal number | Sum | |
| avg_spills_per_overflow | Decimal number | None | |
| hours_per_overflow | Decimal number | None | |

`total_spills` stays decimal because the EA's own figures for 2018, 2019 and 2021 are not
whole numbers. `avg_spills_per_overflow` is the EA's published value. It does not always equal
`total_spills / overflows_with_data` (2020: 32.6 published against 33.4 recalculated).

### like_for_like_2024_2025

One row per company, plus an `ALL COMPANIES` summary row. It covers only overflows reported
in both 2024 and 2025. Source: `outputs/tables/like_for_like_2024_2025.csv`.

| Column | Type | Summarize | Hidden |
|---|---|---|---|
| water_company | Text | None | Yes |
| matched_overflows | Whole number | None | |
| hours_2024 / hours_2025 | Decimal number | None | |
| spills_2024 / spills_2025 | Whole number | None | |
| pct_change_hours | Decimal number | None | |
| pct_change_spills | Decimal number | None | |

`pct_change_*` are stored in percentage points (e.g. -76.06), not as fractions. The measures
recalculate the change from the hours and spill columns instead.

### reconciliation_vs_ea

One row per company per year, 2020–2025 (60 rows): our totals compared with the EA's
published totals. Source: `outputs/tables/reconciliation_vs_ea.csv`.

| Column | Type | Summarize | Hidden |
|---|---|---|---|
| water_company | Text | None | Yes |
| year | Whole number | None | Yes |
| overflows, overflows_with_data, overflows_no_data | Whole number | Sum | |
| total_spills, total_hours | Decimal number | Sum | |
| spills_per_overflow, hours_per_overflow | Decimal number | None | |
| pct_monitors_ok | Decimal number | None | |
| ea_spills, ea_hours | Decimal number | Sum | |
| ea_overflows_listed | Whole number | Sum | |
| diff_spills_pct, diff_hours_pct | Decimal number | None | |
| diff_overflows | Whole number | Sum | |
| ok | True/False | None | |
| status | Text | None | `ok` (59 rows) or `CHECK` (1 row) |

### Dim Company (calculated table)

One row per water and sewerage company (10 rows). It excludes blanks and the like_for_like
`ALL COMPANIES` row.

```dax
FILTER(
    DISTINCT(SELECTCOLUMNS('Fact Overflow Year', "Water Company", 'Fact Overflow Year'[water_company])),
    [Water Company] <> ""
)
```

### Dim Year (calculated table)

Reporting years 2016–2025. It starts in 2016 so the EA long-term series is covered.

```dax
SELECTCOLUMNS(GENERATESERIES(2016, 2025, 1), "Year", [Value])
```

---

## Relationships

| From (many) | To (one) | Why |
|---|---|---|
| Fact Overflow Year[water_company] | Dim Company[Water Company] | Main link: one company has thousands of overflow-years |
| like_for_like_2024_2025[water_company] | Dim Company[Water Company] | One row per company. Set to one-to-many, not one-to-one, so it filters in one direction only. `ALL COMPANIES` has no match and appears as (Blank) only when no company is selected |
| reconciliation_vs_ea[water_company] | Dim Company[Water Company] | One row per company per year |
| Fact Overflow Year[year] | Dim Year[Year] | Covers 2020–2025, a subset of Dim Year |
| long_term_trends_2016_2025[year] | Dim Year[Year] | One row per year; one-to-many for the same reason as like_for_like. The only table that needs 2016–2019 |
| reconciliation_vs_ea[year] | Dim Year[Year] | One row per year per company |

Filters flow from the Dim tables out to the data tables, and the data tables never filter each
other. `reconciliation_vs_ea` is linked to both Dim tables, and one-way filtering stops it
from creating competing filter paths. The three relationships Power BI detected automatically
(fact → long_term_trends, reconciliation → long_term_trends, reconciliation → like_for_like)
were deleted.

---

## Measures

Every visible measure has a format string and a description. Implicit measures are
discouraged, so report visuals use these measures, not raw columns.

### Fact Overflow Year · Core

| Measure | Format | Description |
|---|---|---|
| Total Spills | `#,##0` | Total storm overflow spills, counted with the EA 12/24-hour method, summed across all overflows in the current filter. |
| Total Spill Hours | `#,##0` | Total spill duration in hours across all overflows in the current filter (duration, not sewage volume). |
| Overflows Listed | `#,##0` | Number of overflow-year rows listed in the annual returns, including overflows that reported no spill data. |
| Overflows With Data | `#,##0` | Number of overflow-year rows that reported a spill count, used as the denominator for per-overflow averages. |
| Spills per Overflow | `#,##0.0` | Average spills per overflow, counting only overflows that reported spill data. |
| Hours per Overflow | `#,##0.0` | Average spill hours per overflow, counting only overflows that reported spill data. |
| % Monitors OK | `0.0%` | Share of all listed overflows whose monitor worked at least 90% of the year; a blank monitor reading counts as not OK. |

```dax
Total Spills = SUM('Fact Overflow Year'[spill_count])

Total Spill Hours = SUM('Fact Overflow Year'[spill_hours])

Overflows Listed = COUNTROWS('Fact Overflow Year')

Overflows With Data =
CALCULATE(
    COUNTROWS('Fact Overflow Year'),
    KEEPFILTERS(NOT ISBLANK('Fact Overflow Year'[spill_count]))
)

Spills per Overflow = DIVIDE([Total Spills], [Overflows With Data])

Hours per Overflow = DIVIDE([Total Spill Hours], [Overflows With Data])

% Monitors OK =
DIVIDE(
    CALCULATE(
        COUNTROWS('Fact Overflow Year'),
        KEEPFILTERS('Fact Overflow Year'[edm_operation_pct] >= 90)
    ),
    COUNTROWS('Fact Overflow Year')
)
```

### Fact Overflow Year · Year on year

| Measure | Format | Description |
|---|---|---|
| Spill Hours PY | `#,##0` | Total Spill Hours for the year before the selected year; blank unless exactly one Dim Year is in context. |
| Spills per Overflow PY | `#,##0.0` | Spills per Overflow for the year before the selected year; blank unless exactly one Dim Year is in context. |
| Hours per Overflow PY | `#,##0.0` | Hours per Overflow for the year before the selected year; blank unless exactly one Dim Year is in context. |
| % Change Spill Hours vs PY | `+0.0%;-0.0%;0.0%` | Percentage change in Total Spill Hours versus the previous year; blank when either year has no data. |
| % Change Hours per Overflow vs PY | `+0.0%;-0.0%;0.0%` | Percentage change in Hours per Overflow versus the previous year, which adjusts for the number of overflows reporting. |
| Company Rank (Hours per Overflow) | `0` | Rank of the company by Hours per Overflow among all companies for the year(s) in context, where 1 is the most hours per overflow; ignores company slicers (values rounded to 6 decimals to avoid floating-point ties). |

```dax
Spill Hours PY =
VAR _year = SELECTEDVALUE('Dim Year'[Year])
RETURN
    IF(
        NOT ISBLANK(_year),
        CALCULATE([Total Spill Hours], 'Dim Year'[Year] = _year - 1)
    )

Spills per Overflow PY =
VAR _year = SELECTEDVALUE('Dim Year'[Year])
RETURN
    IF(
        NOT ISBLANK(_year),
        CALCULATE([Spills per Overflow], 'Dim Year'[Year] = _year - 1)
    )

Hours per Overflow PY =
VAR _year = SELECTEDVALUE('Dim Year'[Year])
RETURN
    IF(
        NOT ISBLANK(_year),
        CALCULATE([Hours per Overflow], 'Dim Year'[Year] = _year - 1)
    )

% Change Spill Hours vs PY =
VAR _current = [Total Spill Hours]
VAR _previous = [Spill Hours PY]
RETURN
    IF(
        NOT ISBLANK(_current) && NOT ISBLANK(_previous),
        DIVIDE(_current - _previous, _previous)
    )

% Change Hours per Overflow vs PY =
VAR _current = [Hours per Overflow]
VAR _previous = [Hours per Overflow PY]
RETURN
    IF(
        NOT ISBLANK(_current) && NOT ISBLANK(_previous),
        DIVIDE(_current - _previous, _previous)
    )

Company Rank (Hours per Overflow) =
VAR _current = [Hours per Overflow]
RETURN
    IF(
        HASONEVALUE('Dim Company'[Water Company]) && NOT ISBLANK(_current),
        RANKX(
            ALLNOBLANKROW('Dim Company'[Water Company]),
            ROUND([Hours per Overflow], 6),
            ROUND(_current, 6),
            DESC,
            DENSE
        )
    )
```

Dim Year holds plain years, not dates, so the previous year is found with `Year - 1`. Power
BI's built-in previous-year functions need a date table and won't work here.

### like_for_like_2024_2025 · Like-for-like

| Measure | Format | Description |
|---|---|---|
| LFL % Change Hours | `+0.0%;-0.0%;0.0%` | Change in spill hours from 2024 to 2025 counting only overflows present in both years, recalculated from hours so it totals correctly across companies. |
| LFL % Change Spills | `+0.0%;-0.0%;0.0%` | Change in spill count from 2024 to 2025 counting only overflows present in both years, recalculated from counts so it totals correctly across companies. |
| LFL Matched Overflows | `#,##0` | Number of overflows reported in both 2024 and 2025, excluding the ALL COMPANIES summary row to avoid double counting. |
| LFL % Change Hours (All Companies) | `+0.0%;-0.0%;0.0%` | England-wide like-for-like change in spill hours from the ALL COMPANIES row, ignoring any company selection so it can serve as a reference line. |

```dax
LFL % Change Hours =
VAR _hours2024 = CALCULATE(SUM(like_for_like_2024_2025[hours_2024]), KEEPFILTERS(like_for_like_2024_2025[water_company] <> "ALL COMPANIES"))
VAR _hours2025 = CALCULATE(SUM(like_for_like_2024_2025[hours_2025]), KEEPFILTERS(like_for_like_2024_2025[water_company] <> "ALL COMPANIES"))
RETURN
    DIVIDE(_hours2025 - _hours2024, _hours2024)

LFL % Change Spills =
VAR _spills2024 = CALCULATE(SUM(like_for_like_2024_2025[spills_2024]), KEEPFILTERS(like_for_like_2024_2025[water_company] <> "ALL COMPANIES"))
VAR _spills2025 = CALCULATE(SUM(like_for_like_2024_2025[spills_2025]), KEEPFILTERS(like_for_like_2024_2025[water_company] <> "ALL COMPANIES"))
RETURN
    DIVIDE(_spills2025 - _spills2024, _spills2024)

LFL Matched Overflows =
CALCULATE(
    SUM(like_for_like_2024_2025[matched_overflows]),
    KEEPFILTERS(like_for_like_2024_2025[water_company] <> "ALL COMPANIES")
)

LFL % Change Hours (All Companies) =
CALCULATE(
    DIVIDE(
        SUM(like_for_like_2024_2025[hours_2025]) - SUM(like_for_like_2024_2025[hours_2024]),
        SUM(like_for_like_2024_2025[hours_2024])
    ),
    REMOVEFILTERS('Dim Company'),
    like_for_like_2024_2025[water_company] = "ALL COMPANIES"
)
```

### long_term_trends_2016_2025 · EA long-term

| Measure | Format | Description |
|---|---|---|
| EA Spills per Overflow | `#,##0.0` | EA-published average spills per monitored overflow for the selected year; blank unless exactly one year is in context because averages cannot be added. |
| EA Hours per Overflow | `#,##0.0` | EA-published average spill hours per monitored overflow for the selected year; blank unless exactly one year is in context because averages cannot be added. |
| EA Total Spill Hours | `#,##0` | Total spill hours from the EA long-term trends series (2016 onwards), summed over the years in context. |
| EA Overflows With Data | `#,##0` | Number of overflows with monitoring data in the EA long-term series; across several years this counts overflow-years, not distinct overflows. |

```dax
EA Spills per Overflow =
IF(
    HASONEVALUE('Dim Year'[Year]),
    SUM(long_term_trends_2016_2025[avg_spills_per_overflow])
)

EA Hours per Overflow =
IF(
    HASONEVALUE('Dim Year'[Year]),
    SUM(long_term_trends_2016_2025[hours_per_overflow])
)

EA Total Spill Hours = SUM(long_term_trends_2016_2025[total_hours])

EA Overflows With Data = SUM(long_term_trends_2016_2025[overflows_with_data])
```

### reconciliation_vs_ea · Validation

| Measure | Format | Description |
|---|---|---|
| Company-Years Validated | `#,##0` | Number of company-year totals that match the EA's published figures within tolerance (status = ok). |
| Company-Years Checked | `#,##0` | Number of company-year totals compared against the EA's published figures, whether they passed (ok) or need review (CHECK). |
| Validation Label | text | Text summary of validated versus checked company-years, such as 59 / 60, for a card or subtitle. |

```dax
Company-Years Validated =
CALCULATE(
    COUNTROWS(reconciliation_vs_ea),
    KEEPFILTERS(reconciliation_vs_ea[status] = "ok")
)

Company-Years Checked =
CALCULATE(
    COUNTROWS(reconciliation_vs_ea),
    KEEPFILTERS(reconciliation_vs_ea[status] IN {"ok", "CHECK"})
)

Validation Label =
FORMAT(COALESCE([Company-Years Validated], 0), "0")
    & " / "
    & FORMAT(COALESCE([Company-Years Checked], 0), "0")
```

### When no year is selected

| Measures | No year selected |
|---|---|
| PY measures, % Change measures, EA Spills/Hours per Overflow | Blank, on purpose: a change or average across several years would be misleading |
| Company Rank | Ranks on all six years combined |
| Totals (Core, EA Total Spill Hours, EA Overflows With Data) | Added up across the years in context |

Report pages should use a **single-select year slicer** (saved on 2025), so year-on-year cards
always have exactly one year.

---

## Data-quality fixes

### 1. CSV quote handling and junk rows

The fact table's Power Query step read the CSV with `QuoteStyle.None`. That setting ignores
quotes, so a line break inside a quoted text field started a new row. 20 source records
contain such line breaks (mostly free-text notes), so Power BI loaded **84,980 rows instead of
84,957**:

- **23 junk rows** came from the split fragments. They had a blank year and values in the
  wrong columns, including river names such as "RIVER AVON" and "POOLE BAY (C)" in
  `water_company`. A company dimension built from that table would have had 26
  "companies" instead of 10.
- **20 records were cut short** and kept a wrong `overflow_id`.
- Spill counts and hours were **not** affected: yearly totals matched the CSV exactly before
  and after the fix.

**Fix:** `QuoteStyle.Csv`. The table now loads 84,957 rows, and every `overflow_id` equals
`permit_ref|activity_ref`. One genuine blank-company row remains: a Severn Trent 2021 note
line from the EA workbook, flagged `flag_no_spill_data = TRUE`. It shows as (Blank) under
Dim Company. The Python pipeline was never affected; only Power BI's reading of the CSV was.

### 2. Grid references stored as text

`easting` and `northing` were text. They were converted to Decimal number in the Power Query
type step (so a refresh keeps them) and in the model. Some rows hold 0 rather than blank; the
map visual should exclude them.

### 3. Default totals on ratio columns

Percentage, average and ratio columns were set to add up by default, which gives meaningless
totals. They are now set to Don't summarize, and the figures come from explicit measures
instead.

### 4. Rank rounding

`Company Rank (Hours per Overflow)` first returned rank 3 for Thames Water in 2025 when Thames
was the only company selected (its correct rank is 2). RANKX compares the company's value
calculated in the outer filter with the same value calculated inside its loop over companies.
The two add up the same rows in a different order, so the results differed in the last binary
digit and Thames appeared to outrank itself. **Fix:** both values are rounded to 6 decimals
before ranking. All 10 companies now get the same rank in a table and when filtered on their
own.

### Known open items

- Southern Water 2021: `reconciliation_vs_ea.total_spills` = 19,077.41. The raw return
  probably contains a fractional spill count, which the whole-number `spill_count` column
  rounds, so the fact table's 2021 total is 0.41 lower.
- EA-published spills per overflow differs from total ÷ overflows in 2020–2022 and 2024–2025.
  The EA probably uses a different denominator.

---

## How the model was built

The model was built with [Claude Code](https://claude.com/claude-code) through the
**Power BI Authoring MCP server** (`powerbi-modeling-mcp`). It connected to the model open in
Power BI Desktop, and every change was made against the live model: query and type fixes,
dimension tables, relationships, measures and formats. Each step was planned and approved
before it ran.

Every measure was validated with DAX queries against expected values from the Python
analysis (`src/`). Those figures had already been reconciled with the Environment Agency's
published annual return totals; the reconciliation passes for 59 of 60 company-years. Checked
values include:

| Check | Result |
|---|---|
| Total Spills 2024 / 2025 | 450,398 / 292,119 |
| Total Spill Hours 2024 / 2025 | 3,614,428 / 1,878,240 |
| Overflows With Data 2024 / 2025 | 14,182 / 14,239 |
| Spills per Overflow 2024 / 2025 | 31.8 / 20.5 |
| Hours per Overflow 2024 / 2025 | 254.9 / 131.9 |
| % Monitors OK 2024 / 2025 | 90.3% / 92.5% |
| % Change Spill Hours vs PY 2025 | -48.0% |
| % Change Hours per Overflow vs PY 2025 | -48.2% |
| Company Rank 2025 | South West Water 1, Thames Water 2, Anglian Water 10 |
| LFL % Change Hours | Anglian -76.1%, United Utilities -26.3%, South West -25.9%; all companies -48.9% |
| EA Spills per Overflow 2016 / 2019 / 2025 | 14.7 / 35.4 / 20.5 |
| Validation Label | 59 / 60 |
