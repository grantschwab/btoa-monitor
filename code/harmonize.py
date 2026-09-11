"""Marries StatCan (northbound, into Canada) and BTS (southbound, into the
US) monthly personal-vehicle-passenger counts into one bidirectional view,
for the two Michigan-Ontario crossing pairs:

  - Windsor-Detroit: StatCan GHIB + AMB/DWT  <->  BTS Detroit port (3801)
  - Sarnia-Port Huron: StatCan Sarnia (BWB)   <->  BTS Port Huron port (3802)

Neither side can separate GHIB from AMB/DWT on the Windsor-Detroit US-bound
leg (CBP has no GHIB port code), so that pairing is combined-crossing only.

This is meant to catch bidirectional volume faster than BTOA, which is
bidirectional but reports with a longer, undocumented lag.
"""
from datetime import datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

import statcan_source as sc
import bts_source as bts

HEADER_FILL = PatternFill(start_color="2C3E8C", end_color="2C3E8C", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


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


def _write_pair_sheet(wb, name, northbound, southbound, min_ym="2024-01"):
    ws = wb.create_sheet(name)
    headers = ["Month", "Northbound into Canada (StatCan)", "Southbound into US (BTS)",
               "Combined (both directions)", "Northbound YoY %", "Southbound YoY %",
               "Combined YoY %"]
    ws.append(headers)
    _style_header(ws, len(headers))

    months = sorted(set(northbound) | set(southbound))
    months = [ym for ym in months if ym >= min_ym]
    combined = {ym: northbound.get(ym, 0) + southbound.get(ym, 0)
                for ym in months if ym in northbound and ym in southbound}

    for ym in months:
        n, s = northbound.get(ym), southbound.get(ym)
        c = combined.get(ym)
        ws.append([
            ym,
            int(n) if n is not None else None,
            int(s) if s is not None else None,
            int(c) if c is not None else None,
            _yoy(northbound, ym), _yoy(southbound, ym), _yoy(combined, ym),
        ])
        r = ws.max_row
        for col_idx in (5, 6, 7):
            ws.cell(row=r, column=col_idx).number_format = "0.0%"

    for i, w in enumerate([10, 26, 22, 22, 14, 14, 14], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def build_workbook(path, min_ym="2024-01"):
    sc_monthly, _ = sc.fetch_daily()
    windsor_northbound = {
        ym: sc_monthly[sc.GEO_AMB_DWT][sc.CHAR_TOTAL].get(ym, 0)
            + sc_monthly[sc.GEO_GHIB][sc.CHAR_TOTAL].get(ym, 0)
        for ym in set(sc_monthly[sc.GEO_AMB_DWT][sc.CHAR_TOTAL]) | set(sc_monthly[sc.GEO_GHIB][sc.CHAR_TOTAL])
    }
    sarnia_northbound = dict(sc_monthly[sc.GEO_BWB][sc.CHAR_TOTAL])

    detroit_southbound = bts.fetch_monthly(port_code=bts.PORT_DETROIT, min_date=f"{min_ym}-01")
    porthuron_southbound = bts.fetch_monthly(port_code=bts.PORT_PORT_HURON, min_date=f"{min_ym}-01")

    wb = Workbook()
    wb.remove(wb.active)

    _write_pair_sheet(wb, "Windsor-Detroit", windsor_northbound, detroit_southbound, min_ym)
    _write_pair_sheet(wb, "Sarnia-Port Huron (BWB)", sarnia_northbound, porthuron_southbound, min_ym)

    ws = wb.create_sheet("Methodology")
    ws.column_dimensions["A"].width = 105
    lines = [
        ("Purpose", "Combines StatCan's fast northbound (into Canada) data with BTS's southbound (into the US) data to approximate bidirectional volume faster than waiting on BTOA, which is bidirectional but publishes with a longer, undocumented lag."),
        ("Northbound source", f"Statistics Canada table 24-10-0057 (Frontier Counts), personal-vehicle traveller counts. {sc.TABLE_URL}"),
        ("Southbound source", "BTS Border Crossing/Entry Data (data.bts.gov, resource keg4-3bc2), measure 'Personal Vehicle Passengers', collected by CBP. https://data.bts.gov/Research-and-Statistics/Border-Crossing-Entry-Data/keg4-3bc2"),
        ("Windsor-Detroit pairing", "Northbound = StatCan 'Windsor - Gordie Howe International Bridge' + 'Windsor - other locations' (Ambassador Bridge + Detroit-Windsor Tunnel). Southbound = BTS Detroit port (3801), which CBP reports as Ambassador Bridge + Detroit-Windsor Tunnel + Gordie Howe combined -- CBP has no separate GHIB port code, so GHIB can't be isolated on this side."),
        ("Sarnia-Port Huron pairing", "Northbound = StatCan 'Sarnia' (Blue Water Bridge). Southbound = BTS Port Huron port (3802)."),
        ("Units", "Personal-vehicle passenger counts (people, not vehicles) on both sides -- chosen because it's the closest matching unit between the two sources. Trucks/commercial traffic are NOT included; StatCan tracks those separately (table 24-10-0059) and BTS has a 'Trucks' measure, but they aren't merged here."),
        ("Combined column", "Only populated for months where BOTH sides have data -- BTS typically lags StatCan by several weeks, so the most recent 1-2 months often show a northbound figure with no combined total yet."),
        ("YoY %", "(this month - same month prior year) / prior year."),
        ("Rebuilt", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]
    for i, (k, v) in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=f"{k}: {v}").alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 30

    wb.save(path)
