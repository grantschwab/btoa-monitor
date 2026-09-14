"""Fetches and parses BTOA's traffic spreadsheet for Ambassador Bridge,
Blue Water Bridge, and the Detroit-Windsor Tunnel -- bidirectional,
per-bridge monthly counts, broken out by vehicle category.
"""
import io
from datetime import datetime, timezone

import requests
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

BTOA_URL = "https://www.bridgeandtunneloperators.org/images/BTOA%20Traffic%202026.xlsx"
BTOA_PAGE_URL = "https://www.bridgeandtunneloperators.org/index.php/traffic"

BRIDGE_ORDER = ["AMB", "BWB", "DWT", "GHIB"]
BRIDGE_LABELS = {
    "AMB": "Ambassador Bridge (Detroit)",
    "BWB": "Blue Water Bridge (Port Huron)",
    "DWT": "Detroit-Windsor Tunnel",
    "GHIB": "Gordie Howe International Bridge",
}

# (source row classification, output sheet name)
ANALYSIS_SHEETS = [
    ("TOTAL", "Overall traffic"),
    ("Passenger Cars", "Car traffic"),
    ("Trucks", "Truck traffic"),
]
# (source row classification, chart Category label) -- Total vehicles listed
# first per the requested chart-tab layout.
CHART_CATEGORIES = [
    ("TOTAL", "Total vehicles"),
    ("Passenger Cars", "Passenger cars"),
    ("Trucks", "Trucks"),
]

# Same ordering, shorter labels, for the per-month bar-chart snapshot tabs.
SNAPSHOT_CATEGORIES = [
    ("TOTAL", "Total"),
    ("Passenger Cars", "Cars"),
    ("Trucks", "Trucks"),
]
# First month to get its own bar-chart snapshot tab.
SNAPSHOT_START_YM = (2026, 8)

# GHIB opened Jul 27, 2026. The source sheet zero-pads years before it
# existed (e.g. 2025) rather than leaving them blank -- and inconsistently
# so, with some classification rows None and others explicit 0 for the same
# year. Treat anything before opening as not reported, full stop.
GHIB_OPENED_YM = (2026, 7)

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

