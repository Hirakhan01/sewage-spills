"""
Day 1 check - shows what's inside the 2024/2025 workbooks so the cleaning
script can be fixed precisely.

Run from the project folder:
    python src/check_day1.py data/raw data/clean
"""
import sys
import zipfile
import io
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from day1_clean_edm import find_header_row, match_columns  # noqa: E402

raw_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
clean_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "data/clean")

# ---------------------------------------------------------------- 1. raw files
for year in (2023, 2024, 2025):
    zips = [p for p in raw_dir.glob(f"*{year}*.zip")]
    if not zips:
        print(f"\n##### {year}: no zip found")
        continue
    with zipfile.ZipFile(zips[0]) as z:
        members = [m for m in z.namelist()
                   if m.lower().endswith(".xlsx") and "summary" not in m.lower()]
        for member in members:
            print(f"\n##### {year}: {member}")
            sheets = pd.read_excel(io.BytesIO(z.read(member)), sheet_name=None,

                                   header=None, dtype=object)
            for name, raw in sheets.items():
                hdr = find_header_row(raw)
                print(f"\n  SHEET '{name}'  rows={len(raw)}  header_row={hdr}")
                if hdr is None:
                    continue
                headers = [str(c).strip() for c in raw.iloc[hdr]]
                mapping = match_columns(headers)
                for clean in ("water_company", "spill_hours", "spill_count"):
                    print(f"    {clean:14s} <- {mapping.get(clean)!r}")
                if "spill_hours" in mapping:
                    idx = headers.index(mapping["spill_hours"])
                    vals = raw.iloc[hdr + 1:, idx].dropna().head(6).tolist()
                    print("    sample spill_hours values:")
                    for v in vals:
                        print(f"      {v!r:40s} type={type(v).__name__}")
                if year == 2025 and name == list(sheets)[0]:
                    print("    all headers in this sheet:")
                    for h in headers:
                        print(f"      - {h}")

# ---------------------------------------------------------------- 2. clean file
csv = clean_dir / "edm_annual_2020_2025.csv"
if csv.exists():
    df = pd.read_csv(csv, low_memory=False)
    print("\n##### Rows per source sheet, 2025")
    print(df[df.year == 2025].groupby("source_sheet").size().to_string())
    print("\n##### Spill hours by company, 2020 (checking for missing companies)")
    print(df[df.year == 2020].groupby("water_company")["spill_hours"]
          .agg(total="sum", rows_missing=lambda s: s.isna().sum()).round(0).to_string())


