# 🧹 CleanGram (Pembersih Massal Grup & Spam Telegram)

**CleanGram** adalah aplikasi otomatis untuk **keluar dari puluhan/ratusan grup spam, saluran lendir/judi, dan bot spam** sekali klik, dengan **perlindungan otomatis (whitelist protection)** untuk kontak pribadi dan grup penting.

---

## ✨ Fitur Unggulan
1. 🚪 **Keluar Massal Otomatis:** Keluar dari semua grup/saluran spam dalam hitungan detik.
2. 🗑️ **Hapus Riwayat Chat Total:** Menghapus riwayat percakapan spam sampai bersih tuntas.
3. 🛡️ **Proteksi Kontak HP (Anti-Hapus):** Semua nomor telepon yang tersimpan di kontak HP Anda **100% AMAN**.
4. 📝 **Custom Whitelist Dinamis:** Anda bisa menentukan kata kunci grup penting (misal: `kampus`, `kantor`, `keluarga`) agar tidak ikut terhapus.
5. ⛔ **Tanpa Pemblokiran:** Hanya keluar dan hapus chat, tidak memblokir akun.

---

## 🛠️ Persyaratan Awal (Untuk Orang Awam)
1. **Python 3** (di Laptop atau HP Android lewat aplikasi *Pydroid 3* / *Termux*).
2. **Library Telethon:**
   Buka Terminal / Command Prompt (CMD), lalu ketik:
   ```bash
   pip install telethon
   ```
3. **API ID & API HASH Telegram (Gratis dari Telegram):**
   * Buka browser, kunjungi: [https://my.telegram.org](https://my.telegram.org)
   * Masukkan nomor HP Telegram Anda, lalu masukkan kode konfirmasi yang masuk di Telegram.
   * Pilih menu **API development tools**.
   * Isi kolom `App title` dan `Short name` sembarang (misal: `pembersih`).
   * Salin **`api_id`** (angka) dan **`api_hash`** (kombinasi huruf & angka).

---

## 🚀 Cara Menjalankan

1. Buka folder script ini di Terminal / CMD / Pydroid 3.
2. Jalankan perintah:
   ```bash
   python clean_telegram_groups.py
   ```
3. Di awal, masukkan:
   * **API ID** & **API HASH** Anda (hanya diminta 1x, otomatis tersimpan).
   * Nomor HP Telegram & kode login yang masuk.
   * Kata kunci grup penting Anda (misal: `kampus, kantor, keluarga, bisnis`).
4. Script akan menampilkan:
   * 🛡️ Daftar yang **DILINDUNGI** (Aman).
   * 🎯 Daftar yang **AKAN DIHAPUS**.
5. Ketik **`y`** lalu tekan **Enter**! Selesai, akun Anda langsung bersih kinclong!

---

## 💡 Tips Pencegahan (Biar Gak Dimasukin Grup Spam Lagi)
Buka aplikasi Telegram di HP Anda:
> **Settings (Pengaturan)** ➔ **Privacy and Security (Privasi)** ➔ **Groups & Channels** ➔ Ubah menjadi **`My Contacts (Kontak Saya)`**.
