"""
CleanGram Async Telethon Service (Stateless Encrypted-Token Architecture).
Menjalankan autentikasi OTP/2FA, pemindaian dialog dengan proteksi whitelist/kontak,
dan pembersihan massal tanpa database atau penyimpanan sesi di disk/RAM server.
Kompatibel penuh dengan Vercel Serverless, Docker, maupun Uvicorn lokal.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import zlib
from pathlib import Path
from typing import Any, Optional

import pyaes
from dotenv import load_dotenv
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
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DEFAULT_WHITELIST = ["telegram", "botfather"]
TOKEN_TTL_SECONDS = 1800  # 30 menit masa berlaku token sementara di memori browser


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
        "Silakan buka menu 'Mode Developer' dan masukkan API ID/Hash dari my.telegram.org."
    )


def _get_master_secret() -> bytes:
    """Mengambil kunci enkripsi konsisten untuk token sesi sementara."""
    seed = (
        os.getenv("SESSION_SECRET")
        or os.getenv("TELEGRAM_API_HASH")
        or os.getenv("API_HASH")
    )
    if not seed:
        local_cfg = PROJECT_ROOT / "config_telegram.json"
        if local_cfg.exists():
            try:
                seed = str(json.loads(local_cfg.read_text(encoding="utf-8")).get("api_hash", ""))
            except Exception:
                seed = ""
    if not seed:
        seed = "cleangram-ephemeral-default-key-v1"
    return f"cleangram-stateless:{seed}".encode("utf-8")


def encrypt_state(payload: dict[str, Any]) -> str:
    """Mengenkripsi state sesi menggunakan AES-256-CTR + HMAC-SHA256 (Encrypt-then-MAC)."""
    master = _get_master_secret()
    enc_key = hashlib.sha256(b"enc:" + master).digest()
    mac_key = hashlib.sha256(b"mac:" + master).digest()

    raw = zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), level=6)
    nonce = secrets.token_bytes(16)
    counter = pyaes.Counter(int.from_bytes(nonce, "big"))
    ciphertext = pyaes.AESModeOfOperationCTR(enc_key, counter=counter).encrypt(raw)

    ts_bytes = int(time.time()).to_bytes(8, "big")
    body = ts_bytes + nonce + ciphertext
    tag = hmac.new(mac_key, body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + tag).decode("ascii")


def decrypt_state(token: str, ttl: int = TOKEN_TTL_SECONDS) -> dict[str, Any]:
    """Memverifikasi integritas HMAC, TTL, dan mendekripsi token sesi sementara."""
    if not token:
        raise ValueError("Sesi tidak ditemukan. Silakan mulai ulang dari langkah Nomor HP.")

    try:
        raw_blob = base64.urlsafe_b64decode(token.encode("ascii"))
    except Exception as exc:
        raise ValueError("Token sesi tidak valid. Silakan ulangi login.") from exc

    if len(raw_blob) < 8 + 16 + 32:
        raise ValueError("Format token sesi rusak. Silakan ulangi login.")

    body, tag = raw_blob[:-32], raw_blob[-32:]
    master = _get_master_secret()
    enc_key = hashlib.sha256(b"enc:" + master).digest()
    mac_key = hashlib.sha256(b"mac:" + master).digest()

    expected_tag = hmac.new(mac_key, body, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_tag, tag):
        raise ValueError("Token sesi tidak valid atau kunci server berubah. Silakan login ulang.")

    ts = int.from_bytes(body[:8], "big")
    if (time.time() - ts) > ttl:
        raise ValueError("Sesi sudah kedaluwarsa (batas 30 menit). Silakan mulai ulang.")

    nonce = body[8:24]
    ciphertext = body[24:]
    counter = pyaes.Counter(int.from_bytes(nonce, "big"))
    compressed = pyaes.AESModeOfOperationCTR(enc_key, counter=counter).decrypt(ciphertext)

    try:
        return json.loads(zlib.decompress(compressed).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Gagal membaca state sesi. Silakan ulangi login.") from exc


def _build_client(session_str: str, api_id: int, api_hash: str) -> TelegramClient:
    """Membuat instance Telethon ephemeral berbasis StringSession."""
    return TelegramClient(
        StringSession(session_str),
        api_id,
        api_hash,
        receive_updates=False,
        device_model="Desktop",
        system_version="Windows 11",
        app_version="5.9.0",
        lang_code="en",
        system_lang_code="en",
    )


def _serialize_peer(dialog: Any, tipe: str) -> Optional[dict[str, Any]]:
    """Menyimpan informasi InputPeer ringan agar cleanup batch berjalan tanpa re-scan."""
    ie = dialog.input_entity
    name = (dialog.name or "Akun Terhapus").strip()[:45]
    if isinstance(ie, InputPeerChannel):
        return {"k": "ch", "i": int(ie.channel_id), "h": int(ie.access_hash), "t": tipe, "n": name}
    if isinstance(ie, InputPeerChat):
        return {"k": "gp", "i": int(ie.chat_id), "t": tipe, "n": name}
    if isinstance(ie, InputPeerUser):
        return {"k": "us", "i": int(ie.user_id), "h": int(ie.access_hash), "t": tipe, "n": name}
    return None


def _reconstruct_peer(peer_data: dict[str, Any]) -> Any:
    """Membangun kembali objek InputPeer Telethon dari metadata terenkripsi."""
    kind = peer_data["k"]
    if kind == "ch":
        return InputPeerChannel(int(peer_data["i"]), int(peer_data["h"]))
    if kind == "gp":
        return InputPeerChat(int(peer_data["i"]))
    if kind == "us":
        return InputPeerUser(int(peer_data["i"]), int(peer_data["h"]))
    raise ValueError(f"Tipe peer tidak dikenal: {kind}")


class Require2FAError(Exception):
    """Sentinel exception saat Telegram meminta password 2FA."""

    def __init__(self, flow_token: str) -> None:
        super().__init__("2FA required")
        self.flow_token = flow_token


async def start_login(
    phone: str,
    custom_api_id: Optional[int] = None,
    custom_api_hash: Optional[str] = None,
) -> dict[str, str]:
    """Mengirim kode OTP Telegram dan menghasilkan token sesi terenkripsi."""
    normalized = normalize_phone(phone)
    if len(normalized) < 8:
        raise ValueError("Format nomor HP tidak valid. Gunakan format +628... atau 08...")

    api_id, api_hash = resolve_credentials(custom_api_id, custom_api_hash)
    client = _build_client("", api_id, api_hash)

    try:
        await client.connect()
        sent = await client.send_code_request(normalized)
        session_str = client.session.save()
    except PhoneNumberInvalidError as exc:
        raise ValueError("Nomor HP Telegram tidak terdaftar atau format salah.") from exc
    except FloodWaitError as exc:
        raise ValueError(
            f"Terlalu banyak permintaan OTP. Tunggu {exc.seconds} detik lagi."
        ) from exc
    except Exception as exc:
        raise ValueError(f"Gagal mengirim OTP Telegram: {exc}") from exc
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    code_type = type(sent.type).__name__
    if "App" in code_type:
        delivery = "Aplikasi Telegram (chat resmi dari Telegram)"
    elif "Sms" in code_type:
        delivery = "SMS ke nomor HP Anda"
    elif "Email" in code_type:
        delivery = "Email akun Telegram Anda"
    else:
        delivery = f"Telegram ({code_type})"

    state = {
        "s": session_str,
        "p": normalized,
        "h": sent.phone_code_hash,
        "aid": api_id,
        "ah": api_hash,
        "auth": False,
        "2fa": False,
        "peers": {},
    }
    return {"flow_token": encrypt_state(state), "phone": normalized, "delivery": delivery}


async def _authenticate_client(
    client: TelegramClient,
    state: dict[str, Any],
    code: Optional[str],
    password: Optional[str],
) -> None:
    """Melakukan sign_in dengan OTP dan fallback 2FA."""
    try:
        if state.get("2fa"):
            if not password:
                raise Require2FAError(encrypt_state(state))
            await client.sign_in(password=password)
        else:
            clean_code = (code or "").strip().replace("-", "").replace(" ", "")
            if not clean_code:
                raise ValueError("Masukkan kode OTP 5 digit dari Telegram Anda.")
            try:
                await client.sign_in(
                    state["p"], clean_code, phone_code_hash=state["h"]
                )
            except SessionPasswordNeededError:
                state["2fa"] = True
                state["s"] = client.session.save()
                if password:
                    await client.sign_in(password=password)
                else:
                    raise Require2FAError(encrypt_state(state))

        state["auth"] = True
        state["2fa"] = False
        state["s"] = client.session.save()
    except Require2FAError:
        raise
    except PhoneCodeInvalidError as exc:
        raise ValueError("Kode OTP salah. Periksa kembali pesan resmi dari Telegram.") from exc
    except PhoneCodeExpiredError as exc:
        raise ValueError("Kode OTP sudah kedaluwarsa. Silakan minta ulang OTP baru.") from exc
    except PasswordHashInvalidError as exc:
        raise ValueError("Password Verifikasi 2 Langkah (2FA) salah. Silakan coba lagi.") from exc
    except FloodWaitError as exc:
        raise ValueError(f"Terlalu banyak percobaan login. Tunggu {exc.seconds} detik.") from exc


def classify_dialogs(dialogs: list[Any], whitelist_raw: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Mengklasifikasikan dialog menjadi daftar dilindungi, daftar target, dan peta InputPeer."""
    whitelist = list(DEFAULT_WHITELIST)
    if whitelist_raw.strip():
        extra = [k.strip().lower() for k in whitelist_raw.split(",") if k.strip()]
        whitelist.extend(extra)

    protected: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    peers: dict[str, dict[str, Any]] = {}

    for dialog in dialogs:
        entity = dialog.entity
        if getattr(entity, "is_self", False):
            continue

        name = (dialog.name or "").strip() or "[Tanpa Nama]"
        name_lower = name.lower()
        uname = (getattr(entity, "username", None) or "").lower()

        # 1. Kontak buku telepon HP 100% dilindungi
        if dialog.is_user and getattr(entity, "contact", False):
            protected.append({"id": dialog.id, "name": name, "username": uname, "reason": "Kontak HP"})
            continue

        # 2. Cocok dengan kata kunci Whitelist
        if any(kw in name_lower or (uname and kw in uname) for kw in whitelist):
            protected.append({"id": dialog.id, "name": name, "username": uname, "reason": "Whitelist"})
            continue

        # 3. Target: Grup & Saluran (Channel)
        if dialog.is_group or dialog.is_channel:
            tipe = "Grup" if dialog.is_group else "Saluran"
            peer_meta = _serialize_peer(dialog, tipe)
            if peer_meta:
                peers[str(dialog.id)] = peer_meta
                targets.append({"id": dialog.id, "name": name, "username": uname, "type": tipe})
            continue

        # 4. Target: Bot (Spam / Tidak masuk Whitelist)
        if dialog.is_user and getattr(entity, "bot", False):
            peer_meta = _serialize_peer(dialog, "Bot")
            if peer_meta:
                peers[str(dialog.id)] = peer_meta
                targets.append({"id": dialog.id, "name": name, "username": uname, "type": "Bot"})
            continue

        # 5. Target: Akun Terhapus (Deleted Account)
        if dialog.is_user and getattr(entity, "deleted", False):
            peer_meta = _serialize_peer(dialog, "Akun Terhapus")
            if peer_meta:
                peers[str(dialog.id)] = peer_meta
                targets.append({"id": dialog.id, "name": "Akun Terhapus", "username": "", "type": "Akun Terhapus"})
            continue

        # 6. Chat pribadi manusia non-kontak tetap aman
        if dialog.is_user:
            protected.append({"id": dialog.id, "name": name, "username": uname, "reason": "Chat Pribadi"})

    return protected, targets, peers


