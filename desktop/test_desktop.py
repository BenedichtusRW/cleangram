"""Unit tests untuk CleanGram Desktop Hybrid Engine & API Bridge."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from telethon import functions as tl_functions

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

    def test_resources_and_category_filter_ui_exist(self) -> None:
        ui_html = resource_path("ui/index.html")
        self.assertTrue(ui_html.exists())
        self.assertTrue(resource_path("ui/logo.png").exists())
        self.assertTrue(resource_path("ui/sociabuzz-qr.png").exists())
        self.assertTrue(resource_path("assets/icon.ico").exists())
        txt = ui_html.read_text(encoding="utf-8")
        self.assertIn('id="categoryFilterBar"', txt)
        self.assertIn('id="blockBotsCheck"', txt)
        self.assertIn("https://sociabuzz.com/benedichtus", txt)
        self.assertIn('id="supportQrBox"', txt)
        self.assertIn("Desktop v1.1", txt)

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

    def test_cloud_clean_all_batches_and_block_bots_flag(self) -> None:
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
        with patch.object(engine._http, "post", side_effect=[batch1, batch2]) as post_mock:
            summary = engine.run_cleaning(ids, auto_logout=True, emit=events.append, block_bots=True)

        self.assertEqual(summary["sukses"], 20)
        self.assertEqual(summary["gagal"], 0)
        self.assertFalse(summary["cancelled"])
        self.assertEqual(len(events), 20)
        self.assertTrue(post_mock.call_args_list[0].kwargs["json"]["block_bots"])

    def test_local_clean_single_dialog_blocks_only_bots(self) -> None:
        engine = DesktopHybridEngine(api_base="https://example.invalid")
        fake_client = AsyncMock()
        fake_client.return_value = None
        fake_client.delete_dialog = AsyncMock()
        engine._client = fake_client

        bot_dialog = MagicMock(is_user=True, is_channel=False, is_group=False, input_entity="bot_peer")
        blocked = asyncio.run(engine._local_clean_single_dialog(bot_dialog, tipe="Bot", block_bots=True))
        self.assertTrue(blocked)
        self.assertTrue(
            any(
                isinstance(call.args[0], tl_functions.contacts.BlockRequest)
                for call in fake_client.call_args_list
                if call.args
            )
        )

        fake_client.reset_mock()
        ch_dialog = MagicMock(is_user=False, is_channel=True, is_group=False, input_entity="ch_peer")
        blocked_ch = asyncio.run(engine._local_clean_single_dialog(ch_dialog, tipe="Saluran", block_bots=True))
        self.assertFalse(blocked_ch)
        self.assertFalse(
            any(
                isinstance(call.args[0], tl_functions.contacts.BlockRequest)
                for call in fake_client.call_args_list
                if call.args
            )
        )


if __name__ == "__main__":
    unittest.main()
