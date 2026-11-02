"""
Day 2 - National trend (2016-2025), fair company league table, a like-for-like
comparison of 2024 vs 2025, and a reconciliation against the EA's own
per-company totals.

Usage (from the project folder, after Day 1):
    python src/day2_trends_league.py

Reads   data/clean/edm_annual_2020_2025.csv
        data/raw/*Long-term*.zip   (EA long-term trends + yearly summary tables)
Writes  outputs/tables/*.csv      (feed these into Power BI)
        outputs/figures/*.png     (for the README)

Why "per overflow"?
    Companies have very different numbers of overflows (Welsh Water's English
    sites ~120, Severn Trent ~2,450). Raw totals mostly measure size. Dividing by
    the number of overflows gives a fair comparison, and it's how the EA reports
    its own headline average (2024: 31.8 spills per overflow, 2025: 20.5).

Why "like-for-like"?
    The set of overflows changes every year (new monitors, closures, re-permits),
    and broken monitors undercount spills. So the fairest 2024 -> 2025 comparison
    uses only overflows that appear in BOTH years with monitors working >= 90%
    of the time in both.
"""

import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit("matplotlib is missing - run:  pip install matplotlib")

CLEAN = Path("data/clean/edm_annual_2020_2025.csv")
RAW = Path("data/raw")
TABLES = Path("outputs/tables")
FIGS = Path("outputs/figures")

# Chart styling (validated reference palette, light mode)
BLUE, BLUE_LIGHT, ORANGE = "#2a78d6", "#9ec5f4", "#eb6834"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

EA_PUBLISHED = {  # England headline figures from EA press releases, for validation
    2024: {"avg_spills_per_overflow": 31.8},
    2025: {"avg_spills_per_overflow": 20.5},
}

# One canonical name per company, so our data and the EA's tables line up
COMPANY_KEYWORDS = [
    ("anglian", "Anglian Water"), ("cymru", "Dwr Cymru Welsh Water"),
    ("welsh", "Dwr Cymru Welsh Water"), ("northumbrian", "Northumbrian Water"),
    ("severn", "Severn Trent Water"), ("south west", "South West Water"),
    ("southern", "Southern Water"), ("thames", "Thames Water"),
    ("united", "United Utilities"), ("wessex", "Wessex Water"),
    ("yorkshire", "Yorkshire Water"),
]


def canon(name):
    s = str(name).lower()
    for kw, canonical in COMPANY_KEYWORDS:
        if kw in s:
            return canonical
    return None


# --------------------------------------------------------------------------
# 1. Load
# --------------------------------------------------------------------------
def norm_ref(s: pd.Series) -> pd.Series:
    return (s.astype("string").str.upper()
             .str.replace(r"\s+", "", regex=True)
             .fillna(""))


def load() -> pd.DataFrame:
    if not CLEAN.exists():
        sys.exit(f"{CLEAN} not found - run Day 1 first.")
    df = pd.read_csv(CLEAN, low_memory=False)
    df["water_company"] = df["water_company"].map(lambda n: canon(n) or n)
    df["edm_ok"] = df["edm_operation_pct"] >= 90

    df["_permit"] = norm_ref(df["permit_ref"])
    df["_act"] = norm_ref(df["activity_ref"])
    df["_ngr"] = norm_ref(df["outlet_ngr"])
    df["_site"] = (df["site_name"].astype("string").str.upper()
                   .str.replace(r"[^A-Z0-9]", "", regex=True).fillna(""))
    df["overflow_key"] = df["_permit"] + "|" + df["_act"] + "|" + df["_ngr"]
    return df


# --------------------------------------------------------------------------
# 2. EA reference tables (long-term trends + per-company summaries)
# --------------------------------------------------------------------------
def to_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return float("nan")


