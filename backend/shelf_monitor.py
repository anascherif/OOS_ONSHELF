"""
Core shelf analysis pipeline. This is what runs on every photo.

Pipeline order:
  1. load_and_crop()     - reads image, applies ROI, scales to current res
  2. build_shelf_mask()  - HSV range masking + morphology cleanup
  3. build_exclude_mask()- rectangles over price tags (optional)
  4. calculate_stock()   - ratio of shelf pixels to total pixels
  5. save_debug()        - overlay + annotated debug image

Config is lazy-loaded once per process and cached. All paths are relative
to the script directory so this works no matter what CWD is.
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
    """Lazy-load shelf_config.json. Cached in _cfg so subsequent calls
    don't reread the file. Exits if no config exists."""
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
    """Read a named HSV range from config and return as uint8 array.
    Returns None if the key doesn't exist (not all ranges are required)."""
    if cfg is None:
        cfg = _get_cfg()
    v = cfg.get(key)
    if v is not None:
        return np.array(v, dtype=np.uint8)
    return None


def _load_params(cfg: dict | None = None) -> dict:
    """Pack all config values into a flat dict with sensible defaults.
    HSV values are stored as numpy arrays (OpenCV expects uint8).
    ref_dims is the calibration image size, used to scale the ROI."""
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
    """Read the image, scale the ROI from calibration-image coordinates
    to the current image resolution, and crop.

    Returns (original, crop, scaled_roi).  scaled_roi is the actual pixel
    bounds of the crop on this particular image — used later for debug overlay."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError("Cannot load: '{}'".format(image_path))
    h, w = img.shape[:2]
    roi = params["roi"]
    ref_dims = params.get("ref_dims")

    if roi is not None:
        y1, y2, x1, x2 = roi
        if ref_dims is not None:
            # Scale ROI from calibration image size to this image size
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
        # No ROI configured — use the full image
        scaled_roi = (0, h, 0, w)
        crop = img.copy()

    return img, crop, scaled_roi


def build_shelf_mask(bgr_crop: np.ndarray,
                     params: dict) -> tuple[np.ndarray, np.ndarray | None]:
    """Build a binary mask of the shelf area.

    Strategy: inverse background masking. We detect the shelf background
    (dark + light zones) via HSV inRange, subtract yogurt lids and price
    tags, then clean up noise with morphology.

    Returns (shelf_mask, ignore_mask).  shelf_mask has 255 where shelf
    background is detected.  ignore_mask has 255 on price tags (optional)."""
    hsv      = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
    h, w     = bgr_crop.shape[:2]
    combined = np.zeros((h, w), dtype=np.uint8)

    # Dark shelf background (shadows, back wall)
    dl = params["shelf_dark_lower"]
    du = params["shelf_dark_upper"]
    if dl is not None and du is not None:
        combined = cv2.bitwise_or(combined,
                   cv2.inRange(hsv, dl, du))

    # Light shelf background (bright front areas)
    ll = params["shelf_light_lower"]
    lu = params["shelf_light_upper"]
    if ll is not None and lu is not None:
        combined = cv2.bitwise_or(combined,
                   cv2.inRange(hsv, ll, lu))

    # Yogurt lids — mask them out of the shelf area so they count as product
    yl = params["yogurt_lower"]
    yu = params["yogurt_upper"]
    if yl is not None and yu is not None:
        yogurt   = cv2.inRange(hsv, yl, yu)
        combined = cv2.bitwise_and(combined, cv2.bitwise_not(yogurt))

    # Price tags / barcodes — same treatment
    il = params["ignore_lower"]
    iu = params["ignore_upper"]
    ignore_mask: np.ndarray | None = None
    if il is not None and iu is not None:
        ignore_mask = cv2.inRange(hsv, il, iu)
        combined = cv2.bitwise_and(combined, cv2.bitwise_not(ignore_mask))

    # Morphology: OPEN removes speckle noise, CLOSE fills gaps in shelf area
    k_open  = cv2.getStructuringElement(cv2.MORPH_RECT,
                                        (params["morph_k"], params["morph_k"]))
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT,
                                        (params["morph_k"] * 7, params["morph_k"] * 7))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  k_open)
    cleaned = cv2.morphologyEx(cleaned,  cv2.MORPH_CLOSE, k_close)
    return cleaned, ignore_mask


def build_exclude_mask(crop_shape: tuple, exclude_regions: list,
                        cfg_roi: list[int] | None) -> np.ndarray | None:
    """Create a mask that blacks out specific rectangle regions.

    Exclusion regions are stored in crop-relative pixel coordinates
    (drawn on the calibration image crop). Since analysis images may
    have different resolutions, we scale each rectangle by the ratio
    of current crop size to calibration crop size.

    cfg_roi is the raw [y1,y2,x1,x2] from config — its dimensions
    are the reference crop size from calibration."""
    if not exclude_regions:
        return None
    h, w = crop_shape[:2]
    if cfg_roi and len(cfg_roi) == 4:
        ref_h = max(cfg_roi[1] - cfg_roi[0], 1)
        ref_w = max(cfg_roi[3] - cfg_roi[2], 1)
    else:
        ref_h, ref_w = h, w
    mask = np.zeros((h, w), dtype=np.uint8)
    for ey1, ey2, ex1, ex2 in exclude_regions:
        sy1 = max(0, min(int(ey1 * h / ref_h), h - 1))
        sy2 = max(0, min(int(ey2 * h / ref_h), h))
        sx1 = max(0, min(int(ex1 * w / ref_w), w - 1))
        sx2 = max(0, min(int(ex2 * w / ref_w), w))
        if sy2 > sy1 and sx2 > sx1:
            mask[sy1:sy2, sx1:sx2] = 255
    return mask


def calculate_stock(mask: np.ndarray,
                    ignore_mask: np.ndarray | None = None) -> dict:
    """Stock = percentage of pixels NOT matching shelf background.

    High shelf-background pixels = low stock (empty shelf).
    Low shelf-background pixels = high stock (products covering the background).

    If an ignore_mask is provided (exclusion regions + HSV ignores),
    those pixels are subtracted from the total so they don't distort the ratio."""
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
    """Draw the mask onto the original image and write a debug file.

    Shelf area = red overlay.  Ignored/tag areas = blue overlay.
    Green rectangle = ROI boundary.  Resized to 900px high for easy viewing."""
    y1, y2, x1, x2 = scaled_roi
    h, w = orig.shape[:2]

    # Place the crop-size mask into the full-image-size coordinates
    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = mask

    overlay = orig.copy()
    overlay[full_mask > 0] = [0, 0, 220]        # red tint = shelf background

    if ignore_mask is not None:
        full_ignore = np.zeros((h, w), dtype=np.uint8)
        full_ignore[y1:y2, x1:x2] = ignore_mask
        overlay[full_ignore > 0] = [255, 120, 0]  # blue tint = tags / excluded

    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    label = "RED=shelf  BLUE=ignored(tags)  Stock: {}%".format(stock_pct)
    cv2.putText(overlay, label, (8, 24), font, 0.45, (0, 255, 0), 1)

    # Resize to a consistent viewing height
    sc    = 900 / overlay.shape[0]
    w_new = int(overlay.shape[1] * sc)
    debug = cv2.resize(overlay, (w_new, 900))

    base_dir = os.path.dirname(os.path.abspath(image_path))
    name, ext  = os.path.splitext(os.path.basename(image_path))
    debug_path = os.path.join(base_dir, "{}_debug{}".format(name, ext))
    cv2.imwrite(debug_path, debug)
    return debug_path


def analyze(image_path: str, save_debug_img: bool = True) -> dict:
    """Run the full analysis pipeline on a single photo.

    Returns a dict with stock_pct, empty_pct, alert flag, and file paths.
    This is the function called by watcher.py and the CLI."""
    cfg    = _get_cfg()
    params = _load_params(cfg)
    orig, crop, scaled_roi = load_and_crop(image_path, params)
    mask, ignore_hsv = build_shelf_mask(crop, params)

    # Build exclusion mask from saved rectangles (price tags, etc.)
    exclude_mask = build_exclude_mask(
        crop.shape, params.get("exclude_regions", []),
        params.get("roi"))

    # Combine HSV-based ignore mask with position-based exclusion mask
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
    """Print a human-readable analysis summary to the terminal."""
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
