"""
One-time setup tool — run this ONCE after installing the camera.

Usage:  python hsv_calibrator.py <reference_photo.jpg>

Three phases:
  1. Crop — drag a box around the shelf area
  2. Sample — click on shelf surfaces to teach the color model
  3. Exclude — mark price tags / banners that should be ignored

Produces shelf_config.json, which shelf_monitor.py and watcher.py read.
Never run this again unless you move the camera or repaint the shelf.

Controls (varies by phase — look at the HUD bar at the top):
  Phase 1: Click + drag to draw box, ENTER to confirm
  Phase 2: D/L/Y/I to switch color modes, click to sample, S to proceed
  Phase 3: Click + drag to draw exclusion rects, ENTER to save
  Q at any time to quit without saving
"""

import cv2
import numpy as np
import sys
import os
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WIN_H        = 700
CONFIG_PATH  = os.path.join(_SCRIPT_DIR, "shelf_config.json")

# Each mode stores clicked points and their HSV values separately.
# The tool blends dark + light shelf ranges into one detection mask,
# then subtracts yogurt (product) areas so only empty shelf is counted.
MODES = {
    'd': {'name': 'DARK SHELF',         'color': (0, 165, 255), 'points': [], 'hsv': []},
    'l': {'name': 'LIGHT SHELF',        'color': (0, 255, 255), 'points': [], 'hsv': []},
    'y': {'name': 'YOGURT (exclude)',   'color': (0,   0, 255), 'points': [], 'hsv': []},
    'i': {'name': 'IGNORE / TAGS',      'color': (255, 120, 0), 'points': [], 'hsv': []},
}


def _find_image(path_arg: str | None) -> str | None:
    """Try several locations for the reference photo.
    Checks: exact path → script dir → parent dir → common filenames."""
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
    """Take a list of clicked HSV points and expand them into a
    detection range by adding tolerance on each axis.
    Tolerance values are generous because real-world lighting changes."""
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
    """Build a binary mask showing where the shelf surface is detected.
    Combines dark + light ranges, subtracts yogurt colors,
    then cleans up noise with morphological operations.
    This is shown live in Phase 2 so you can adjust your samples."""
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
    """Render the Phase 1 UI: full image with HUD on top.
    Shows the drag rectangle in real time as the user draws."""
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


def build_phase3_display(img_crop: np.ndarray, scale: float,
                          exclude_rects: list,
                          drag_start: tuple | None,
                          drag_current: tuple | None) -> tuple[np.ndarray, int]:
    """Render Phase 3 UI: cropped shelf with exclusion rectangles overlaid.
    User draws boxes around price tags that should not count as 'empty'."""
    ih, iw   = img_crop.shape[:2]
    disp_h   = int(ih * scale)
    disp_w   = int(iw * scale)
    disp     = cv2.resize(img_crop.copy(), (disp_w, disp_h))

    for ey1, ey2, ex1, ex2 in exclude_rects:
        cv2.rectangle(disp,
                      (int(ex1*scale), int(ey1*scale)),
                      (int(ex2*scale), int(ey2*scale)),
                      (255, 100, 0), 2)
        cv2.putText(disp, "excluded",
                    (int(ex1*scale)+4, int(ey1*scale)+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,100,0), 1)

    if drag_start and drag_current:
        x1 = int(drag_start[1] * scale)
        y1 = int(drag_start[0] * scale)
        x2 = int(drag_current[1] * scale)
        y2 = int(drag_current[0] * scale)
        cv2.rectangle(disp, (x1, y1), (x2, y2), (255, 200, 0), 2)
        cv2.putText(disp, "Release to add exclusion",
                    (x1+4, y1+20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,200,0), 1)

    hud_h = 70
    hud   = np.zeros((hud_h, disp_w, 3), dtype=np.uint8)
    hud[:] = (30, 30, 30)
    cv2.rectangle(hud, (0,0), (disp_w, 28), (255,100,0), -1)
    cv2.putText(hud, "PHASE 3 - Draw exclusion rectangles around price tags",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,0), 2)
    cv2.putText(hud,
                "Click + drag to draw box  [C] Clear  [ENTER] Save  [Q] Back",
                (8, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200,200,200), 1)

    return np.vstack([hud, disp]), hud_h


def build_phase2_display(img_crop: np.ndarray, hsv_crop: np.ndarray,
                         scale: float, crop_box: tuple,
                         current_mode: str) -> tuple[np.ndarray, int]:
    """Render Phase 2 UI: side-by-side shelf image + live mask preview.
    Left: cropped shelf with colored dots showing sampled points.
    Right: detection mask (shelf turned red) + stock percentage.
    The live preview updates after every click so you can iterate."""
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
    i = len(MODES['i']['hsv'])
    cv2.putText(hud,
                "[D] Dark shelf({})  [L] Light shelf({})  [Y] Yogurt({})"
                "  [I] Ignore/tags({})   [C] Clear  [R] Reset  [S] Save  [Q] Quit".format(d, l, y, i),
                (8, 55), font, 0.38, (200,200,200), 1)
    cv2.putText(hud,
                "Stock estimate: {}%   Crop: {}".format(stock_pct, crop_box),
                (8, 78), font, 0.38, (0,255,120), 1)

    return np.vstack([hud, panels]), hud_h


