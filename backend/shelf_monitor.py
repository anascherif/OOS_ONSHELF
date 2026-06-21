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
        "ignore_lower"     : _arr("ignore_lower", cfg),
        "ignore_upper"     : _arr("ignore_upper", cfg),
        "exclude_regions"  : cfg.get("exclude_regions", []),
        "morph_k"          : cfg.get("morph_kernel", 7),
        "alert_threshold"  : cfg.get("alert_threshold", 30.0),
        "ref_dims"         : cfg.get("image_size"),
    }


def load_and_crop(image_path: str,
                  params: dict) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError("Cannot load: '{}'".format(image_path))
    h, w = img.shape[:2]
    roi = params["roi"]
    ref_dims = params.get("ref_dims")

    if roi is not None:
        y1, y2, x1, x2 = roi
        if ref_dims is not None:
            rw, rh = ref_dims
            y1 = int(y1 * h / rh)
            y2 = int(y2 * h / rh)
            x1 = int(x1 * w / rw)
            x2 = int(x2 * w / rw)
        y1 = max(0, y1); y2 = min(h, y2)
        x1 = max(0, x1); x2 = min(w, x2)
        scaled_roi = (y1, y2, x1, x2)
        crop = img[y1:y2, x1:x2]
    else:
        scaled_roi = (0, h, 0, w)
        crop = img.copy()

    return img, crop, scaled_roi


def build_shelf_mask(bgr_crop: np.ndarray,
                     params: dict) -> tuple[np.ndarray, np.ndarray | None]:
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

    il = params["ignore_lower"]
    iu = params["ignore_upper"]
    ignore_mask: np.ndarray | None = None
    if il is not None and iu is not None:
        ignore_mask = cv2.inRange(hsv, il, iu)
        combined = cv2.bitwise_and(combined, cv2.bitwise_not(ignore_mask))

    k_open  = cv2.getStructuringElement(cv2.MORPH_RECT,
                                        (params["morph_k"], params["morph_k"]))
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT,
                                        (params["morph_k"] * 7, params["morph_k"] * 7))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  k_open)
    cleaned = cv2.morphologyEx(cleaned,  cv2.MORPH_CLOSE, k_close)
    return cleaned, ignore_mask


def build_exclude_mask(crop_shape: tuple, exclude_regions: list) -> np.ndarray | None:
    if not exclude_regions:
        return None
    h, w = crop_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for ey1, ey2, ex1, ex2 in exclude_regions:
        sy1 = max(0, min(int(ey1), h - 1))
        sy2 = max(0, min(int(ey2), h))
        sx1 = max(0, min(int(ex1), w - 1))
        sx2 = max(0, min(int(ex2), w))
        if sy2 > sy1 and sx2 > sx1:
            mask[sy1:sy2, sx1:sx2] = 255
    return mask


def calculate_stock(mask: np.ndarray,
                    ignore_mask: np.ndarray | None = None) -> dict:
    total    = mask.shape[0] * mask.shape[1]
    shelf_px = cv2.countNonZero(mask)

    if ignore_mask is not None:
        excluded   = cv2.countNonZero(ignore_mask)
        overlapped = cv2.countNonZero(cv2.bitwise_and(mask, ignore_mask))
        shelf_px   = shelf_px - overlapped
        total      = total - excluded

    stock = round(((total - shelf_px) / total) * 100, 2) if total > 0 else 0
    empty = round(100 - stock, 2)
    return {
        "total_pixels": total,
        "shelf_pixels": shelf_px,
        "stock_pct"   : stock,
        "empty_pct"   : empty,
    }


def save_debug(orig: np.ndarray, mask: np.ndarray,
               scaled_roi: tuple[int, int, int, int],
               image_path: str, stock_pct: float,
               ignore_mask: np.ndarray | None = None) -> str:
    y1, y2, x1, x2 = scaled_roi
    h, w = orig.shape[:2]

    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = mask

    overlay = orig.copy()
    overlay[full_mask > 0] = [0, 0, 220]

    if ignore_mask is not None:
        full_ignore = np.zeros((h, w), dtype=np.uint8)
        full_ignore[y1:y2, x1:x2] = ignore_mask
        overlay[full_ignore > 0] = [255, 120, 0]

    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    label = "RED=shelf  BLUE=ignored(tags)  Stock: {}%".format(stock_pct)
    cv2.putText(overlay, label, (8, 24), font, 0.45, (0, 255, 0), 1)

    sc    = 900 / overlay.shape[0]
    w_new = int(overlay.shape[1] * sc)
    debug = cv2.resize(overlay, (w_new, 900))

    base_dir = os.path.dirname(os.path.abspath(image_path))
    name, ext  = os.path.splitext(os.path.basename(image_path))
    debug_path = os.path.join(base_dir, "{}_debug{}".format(name, ext))
    cv2.imwrite(debug_path, debug)
    return debug_path


def analyze(image_path: str, save_debug_img: bool = True) -> dict:
    cfg    = _get_cfg()
    params = _load_params(cfg)
    orig, crop, scaled_roi = load_and_crop(image_path, params)
    mask, ignore_hsv = build_shelf_mask(crop, params)

    exclude_mask = build_exclude_mask(
        crop.shape, params.get("exclude_regions", []))

    ignore_mask = ignore_hsv
    if exclude_mask is not None:
        if ignore_mask is not None:
            ignore_mask = cv2.bitwise_or(ignore_mask, exclude_mask)
        else:
            ignore_mask = exclude_mask

    metrics = calculate_stock(mask, ignore_mask)

    debug_path: str | None = None
    if save_debug_img:
        debug_path = save_debug(orig, mask, scaled_roi, image_path,
                                metrics["stock_pct"], ignore_mask)

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
