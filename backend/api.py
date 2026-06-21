"""
========================================================================
  SHELFSENSE API - Flask server serving real data to the dashboard
  Usage : python api.py
  Port  : 5001 (configurable via API_PORT env var)

  ENDPOINTS
  ----------
  GET /api/latest-scan      - Most recent row from results.csv
  GET /api/scan-history      - All rows from results.csv
  GET /api/alert-log          - Critical alert events from CSV
  GET /api/config             - shelf_config.json contents + financials
  GET /api/channel-status     - Alert channel health + enabled state
  GET /api/health             - Service health check
========================================================================
"""

import os
import csv
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
RESULTS_CSV   = _SCRIPT_DIR / "results.csv"
SHELF_CONFIG  = _SCRIPT_DIR / "shelf_config.json"
ALERT_CONFIG  = _SCRIPT_DIR / "alert_config.json"
LAST_ALERT_FILE = _SCRIPT_DIR / ".last_alert_time"

DEFAULTS = {
    "unit_price": 0.5,
    "currency": "TND",
    "sales_per_hour": 20,
    "scan_interval_hours": 0.25,
    "store_open": 8,
    "store_close": 22,
}

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ------------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _get_financial_config() -> dict:
    cfg = _load_json(SHELF_CONFIG) or {}
    return {k: cfg.get(k, v) for k, v in DEFAULTS.items()}