def read_ea_reference():
    """Returns (long_term DataFrame, ea_company_totals DataFrame) or (None, None)."""
    zips = [p for p in RAW.glob("*.zip") if re.search(r"long|trend", p.name, re.I)]
    if not zips:
        print("\n(No long-term trends zip in data/raw - skipping 2016-2019 and reconciliation.)")
        return None, None
    with zipfile.ZipFile(zips[0]) as z:
        member = next(m for m in z.namelist() if m.lower().endswith(".xlsx"))
        with z.open(member) as f:
            sheets = pd.read_excel(f, sheet_name=None, header=None, dtype=object)

    long_term, company_rows = None, []
    for name, s in sheets.items():
        if re.search(r"long", name, re.I):
            long_term = parse_long_term(s)
        m = re.search(r"(20\d{2})\s*summary", name, re.I)
        if m:
            company_rows += parse_company_summary(s, int(m.group(1)))
    return long_term, pd.DataFrame(company_rows)


def parse_long_term(s: pd.DataFrame) -> pd.DataFrame:
    # header row = the row that contains the year 2016
    hdr = next(i for i in range(len(s))
               if any(re.fullmatch(r"2016(\.0)?", str(v).strip()) for v in s.iloc[i]))
    year_cols = {}
    for c, v in s.iloc[hdr].items():
        m = re.match(r"(20\d{2})", str(v).strip())
        if m:
            year_cols[c] = int(m.group(1))
    label_col = min(c for c in s.columns if c < min(year_cols) and pd.notna(s.iloc[hdr][c]))

    wanted = {
        "overflows_with_data": r"with spill",
        "total_spills": r"monitored spill events",
        "total_hours": r"total duration",
        "avg_spills_per_overflow": r"average number of spill",
    }
    out = {"year": list(year_cols.values())}
    for col, pattern in wanted.items():
        row = next((i for i in range(hdr + 1, len(s))
                    if re.search(pattern, str(s.iloc[i][label_col]), re.I)), None)
        out[col] = [to_num(s.iloc[row][c]) if row is not None else float("nan") for c in year_cols]
    lt = pd.DataFrame(out)
    lt["hours_per_overflow"] = lt["total_hours"] / lt["overflows_with_data"]
    return lt


def parse_company_summary(s: pd.DataFrame, year: int):
    hdr = next((i for i in range(len(s)) if any("anglian" in str(v).lower() for v in s.iloc[i])), None)
    if hdr is None:
        return []
    label_col = next(c for c in s.columns if pd.notna(s.iloc[hdr][c]))
    comp_cols = {c: canon(v) for c, v in s.iloc[hdr].items()
                 if c != label_col and canon(v)}

    def find(pattern, exclude=r"average|%"):
        for i in range(hdr + 1, len(s)):
            lab = str(s.iloc[i][label_col])
            if re.search(pattern, lab, re.I) and not re.search(exclude, lab, re.I):
                return i
        return None

    rows = {
        "ea_spills": find(r"(spill events|monitored spill)"),
        "ea_hours": find(r"duration"),
        "ea_overflows_listed": find(r"overflows listed|storm overflows listed"),
    }
    out = []
    for c, comp in comp_cols.items():
        rec = {"year": year, "water_company": comp}
        for k, r in rows.items():
            rec[k] = to_num(s.iloc[r][c]) if r is not None else float("nan")
        out.append(rec)
    return out


def reconcile(cy: pd.DataFrame, ea: pd.DataFrame) -> pd.DataFrame:
    if ea is None or ea.empty:
        return pd.DataFrame()
    r = cy.merge(ea, on=["year", "water_company"], how="outer")
    r["diff_spills_pct"] = 100 * (r["total_spills"] / r["ea_spills"] - 1)
    r["diff_hours_pct"] = 100 * (r["total_hours"] / r["ea_hours"] - 1)
    r["diff_overflows"] = r["overflows"] - r["ea_overflows_listed"]
    r["ok"] = (r["diff_spills_pct"].abs() <= 2) & (r["diff_hours_pct"].abs() <= 2)
    has_ea = r["ea_spills"].notna() & r["ea_hours"].notna()
    r["status"] = "-"
    r.loc[has_ea & r["ok"], "status"] = "ok"
    r.loc[has_ea & ~r["ok"], "status"] = "CHECK"

    print("\n=== Reconciliation vs EA per-company totals (within 2% = ok, '-' = no EA figure) ===")
    piv = r.pivot_table(index="water_company", columns="year", values="status", aggfunc="first")
    print(piv.fillna("-").to_string())
    bad = r[r["status"] == "CHECK"].sort_values(["year", "water_company"])
    if len(bad):
        print("\n  Rows to look at:")
        print(bad[["year", "water_company", "overflows", "ea_overflows_listed",
                   "total_spills", "ea_spills", "diff_spills_pct",
                   "total_hours", "ea_hours", "diff_hours_pct"]].round(1).to_string(index=False))
    return r


