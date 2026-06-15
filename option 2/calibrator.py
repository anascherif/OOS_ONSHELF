"""
========================================================================
  HSV CALIBRATOR — Smart Multi-Zone Shelf Color Sampler
  Usage: python hsv_calibrator.py <your_image.png>
========================================================================

KEYBOARD CONTROLS
-----------------
  D  → switch to DARK SHELF mode   (shadow / back-of-shelf areas)
  L  → switch to LIGHT SHELF mode  (bright / front-of-shelf areas)
  Y  → switch to YOGURT mode        (lids, packaging — to EXCLUDE)
  C  → clear all points in current mode
  R  → reset everything
  S  → save config + generate shelf_monitor.py with your values
  Q  → quit without saving

WORKFLOW
--------
  1. Run the script on your image
  2. Press D → click all dark/shadow empty shelf areas
  3. Press L → click all bright/lit empty shelf areas
  4. Press Y → click on yogurt lids (white, colored packaging)
  5. Press S → saves final shelf_monitor.py ready to run
"""

import cv2
import numpy as np
import sys
import os
from datetime import datetime

# ── Mode definitions ─────────────────────────────────────────────────
MODES = {
    'd': {
        'name'   : 'DARK SHELF',
        'label'  : 'D = Dark shelf / shadows',
        'color'  : (0,   165, 255),   # orange
        'points' : [],
        'hsv'    : [],
    },
    'l': {
        'name'   : 'LIGHT SHELF',
        'label'  : 'L = Light shelf / bright areas',
        'color'  : (0,   255, 255),   # yellow
        'points' : [],
        'hsv'    : [],
    },
    'y': {
        'name'   : 'YOGURT (exclude)',
        'label'  : 'Y = Yogurt lids / packaging',
        'color'  : (0,   0,   255),   # red
        'points' : [],
        'hsv'    : [],
    },
}

current_mode = 'd'   # start in dark shelf mode


# ════════════════════════════════════════════════════════════════════
# CORE HSV COMPUTATION
# ════════════════════════════════════════════════════════════════════

def compute_range(hsv_values: list, tolerance_h=8, tolerance_s=12, tolerance_v=20) -> tuple[np.ndarray, np.ndarray]:
    """
    Given a list of (H, S, V) tuples, compute a safe lower/upper range
    with tolerances, clamped to OpenCV HSV bounds.
    Returns a default (0,0,0)/(179,255,255) range if no values provided.
    """
    if not hsv_values:
        return np.array([0, 0, 0]), np.array([179, 255, 255])

    h_vals = [p[0] for p in hsv_values]
    s_vals = [p[1] for p in hsv_values]
    v_vals = [p[2] for p in hsv_values]

    lower = np.array([
        max(0,   min(h_vals) - tolerance_h),
        max(0,   min(s_vals) - tolerance_s),
        max(0,   min(v_vals) - tolerance_v),
    ])
    upper = np.array([
        min(179, max(h_vals) + tolerance_h),
        min(255, max(s_vals) + tolerance_s),
        min(255, max(v_vals) + tolerance_v),
    ])
    return lower, upper


def build_preview_mask(hsv_full: np.ndarray) -> np.ndarray:
    """
    Build a live preview mask from current sampled points.
    Shelf ranges (D + L) → included (white)
    Yogurt range         → excluded (subtract from shelf mask)
    """
    h, w = hsv_full.shape[:2]
    shelf_mask  = np.zeros((h, w), dtype=np.uint8)
    yogurt_mask = np.zeros((h, w), dtype=np.uint8)

    for mode_key in ('d', 'l'):
        hsv_vals = MODES[mode_key]['hsv']
        if len(hsv_vals) >= 1:
            lower, upper = compute_range(hsv_vals)
            m = cv2.inRange(hsv_full, lower, upper)
            shelf_mask = cv2.bitwise_or(shelf_mask, m)

    yogurt_vals = MODES['y']['hsv']
    if len(yogurt_vals) >= 1:
        lower_y, upper_y = compute_range(yogurt_vals,
                                         tolerance_h=12,
                                         tolerance_s=20,
                                         tolerance_v=25)
        yogurt_mask = cv2.inRange(hsv_full, lower_y, upper_y)

    # Shelf minus yogurt overlap = final clean shelf mask
    final = cv2.bitwise_and(shelf_mask,
                            cv2.bitwise_not(yogurt_mask))

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    final  = cv2.morphologyEx(final, cv2.MORPH_OPEN,  kernel)
    final  = cv2.morphologyEx(final, cv2.MORPH_CLOSE, kernel)

    return final


