"""
CleanGram Async Telethon Service (Ephemeral In-Memory Architecture).
Handles OTP login, 2FA verification, dialog scanning, whitelist protection,
and bulk leaving/deleting spam dialogs without blocking or storing persistent sessions.
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from dotenv import load_dotenv
from telethon import TelegramClient, functions
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

# Muat .env jika ada (berguna saat development lokal maupun hosting)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DEFAULT_WHITELIST = ["telegram", "botfather"]
SESSION_TTL_SECONDS = 600  # 10 menit batas sesi aktif di RAM


def normalize_phone(phone: str) -> str:
    """Merapikan format nomor HP (mengubah awalan 08 menjadi +628)."""
    cleaned = "".join(ch for ch in phone.strip() if ch.isdigit() or ch == "+")
    if cleaned.startswith("08"):
        cleaned = "+62" + cleaned[1:]
    elif cleaned.startswith("62") and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    elif cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def resolve_credentials(
    custom_api_id: Optional[int] = None,
    custom_api_hash: Optional[str] = None,
) -> tuple[int, str]:
    """Menentukan API ID & API Hash dari input custom, env var, atau config lokal."""
    if custom_api_id and custom_api_hash and len(custom_api_hash.strip()) >= 10:
        return int(custom_api_id), custom_api_hash.strip()

    env_id = os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID")
    env_hash = os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH")
    if env_id and env_hash:
        return int(env_id), env_hash.strip()

    local_cfg = PROJECT_ROOT / "config_telegram.json"
    if local_cfg.exists():
        try:
            data = json.loads(local_cfg.read_text(encoding="utf-8"))
            if data.get("api_id") and data.get("api_hash"):
                return int(data["api_id"]), str(data["api_hash"]).strip()
        except Exception:
            pass

    raise ValueError(
        "API ID & API Hash Telegram belum dikonfigurasi di server. "
        "Silakan buka menu 'Gunakan API Sendiri' di bawah dan isi API ID/Hash dari my.telegram.org."
    )


@dataclass
class FlowState:
    """Menyimpan state sementara untuk satu sesi pengunjung di RAM."""

    flow_id: str
    client: TelegramClient
    phone: str
    phone_code_hash: str
    authorized: bool = False
    awaiting_2fa: bool = False
    targets_map: dict[int, tuple[Any, str]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_active = time.time()


class CleanGramSessionManager:
    """Mengelola sesi ephemeral Telethon secara asinkron tanpa menyimpan ke disk."""

    def __init__(self) -> None:
        self._flows: dict[str, FlowState] = {}

    async def purge_expired(self) -> None:
        """Membersihkan sesi yang idle melebihi TTL dari memori server."""
        now = time.time()
        expired_ids = [
            fid
            for fid, state in self._flows.items()
            if (now - state.last_active) > SESSION_TTL_SECONDS
        ]
        for fid in expired_ids:
            await self.destroy_flow(fid, logout=True)

    async def destroy_flow(self, flow_id: str, logout: bool = True) -> bool:
        """Logout sesi dari Telegram Devices & hapus tuntas dari RAM server."""
        state = self._flows.pop(flow_id, None)
        if not state:
            return False

        if logout and state.authorized:
            try:
                await state.client.log_out()
            except Exception:
                pass

        try:
            await state.client.disconnect()
        except Exception:
            pass
        return True

    def _get_flow(self, flow_id: str) -> FlowState:
        state = self._flows.get(flow_id)
        if not state:
            raise ValueError(
                "Sesi telah berakhir atau tidak ditemukan. Silakan ulangi dari langkah Nomor HP."
            )
        state.touch()
        return state

    async def start_login(
        self,
        phone: str,
        custom_api_id: Optional[int] = None,
        custom_api_hash: Optional[str] = None,
    ) -> dict[str, str]:
        """Mengirim kode OTP login Telegram ke nomor HP pengguna."""
        await self.purge_expired()

        normalized = normalize_phone(phone)
        if len(normalized) < 8:
            raise ValueError("Format nomor HP tidak valid. Gunakan format +628...")

        api_id, api_hash = resolve_credentials(custom_api_id, custom_api_hash)

        client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            receive_updates=False,
            device_model="CleanGram Web",
            system_version="Web Cloud",
            app_version="1.0.0",
        )

        try:
            await client.connect()
            sent = await client.send_code_request(normalized)
        except PhoneNumberInvalidError as exc:
            await client.disconnect()
            raise ValueError("Nomor HP Telegram tidak terdaftar atau format salah.") from exc
        except FloodWaitError as exc:
            await client.disconnect()
            raise ValueError(
                f"Terlalu banyak permintaan OTP. Tunggu {exc.seconds} detik lagi."
            ) from exc
        except Exception as exc:
            await client.disconnect()
            raise ValueError(f"Gagal mengirim OTP Telegram: {exc}") from exc

        flow_id = uuid.uuid4().hex
        self._flows[flow_id] = FlowState(
            flow_id=flow_id,
            client=client,
            phone=normalized,
            phone_code_hash=sent.phone_code_hash,
        )
        return {"flow_id": flow_id, "phone": normalized}

    async def verify_and_scan(
        self,
        flow_id: str,
        code: Optional[str] = None,
        password: Optional[str] = None,
        whitelist_raw: str = "",
    ) -> dict[str, Any]:
        """Verifikasi OTP/2FA lalu memindai seluruh grup, saluran, dan bot di akun."""
        state = self._get_flow(flow_id)

        if not state.authorized:
            await self._authenticate_flow(state, code=code, password=password)

        me = await state.client.get_me()
        user_info = {
            "first_name": getattr(me, "first_name", "") or "Pengguna",
            "last_name": getattr(me, "last_name", "") or "",
            "username": getattr(me, "username", None),
            "phone": state.phone,
        }

        whitelist = list(DEFAULT_WHITELIST)
        if whitelist_raw.strip():
            extra = [k.strip().lower() for k in whitelist_raw.split(",") if k.strip()]
            whitelist.extend(extra)

        dialogs = await state.client.get_dialogs()
        state.targets_map.clear()

        protected: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []

        for dialog in dialogs:
            entity = dialog.entity
            if getattr(entity, "is_self", False):
                continue

            name = (dialog.name or "").strip() or "[Tanpa Nama]"
            name_lower = name.lower()
            uname = (getattr(entity, "username", None) or "").lower()

            # 1. Kontak buku telepon HP 100% dilindungi
            if dialog.is_user and getattr(entity, "contact", False):
                protected.append(
                    {"id": dialog.id, "name": name, "username": uname, "reason": "Kontak HP"}
                )
                continue

            # 2. Cocok dengan kata kunci Whitelist
            if any(kw in name_lower or (uname and kw in uname) for kw in whitelist):
                protected.append(
                    {"id": dialog.id, "name": name, "username": uname, "reason": "Whitelist"}
                )
                continue

            # 3. Target: Grup & Saluran (Channel)
            if dialog.is_group or dialog.is_channel:
                tipe = "Grup" if dialog.is_group else "Saluran"
                state.targets_map[dialog.id] = (dialog, tipe)
                targets.append(
                    {"id": dialog.id, "name": name, "username": uname, "type": tipe}
                )
                continue

            # 4. Target: Bot (Spam / Tak Terdaftar di Whitelist)
            if dialog.is_user and getattr(entity, "bot", False):
                state.targets_map[dialog.id] = (dialog, "Bot")
                targets.append(
                    {"id": dialog.id, "name": name, "username": uname, "type": "Bot"}
                )
                continue

            # 5. Target: Akun Terhapus (Deleted Account)
            if dialog.is_user and getattr(entity, "deleted", False):
                state.targets_map[dialog.id] = (dialog, "Akun Terhapus")
                targets.append(
                    {
                        "id": dialog.id,
                        "name": "Akun Terhapus",
                        "username": "",
                        "type": "Akun Terhapus",
                    }
                )
                continue

            # 6. Chat pribadi manusia non-kontak tetap aman (tidak ikut terhapus)
            if dialog.is_user:
                protected.append(
                    {"id": dialog.id, "name": name, "username": uname, "reason": "Chat Pribadi"}
                )

        return {
            "status": "scanned",
            "flow_id": flow_id,
            "user": user_info,
            "protected_count": len(protected),
            "target_count": len(targets),
            "protected": protected,
            "targets": targets,
        }

    async def _authenticate_flow(
        self,
        state: FlowState,
        code: Optional[str],
        password: Optional[str],
    ) -> None:
        """Menangani login OTP dan fallback 2FA tanpa duplikasi logika."""
        try:
            if state.awaiting_2fa:
                if not password:
                    raise _Require2FAError()
                await state.client.sign_in(password=password)
            else:
                clean_code = (code or "").strip().replace("-", "").replace(" ", "")
                if not clean_code:
                    raise ValueError("Masukkan kode OTP 5 digit dari Telegram Anda.")
                try:
                    await state.client.sign_in(
                        state.phone, clean_code, phone_code_hash=state.phone_code_hash
                    )
                except SessionPasswordNeededError:
                    state.awaiting_2fa = True
                    if password:
                        await state.client.sign_in(password=password)
                    else:
                        raise _Require2FAError()

            state.authorized = True
            state.awaiting_2fa = False
        except _Require2FAError:
            raise
        except PhoneCodeInvalidError as exc:
            raise ValueError("Kode OTP salah. Periksa kembali pesan resmi dari Telegram.") from exc
        except PhoneCodeExpiredError as exc:
            await self.destroy_flow(state.flow_id, logout=False)
            raise ValueError("Kode OTP sudah kedaluwarsa. Silakan minta ulang OTP baru.") from exc
        except PasswordHashInvalidError as exc:
            raise ValueError("Password Verifikasi 2 Langkah (2FA) salah. Silakan coba lagi.") from exc
        except FloodWaitError as exc:
            raise ValueError(
                f"Terlalu banyak percobaan login. Tunggu {exc.seconds} detik."
            ) from exc

    async def _clean_single_dialog(self, client: TelegramClient, dialog: Any) -> None:
        """Keluar dari grup/saluran dan hapus riwayat chat (TANPA memblokir)."""
        if dialog.is_channel:
            try:
                await client(functions.channels.LeaveChannelRequest(dialog.input_entity))
            except Exception:
                pass
            try:
                await client(
                    functions.channels.DeleteHistoryRequest(channel=dialog.input_entity, max_id=0)
                )
            except Exception:
                pass
        elif dialog.is_group:
            try:
                await client(
                    functions.messages.DeleteChatUserRequest(chat_id=dialog.id, user_id="me")
                )
            except Exception:
                pass

        while True:
            try:
                res = await client(
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
            await client.delete_dialog(dialog, revoke=True)
        except Exception:
            pass

    async def stream_clean(
        self,
        flow_id: str,
        selected_ids: list[int],
        auto_logout: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Menjalankan pembersihan secara asinkron dan mengalirkan progres SSE ke UI."""
        state = self._get_flow(flow_id)
        if not state.authorized:
            raise ValueError("Akun belum terverifikasi.")

        selected_items = [
            (did, *state.targets_map[did])
            for did in selected_ids
            if did in state.targets_map
        ]

        total = len(selected_items)
        yield f"data: {json.dumps({'event': 'start', 'total': total})}\n\n"

        sukses = 0
        gagal = 0

        try:
            for idx, (did, dialog, tipe) in enumerate(selected_items, 1):
                state.touch()
                display_name = (dialog.name or "Akun Terhapus")[:45]

                try:
                    await self._clean_single_dialog(state.client, dialog)
                    sukses += 1
                    payload = {
                        "event": "progress",
                        "current": idx,
                        "total": total,
                        "id": did,
                        "name": display_name,
                        "type": tipe,
                        "status": "ok",
                        "message": "Berhasil keluar & hapus riwayat",
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    await asyncio.sleep(0.35)

                except FloodWaitError as exc:
                    wait_sec = min(exc.seconds, 60)
                    yield f"data: {json.dumps({'event': 'floodwait', 'seconds': wait_sec, 'name': display_name})}\n\n"
                    await asyncio.sleep(wait_sec)
                    try:
                        await self._clean_single_dialog(state.client, dialog)
                        sukses += 1
                    except Exception as inner_exc:
                        gagal += 1
                        yield f"data: {json.dumps({'event': 'progress', 'current': idx, 'total': total, 'id': did, 'name': display_name, 'type': tipe, 'status': 'error', 'message': str(inner_exc)})}\n\n"

                except Exception as exc:
                    gagal += 1
                    payload = {
                        "event": "progress",
                        "current": idx,
                        "total": total,
                        "id": did,
                        "name": display_name,
                        "type": tipe,
                        "status": "error",
                        "message": str(exc),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

        finally:
            await self.destroy_flow(flow_id, logout=auto_logout)

        yield f"data: {json.dumps({'event': 'done', 'sukses': sukses, 'gagal': gagal, 'logged_out': auto_logout})}\n\n"


class _Require2FAError(Exception):
    """Internal sentinel exception saat Telegram meminta password 2FA."""


session_manager = CleanGramSessionManager()
