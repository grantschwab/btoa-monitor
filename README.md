# BTOA Traffic Monitor

Watches the Bridge and Tunnel Operators Association's `BTOA Traffic 2026.xlsx`
(https://www.bridgeandtunneloperators.org/index.php/traffic) for changes and
emails an alert when the file is updated.

## Why Last-Modified instead of ETag

BTOA's server (Apache) doesn't send an `ETag` header on this file — only
`Last-Modified` and `Content-Length`. `btoa_monitor.py` combines both into a
single signature string and alerts whenever it changes. This is a coarser
signal than ETag: a formatting-only re-save of the workbook (no new monthly
data) will also trigger an alert. There's no in-file diffing — the email just
tells you the file changed and links to it so you can check for yourself
whether new monthly figures appeared.

## How it runs

GitHub Actions cron, once daily (`0 13 * * *`, ~9am ET). State (the last-seen
signature) is kept in `state.json`, persisted between runs via
`actions/cache` — not committed to git — using the same "unique key + prefix
restore-keys" trick as the recall-tool monitor, so the cache grows
monotonically without race conditions.

## Setup

Repo secrets required:
- `GMAIL_USER` — sending Gmail address
- `GMAIL_APP_PASS` — Gmail app password (not the account password)
- `NOTIFY_EMAILS` — comma-separated recipient list

## Testing

Trigger the workflow manually via **Actions → BTOA Monitor → Run workflow**
with `force: true` to send a test email regardless of whether the file has
changed.

To run locally:

```
pip install -r requirements.txt
GMAIL_USER=... GMAIL_APP_PASS=... NOTIFY_EMAILS=... FORCE_EMAIL=true python btoa_monitor.py
```
