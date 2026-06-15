"""
========================================================================
  WATCHER - Automatic shelf monitoring engine
  Usage : python watcher.py
  Reads : shelf_config.json  (written by hsv_calibrator.py)

  WHAT THIS DOES
  --------------
  Watches the  incoming/  folder for new photos.
  When a new photo appears (dropped by camera sync, cloud tool, etc.):
    1. Waits 2 seconds (ensures file is fully written before reading)
    2. Runs shelf_monitor.py on the photo
    3. Appends one row to results.csv
    4. Saves a debug image to  archive/debug/
    5. Moves the original photo to  archive/photos/
    6. Prints alarm to terminal if stock < 30%
    7. (Gmail + Telegram alerts plugged in here later)

  FOLDER STRUCTURE (auto-created on first run)
  ---------------------------------------------
  option 3/
  |-- hsv_calibrator.py
  |-- shelf_monitor.py
  |-- watcher.py
  |-- shelf_config.json       <- written by calibrator
  |-- results.csv             <- one row per photo, auto-created
  |-- incoming/               <- camera drops photos here
  +-- archive/
      |-- photos/             <- processed originals
      +-- debug/              <- debug overlay images

  STOPPING THE WATCHER
  --------------------
  Press  Ctrl+C  to stop cleanly.
========================================================================
"""

import os
import sys
import time
import shutil
import csv
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shelf_monitor as monitor

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

INCOMING_DIR    = _SCRIPT_DIR / "incoming"
ARCHIVE_PHOTOS  = _SCRIPT_DIR / "archive" / "photos"
ARCHIVE_DEBUG   = _SCRIPT_DIR / "archive" / "debug"
RESULTS_CSV     = _SCRIPT_DIR / "results.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}

SCAN_INTERVAL = 5

FILE_SETTLE_TIME = 2


def setup() -> None:
    INCOMING_DIR.mkdir(exist_ok=True)
    ARCHIVE_PHOTOS.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DEBUG.mkdir(parents=True, exist_ok=True)

    if not RESULTS_CSV.exists():
        with open(RESULTS_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "filename",
                "stock_pct",
                "empty_pct",
                "status",
                "debug_file",
            ])
        print("  Created {}".format(RESULTS_CSV))


def log_result(metrics: dict, filename: str,
               debug_filename: str) -> tuple[str, str]:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status    = "CRITICAL" if metrics["alert"] else "OK"

    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            filename,
            metrics["stock_pct"],
            metrics["empty_pct"],
            status,
            debug_filename,
        ])

    return timestamp, status


def handle_alert(metrics: dict, filename: str, timestamp: str) -> None:
    cfg = monitor._get_cfg()
    threshold = cfg.get("alert_threshold", 30)

    print()
    print("#" * 50)
    print("  STOCK CRITICAL ALERT")
    print("  Time     : {}".format(timestamp))
    print("  Image    : {}".format(filename))
    print("  Stock    : {}%".format(metrics['stock_pct']))
    print("  Threshold: {}%".format(threshold))
    print("#" * 50)
    print()


def process_image(img_path: Path) -> None:
    print()
    print("  " + "-" * 45)
    print("  New photo detected: {}".format(img_path.name))
    print("  Processing...")

    try:
        metrics = monitor.analyze(str(img_path), save_debug_img=True)

        debug_src: Path | None = Path(metrics["debug_path"]) if metrics["debug_path"] else None
        debug_name = "{}_debug{}".format(img_path.stem, img_path.suffix)
        if debug_src and debug_src.exists():
            debug_dst  = ARCHIVE_DEBUG / debug_name
            shutil.move(str(debug_src), str(debug_dst))
        else:
            debug_name = "none"

        timestamp, status = log_result(metrics, img_path.name, debug_name)

        print("  Done")
        print("  Stock    : {}%".format(metrics['stock_pct']))
        print("  Status   : {}".format(status))
        print("  Logged   -> {}".format(RESULTS_CSV))

        if metrics["alert"]:
            handle_alert(metrics, img_path.name, timestamp)

        archive_dst = ARCHIVE_PHOTOS / img_path.name
        if archive_dst.exists():
            stem = img_path.stem
            ext  = img_path.suffix
            ts   = datetime.now().strftime("%H%M%S")
            archive_dst = ARCHIVE_PHOTOS / "{}_{}{}".format(stem, ts, ext)
        shutil.move(str(img_path), str(archive_dst))
        print("  Archived -> {}".format(archive_dst))

    except Exception as e:
        print("  Error processing {}: {}".format(img_path.name, e))
        error_dst = ARCHIVE_PHOTOS / img_path.name
        if error_dst.exists():
            stem = img_path.stem
            ext  = img_path.suffix
            ts   = datetime.now().strftime("%H%M%S")
            error_dst = ARCHIVE_PHOTOS / "{}_{}{}".format(stem, ts, ext)
        shutil.move(str(img_path), str(error_dst))


def current_incoming_files() -> set[str]:
    return {f.name for f in INCOMING_DIR.iterdir()
            if f.suffix.lower() in IMAGE_EXTS}


def watch() -> None:
    setup()

    print()
    print("=" * 50)
    print("  SHELF WATCHER - Running")
    print("=" * 50)
    print("  Watching   : {}".format(INCOMING_DIR.resolve()))
    print("  Results    : {}".format(RESULTS_CSV.resolve()))
    print("  Archive    : {}".format(ARCHIVE_PHOTOS.resolve()))
    print("  Scan every : {}s".format(SCAN_INTERVAL))
    print("  Press Ctrl+C to stop.")
    print()

    prev_files = current_incoming_files()

    while True:
        try:
            now_files = current_incoming_files()
            new_files = now_files - prev_files

            for fname in sorted(new_files):
                f = INCOMING_DIR / fname

                time.sleep(FILE_SETTLE_TIME)

                if not f.exists():
                    continue

                process_image(f)

            prev_files = now_files

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            print()
            print("  Watcher stopped. Results saved in results.csv")
            print()
            break
        except Exception as e:
            print("  Watcher error: {}".format(e))
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    watch()
