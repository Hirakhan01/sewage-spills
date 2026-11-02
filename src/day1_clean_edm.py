"""
Day 1 - Combine the Environment Agency EDM storm overflow annual returns
(2020-2025) into one tidy table: one row per overflow, per year.

Usage
-----
1. Put the downloaded zips (or the .xlsx files inside them) in data/raw/
2. Run:  python day1_clean_edm.py data/raw data/clean

What it produces (in data/clean/)
---------------------------------
- edm_annual_2020_2025.csv     the combined, cleaned table
- column_mapping_report.csv    which original column became which clean column,
                               for every file and sheet (check this!)
- skipped_sheets.csv           sheets that were ignored and why

Why it's written defensively
----------------------------
The EA's column names change slightly from year to year, the header isn't
always on the first row, and each workbook mixes data sheets with README /
summary sheets. So instead of hard-coding column names, the script finds the
header row and matches columns by keywords. Always read the mapping report.
"""

import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# 1. Column matching rules
#    Each clean column has keyword groups. A source column matches if ALL
#    words in ANY group appear in its (lower-cased) name, and NONE of the
#    "exclude" words appear. First match wins, so order matters.
# --------------------------------------------------------------------------
COLUMN_RULES = {
    "water_company":    {"any": [["water", "company"], ["wasc"]], "exclude": ["permit", "operational"]},
    "site_name":        {"any": [["site", "name", "consent"], ["site", "name", "ea"], ["site", "name"]],
                         "exclude": ["operational", "wasc"]},
    "site_name_wasc":   {"any": [["site", "name", "operational"], ["site", "name", "wasc"]], "exclude": []},
    "permit_ref":       {"any": [["permit", "ref"], ["consent", "ref"]], "exclude": ["activity"]},
    "activity_ref":     {"any": [["activity", "ref"]], "exclude": []},
    "asset_type":       {"any": [["asset", "type"]], "exclude": []},
    "outlet_ngr":       {"any": [["outlet", "ngr"], ["discharge", "ngr"], ["ngr"], ["grid", "ref"]],
                         "exclude": ["treatment", "wwtw"]},
    "receiving_water":  {"any": [["receiving", "water"], ["receiving", "environment"]], "exclude": []},
    "wfd_waterbody_id": {"any": [["wfd", "waterbody"], ["waterbody", "id"]], "exclude": []},
    # Duration is matched BEFORE count: the EA's duration header also mentions
    # "spills" and "count method", so it would otherwise be mistaken for the count.
    "spill_hours":      {"any": [["total", "duration"], ["duration", "hr"], ["duration", "hour"]],
                         "exclude": ["average", "previous", "long term", "excluding", "%"]},
    "spill_count":      {"any": [["counted", "spill"], ["spill", "count"], ["number", "spill"]],
                         "exclude": ["duration", "hrs", "hour", "average", "previous", "long term",
                                     "excluding", "%"]},
    "edm_operation_pct":{"any": [["edm", "operation"], ["edm", "operational"], ["%", "reporting", "period"]],
                         "exclude": ["commission", "date", "reason", "explanation"]},
    "edm_low_reason":   {"any": [["reason", "edm"], ["explanation", "edm"], ["reason", "operational"],
                                 ["explanation", "90"]], "exclude": []},
    "high_spill_reason":{"any": [["high", "spill"], ["reason", "spill"], ["explanation", "spill"]], "exclude": []},
}

SKIP_SHEET_WORDS = ["readme", "read me", "guide", "summary", "contents", "notes",
                    "key", "trend", "glossary", "definitions", "index"]

NUMERIC_COLS = ["spill_count", "spill_hours", "edm_operation_pct"]


def norm(text) -> str:
    """Lower-case, single-spaced version of a header for keyword matching."""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def match_columns(columns):
    """Return {clean_name: original_column} using COLUMN_RULES."""
    mapping, used = {}, set()
    for clean, rule in COLUMN_RULES.items():
        for col in columns:
            if col in used:
                continue
            name = norm(col)
            if any(x in name for x in rule["exclude"]):
                continue
            if any(all(w in name for w in group) for group in rule["any"]):
                mapping[clean] = col
                used.add(col)
                break
    return mapping


