"""
========================================================================
  ALERTS - Gmail + Telegram + WhatsApp (via OpenWA)
  Reads : alert_config.json

  HOW TO ENABLE EACH CHANNEL
  ---------------------------
  1. Open alert_config.json
  2. Fill in your credentials
  3. Set "enabled": true for the channels you want active
  4. Save - no code changes needed

  COOLDOWN
  --------
  To avoid spamming (camera runs every 15 min, stock might stay
  critical for hours), alerts are only sent once per
  "cooldown_minutes" window. Configurable in alert_config.json.

  TESTING
  -------
  Run this file directly to send a test alert on all enabled channels:
      python alerts.py --test
========================================================================
"""

import json
import os
import sys
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta

_SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH    = os.path.join(_SCRIPT_DIR, "alert_config.json")
LAST_ALERT_FILE = os.path.join(_SCRIPT_DIR, ".last_alert_time")


# --- CONFIG LOADING -------------------------------------------------------

def load_config():
    if not os.path.exists(CONFIG_PATH):
        example = os.path.join(_SCRIPT_DIR, "alert_config.example.json")
        print("  Warning: 'alert_config.json' not found. Alerts disabled.")
        if os.path.exists(example):
            print("  Tip: copy 'alert_config.example.json' to 'alert_config.json'")
            print("       and fill in your real credentials.")
        return None
    with open(CONFIG_PATH) as f:
        return json.load(f)


# --- COOLDOWN --------------------------------------------------------------

def is_in_cooldown(cooldown_minutes):
    if not os.path.exists(LAST_ALERT_FILE):
        return False
    with open(LAST_ALERT_FILE) as f:
        last_time_str = f.read().strip()
    try:
        last_time = datetime.fromisoformat(last_time_str)
    except ValueError:
        return False
    elapsed = datetime.now() - last_time
    return elapsed < timedelta(minutes=cooldown_minutes)


def update_cooldown():
    with open(LAST_ALERT_FILE, "w") as f:
        f.write(datetime.now().isoformat())


# --- GMAIL -----------------------------------------------------------------

def send_gmail(cfg, subject, body, image_path=None):
    """
    cfg = {
        "sender_email"    : "your_email@gmail.com",
        "app_password"    : "16-char app password (no spaces)",
        "recipient_email" : "manager@store.com"
    }
    """
    try:
        msg = MIMEMultipart()
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = cfg["recipient_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment",
                               filename=os.path.basename(image_path))
                msg.attach(img)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(cfg["sender_email"], cfg["app_password"])
            server.send_message(msg)

        print("  Gmail sent OK")
        return True

    except smtplib.SMTPAuthenticationError:
        print("  Gmail FAILED: authentication error.")
        print("     Check sender_email and app_password (no spaces!) in alert_config.json")
        print("     Make sure 2-Step Verification is enabled on the Gmail account.")
        return False
    except Exception as e:
        print("  Gmail FAILED: {}".format(e))
        return False


# --- TELEGRAM --------------------------------------------------------------

def send_telegram(cfg, text, image_path=None):
    """
    cfg = {
        "bot_token" : "123456789:ABC...",
        "chat_id"   : "987654321"
    }
    """
    base_url = "https://api.telegram.org/bot{}".format(cfg['bot_token'])

    try:
        if image_path and os.path.exists(image_path):
            url = "{}/sendPhoto".format(base_url)
            with open(image_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": cfg["chat_id"], "caption": text},
                    files={"photo": f},
                    timeout=15,
                )
        else:
            url = "{}/sendMessage".format(base_url)
            resp = requests.post(
                url,
                data={"chat_id": cfg["chat_id"], "text": text},
                timeout=15,
            )

        data = resp.json()
        if data.get("ok"):
            print("  Telegram sent OK")
            return True
        else:
            msg = data.get('description', 'unknown error')
            print("  Telegram FAILED: {}".format(msg))
            if "chat not found" in str(msg).lower():
                print("     -> Did you message your bot first? Bots can't")
                print("       initiate conversations. Send /start to your bot.")
            return False

    except requests.exceptions.RequestException as e:
        print("  Telegram FAILED: {}".format(e))
        return False


# --- WHATSAPP (via OpenWA) -------------------------------------------------

def send_whatsapp(cfg, text):
    """
    cfg = {
        "api_url"          : "http://localhost:8002/send",
        "recipient_number" : "21612345678"
    }
    """
    try:
        resp = requests.post(
            cfg["api_url"],
            json={"to": cfg["recipient_number"], "message": text},
            timeout=15,
        )
        if resp.status_code == 200:
            print("  WhatsApp sent OK")
            return True
        else:
            print("  WhatsApp FAILED: HTTP {} - {}".format(resp.status_code, resp.text))
            return False

    except requests.exceptions.ConnectionError:
        print("  WhatsApp FAILED: cannot reach {}".format(cfg['api_url']))
        print("     -> Is the OpenWA server running? (node server.js)")
        return False
    except requests.exceptions.RequestException as e:
        print("  WhatsApp FAILED: {}".format(e))
        return False


# --- MAIN DISPATCH ---------------------------------------------------------

def send_stock_alert(stock_pct, threshold, filename, image_path=None,
                     force=False):
    """
    Main entry point. Called from watcher.py when stock is critical.

    force=True bypasses cooldown (used for --test).
    Returns dict of {channel: success_bool} for channels that were enabled.
    """
    cfg = load_config()
    if cfg is None:
        return {}

    cooldown = cfg.get("cooldown_minutes", 30)

    if not force and is_in_cooldown(cooldown):
        print("  Alert skipped - cooldown active ({} min between alerts)".format(cooldown))
        return {}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    subject = "SHELF ALERT - Stock at {}%".format(stock_pct)
    body = (
        "Stock level is critically low.\n\n"
        "  Stock remaining : {}%\n"
        "  Threshold       : {}%\n"
        "  Image           : {}\n"
        "  Time            : {}\n\n"
        "Please restock soon."
    ).format(stock_pct, threshold, filename, timestamp)

    results = {}

    if cfg.get("gmail", {}).get("enabled"):
        print("\n  Sending Gmail...")
        results["gmail"] = send_gmail(cfg["gmail"], subject, body, image_path)

    if cfg.get("telegram", {}).get("enabled"):
        print("\n  Sending Telegram...")
        results["telegram"] = send_telegram(cfg["telegram"], body, image_path)

    if cfg.get("whatsapp", {}).get("enabled"):
        print("\n  Sending WhatsApp...")
        results["whatsapp"] = send_whatsapp(cfg["whatsapp"], body)

    if not results:
        print("  Info: No alert channels enabled in alert_config.json")
    else:
        update_cooldown()

    return results


# --- TEST MODE -------------------------------------------------------------

if __name__ == "__main__":
    if "--test" in sys.argv:
        print()
        print("=" * 50)
        print("  ALERT TEST - sending to all enabled channels")
        print("=" * 50)

        results = send_stock_alert(
            stock_pct=23.5,
            threshold=30.0,
            filename="test_photo.jpg",
            image_path=None,
            force=True,
        )

        print()
        print("=" * 50)
        print("  RESULTS")
        print("=" * 50)
        if not results:
            print("  No channels enabled.")
            print("  Edit alert_config.json and set 'enabled': true")
            print("  for at least one channel, then re-run this test.")
        else:
            for channel, success in results.items():
                status = "OK" if success else "FAILED"
                print("  {:10s} -> {}".format(channel, status))
        print("=" * 50)
        print()

    else:
        print("  Usage: python alerts.py --test")
        print("  This sends a test alert to verify your configuration.")
