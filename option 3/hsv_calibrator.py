"""
========================================================================
  HSV CALIBRATOR - Run this ONCE on setup day
  Usage : python hsv_calibrator.py <reference_photo.jpg>

  WHAT THIS DOES
  --------------
  1. You draw a crop box  -> defines the shelf area for ALL future photos
  2. You click shelf colors (dark + light zones)
  3. You click yogurt colors (to exclude from mask)
  4. Press S -> saves shelf_config.json
  5. Never run this again unless camera is moved or shelf repainted

  OUTPUT
  ------
  shelf_config.json  <- read automatically by shelf_monitor.py + watcher.py
========================================================================

KEYBOARD CONTROLS
-----------------
  PHASE 1 - Crop box (always starts here)
    Click + drag on image -> draw the shelf crop region
    Press ENTER           -> confirm crop, move to Phase 2

  PHASE 2 - Color sampling
    D -> DARK SHELF mode   (shadow / back-of-shelf)
    L -> LIGHT SHELF mode  (bright / front-of-shelf)
    Y -> YOGURT mode       (lids / packaging -> exclude)
    C -> clear current mode points
    R -> reset all points (keeps crop)
    S -> save shelf_config.json and exit
    Q -> quit without saving
"""

import cv2
import numpy as np
import sys
import os
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WIN_H        = 700
CONFIG_PATH  = os.path.join(_SCRIPT_DIR, "shelf_config.json")

MODES = {
    'd': {'name': 'DARK SHELF',       'color': (0, 165, 255), 'points': [], 'hsv': []},
    'l': {'name': 'LIGHT SHELF',      'color': (0, 255, 255), 'points': [], 'hsv': []},
    'y': {'name': 'YOGURT (exclude)', 'color': (0,   0, 255), 'points': [], 'hsv': []},
}