async def _scan_authorized_client(
    client: TelegramClient,
    state: dict[str, Any],
    whitelist_raw: str = "",
) -> dict[str, Any]:
    """Memindai akun yang sudah login, menyimpan peta peer, dan mengembalikan respon siap pakai."""
    me = await client.get_me()
    user_info = {
        "first_name": getattr(me, "first_name", "") or "Pengguna",
        "last_name": getattr(me, "last_name", "") or "",
        "username": getattr(me, "username", None),
        "phone": state.get("p") or getattr(me, "phone", None) or "",
    }

    dialogs = await client.get_dialogs()
    protected, targets, peers = classify_dialogs(dialogs, whitelist_raw)

    state["s"] = client.session.save()
    state["peers"] = peers

    return {
        "status": "scanned",
        "flow_token": encrypt_state(state),
        "user": user_info,
        "protected_count": len(protected),
        "target_count": len(targets),
        "protected": protected,
        "targets": targets,
    }


def _encode_qr_url(token_bytes: bytes) -> str:
    """Mengubah token biner Telegram menjadi URI tg://login?token=..."""
    b64 = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
    return f"tg://login?token={b64}"


async def qr_start(
    custom_api_id: Optional[int] = None,
    custom_api_hash: Optional[str] = None,
) -> dict[str, str]:
    """Memulai login berbasis QR Code Telegram (tanpa perlu SMS/OTP)."""
    api_id, api_hash = resolve_credentials(custom_api_id, custom_api_hash)
    client = _build_client("", api_id, api_hash)

    try:
        await client.connect()
        resp = await client(functions.auth.ExportLoginTokenRequest(api_id, api_hash, []))
        session_str = client.session.save()
    except FloodWaitError as exc:
        raise ValueError(f"Terlalu banyak permintaan QR. Tunggu {exc.seconds} detik.") from exc
    except Exception as exc:
        raise ValueError(f"Gagal membuat QR Code Telegram: {exc}") from exc
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    if not hasattr(resp, "token"):
        raise ValueError("Respon QR Telegram tidak terduga. Silakan coba lagi.")

    state = {
        "s": session_str,
        "p": "QR Login",
        "h": "",
        "aid": api_id,
        "ah": api_hash,
        "auth": False,
        "2fa": False,
        "peers": {},
    }
    return {
        "flow_token": encrypt_state(state),
        "qr_url": _encode_qr_url(resp.token),
    }


