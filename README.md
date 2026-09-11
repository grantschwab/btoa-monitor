# Border Crossing Data Monitor

Watches three border-crossing data sources for the Detroit-Windsor area and
emails an alert when new data becomes available. Runs via GitHub Actions.
Scripts live in `code/`; spreadsheets are rebuilt into `data/` and
auto-committed.

## Sources

| Monitor | Source | Covers | Cadence (observed) |
|---|---|---|---|
| `code/btoa_monitor.py` | BTOA (bridge/tunnel operators) spreadsheet | AMB, BWB, DWT, GHIB — bidirectional, per-bridge | Monthly, ~14-day lag after month start |
| `code/statcan_monitor.py` | Statistics Canada table 24-10-0057 (Frontier Counts) | GHIB, AMB+DWT (combined), BWB — **northbound only** (into Canada) | Monthly, ~11-day lag |
| `code/bts_monitor.py` | BTS Border Crossing/Entry Data (CBP) | Detroit port (AMB+DWT+GHIB combined), Port Huron (BWB) — **southbound only** (into the US) | Monthly, longer lag than StatCan |

StatCan is the fastest of the three and is the only one that separates GHIB
from Ambassador Bridge/DWT on that side — but it's northbound-only. BTOA is
the only source that's bidirectional *and* separates all four crossings
(including GHIB), but is the slowest. BTS fills in the southbound leg with a
US government source, faster in principle than BTOA but still behind
StatCan. GHIB opened July 27, 2026, so all GHIB columns/series are blank
before then and partial for that first month.

## Output data (`data/`)

- **`btoa_traffic_analysis.xlsx`** — rebuilt by `btoa_monitor.py` whenever a
  new month lands. Per-bridge (AMB/BWB/DWT/GHIB) monthly figures,
  2019-present:
  - `Chart Data` — long format for charting: one row per month per category
    (Total vehicles, Passenger cars, Trucks, in that order), bridges as
    columns. Matches the layout used for the existing chart.
  - `Overall traffic` / `Car traffic` / `Truck traffic` — one sheet each,
    per-bridge monthly totals + YoY % columns.
  - Monthly bar-chart snapshot tabs (e.g. `August 2026`) — one added
    automatically for every month from August 2026 onward once BTOA
    reports it: `crossing / month_<prior year> / month_<year> /
    pct_change / category` (Total → Cars → Trucks), ready to drop into a
    bar chart.
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

All three are committed back to the repo automatically when a monitor
detects new data (see the workflow's "Commit data files if updated" step).

## How it runs

Two GitHub Actions workflows, both invoking scripts as `python code/*.py`
from the repo root (so `state.json` / `data/` stay at the repo root
regardless of where the scripts live):

- **`.github/workflows/btoa_monitor.yml`** — daily at 13:00 UTC (~9am ET),
  runs all three monitors in sequence, then commits any updated
  spreadsheets.
- **`.github/workflows/btoa_extra_checks.yml`** — runs 4x/day
  (9am/noon/3pm/6pm ET) but only actually executes `btoa_monitor.py` on the
  14th, 15th, or a weekend-adjusted 16th of the month, gated by a bash date
  check. BTOA typically finalizes its spreadsheet ~14 days after month
  start, so this catches that update within hours instead of waiting for
  the once-daily cron. Shares the `btoa-monitor` concurrency group with the
  daily workflow (serialized, not cancelled) to avoid racing on
  `state.json`/git state.

Each monitor keeps its own state file (`state.json` / `statcan_state.json`
/ `bts_state.json`), cached via `actions/cache` (not committed to git)
using the same "unique key + prefix restore-keys" trick so the cache grows
monotonically without race conditions.

## Setup

Repo secrets required:
- `GMAIL_USER` — sending Gmail address
- `GMAIL_APP_PASS` — Gmail app password (not the account password)
- `NOTIFY_EMAILS` — comma-separated recipient list

## Testing

Trigger a workflow manually via **Actions → Border Crossing Monitor → Run
workflow** with `force: true` to send test emails from all three monitors
regardless of whether anything changed. **Actions → BTOA Extra Checks
(finalization window) → Run workflow** can also be triggered manually, but
the date gate still applies even on manual dispatch — it only actually
checks BTOA on the 14th/15th/16th window, so a manual run on any other day
will show `should_run=false` in the `check-window` job logs and skip.

To run a single monitor locally (from the repo root, so relative paths
resolve the same way as in Actions):

```
pip install -r requirements.txt
GMAIL_USER=... GMAIL_APP_PASS=... NOTIFY_EMAILS=... FORCE_EMAIL=true python code/statcan_monitor.py
```
