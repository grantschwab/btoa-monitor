import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import requests

BTOA_URL = "https://www.bridgeandtunneloperators.org/images/BTOA%20Traffic%202026.xlsx"
BTOA_PAGE_URL = "https://www.bridgeandtunneloperators.org/index.php/traffic"

STATE_FILE = "state.json"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def check_btoa(state, force=False):
    """BTOA's server sends no ETag header, so we key off Last-Modified plus
    Content-Length as a fallback signal (some static hosts vary Content-Length
    without touching Last-Modified on a re-save)."""
    last_signature = state.get("signature", "")

    head = requests.head(BTOA_URL, timeout=30)
    head.raise_for_status()
    last_modified = head.headers.get("last-modified", "")
    content_length = head.headers.get("content-length", "")
    current_signature = f"{last_modified}|{content_length}"

    print(f"  Last-Modified : {last_modified}")
    print(f"  Content-Length: {content_length}")

    changed = current_signature != last_signature

    if not changed and not force:
        print("  File unchanged. Nothing to do.")
        return False, current_signature, last_modified, content_length

    if force and not changed:
        print("  FORCE mode: sending test email despite unchanged file.")

    return True, current_signature, last_modified, content_length


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def build_email(prev_last_modified, new_last_modified, new_content_length, force=False):
    banner = ""
    if force:
        banner = """<p style="background:#fff3cd;color:#856404;padding:8px 12px;border-radius:4px;margin:0 0 12px 0">
&#9888; This is a manually triggered test run, not a live change detection.
</p>"""
    return f"""<html><body style="font-family:sans-serif;font-size:14px;max-width:640px;margin:0 auto">
<h2 style="color:#2c3e8c;margin-bottom:4px">&#128260; BTOA Traffic File Updated</h2>
<p style="color:#888;margin-top:0">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
{banner}
<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px">
  <tr><td style="padding:4px 10px;color:#666">Previous Last-Modified</td><td style="padding:4px 10px">{prev_last_modified or "(none — first run)"}</td></tr>
  <tr><td style="padding:4px 10px;color:#666">New Last-Modified</td><td style="padding:4px 10px"><b>{new_last_modified}</b></td></tr>
  <tr><td style="padding:4px 10px;color:#666">Content-Length</td><td style="padding:4px 10px">{new_content_length}</td></tr>
</table>
<p style="margin-top:20px">
  <a href="{BTOA_URL}">&#11015; Download the file</a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="{BTOA_PAGE_URL}">BTOA Traffic Data page</a>
</p>
<p style="font-size:12px;color:#888;margin-top:24px">
  Note: this only checks HTTP headers on the file, not its contents — a new
  Last-Modified doesn't necessarily mean a new month of data has been added
  (e.g. a formatting-only re-save will also trigger this alert).
</p>
</body></html>"""


def send_email(html, force=False):
    user = os.environ["GMAIL_USER"]
    pwd = os.environ["GMAIL_APP_PASS"]
    recipients = [e.strip() for e in os.environ["NOTIFY_EMAILS"].split(",")]
    msg = MIMEMultipart("alternative")
    prefix = "[TEST] " if force else ""
    msg["Subject"] = f"{prefix}[BTOA Alert] Traffic file updated"
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.sendmail(user, recipients, msg.as_string())
    print(f"Email sent to: {', '.join(recipients)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    state = load_state()
    force = os.environ.get("FORCE_EMAIL", "").lower() == "true"
    if force:
        print("*** FORCE MODE — will email regardless of change state ***")

    prev_last_modified = state.get("last_modified", "")

    print(f"[{datetime.now(timezone.utc).isoformat()[:19]}Z] Checking BTOA traffic file...")
    changed, signature, last_modified, content_length = check_btoa(state, force=force)

    if changed:
        html = build_email(prev_last_modified, last_modified, content_length, force=force)
        send_email(html, force=force)
        state["signature"] = signature
        state["last_modified"] = last_modified
        state["content_length"] = content_length
        state["last_changed_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
    else:
        print("Nothing to send.")


if __name__ == "__main__":
    main()
