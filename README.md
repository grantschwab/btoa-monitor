# Border Crossing Data Monitor

Watches three border-crossing data sources for the Detroit-Windsor area and
emails an alert when new data becomes available. Runs daily via GitHub
Actions.

## Sources

| Monitor | Source | Covers | Cadence (observed) |
|---|---|---|---|
| `btoa_monitor.py` | BTOA (bridge/tunnel operators) spreadsheet | AMB, BWB, DWT — bidirectional, per-bridge | Monthly, undocumented lag |
| `statcan_monitor.py` | Statistics Canada table 24-10-0057 (Frontier Counts) | GHIB, AMB+DWT (combined), BWB — **northbound only** (into Canada) | Monthly, ~11-day lag |
| `bts_monitor.py` | BTS Border Crossing/Entry Data (CBP) | Detroit port (AMB+DWT+GHIB combined), Port Huron (BWB) — **southbound only** (into the US) | Monthly, longer lag than StatCan |

StatCan is the fastest of the three and is the only one that separates GHIB
from Ambassador Bridge/DWT — but it's northbound-only. BTOA is the only
source that's bidirectional *and* separates all bridges, but is the slowest.
BTS fills in the southbound leg with a US government source, faster in
principle than BTOA but still behind StatCan.

## Output data (`data/`)

- **`statcan_windsor_area_monthly.xlsx`** — monthly total/Canadian/American
  trips with YoY %, one sheet per crossing (GHIB, AMB+DWT, BWB), rebuilt by
  `statcan_monitor.py`.
- **`harmonized_windsor_detroit_monthly.xlsx`** — StatCan (northbound) and
  BTS (southbound) side by side per month, with a combined bidirectional
  total once both sides have data. Two sheets: Windsor-Detroit and
  Sarnia-Port Huron. Rebuilt by both `statcan_monitor.py` and
  `bts_monitor.py`, since either source updating changes it.
  **Caveat:** CBP has no separate GHIB port code, so on the Windsor-Detroit
  sheet the southbound figure is always AMB+DWT+GHIB combined — GHIB can't
  be isolated bidirectionally, only northbound.

Both are committed back to the repo automatically when a monitor detects
new data (see the workflow's "Commit data files if updated" step).

## How it runs

One GitHub Actions workflow (`.github/workflows/btoa_monitor.yml`), daily at
13:00 UTC (~9am ET), runs all three monitors in sequence, then commits any
updated spreadsheets. Each monitor keeps its own state file
(`state.json` / `statcan_state.json` / `bts_state.json`), cached via
`actions/cache` (not committed to git) using the same "unique key + prefix
restore-keys" trick so the cache grows monotonically without race
conditions.

## Setup

Repo secrets required:
- `GMAIL_USER` — sending Gmail address
- `GMAIL_APP_PASS` — Gmail app password (not the account password)
- `NOTIFY_EMAILS` — comma-separated recipient list

## Testing

Trigger the workflow manually via **Actions → Border Crossing Monitor → Run
workflow** with `force: true` to send test emails from all three monitors
regardless of whether anything changed.

To run a single monitor locally:

```
pip install -r requirements.txt
GMAIL_USER=... GMAIL_APP_PASS=... NOTIFY_EMAILS=... FORCE_EMAIL=true python statcan_monitor.py
```
