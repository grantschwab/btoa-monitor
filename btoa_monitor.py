import io
import os
from datetime import datetime, timezone
import requests
import openpyxl

from common import load_state, save_state, send_email

BTOA_URL = "https://www.bridgeandtunneloperators.org/images/BTOA%20Traffic%202026.xlsx"
BTOA_PAGE_URL = "https://www.bridgeandtunneloperators.org/index.php/traffic"

# AMB is used as the bellwether sheet: in past pulls it, BWB, and DWT have
# always advanced to a new reported month together, so checking one bridge
# is enough to detect "a new month landed" without parsing every sheet.
MONTH_SHEET = "AMB"
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

STATE_FILE = "state.json"


# ---------------------------------------------------------------------------
# Change detection (cheap: HEAD only)
# ---------------------------------------------------------------------------

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
# Month detection (expensive: full download + parse)
# ---------------------------------------------------------------------------

def latest_reported_month(xlsx_bytes):
    """Scan the AMB sheet's TOTAL rows and return the (year, month) of the
    most recent month with an actual reported (non-empty, non-zero) value.
    Row layout: col0=Year, col2=Vehicle Classification, col4:16=Jan..Dec."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb[MONTH_SHEET]

    best = None  # (year, month)
    for row in ws.iter_rows(min_row=10, values_only=True):
        if len(row) < 16:
            continue
        year, classification, months = row[0], row[2], row[4:16]
        if classification != "TOTAL" or not isinstance(year, int):
            continue
        filled_months = [i + 1 for i, v in enumerate(months) if v not in (None, 0)]
        if not filled_months:
            continue
        candidate = (year, max(filled_months))
        if best is None or candidate > best:
            best = candidate
    return best  # (year, month) or None


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def build_email(prev_ym, new_ym, force=False):
    prev_str = f"{MONTH_NAMES[prev_ym[1] - 1]} {prev_ym[0]}" if prev_ym else "(none — first run)"
    new_str = f"{MONTH_NAMES[new_ym[1] - 1]} {new_ym[0]}"
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
  <a href="{BTOA_URL}">&#11015; Download the file</a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="{BTOA_PAGE_URL}">BTOA Traffic Data page</a>
</p>
<p style="font-size:12px;color:#888;margin-top:24px">
  Detected from the AMB sheet's monthly TOTAL row. AMB, BWB, and DWT have
  historically advanced together, so this is treated as a stand-in for all
  Detroit-area bridges/tunnel, but worth a quick check on first use.
</p>
</body></html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    state = load_state(STATE_FILE)
    force = os.environ.get("FORCE_EMAIL", "").lower() == "true"
    if force:
        print("*** FORCE MODE — will email regardless of state ***")

    print(f"[{datetime.now(timezone.utc).isoformat()[:19]}Z] Checking BTOA traffic file...")

    signature = head_signature()
    signature_changed = signature != state.get("signature", "")

    if not signature_changed and not force:
        print("  File unchanged since last check. Skipping download.")
        return

    print("  File changed (or forced) — downloading to check for a new month...")
    resp = requests.get(BTOA_URL, timeout=120)
    resp.raise_for_status()

    prev_ym = tuple(state["latest_ym"]) if state.get("latest_ym") else None
    new_ym = latest_reported_month(resp.content)

    if new_ym is None:
        print("  Could not find any reported month in the AMB sheet — leaving state as-is.")
        return

    print(f"  Latest reported month: {MONTH_NAMES[new_ym[1]-1]} {new_ym[0]} (previously: {prev_ym})")

    new_month_available = prev_ym is None or new_ym > prev_ym

    if new_month_available or force:
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
