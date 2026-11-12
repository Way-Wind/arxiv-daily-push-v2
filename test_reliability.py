import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import delivery
import main
import page_builder
from wechat_push import WeChatPusher


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def test_corrupt_state_stops(self):
        Path(main.STATE_FILE).write_text("broken")
        with self.assertRaises(ValueError):
            main._load_pushed_ids()

    def test_token_retry_exhaustion_raises(self):
        pusher = WeChatPusher("a", "b", "c", "d")
        response = Mock()
        response.json.return_value = {"errcode": 40001}
        with patch.object(pusher, "get_access_token", return_value="token"), \
                patch("wechat_push.requests.post", return_value=response):
            with self.assertRaises(RuntimeError):
                pusher.send_template({})

    def test_partial_delivery_is_saved_and_resumed(self):
        delivery.save_pending([{"data": {}}, {"data": {}}],
                              [{"id": "a"}, {"id": "b"}], "detailed")
        config = dict(app_id="a", app_secret="b", template_id="c", user_openid="d")
        with patch("wechat_push.WeChatPusher") as cls, patch("delivery.time.sleep"):
            cls.return_value.send_template.side_effect = [True, RuntimeError("failed")]
            with self.assertRaises(RuntimeError):
                delivery.send_pending(config)
            self.assertEqual(main._load_pushed_ids(), {"a"})
            cls.return_value.send_template.side_effect = [True]
            delivery.send_pending(config)
            self.assertEqual(cls.return_value.send_template.call_count, 3)
        self.assertEqual(main._load_pushed_ids(), {"a", "b"})
        self.assertFalse(delivery.PENDING_FILE.exists())

    def test_same_day_pages_preserve_original(self):
        first, _ = page_builder.write_daily_page([], {}, [], "2026-11-13")
        original = Path(first).read_bytes()
        second, index = page_builder.write_daily_page([], {}, [], "2026-11-13")
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), original)
        self.assertIn(Path(first).name, Path(index).read_text(encoding="utf-8"))
        self.assertIn(Path(second).name, Path(index).read_text(encoding="utf-8"))

    def test_failed_summary_not_queued(self):
        papers = [dict(id=i, primary="math.DG", categories=["math.DG"],
                       title="Title", summary="Abstract", url="https://arxiv.org/abs/" + i)
                  for i in ("a", "b")]
        config = {"arxiv": dict(categories=["math.DG"], hours_back=30, max_papers_per_run=200),
                  "deepseek": dict(api_key="fake", base_url="https://example.invalid", model="fake"),
                  "wechat": dict(app_id="a", app_secret="b", template_id="c", user_openid="d",
                                 mode="digest", template_fields=main.DEFAULT_TEMPLATE_FIELDS)}
        with patch("sys.argv", ["main.py", "--prepare-only"]), \
                patch.object(main, "load_config", return_value=config), \
                patch.object(main, "fetch_new_papers", return_value=papers), \
                patch.object(main, "summarize_papers", return_value={"a": {"summary": "ok"}}), \
                patch.dict(os.environ, {"PAGE_BASE_URL": "https://example.invalid"}):
            main.main()
        entries = json.loads(delivery.PENDING_FILE.read_text(encoding="utf-8"))
        self.assertEqual(entries[0]["ids"], ["a"])
        self.assertFalse(Path(main.STATE_FILE).exists())


if __name__ == "__main__":
    unittest.main()
