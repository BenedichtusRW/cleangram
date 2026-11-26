"""Unit tests untuk CleanGram Desktop Hybrid Engine & API Bridge."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

DESKTOP_DIR = Path(__file__).resolve().parent
if str(DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_DIR))

from app import DesktopApiBridge, resource_path  # noqa: E402
from engine import DesktopHybridEngine, make_qr_data_uri, normalize_phone  # noqa: E402


class TestDesktopHybrid(unittest.TestCase):
    def test_phone_normalization(self) -> None:
        self.assertEqual(normalize_phone("0812-3456-7890"), "+6281234567890")
        self.assertEqual(normalize_phone("6281234567890"), "+6281234567890")
        self.assertEqual(normalize_phone("+62 812 3456 7890"), "+6281234567890")

    def test_qr_data_uri_generation(self) -> None:
        uri = make_qr_data_uri("tg://login?token=demo123")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertGreater(len(uri), 100)

    def test_resources_exist(self) -> None:
        self.assertTrue(resource_path("ui/index.html").exists())
        self.assertTrue(resource_path("ui/logo.png").exists())
        self.assertTrue(resource_path("assets/icon.ico").exists())

    def test_default_cloud_qr_does_not_require_api_id(self) -> None:
        engine = DesktopHybridEngine(api_base="https://example.invalid")
        mock_resp = MagicMock(ok=True)
        mock_resp.json.return_value = {
            "flow_token": "tok_abc",
            "qr_url": "tg://login?token=cloud_test_token",
        }
        with patch.object(engine._http, "post", return_value=mock_resp) as post_mock:
            res = engine.start_qr(use_local=False, api_id="", api_hash="")
        self.assertEqual(res["mode"], "cloud")
        self.assertTrue(res["qr_data_uri"].startswith("data:image/png;base64,"))
        post_mock.assert_called_once()

    def test_local_mode_validates_api_credentials(self) -> None:
        bridge = DesktopApiBridge()
        res = bridge.start_qr(use_local=True, api_id="not_a_number", api_hash="short")
        self.assertFalse(res["ok"])
        self.assertIn("API ID harus berupa angka", res["error"])

    def test_cloud_clean_all_batches_and_progress(self) -> None:
        engine = DesktopHybridEngine(api_base="https://example.invalid")
        engine._flow_token = "tok_clean"
        ids = list(range(1, 21))

        batch1 = MagicMock(ok=True)
        batch1.json.return_value = {
            "results": [{"id": i, "name": f"Grup {i}", "type": "Grup", "status": "ok"} for i in range(1, 16)],
            "floodwait_seconds": 0,
        }
        batch2 = MagicMock(ok=True)
        batch2.json.return_value = {
            "results": [{"id": i, "name": f"Bot {i}", "type": "Bot", "status": "ok"} for i in range(16, 21)],
            "floodwait_seconds": 0,
        }

        events: list[dict] = []
        with patch.object(engine._http, "post", side_effect=[batch1, batch2]):
            summary = engine.run_cleaning(ids, auto_logout=True, emit=events.append)

        self.assertEqual(summary["sukses"], 20)
        self.assertEqual(summary["gagal"], 0)
        self.assertFalse(summary["cancelled"])
        self.assertEqual(len(events), 20)


if __name__ == "__main__":
    unittest.main()
