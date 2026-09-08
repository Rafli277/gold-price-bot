"""
Gold Price Telegram Bot
Fetch harga emas dunia + harga Antam/UBS/Galeri24 resmi + kurs USD/IDR,
lalu kirim update ke Telegram. Dijalankan via GitHub Actions setiap 2 jam.
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
FX_API_URL = "https://api.frankfurter.dev/v1/latest"  # fallback kurs, gratis, tanpa API key
OZ_TO_GRAM = 31.1034768  # 1 troy ounce = 31.1034768 gram

# Sumber harga lokal Indonesia (community project, gratis, tanpa API key)
# https://github.com/iamutaki/logam-mulia-api
LM_API_BASE = "https://logam-mulia-api.iamutaki.workers.dev/api/prices"

# (label ditampilkan, endpoint source, materialType, weight acuan)
GOLD_SOURCES = [
    ("Antam Resmi", "logammulia", "Emas Batangan", 1),
    ("UBS", "galeri24", "UBS", 1),
    ("Galeri 24", "galeri24", "GALERI 24", 1),
]

KURSDOLAR_SOURCE = "kursdolar"


# ---------------------------------------------------------------------------
# Harga emas dunia (GoldAPI.io)
# ---------------------------------------------------------------------------

def fetch_gold_price() -> dict:
    """Ambil harga emas dunia terkini dari GoldAPI.io"""
    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.get(GOLD_API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Kurs USD/IDR: coba logam-mulia-api (kursdolar) dulu, fallback ke Frankfurter
# ---------------------------------------------------------------------------

def fetch_usd_idr_frankfurter() -> float | None:
    """Fallback kurs USD -> IDR (gratis, tanpa API key)"""
    try:
        resp = requests.get(FX_API_URL, params={"from": "USD", "to": "IDR"}, timeout=15)
        resp.raise_for_status()
        return resp.json()["rates"]["IDR"]
    except (requests.RequestException, ValueError, KeyError):
        return None


MIN_PLAUSIBLE_USD_IDR = 8_000
MAX_PLAUSIBLE_USD_IDR = 25_000


def _extract_rate(item: dict) -> float | None:
    """
    Cari field kurs dari item kursdolar, dan HANYA terima kalau nilainya masuk akal
    sebagai kurs USD/IDR (8.000-25.000). Ini guard karena field JSON persisnya
    belum diverifikasi manual -> mencegah bug seperti "Rp882,000/USD" (field yang
    ke-parse ternyata bukan rate, misal harga emas per gram ikut ke-ambil).
    """
    for key in ("rate", "price", "sellPrice", "value"):
        val = item.get(key)
        if val:
            try:
                rate = float(val)
            except (TypeError, ValueError):
                continue
            if MIN_PLAUSIBLE_USD_IDR <= rate <= MAX_PLAUSIBLE_USD_IDR:
                return rate
    return None


def fetch_kursdolar() -> dict | None:
    """Ambil kurs USD/IDR dari logam-mulia-api. Return None kalau gagal/format tak dikenali."""
    try:
        resp = requests.get(f"{LM_API_BASE}/{KURSDOLAR_SOURCE}", timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            return None
        data = payload.get("data", [])
        if not data:
            return None
        rate = _extract_rate(data[0])
        if rate is None:
            return None
        return {"rate": rate, "recordedDate": data[0].get("recordedDate")}
    except (requests.RequestException, ValueError):
        return None


def fetch_kursdolar_yesterday(today_date: str) -> float | None:
    try:
        resp = requests.get(
            f"{LM_API_BASE}/{KURSDOLAR_SOURCE}/history",
            params={"length": 5},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        for rec in payload.get("data", []):
            if rec.get("recordedDate") != today_date:
                rate = _extract_rate(rec)
                if rate is not None:
                    return rate
    except (requests.RequestException, ValueError):
        return None
    return None


def resolve_usd_idr() -> dict:
    """Ambil kurs terbaik yang tersedia (+ kurs kemarin kalau ada). Return dict."""
    kursdolar = fetch_kursdolar()
    if kursdolar:
        yesterday = fetch_kursdolar_yesterday(kursdolar.get("recordedDate"))
        return {
            "rate": kursdolar["rate"],
            "yesterday": yesterday,
            "source": "kursdolar",
        }
    rate = fetch_usd_idr_frankfurter()
    if rate:
        return {"rate": rate, "yesterday": None, "source": "Frankfurter (fallback)"}
    raise RuntimeError("Semua sumber kurs USD/IDR gagal diambil")


# ---------------------------------------------------------------------------
# Harga emas lokal (Antam / UBS / Galeri 24) via logam-mulia-api
# ---------------------------------------------------------------------------

def fetch_local_gold_price(source: str, material_type: str, weight: float) -> dict | None:
    """Ambil harga terkini untuk satu source+materialType+weight tertentu."""
    try:
        resp = requests.get(f"{LM_API_BASE}/{source}", timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            return None
        for item in payload.get("data", []):
            if item.get("weight") == weight and item.get("materialType") == material_type:
                return item
    except (requests.RequestException, ValueError):
        return None
    return None


def fetch_local_gold_yesterday(
    source: str, material_type: str, weight: float, today_date: str
) -> int | None:
    """Ambil harga hari sebelumnya untuk source+materialType+weight tertentu."""
    try:
        resp = requests.get(
            f"{LM_API_BASE}/{source}/history",
            params={"weight": weight, "materialType": material_type, "length": 5},
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


def get_local_gold_row(label: str, source: str, material_type: str, weight: float) -> dict:
    """Ambil satu baris data (Sekarang/Kemarin/Gap) untuk satu sumber harga lokal."""
    item = fetch_local_gold_price(source, material_type, weight)
    if not item:
        return {"label": label, "now": None, "yesterday": None}

    price = item.get("sellPrice")
    date = item.get("recordedDate")
    yesterday = fetch_local_gold_yesterday(source, material_type, weight, date)
    return {"label": label, "now": price, "yesterday": yesterday, "date": date}


def _fmt_rp(value) -> str:
    return f"Rp{value:,.0f}" if value is not None else "N/A"


def _fmt_gap(now, yesterday) -> str:
    if now is None or yesterday is None:
        return "-"
    gap = now - yesterday
    arrow = "▲" if gap >= 0 else "▼"
    return f"{arrow}{abs(gap):,.0f}"


def build_price_table(rows: list[dict]) -> str:
    """Bangun tabel monospace (Sumber | Sekarang | Kemarin | Gap) untuk Telegram."""
    headers = ["Sumber", "Sekarang", "Kemarin", "Gap"]
    table_rows = []
    for r in rows:
        table_rows.append(
            [r["label"], _fmt_rp(r["now"]), _fmt_rp(r["yesterday"]), _fmt_gap(r["now"], r["yesterday"])]
        )

    all_rows = [headers] + table_rows
    col_widths = [max(len(row[i]) for row in all_rows) for i in range(4)]

    def fmt_row(row):
        return "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row))

    lines = [fmt_row(headers), "-" * (sum(col_widths) + 6)]
    lines += [fmt_row(r) for r in table_rows]
    return "```\n" + "\n".join(lines) + "\n```"


# ---------------------------------------------------------------------------
# Format pesan
# ---------------------------------------------------------------------------

def format_message(data: dict, fx: dict) -> str:
    """Format data harga emas jadi pesan Telegram yang enak dibaca, pakai tabel monospace"""
    price_usd_oz = data.get("price")
    price_usd_gram = data.get("price_gram_24k")
    prev_close_oz = data.get("prev_close_price")  # dari GoldAPI
    change_usd = data.get("ch") or 0
    change_pct = data.get("chp") or 0

    usd_idr = fx["rate"]
    usd_idr_yesterday = fx.get("yesterday")
    usd_idr_source = fx["source"]

    prev_close_gram = prev_close_oz / OZ_TO_GRAM if prev_close_oz else None
    price_idr_gram = price_usd_gram * usd_idr
    prev_close_idr_gram = prev_close_gram * usd_idr if prev_close_gram else None
    change_idr_gram = price_idr_gram - prev_close_idr_gram if prev_close_idr_gram else 0

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
        f"Kemarin: Rp{prev_close_idr_gram:,.0f} / gram\n" if prev_close_idr_gram else ""
    )

    # Baris-baris tabel: Antam, UBS, Galeri 24, + Kurs USD/IDR
    rows = [
        get_local_gold_row(label, source, material_type, weight)
        for label, source, material_type, weight in GOLD_SOURCES
    ]
    rows.append({"label": "Kurs USD/IDR", "now": usd_idr, "yesterday": usd_idr_yesterday})
    table = build_price_table(rows)

    message = (
        f"🥇 *Update Harga Emas Dunia*\n"
        f"_{now}_\n\n"
        f"*Harga Lokal (per 1 gram, kecuali Kurs)*\n"
        f"{table}\n"
        f"_(sumber kurs: {usd_idr_source})_\n\n"
        f"*Harga Internasional (XAU/USD)*\n"
        f"Sekarang: ${price_usd_oz:,.2f} / oz (${price_usd_gram:,.2f}/gram)\n"
        f"{prev_close_line}"
        f"Gap: {arrow} {change_usd:+.2f} ({change_pct:+.2f}%)\n\n"
        f"*Estimasi dalam Rupiah (per gram, 24k)*\n"
        f"Sekarang: Rp{price_idr_gram:,.0f}\n"
        f"{prev_close_idr_line}"
        f"Gap: {arrow_idr} Rp{abs(change_idr_gram):,.0f}\n"
        f"_(estimasi dari harga emas dunia, biasanya lebih rendah dari harga_\n"
        f"_lokal resmi karena belum termasuk premium cetak & sertifikasi)_"
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
        fx = resolve_usd_idr()
        message = format_message(data, fx)
        send_telegram_message(message)
        print("Berhasil kirim update harga emas.")
    except requests.RequestException as e:
        print(f"ERROR saat request: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()