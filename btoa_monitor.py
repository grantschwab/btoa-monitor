import os
from datetime import datetime, timezone

import btoa_source as bt
from common import load_state, save_state, send_email

STATE_FILE = "state.json"
DATA_DIR = "data"
ANALYSIS_XLSX = os.path.join(DATA_DIR, "btoa_traffic_analysis.xlsx")
REPO_BASE = "https://github.com/grantschwab/btoa-monitor/blob/main"


def build_email(prev_ym, new_ym, force=False):
    prev_str = f"{bt.MONTH_NAMES[prev_ym[1] - 1]} {prev_ym[0]}" if prev_ym else "(none — first run)"
    new_str = f"{bt.MONTH_NAMES[new_ym[1] - 1]} {new_ym[0]}"
    banner = ""
    if force:
        banner = """<p style="background:#fff3cd;color:#856404;padding:8px 12px;border-radius:4px;margin:0 0 12px 0">
&#9888; This is a manually triggered test run, not a live change detection.
</p>"""
    return f"""<html><body style="font-family:sans-serif;font-size:14px;max-width:640px;margin:0 auto">
<h2 style="color:#2c3e8c;margin-bottom:4px">&#128197; New Month of BTOA Traffic Data</h2>
<p style="color:#888;margin-top:0">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
{banner}
<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px">
  <tr><td style="padding:4px 10px;color:#666">Previously latest reported month</td><td style="padding:4px 10px">{prev_str}</td></tr>
  <tr><td style="padding:4px 10px;color:#666">Now latest reported month</td><td style="padding:4px 10px"><b>{new_str}</b></td></tr>
</table>
<p style="margin-top:20px">
  <a href="{REPO_BASE}/{ANALYSIS_XLSX}">&#128202; Updated traffic analysis spreadsheet</a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="{bt.BTOA_URL}">&#11015; Download the raw BTOA file</a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="{bt.BTOA_PAGE_URL}">BTOA Traffic Data page</a>
</p>
<p style="font-size:12px;color:#888;margin-top:24px">
  Detected from the AMB sheet's monthly TOTAL row. AMB, BWB, and DWT have
  historically advanced together, so this is treated as a stand-in for all
  Detroit-area bridges/tunnel, but worth a quick check on first use.
</p>
</body></html>"""


def main():
    state = load_state(STATE_FILE)
    force = os.environ.get("FORCE_EMAIL", "").lower() == "true"
    if force:
        print("*** FORCE MODE — will email regardless of state ***")

    print(f"[{datetime.now(timezone.utc).isoformat()[:19]}Z] Checking BTOA traffic file...")

    signature = bt.head_signature()
    signature_changed = signature != state.get("signature", "")

    if not signature_changed and not force:
        print("  File unchanged since last check. Skipping download.")
        return

    print("  File changed (or forced) — downloading to check for a new month...")
    xlsx_bytes = bt.fetch_bytes()

    prev_ym = tuple(state["latest_ym"]) if state.get("latest_ym") else None
    new_ym = bt.latest_reported_month(xlsx_bytes)

    if new_ym is None:
        print("  Could not find any reported month in the AMB sheet — leaving state as-is.")
        return

    print(f"  Latest reported month: {bt.MONTH_NAMES[new_ym[1]-1]} {new_ym[0]} (previously: {prev_ym})")

    new_month_available = prev_ym is None or new_ym > prev_ym

    if new_month_available or force:
        os.makedirs(DATA_DIR, exist_ok=True)
        print("  Rebuilding BTOA traffic analysis workbook...")
        bt.build_workbook(xlsx_bytes, ANALYSIS_XLSX)

        html = build_email(prev_ym, new_ym, force=force)
        send_email("[BTOA Alert] New month of traffic data available", html, force=force)
    else:
        print("  File changed but no new month detected (e.g. a formatting re-save). Not emailing.")

    # Always persist the latest signature so we don't re-download on an
    # unchanged file tomorrow. Only advance latest_ym when it actually grew,
    # so a force-test run doesn't clobber real state.
    state["signature"] = signature
    if new_month_available:
        state["latest_ym"] = list(new_ym)
        state["latest_ym_detected_at"] = datetime.now(timezone.utc).isoformat()
    save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
