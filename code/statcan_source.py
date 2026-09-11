"""Fetches and aggregates StatCan's Frontier Counts data (table 24-10-0057)
for the Windsor-area land crossings: Gordie Howe Int'l Bridge, Ambassador
Bridge + Detroit-Windsor Tunnel (bundled together in this table, no further
split available), and the Blue Water Bridge (Sarnia).
"""
import calendar
from datetime import datetime, timezone

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

WDS_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods"
PRODUCT_ID = 24100057
TABLE_URL = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2410005701"

# Geography member IDs (of 135 total in this table)
GEO_GHIB = "135"
GEO_AMB_DWT = "66"
GEO_BWB = "62"

GEO_LABELS = {
    GEO_GHIB: "Gordie Howe International Bridge",
    GEO_AMB_DWT: "Ambassador Bridge + Detroit-Windsor Tunnel (combined)",
    GEO_BWB: "Blue Water Bridge (Sarnia)",
}
GEO_SHEET_NAMES = {GEO_GHIB: "GHIB", GEO_AMB_DWT: "AMB+DWT", GEO_BWB: "BWB (Sarnia)"}

# Traveller characteristic member IDs
CHAR_TOTAL = "4"
CHAR_AMERICANS = "1"
CHAR_CANADIANS = "3"

# Vehicle licence plate = 65 ("Vehicles entering Canada", i.e. all plates),
# Vehicle type = 4 ("Vehicles" total), Traveller type = 3 ("Travellers" total)
COORD_SUFFIX = "65.4.{char}.3.0.0.0.0.0"


def _coord(geo, char):
    return f"{geo}.{COORD_SUFFIX.format(char=char)}"


def fetch_daily(geo_ids=(GEO_GHIB, GEO_AMB_DWT, GEO_BWB),
                 char_ids=(CHAR_TOTAL, CHAR_CANADIANS, CHAR_AMERICANS), latest_n=1200):
    """Returns {geo: {char: {ym: total}}} aggregated from daily to monthly."""
    payload = [
        {"productId": PRODUCT_ID, "coordinate": _coord(g, c), "latestN": latest_n}
        for g in geo_ids for c in char_ids
    ]
    resp = requests.post(WDS_URL, json=payload, timeout=60)
    resp.raise_for_status()
    results = resp.json()

    monthly = {g: {c: {} for c in char_ids} for g in geo_ids}
    days_reported = {g: {} for g in geo_ids}

    for entry in results:
        obj = entry["object"]
        geo, char = obj["coordinate"].split(".")[0], obj["coordinate"].split(".")[3]
        for p in obj["vectorDataPoint"]:
            ym = p["refPer"][:7]
            v = p["value"]
            if v is None:
                continue
            monthly[geo][char][ym] = monthly[geo][char].get(ym, 0) + v
            if char == CHAR_TOTAL:
                days_reported[geo][ym] = days_reported[geo].get(ym, 0) + 1

    return monthly, days_reported


