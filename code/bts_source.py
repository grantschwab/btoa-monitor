"""Fetches BTS Border Crossing/Entry Data (Bureau of Transportation
Statistics, via CBP) for the Detroit port (3801), which covers Ambassador
Bridge + Detroit-Windsor Tunnel + Gordie Howe International Bridge combined
-- CBP does not report a separate GHIB port code, so it can't be split out
on the US side the way it can on the Canadian (StatCan) side.

Southbound only (entering the US). Monthly cadence, roughly ~6 week lag
based on observed history.
"""
import calendar
from datetime import datetime, timezone

import requests

API_URL = "https://data.bts.gov/resource/keg4-3bc2.json"
PORT_DETROIT = "3801"    # Ambassador Bridge + Detroit-Windsor Tunnel + GHIB, combined
PORT_PORT_HURON = "3802"  # Blue Water Bridge
MEASURE = "Personal Vehicle Passengers"


def fetch_monthly(port_code=PORT_DETROIT, min_date="2024-01-01"):
    """Returns {ym: value} for the given port, sorted ascending."""
    params = {
        "$select": "date,value",
        "port_code": port_code,
        "measure": MEASURE,
        "$where": f"date>='{min_date}T00:00:00'",
        "$order": "date",
        "$limit": 1000,
    }
    resp = requests.get(API_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()
    return {r["date"][:7]: float(r["value"]) for r in rows}


def latest_month(port_code=PORT_DETROIT, min_date="2024-01-01"):
    monthly = fetch_monthly(port_code=port_code, min_date=min_date)
    if not monthly:
        return None
    ym = max(monthly.keys())
    y, m = int(ym[:4]), int(ym[5:7])
    return (y, m)
