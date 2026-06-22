# ShelfSense

Real-time computer vision shelf monitoring for retail operations. Automatically detects stock depletion from store camera photos, computes financial impact, and dispatches alerts via Gmail, Telegram, and WhatsApp.

## Overview

ShelfSense replaces manual shelf checks with an automated pipeline: a shop assistant snaps a photo, drops it into the incoming folder, and the system processes it against a calibrated mask to compute fill rate, missed sales, and projected loss. A live web dashboard provides at-a-glance KPIs, depletion trends, and alert history.

## Architecture

```
backend/                          frontend/
  hsv_calibrator.py  (setup)       app/           pages + layout
  shelf_monitor.py   (core CV)     components/    dashboard widgets
  watcher.py         (auto-loop)   lib/           API client + types
  alerts.py          (dispatch)    public/         assets
  api.py             (Flask API)
  archive/                         next.config.mjs
    photos/  debug/               package.json
  incoming/        <- drop photos here
  results.csv      <- scan log
  shelf_config.json               tsconfig.json
  requirements.txt
```

## Prerequisites

- Python 3.10+
- Node.js 20+

## Setup

### 1. Calibrate (run once per shelf)

```bash
cd backend
pip install -r requirements.txt
python hsv_calibrator.py reference_photo.jpg
```

Draw a crop box around the shelf, sample dark (D) and light (L) background colours, and optionally exclude product colours (Y) or price tags (I). Press S to save `shelf_config.json`.

### 2. Configure alerts (optional)

```bash
cp alert_config.example.json alert_config.json
```

Edit `alert_config.json` with your Gmail app password, Telegram bot token, or WhatsApp gateway URL. Placeholder fields are documented in the example file.

### 3. Start the watcher

```bash
cd backend
python watcher.py
```

The watcher polls `incoming/` for new images, runs `shelf_monitor.py` on each one, logs results to `results.csv`, archives originals and debug overlays, and triggers alerts when stock falls below the configured threshold.

### 4. Start the API server

```bash
cd backend
python api.py
```

Serves scan data and configuration to the dashboard on port 5001. CORS is enabled for all origins on `/api/*` routes.

### 5. Start the dashboard

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:3000`. The dashboard polls the API every 15 seconds. All API calls use relative paths through a Next.js proxy rewrite — no hardcoded hostnames.

### 6. Feed photos

Drop JPEG or PNG files into `backend/incoming/`. The watcher picks up new files by snapshot-diff (not continuous polling), processes each one, and the dashboard reflects the latest scan within one poll cycle.

## API Reference

Base URL: `http://localhost:5001`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health check |
| GET | `/api/latest-scan` | Most recent scan from `results.csv` |
| GET | `/api/scan-history` | All of today's valid scan rows |
| GET | `/api/alert-log` | Critical alerts raised today |
| GET | `/api/config` | `shelf_config.json` merged with financial defaults |
| GET | `/api/channel-status` | Alert channel state and last-sent timestamp |

## Configuration

### Financial defaults

Written to `shelf_config.json` by the calibrator. Override any field without re-calibrating:

| Key | Default | Description |
|-----|---------|-------------|
| `unit_price` | 0.5 | Price per unit in local currency |
| `currency` | TND | Display currency code |
| `sales_per_hour` | 20 | Average customer demand per hour |
| `scan_interval_hours` | 0.25 | Expected interval between scans |
| `store_open` | 8 | Store opening hour (24 h) |
| `store_close` | 22 | Store closing hour (24 h) |

### Alert channels

| Channel | Protocol | Config file |
|---------|----------|-------------|
| Gmail | SMTP (smtp.gmail.com:587) | `alert_config.json` → `gmail` |
| Telegram | Bot API | `alert_config.json` → `telegram` |
| WhatsApp | HTTP gateway | `alert_config.json` → `whatsapp` |

## Exclusion regions

Price tags, barcodes, and other non-product objects can be masked by drawing exclusion rectangles during calibration (Phase 3). Coordinates are stored in crop-relative pixels and scaled proportionally when the analysis runs on images of different resolutions.

## Development

- Backend scripts use `_SCRIPT_DIR` for all path lookups — they work from any working directory
- `shelf_config.json` and `alert_config.json` contain site-specific data and are excluded from version control
- Results are filtered to the current date by the API — the full history is preserved in `results.csv`
- Financial constants are read from the config file at runtime; no hardcoded values in source code

## Notes

- The dashboard is read-only. Configuration changes must be made through the calibrator or by editing `shelf_config.json` directly.
- Exclusion regions are the most calibration-sensitive parameter — verify placement on a test image after calibration.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Computer vision | Python, OpenCV, NumPy |
| Backend API | Flask, flask-cors |
| Frontend | Next.js 16, React 19 |
| UI | Tailwind CSS 4, shadcn/ui, Lucide icons |
| Charts | Recharts |
| Alerts | smtplib (Gmail), python-telegram-bot, requests (WhatsApp) |

## License

MIT