def _find_image(path_arg: str | None) -> str | None:
    if path_arg and os.path.isfile(path_arg):
        return path_arg
    candidates: list[str | None] = [
        path_arg,
        os.path.join(_SCRIPT_DIR, path_arg) if path_arg else None,
        os.path.join(_SCRIPT_DIR, "base one.png"),
        os.path.join(os.path.dirname(_SCRIPT_DIR), "base one.png"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return path_arg


def compute_range(hsv_values: list, tol_h=10, tol_s=15, tol_v=25) -> tuple:
    if not hsv_values:
        return None, None
    h = [v[0] for v in hsv_values]
    s = [v[1] for v in hsv_values]
    v = [v[2] for v in hsv_values]
    lower = np.array([
        max(0,   min(h)-tol_h),
        max(0,   min(s)-tol_s),
        max(0,   min(v)-tol_v),
    ], dtype=np.uint8)
    upper = np.array([
        min(179, max(h)+tol_h),
        min(255, max(s)+tol_s),
        min(255, max(v)+tol_v),
    ], dtype=np.uint8)
    return lower, upper


def build_preview_mask(hsv_crop: np.ndarray) -> np.ndarray:
    h, w       = hsv_crop.shape[:2]
    shelf_mask = np.zeros((h, w), dtype=np.uint8)

    for key in ('d', 'l'):
        lower, upper = compute_range(MODES[key]['hsv'])
        if lower is not None and upper is not None:
            shelf_mask = cv2.bitwise_or(shelf_mask,
                         cv2.inRange(hsv_crop, lower, upper))

    yog_l, yog_u = compute_range(MODES['y']['hsv'], tol_h=12, tol_s=20, tol_v=25)
    if yog_l is not None and yog_u is not None:
        yogurt_mask = cv2.inRange(hsv_crop, yog_l, yog_u)
        shelf_mask  = cv2.bitwise_and(shelf_mask, cv2.bitwise_not(yogurt_mask))

    k          = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    shelf_mask = cv2.morphologyEx(shelf_mask, cv2.MORPH_OPEN,  k)
    shelf_mask = cv2.morphologyEx(shelf_mask, cv2.MORPH_CLOSE, k)
    return shelf_mask


def build_phase1_display(img_orig: np.ndarray, scale: float,
                         crop_box: tuple | None,
                         drag_start: tuple | None,
                         drag_current: tuple | None) -> tuple[np.ndarray, int]:
    ih, iw   = img_orig.shape[:2]
    disp_h   = int(ih * scale)
    disp_w   = int(iw * scale)
    disp     = cv2.resize(img_orig, (disp_w, disp_h))

    if drag_start and drag_current:
        x1 = int(drag_start[0]   * scale)
        y1 = int(drag_start[1]   * scale)
        x2 = int(drag_current[0] * scale)
        y2 = int(drag_current[1] * scale)
        cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(disp, "Release to set crop",
                    (x1+4, y1+20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,0), 1)

    if crop_box:
        cx1,cy1,cx2,cy2 = crop_box
        cv2.rectangle(disp,
                      (int(cx1*scale), int(cy1*scale)),
                      (int(cx2*scale), int(cy2*scale)),
                      (0, 255, 0), 2)
        cv2.putText(disp, "Crop: ({},{}) to ({},{})".format(cx1, cy1, cx2, cy2),
                    (int(cx1*scale)+4, int(cy1*scale)+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,0), 1)

    hud_h  = 70
    hud    = np.zeros((hud_h, disp_w, 3), dtype=np.uint8)
    hud[:] = (30, 30, 30)
    font   = cv2.FONT_HERSHEY_SIMPLEX
    cv2.rectangle(hud, (0,0), (disp_w, 28), (0,180,0), -1)
    cv2.putText(hud, "PHASE 1 - Draw crop box around the shelf",
                (8, 20), font, 0.50, (0,0,0), 2)
    cv2.putText(hud,
                "Click + drag to draw box | ENTER to confirm | Q to quit",
                (8, 55), font, 0.38, (200,200,200), 1)

    return np.vstack([hud, disp]), hud_h


def build_phase2_display(img_crop: np.ndarray, hsv_crop: np.ndarray,
                         scale: float, crop_box: tuple,
                         current_mode: str) -> tuple[np.ndarray, int]:
    ih, iw     = img_crop.shape[:2]
    disp_h     = int(ih * scale)
    disp_w     = int(iw * scale)

    left       = cv2.resize(img_crop.copy(), (disp_w, disp_h))

    mask       = build_preview_mask(hsv_crop)
    right_full = img_crop.copy()
    right_full[mask > 0] = [0, 0, 200]
    right      = cv2.resize(right_full, (disp_w, disp_h))

    total_px  = mask.shape[0] * mask.shape[1]
    shelf_px  = cv2.countNonZero(mask)
    stock_pct = round(((total_px - shelf_px) / total_px) * 100, 1) if total_px > 0 else 0

    for key, data in MODES.items():
        for (px, py) in data['points']:
            sx, sy = int(px * scale), int(py * scale)
            cv2.circle(left, (sx, sy), 5, data['color'], -1)
            cv2.circle(left, (sx, sy), 6, (255,255,255), 1)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(left,  "CROPPED SHELF - click to sample",
                (6, 16), font, 0.38, (255,255,255), 1)
    cv2.putText(right, "LIVE MASK - Stock: {}%".format(stock_pct),
                (6, 16), font, 0.38, (0,0,220), 1)

    panels = np.hstack([left, right])

    hud_h  = 85
    hud    = np.zeros((hud_h, disp_w*2, 3), dtype=np.uint8)
    hud[:] = (30,30,30)

    mode_col = MODES[current_mode]['color']
    cv2.rectangle(hud, (0,0), (disp_w*2, 28), mode_col, -1)
    cv2.putText(hud,
                "PHASE 2 - MODE: {}  ({} pts)".format(
                    MODES[current_mode]['name'], len(MODES[current_mode]['hsv'])),
                (8, 20), font, 0.50, (0,0,0), 2)

    d = len(MODES['d']['hsv'])
    l = len(MODES['l']['hsv'])
    y = len(MODES['y']['hsv'])
    cv2.putText(hud,
                "[D] Dark shelf({})  [L] Light shelf({})  [Y] Yogurt({})"
                "   [C] Clear  [R] Reset  [S] Save & exit  [Q] Quit".format(d, l, y),
                (8, 55), font, 0.38, (200,200,200), 1)
    cv2.putText(hud,
                "Stock estimate: {}%   Crop: {}".format(stock_pct, crop_box),
                (8, 78), font, 0.38, (0,255,120), 1)

    return np.vstack([hud, panels]), hud_h


def save_config(image_path: str, img_orig: np.ndarray,
                crop_box: tuple | None) -> bool:
    if crop_box is None:
        print("  Warning: No crop box defined. Draw the crop box first.")
        return False

    dark_l,  dark_u  = compute_range(MODES['d']['hsv'])
    light_l, light_u = compute_range(MODES['l']['hsv'])
    yog_l,   yog_u   = compute_range(MODES['y']['hsv'],
                                     tol_h=12, tol_s=20, tol_v=25)

    if dark_l is None and light_l is None:
        print("  Warning: No shelf color points. Sample shelf colors first.")
        return False

    ih, iw = img_orig.shape[:2]
    x1, y1, x2, y2 = crop_box

    config = {
        "roi"               : [int(y1), int(y2), int(x1), int(x2)],
        "shelf_dark_lower"  : dark_l.tolist()  if dark_l  is not None else None,
        "shelf_dark_upper"  : dark_u.tolist()  if dark_u  is not None else None,
        "shelf_light_lower" : light_l.tolist() if light_l is not None else None,
        "shelf_light_upper" : light_u.tolist() if light_u is not None else None,
        "yogurt_lower"      : yog_l.tolist()   if yog_l   is not None else None,
        "yogurt_upper"      : yog_u.tolist()   if yog_u   is not None else None,
        "morph_kernel"      : 7,
        "alert_threshold"   : 30.0,
        "calibrated_on"     : os.path.basename(image_path),
        "image_size"        : [iw, ih],
    }

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    print()
    print("=" * 50)
    print("  shelf_config.json saved successfully")
    print("  Crop ROI         : y={}->{}, x={}->{}".format(y1, y2, x1, x2))
    if dark_l is not None and dark_u is not None:
        print("  Dark shelf       : {} / {}".format(dark_l.tolist(), dark_u.tolist()))
    if light_l is not None and light_u is not None:
        print("  Light shelf      : {} / {}".format(light_l.tolist(), light_u.tolist()))
    if yog_l is not None and yog_u is not None:
        print("  Yogurt exclude   : {} / {}".format(yog_l.tolist(), yog_u.tolist()))
    print()
    print("  Next steps:")
    print("  1. python shelf_monitor.py <any_photo.jpg>")
    print("  2. python watcher.py")
    print("=" * 50)
    print()
    return True


def main() -> None:
    image_path = _find_image(sys.argv[1] if len(sys.argv) > 1 else None)
    if image_path is None or not os.path.isfile(image_path):
        print("  Error: no image found.")
        print("  Usage: python hsv_calibrator.py <photo.jpg>")
        sys.exit(1)

    img_orig = cv2.imread(image_path)
    if img_orig is None:
        print("  Cannot load '{}'".format(image_path))
        sys.exit(1)

    ih, iw = img_orig.shape[:2]
    scale_p1 = WIN_H / ih

    crop_box:     tuple | None = None
    drawing_crop  = False
    drag_start:   tuple | None = None
    drag_current: tuple | None = None
    phase         = 1
    current_mode  = 'd'
    img_crop:     np.ndarray | None = None
    hsv_crop:     np.ndarray | None = None

    print()
    print("  Image: {}  ({}x{} px)".format(os.path.basename(image_path), iw, ih))
    print("  PHASE 1: Click and drag to draw the shelf crop box.")
    print("           Press ENTER to confirm.")
    print()

    win = "Shelf Calibrator | ENTER=confirm crop | S=save | Q=quit"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    def on_mouse(event: int, wx: int, wy: int, flags: int, param) -> None:
        nonlocal crop_box, drawing_crop, drag_start, drag_current, phase
        nonlocal img_crop, hsv_crop, current_mode

        if phase == 1:
            ix = int(wx / scale_p1)
            iy = int((wy - 70) / scale_p1)
            ix = max(0, min(ix, iw-1))
            iy = max(0, min(iy, ih-1))

            if event == cv2.EVENT_LBUTTONDOWN:
                drawing_crop = True
                drag_start   = (ix, iy)
                drag_current = (ix, iy)

            elif event == cv2.EVENT_MOUSEMOVE and drawing_crop:
                drag_current = (ix, iy)
                frame, _ = build_phase1_display(
                    img_orig, scale_p1, crop_box, drag_start, drag_current)
                cv2.imshow(win, frame)

            elif event == cv2.EVENT_LBUTTONUP and drawing_crop:
                drawing_crop = False
                assert drag_start is not None
                x1 = min(drag_start[0], ix)
                y1 = min(drag_start[1], iy)
                x2 = max(drag_start[0], ix)
                y2 = max(drag_start[1], iy)
                if (x2-x1) > 10 and (y2-y1) > 10:
                    crop_box = (x1, y1, x2, y2)
                    print("  Crop box set: x={}->{}, y={}->{}  ({}x{} px)".format(
                        x1, x2, y1, y2, x2-x1, y2-y1))
                    print("  Press ENTER to confirm and move to color sampling.")
                drag_current = None
                frame, _ = build_phase1_display(
                    img_orig, scale_p1, crop_box, drag_start, drag_current)
                cv2.imshow(win, frame)

        elif phase == 2:
            if event != cv2.EVENT_LBUTTONDOWN:
                return
            if crop_box is None or img_crop is None or hsv_crop is None:
                return

            crop_w = crop_box[2] - crop_box[0]
            crop_h = crop_box[3] - crop_box[1]
            scale_p2 = WIN_H / max(crop_h, 1)

            panel_w = int(crop_w * scale_p2)
            hud_h = 85

            if wx > panel_w:
                wx = wx - panel_w

            cx = int(wx / scale_p2)
            cy = int((wy - hud_h) / scale_p2)
            cx = max(0, min(cx, crop_w-1))
            cy = max(0, min(cy, crop_h-1))

            hv, hs, hval = hsv_crop[cy, cx]
            MODES[current_mode]['points'].append((cx, cy))
            MODES[current_mode]['hsv'].append((int(hv), int(hs), int(hval)))

            print("  [{}] ({:3d},{:3d}) -> H={:3d} S={:3d} V={:3d}".format(
                MODES[current_mode]['name'], cx, cy, hv, hs, hval))

            frame, _ = build_phase2_display(
                img_crop, hsv_crop, scale_p2, crop_box, current_mode)
            cv2.imshow(win, frame)

    cv2.setMouseCallback(win, on_mouse)

    frame, _ = build_phase1_display(img_orig, scale_p1, None, None, None)
    h_panel = frame.shape[0]
    w_panel = frame.shape[1]
    win_w   = int(w_panel * WIN_H / h_panel)
    cv2.resizeWindow(win, win_w, WIN_H)
    cv2.imshow(win, frame)

    while True:
        key = cv2.waitKey(20) & 0xFF

        if key in (ord('q'), ord('Q'), 27):
            print("  Quit without saving.")
            break

        elif key == 13 and phase == 1:
            if crop_box is None:
                print("  Warning: Draw a crop box first.")
                continue
            phase = 2
            x1, y1, x2, y2 = crop_box
            img_crop = img_orig[y1:y2, x1:x2]
            hsv_crop = cv2.cvtColor(img_crop, cv2.COLOR_BGR2HSV)

            crop_h = crop_box[3] - crop_box[1]
            scale_p2 = WIN_H / max(crop_h, 1)

            print()
            print("  Crop confirmed: {}x{} px".format(
                img_crop.shape[1], img_crop.shape[0]))
            print("  PHASE 2: Sample shelf colors.")
            print("  [D] Dark shelf  [L] Light shelf  [Y] Yogurt  [S] Save")
            print()

            frame, _ = build_phase2_display(
                img_crop, hsv_crop, scale_p2, crop_box, current_mode)
            w_panel = frame.shape[1]
            h_panel = frame.shape[0]
            win_w   = int(w_panel * WIN_H / h_panel)
            cv2.resizeWindow(win, win_w, WIN_H)
            cv2.imshow(win, frame)

        elif phase == 2:
            if   key in (ord('d'), ord('D')):
                current_mode = 'd'
                print()
                print("  --- MODE: DARK SHELF ---")
            elif key in (ord('l'), ord('L')):
                current_mode = 'l'
                print()
                print("  --- MODE: LIGHT SHELF ---")
            elif key in (ord('y'), ord('Y')):
                current_mode = 'y'
                print()
                print("  --- MODE: YOGURT (exclude) ---")
            elif key in (ord('c'), ord('C')):
                n = len(MODES[current_mode]['points'])
                MODES[current_mode]['points'].clear()
                MODES[current_mode]['hsv'].clear()
                print("  Cleared {} pts from {}".format(
                    n, MODES[current_mode]['name']))
            elif key in (ord('r'), ord('R')):
                for m in MODES.values():
                    m['points'].clear()
                    m['hsv'].clear()
                print("  Reset - all color points cleared.")
            elif key in (ord('s'), ord('S')):
                if save_config(image_path, img_orig, crop_box):
                    break
                continue
            else:
                continue

            if crop_box is None or img_crop is None or hsv_crop is None:
                continue
            crop_h = crop_box[3] - crop_box[1]
            scale_p2 = WIN_H / max(crop_h, 1)
            frame, _ = build_phase2_display(
                img_crop, hsv_crop, scale_p2, crop_box, current_mode)
            cv2.imshow(win, frame)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