# --------------------------------------------------------------------------
# 3. Metrics
# --------------------------------------------------------------------------
def summarise(g: pd.DataFrame) -> pd.Series:
    # Like the EA, average over overflows that actually reported spill data -
    # an overflow with no data isn't an overflow with zero spills.
    n = g["spill_count"].notna().sum()
    return pd.Series({
        "overflows": len(g),
        "overflows_with_data": n,
        "total_spills": g["spill_count"].sum(),
        "total_hours": g["spill_hours"].sum(),
        "spills_per_overflow": g["spill_count"].sum() / n,
        "hours_per_overflow": g["spill_hours"].sum() / n,
        "pct_monitors_ok": 100 * g["edm_ok"].mean(),
        "overflows_no_data": int(g["flag_no_spill_data"].sum()),
    })


def national_trend(df):
    t = df.groupby("year").apply(summarise, include_groups=False).reset_index()
    print("\n=== National trend 2020-2025 (your data) ===")
    print(t.round(1).to_string(index=False))
    for yr, ref in EA_PUBLISHED.items():
        if yr in t["year"].values:
            mine = t.loc[t["year"] == yr, "spills_per_overflow"].iloc[0]
            print(f"  {yr}: avg spills per overflow = {mine:.1f}  (EA published {ref['avg_spills_per_overflow']})")
    return t


def company_year(df):
    return (df.groupby(["water_company", "year"])
              .apply(summarise, include_groups=False).reset_index())


def league_table(cy, year=2025, prev=2024):
    cur = cy[cy["year"] == year].set_index("water_company")
    old = cy[cy["year"] == prev].set_index("water_company")
    lt = cur[["overflows", "total_spills", "total_hours",
              "spills_per_overflow", "hours_per_overflow", "pct_monitors_ok"]].copy()
    lt[f"hours_per_overflow_{prev}"] = old["hours_per_overflow"]
    lt["pct_change_hours_per_overflow"] = 100 * (lt["hours_per_overflow"] / old["hours_per_overflow"] - 1)
    lt["pct_change_spills_per_overflow"] = 100 * (lt["spills_per_overflow"] / old["spills_per_overflow"] - 1)
    lt = lt.sort_values("hours_per_overflow", ascending=False)
    lt.insert(0, "rank_worst_first", range(1, len(lt) + 1))
    print(f"\n=== League table {year} (worst first, by spill hours per overflow) ===")
    print(lt.round(1).to_string())
    return lt.reset_index()


# --------------------------------------------------------------------------
# 4. Like-for-like matching across years
# --------------------------------------------------------------------------
MATCH_PASSES = [  # tried in order; each only uses rows not matched yet
    ("permit+activity+gridref", ["_permit", "_act", "_ngr"], "_permit"),
    ("permit+activity",         ["_permit", "_act"],         "_permit"),
    ("permit+gridref",          ["_permit", "_ngr"],         "_ngr"),
    ("company+site name",       ["water_company", "_site"],  "_site"),
]


