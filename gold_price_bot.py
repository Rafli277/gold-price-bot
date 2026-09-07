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
FX_API_URL = "https://api.frankfurter.dev/v1/latest"  # free, no API key
GOLD_INFO_LINK = "https://www.logammulia.com/id/grafik-harga-emas"
OZ_TO_GRAM = 31.1034768  # 1 troy ounce = 31.1034768 gram


def fetch_gold_price() -> dict:
    """Ambil harga emas terkini dari GoldAPI.io"""
    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.get(GOLD_API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_usd_idr_rate() -> float:
    """Ambil kurs USD -> IDR terkini (gratis, tanpa API key)"""
    resp = requests.get(FX_API_URL, params={"from": "USD", "to": "IDR"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data["rates"]["IDR"]


def format_message(data: dict, usd_idr: float) -> str:
    """Format data harga emas jadi pesan Telegram yang enak dibaca"""
    price_usd_oz = data.get("price")
    price_usd_gram = data.get("price_gram_24k")
    prev_close_oz = data.get("prev_close_price")  # harga penutupan kemarin, dari GoldAPI
    change_usd = data.get("ch") or 0
    change_pct = data.get("chp") or 0

    # Harga kemarin (per gram), dari prev_close_price (per troy ounce)
    prev_close_gram = prev_close_oz / OZ_TO_GRAM if prev_close_oz else None

    # Estimasi konversi ke Rupiah (harga emas dunia murni, BUKAN harga resmi Antam)
    price_idr_gram = price_usd_gram * usd_idr
    prev_close_idr_gram = prev_close_gram * usd_idr if prev_close_gram else None
    change_idr_gram = (
        price_idr_gram - prev_close_idr_gram if prev_close_idr_gram else 0
    )

    # Waktu WIB (UTC+7)
    wib = timezone(timedelta(hours=7))
    now = datetime.now(wib).strftime("%d %b %Y, %H:%M WIB")

    arrow = "🔺" if change_usd >= 0 else "🔻"
    arrow_idr = "🔺" if change_idr_gram >= 0 else "🔻"

    prev_close_line = (
        f"Kemarin: ${prev_close_oz:,.2f} / oz (${prev_close_gram:,.2f}/gram)\n"
        if prev_close_oz
        else ""
    )
    prev_close_idr_line = (
        f"Kemarin: Rp{prev_close_idr_gram:,.0f} / gram\n"
        if prev_close_idr_gram
        else ""
    )

    message = (
        f"🥇 *Update Harga Emas Dunia*\n"
        f"_{now}_\n\n"
        f"*Harga Internasional (XAU/USD)*\n"
        f"Sekarang: ${price_usd_oz:,.2f} / oz (${price_usd_gram:,.2f}/gram)\n"
        f"{prev_close_line}"
        f"Gap: {arrow} {change_usd:+.2f} ({change_pct:+.2f}%)\n\n"
        f"*Estimasi dalam Rupiah (per gram, 24k)*\n"
        f"Sekarang: Rp{price_idr_gram:,.0f}\n"
        f"{prev_close_idr_line}"
        f"Gap: {arrow_idr} Rp{abs(change_idr_gram):,.0f}\n"
        f"Kurs: Rp{usd_idr:,.0f}/USD\n"
        f"_(estimasi dari harga emas dunia, bukan harga resmi Antam —_\n"
        f"_harga Antam biasanya lebih tinggi karena ada premium cetak & sertifikasi)_\n\n"
        f"[📈 Cek harga emas harian lainnya]({GOLD_INFO_LINK})"
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
        usd_idr = fetch_usd_idr_rate()
        message = format_message(data, usd_idr)
        send_telegram_message(message)
        print("Berhasil kirim update harga emas.")
    except requests.RequestException as e:
        print(f"ERROR saat request: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()