def save_config(image_path: str, img_orig: np.ndarray,
                crop_box: tuple | None,
                exclude_rects: list | None = None) -> bool:
    """Save everything to shelf_config.json.
    Computes HSV ranges from the clicked points, bundles them with
    crop ROI, exclusion regions, and financial defaults."""
    if crop_box is None:
        print("  Warning: No crop box defined. Draw the crop box first.")
        return False

    dark_l,  dark_u  = compute_range(MODES['d']['hsv'])
    light_l, light_u = compute_range(MODES['l']['hsv'])
    yog_l,   yog_u   = compute_range(MODES['y']['hsv'],
                                     tol_h=12, tol_s=20, tol_v=25)
    ignore_l, ignore_u = compute_range(MODES['i']['hsv'],
                                       tol_h=10, tol_s=15, tol_v=25)

    if dark_l is None and light_l is None:
        print("  Warning: No shelf color points. Sample shelf colors first.")
        return False

    ih, iw = img_orig.shape[:2]
    x1, y1, x2, y2 = crop_box

    rects_list = []
    if exclude_rects:
        for ey1, ey2, ex1, ex2 in exclude_rects:
            rects_list.append([int(ey1), int(ey2), int(ex1), int(ex2)])

    config = {
        "roi"               : [int(y1), int(y2), int(x1), int(x2)],
        "shelf_dark_lower"  : dark_l.tolist()  if dark_l  is not None else None,
        "shelf_dark_upper"  : dark_u.tolist()  if dark_u  is not None else None,
        "shelf_light_lower" : light_l.tolist() if light_l is not None else None,
        "shelf_light_upper" : light_u.tolist() if light_u is not None else None,
        "yogurt_lower"      : yog_l.tolist()   if yog_l   is not None else None,
        "yogurt_upper"      : yog_u.tolist()   if yog_u   is not None else None,
        "ignore_lower"      : ignore_l.tolist() if ignore_l is not None else None,
        "ignore_upper"      : ignore_u.tolist() if ignore_u is not None else None,
        "exclude_regions"   : rects_list,
        "morph_kernel"      : 7,
        "alert_threshold"   : 30.0,
        "unit_price"        : 0.5,
        "currency"          : "TND",
        "sales_per_hour"    : 20,
        "scan_interval_hours": 0.25,
        "store_open"        : 8,
        "store_close"       : 22,
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
    if ignore_l is not None and ignore_u is not None:
        print("  Ignore/tags      : {} / {}".format(ignore_l.tolist(), ignore_u.tolist()))
    if rects_list:
        for i, r in enumerate(rects_list):
            print("  Exclude rect {}  : {}".format(i+1, r))
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

    crop_box:        tuple | None = None
    drawing_crop     = False
    drag_start:      tuple | None = None
    drag_current:    tuple | None = None
    phase            = 1
    current_mode     = 'd'
    img_crop:        np.ndarray | None = None
    hsv_crop:        np.ndarray | None = None
    scale_p2         = 1.0
    exclude_rects:   list[tuple] = []
    drawing_exclude  = False
    excl_start:      tuple | None = None
    excl_current:    tuple | None = None

    print()
    print("  Image: {}  ({}x{} px)".format(os.path.basename(image_path), iw, ih))
    print("  PHASE 1: Click and drag to draw the shelf crop box.")
    print("           Press ENTER to confirm.")
    print()

    win = "Shelf Calibrator | ENTER=confirm crop | S=save | Q=quit"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    def on_mouse(event: int, wx: int, wy: int, flags: int, param) -> None:
        """Central mouse handler — behavior changes by phase.
        Phase 1: drag to draw crop box.
        Phase 2: click on shelf areas to sample colors.
        Phase 3: drag to draw exclusion rectangles."""
        nonlocal crop_box, drawing_crop, drag_start, drag_current, phase
        nonlocal img_crop, hsv_crop, current_mode, scale_p2
        nonlocal exclude_rects, drawing_exclude, excl_start, excl_current

        if phase == 1:
            # Phase 1: drag to draw crop box
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
            # Phase 2: click to sample colors on the shelf
            if event != cv2.EVENT_LBUTTONDOWN:
                return
            if crop_box is None or img_crop is None or hsv_crop is None:
                return

            crop_w = crop_box[2] - crop_box[0]
            crop_h = crop_box[3] - crop_box[1]
            scale_p2 = WIN_H / max(crop_h, 1)

            panel_w = int(crop_w * scale_p2)
            hud_h = 85

            # If click is on the right panel (mask preview), offset x
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

        elif phase == 3:
            # Phase 3: drag to draw exclusion rectangles around price tags
            if crop_box is None or img_crop is None:
                return
            crop_h = crop_box[3] - crop_box[1]
            crop_w = crop_box[2] - crop_box[0]
            s3 = WIN_H / max(crop_h, 1)

            iy = int((wy - 70) / s3)
            ix = int(wx / s3)
            ix = max(0, min(ix, crop_w-1))
            iy = max(0, min(iy, crop_h-1))

            if event == cv2.EVENT_LBUTTONDOWN:
                drawing_exclude = True
                excl_start = (iy, ix)
                excl_current = (iy, ix)

            elif event == cv2.EVENT_MOUSEMOVE and drawing_exclude:
                excl_current = (iy, ix)
                frame, _ = build_phase3_display(
                    img_crop, s3, exclude_rects, excl_start, excl_current)
                cv2.imshow(win, frame)

            elif event == cv2.EVENT_LBUTTONUP and drawing_exclude:
                drawing_exclude = False
                if excl_start is not None:
                    ey1 = min(excl_start[0], iy)
                    ey2 = max(excl_start[0], iy)
                    ex1 = min(excl_start[1], ix)
                    ex2 = max(excl_start[1], ix)
                    if (ey2-ey1) > 5 and (ex2-ex1) > 5:
                        exclude_rects.append((ey1, ey2, ex1, ex2))
                        print("  Exclude rect added: y={}->{}, x={}->{}".format(ey1, ey2, ex1, ex2))
                excl_current = None
                frame, _ = build_phase3_display(
                    img_crop, s3, exclude_rects, excl_start, excl_current)
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
            # ENTER — confirm crop and move to Phase 2
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
            print("  [D] Dark shelf  [L] Light shelf  [Y] Yogurt  [S] Exclude rects")
            print()

            frame, _ = build_phase2_display(
                img_crop, hsv_crop, scale_p2, crop_box, current_mode)
            w_panel = frame.shape[1]
            h_panel = frame.shape[0]
            win_w   = int(w_panel * WIN_H / h_panel)
            cv2.resizeWindow(win, win_w, WIN_H)
            cv2.imshow(win, frame)

        elif phase == 2:
            # Phase 2 keystrokes: switch mode, clear, reset, save
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
            elif key in (ord('i'), ord('I')):
                current_mode = 'i'
                print()
                print("  --- MODE: IGNORE / TAGS ---")
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
                # S saves config and moves to Phase 3 (exclusion rects)
                if crop_box is None:
                    continue
                phase = 3
                print()
                print("  PHASE 3: Draw exclusion rectangles around price tags/banners.")
                print("  Click + drag to draw. [ENTER] Save  [C] Clear  [Q] Back")
                print()
                crop_h = crop_box[3] - crop_box[1]
                s3 = WIN_H / max(crop_h, 1)
                if img_crop is not None:
                    frame, _ = build_phase3_display(
                        img_crop, s3, exclude_rects, None, None)
                    h_panel = frame.shape[0]
                    w_panel = frame.shape[1]
                    win_w   = int(w_panel * WIN_H / h_panel)
                    cv2.resizeWindow(win, win_w, WIN_H)
                    cv2.imshow(win, frame)
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

        elif phase == 3:
            if key == 13:
                # ENTER — save everything and exit
                if save_config(image_path, img_orig, crop_box, exclude_rects):
                    break
                continue
            elif key in (ord('c'), ord('C')):
                exclude_rects.clear()
                print("  Exclude rectangles cleared.")
                if img_crop is not None and crop_box is not None:
                    crop_h = crop_box[3] - crop_box[1]
                    s3 = WIN_H / max(crop_h, 1)
                    frame, _ = build_phase3_display(
                        img_crop, s3, exclude_rects, None, None)
                    cv2.imshow(win, frame)
            elif key in (ord('q'), ord('Q')):
                # Q goes back to Phase 2
                phase = 2
                print()
                print("  Back to Phase 2. Press S to return to exclusion or edit colors.")
                print()
                if img_crop is not None and hsv_crop is not None and crop_box is not None:
                    crop_h = crop_box[3] - crop_box[1]
                    scale_p2 = WIN_H / max(crop_h, 1)
                    frame, _ = build_phase2_display(
                        img_crop, hsv_crop, scale_p2, crop_box, current_mode)
                    cv2.imshow(win, frame)
                    cv2.resizeWindow(win, int(frame.shape[1] * WIN_H / frame.shape[0]), WIN_H)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
