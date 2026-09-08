# Telegram `/info` → trigger GitHub Actions on-demand

Komponen ini bikin bot Telegram bisa langsung kirim update harga emas kapan saja kamu ketik `/info`, tanpa nunggu jadwal 2 jam.

**Alur kerjanya:**
```
Kamu ketik /info di Telegram
        ↓
Telegram kirim webhook ke Cloudflare Worker
        ↓
Worker verifikasi chat ID kamu + secret token
        ↓
Worker panggil GitHub API (repository_dispatch)
        ↓
GitHub Actions workflow "Gold Price Update" langsung jalan
        ↓
Bot kirim pesan harga emas terbaru (proses yang sama seperti jadwal 2 jam)
```

## Setup

### 1. Install Wrangler (CLI Cloudflare)
```bash
npm install -g wrangler
wrangler login
```
Ikuti instruksi login lewat browser (pakai akun Cloudflare gratis, buat baru kalau belum punya).

### 2. Buat GitHub Personal Access Token (fine-grained)
1. GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained tokens** → **Generate new token**
2. **Repository access**: pilih **Only select repositories** → pilih repo `gold-price-bot` kamu (bukan semua repo, biar aman)
3. **Permissions** → **Repository permissions** → **Contents**: set ke **Read and write**
   ⚠️ Bukan "Actions" — endpoint `repository_dispatch` butuh permission **Contents**, meskipun yang di-trigger adalah workflow Actions. (`Metadata: Read-only` otomatis ke-select bareng Contents, biarkan saja.)
4. Generate, lalu **simpan token-nya** (cuma muncul sekali)

### 3. Deploy Worker
```bash
cd telegram-webhook
wrangler deploy
```
Setelah sukses, kamu akan dapat URL Worker, formatnya:
`https://gold-price-bot-webhook.<subdomain-kamu>.workers.dev`

### 4. Set secrets di Worker
Jalankan satu-satu (Wrangler akan minta kamu ketik value-nya setelah command):
```bash
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_WEBHOOK_SECRET
wrangler secret put GITHUB_PAT
wrangler secret put GITHUB_OWNER
wrangler secret put GITHUB_REPO
wrangler secret put ALLOWED_CHAT_ID
```

Isi masing-masing:
- `TELEGRAM_BOT_TOKEN` → token bot kamu (yang sama dipakai di GitHub Secrets)
- `TELEGRAM_WEBHOOK_SECRET` → string rahasia bebas buatan sendiri, misal hasil dari `openssl rand -hex 20`
- `GITHUB_PAT` → token dari langkah 2
- `GITHUB_OWNER` → username GitHub kamu, misal `Rafli277`
- `GITHUB_REPO` → nama repo, misal `gold-price-bot`
- `ALLOWED_CHAT_ID` → chat ID Telegram kamu (yang sudah kamu ambil sebelumnya lewat getUpdates)

### 5. Daftarkan webhook ke Telegram
Ganti `<BOT_TOKEN>`, `<WORKER_URL>`, `<WEBHOOK_SECRET>` sesuai punya kamu, lalu akses URL ini di browser (atau `curl`):
```
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<WEBHOOK_SECRET>
```
Contoh:
```
https://api.telegram.org/bot8825785045:AAH.../setWebhook?url=https://gold-price-bot-webhook.rafli.workers.dev&secret_token=abcd1234...
```
Kalau sukses, responsnya `{"ok":true,"result":true,"description":"Webhook was set"}`.

### 6. Test
Ketik `/info` ke bot kamu di Telegram. Harusnya:
1. Bot langsung balas "⏳ Oke, lagi ambil harga emas terbaru..."
2. Beberapa detik kemudian, GitHub Actions workflow jalan (cek tab **Actions**, event-nya akan tertulis "Triggered via repository_dispatch")
3. Bot kirim pesan harga emas lengkap seperti biasa

## Catatan keamanan
- Worker **menolak** request yang bukan dari Telegram (cek header secret token) dan **mengabaikan** command dari chat ID selain punya kamu — jadi orang lain yang nemu bot kamu di Telegram gak bisa spam-trigger workflow kamu.
- GitHub PAT dibatasi cuma untuk 1 repo dan cuma permission Actions — kalau bocor, dampaknya terbatas (bukan akses penuh ke semua repo kamu).
- Cloudflare Workers free tier: 100.000 request/hari — jauh lebih dari cukup untuk pemakaian personal.

## Kalau mau nonaktifkan fitur ini
```
https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook
```
Bot akan berhenti dengar pesan masuk (tapi jadwal update tiap 2 jam tetap jalan seperti biasa, karena itu independen).