"""
Automatic shelf monitoring engine.

Polling loop that watches the incoming/ folder for new photos.
Uses snapshot-diff: it remembers which files existed on the previous
poll cycle and processes any new ones. This avoids needing filesystem
notifications (which are unreliable on network drives and Windows).

On each new file:
  1. Wait FILE_SETTLE_TIME seconds for the write to complete
  2. Rename to a timestamped filename (prevents re-processing)
  3. Run shelf_monitor.analyze() — the core CV pipeline
  4. Compute financial impact from configurable defaults
  5. Log one row to results.csv (12 fields)
  6. Move original to archive/photos/, debug to archive/debug/
  7. Dispatch alerts if stock is below threshold

Financial totals (daily_loss, daily_missed_units) accumulate in memory
and reset on restart. They're not persisted between watcher sessions.
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
import alerts

# Fallback values — overridden by shelf_config.json at runtime
_FINANCIAL_DEFAULTS = {
    "unit_price": 0.5,
    "currency": "TND",
    "sales_per_hour": 20,
    "scan_interval_hours": 0.25,
    "store_open": 8,
    "store_close": 22,
}

# Reset every time the watcher starts — not saved to disk
daily_loss         = 0.0
daily_missed_units = 0.0


def _get_financial() -> dict:
    """Merge config values on top of defaults. Config wins."""
    cfg = monitor._get_cfg()
    return {k: cfg.get(k, v) for k, v in _FINANCIAL_DEFAULTS.items()}

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

INCOMING_DIR    = _SCRIPT_DIR / "incoming"
ARCHIVE_PHOTOS  = _SCRIPT_DIR / "archive" / "photos"
ARCHIVE_DEBUG   = _SCRIPT_DIR / "archive" / "debug"
RESULTS_CSV     = _SCRIPT_DIR / "results.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}

SCAN_INTERVAL = 5  # seconds between polls

FILE_SETTLE_TIME = 2  # seconds to wait before reading a new file

EXPECTED_HEADER = [
    "timestamp",
    "filename",
    "stock_pct",
    "empty_pct",
    "status",
    "debug_file",
    "scan_loss_tnd",
    "missed_units",
    "daily_loss_tnd",
    "daily_missed_units",
    "projected_loss_tnd",
    "recoverable_tnd",
]


def setup() -> None:
    """Create the required directories and ensure results.csv exists with headers."""
    INCOMING_DIR.mkdir(exist_ok=True)
    ARCHIVE_PHOTOS.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DEBUG.mkdir(parents=True, exist_ok=True)

    # If CSV exists but has old headers, rewrite it (auto-upgrade)
    needs_header = not RESULTS_CSV.exists()
    if not needs_header:
        with open(RESULTS_CSV, "r") as f:
            first = f.readline().strip().split(",")
            if first != EXPECTED_HEADER:
                needs_header = True

    if needs_header:
        existed = RESULTS_CSV.exists()
        with open(RESULTS_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(EXPECTED_HEADER)
        msg = "  Upgraded" if existed else "  Created"
        print("{} {}".format(msg, RESULTS_CSV))


def log_result(metrics: dict, filename: str,
               debug_filename: str,
               scan_loss: float = 0.0,
               missed_units: float = 0.0,
               daily_loss: float = 0.0,
               daily_missed_units: float = 0.0,
               projected_loss: float = 0.0,
               recoverable: float = 0.0) -> tuple[str, str]:
    """Append a single scan result row to results.csv. Returns (timestamp, status)."""
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
            round(scan_loss, 4),
            round(missed_units, 2),
            round(daily_loss, 4),
            round(daily_missed_units, 2),
            round(projected_loss, 4),
            round(recoverable, 4),
        ])

    return timestamp, status


def handle_alert(metrics: dict, filename: str, timestamp: str,
                 debug_image_path: str | None = None) -> None:
    """Print alert to terminal and dispatch via configured channels."""
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

    alerts.send_stock_alert(
        stock_pct  = metrics["stock_pct"],
        threshold  = threshold,
        filename   = filename,
        image_path = debug_image_path,
    )


def process_image(img_path: Path) -> None:
    """Run analysis on a single image, log results, archive, alert."""
    print()
    print("  " + "-" * 45)
    print("  New photo detected: {}".format(img_path.name))
    print("  Processing...")

    try:
        metrics = monitor.analyze(str(img_path), save_debug_img=True)

        # Move debug image to archive
        debug_src: Path | None = Path(metrics["debug_path"]) if metrics["debug_path"] else None
        debug_name = "{}_debug{}".format(img_path.stem, img_path.suffix)
        debug_dst_path: str | None = None
        if debug_src and debug_src.exists():
            debug_dst = ARCHIVE_DEBUG / debug_name
            shutil.move(str(debug_src), str(debug_dst))
            debug_dst_path = str(debug_dst)
        else:
            debug_name = "none"

        # Financial calculations
        fin = _get_financial()
        empty_rate    = (100.0 - metrics["stock_pct"]) / 100.0
        missed_units  = fin["sales_per_hour"] * fin["scan_interval_hours"] * empty_rate
        scan_loss     = missed_units * fin["unit_price"]
        global daily_loss, daily_missed_units
        daily_loss         += scan_loss
        daily_missed_units += missed_units

        # Projected loss = extrapolate from current daily loss to full day
        now_hour     = datetime.now().hour + datetime.now().minute / 60.0
        hours_elapsed = now_hour - fin["store_open"]
        if hours_elapsed > 0:
            projected_loss = round(
                daily_loss * (fin["store_close"] - fin["store_open"]) / hours_elapsed, 4)
            recoverable    = round(projected_loss - daily_loss, 4)
        else:
            projected_loss = 0.0
            recoverable    = 0.0

        timestamp, status = log_result(metrics, img_path.name, debug_name,
                                        scan_loss, missed_units,
                                        daily_loss, daily_missed_units,
                                        projected_loss, recoverable)

        print("  Done")
        print("  Stock    : {}%".format(metrics['stock_pct']))
        print("  Status   : {}".format(status))
        print("  Logged   -> {}".format(RESULTS_CSV))
        print("  Scan loss: {:.4f} TND  |  Missed: {:.2f}  |  " \
              "Daily: {:.4f} TND / {:.2f}  |  " \
              "Projected: {:.4f} TND  |  Recoverable: {:.4f} TND".format(
            scan_loss, missed_units, daily_loss, daily_missed_units,
            projected_loss, recoverable))

        if metrics["alert"]:
            handle_alert(metrics, img_path.name, timestamp, debug_dst_path)

        # Archive the original photo (avoid overwrite with timestamp suffix)
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
        # Still archive the file so it won't be retried
        error_dst = ARCHIVE_PHOTOS / img_path.name
        if error_dst.exists():
            stem = img_path.stem
            ext  = img_path.suffix
            ts   = datetime.now().strftime("%H%M%S")
            error_dst = ARCHIVE_PHOTOS / "{}_{}{}".format(stem, ts, ext)
        shutil.move(str(img_path), str(error_dst))


def current_incoming_files() -> set[str]:
    """Return filenames currently in the incoming folder (images only)."""
    return {f.name for f in INCOMING_DIR.iterdir()
            if f.suffix.lower() in IMAGE_EXTS}


def watch() -> None:
    """Main loop: poll incoming/, process new files, sleep, repeat."""
    setup()

    print()
    print("=" * 50)
    print("  SHELFSENSE WATCHER - Running")
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
            new_files = now_files - prev_files  # snapshot diff

            for fname in sorted(new_files):
                f = INCOMING_DIR / fname

                # Let the file finish writing (network drives, cloud sync)
                time.sleep(FILE_SETTLE_TIME)

                if not f.exists():
                    continue

                # Rename to timestamped filename to prevent re-processing
                ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                new_name = "{}{}".format(ts, f.suffix)
                counter = 1
                while (INCOMING_DIR / new_name).exists():
                    new_name = "{}_{}{}".format(ts, counter, f.suffix)
                    counter += 1
                new_path = INCOMING_DIR / new_name
                f.rename(new_path)
                f = new_path

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