def match_years(df, a=2024, b=2025):
    A = df[df["year"] == a].copy()
    B = df[df["year"] == b].copy()
    A["_row"], B["_row"] = A.index, B.index
    pairs = []
    for method, cols, must_have in MATCH_PASSES:
        ua = A[~A["_row"].isin([p[0] for p in pairs]) & (A[must_have] != "")]
        ub = B[~B["_row"].isin([p[1] for p in pairs]) & (B[must_have] != "")]
        def make_key(d):
            k = d[cols[0]].astype(str)
            for c in cols[1:]:
                k = k + "|" + d[c].astype(str)
            return d.assign(k=k)
        ka, kb = make_key(ua), make_key(ub)
        ka = ka[~ka["k"].duplicated(keep=False)]   # only keys unique in each year
        kb = kb[~kb["k"].duplicated(keep=False)]
        m = ka[["k", "_row"]].merge(kb[["k", "_row"]], on="k", suffixes=("_a", "_b"))
        pairs += [(ra, rb, method) for ra, rb in zip(m["_row_a"], m["_row_b"])]

    p = pd.DataFrame(pairs, columns=["row_a", "row_b", "match_method"])
    cols = ["water_company", "site_name", "spill_hours", "spill_count", "edm_ok"]
    wide = (p.join(df.loc[p["row_a"], cols].reset_index(drop=True).add_suffix(f"_{a}"))
             .join(df.loc[p["row_b"], ["spill_hours", "spill_count", "edm_ok"]]
                   .reset_index(drop=True).add_suffix(f"_{b}")))
    wide = wide.rename(columns={f"water_company_{a}": "water_company", f"site_name_{a}": "site_name"})

    print(f"\n=== Matching overflows {a} -> {b} ===")
    print(f"  matched {len(wide):,} of {len(A):,} ({100 * len(wide) / len(A):.0f}%)")
    print("  by method:", wide["match_method"].value_counts().to_dict())
    rate = (wide.groupby("water_company").size() / A.groupby("water_company").size() * 100).round(0)
    print("  match rate by company (%):", rate.to_dict())
    return wide


def like_for_like(wide, a=2024, b=2025):
    ok = wide[wide[f"edm_ok_{a}"].astype(bool) & wide[f"edm_ok_{b}"].astype(bool)].dropna(
        subset=[f"spill_hours_{a}", f"spill_hours_{b}"])
    print(f"  usable for like-for-like (monitor >= 90% in both years): {len(ok):,}")
    lfl = ok.groupby("water_company").agg(
        matched_overflows=("site_name", "size"),
        **{f"hours_{a}": (f"spill_hours_{a}", "sum"), f"hours_{b}": (f"spill_hours_{b}", "sum"),
           f"spills_{a}": (f"spill_count_{a}", "sum"), f"spills_{b}": (f"spill_count_{b}", "sum")})
    lfl.loc["ALL COMPANIES"] = lfl.sum()
    lfl["pct_change_hours"] = 100 * (lfl[f"hours_{b}"] / lfl[f"hours_{a}"] - 1)
    lfl["pct_change_spills"] = 100 * (lfl[f"spills_{b}"] / lfl[f"spills_{a}"] - 1)
    print(f"\n=== Like-for-like {a} vs {b} ===")
    print(lfl.round(1).to_string())
    return lfl.reset_index(), ok


# --------------------------------------------------------------------------
# 5. Charts
# --------------------------------------------------------------------------
def style(ax, title, subtitle=None):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_title(title, loc="left", fontsize=12, color=INK, fontweight="bold", pad=18)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2)


def bar_labels(ax, bars, vals, fmt):
    vals = list(vals)
    peak = max(vals)
    for b, v in zip(bars, vals):  # label first, peak and last only
        if b in (bars[0], bars[-1]) or v == peak:
            ax.text(b.get_x() + b.get_width() / 2, v, fmt(v), ha="center",
                    va="bottom", fontsize=9, color=INK)


def fig_trend(t):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=SURFACE)
    yrs = t["year"].astype(str)
    for ax, col, title, fmt in (
        (axes[0], "total_hours", "Total spill hours, England", lambda v: f"{v/1e6:.2f}m"),
        (axes[1], "spills_per_overflow", "Average spills per overflow", lambda v: f"{v:.1f}"),
    ):
        bars = ax.bar(yrs, t[col], color=BLUE, width=0.6)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", labelleft=False)
        bar_labels(ax, bars, t[col], fmt)
        style(ax, title)
    fig.text(0.01, 0.01, "Source: Environment Agency EDM Storm Overflow Annual Returns 2020-2025",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGS / "01_national_trend.png", dpi=160)
    plt.close(fig)


def fig_long_term(lt):
    d = lt.dropna(subset=["avg_spills_per_overflow"])
    fig, ax = plt.subplots(figsize=(10, 4.2), facecolor=SURFACE)
    colors = [BLUE_LIGHT if y < 2020 else BLUE for y in d["year"]]
    bars = ax.bar(d["year"].astype(str), d["avg_spills_per_overflow"], color=colors, width=0.6)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelleft=False)
    bar_labels(ax, bars, d["avg_spills_per_overflow"], lambda v: f"{v:.1f}")
    first = d.iloc[0]
    style(ax, "Average spills per monitored overflow, England 2016-2025",
          f"Lighter bars: monitors still being installed ({first['overflows_with_data']:,.0f} overflows "
          f"monitored in {first['year']:.0f}), so early years aren't directly comparable")
    fig.text(0.01, 0.01, "Source: Environment Agency EDM Annual Returns - Long-term Trends",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGS / "04_long_term_spills_per_overflow.png", dpi=160)
    plt.close(fig)


