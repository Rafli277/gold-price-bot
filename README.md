# Gold Price Telegram Bot

Bot yang kirim update harga emas dunia (XAU/USD) ke Telegram setiap 2 jam, jalan otomatis lewat GitHub Actions (gratis, tanpa server).

## Setup

### 1. Buat Telegram Bot
1. Chat `@BotFather` di Telegram → `/newbot` → ikuti instruksi.
2. Simpan **token** yang diberikan (format: `123456:ABC-DEF...`).

### 2. Dapatkan Chat ID
- Untuk chat pribadi: kirim pesan apa saja ke bot kamu, lalu buka:
  `https://api.telegram.org/bot<TOKEN>/getUpdates`
  Cari nilai `"chat":{"id": ...}`.
- Untuk channel: tambahkan bot sebagai admin channel, chat id-nya biasanya diawali `-100`.

### 3. Dapatkan API Key Harga Emas
Daftar gratis di [goldapi.io](https://www.goldapi.io) (free tier ~100 request/bulan, cukup untuk update tiap 2 jam = 12x/hari = ~360/bulan — cek limit, kalau kurang bisa upgrade atau ganti sumber seperti metals-api.com/API Ninjas).

### 4. Push repo ini ke GitHub

```bash
cd gold-price-bot
git init
git add .
git commit -m "init gold price bot"
git branch -M main
git remote add origin <URL_REPO_KAMU>
git push -u origin main
```

### 5. Set GitHub Secrets
Di repo GitHub: **Settings → Secrets and variables → Actions → New repository secret**, tambahkan 3 secret:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GOLD_API_KEY`

### 6. Test manual
Buka tab **Actions** di repo → pilih workflow "Gold Price Update" → **Run workflow** untuk test tanpa nunggu jadwal.

## Catatan
- Jadwal cron `0 */2 * * *` jalan tiap 2 jam berdasarkan **UTC**, bukan WIB — kalau mau selaras waktu tertentu di WIB, geser jamnya (WIB = UTC+7).
- GitHub Actions scheduled workflow bisa telat beberapa menit saat beban tinggi — normal, bukan bug.
- Kalau repo private, cron GitHub Actions tetap jalan tapi ada batas menit runner gratis/bulan (biasanya lebih dari cukup untuk task sesingkat ini).