async def qr_check(flow_token: str, whitelist_raw: str = "") -> dict[str, Any]:
    """Memeriksa status scan QR; jika sudah di-scan langsung memindai grup/kontak."""
    state = decrypt_state(flow_token)
    api_id = int(state["aid"])
    api_hash = str(state["ah"])
    client = _build_client(state["s"], api_id, api_hash)

    try:
        await client.connect()
        try:
            resp = await client(functions.auth.ExportLoginTokenRequest(api_id, api_hash, []))
            if isinstance(resp, tl_types.auth.LoginTokenMigrateTo):
                await client._switch_dc(resp.dc_id)
                resp = await client(functions.auth.ImportLoginTokenRequest(resp.token))
        except SessionPasswordNeededError:
            state["2fa"] = True
            state["s"] = client.session.save()
            raise Require2FAError(encrypt_state(state))

        if isinstance(resp, tl_types.auth.LoginTokenSuccess):
            user = resp.authorization.user
            await client._on_login(user)
            state["auth"] = True
            state["2fa"] = False
            state["p"] = getattr(user, "phone", None) or "QR Login"
            return await _scan_authorized_client(client, state, whitelist_raw=whitelist_raw)

        if hasattr(resp, "token"):
            state["s"] = client.session.save()
            return {
                "status": "pending",
                "flow_token": encrypt_state(state),
                "qr_url": _encode_qr_url(resp.token),
            }

        raise ValueError("Status QR tidak dikenali. Silakan buat ulang QR Code.")
    except Require2FAError:
        raise
    except Exception as exc:
        msg = str(exc)
        if "EXPIRED" in msg.upper() or "INVALID" in msg.upper():
            raise ValueError("QR Code sudah kedaluwarsa. Klik muat ulang QR.") from exc
        raise ValueError(f"Gagal memeriksa status QR: {exc}") from exc
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def verify_and_scan(
    flow_token: str,
    code: Optional[str] = None,
    password: Optional[str] = None,
    whitelist_raw: str = "",
) -> dict[str, Any]:
    """Memverifikasi login, memindai dialog, dan menyertakan token terbarui."""
    state = decrypt_state(flow_token)
    client = _build_client(state["s"], int(state["aid"]), str(state["ah"]))

    try:
        await client.connect()
        if not state.get("auth"):
            await _authenticate_client(client, state, code=code, password=password)

        return await _scan_authorized_client(client, state, whitelist_raw=whitelist_raw)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def _clean_single_peer(client: TelegramClient, peer: Any, kind: str) -> None:
    """Keluar dari grup/saluran dan menghapus seluruh riwayat obrolan tanpa memblokir."""
    if kind == "ch":
        try:
            await client(functions.channels.LeaveChannelRequest(peer))
        except Exception:
            pass
        try:
            await client(functions.channels.DeleteHistoryRequest(channel=peer, max_id=0))
        except Exception:
            pass
    elif kind == "gp":
        try:
            await client(functions.messages.DeleteChatUserRequest(chat_id=peer.chat_id, user_id="me"))
        except Exception:
            pass

    while True:
        try:
            res = await client(
                functions.messages.DeleteHistoryRequest(
                    peer=peer,
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
        await client.delete_dialog(peer, revoke=True)
    except Exception:
        pass


async def clean_batch(
    flow_token: str,
    target_ids: list[int],
    is_last_batch: bool = True,
    auto_logout: bool = True,
) -> dict[str, Any]:
    """Membersihkan satu batch item (aman dari timeout serverless) lalu opsional logout."""
    state = decrypt_state(flow_token)
    if not state.get("auth"):
        raise ValueError("Akun belum terverifikasi.")

    peers_map: dict[str, dict[str, Any]] = state.get("peers", {})
    client = _build_client(state["s"], int(state["aid"]), str(state["ah"]))

    results: list[dict[str, Any]] = []
    sukses = 0
    gagal = 0
    floodwait_seconds = 0
    logged_out = False

    try:
        await client.connect()

        for did in target_ids:
            meta = peers_map.get(str(did))
            if not meta:
                gagal += 1
                results.append({"id": did, "name": str(did), "type": "-", "status": "error", "message": "Metadata hilang"})
                continue

            peer = _reconstruct_peer(meta)
            kind = meta["k"]
            name = meta.get("n", "Tanpa Nama")
            tipe = meta.get("t", "Target")

            try:
                await _clean_single_peer(client, peer, kind)
                sukses += 1
                results.append({"id": did, "name": name, "type": tipe, "status": "ok", "message": "Berhasil keluar & hapus riwayat"})
                await asyncio.sleep(0.3)
            except FloodWaitError as exc:
                if exc.seconds <= 12:
                    await asyncio.sleep(exc.seconds)
                    try:
                        await _clean_single_peer(client, peer, kind)
                        sukses += 1
                        results.append({"id": did, "name": name, "type": tipe, "status": "ok", "message": "Berhasil setelah jeda limit"})
                        continue
                    except Exception as inner_exc:
                        gagal += 1
                        results.append({"id": did, "name": name, "type": tipe, "status": "error", "message": str(inner_exc)})
                else:
                    floodwait_seconds = exc.seconds
                    break
            except Exception as exc:
                gagal += 1
                results.append({"id": did, "name": name, "type": tipe, "status": "error", "message": str(exc)})

        if is_last_batch and auto_logout and floodwait_seconds == 0:
            try:
                await client.log_out()
                logged_out = True
            except Exception:
                pass

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    return {
        "results": results,
        "sukses": sukses,
        "gagal": gagal,
        "floodwait_seconds": floodwait_seconds,
        "logged_out": logged_out,
    }


async def logout_flow(flow_token: str) -> bool:
    """Me-logout sesi sementara secara permanen dari server Telegram."""
    try:
        state = decrypt_state(flow_token)
    except Exception:
        return False

    if not state.get("auth"):
        return True

    client = _build_client(state["s"], int(state["aid"]), str(state["ah"]))
    try:
        await client.connect()
        await client.log_out()
        return True
    except Exception:
        return False
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
