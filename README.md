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

## 💻 Opsi 2: Aplikasi Desktop Windows (`desktop/` — Tanpa Setup API + Mode Lokal)

Tampilan modern *Obsidian Dark* dengan 2 mode fleksibel: **Mode Cepat (Default)** langsung jalan lewat Scan QR / OTP tanpa perlu daftar API ID, plus **Mode Lanjutan 100% Lokal** bagi pengguna yang ingin koneksi langsung PC ↔ Telegram dengan API pribadi.

### Download Langsung (Tanpa Install Python):
👉 **[Download CleanGram.exe (Windows)](https://github.com/BenedichtusRW/cleangram/releases/latest/download/CleanGram.exe)** *(lihat semua rilis di [GitHub Releases](https://github.com/BenedichtusRW/cleangram/releases))*
* **Syarat Minimum:** Windows 10 / 11 (64-bit).

### Menjalankan dari Source:
```bash
cd desktop
pip install -r requirements.txt
python app.py
```

### Build Menjadi `CleanGram.exe` Standalone:
Jalankan script [`desktop/build_exe.bat`](desktop/build_exe.bat) untuk menghasilkan file `desktop/dist/CleanGram.exe` (tidak butuh install Python saat dijalankan).

---

## 📱 Opsi 3: Aplikasi Android Native (`mobile/` — Flutter)

Aplikasi Android native dengan ikon **CleanGram**, login via **Nomor HP & OTP** atau **Scan QR**, serta pembersihan batch aman melalui API `https://cleangram-alpha.vercel.app` (*Zero Storage* & *Auto-Logout*).

### Download Langsung:
👉 **[Download CleanGram.apk (Android)](https://github.com/BenedichtusRW/cleangram/releases/latest/download/CleanGram.apk)** *(atau pilih rilis di [GitHub Releases](https://github.com/BenedichtusRW/cleangram/releases))*
* **Syarat Minimum:** **Android 7.0 (Nougat) ke atas — 64-bit (`arm64-v8a`)**. Untuk HP Android 32-bit, Android 6 ke bawah, atau iPhone/iPad (iOS), silakan langsung pakai versi **Website / PWA**.

### Build dari Source:
```bash
cd mobile
flutter pub get
flutter build apk --release
```
Hasil compile APK berada di `mobile/build/app/outputs/flutter-apk/app-release.apk`.

---

## ⚙️ Opsi 4: Cara Manual via Terminal / CLI (`clean_telegram_groups.py`)

Cocok untuk membersihkan ribuan grup secara *direct* 100% lokal (bebas batas waktu server), bisa dijalankan di **Laptop (Windows / Mac / Linux)** maupun **HP Android**.

### Persiapan Awal (Wajib):
Dapatkan **API ID** & **API HASH** gratis terlebih dahulu dari [https://my.telegram.org](https://my.telegram.org) ➔ **API development tools**.

### A. Menjalankan di Laptop / PC (Windows, MacBook, Linux):
1. Pastikan **Python 3** sudah terpasang.
2. Install library Telethon dan jalankan script:
   ```bash
   pip install telethon
   python clean_telegram_groups.py
   ```
   *(Di macOS/Linux gunakan `pip3` dan `python3` jika `python` belum tersedia).*

### B. Menjalankan di HP Android (Tanpa PC):
Pilih salah satu aplikasi gratis berikut:
* **Via Termux (Disarankan — install dari [F-Droid](https://f-droid.org/packages/com.termux/) / GitHub, bukan Play Store):**
  ```bash
  pkg update && pkg install python git -y
  pip install telethon
  git clone https://github.com/BenedichtusRW/cleangram.git
  cd cleangram
  python clean_telegram_groups.py
  ```
* **Via Pydroid 3 (Alternatif Praktis di Play Store):**
  1. Buka menu **Pip** di Pydroid 3 ➔ ketik **`telethon`** ➔ **Install**.
  2. Download file `clean_telegram_groups.py` dari repository ini, buka di Pydroid 3, lalu tekan tombol **Play (▶)**.

### Alur Penggunaan di Terminal:
1. Masukkan **API ID**, **API HASH** *(otomatis disimpan lokal di `config_telegram.json`)*, **Nomor HP Telegram**, kode **OTP**, dan password **2FA** jika aktif.
2. Tambahkan kata kunci grup penting Anda (misal: `kampus, kantor, keluarga, bisnis`). Kontak HP otomatis aman 100%.
3. Periksa daftar **Dilindungi** & **Target**, lalu ketik **`y`** dan **Enter** untuk mulai membersihkan.

---

## 💡 Tips Pencegahan (Biar Gak Dimasukin Grup Spam Lagi)
Buka aplikasi Telegram di HP Anda:
> **Settings (Pengaturan)** ➔ **Privacy and Security (Privasi)** ➔ **Groups & Channels** ➔ Ubah menjadi **`My Contacts (Kontak Saya)`**.

---

<p align="center">Built by <a href="https://github.com/BenedichtusRW"><strong>ben_dev</strong></a></p>