def _read_csv() -> tuple[list[dict], list[str]]:
    if not RESULTS_CSV.exists():
        return [], []
    with open(RESULTS_CSV, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    return rows, list(fieldnames)


def _valid_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        ts = (r.get("timestamp") or "").strip()
        if not ts or ts.startswith("/"):
            continue
        out.append(r)
    return out


def _today_rows(rows: list[dict]) -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    for r in rows:
        ts = (r.get("timestamp") or "").strip()
        if ts.startswith(today):
            out.append(r)
    return out


def _compute_roi_pixels(cfg: dict) -> int:
    roi = cfg.get("roi")
    if not roi or len(roi) != 4:
        return 0
    y1, y2, x1, x2 = roi
    return abs(y2 - y1) * abs(x2 - x1)


def _row_to_scan(row: dict, roi_pixels: int) -> dict:
    stock = float(row.get("stock_pct", 0))
    empty = float(row.get("empty_pct", 100 - stock))
    product_px = int(round(stock / 100.0 * roi_pixels)) if roi_pixels > 0 else 0
    exposed_px = int(round(empty / 100.0 * roi_pixels)) if roi_pixels > 0 else 0

    ts_str = row.get("timestamp", "")
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        time_str = ts.strftime("%H:%M")
        iso = ts.isoformat()
    except (ValueError, TypeError):
        time_str = ts_str
        iso = ts_str

    return {
        "time": time_str,
        "timestamp": iso,
        "stock": stock,
        "exposedPixels": exposed_px,
        "productPixels": product_px,
        "missedUnits": float(row.get("missed_units", 0)),
        "lostRevenue": float(row.get("scan_loss_tnd", 0)),
    }


def _get_enabled_channels(alert_cfg: dict | None) -> list[str]:
    if not alert_cfg:
        return ["Telegram", "Gmail"]
    channels = []
    if alert_cfg.get("telegram", {}).get("enabled"):
        channels.append("Telegram")
    if alert_cfg.get("gmail", {}).get("enabled"):
        channels.append("Gmail")
    if alert_cfg.get("whatsapp", {}).get("enabled"):
        channels.append("WhatsApp")
    return channels if channels else ["Telegram", "Gmail"]


# ------------------------------------------------------------------
#  Endpoints
# ------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "ShelfSense API"})


@app.route("/api/latest-scan")
def latest_scan():
    rows, _ = _read_csv()
    valid = _valid_rows(rows)
    if not valid:
        return jsonify(None)

    row = valid[-1]
    cfg = _load_json(SHELF_CONFIG) or {}
    roi_px = _compute_roi_pixels(cfg)
    scan = _row_to_scan(row, roi_px)

    scan.update({
        "filename": row.get("filename", ""),
        "status": row.get("status", ""),
        "dailyLossTnd": float(row.get("daily_loss_tnd", 0)),
        "dailyMissedUnits": float(row.get("daily_missed_units", 0)),
        "projectedLossTnd": float(row.get("projected_loss_tnd", 0)),
        "recoverableTnd": float(row.get("recoverable_tnd", 0)),
    })
    return jsonify(scan)


@app.route("/api/scan-history")
def scan_history():
    rows, _ = _read_csv()
    valid = _valid_rows(rows)
    today = _today_rows(valid)
    cfg = _load_json(SHELF_CONFIG) or {}
    roi_px = _compute_roi_pixels(cfg)
    scans = [_row_to_scan(r, roi_px) for r in today]
    return jsonify(scans)


@app.route("/api/alert-log")
def alert_log():
    rows, _ = _read_csv()
    valid = _valid_rows(rows)
    today = _today_rows(valid)
    alert_cfg = _load_json(ALERT_CONFIG)
    channels = _get_enabled_channels(alert_cfg)

    alerts = []
    for r in today:
        if (r.get("status") or "").upper() != "CRITICAL":
            continue
        stock = float(r.get("stock_pct", 0))
        ts_str = r.get("timestamp", "")
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            time_str = ts.strftime("%H:%M")
        except (ValueError, TypeError):
            time_str = ts_str

        ch = list(channels)
        if stock < 20 and "WhatsApp" not in ch:
            if alert_cfg and alert_cfg.get("whatsapp", {}).get("enabled"):
                ch.append("WhatsApp")

        alerts.append({
            "id": "{}-{}".format(ts_str, stock),
            "time": time_str,
            "stock": stock,
            "channels": ch,
            "message": "Critical Stock Alert ({}%) dispatched".format(stock),
        })

    alerts.reverse()
    return jsonify(alerts)


@app.route("/api/config")
def config():
    cfg = _load_json(SHELF_CONFIG)
    if cfg is None:
        return jsonify({
            "error": "shelf_config.json not found. Run hsv_calibrator.py first."
        }), 404

    fin = _get_financial_config()
    cfg.update(fin)
    cfg["roi_total_pixels"] = _compute_roi_pixels(cfg)
    return jsonify(cfg)


@app.route("/api/channel-status")
def channel_status():
    alert_cfg = _load_json(ALERT_CONFIG)

    last_sent = None
    if LAST_ALERT_FILE.exists():
        try:
            with open(LAST_ALERT_FILE) as f:
                last_sent = f.read().strip()
        except Exception:
            pass

    channels = []

    tg = (alert_cfg or {}).get("telegram", {})
    channels.append({
        "name": "Telegram Bot API",
        "detail": "bot active" if tg.get("enabled") else "disabled",
        "enabled": bool(tg.get("enabled", False)),
        "last_sent": last_sent,
    })

    gm = (alert_cfg or {}).get("gmail", {})
    channels.append({
        "name": "Gmail SMTP Server",
        "detail": "smtp.gmail.com:587",
        "enabled": bool(gm.get("enabled", False)),
        "last_sent": last_sent,
    })

    wa = (alert_cfg or {}).get("whatsapp", {})
    channels.append({
        "name": "WhatsApp Gateway",
        "detail": wa.get("api_url", "not configured"),
        "enabled": bool(wa.get("enabled", False)),
        "last_sent": last_sent,
    })

    return jsonify(channels)


# ------------------------------------------------------------------
#  Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", 5001))
    print()
    print("=" * 50)
    print("  SHELFSENSE API - Starting on port {}".format(port))
    print("=" * 50)
    print("  Endpoints:")
    print("    GET /api/latest-scan")
    print("    GET /api/scan-history")
    print("    GET /api/alert-log")
    print("    GET /api/config")
    print("    GET /api/channel-status")
    print("    GET /api/health")
    print()
    app.run(host="0.0.0.0", port=port, debug=True)
