"""
Gold Price Telegram Bot
Fetch harga emas dunia (XAU/USD) dan kirim update ke Telegram.
Dijalankan via GitHub Actions setiap 2 jam.
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta

# --- Konfigurasi dari environment variables (diisi lewat GitHub Secrets) ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GOLD_API_KEY = os.environ.get("GOLD_API_KEY")

GOLD_API_URL = "https://www.goldapi.io/api/XAU/USD"


def fetch_gold_price() -> dict:
    """Ambil harga emas terkini dari GoldAPI.io"""
    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.get(GOLD_API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def format_message(data: dict) -> str:
    """Format data harga emas jadi pesan Telegram yang enak dibaca"""
    price_usd_oz = data.get("price")
    price_usd_gram = data.get("price_gram_24k")
    change = data.get("ch")
    change_pct = data.get("chp")

    # Waktu WIB (UTC+7)
    wib = timezone(timedelta(hours=7))
    now = datetime.now(wib).strftime("%d %b %Y, %H:%M WIB")

    arrow = "🔺" if (change or 0) >= 0 else "🔻"

    message = (
        f"🥇 *Update Harga Emas Dunia*\n"
        f"_{now}_\n\n"
        f"Harga: *${price_usd_oz:,.2f}* / troy ounce\n"
        f"Harga: *${price_usd_gram:,.2f}* / gram (24k)\n"
        f"Perubahan: {arrow} {change:+.2f} ({change_pct:+.2f}%)\n"
    )
    return message


def send_telegram_message(text: str) -> None:
    """Kirim pesan ke chat/channel Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


def main():
    missing = [
        name
        for name, val in [
            ("TELEGRAM_BOT_TOKEN", BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", CHAT_ID),
            ("GOLD_API_KEY", GOLD_API_KEY),
        ]
        if not val
    ]
    if missing:
        print(f"ERROR: Env var belum diset: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    try:
        data = fetch_gold_price()
        message = format_message(data)
        send_telegram_message(message)
        print("Berhasil kirim update harga emas.")
    except requests.RequestException as e:
        print(f"ERROR saat request: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
