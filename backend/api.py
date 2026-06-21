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
import base64
import numpy as np
from datetime import datetime
from pathlib import Path

import cv2

from flask import Flask, jsonify, request
from flask_cors import CORS

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
RESULTS_CSV   = _SCRIPT_DIR / "results.csv"
SHELF_CONFIG  = _SCRIPT_DIR / "shelf_config.json"
ALERT_CONFIG  = _SCRIPT_DIR / "alert_config.json"
LAST_ALERT_FILE = _SCRIPT_DIR / ".last_alert_time"
CALIBRATE_STATE = _SCRIPT_DIR / "._calibrate_state.json"
INCOMING_DIR     = _SCRIPT_DIR / "incoming"

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
#  Calibration Wizard Helpers
# ------------------------------------------------------------------

CALIBRATE_DEFAULTS = {
    "unit_price": 0.5,
    "currency": "TND",
    "sales_per_hour": 20,
    "scan_interval_hours": 0.25,
    "store_open": 8,
    "store_close": 22,
}


def _calib_state() -> dict:
    if CALIBRATE_STATE.exists():
        with open(CALIBRATE_STATE) as f:
            return json.load(f)
    return {"step": "upload"}


def _save_calib_state(state: dict) -> None:
    with open(CALIBRATE_STATE, "w") as f:
        json.dump(state, f, indent=2)


def _img_to_b64(img: np.ndarray, max_w: int = 900) -> str:
    h, w = img.shape[:2]
    if w > max_w:
        sc = max_w / w
        img = cv2.resize(img, (max_w, int(h * sc)))
    _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return base64.b64encode(buf).decode()


def _compute_hsv_range(pixels: list, tol_h=10, tol_s=15, tol_v=25) -> tuple:
    if not pixels:
        return None, None
    h = [p[0] for p in pixels]
    s = [p[1] for p in pixels]
    v = [p[2] for p in pixels]
    lower = [max(0, min(h) - tol_h), max(0, min(s) - tol_s), max(0, min(v) - tol_v)]
    upper = [min(179, max(h) + tol_h), min(255, max(s) + tol_s), min(255, max(v) + tol_v)]
    return lower, upper


def _build_preview_mask(hsv_crop: np.ndarray, state: dict) -> np.ndarray:
    h, w = hsv_crop.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for key in ("dark", "light"):
        lo = state.get("shelf_{}_lower".format(key))
        hi = state.get("shelf_{}_upper".format(key))
        if lo and hi:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv_crop, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8)))
    yl = state.get("yogurt_lower")
    yu = state.get("yogurt_upper")
    if yl and yu:
        ym = cv2.inRange(hsv_crop, np.array(yl, dtype=np.uint8), np.array(yu, dtype=np.uint8))
        mask = cv2.bitwise_and(mask, cv2.bitwise_not(ym))
    il = state.get("ignore_lower")
    iu = state.get("ignore_upper")
    if il and iu:
        im = cv2.inRange(hsv_crop, np.array(il, dtype=np.uint8), np.array(iu, dtype=np.uint8))
        mask = cv2.bitwise_and(mask, cv2.bitwise_not(im))
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    return mask


# ------------------------------------------------------------------
#  Calibration Wizard Endpoints
# ------------------------------------------------------------------

@app.route("/api/calibrate/state", methods=["GET"])
def calibrate_get_state():
    return jsonify(_calib_state())


@app.route("/api/calibrate/upload", methods=["POST"])
def calibrate_upload():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    INCOMING_DIR.mkdir(exist_ok=True)
    path = str(INCOMING_DIR / "calibrate_temp.jpg")
    file.save(path)
    img = cv2.imread(path)
    if img is None:
        return jsonify({"error": "Could not decode image"}), 400
    h, w = img.shape[:2]
    preview = _img_to_b64(img)
    state = {
        "step": "uploaded",
        "image_path": path,
        "image_size": [w, h],
        "roi": None,
        "shelf_dark_points": [],
        "shelf_dark_lower": None,
        "shelf_dark_upper": None,
        "shelf_light_points": [],
        "shelf_light_lower": None,
        "shelf_light_upper": None,
        "yogurt_points": [],
        "yogurt_lower": None,
        "yogurt_upper": None,
        "ignore_points": [],
        "ignore_lower": None,
        "ignore_upper": None,
        "exclude_regions": [],
    }
    _save_calib_state(state)
    return jsonify({"preview": preview, "width": w, "height": h})


@app.route("/api/calibrate/crop", methods=["POST"])
def calibrate_crop():
    state = _calib_state()
    data = request.get_json()
    if not data or "roi" not in data:
        return jsonify({"error": "Missing roi [y1,y2,x1,x2]"}), 400
    state["roi"] = data["roi"]
    img_path = state.get("image_path")
    if not img_path or not os.path.exists(img_path):
        return jsonify({"error": "No uploaded image"}), 400
    img = cv2.imread(img_path)
    y1, y2, x1, x2 = data["roi"]
    crop = img[y1:y2, x1:x2]
    state["crop_preview"] = _img_to_b64(crop)
    state["step"] = "cropped"
    _save_calib_state(state)
    return jsonify({"crop_preview": state["crop_preview"], "roi": data["roi"]})


