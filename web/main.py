"""
CleanGram Web Application (FastAPI Backend — Stateless & Serverless-Ready).
Menyediakan antarmuka web responsif (Desktop & Mobile PWA) serta API stateless
yang aman berjalan di Vercel Serverless, Docker, maupun Uvicorn lokal.
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from cleaner_service import (  # noqa: E402
    Require2FAError,
    clean_batch,
    logout_flow,
    qr_check,
    qr_start,
    start_login,
    verify_and_scan,
)

app = FastAPI(
    title="CleanGram Web",
    description="Pembersih Massal Grup & Spam Telegram dengan Proteksi Whitelist",
    version="1.1.0",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.middleware("http")
async def add_static_cache_headers(request: Request, call_next):
    """Menambahkan header Cache-Control untuk file statis agar hemat CPU server."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800")
    return response


class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=25)
    custom_api_id: Optional[int] = None
    custom_api_hash: Optional[str] = None


class VerifyScanRequest(BaseModel):
    flow_token: str
    code: Optional[str] = None
    password: Optional[str] = None
    whitelist: str = ""


class CleanBatchRequest(BaseModel):
    flow_token: str
    target_ids: list[int]
    is_last_batch: bool = True
    auto_logout: bool = True


class LogoutRequest(BaseModel):
    flow_token: str


class QrStartRequest(BaseModel):
    custom_api_id: Optional[int] = None
    custom_api_hash: Optional[str] = None


class QrCheckRequest(BaseModel):
    flow_token: str
    whitelist: str = ""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Menampilkan halaman utama CleanGram."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/sw.js")
async def service_worker():
    """Menyajikan Service Worker dari root scope agar PWA terdeteksi penuh."""
    sw_path = BASE_DIR / "static" / "sw.js"
    return HTMLResponse(
        content=sw_path.read_text(encoding="utf-8"),
        media_type="application/javascript",
    )


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Endpoint kesehatan untuk monitor uptime (GET & HEAD)."""
    return {"status": "ok", "service": "cleangram-web"}


@app.post("/api/send-code")
async def api_send_code(payload: SendCodeRequest):
    """Mengirim kode OTP login resmi ke Telegram pengguna."""
    try:
        result = await start_login(
            phone=payload.phone,
            custom_api_id=payload.custom_api_id,
            custom_api_hash=payload.custom_api_hash,
        )
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kesalahan server: {exc}") from exc


@app.post("/api/verify-scan")
async def api_verify_scan(payload: VerifyScanRequest):
    """Memverifikasi OTP/2FA dan memindai daftar grup/kontak akun pengguna."""
    try:
        result = await verify_and_scan(
            flow_token=payload.flow_token,
            code=payload.code,
            password=payload.password,
            whitelist_raw=payload.whitelist,
        )
        return JSONResponse(result)
    except Require2FAError as exc:
        return JSONResponse({"status": "2fa_required", "flow_token": exc.flow_token})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal memindai akun: {exc}") from exc


@app.post("/api/clean-batch")
async def api_clean_batch(payload: CleanBatchRequest):
    """Membersihkan satu batch item pilihan agar aman di lingkungan serverless."""
    if not payload.target_ids:
        raise HTTPException(status_code=400, detail="Tidak ada item yang dikirim.")

    try:
        result = await clean_batch(
            flow_token=payload.flow_token,
            target_ids=payload.target_ids,
            is_last_batch=payload.is_last_batch,
            auto_logout=payload.auto_logout,
        )
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal membersihkan batch: {exc}") from exc


@app.post("/api/qr-start")
async def api_qr_start(payload: QrStartRequest):
    """Membuat token QR Code login Telegram tanpa OTP/SMS."""
    try:
        return JSONResponse(
            await qr_start(
                custom_api_id=payload.custom_api_id,
                custom_api_hash=payload.custom_api_hash,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kesalahan server QR: {exc}") from exc


@app.post("/api/qr-check")
async def api_qr_check(payload: QrCheckRequest):
    """Mengecek apakah QR sudah di-scan pengguna; jika sukses langsung pindai akun."""
    try:
        return JSONResponse(
            await qr_check(flow_token=payload.flow_token, whitelist_raw=payload.whitelist)
        )
    except Require2FAError as exc:
        return JSONResponse({"status": "2fa_required", "flow_token": exc.flow_token})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal cek QR: {exc}") from exc


@app.post("/api/logout")
async def api_logout(payload: LogoutRequest):
    """Membatalkan proses dan me-logout sesi secara permanen dari Telegram."""
    logged_out = await logout_flow(payload.flow_token)
    return {"status": "logged_out", "logged_out": logged_out}