HEADER_FILL = PatternFill(start_color="2C3E8C", end_color="2C3E8C", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


# ---------------------------------------------------------------------------
# Fetch / detect
# ---------------------------------------------------------------------------

def fetch_bytes():
    resp = requests.get(BTOA_URL, timeout=120)
    resp.raise_for_status()
    return resp.content


def head_signature():
    """BTOA's server sends no ETag header, so we key off Last-Modified plus
    Content-Length as a fallback signal (some static hosts vary Content-Length
    without touching Last-Modified on a re-save)."""
    head = requests.head(BTOA_URL, timeout=30)
    head.raise_for_status()
    last_modified = head.headers.get("last-modified", "")
    content_length = head.headers.get("content-length", "")
    print(f"  Last-Modified : {last_modified}")
    print(f"  Content-Length: {content_length}")
    return f"{last_modified}|{content_length}"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_bridge_monthly(xlsx_bytes, sheet_name):
    """Returns {(year, month): {classification: value}} for one bridge sheet.
    Row layout: col0=Year, col2=Vehicle Classification, col4:16=Jan..Dec
    (raw, non-cumulative monthly totals)."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb[sheet_name]

    data = {}
    for row in ws.iter_rows(min_row=10, values_only=True):
        if len(row) < 16:
            continue
        year, classification, months = row[0], row[2], row[4:16]
        if not isinstance(year, int) or classification not in (
            "Passenger Cars", "Trucks", "Buses & Misc.", "TOTAL"
        ):
            continue
        for i, v in enumerate(months):
            if v is None:
                continue
            # Some years appear twice in the sheet with identical values
            # (a formatting quirk, not a data conflict) -- last write wins,
            # harmlessly, since the values match.
            data.setdefault((year, i + 1), {})[classification] = v

    if sheet_name == "GHIB":
        data = {ym: v for ym, v in data.items() if ym >= GHIB_OPENED_YM}

    return data


def parse_all_bridges(xlsx_bytes):
    return {b: parse_bridge_monthly(xlsx_bytes, b) for b in BRIDGE_ORDER}


def latest_reported_month(xlsx_bytes):
    """(year, month) of the most recent month with a real TOTAL for AMB --
    AMB, BWB, and DWT have always advanced together historically, so AMB is
    a reliable stand-in for "a new month landed" across all three."""
    monthly = parse_bridge_monthly(xlsx_bytes, "AMB")
    totals = {ym: v.get("TOTAL") for ym, v in monthly.items() if v.get("TOTAL")}
    if not totals:
        return None
    return max(totals.keys())


# ---------------------------------------------------------------------------
# Workbook building
# ---------------------------------------------------------------------------

def _style_header(ws, n_cols):
    for col in range(1, n_cols + 1):
        c = ws.cell(row=1, column=col)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center")


def _yoy(store, ym):
    y, m = ym
    cur, prev = store.get(ym), store.get((y - 1, m))
    if not cur or not prev:
        return None
    return (cur - prev) / prev


def build_workbook(xlsx_bytes, path, min_year=2019):
    bridges = parse_all_bridges(xlsx_bytes)

    # The source sheet zero-pads months later in the current year that
    # haven't been reported yet (rather than leaving them blank), so cap at
    # the actual latest reported month to avoid treating those as real
    # zero-traffic months.
    cutoff = latest_reported_month(xlsx_bytes)

    all_months = sorted(set().union(*[set(bridges[b].keys()) for b in BRIDGE_ORDER]))
    display_months = [ym for ym in all_months if ym[0] >= min_year and (cutoff is None or ym <= cutoff)]

    wb = Workbook()
    wb.remove(wb.active)

    # --- Chart Data (long format), first tab ---
    ws = wb.create_sheet("Chart Data", 0)
    headers = ["Month_Year"] + [BRIDGE_LABELS[b] for b in BRIDGE_ORDER] + ["Category"]
    ws.append(headers)
    _style_header(ws, len(headers))
    for ym in display_months:
        y, m = ym
        month_label = f"{MONTH_NAMES[m-1]} {y}"
        for classification, category_label in CHART_CATEGORIES:
            row = [month_label]
            for b in BRIDGE_ORDER:
                v = bridges[b].get(ym, {}).get(classification)
                row.append(int(v) if v is not None else None)
            row.append(category_label)
            ws.append(row)
    for i, w in enumerate([16] + [24] * len(BRIDGE_ORDER) + [16], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    # --- Overall / Car / Truck traffic analysis sheets ---
    for classification, sheet_name in ANALYSIS_SHEETS:
        ws = wb.create_sheet(sheet_name)
        headers = (["Month"] + [BRIDGE_LABELS[b] for b in BRIDGE_ORDER]
                   + [f"{BRIDGE_LABELS[b]} YoY %" for b in BRIDGE_ORDER])
        ws.append(headers)
        _style_header(ws, len(headers))

        series = {
            b: {ym: v.get(classification) for ym, v in bridges[b].items() if classification in v}
            for b in BRIDGE_ORDER
        }

        for ym in display_months:
            y, m = ym
            row = [f"{MONTH_NAMES[m-1]} {y}"]
            for b in BRIDGE_ORDER:
                v = series[b].get(ym)
                row.append(int(v) if v is not None else None)
            for b in BRIDGE_ORDER:
                row.append(_yoy(series[b], ym))
            ws.append(row)
            r = ws.max_row
            for col_idx in range(5, 5 + len(BRIDGE_ORDER)):
                ws.cell(row=r, column=col_idx).number_format = "0.0%"

        widths = [16] + [24] * len(BRIDGE_ORDER) + [16] * len(BRIDGE_ORDER)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"

    # --- Per-month bar-chart snapshot tabs (this month vs. same month last
    # year), one tab per month from SNAPSHOT_START_YM through the latest
    # reported month. Rebuilt from source each time, so these stay correct
    # and a new tab simply appears once a new month clears the cutoff. ---
    snapshot_months = [
        ym for ym in display_months
        if ym >= SNAPSHOT_START_YM and (cutoff is None or ym <= cutoff)
    ]
    for ym in snapshot_months:
        y, m = ym
        prev_y = y - 1
        sheet_name = f"{MONTH_NAMES[m-1]} {y}"
        ws = wb.create_sheet(sheet_name)
        headers = ["crossing", f"month_{prev_y}", f"month_{y}", "pct_change", "category"]
        ws.append(headers)
        _style_header(ws, len(headers))

        for classification, category_label in SNAPSHOT_CATEGORIES:
            for b in BRIDGE_ORDER:
                cur = bridges[b].get((y, m), {}).get(classification)
                prev = bridges[b].get((prev_y, m), {}).get(classification)
                pct = (cur - prev) / prev if (cur is not None and prev) else None
                ws.append([
                    BRIDGE_LABELS[b],
                    int(prev) if prev is not None else None,
                    int(cur) if cur is not None else None,
                    pct,
                    category_label,
                ])
                ws.cell(row=ws.max_row, column=4).number_format = "0.0%"

        for i, w in enumerate([28, 14, 14, 12, 12], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"

    # --- Methodology ---
    ws = wb.create_sheet("Methodology")
    ws.column_dimensions["A"].width = 105
    lines = [
        ("Source", "Bridge and Tunnel Operators Association (BTOA)"),
        ("Source file", BTOA_URL),
        ("Source page", BTOA_PAGE_URL),
        ("Coverage", "Ambassador Bridge, Blue Water Bridge, Detroit-Windsor Tunnel, Gordie Howe International Bridge -- bidirectional (both directions combined), operator-reported. GHIB opened July 27, 2026, so its columns are blank before then and partial for its first (July 2026) month."),
        ("Vehicle categories", "'Overall traffic' = TOTAL row (Passenger Cars + Trucks + Buses & Misc.). 'Car traffic' = Passenger Cars. 'Truck traffic' = Trucks. Buses & Misc. is in the source but not broken out in its own tab here."),
        ("Chart Data tab", "Long format for charting: one row per month per category (Total vehicles, Passenger cars, Trucks, in that order), with each bridge as a column. Matches the layout used for the existing chart."),
        ("Monthly snapshot tabs", f"One tab per month from {MONTH_NAMES[SNAPSHOT_START_YM[1]-1]} {SNAPSHOT_START_YM[0]} onward (e.g. 'August 2026'), formatted for a bar chart: crossing, this month vs. same month prior year, pct_change, category (Total/Cars/Trucks). A new tab appears automatically once that month is reported."),
        ("Date range shown", f"{min_year}-present. Underlying source data goes back further (to 2006) and is used internally to compute YoY % for {min_year}, but only {min_year}+ rows are shown."),
        ("YoY %", "(this month - same month prior year) / prior year."),
        ("Rebuilt", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]
    for i, (k, v) in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=f"{k}: {v}").alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 30

    wb.save(path)