def fig_league(lt, year=2025):
    d = lt.sort_values("hours_per_overflow")
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=SURFACE)
    bars = ax.barh(d["water_company"], d["hours_per_overflow"], color=BLUE, height=0.6)
    for b, v in zip(bars, d["hours_per_overflow"]):
        ax.text(v, b.get_y() + b.get_height() / 2, f"  {v:.0f}", va="center", fontsize=9, color=INK)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=INK_2)
    style(ax, f"Spill hours per overflow, {year}",
          "Average hours of untreated discharge per storm overflow - longest at top")
    fig.tight_layout()
    fig.savefig(FIGS / "02_league_table_hours_per_overflow.png", dpi=160)
    plt.close(fig)


def fig_change(lfl, a=2024, b=2025):
    d = lfl[lfl["water_company"] != "ALL COMPANIES"].sort_values("pct_change_hours", ascending=False)
    total = lfl.loc[lfl["water_company"] == "ALL COMPANIES", "pct_change_hours"].iloc[0]
    colors = [ORANGE if v > 0 else BLUE for v in d["pct_change_hours"]]
    fig, ax = plt.subplots(figsize=(9, 5.5), facecolor=SURFACE)
    bars = ax.barh(d["water_company"], d["pct_change_hours"], color=colors, height=0.6)
    ax.axvline(0, color=AXIS, linewidth=1)
    ax.axvline(total, color=INK_2, linewidth=1, linestyle="--")
    ax.text(total, -0.75, f"all companies {total:.0f}%", fontsize=8, color=INK_2, ha="center", va="top")
    lo, hi = min(d["pct_change_hours"].min(), 0), max(d["pct_change_hours"].max(), 0)
    span = hi - lo or 1
    ax.set_xlim(lo - 0.15 * span, hi + 0.15 * span)
    ax.set_ylim(-1.2, len(d) - 0.4)
    for bar, v in zip(bars, d["pct_change_hours"]):
        ax.text(v, bar.get_y() + bar.get_height() / 2, f" {v:.0f}% " if v < 0 else f" +{v:.0f}%",
                va="center", ha="right" if v < 0 else "left", fontsize=9, color=INK)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=INK_2)
    style(ax, f"Change in spill hours, {a} to {b} (like-for-like)",
          "Same overflows in both years, monitors working >= 90% of the time. Blue = fall, orange = rise")
    fig.tight_layout()
    fig.savefig(FIGS / "03_change_like_for_like.png", dpi=160)
    plt.close(fig)


# --------------------------------------------------------------------------
def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    df = load()
    long_term, ea_company = read_ea_reference()

    t = national_trend(df)
    cy = company_year(df)
    rec = reconcile(cy, ea_company)
    lt = league_table(cy)
    wide = match_years(df)
    lfl, lfl_rows = like_for_like(wide)

    t.to_csv(TABLES / "national_trend.csv", index=False)
    cy.to_csv(TABLES / "company_year.csv", index=False)
    lt.to_csv(TABLES / "league_table_2025.csv", index=False)
    lfl.to_csv(TABLES / "like_for_like_2024_2025.csv", index=False)
    lfl_rows.to_csv(TABLES / "like_for_like_overflows.csv", index=False)
    if not rec.empty:
        rec.to_csv(TABLES / "reconciliation_vs_ea.csv", index=False)

    fig_trend(t)
    fig_league(lt)
    fig_change(lfl)
    if long_term is not None:
        print("\n=== EA long-term trend 2016-2025 ===")
        print(long_term.round(1).to_string(index=False))
        long_term.to_csv(TABLES / "long_term_trends_2016_2025.csv", index=False)
        fig_long_term(long_term)

    print(f"\nSaved tables to {TABLES}/ and charts to {FIGS}/")


if __name__ == "__main__":
    main()