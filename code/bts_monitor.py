import os
from datetime import datetime, timezone

import bts_source as bts
import harmonize
from common import load_state, save_state, send_email

STATE_FILE = "bts_state.json"
DATA_DIR = "data"
HARMONIZED_XLSX = os.path.join(DATA_DIR, "harmonized_windsor_detroit_monthly.xlsx")

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
REPO_BASE = "https://github.com/grantschwab/btoa-monitor/blob/main"


def build_email(prev_ym, new_ym, force=False):
    prev_str = f"{MONTH_NAMES[prev_ym[1]-1]} {prev_ym[0]}" if prev_ym else "(none — first run)"
    new_str = f"{MONTH_NAMES[new_ym[1]-1]} {new_ym[0]}"
    banner = ""
    if force:
        banner = """<p style="background:#fff3cd;color:#856404;padding:8px 12px;border-radius:4px;margin:0 0 12px 0">
&#9888; This is a manually triggered test run, not a live change detection.
</p>"""
    return f"""<html><body style="font-family:sans-serif;font-size:14px;max-width:640px;margin:0 auto">
<h2 style="color:#2c3e8c;margin-bottom:4px">&#128197; New Month of US (BTS) Border Crossing Data</h2>
<p style="color:#888;margin-top:0">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
{banner}
<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px">
  <tr><td style="padding:4px 10px;color:#666">Previously latest month</td><td style="padding:4px 10px">{prev_str}</td></tr>
  <tr><td style="padding:4px 10px;color:#666">Now latest month</td><td style="padding:4px 10px"><b>{new_str}</b></td></tr>
</table>
<p style="margin-top:20px">
  <a href="{REPO_BASE}/{HARMONIZED_XLSX}">&#128260; Harmonized bidirectional spreadsheet</a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="https://data.bts.gov/Research-and-Statistics/Border-Crossing-Entry-Data/keg4-3bc2">BTS Border Crossing/Entry Data</a>
</p>
<p style="font-size:12px;color:#888;margin-top:24px">
  Detected at the Detroit port (Ambassador Bridge + Detroit-Windsor Tunnel +
  Gordie Howe International Bridge, combined -- CBP has no separate GHIB
  port code on this side).
</p>
</body></html>"""


def main():
    state = load_state(STATE_FILE)
    force = os.environ.get("FORCE_EMAIL", "").lower() == "true"
    if force:
        print("*** FORCE MODE — will email regardless of state ***")

    print(f"[{datetime.now(timezone.utc).isoformat()[:19]}Z] Checking BTS Detroit port data...")
    new_ym = bts.latest_month(port_code=bts.PORT_DETROIT)
    if new_ym is None:
        print("  Could not determine latest month.")
        return

    prev_ym = tuple(state["latest_ym"]) if state.get("latest_ym") else None
    print(f"  Latest month: {MONTH_NAMES[new_ym[1]-1]} {new_ym[0]} (previously: {prev_ym})")

    new_month_available = prev_ym is None or new_ym > prev_ym

    if new_month_available or force:
        os.makedirs(DATA_DIR, exist_ok=True)
        print("  Rebuilding harmonized bidirectional workbook...")
        harmonize.build_workbook(HARMONIZED_XLSX)

        html = build_email(prev_ym, new_ym, force=force)
        send_email("[BTS Alert] New month of US border crossing data available", html, force=force)
    else:
        print("  No new month. Not emailing.")

    if new_month_available:
        state["latest_ym"] = list(new_ym)
        state["latest_ym_detected_at"] = datetime.now(timezone.utc).isoformat()
        save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
