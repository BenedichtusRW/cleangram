"""
CleanGram Desktop Async Telethon Engine.
Menjalankan koneksi MTProto Telethon secara lokal 100% di PC pengguna
di dalam dedicated asyncio background thread agar GUI tetap responsif.
"""

import asyncio
import base64
import json
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from telethon import TelegramClient, functions
from telethon import types as tl_types
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

CONFIG_DIR = Path.home() / ".cleangram"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_WHITELIST = ["telegram", "botfather"]


def normalize_phone(phone: str) -> str:
    """Merapikan nomor HP Indonesia (08... -> +628...)."""
    cleaned = "".join(ch for ch in phone.strip() if ch.isdigit() or ch == "+")
    if cleaned.startswith("08"):
        cleaned = "+62" + cleaned[1:]
    elif cleaned.startswith("62") and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    elif cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def load_saved_credentials() -> tuple[str, str]:
    """Memuat API ID & Hash milik pengguna dari folder konfigurasi lokal (~/.cleangram)."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            api_id = str(data.get("api_id", "")).strip()
            api_hash = str(data.get("api_hash", "")).strip()
            return api_id, api_hash
        except Exception:
            pass
    return "", ""


def save_credentials(api_id: int, api_hash: str) -> None:
    """Menyimpan API ID & Hash secara lokal di PC pengguna."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps({"api_id": api_id, "api_hash": api_hash}, indent=2),
        encoding="utf-8",
    )


