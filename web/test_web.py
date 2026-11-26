"""Unit tests untuk CleanGram Web endpoints, Analytics tags, dan Stats Service."""

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

WEB_DIR = Path(__file__).resolve().parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import main  # noqa: E402
import stats_service  # noqa: E402


class TestWebAnalyticsAndStats(unittest.TestCase):
    def test_index_contains_vercel_analytics_and_stats_containers(self) -> None:
        html = main.templates.get_template("index.html").render()
        self.assertIn("/_vercel/insights/script.js", html)
        self.assertIn("window.va", html)
        self.assertIn('id="liveStatsCard"', html)
        self.assertIn('id="activityToast"', html)
        self.assertIn('property="og:image"', html)

    def test_stats_unconfigured_graceful_fallback(self) -> None:
        env = {
            "UPSTASH_REDIS_REST_URL": "",
            "UPSTASH_REDIS_REST_TOKEN": "",
            "KV_REST_API_URL": "",
            "KV_REST_API_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertFalse(stats_service.is_stats_configured())
            data = asyncio.run(stats_service.get_stats())
            self.assertEqual(
                data,
                {
                    "configured": False,
                    "visits": 0,
                    "sessions": 0,
                    "cleaned_items": 0,
                    "completed_runs": 0,
                    "last_activity": None,
                },
            )

    def test_stats_configured_endpoints_and_cleanup_recording(self) -> None:
        sample_last = json.dumps({"count": 27, "ts": 1795710000})
        env = {
            "UPSTASH_REDIS_REST_URL": "https://demo-redis.upstash.io",
            "UPSTASH_REDIS_REST_TOKEN": "demo_token",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(
                stats_service,
                "_execute_pipeline_sync",
                return_value=[42, 15, 680, 14, sample_last],
            ):
                r_get = asyncio.run(main.api_stats())
                body = json.loads(bytes(r_get.body).decode("utf-8"))
                self.assertEqual(r_get.status_code, 200)
                self.assertTrue(body["configured"])
                self.assertEqual(body["visits"], 42)
                self.assertEqual(body["sessions"], 15)
                self.assertEqual(body["cleaned_items"], 680)
                self.assertEqual(body["completed_runs"], 14)
                self.assertEqual(body["last_activity"]["count"], 27)

                r_post = asyncio.run(main.api_stats_visit())
                post_body = json.loads(bytes(r_post.body).decode("utf-8"))
                self.assertEqual(r_post.status_code, 200)
                self.assertEqual(post_body["visits"], 42)

            mock_batch = {
                "results": [
                    {"id": 1, "name": "Spam 1", "type": "Grup", "status": "ok"},
                    {"id": 2, "name": "Bot 2", "type": "Bot", "status": "error"},
                ],
                "floodwait_seconds": 0,
            }
            with patch.object(main, "clean_batch", AsyncMock(return_value=mock_batch)):
                with patch.object(main, "record_cleanup", AsyncMock()) as rec_mock:
                    payload = main.CleanBatchRequest(
                        flow_token="tok",
                        target_ids=[1, 2],
                        is_last_batch=True,
                        auto_logout=True,
                    )
                    r_clean = asyncio.run(main.api_clean_batch(payload))
                    self.assertEqual(r_clean.status_code, 200)
                    rec_mock.assert_awaited_once_with(ok_count=1, completed=True)


if __name__ == "__main__":
    unittest.main()