def expected_days(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return calendar.monthrange(y, m)[1]


def latest_complete_month(geo_ids=(GEO_AMB_DWT, GEO_BWB)):
    """Bellwether check: latest (year, month) tuple with a full calendar
    month reported, using crossings that have run since before 2024 (skips
    GHIB, which didn't exist until Jul 2026 and would always look partial
    for its first month)."""
    monthly, days_reported = fetch_daily(geo_ids=geo_ids, char_ids=(CHAR_TOTAL,), latest_n=45)
    best = None
    for geo in geo_ids:
        for ym, days in days_reported[geo].items():
            if days >= expected_days(ym):
                y, m = int(ym[:4]), int(ym[5:7])
                if best is None or (y, m) > best:
                    best = (y, m)
    return best


# ---------------------------------------------------------------------------
# Workbook building
# ---------------------------------------------------------------------------

HEADER_FILL = PatternFill(start_color="2C3E8C", end_color="2C3E8C", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
PARTIAL_FILL = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")


def _yoy(store, ym):
    y, m = int(ym[:4]), int(ym[5:7])
    prev_ym = f"{y-1}-{m:02d}"
    cur, prev = store.get(ym), store.get(prev_ym)
    if not cur or not prev:
        return None
    return (cur - prev) / prev


def _style_header(ws, n_cols):
    for col in range(1, n_cols + 1):
        c = ws.cell(row=1, column=col)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center")


def build_workbook(path, min_ym="2024-01"):
    monthly, days_reported = fetch_daily()
    geo_order = [GEO_GHIB, GEO_AMB_DWT, GEO_BWB]

    wb = Workbook()
    wb.remove(wb.active)

    # Combined sheet first
    ws = wb.create_sheet("All Windsor-area combined", 0)
    headers = ["Month", "Total trips", "Trips by Canadians", "Trips by Americans",
               "Total YoY %", "Canadians YoY %", "Americans YoY %", "Includes GHIB?"]
    ws.append(headers)
    _style_header(ws, len(headers))

    all_months = sorted(set().union(*[monthly[g][CHAR_TOTAL].keys() for g in geo_order]))
    all_months = [ym for ym in all_months if ym >= min_ym]

    combined = {"total": {}, "can": {}, "us": {}}
    for ym in all_months:
        combined["total"][ym] = sum(monthly[g][CHAR_TOTAL].get(ym, 0) for g in geo_order)
        combined["can"][ym] = sum(monthly[g][CHAR_CANADIANS].get(ym, 0) for g in geo_order)
        combined["us"][ym] = sum(monthly[g][CHAR_AMERICANS].get(ym, 0) for g in geo_order)

    for ym in all_months:
        includes_ghib = ym in monthly[GEO_GHIB][CHAR_TOTAL]
        ws.append([
            ym, int(combined["total"][ym]), int(combined["can"][ym]), int(combined["us"][ym]),
            _yoy(combined["total"], ym), _yoy(combined["can"], ym), _yoy(combined["us"], ym),
            "Yes" if includes_ghib else "No (opened Jul 27, 2026)",
        ])
        r = ws.max_row
        for col_idx in (5, 6, 7):
            ws.cell(row=r, column=col_idx).number_format = "0.0%"
    for i, w in enumerate([10, 13, 18, 18, 12, 15, 15, 24], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    # One sheet per crossing
    for geo in geo_order:
        ws = wb.create_sheet(GEO_SHEET_NAMES[geo])
        headers = ["Month", "Total trips", "Trips by Canadians", "Trips by Americans",
                   "Total YoY %", "Canadians YoY %", "Americans YoY %",
                   "Days reported", "Partial month?"]
        ws.append(headers)
        _style_header(ws, len(headers))

        for ym in sorted(monthly[geo][CHAR_TOTAL].keys()):
            if ym < min_ym:
                continue
            total = monthly[geo][CHAR_TOTAL].get(ym)
            can = monthly[geo][CHAR_CANADIANS].get(ym)
            us = monthly[geo][CHAR_AMERICANS].get(ym)
            days_rep = days_reported[geo].get(ym, 0)
            is_partial = days_rep < expected_days(ym)

            ws.append([
                ym, int(total) if total is not None else None,
                int(can) if can is not None else None,
                int(us) if us is not None else None,
                _yoy(monthly[geo][CHAR_TOTAL], ym),
                _yoy(monthly[geo][CHAR_CANADIANS], ym),
                _yoy(monthly[geo][CHAR_AMERICANS], ym),
                days_rep, "PARTIAL" if is_partial else "",
            ])
            r = ws.max_row
            for col_idx in (5, 6, 7):
                ws.cell(row=r, column=col_idx).number_format = "0.0%"
            if is_partial:
                for col_idx in range(1, len(headers) + 1):
                    ws.cell(row=r, column=col_idx).fill = PARTIAL_FILL

        for i, w in enumerate([10, 13, 18, 18, 12, 15, 15, 14, 13], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"

    # Methodology
    ws = wb.create_sheet("Methodology")
    ws.column_dimensions["A"].width = 105
    lines = [
        ("Source", "Statistics Canada, Frontier Counts / Leading indicator of international arrivals to Canada"),
        ("Table", "24-10-0057-01 — International visitors entering or returning to Canada by land, by vehicle type, vehicle licence plate and traveller type"),
        ("Table URL", TABLE_URL),
        ("Method", "Pulled via StatCan Web Data Service API (getDataFromCubePidCoordAndLatestNPeriods), daily series aggregated to calendar-month totals."),
        ("Geography", "This table has 135 geography members at individual land-crossing granularity. Windsor-area members used: 'Windsor - Gordie Howe International Bridge', 'Windsor - other locations' (bundles Ambassador Bridge + Detroit-Windsor Tunnel, no further split available), and 'Sarnia' (Blue Water Bridge)."),
        ("Traveller categories", "'Total trips' = all traveller types. 'Trips by Canadians' = Canadian residents returning to Canada. 'Trips by Americans' = US residents entering Canada. Overseas-resident visitors are in Total but not broken out here."),
        ("Vehicle scope", "Automobile/personal-vehicle traveller counts only. Commercial trucks are a separate StatCan table (24-10-0059) and are NOT included."),
        ("GHIB history", "Opened July 27, 2026 — no data before that date. July 2026 is a partial month (5 days)."),
        ("Partial months", "Flagged PARTIAL when fewer days were reported than the calendar month contains."),
        ("YoY %", "(this month − same month prior year) / prior year. Blank when no prior-year data exists."),
        ("Rebuilt", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]
    for i, (k, v) in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=f"{k}: {v}").alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 30

    wb.save(path)
