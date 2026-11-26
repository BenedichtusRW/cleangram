<p align="center">
  <img src="web/static/logo.png" alt="CleanGram Logo" width="120" style="border-radius: 24px;" />
</p>

<h1 align="center">🧹 CleanGram</h1>

<p align="center">
  <strong>Pembersih Massal Grup Spam, Saluran Tak Dikenal, & Bot Spam Telegram</strong><br/>
  Tersedia dalam versi <strong>Website & Mobile PWA</strong> (<a href="https://cleangram-alpha.vercel.app"><strong>cleangram-alpha.vercel.app</strong></a>) serta <strong>Script CLI Python</strong> dengan perlindungan kontak otomatis.
</p>

<p align="center">
  <a href="https://cleangram-alpha.vercel.app">🌐 <strong>Buka CleanGram Web Live (Gratis &amp; Tanpa Install)</strong></a>
</p>

---

## ✨ Fitur Unggulan
1. 🚪 **Keluar Massal Otomatis:** Keluar dari puluhan/ratusan grup & saluran spam dalam hitungan detik.
2. 🗑️ **Hapus Riwayat Chat Total:** Menghapus riwayat percakapan spam (`revoke=True`) sampai bersih tuntas.
3. 🛡️ **Proteksi Kontak HP (Anti-Hapus):** Semua nomor yang tersimpan di kontak HP & chat pribadi manusia **100% AMAN**.
4. 📝 **Custom Whitelist Dinamis:** Lindungi grup penting Anda menggunakan kata kunci khusus (misal: `kampus`, `kantor`, `keluarga`).
5. 🔒 **Zero-Storage Privacy (Versi Web):** Berjalan sementara di RAM, tanpa database, dan otomatis **Logout permanen** dari *Telegram Devices* setelah selesai.
6. ⛔ **Tanpa Pemblokiran:** Hanya keluar dan hapus chat, tidak memblokir akun.

---

## 🌐 Opsi 1: Menjalankan Website & Mobile PWA (Folder `web/`)

Versi Web dibangun dengan **FastAPI + Async Telethon + Tailwind CSS** dan mendukung **PWA** (*Add to Home Screen* di Android/iOS).

### Jalankan secara Lokal:
```bash
cd web
pip install -r requirements.txt
uvicorn main:app --reload
```
Buka browser lalu akses: `http://127.0.0.1:8000`

### Deploy Gratis Tanpa Kartu Kredit ke Vercel:
Repository ini sudah dikonfigurasi *stateless* dan dilengkapi [`web/vercel.json`](web/vercel.json).
1. Import repository ini di dashboard **[Vercel.com](https://vercel.com)** (akun Hobby Free).
2. Atur **Root Directory** ke `web`.
3. Tambahkan Environment Variables di Vercel:
   * `TELEGRAM_API_ID`
   * `TELEGRAM_API_HASH`
4. Klik **Deploy** — web langsung online tanpa *auto-sleep*!

---

## ⚙️ Opsi 2: Cara Manual via Terminal / CLI (`clean_telegram_groups.py`)

### Persyaratan:
1. **Python 3** (Laptop atau HP Android via *Pydroid 3* / *Termux*).
2. Install library Telethon:
   ```bash
   pip install telethon
   ```
3. Dapatkan **API ID** & **API HASH** gratis dari [https://my.telegram.org](https://my.telegram.org) ➔ **API development tools**.

### Cara Menjalankan:
```bash
python clean_telegram_groups.py
```
1. Masukkan **API ID**, **API HASH**, Nomor HP Telegram, dan kode OTP yang masuk.
2. Tambahkan kata kunci grup penting Anda (misal: `kampus, kantor, keluarga, bisnis`).
3. Periksa daftar **Dilindungi** & **Target**, lalu ketik **`y`** dan **Enter**.

---

## 💡 Tips Pencegahan (Biar Gak Dimasukin Grup Spam Lagi)
Buka aplikasi Telegram di HP Anda:
> **Settings (Pengaturan)** ➔ **Privacy and Security (Privasi)** ➔ **Groups & Channels** ➔ Ubah menjadi **`My Contacts (Kontak Saya)`**.