# ════════════════════════════════════════════════════════════════════
# DISPLAY
# ════════════════════════════════════════════════════════════════════

def build_display(img_orig: np.ndarray,
                  hsv_full: np.ndarray,
                  image_path: str) -> np.ndarray:
    """
    Build the full display panel:
      LEFT  — original image with all clicked dots
      RIGHT — live red overlay showing current shelf detection
    """
    display = img_orig.copy()
    h, w    = display.shape[:2]

    # ── Draw all clicked dots ────────────────────────────────────────
    for mode_key, mode_data in MODES.items():
        color = mode_data['color']
        for (px, py) in mode_data['points']:
            cv2.circle(display, (px, py), 6, color, -1)
            cv2.circle(display, (px, py), 7, (255, 255, 255), 1)

    # ── Build live mask preview ──────────────────────────────────────
    mask          = build_preview_mask(hsv_full)
    overlay       = img_orig.copy()
    overlay[mask > 0] = [0, 0, 200]

    # Count stats
    total_px = mask.shape[0] * mask.shape[1]
    shelf_px = cv2.countNonZero(mask)
    stock_pct = round(((total_px - shelf_px) / total_px) * 100, 1) if total_px > 0 else 0

    # ── HUD panel ────────────────────────────────────────────────────
    hud_height = 160
    hud        = np.zeros((hud_height, w * 2, 3), dtype=np.uint8)
    hud[:]     = (30, 30, 30)

    font  = cv2.FONT_HERSHEY_SIMPLEX
    small = 0.42
    med   = 0.52

    # Current mode indicator
    mode_color = MODES[current_mode]['color']
    mode_name  = MODES[current_mode]['name']
    cv2.rectangle(hud, (0, 0), (w * 2, 30), mode_color, -1)
    cv2.putText(hud, f"ACTIVE MODE: {mode_name}",
                (10, 22), font, med, (0, 0, 0), 2)

    # Controls legend
    controls = [
        ("D", MODES['d']['color'], f"Dark shelf  ({len(MODES['d']['hsv'])} pts)"),
        ("L", MODES['l']['color'], f"Light shelf ({len(MODES['l']['hsv'])} pts)"),
        ("Y", MODES['y']['color'], f"Yogurt excl ({len(MODES['y']['hsv'])} pts)"),
    ]
    for i, (key, col, label) in enumerate(controls):
        x = 10 + i * (w * 2 // 3)
        cv2.circle(hud, (x + 12, 55), 8, col, -1)
        cv2.putText(hud, f"[{key}] {label}",
                    (x + 26, 60), font, small, (220, 220, 220), 1)

    # Action keys
    actions = "[C] Clear mode   [R] Reset all   [S] Save config   [Q] Quit"
    cv2.putText(hud, actions, (10, 90), font, small, (180, 180, 180), 1)

    # Live stock estimate
    cv2.putText(hud, f"Live stock estimate: {stock_pct}%",
                (10, 120), font, med, (0, 255, 120), 1)
    cv2.putText(hud, f"Image: {os.path.basename(image_path)}",
                (10, 148), font, small, (140, 140, 140), 1)

    # ── Column headers ────────────────────────────────────────────────
    header      = np.zeros((28, w * 2, 3), dtype=np.uint8)
    header[:]   = (50, 50, 50)
    cv2.putText(header, "ORIGINAL  (click to sample)",
                (10, 20), font, small, (200, 200, 200), 1)
    cv2.putText(header, "LIVE MASK  (red = detected shelf)",
                (w + 10, 20), font, small, (0, 0, 200), 1)

    # ── Stitch everything together ───────────────────────────────────
    side_by_side = np.hstack([display, overlay])
    full_display = np.vstack([hud, header, side_by_side])

    return full_display


# ════════════════════════════════════════════════════════════════════
# CONFIG GENERATION
# ════════════════════════════════════════════════════════════════════

def generate_shelf_monitor(image_path: str,
                            dark_lower,  dark_upper,
                            light_lower, light_upper,
                            yog_lower,   yog_upper) -> str:
    """Generate the complete shelf_monitor.py with calibrated values."""

    def arr(a):
        return f"np.array([{a[0]:3d}, {a[1]:3d}, {a[2]:3d}])"

    dark_l  = arr(dark_lower)
    dark_u  = arr(dark_upper)
    light_l = arr(light_lower)
    light_u = arr(light_upper)

    has_yogurt = len(MODES['y']['hsv']) > 0

    yog_exclude = ""
    if has_yogurt:
        yog_exclude = f"""
    # Remove any yogurt pixels that leaked into the shelf mask
    yogurt_mask = cv2.inRange(hsv, YOGURT_LOWER, YOGURT_UPPER)
    combined    = cv2.bitwise_and(combined, cv2.bitwise_not(yogurt_mask))
"""

    yog_config = ""
    if has_yogurt:
        yog_config = f"""
# Yogurt packaging range (used to EXCLUDE false positives)
YOGURT_LOWER = {arr(yog_lower)}
YOGURT_UPPER = {arr(yog_upper)}
"""

    script = f'''"""
========================================================================
  SHELF MONITORING SYSTEM — Auto-generated by hsv_calibrator.py
  Calibrated : {datetime.now().strftime("%Y-%m-%d %H:%M")}
  Source img : {os.path.basename(image_path)}
========================================================================
"""

import cv2
import numpy as np
import sys
import os

# ============================================================
# SECTION 1 — CONFIGURATION  (auto-calibrated)
# ============================================================

# Dark shelf areas (shadows, back of shelf)
SHELF_DARK_LOWER  = {dark_l}
SHELF_DARK_UPPER  = {dark_u}

# Light shelf areas (front edges, bright zones)
SHELF_LIGHT_LOWER = {light_l}
SHELF_LIGHT_UPPER = {light_u}
{yog_config}
ALERT_THRESHOLD_PCT = 30.0
MORPH_KERNEL_SIZE   = 7

# Crop: (y1, y2, x1, x2) — set to None to use full image
ROI_COORDS: tuple[int, int, int, int] | None = (30, 478, 0, 286) 


# ============================================================
# SECTION 2 — CORE FUNCTIONS
# ============================================================

def load_and_crop(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot load: \\'{{image_path}}\\'")
    print(f"  Image shape    : {{img.shape}}")
    if ROI_COORDS is not None:
        y1, y2, x1, x2 = ROI_COORDS
        img = img[y1:y2, x1:x2]
        print(f"  After ROI crop : {{img.shape}}")
    return img


def build_shelf_mask(bgr_crop: np.ndarray) -> np.ndarray:
    hsv      = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)

    mask_dark  = cv2.inRange(hsv, SHELF_DARK_LOWER,  SHELF_DARK_UPPER)
    mask_light = cv2.inRange(hsv, SHELF_LIGHT_LOWER, SHELF_LIGHT_UPPER)
    combined   = cv2.bitwise_or(mask_dark, mask_light)
{yog_exclude}
    kernel  = cv2.getStructuringElement(
                  cv2.MORPH_RECT,
                  (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  kernel)
    cleaned = cv2.morphologyEx(cleaned,  cv2.MORPH_CLOSE, kernel)
    return cleaned


def calculate_stock(mask: np.ndarray) -> dict:
    total_pixels         = mask.shape[0] * mask.shape[1]
    visible_shelf_pixels = cv2.countNonZero(mask)
    yogurt_pixels        = total_pixels - visible_shelf_pixels
    stock_pct            = (yogurt_pixels / total_pixels) * 100
    return {{
        "total_pixels"         : total_pixels,
        "visible_shelf_pixels" : visible_shelf_pixels,
        "yogurt_pixels"        : yogurt_pixels,
        "stock_pct"            : round(stock_pct, 2),
        "empty_pct"            : round(100 - stock_pct, 2),
    }}


def save_debug_image(bgr_crop: np.ndarray,
                     mask: np.ndarray,
                     output_path: str,
                     stock_pct: float) -> None:
    overlay = bgr_crop.copy()
    overlay[mask > 0] = [0, 0, 220]

    orig_lab = bgr_crop.copy()
    cv2.putText(orig_lab, "ORIGINAL",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    cv2.putText(overlay, f"RED=SHELF | Stock: {{stock_pct}} %",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,220), 1)

    debug   = np.vstack([orig_lab, overlay])
    scale   = 900 / debug.shape[0]
    w_new   = int(debug.shape[1] * scale)
    debug   = cv2.resize(debug, (w_new, 900), interpolation=cv2.INTER_LINEAR)
    mid     = 900 // 2
    cv2.line(debug, (0, mid), (w_new, mid), (255,255,255), 2)
    cv2.imwrite(output_path, debug)
    print(f"  Debug saved → {{output_path}}")


def print_results(image_name: str, metrics: dict) -> None:
    sep = "─" * 45
    print(f"\\n{{sep}}")
    print(f"  Image            : {{image_name}}")
    print(f"  Total ROI pixels : {{metrics['total_pixels']:,}}")
    print(f"  Shelf pixels     : {{metrics['visible_shelf_pixels']:,}} "
          f"( {{metrics['empty_pct']}} % empty)")
    print(f"  Yogurt pixels    : {{metrics['yogurt_pixels']:,}} "
          f"( {{metrics['stock_pct']}} % filled)")
    print(f"{{sep}}")
    if metrics["stock_pct"] < ALERT_THRESHOLD_PCT:
        print(f"\\n  🚨 ALARM: STOCK CRITICAL 🚨")
        print(f"  Stock ( {{metrics['stock_pct']}} %) below {{ALERT_THRESHOLD_PCT}}%!\\n")
    else:
        print(f"\\n  ✅ Stock OK — {{metrics['stock_pct']}} % remaining\\n")


def analyze_image(image_path: str) -> dict:
    crop    = load_and_crop(image_path)
    mask    = build_shelf_mask(crop)
    metrics = calculate_stock(mask)
    print_results(os.path.basename(image_path), metrics)
    debug_path = image_path.replace(".", "_debug.")
    save_debug_image(crop, mask, debug_path, metrics["stock_pct"])
    return metrics


# ============================================================
# SECTION 3 — ENTRY POINT
# ============================================================

if __name__ == "__main__":
    image = sys.argv[1] if len(sys.argv) > 1 else "base one.png"
    analyze_image(image)
'''
    return script


# ════════════════════════════════════════════════════════════════════
# SAVE
# ════════════════════════════════════════════════════════════════════

def save_results(image_path: str) -> None:
    """Compute final ranges and write shelf_monitor.py."""

    dark_lower,  dark_upper  = compute_range(MODES['d']['hsv'],
                                             tolerance_h=8,
                                             tolerance_s=12,
                                             tolerance_v=20)
    light_lower, light_upper = compute_range(MODES['l']['hsv'],
                                             tolerance_h=8,
                                             tolerance_s=12,
                                             tolerance_v=20)
    yog_lower,   yog_upper   = compute_range(MODES['y']['hsv'],
                                             tolerance_h=12,
                                             tolerance_s=20,
                                             tolerance_v=25)

    has_dark  = len(MODES['d']['hsv']) > 0
    has_light = len(MODES['l']['hsv']) > 0
    has_yogurt = len(MODES['y']['hsv']) > 0

    print("\n" + "═" * 50)
    print("  CALIBRATION SUMMARY")
    print("═" * 50)

    if has_dark:
        print(f"\n  DARK SHELF  ({len(MODES['d']['hsv'])} points)")
        print(f"    LOWER = {dark_lower.tolist()}")
        print(f"    UPPER = {dark_upper.tolist()}")
    else:
        print("\n  ⚠️  No dark shelf points — skipped")

    if has_light:
        print(f"\n  LIGHT SHELF  ({len(MODES['l']['hsv'])} points)")
        print(f"    LOWER = {light_lower.tolist()}")
        print(f"    UPPER = {light_upper.tolist()}")
    else:
        print("\n  ⚠️  No light shelf points — skipped")

    if has_yogurt:
        print(f"\n  YOGURT EXCLUDE  ({len(MODES['y']['hsv'])} points)")
        print(f"    LOWER = {yog_lower.tolist()}")
        print(f"    UPPER = {yog_upper.tolist()}")
    else:
        print("\n  ℹ️  No yogurt points — exclusion mask not applied")

    # Write the final shelf_monitor.py
    script_content = generate_shelf_monitor(
        image_path,
        dark_lower,  dark_upper,
        light_lower, light_upper,
        yog_lower,   yog_upper,
    )

    out_path = "shelf_monitor1.py"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    print(f"\n  ✅ shelf_monitor.py written → {out_path}")
    print(f"  Run it with:  python shelf_monitor.py {os.path.basename(image_path)}")
    print("═" * 50 + "\n")


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

def main():
    global current_mode

    image_path = sys.argv[1] if len(sys.argv) > 1 else "base one.png"

    _img_orig = cv2.imread(image_path)
    if _img_orig is None:
        print(f"Error: cannot load '{image_path}'")
        sys.exit(1)
    img_orig: np.ndarray = _img_orig
    hsv_full: np.ndarray = cv2.cvtColor(img_orig, cv2.COLOR_BGR2HSV)

    print("\n" + "═" * 50)
    print("  HSV CALIBRATOR — Multi-Zone Shelf Sampler")
    print("═" * 50)
    print("  D → dark shelf    L → light shelf    Y → yogurt")
    print("  C → clear mode    R → reset all")
    print("  S → save config   Q → quit")
    print("═" * 50 + "\n")

    def on_click(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        orig_x = min(x, img_orig.shape[1] - 1)
        orig_y = min(max(0,y-188), img_orig.shape[0] - 1)

        h, s, v = hsv_full[orig_y, orig_x]
        MODES[current_mode]['points'].append((orig_x, orig_y))
        MODES[current_mode]['hsv'].append((int(h), int(s), int(v)))

        mode_name = MODES[current_mode]['name']
        print(f"  [{mode_name}] pixel ({orig_x:3d},{orig_y:3d}) "
              f"→ HSV: H={h:3d}  S={s:3d}  V={v:3d}")

        # Refresh display
        frame = build_display(img_orig, hsv_full, image_path)
        cv2.imshow(win_name, frame)

    win_name = "HSV Calibrator  |  D=dark  L=light  Y=yogurt  S=save  Q=quit"
    frame    = build_display(img_orig, hsv_full, image_path)
    cv2.imshow(win_name, frame)
    cv2.setMouseCallback(win_name, on_click)

    while True:
        key = cv2.waitKey(20) & 0xFF

        if key in (ord('q'), ord('Q'), 27):
            print("  Quit without saving.")
            break

        elif key in (ord('d'), ord('D')):
            current_mode = 'd'
            print(f"\n  ── MODE: DARK SHELF ──")

        elif key in (ord('l'), ord('L')):
            current_mode = 'l'
            print(f"\n  ── MODE: LIGHT SHELF ──")

        elif key in (ord('y'), ord('Y')):
            current_mode = 'y'
            print(f"\n  ── MODE: YOGURT (exclude) ──")

        elif key in (ord('c'), ord('C')):
            count = len(MODES[current_mode]['points'])
            MODES[current_mode]['points'].clear()
            MODES[current_mode]['hsv'].clear()
            print(f"  Cleared {count} points from {MODES[current_mode]['name']}")

        elif key in (ord('r'), ord('R')):
            for m in MODES.values():
                m['points'].clear()
                m['hsv'].clear()
            print("  Reset — all points cleared.")

        elif key in (ord('s'), ord('S')):
            total = sum(len(m['hsv']) for m in MODES.values())
            if total == 0:
                print("  ⚠️  No points sampled yet — click on the image first.")
            else:
                save_results(image_path)
                break

        else:
            continue

        # Refresh display after any keypress
        frame = build_display(img_orig, hsv_full, image_path)
        cv2.imshow(win_name, frame)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()