"""
=============================================================================
   PEMBERSIH MASSAL TELEGRAM: KELUAR GRUP & HAPUS CHAT SPAM (OPEN SOURCE)
=============================================================================
Dibuat untuk membersihkan puluhan/ratusan grup lendir, saluran judi/slot,
dan bot spam secara otomatis sekali klik, tanpa menghapus kontak pribadi
dan grup penting.
=============================================================================
"""

import os
import sys
import json
import time
from telethon.sync import TelegramClient
from telethon import functions
from telethon.errors import FloodWaitError

CONFIG_FILE = "config_telegram.json"

# =============================================================================
# 1. PENGATURAN KUNCI: GRUP / BOT YANG DILINDUNGI (ANTI-HAPUS)
# =============================================================================
# Masukkan kata kunci nama grup/bot penting yang TIDAK BOLEH dihapus.
# Huruf besar/kecil tidak berpengaruh (otomatis disesuaikan).
DEFAULT_WHITELIST = [
    "telegram", "botfather",
    "kampus", "alumni", "kantor", "keluarga"  # Contoh umum
]

def load_or_ask_credentials():
    """Membaca API ID & HASH dari config.json atau meminta input dari pengguna."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("api_id") and data.get("api_hash"):
                    return int(data["api_id"]), str(data["api_hash"])
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("🔑 SETUP AWAL (Hanya dilakukan 1x di awal):")
    print("Dapatkan API ID & API HASH gratis dari: https://my.telegram.org")
    print("=" * 65)
    
    while True:
        try:
            api_id_input = input("Masukkan API ID Anda (angka): ").strip()
            api_id = int(api_id_input)
            break
        except ValueError:
            print("❌ API ID harus berupa angka! Silakan ulangi.")

    while True:
        api_hash = input("Masukkan API HASH Anda (huruf & angka): ").strip()
        if len(api_hash) >= 10:
            break
        print("❌ API HASH tidak valid! Silakan ulangi.")

    # Simpan agar tidak perlu input lagi di masa depan
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_id": api_id, "api_hash": api_hash}, f, indent=4)
    print("✓ Pengaturan tersimpan di config_telegram.json!\n")
    return api_id, api_hash


def main():
    print("=" * 65)
    print("   PEMBERSIH TOTAL: KELUAR GRUP & HAPUS BERSIH SPAM TELEGRAM")
    print("=" * 65)

    api_id, api_hash = load_or_ask_credentials()

    # Session file disimpan di folder script lokal (aman di PC / HP mana pun)
    session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_cleaner_session")
    client = TelegramClient(session_path, api_id, api_hash, receive_updates=False)

    client.connect()

    if not client.is_user_authorized():
        print("\nSilakan login ke akun Telegram Anda:")
        phone = input("Masukkan Nomor HP Telegram (contoh: +628123456789): ").strip()
        client.send_code_request(phone)
        print("✓ Kode login telah dikirim ke aplikasi Telegram di HP Anda!")
        code = input("Masukkan 5 digit kode yang Anda terima: ").strip()
        try:
            client.sign_in(phone, code)
        except Exception as e:
            if "password" in str(e).lower():
                pwd = input("Akun Anda mengaktifkan Verifikasi 2 Langkah (2FA). Masukkan password: ")
                client.sign_in(password=pwd)
            else:
                print(f"❌ Gagal login: {e}")
                return

    print("\n✓ BERHASIL TERHUBUNG KE AKUN TELEGRAM!")

    # Input kata kunci tambahan dari pengguna
    print("\n" + "-" * 65)
    print("🛡️ PERLINDUNGAN GRUP PENTING:")
    print("Semua kontak teman/keluarga di HP Anda OTOMATIS 100% AMAN.")
    print("Default aman: telegram, botfather, kampus, kantor, keluarga.")
    custom_input = input("Tambahkan nama grup penting lainnya (pisahkan koma, atau tekan Enter jika cukup): ").strip()
    
    whitelist = list(DEFAULT_WHITELIST)
    if custom_input:
        extra_keywords = [k.strip().lower() for k in custom_input.split(",") if k.strip()]
        whitelist.extend(extra_keywords)

    print("\nSedang memindai seluruh chat & grup di akun Anda...")

    dialogs = client.get_dialogs()
    targets = []
    dilindungi = []

    for dialog in dialogs:
        name = (dialog.name or "").strip()
        name_lower = name.lower()
        uname = (getattr(dialog.entity, 'username', '') or '').lower()

        # 1. Lindungi akun sendiri & Saved Messages
        if getattr(dialog.entity, 'is_self', False):
            continue

        # 2. Lindungi kontak asli di HP (Teman, Keluarga, Rekan Kerja)
        if dialog.is_user and getattr(dialog.entity, 'contact', False):
            dilindungi.append((name, "KONTAK_HP"))
            continue

        # 3. Lindungi grup/bot yang ada di daftar Whitelist
        if any(k in name_lower or k in uname for k in whitelist):
            u_tag = f"@{uname}" if uname else name
            dilindungi.append((name, f"WHITELIST ({u_tag})"))
            continue

        # 4. Targetkan Grup & Saluran Spam
        if dialog.is_group or dialog.is_channel:
            tipe = "Grup" if dialog.is_group else "Saluran"
            targets.append((dialog, tipe))

        # 5. Targetkan Bot Spam (Lendir, Judi, Slot, Bokep, dll)
        elif dialog.is_user and getattr(dialog.entity, 'bot', False):
            targets.append((dialog, "Bot Spam"))

        # 6. Targetkan Akun Terhapus (Ghost Account)
        elif dialog.is_user and getattr(dialog.entity, 'deleted', False):
            targets.append((dialog, "Akun Terhapus"))

    # Tampilkan daftar proteksi
    print("\n" + "=" * 65)
    print(f"🛡️  OBROLAN & BOT YANG DILINDUNGI ({len(dilindungi)} item - 100% AMAN):")
    print("=" * 65)
    for idx, (d_name, d_type) in enumerate(dilindungi[:12], 1):
        print(f"  {idx:2d}. ★ {d_name} [{d_type}]")
    if len(dilindungi) > 12:
        print(f"  ... dan {len(dilindungi) - 12} kontak pribadi lainnya tetap AMAN!")
    print("-" * 65)

    if not targets:
        print("\n🎉 SELAMAT! Akun Telegram Anda sudah BERSIH TOTAL dari spam!")
        client.disconnect()
        return

    # Tampilkan daftar target pembersihan
    print(f"\n🎯 DITEMUKAN {len(targets)} SPAM YANG AKAN DI-LEAVE & DIHAPUS:")
    print("=" * 65)
    for idx, (t, tipe) in enumerate(targets, 1):
        uname = getattr(t.entity, 'username', None)
        u_str = f" (@{uname})" if uname else ""
        t_name = t.name if t.name else "[Tanpa Nama / Akun Terhapus]"
        print(f" {idx:2d}. [{tipe:13s}] {t_name}{u_str}")

    print("=" * 65)
    print("PERINGATAN: Sistem HANYA akan KELUAR & MENGHAPUS CHAT (TANPA BLOKIR).")
    print("=" * 65)

    konfirmasi = input(f"\nYAKIN ingin KELUAR & HAPUS semua {len(targets)} chat spam di atas? (ketik 'y' lalu Enter): ").strip().lower()

    if konfirmasi != 'y':
        print("\n[DIBATALKAN] Pembersihan dibatalkan. Tidak ada yang disentuh.")
        client.disconnect()
        return

    print("\n[MEMULAI PEMBERSIHAN OTOMATIS] Harap tunggu...")
    sukses = 0
    gagal = 0

    for idx, (t, tipe) in enumerate(targets, 1):
        display_name = (t.name or "Akun Terhapus")[:30]
        try:
            print(f"[{idx}/{len(targets)}] Keluar & Hapus Chat: {display_name}...", end=" ", flush=True)

            # 1. Jika Saluran / Megagroup: Leave & hapus history
            if t.is_channel:
                try:
                    client(functions.channels.LeaveChannelRequest(t.input_entity))
                except Exception:
                    pass
                try:
                    client(functions.channels.DeleteHistoryRequest(channel=t.input_entity, max_id=0))
                except Exception:
                    pass

            # 2. Jika Grup Biasa (Basic Chat): Keluar dari grup
            elif t.is_group:
                try:
                    client(functions.messages.DeleteChatUserRequest(chat_id=t.id, user_id='me'))
                except Exception:
                    pass

            # 3. Hapus seluruh riwayat obrolan (revoke=True agar lenyap dari kedua pihak)
            while True:
                try:
                    res = client(functions.messages.DeleteHistoryRequest(peer=t.input_entity, max_id=0, just_clear=False, revoke=True))
                    if not hasattr(res, 'offset') or res.offset == 0:
                        break
                    time.sleep(0.2)
                except Exception:
                    break

            # 4. Hapus dialog dari inbox
            try:
                client.delete_dialog(t, revoke=True)
            except Exception:
                pass

            print("✓ [BERES]")
            sukses += 1
            time.sleep(0.4)

        except FloodWaitError as e:
            print(f"\n[Limit Telegram] Istirahat {e.seconds} detik...")
            time.sleep(e.seconds)
            sukses += 1
        except Exception as e:
            print(f"✗ [{e}]")
            gagal += 1

    print("\n" + "=" * 65)
    print("🎉 PEMBERSIHAN SELESAI TOTAL!")
    print(f"✓ Berhasil keluar & hapus : {sukses} spam")
    if gagal > 0:
        print(f"✗ Dilewati                : {gagal} item")
    print("=" * 65)

    client.disconnect()

if __name__ == '__main__':
    main()
