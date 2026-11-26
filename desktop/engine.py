"""
CleanGram Desktop Hybrid Engine (Mode Cepat Tanpa API + Mode Lokal 100% Direct).
Secara default langsung terhubung ke API aman CleanGram (tanpa perlu user mendaftar API ID),
dan mendukung Mode Lanjutan 100% lokal (Telethon direct PC <-> Telegram) jika diisi API ID sendiri.
"""

import asyncio
import base64
import io
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import qrcode
import requests
from PIL import Image
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

DEFAULT_API_BASE = os.getenv("CLEANGRAM_API_BASE", "https://cleangram-alpha.vercel.app").rstrip("/")
CONFIG_DIR = Path.home() / ".cleangram"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_WHITELIST = ["telegram", "botfather"]
CLOUD_BATCH_SIZE = 15


def normalize_phone(phone: str) -> str:
    """Merapikan format nomor HP Indonesia (08... -> +628...)."""
    cleaned = "".join(ch for ch in phone.strip() if ch.isdigit() or ch == "+")
    if cleaned.startswith("08"):
        cleaned = "+62" + cleaned[1:]
    elif cleaned.startswith("62") and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    elif cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def make_qr_data_uri(qr_url: str) -> str:
    """Merender URI tg://login?token=... menjadi Data URI PNG crisp 100% offline."""
    qr = qrcode.QRCode(border=2, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_url)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="#09090B", back_color="#FFFFFF").get_image().convert("RGB")
    pil_img = pil_img.resize((220, 220), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def load_saved_config() -> dict[str, Any]:
    """Memuat konfigurasi Mode Lanjutan lokal dari ~/.cleangram/config.json."""
    default_cfg: dict[str, Any] = {"api_id": "", "api_hash": "", "use_local_mode": False}
    if not CONFIG_FILE.exists():
        return default_cfg
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        api_id = str(data.get("api_id", "")).strip()
        api_hash = str(data.get("api_hash", "")).strip()
        use_local = bool(data.get("use_local_mode", bool(api_id and api_hash)))
        return {"api_id": api_id, "api_hash": api_hash, "use_local_mode": use_local}
    except Exception:
        return default_cfg


def save_saved_config(api_id: str, api_hash: str, use_local_mode: bool) -> None:
    """Menyimpan konfigurasi API ID lokal ke folder ~/.cleangram/."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(
            {
                "api_id": api_id.strip(),
                "api_hash": api_hash.strip(),
                "use_local_mode": bool(use_local_mode),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_saved_config() -> None:
    """Menghapus API lokal tersimpan dan kembali ke Mode Cepat tanpa API."""
    if CONFIG_FILE.exists():
        try:
            CONFIG_FILE.unlink()
        except Exception:
            pass


def _extract_http_error(resp: requests.Response, fallback: str) -> str:
    try:
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])
    except Exception:
        pass
    return f"{fallback} (HTTP {resp.status_code})"


class DesktopHybridEngine:
    """Engine pembersih Telegram desktop: otomatis Mode Cepat (Tanpa API) atau Mode Lokal Direct."""

    def __init__(self, api_base: str = DEFAULT_API_BASE) -> None:
        self.api_base = api_base.rstrip("/")
        self._http = requests.Session()
        self._http.headers.update({"Content-Type": "application/json", "User-Agent": "CleanGramDesktop/2.0"})

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        self._active_mode: str = "cloud"
        self._flow_token: Optional[str] = None
        self._cloud_pending_qr_2fa: bool = False

        # State khusus Mode Lokal Direct (Telethon)
        self._client: Optional[TelegramClient] = None
        self._api_id: int = 0
        self._api_hash: str = ""
        self._phone: str = ""
        self._phone_code_hash: str = ""
        self._local_needs_2fa: bool = False
        self._targets_map: dict[int, tuple[Any, str]] = {}

        self._cancel_event = threading.Event()
        self._cleaning_lock = threading.Lock()

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_coro(self, coro: Any, timeout: float = 90.0) -> Any:
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    @property
    def active_mode(self) -> str:
        return self._active_mode

    def request_cancel(self) -> None:
        """Meminta penghentian proses pembersihan secara aman."""
        self._cancel_event.set()

    def _validate_local_creds(self, api_id_raw: str, api_hash_raw: str) -> tuple[int, str]:
        raw_id = str(api_id_raw or "").strip()
        raw_hash = str(api_hash_raw or "").strip()
        if not raw_id.isdigit():
            raise ValueError("Mode Lokal aktif, tapi API ID harus berupa angka dari my.telegram.org.")
        if len(raw_hash) < 10:
            raise ValueError("Mode Lokal aktif, tapi API Hash tidak valid.")
        return int(raw_id), raw_hash

    def _choose_mode(self, use_local: bool, api_id_raw: str, api_hash_raw: str) -> tuple[str, Optional[int], Optional[str]]:
        if not use_local:
            return "cloud", None, None
        aid, ahash = self._validate_local_creds(api_id_raw, api_hash_raw)
        return "local", aid, ahash

    # ---- LOCAL TELETHON HELPERS ----
    async def _local_reset_client(self, api_id: int, api_hash: str) -> TelegramClient:
        await self._local_disconnect(logout=False)
        self._api_id = api_id
        self._api_hash = api_hash
        self._local_needs_2fa = False
        self._client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            receive_updates=False,
            device_model="CleanGram Desktop",
            system_version="Windows 11",
            app_version="2.0.0",
            lang_code="en",
            system_lang_code="en",
        )
        await self._client.connect()
        return self._client

    async def _local_disconnect(self, logout: bool = False) -> bool:
        client = self._client
        self._client = None
        self._targets_map.clear()
        self._local_needs_2fa = False
        if not client:
            return False
        logged_out = False
        if logout:
            try:
                if await client.is_user_authorized():
                    await client.log_out()
                    logged_out = True
            except Exception:
                pass
        try:
            await client.disconnect()
        except Exception:
            pass
        return logged_out

    async def _local_start_qr(self, api_id: int, api_hash: str) -> str:
        client = await self._local_reset_client(api_id, api_hash)
        resp = await client(functions.auth.ExportLoginTokenRequest(api_id, api_hash, []))
        if not hasattr(resp, "token"):
            raise ValueError("Gagal mendapatkan token QR dari Telegram.")
        b64 = base64.urlsafe_b64encode(resp.token).decode("ascii").rstrip("=")
        return f"tg://login?token={b64}"

    async def _local_poll_qr(self, whitelist_raw: str) -> dict[str, Any]:
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
            self._local_needs_2fa = True
            return {"status": "2fa_required"}

        if isinstance(resp, tl_types.auth.LoginTokenSuccess):
            await self._client._on_login(resp.authorization.user)
            scan = await self._local_scan_dialogs(whitelist_raw)
            return {"status": "scanned", **scan}

        if hasattr(resp, "token"):
            b64 = base64.urlsafe_b64encode(resp.token).decode("ascii").rstrip("=")
            qr_url = f"tg://login?token={b64}"
            return {"status": "pending", "qr_data_uri": make_qr_data_uri(qr_url)}

        raise ValueError("Status QR tidak terduga. Silakan buat ulang QR.")

    async def _local_send_otp(self, api_id: int, api_hash: str, phone: str) -> dict[str, str]:
        normalized = normalize_phone(phone)
        if len(normalized) < 8:
            raise ValueError("Format nomor HP tidak valid. Gunakan awalan +628... atau 08...")
        client = await self._local_reset_client(api_id, api_hash)
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

    async def _local_verify_scan(self, code: Optional[str], password: Optional[str], whitelist_raw: str) -> dict[str, Any]:
        if not self._client:
            raise ValueError("Sesi belum aktif. Silakan ulangi login.")

        if self._local_needs_2fa:
            if not password:
                return {"status": "2fa_required"}
            try:
                await self._client.sign_in(password=password)
                self._local_needs_2fa = False
            except PasswordHashInvalidError as exc:
                raise ValueError("Password Verifikasi 2 Langkah (2FA) salah.") from exc
        else:
            clean_code = (code or "").strip().replace("-", "").replace(" ", "")
            if not clean_code:
                raise ValueError("Masukkan kode OTP 5 digit.")
            try:
                await self._client.sign_in(
                    self._phone, clean_code, phone_code_hash=self._phone_code_hash
                )
            except SessionPasswordNeededError:
                if password:
                    try:
                        await self._client.sign_in(password=password)
                    except PasswordHashInvalidError as exc:
                        raise ValueError("Password Verifikasi 2 Langkah (2FA) salah.") from exc
                else:
                    self._local_needs_2fa = True
                    return {"status": "2fa_required"}
            except PhoneCodeInvalidError as exc:
                raise ValueError("Kode OTP salah.") from exc
            except PhoneCodeExpiredError as exc:
                raise ValueError("Kode OTP kedaluwarsa. Silakan minta kode baru.") from exc
            except FloodWaitError as exc:
                raise ValueError(f"Limit Telegram: tunggu {exc.seconds} detik.") from exc

        scan = await self._local_scan_dialogs(whitelist_raw)
        return {"status": "scanned", **scan}

    async def _local_scan_dialogs(self, whitelist_raw: str) -> dict[str, Any]:
        assert self._client is not None
        me = await self._client.get_me()
        user_info = {
            "first_name": getattr(me, "first_name", "") or "Pengguna",
            "last_name": getattr(me, "last_name", "") or "",
            "username": getattr(me, "username", None),
        }

        whitelist = list(DEFAULT_WHITELIST)
        if whitelist_raw.strip():
            whitelist.extend(k.strip().lower() for k in whitelist_raw.split(",") if k.strip())

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

    async def _local_clean_single_dialog(self, dialog: Any) -> None:
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
                        peer=dialog.input_entity, max_id=0, just_clear=False, revoke=True
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

    async def _local_clean_all(
        self,
        selected_ids: list[int],
        auto_logout: bool,
        emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        if not self._client:
            raise ValueError("Koneksi Telegram terputus.")

        items = [(did, *self._targets_map[did]) for did in selected_ids if did in self._targets_map]
        total = len(items)
        sukses = 0
        gagal = 0
        cancelled = False

        try:
            for idx, (_did, dialog, tipe) in enumerate(items, 1):
                if self._cancel_event.is_set():
                    cancelled = True
                    break

                name = (dialog.name or "Akun Terhapus")[:50]
                try:
                    await self._local_clean_single_dialog(dialog)
                    sukses += 1
                    emit(
                        {
                            "event": "progress",
                            "processed": idx,
                            "total": total,
                            "status": "ok",
                            "name": name,
                            "type": tipe,
                            "message": "Berhasil keluar & hapus",
                        }
                    )
                    await asyncio.sleep(0.3)
                except FloodWaitError as exc:
                    wait_sec = max(int(exc.seconds), 1)
                    emit(
                        {
                            "event": "wait",
                            "processed": idx - 1,
                            "total": total,
                            "seconds": wait_sec,
                        }
                    )
                    for _ in range(wait_sec):
                        if self._cancel_event.is_set():
                            cancelled = True
                            break
                        await asyncio.sleep(1)
                    if cancelled:
                        break
                    try:
                        await self._local_clean_single_dialog(dialog)
                        sukses += 1
                        emit(
                            {
                                "event": "progress",
                                "processed": idx,
                                "total": total,
                                "status": "ok",
                                "name": name,
                                "type": tipe,
                                "message": "Berhasil setelah jeda limit",
                            }
                        )
                    except Exception as inner_exc:
                        gagal += 1
                        emit(
                            {
                                "event": "progress",
                                "processed": idx,
                                "total": total,
                                "status": "error",
                                "name": name,
                                "type": tipe,
                                "message": str(inner_exc),
                            }
                        )
                except Exception as exc:
                    gagal += 1
                    emit(
                        {
                            "event": "progress",
                            "processed": idx,
                            "total": total,
                            "status": "error",
                            "name": name,
                            "type": tipe,
                            "message": str(exc),
                        }
                    )
        finally:
            logged_out = await self._local_disconnect(logout=auto_logout)

        return {
            "sukses": sukses,
            "gagal": gagal,
            "cancelled": cancelled,
            "logged_out": logged_out,
        }

    # ---- UNIFIED PUBLIC API (CLOUD OR LOCAL) ----
    def start_qr(self, use_local: bool = False, api_id: str = "", api_hash: str = "") -> dict[str, Any]:
        mode, aid, ahash = self._choose_mode(use_local, api_id, api_hash)
        self.logout()
        self._active_mode = mode
        self._cloud_pending_qr_2fa = False

        if mode == "local":
            assert aid is not None and ahash is not None
            qr_url = self._run_coro(self._local_start_qr(aid, ahash), timeout=30)
            return {"mode": "local", "qr_data_uri": make_qr_data_uri(qr_url)}

        resp = self._http.post(
            f"{self.api_base}/api/qr-start",
            json={"custom_api_id": None, "custom_api_hash": None},
            timeout=30,
        )
        if not resp.ok:
            raise ValueError(_extract_http_error(resp, "Gagal membuat QR Code dari server"))
        data = resp.json()
        self._flow_token = data.get("flow_token")
        qr_url = data.get("qr_url", "")
        if not qr_url or not self._flow_token:
            raise ValueError("Respons QR server tidak lengkap.")
        return {"mode": "cloud", "qr_data_uri": make_qr_data_uri(qr_url)}

    def poll_qr(self, whitelist_raw: str = "") -> dict[str, Any]:
        if self._active_mode == "local":
            return self._run_coro(self._local_poll_qr(whitelist_raw), timeout=60)

        if not self._flow_token:
            raise ValueError("Sesi QR telah dibatalkan.")
        resp = self._http.post(
            f"{self.api_base}/api/qr-check",
            json={"flow_token": self._flow_token, "whitelist": whitelist_raw},
            timeout=60,
        )
        if not resp.ok:
            raise ValueError(_extract_http_error(resp, "QR kedaluwarsa atau gagal diperiksa"))
        data = resp.json()
        if data.get("flow_token"):
            self._flow_token = data["flow_token"]

        status = data.get("status")
        if status == "2fa_required":
            self._cloud_pending_qr_2fa = True
            return {"status": "2fa_required"}
        if status == "scanned":
            return {
                "status": "scanned",
                "user": data.get("user", {}),
                "targets": data.get("targets", []),
                "protected": data.get("protected", []),
            }
        qr_url = data.get("qr_url")
        return {
            "status": "pending",
            "qr_data_uri": make_qr_data_uri(qr_url) if qr_url else None,
        }

    def send_otp(
        self, phone: str, use_local: bool = False, api_id: str = "", api_hash: str = ""
    ) -> dict[str, Any]:
        mode, aid, ahash = self._choose_mode(use_local, api_id, api_hash)
        self.logout()
        self._active_mode = mode
        self._cloud_pending_qr_2fa = False

        if mode == "local":
            assert aid is not None and ahash is not None
            res = self._run_coro(self._local_send_otp(aid, ahash, phone), timeout=30)
            return {"mode": "local", **res}

        resp = self._http.post(
            f"{self.api_base}/api/send-code",
            json={"phone": phone, "custom_api_id": None, "custom_api_hash": None},
            timeout=30,
        )
        if not resp.ok:
            raise ValueError(_extract_http_error(resp, "Gagal mengirim OTP"))
        data = resp.json()
        self._flow_token = data.get("flow_token")
        return {
            "mode": "cloud",
            "phone": data.get("phone", normalize_phone(phone)),
            "delivery": data.get("delivery", "Aplikasi Telegram"),
        }

    def verify_scan(
        self, code: Optional[str] = None, password: Optional[str] = None, whitelist_raw: str = ""
    ) -> dict[str, Any]:
        if self._active_mode == "local":
            return self._run_coro(self._local_verify_scan(code, password, whitelist_raw), timeout=90)

        if not self._flow_token:
            raise ValueError("Sesi login tidak ditemukan. Silakan ulangi login.")

        resp = self._http.post(
            f"{self.api_base}/api/verify-scan",
            json={
                "flow_token": self._flow_token,
                "code": (code or "").strip() or None,
                "password": password or None,
                "whitelist": whitelist_raw,
            },
            timeout=90,
        )
        if not resp.ok:
            raise ValueError(_extract_http_error(resp, "Gagal verifikasi / memindai akun"))
        data = resp.json()
        if data.get("flow_token"):
            self._flow_token = data["flow_token"]
        if data.get("status") == "2fa_required":
            return {"status": "2fa_required"}
        return {
            "status": "scanned",
            "user": data.get("user", {}),
            "targets": data.get("targets", []),
            "protected": data.get("protected", []),
        }

    def run_cleaning(
        self,
        selected_ids: list[int],
        auto_logout: bool,
        emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        with self._cleaning_lock:
            self._cancel_event.clear()
            if self._active_mode == "local":
                return self._run_coro(
                    self._local_clean_all(selected_ids, auto_logout, emit),
                    timeout=3600,
                )
            return self._cloud_clean_all(selected_ids, auto_logout, emit)

    def _cloud_clean_all(
        self,
        selected_ids: list[int],
        auto_logout: bool,
        emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        if not self._flow_token:
            raise ValueError("Sesi pembersihan tidak valid.")

        total = len(selected_ids)
        processed = 0
        sukses = 0
        gagal = 0
        cursor = 0
        cancelled = False

        try:
            while cursor < total:
                if self._cancel_event.is_set():
                    cancelled = True
                    break

                batch_ids = selected_ids[cursor : cursor + CLOUD_BATCH_SIZE]
                is_last_batch = (cursor + len(batch_ids)) >= total

                resp = self._http.post(
                    f"{self.api_base}/api/clean-batch",
                    json={
                        "flow_token": self._flow_token,
                        "target_ids": batch_ids,
                        "is_last_batch": is_last_batch,
                        "auto_logout": auto_logout,
                    },
                    timeout=90,
                )
                if not resp.ok:
                    raise ValueError(_extract_http_error(resp, "Gagal membersihkan batch"))
                data = resp.json()
                results = data.get("results", [])

                for item in results:
                    processed += 1
                    st = item.get("status")
                    if st == "ok":
                        sukses += 1
                    else:
                        gagal += 1
                    emit(
                        {
                            "event": "progress",
                            "processed": processed,
                            "total": total,
                            "status": "ok" if st == "ok" else "error",
                            "name": item.get("name", "Item"),
                            "type": item.get("type", "Chat"),
                            "message": item.get("message") or ("Berhasil keluar & hapus" if st == "ok" else "Dilewati"),
                        }
                    )

                cursor += len(results)
                wait_sec = int(data.get("floodwait_seconds") or 0)
                if wait_sec > 0:
                    emit({"event": "wait", "processed": processed, "total": total, "seconds": wait_sec})
                    for _ in range(wait_sec):
                        if self._cancel_event.is_set():
                            cancelled = True
                            break
                        time.sleep(1)
                    if cancelled:
                        break
                    continue

                if not results:
                    cursor += len(batch_ids)
        finally:
            logged_out = False
            if cancelled and auto_logout and self._flow_token:
                logged_out = self.logout()
            elif not cancelled:
                logged_out = bool(auto_logout)
                self._flow_token = None

        return {
            "sukses": sukses,
            "gagal": gagal,
            "cancelled": cancelled,
            "logged_out": logged_out,
        }

    def logout(self) -> bool:
        """Memutus koneksi lokal atau mengirim request logout ke API cloud."""
        logged_out = False
        if self._client is not None:
            try:
                logged_out = bool(self._run_coro(self._local_disconnect(logout=True), timeout=15))
            except Exception:
                pass
        if self._flow_token:
            tok = self._flow_token
            self._flow_token = None
            try:
                resp = self._http.post(
                    f"{self.api_base}/api/logout",
                    json={"flow_token": tok},
                    timeout=15,
                )
                if resp.ok:
                    logged_out = bool(resp.json().get("logged_out", True))
            except Exception:
                pass
        return logged_out

    def shutdown(self) -> None:
        self._cancel_event.set()
        self.logout()
