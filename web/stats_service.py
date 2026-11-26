"""
CleanGram Anonymous Live Statistics Service (Upstash Redis REST / Vercel KV).
Menyimpan statistik agregat tanpa menyentuh data pribadi (tanpa nama, nomor HP, atau chat).
Jika environment variables Redis belum dikonfigurasi, seluruh fungsi berjalan aman sebagai no-op.
"""

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional


def _redis_credentials() -> tuple[str, str]:
    """Mengambil kredensial Upstash Redis atau Vercel KV REST API dari env."""
    url = (
        os.getenv("UPSTASH_REDIS_REST_URL")
        or os.getenv("KV_REST_API_URL")
        or ""
    ).strip().rstrip("/")
    token = (
        os.getenv("UPSTASH_REDIS_REST_TOKEN")
        or os.getenv("KV_REST_API_TOKEN")
        or ""
    ).strip()
    return url, token


def is_stats_configured() -> bool:
    """Memeriksa apakah Upstash Redis / Vercel KV telah terhubung."""
    url, token = _redis_credentials()
    return bool(url and token)


def _execute_pipeline_sync(commands: list[list[Any]]) -> Optional[list[Any]]:
    """Menjalankan batch perintah Redis melalui Upstash REST API."""
    url, token = _redis_credentials()
    if not url or not token:
        return None

    req = urllib.request.Request(
        f"{url}/pipeline",
        data=json.dumps(commands).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CleanGramStats/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [item.get("result") if isinstance(item, dict) else None for item in parsed]
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return None


def _safe_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _format_stats_response(results: Optional[list[Any]]) -> dict[str, Any]:
    if not is_stats_configured() or results is None or len(results) < 5:
        return {
            "configured": is_stats_configured(),
            "visits": 0,
            "sessions": 0,
            "cleaned_items": 0,
            "completed_runs": 0,
            "last_activity": None,
        }

    last_raw = results[4]
    last_activity: Optional[dict[str, int]] = None
    if isinstance(last_raw, str) and last_raw.strip():
        try:
            decoded = json.loads(last_raw)
            if isinstance(decoded, dict) and _safe_int(decoded.get("count")) > 0:
                last_activity = {
                    "count": _safe_int(decoded.get("count")),
                    "ts": _safe_int(decoded.get("ts")),
                }
        except ValueError:
            last_activity = None

    return {
        "configured": True,
        "visits": _safe_int(results[0]),
        "sessions": _safe_int(results[1]),
        "cleaned_items": _safe_int(results[2]),
        "completed_runs": _safe_int(results[3]),
        "last_activity": last_activity,
    }


async def get_stats() -> dict[str, Any]:
    """Mengambil ringkasan statistik penggunaan anonim CleanGram."""
    if not is_stats_configured():
        return _format_stats_response(None)
    results = await asyncio.to_thread(
        _execute_pipeline_sync,
        [
            ["GET", "cleangram:visits"],
            ["GET", "cleangram:sessions"],
            ["GET", "cleangram:cleaned_items"],
            ["GET", "cleangram:completed_runs"],
            ["GET", "cleangram:last_activity"],
        ],
    )
    return _format_stats_response(results)


async def record_visit() -> dict[str, Any]:
    """Menambah penghitung kunjungan dan mengembalikan statistik terbaru."""
    if not is_stats_configured():
        return _format_stats_response(None)
    results = await asyncio.to_thread(
        _execute_pipeline_sync,
        [
            ["INCR", "cleangram:visits"],
            ["GET", "cleangram:sessions"],
            ["GET", "cleangram:cleaned_items"],
            ["GET", "cleangram:completed_runs"],
            ["GET", "cleangram:last_activity"],
        ],
    )
    return _format_stats_response(results)


async def record_scan_session() -> None:
    """Mencatat satu sesi login & pemindaian akun yang berhasil."""
    if not is_stats_configured():
        return
    await asyncio.to_thread(
        _execute_pipeline_sync,
        [["INCR", "cleangram:sessions"]],
    )


async def record_cleanup(ok_count: int, completed: bool = False) -> None:
    """Mencatat jumlah item yang berhasil dibersihkan secara anonim."""
    if not is_stats_configured() or (ok_count <= 0 and not completed):
        return
    commands: list[list[Any]] = []
    if ok_count > 0:
        commands.append(["INCRBY", "cleangram:cleaned_items", int(ok_count)])
        commands.append(
            [
                "SET",
                "cleangram:last_activity",
                json.dumps({"count": int(ok_count), "ts": int(time.time())}),
            ]
        )
    if completed:
        commands.append(["INCR", "cleangram:completed_runs"])
    await asyncio.to_thread(_execute_pipeline_sync, commands)