class DesktopCleanerEngine:
    """Mengelola koneksi dan operasi pembersihan Telegram pada background thread asyncio."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        self._client: Optional[TelegramClient] = None
        self._api_id: int = 0
        self._api_hash: str = ""
        self._phone: str = ""
        self._phone_code_hash: str = ""
        self._targets_map: dict[int, tuple[Any, str]] = {}
        self._cancel_requested: bool = False

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(
        self,
        coro: Any,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Menjalankan coroutine di background thread tanpa memblokir GUI Tkinter."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _done(fut: Any) -> None:
            try:
                res = fut.result()
                if on_success:
                    on_success(res)
            except Exception as exc:
                if on_error:
                    on_error(exc)

        future.add_done_callback(_done)

    def request_cancel(self) -> None:
        """Menandai pembatalan proses pembersihan yang sedang berjalan."""
        self._cancel_requested = True

    async def _reset_client(self, api_id: int, api_hash: str) -> TelegramClient:
        await self.disconnect(logout=False)
        self._api_id = api_id
        self._api_hash = api_hash
        self._client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            receive_updates=False,
            device_model="CleanGram Desktop",
            system_version="Windows 11",
            app_version="1.1.0",
            lang_code="en",
            system_lang_code="en",
        )
        await self._client.connect()
        return self._client

    async def disconnect(self, logout: bool = False) -> None:
        """Memutus koneksi client aktif dan opsional melakukan logout permanen."""
        client = self._client
        self._client = None
        self._targets_map.clear()
        if not client:
            return
        if logout:
            try:
                if await client.is_user_authorized():
                    await client.log_out()
            except Exception:
                pass
        try:
            await client.disconnect()
        except Exception:
            pass

    async def start_qr_login(self, api_id: int, api_hash: str) -> str:
        """Memulai sesi QR Code login dan mengembalikan URI tg://login?token=..."""
        client = await self._reset_client(api_id, api_hash)
        resp = await client(functions.auth.ExportLoginTokenRequest(api_id, api_hash, []))
        if not hasattr(resp, "token"):
            raise ValueError("Gagal mendapatkan token QR dari Telegram.")
        b64 = base64.urlsafe_b64encode(resp.token).decode("ascii").rstrip("=")
        return f"tg://login?token={b64}"

    async def poll_qr_status(self) -> dict[str, Any]:
        """Memeriksa apakah QR sudah di-scan pada aplikasi Telegram HP."""
        if not self._client:
            raise ValueError("Sesi QR telah dibatalkan.")

        try:
            resp = await self._client(
                functions.auth.ExportLoginTokenRequest(self._api_id, self._api_hash, [])
            )
            if isinstance(resp, tl_types.auth.LoginTokenMigrateTo):
                await self._client._switch_dc(resp.dc_id)
                resp = await self._client(functions.auth.ImportLoginTokenRequest(resp.token))
        except SessionPasswordNeededError:
            return {"status": "2fa_required"}

        if isinstance(resp, tl_types.auth.LoginTokenSuccess):
            await self._client._on_login(resp.authorization.user)
            return {"status": "authorized"}

        if hasattr(resp, "token"):
            b64 = base64.urlsafe_b64encode(resp.token).decode("ascii").rstrip("=")
            return {"status": "pending", "qr_url": f"tg://login?token={b64}"}

        raise ValueError("Status QR tidak terduga. Silakan buat ulang QR.")

    async def send_otp(self, api_id: int, api_hash: str, phone: str) -> dict[str, str]:
        """Mengirim kode OTP resmi ke akun Telegram pengguna."""
        normalized = normalize_phone(phone)
        if len(normalized) < 8:
            raise ValueError("Format nomor HP tidak valid. Gunakan awalan +628... atau 08...")

        client = await self._reset_client(api_id, api_hash)
        try:
            sent = await client.send_code_request(normalized)
        except PhoneNumberInvalidError as exc:
            raise ValueError("Nomor HP Telegram tidak valid atau tidak terdaftar.") from exc
        except FloodWaitError as exc:
            raise ValueError(f"Terlalu banyak permintaan OTP. Tunggu {exc.seconds} detik.") from exc

        self._phone = normalized
        self._phone_code_hash = sent.phone_code_hash
        code_type = type(sent.type).__name__
        delivery = "Aplikasi Telegram" if "App" in code_type else f"Telegram ({code_type})"
        return {"phone": normalized, "delivery": delivery}

    async def verify_otp(self, code: str) -> dict[str, Any]:
        """Memverifikasi kode OTP 5 digit."""
        if not self._client:
            raise ValueError("Sesi belum dimulai. Kirim ulang OTP terlebih dahulu.")
        clean_code = code.strip().replace("-", "").replace(" ", "")
        if not clean_code:
            raise ValueError("Masukkan kode OTP 5 digit.")

        try:
            await self._client.sign_in(
                self._phone, clean_code, phone_code_hash=self._phone_code_hash
            )
            return {"status": "authorized"}
        except SessionPasswordNeededError:
            return {"status": "2fa_required"}
        except PhoneCodeInvalidError as exc:
            raise ValueError("Kode OTP salah.") from exc
        except PhoneCodeExpiredError as exc:
            raise ValueError("Kode OTP kedaluwarsa. Minta kode baru.") from exc
        except FloodWaitError as exc:
            raise ValueError(f"Limit Telegram: tunggu {exc.seconds} detik.") from exc

    async def verify_2fa(self, password: str) -> dict[str, Any]:
        """Menyelesaikan login akun yang dilindungi password 2FA."""
        if not self._client:
            raise ValueError("Sesi login tidak aktif.")
        if not password:
            raise ValueError("Password 2FA tidak boleh kosong.")
        try:
            await self._client.sign_in(password=password)
            return {"status": "authorized"}
        except PasswordHashInvalidError as exc:
            raise ValueError("Password Verifikasi 2 Langkah (2FA) salah.") from exc

    async def scan_dialogs(self, whitelist_raw: str = "") -> dict[str, Any]:
        """Memindai seluruh grup, saluran, bot, dan kontak akun yang terhubung."""
        if not self._client:
            raise ValueError("Belum terhubung ke akun Telegram.")

        me = await self._client.get_me()
        user_info = {
            "first_name": getattr(me, "first_name", "") or "Pengguna",
            "last_name": getattr(me, "last_name", "") or "",
            "username": getattr(me, "username", None),
        }

        whitelist = list(DEFAULT_WHITELIST)
        if whitelist_raw.strip():
            whitelist.extend(
                k.strip().lower() for k in whitelist_raw.split(",") if k.strip()
            )

        dialogs = await self._client.get_dialogs()
        self._targets_map.clear()
        protected: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []

        for dialog in dialogs:
            entity = dialog.entity
            if getattr(entity, "is_self", False):
                continue

            name = (dialog.name or "").strip() or "[Tanpa Nama]"
            name_lower = name.lower()
            uname = (getattr(entity, "username", None) or "").lower()

            if dialog.is_user and getattr(entity, "contact", False):
                protected.append({"id": dialog.id, "name": name, "username": uname, "reason": "Kontak HP"})
                continue

            if any(kw in name_lower or (uname and kw in uname) for kw in whitelist):
                protected.append({"id": dialog.id, "name": name, "username": uname, "reason": "Dilindungi"})
                continue

            if dialog.is_group or dialog.is_channel:
                tipe = "Grup" if dialog.is_group else "Saluran"
                self._targets_map[dialog.id] = (dialog, tipe)
                targets.append({"id": dialog.id, "name": name, "username": uname, "type": tipe})
                continue

            if dialog.is_user and getattr(entity, "bot", False):
                self._targets_map[dialog.id] = (dialog, "Bot")
                targets.append({"id": dialog.id, "name": name, "username": uname, "type": "Bot"})
                continue

            if dialog.is_user and getattr(entity, "deleted", False):
                self._targets_map[dialog.id] = (dialog, "Akun Terhapus")
                targets.append({"id": dialog.id, "name": "Akun Terhapus", "username": "", "type": "Akun Terhapus"})
                continue

            if dialog.is_user:
                protected.append({"id": dialog.id, "name": name, "username": uname, "reason": "Chat Pribadi"})

        return {"user": user_info, "protected": protected, "targets": targets}

    async def _clean_single_dialog(self, dialog: Any) -> None:
        """Keluar dari grup/saluran dan hapus riwayat chat total tanpa memblokir."""
        assert self._client is not None
        if dialog.is_channel:
            try:
                await self._client(functions.channels.LeaveChannelRequest(dialog.input_entity))
            except Exception:
                pass
            try:
                await self._client(functions.channels.DeleteHistoryRequest(channel=dialog.input_entity, max_id=0))
            except Exception:
                pass
        elif dialog.is_group:
            try:
                await self._client(functions.messages.DeleteChatUserRequest(chat_id=dialog.id, user_id="me"))
            except Exception:
                pass

        while True:
            try:
                res = await self._client(
                    functions.messages.DeleteHistoryRequest(
                        peer=dialog.input_entity,
                        max_id=0,
                        just_clear=False,
                        revoke=True,
                    )
                )
                if not hasattr(res, "offset") or res.offset == 0:
                    break
                await asyncio.sleep(0.15)
            except Exception:
                break

        try:
            await self._client.delete_dialog(dialog, revoke=True)
        except Exception:
            pass

    async def clean_targets(
        self,
        selected_ids: list[int],
        auto_logout: bool,
        on_progress: Callable[[int, int, str, str, str, str], None],
    ) -> dict[str, Any]:
        """Menjalankan pembersihan seluruh item terpilih dengan jeda FloodWait otomatis."""
        if not self._client:
            raise ValueError("Koneksi Telegram terputus.")

        self._cancel_requested = False
        items = [
            (did, *self._targets_map[did])
            for did in selected_ids
            if did in self._targets_map
        ]
        total = len(items)
        sukses = 0
        gagal = 0
        cancelled = False

        try:
            for idx, (did, dialog, tipe) in enumerate(items, 1):
                if self._cancel_requested:
                    cancelled = True
                    break

                name = (dialog.name or "Akun Terhapus")[:45]
                try:
                    await self._clean_single_dialog(dialog)
                    sukses += 1
                    on_progress(idx, total, name, tipe, "ok", "Berhasil keluar & hapus")
                    await asyncio.sleep(0.3)
                except FloodWaitError as exc:
                    on_progress(idx, total, name, tipe, "wait", f"Limit Telegram: jeda {exc.seconds} detik...")
                    await asyncio.sleep(exc.seconds)
                    if self._cancel_requested:
                        cancelled = True
                        break
                    try:
                        await self._clean_single_dialog(dialog)
                        sukses += 1
                        on_progress(idx, total, name, tipe, "ok", "Berhasil setelah jeda limit")
                    except Exception as inner_exc:
                        gagal += 1
                        on_progress(idx, total, name, tipe, "error", str(inner_exc))
                except Exception as exc:
                    gagal += 1
                    on_progress(idx, total, name, tipe, "error", str(exc))
        finally:
            await self.disconnect(logout=auto_logout)

        return {
            "sukses": sukses,
            "gagal": gagal,
            "cancelled": cancelled,
            "logged_out": auto_logout,
        }