def find_header_row(raw: pd.DataFrame, max_scan: int = 25):
    """The header row is the first row that mentions both a site and a spill/duration."""
    for i in range(min(max_scan, len(raw))):
        cells = " | ".join(norm(v) for v in raw.iloc[i].dropna().tolist())
        if "site" in cells and ("spill" in cells or "duration" in cells):
            return i
    return None


# --------------------------------------------------------------------------
# 2. OS grid reference -> easting / northing (so you can map it later)
# --------------------------------------------------------------------------
def ngr_to_en(ref):
    """Convert e.g. 'SE 30245 33780' to (430245, 433780). Returns (None, None) if invalid."""
    if not isinstance(ref, str):
        return None, None
    ref = re.sub(r"\s+", "", ref).upper()
    m = re.fullmatch(r"([A-HJ-Z]{2})(\d{2,10})", ref)
    if not m or len(m.group(2)) % 2:
        return None, None
    letters, digits = m.groups()
    l1, l2 = ord(letters[0]) - 65, ord(letters[1]) - 65
    l1 -= l1 > 7  # the grid skips the letter I
    l2 -= l2 > 7
    e100 = ((l1 - 2) % 5) * 5 + (l2 % 5)
    n100 = (19 - (l1 // 5) * 5) - (l2 // 5)
    half = len(digits) // 2
    e = int(digits[:half].ljust(5, "0"))
    n = int(digits[half:].ljust(5, "0"))
    return e100 * 100000 + e, n100 * 100000 + n


# --------------------------------------------------------------------------
# 3. Reading the files
# --------------------------------------------------------------------------
def iter_workbooks(raw_dir: Path):
    """Yield (source_label, year, file-like) for every annual-return workbook."""
    for path in sorted(raw_dir.iterdir()):
        name = path.name
        if re.search(r"long|trend", name, re.I):
            continue  # long-term trends file is used on Day 2, not here
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as z:
                for member in z.namelist():
                    if member.lower().endswith((".xlsx", ".xls")) and not re.search(r"readme|guide|trend", member, re.I):
                        year = re.search(r"20\d{2}", member) or re.search(r"20\d{2}", name)
                        yield f"{name}/{member}", int(year.group()) if year else None, io.BytesIO(z.read(member))
        elif path.suffix.lower() in (".xlsx", ".xls"):
            year = re.search(r"20\d{2}", name)
            yield name, int(year.group()) if year else None, path


def process_workbook(label, year, fileobj, mapping_log, skipped_log):
    frames = []
    sheets = pd.read_excel(fileobj, sheet_name=None, header=None, dtype=object)
    for sheet_name, raw in sheets.items():
        if any(w in sheet_name.lower() for w in SKIP_SHEET_WORDS):
            skipped_log.append({"file": label, "sheet": sheet_name, "reason": "looks like README/summary"})
            continue
        hdr = find_header_row(raw)
        if hdr is None:
            skipped_log.append({"file": label, "sheet": sheet_name, "reason": "no header row with site + spill found"})
            continue

        df = raw.iloc[hdr + 1:].copy()
        df.columns = [str(c).strip() for c in raw.iloc[hdr]]
        df = df.dropna(how="all")
        mapping = match_columns(df.columns)

        for clean, original in mapping.items():
            mapping_log.append({"file": label, "sheet": sheet_name, "year": year,
                                "clean_column": clean, "original_column": original})
        missing = [c for c in ("site_name", "spill_count", "spill_hours") if c not in mapping]
        if missing:
            skipped_log.append({"file": label, "sheet": sheet_name,
                                "reason": f"missing key columns: {missing}"})
            continue

        out = df[list(mapping.values())].rename(columns={v: k for k, v in mapping.items()})
        out.insert(0, "year", year)
        if "water_company" not in out:
            out.insert(1, "water_company", sheet_name)
        out["source_file"] = label
        out["source_sheet"] = sheet_name
        frames.append(out)
    return frames


# --------------------------------------------------------------------------
# 4. Cleaning
# --------------------------------------------------------------------------
def clean(df: pd.DataFrame) -> pd.DataFrame:
    # Text tidy-up
    for col in df.columns:
        if df[col].dtype == object and col not in NUMERIC_COLS:
            df[col] = df[col].astype("string").str.strip().replace({"": pd.NA, "nan": pd.NA})

    # Numbers: remove commas, turn things like "N/A" into blanks
    for col in NUMERIC_COLS:
        if col in df:
            df[col] = pd.to_numeric(df[col].astype("string").str.replace(",", ""), errors="coerce")

    # EDM operation is sometimes stored as 0-1 rather than 0-100
    if "edm_operation_pct" in df:
        frac = df.groupby(["source_file", "source_sheet"])["edm_operation_pct"].transform("max") <= 1
        df.loc[frac, "edm_operation_pct"] = df.loc[frac, "edm_operation_pct"] * 100

    # Drop footer / blank rows that have no site at all
    df = df[df["site_name"].notna() & ~df["site_name"].str.match(r"(?i)^\s*(grand )?totals?\b")].copy()

    # Consistent company names across years
    df["water_company"] = (df["water_company"].str.replace(r"\s+", " ", regex=True)
                           .str.replace(r"(?i)\b(plc|ltd|limited|services)\b", "", regex=True)
                           .str.strip().str.title())

    # Data-quality flags (these become a dashboard page later)
    df["flag_no_spill_data"] = df["spill_count"].isna() & df["spill_hours"].isna()
    if "edm_operation_pct" in df:
        df["flag_edm_below_90pct"] = df["edm_operation_pct"] < 90

    # Grid reference -> easting/northing for mapping
    if "outlet_ngr" in df:
        en = df["outlet_ngr"].map(ngr_to_en)
        df["easting"] = en.map(lambda t: t[0])
        df["northing"] = en.map(lambda t: t[1])

    # A stable ID for joining the same overflow across years
    key_parts = [c for c in ("permit_ref", "activity_ref") if c in df]
    if key_parts:
        df["overflow_id"] = df[key_parts].fillna("").agg("|".join, axis=1).str.upper()

    return df


def quality_report(df: pd.DataFrame):
    print("\n=== Rows per company per year ===")
    print(df.pivot_table(index="water_company", columns="year", values="site_name",
                         aggfunc="count", fill_value=0).to_string())
    print("\n=== Totals per year (compare with the EA's published headline figures) ===")
    agg = {"spill_count": "sum", "spill_hours": "sum", "flag_no_spill_data": "sum"}
    if "flag_edm_below_90pct" in df:
        agg["flag_edm_below_90pct"] = "sum"
    print(df.groupby("year").agg(agg).round(0).to_string())
    print("\n=== Missing values per column (%) ===")
    print((df.isna().mean() * 100).round(1).sort_values(ascending=False).to_string())


def main(raw_dir="data/raw", out_dir="data/clean"):
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames, mapping_log, skipped_log = [], [], []
    for label, year, fileobj in iter_workbooks(raw_dir):
        print(f"Reading {label} (year={year})")
        frames += process_workbook(label, year, fileobj, mapping_log, skipped_log)

    if not frames:
        sys.exit("No data sheets found. Check data/raw and skipped_sheets.csv.")

    df = clean(pd.concat(frames, ignore_index=True))
    df.to_csv(out_dir / "edm_annual_2020_2025.csv", index=False)
    pd.DataFrame(mapping_log).to_csv(out_dir / "column_mapping_report.csv", index=False)
    pd.DataFrame(skipped_log).to_csv(out_dir / "skipped_sheets.csv", index=False)

    quality_report(df)
    print(f"\nSaved {len(df):,} rows to {out_dir / 'edm_annual_2020_2025.csv'}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
