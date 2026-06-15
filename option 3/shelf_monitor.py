"""
========================================================================
  SHELF MONITOR - Run on any photo after calibration
  Usage : python shelf_monitor.py <photo.jpg>
  Reads : shelf_config.json  (written once by hsv_calibrator.py)
========================================================================
"""

import cv2
import numpy as np
import sys
import os
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_SCRIPT_DIR, "shelf_config.json")

_cfg = None


def _get_cfg() -> dict:
    global _cfg
    if _cfg is not None:
        return _cfg
    if not os.path.exists(CONFIG_PATH):
        print("  Warning: shelf_config.json not found.")
        print("  Run hsv_calibrator.py first.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        _cfg = json.load(f)
    return _cfg


def _arr(key: str, cfg: dict | None = None) -> np.ndarray | None:
    if cfg is None:
        cfg = _get_cfg()
    v = cfg.get(key)
    if v is not None:
        return np.array(v, dtype=np.uint8)
    return None


def _load_params(cfg: dict | None = None) -> dict:
    if cfg is None:
        cfg = _get_cfg()
    return {
        "roi"              : cfg.get("roi"),
        "shelf_dark_lower" : _arr("shelf_dark_lower", cfg),
        "shelf_dark_upper" : _arr("shelf_dark_upper", cfg),
        "shelf_light_lower": _arr("shelf_light_lower", cfg),
        "shelf_light_upper": _arr("shelf_light_upper", cfg),
        "yogurt_lower"     : _arr("yogurt_lower", cfg),
        "yogurt_upper"     : _arr("yogurt_upper", cfg),
        "morph_k"          : cfg.get("morph_kernel", 7),
        "alert_threshold"  : cfg.get("alert_threshold", 30.0),
    }


def load_and_crop(image_path: str, params: dict) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError("Cannot load: '{}'".format(image_path))
    roi = params["roi"]
    if roi is not None:
        y1, y2, x1, x2 = roi
        img = img[y1:y2, x1:x2]
    return img


def build_shelf_mask(bgr_crop: np.ndarray, params: dict) -> np.ndarray:
    hsv      = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
    h, w     = bgr_crop.shape[:2]
    combined = np.zeros((h, w), dtype=np.uint8)

    dl = params["shelf_dark_lower"]
    du = params["shelf_dark_upper"]
    if dl is not None and du is not None:
        combined = cv2.bitwise_or(combined,
                   cv2.inRange(hsv, dl, du))

    ll = params["shelf_light_lower"]
    lu = params["shelf_light_upper"]
    if ll is not None and lu is not None:
        combined = cv2.bitwise_or(combined,
                   cv2.inRange(hsv, ll, lu))

    yl = params["yogurt_lower"]
    yu = params["yogurt_upper"]
    if yl is not None and yu is not None:
        yogurt   = cv2.inRange(hsv, yl, yu)
        combined = cv2.bitwise_and(combined, cv2.bitwise_not(yogurt))

    k       = cv2.getStructuringElement(cv2.MORPH_RECT,
                                        (params["morph_k"], params["morph_k"]))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  k)
    cleaned = cv2.morphologyEx(cleaned,  cv2.MORPH_CLOSE, k)
    return cleaned


def calculate_stock(mask: np.ndarray) -> dict:
    total    = mask.shape[0] * mask.shape[1]
    shelf_px = cv2.countNonZero(mask)
    stock    = round(((total - shelf_px) / total) * 100, 2)
    empty    = round(100 - stock, 2)
    return {
        "total_pixels": total,
        "shelf_pixels": shelf_px,
        "stock_pct"   : stock,
        "empty_pct"   : empty,
    }


def save_debug(bgr_crop: np.ndarray, mask: np.ndarray,
               image_path: str, stock_pct: float) -> str:
    overlay = bgr_crop.copy()
    overlay[mask > 0] = [0, 0, 220]
    orig    = bgr_crop.copy()
    font    = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(orig,    "ORIGINAL",
                (8,20), font, 0.5, (255,255,255), 1)
    cv2.putText(overlay, "RED=EMPTY SHELF | Stock: {}%".format(stock_pct),
                (8,20), font, 0.45, (0,0,220), 1)
    debug  = np.vstack([orig, overlay])
    sc     = 900 / debug.shape[0]
    w_new  = int(debug.shape[1] * sc)
    debug  = cv2.resize(debug, (w_new, 900))
    mid    = 900 // 2
    cv2.line(debug, (0,mid), (debug.shape[1],mid), (255,255,255), 2)

    base_dir = os.path.dirname(os.path.abspath(image_path))
    name, ext  = os.path.splitext(os.path.basename(image_path))
    debug_path = os.path.join(base_dir, "{}_debug{}".format(name, ext))
    cv2.imwrite(debug_path, debug)
    return debug_path


def analyze(image_path: str, save_debug_img: bool = True) -> dict:
    cfg    = _get_cfg()
    params = _load_params(cfg)
    crop    = load_and_crop(image_path, params)
    mask    = build_shelf_mask(crop, params)
    metrics = calculate_stock(mask)

    debug_path: str | None = None
    if save_debug_img:
        debug_path = save_debug(crop, mask, image_path, metrics["stock_pct"])

    metrics["image_path"] = image_path
    metrics["debug_path"] = debug_path
    metrics["alert"]      = metrics["stock_pct"] < params["alert_threshold"]
    return metrics


def print_results(metrics: dict) -> None:
    cfg = _get_cfg()
    alert_threshold = cfg.get("alert_threshold", 30.0)

    sep = "-" * 45
    print()
    print(sep)
    print("  Image   : {}".format(os.path.basename(metrics['image_path'])))
    print("  Stock   : {}%".format(metrics['stock_pct']))
    print("  Empty   : {}%".format(metrics['empty_pct']))
    print(sep)
    if metrics["alert"]:
        print()
        print("  ALARM: STOCK CRITICAL - below {}%!".format(alert_threshold))
        print()
    else:
        print()
        print("  Stock OK - {}% remaining".format(metrics['stock_pct']))
        print()
    if metrics["debug_path"]:
        print("  Debug   -> {}".format(metrics['debug_path']))
        print()


# Entry point
if __name__ == "__main__":
    image = sys.argv[1] if len(sys.argv) > 1 else "base one.png"
    results = analyze(image)
    print_results(results)
