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
GOLD_INFO_LINK = "https://harga-emas.org/"  # info harga emas harian (Indonesia)
OZ_TO_GRAM = 31.1034768  # 1 troy ounce = 31.1034768 gram

# Sumber harga Antam resmi (community project, gratis, tanpa API key)
# https://github.com/iamutaki/logam-mulia-api
ANTAM_API_URL = "https://logam-mulia-api.iamutaki.workers.dev/api/prices/logammulia"
ANTAM_HISTORY_URL = "https://logam-mulia-api.iamutaki.workers.dev/api/prices/logammulia/history"
ANTAM_WEIGHT = 1  # gram, dijadikan acuan (harga per gram)
ANTAM_MATERIAL_TYPE = "Emas Batangan"


def fetch_gold_price() -> dict:
    """Ambil harga emas dunia terkini dari GoldAPI.io"""
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


def fetch_antam_price() -> dict | None:
    """
    Ambil harga Antam resmi (1 gram, Emas Batangan) dari logam-mulia-api.
    Return None kalau gagal/data tidak ditemukan -> caller harus fallback.
    """
    try:
        resp = requests.get(ANTAM_API_URL, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            return None
        for item in payload.get("data", []):
            if (
                item.get("weight") == ANTAM_WEIGHT
                and item.get("materialType") == ANTAM_MATERIAL_TYPE
            ):
                return item
    except (requests.RequestException, ValueError):
        return None
    return None


def fetch_antam_yesterday_price(today_date: str) -> int | None:
    """Ambil harga Antam hari sebelumnya (untuk hitung gap) dari endpoint history."""
    try:
        resp = requests.get(
            ANTAM_HISTORY_URL,
            params={
                "weight": ANTAM_WEIGHT,
                "materialType": ANTAM_MATERIAL_TYPE,
                "length": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        for rec in payload.get("data", []):
            if rec.get("recordedDate") != today_date:
                return rec.get("sellPrice")
    except (requests.RequestException, ValueError):
        return None
    return None


def format_message(data: dict, usd_idr: float, antam: dict | None) -> str:
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

    # --- Bagian harga Antam resmi (kalau berhasil diambil) ---
    antam_section = ""
    if antam:
        antam_price = antam.get("sellPrice")
        antam_date = antam.get("recordedDate")
        antam_yesterday = fetch_antam_yesterday_price(antam_date)

        antam_lines = [f"*Harga Antam Resmi (1 gram)*", f"Sekarang: Rp{antam_price:,.0f}"]
        if antam_yesterday:
            gap_antam = antam_price - antam_yesterday
            arrow_antam = "🔺" if gap_antam >= 0 else "🔻"
            antam_lines.append(f"Kemarin: Rp{antam_yesterday:,.0f}")
            antam_lines.append(f"Gap: {arrow_antam} Rp{abs(gap_antam):,.0f}")
        antam_lines.append(f"_(update: {antam_date}, sumber: logammulia.com)_")
        antam_section = "\n".join(antam_lines) + "\n\n"
    else:
        antam_section = (
            "*Harga Antam Resmi*\n"
            "_Sumber Antam sedang tidak tersedia, tampil estimasi saja._\n\n"
        )

    message = (
        f"🥇 *Update Harga Emas Dunia*\n"
        f"_{now}_\n\n"
        f"{antam_section}"
        f"*Harga Internasional (XAU/USD)*\n"
        f"Sekarang: ${price_usd_oz:,.2f} / oz (${price_usd_gram:,.2f}/gram)\n"
        f"{prev_close_line}"
        f"Gap: {arrow} {change_usd:+.2f} ({change_pct:+.2f}%)\n\n"
        f"*Estimasi dalam Rupiah (per gram, 24k)*\n"
        f"Sekarang: Rp{price_idr_gram:,.0f}\n"
        f"{prev_close_idr_line}"
        f"Gap: {arrow_idr} Rp{abs(change_idr_gram):,.0f}\n"
        f"Kurs: Rp{usd_idr:,.0f}/USD\n"
        f"_(estimasi dari harga emas dunia, biasanya lebih rendah dari_\n"
        f"_harga Antam resmi karena belum termasuk premium cetak & sertifikasi)_\n\n"
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
        antam = fetch_antam_price()  # None kalau gagal -> pesan tetap terkirim tanpa data Antam
        message = format_message(data, usd_idr, antam)
        send_telegram_message(message)
        print("Berhasil kirim update harga emas.")
    except requests.RequestException as e:
        print(f"ERROR saat request: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()