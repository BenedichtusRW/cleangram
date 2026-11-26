"""
CleanGram Desktop Application (Modern WebView2 Standalone GUI).
Menggunakan Microsoft Edge WebView2 bawaan Windows via pywebview dengan desain
Obsidian Dark yang seirama dengan versi Web & Android, serta mesin Hybrid
(Mode Cepat Tanpa API sebagai default + Mode Lanjutan 100% Lokal Direct).
"""

import json
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Optional

import webview

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine import (  # noqa: E402
    DesktopHybridEngine,
    clear_saved_config,
    load_saved_config,
    save_saved_config,
)


def resource_path(rel_path: str) -> Path:
    """Mendukung resolusi asset baik saat run script maupun setelah dibundle PyInstaller."""
    root = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    return root / rel_path


class DesktopApiBridge:
    """Menjembatani panggilan JavaScript UI ke mesin Python DesktopHybridEngine."""

    def __init__(self, engine: Optional[DesktopHybridEngine] = None) -> None:
        self.engine = engine or DesktopHybridEngine()
        self._window: Any = None

    def attach_window(self, window: Any) -> None:
        self._window = window

    def _ok(self, data: Any = None) -> dict[str, Any]:
        return {"ok": True, "data": data}

    def _err(self, exc: Exception) -> dict[str, Any]:
        return {"ok": False, "error": str(exc)}

    def _push_event(self, payload: dict[str, Any]) -> None:
        if not self._window:
            return
        try:
            serialized = json.dumps(payload)
            self._window.evaluate_js(f"window.__onCleanEvent({serialized})")
        except Exception:
            pass

    def get_init_config(self) -> dict[str, Any]:
        try:
            return self._ok(load_saved_config())
        except Exception as exc:
            return self._err(exc)

    def save_advanced_config(
        self, use_local: bool, api_id: str, api_hash: str, persist: bool
    ) -> dict[str, Any]:
        try:
            if persist:
                save_saved_config(api_id, api_hash, use_local)
            else:
                clear_saved_config()
            return self._ok(
                {"use_local_mode": bool(use_local), "api_id": api_id.strip(), "api_hash": api_hash.strip()}
            )
        except Exception as exc:
            return self._err(exc)

    def reset_advanced_config(self) -> dict[str, Any]:
        try:
            clear_saved_config()
            return self._ok(True)
        except Exception as exc:
            return self._err(exc)

    def start_qr(self, use_local: bool = False, api_id: str = "", api_hash: str = "") -> dict[str, Any]:
        try:
            return self._ok(self.engine.start_qr(use_local=bool(use_local), api_id=api_id, api_hash=api_hash))
        except Exception as exc:
            return self._err(exc)

    def poll_qr(self, whitelist: str = "") -> dict[str, Any]:
        try:
            return self._ok(self.engine.poll_qr(whitelist_raw=whitelist))
        except Exception as exc:
            return self._err(exc)

    def send_otp(
        self, phone: str, use_local: bool = False, api_id: str = "", api_hash: str = ""
    ) -> dict[str, Any]:
        try:
            return self._ok(
                self.engine.send_otp(phone=phone, use_local=bool(use_local), api_id=api_id, api_hash=api_hash)
            )
        except Exception as exc:
            return self._err(exc)

    def verify_scan(
        self, code: str = "", password: str = "", whitelist: str = ""
    ) -> dict[str, Any]:
        try:
            return self._ok(self.engine.verify_scan(code=code, password=password, whitelist_raw=whitelist))
        except Exception as exc:
            return self._err(exc)

    def start_cleaning(self, selected_ids: list[int], auto_logout: bool = True) -> dict[str, Any]:
        try:
            ids = [int(x) for x in (selected_ids or [])]
            if not ids:
                raise ValueError("Pilih minimal 1 target untuk dibersihkan.")

            def worker() -> None:
                try:
                    summary = self.engine.run_cleaning(ids, bool(auto_logout), self._push_event)
                    self._push_event({"event": "done", **summary})
                except Exception as exc:
                    self._push_event({"event": "error", "message": str(exc)})

            threading.Thread(target=worker, daemon=True).start()
            return self._ok(True)
        except Exception as exc:
            return self._err(exc)

    def cancel_cleaning(self) -> dict[str, Any]:
        try:
            self.engine.request_cancel()
            return self._ok(True)
        except Exception as exc:
            return self._err(exc)

    def logout(self) -> dict[str, Any]:
        try:
            return self._ok(self.engine.logout())
        except Exception as exc:
            return self._err(exc)

    def open_url(self, url: str) -> dict[str, Any]:
        try:
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                webbrowser.open(url)
            return self._ok(True)
        except Exception as exc:
            return self._err(exc)


def main() -> None:
    ui_index = resource_path("ui/index.html")
    ico_path = resource_path("assets/icon.ico")
    bridge = DesktopApiBridge()

    window = webview.create_window(
        title="CleanGram Desktop — Pembersih Massal Telegram",
        url=str(ui_index),
        js_api=bridge,
        width=820,
        height=760,
        min_size=(620, 560),
        background_color="#09090B",
        text_select=True,
    )
    bridge.attach_window(window)

    def on_closing() -> None:
        bridge.engine.shutdown()

    window.events.closing += on_closing

    webview.start(
        http_server=True,
        private_mode=True,
        icon=str(ico_path) if ico_path.exists() else None,
    )


if __name__ == "__main__":
    main()
