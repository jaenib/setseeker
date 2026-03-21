import tempfile
import unittest
from pathlib import Path
from unittest import mock

import reciprocity


class ReciprocityTests(unittest.TestCase):
    def test_missing_backend_blocks(self):
        status = reciprocity.evaluate_reciprocity_status(
            reciprocity.ReciprocityConfig(),
            expected_username="alice",
        )

        self.assertFalse(status.overall_ok)
        self.assertIn("No reciprocity backend is configured.", status.blocking_reasons)

    def test_account_mismatch_blocks(self):
        snapshot = reciprocity.SlskdSnapshot(
            base_url="http://slskd.example:5030",
            state={
                "server": {"isLoggedIn": True},
                "shares": {"ready": True, "scanning": False, "faulted": False, "cancelled": False, "directories": 12, "files": 300},
                "user": {"username": "bob"},
            },
            options={
                "soulseek": {"listenPort": 50300, "listenIpAddress": "0.0.0.0"},
                "global": {"upload": {"slots": 10}},
            },
            shares={"local": [{"id": "share-1"}]},
            uploads=[],
            downloads=[],
        )

        status = reciprocity.evaluate_slskd_snapshot(
            snapshot,
            reciprocity.ReciprocityConfig(backend="slskd", slskd=reciprocity.SlskdConfig(url="http://slskd.example:5030")),
            expected_username="alice",
        )

        self.assertFalse(status.overall_ok)
        self.assertTrue(any("does not match" in reason for reason in status.blocking_reasons))

    def test_healthy_remote_slskd_snapshot_allows(self):
        snapshot = reciprocity.SlskdSnapshot(
            base_url="http://slskd.example:5030",
            state={
                "server": {"isLoggedIn": True},
                "shares": {"ready": True, "scanning": False, "faulted": False, "cancelled": False, "directories": 42, "files": 9000},
                "user": {"username": "alice"},
            },
            options={
                "soulseek": {"listenPort": 50300, "listenIpAddress": "0.0.0.0"},
                "global": {"upload": {"slots": 20}},
            },
            shares={"local": [{"id": "share-1"}, {"id": "share-2"}]},
            uploads=[{"bytesTransferred": 2048}],
            downloads=[{"bytesTransferred": 4096}],
        )

        status = reciprocity.evaluate_slskd_snapshot(
            snapshot,
            reciprocity.ReciprocityConfig(backend="slskd", slskd=reciprocity.SlskdConfig(url="http://slskd.example:5030")),
            expected_username="alice",
        )

        self.assertTrue(status.overall_ok)
        self.assertIsNone(status.listening_port_ok)
        self.assertEqual(status.bytes_uploaded, 2048)
        self.assertEqual(status.bytes_downloaded, 4096)

    def test_load_config_from_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "reciprocity_config.json"
            config_path.write_text(
                (
                    '{'
                    '"backend":"slskd",'
                    '"slskd":{"url":"http://127.0.0.1:5030","api_key":"abc123","require_same_username":true}'
                    '}'
                ),
                encoding="utf-8",
            )

            with mock.patch.dict("os.environ", {}, clear=False):
                config = reciprocity.load_reciprocity_config(config_path)

        self.assertEqual(config.backend, "slskd")
        self.assertEqual(config.slskd.url, "http://127.0.0.1:5030")
        self.assertEqual(config.slskd.api_key, "abc123")
        self.assertTrue(config.slskd.require_same_username)


if __name__ == "__main__":
    unittest.main()