@app.route("/api/calibrate/color-sample", methods=["POST"])
def calibrate_color_sample():
    state = _calib_state()
    data = request.get_json()
    if not data or "mode" not in data or "x" not in data or "y" not in data:
        return jsonify({"error": "Missing mode, x, or y"}), 400
    mode = data["mode"]
    cx, cy = data["x"], data["y"]
    if mode not in ("dark", "light", "yogurt", "ignore"):
        return jsonify({"error": "Invalid mode"}), 400
    img_path = state.get("image_path")
    roi = state.get("roi")
    if not img_path or not os.path.exists(img_path) or not roi:
        return jsonify({"error": "No image or crop defined"}), 400
    y1, y2, x1, x2 = roi
    img = cv2.imread(img_path)
    crop = img[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    cy = max(0, min(cy, hsv.shape[0] - 1))
    cx = max(0, min(cx, hsv.shape[1] - 1))
    h, s, v = int(hsv[cy, cx, 0]), int(hsv[cy, cx, 1]), int(hsv[cy, cx, 2])
    pts_key = "shelf_{}_points".format(mode) if mode in ("dark", "light") else "{}_points".format(mode)
    state.setdefault(pts_key, []).append([h, s, v])
    lo, hi = _compute_hsv_range(state[pts_key])
    lo_key = "shelf_{}_lower".format(mode) if mode in ("dark", "light") else "{}_lower".format(mode)
    hi_key = "shelf_{}_upper".format(mode) if mode in ("dark", "light") else "{}_upper".format(mode)
    state[lo_key] = lo
    state[hi_key] = hi
    hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = _build_preview_mask(hsv_crop, state)
    total_px = mask.shape[0] * mask.shape[1]
    shelf_px = cv2.countNonZero(mask)
    stock_pct = round(((total_px - shelf_px) / total_px) * 100, 1) if total_px > 0 else 0
    state["step"] = "sampling"
    _save_calib_state(state)
    return jsonify({
        "hsv": [h, s, v],
        "lower": lo,
        "upper": hi,
        "pointCount": len(state[pts_key]),
        "maskPreview": _img_to_b64(cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)),
        "stockEstimate": stock_pct,
    })


@app.route("/api/calibrate/exclude", methods=["POST"])
def calibrate_exclude():
    state = _calib_state()
    data = request.get_json()
    if not data or "x1" not in data or "y1" not in data or "x2" not in data or "y2" not in data:
        return jsonify({"error": "Missing exclude rect coordinates"}), 400
    rect = [data["y1"], data["y2"], data["x1"], data["x2"]]
    state.setdefault("exclude_regions", []).append(rect)
    state["step"] = "exclude"
    _save_calib_state(state)
    return jsonify({"exclude_regions": state["exclude_regions"]})


@app.route("/api/calibrate/exclude-clear", methods=["POST"])
def calibrate_exclude_clear():
    state = _calib_state()
    state["exclude_regions"] = []
    _save_calib_state(state)
    return jsonify({"exclude_regions": []})


@app.route("/api/calibrate/save", methods=["POST"])
def calibrate_save():
    state = _calib_state()
    roi = state.get("roi")
    if not roi:
        return jsonify({"error": "No crop region defined"}), 400
    if not state.get("shelf_dark_lower") and not state.get("shelf_light_lower"):
        return jsonify({"error": "Sample at least one shelf color first"}), 400
    config = {
        "roi": roi,
        "shelf_dark_lower": state.get("shelf_dark_lower"),
        "shelf_dark_upper": state.get("shelf_dark_upper"),
        "shelf_light_lower": state.get("shelf_light_lower"),
        "shelf_light_upper": state.get("shelf_light_upper"),
        "yogurt_lower": state.get("yogurt_lower"),
        "yogurt_upper": state.get("yogurt_upper"),
        "ignore_lower": state.get("ignore_lower"),
        "ignore_upper": state.get("ignore_upper"),
        "exclude_regions": state.get("exclude_regions", []),
        "morph_kernel": 7,
        "alert_threshold": 30.0,
        "calibrated_on": os.path.basename(state.get("image_path", "unknown")),
        "image_size": state.get("image_size", [0, 0]),
    }
    config.update(CALIBRATE_DEFAULTS)
    with open(SHELF_CONFIG, "w") as f:
        json.dump(config, f, indent=2)
    if CALIBRATE_STATE.exists():
        CALIBRATE_STATE.unlink()
    return jsonify({"status": "ok", "message": "shelf_config.json saved successfully"})


@app.route("/api/calibrate/reset", methods=["POST"])
def calibrate_reset():
    if CALIBRATE_STATE.exists():
        CALIBRATE_STATE.unlink()
    return jsonify({"status": "ok"})


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
