"""
CleanGram Web Application (FastAPI Backend).
Menyediakan halaman web responsif (Desktop & Mobile PWA) dan REST/SSE API
untuk membersihkan grup & spam Telegram secara aman tanpa menyimpan sesi.
"""

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from cleaner_service import _Require2FAError, session_manager  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Membersihkan seluruh sesi aktif saat server shutdown."""
    yield
    for fid in list(session_manager._flows.keys()):
        await session_manager.destroy_flow(fid, logout=True)


app = FastAPI(
    title="CleanGram Web",
    description="Pembersih Massal Grup & Spam Telegram dengan Proteksi Whitelist",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=25)
    custom_api_id: Optional[int] = None
    custom_api_hash: Optional[str] = None


class VerifyScanRequest(BaseModel):
    flow_id: str
    code: Optional[str] = None
    password: Optional[str] = None
    whitelist: str = ""


class CleanRequest(BaseModel):
    flow_id: str
    selected_ids: list[int]
    auto_logout: bool = True


class LogoutRequest(BaseModel):
    flow_id: str


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
    """Endpoint kesehatan untuk uptime monitor Render.com (GET & HEAD)."""
    return {"status": "ok", "service": "cleangram-web"}


@app.post("/api/send-code")
async def api_send_code(payload: SendCodeRequest):
    """Mengirim kode OTP login resmi ke Telegram pengguna."""
    try:
        result = await session_manager.start_login(
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
        result = await session_manager.verify_and_scan(
            flow_id=payload.flow_id,
            code=payload.code,
            password=payload.password,
            whitelist_raw=payload.whitelist,
        )
        return JSONResponse(result)
    except _Require2FAError:
        return JSONResponse({"status": "2fa_required", "flow_id": payload.flow_id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal memindai akun: {exc}") from exc


@app.post("/api/clean")
async def api_clean(payload: CleanRequest):
    """Menjalankan pembersihan dan streaming progres secara real-time via SSE."""
    if not payload.selected_ids:
        raise HTTPException(status_code=400, detail="Pilih minimal 1 item untuk dibersihkan.")

    try:
        # Validasi awal flow_id sebelum memulai stream
        session_manager._get_flow(payload.flow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream():
        try:
            async for chunk in session_manager.stream_clean(
                flow_id=payload.flow_id,
                selected_ids=payload.selected_ids,
                auto_logout=payload.auto_logout,
            ):
                yield chunk
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/logout")
async def api_logout(payload: LogoutRequest):
    """Membatalkan proses dan langsung me-logout sesi dari server & Telegram."""
    destroyed = await session_manager.destroy_flow(payload.flow_id, logout=True)
    return {"status": "logged_out", "destroyed": destroyed}
