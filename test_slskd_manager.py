import unittest
from pathlib import Path
from unittest import mock

import slskd_manager


class SlskdManagerTests(unittest.TestCase):
    def test_detect_release_asset_name_for_macos_arm64(self):
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("platform.machine", return_value="arm64"):
            asset = slskd_manager.detect_release_asset_name("0.24.5")
        self.assertEqual(asset, "slskd-0.24.5-osx-arm64.zip")

    def test_detect_release_asset_name_for_linux_x64(self):
        with mock.patch("platform.system", return_value="Linux"), mock.patch("platform.machine", return_value="x86_64"), mock.patch(
            "platform.libc_ver", return_value=("glibc", "2.31")
        ):
            asset = slskd_manager.detect_release_asset_name("0.24.5")
        self.assertEqual(asset, "slskd-0.24.5-linux-x64.zip")

    def test_render_slskd_yaml_contains_expected_paths_and_auth(self):
        yaml_text = slskd_manager.render_slskd_yaml(
            soulseek_username="alice",
            soulseek_password="secret",
            share_dir=Path("/tmp/share"),
            downloads_dir=Path("/tmp/downloads"),
            incomplete_dir=Path("/tmp/incomplete"),
            web_port=5030,
            listen_port=50300,
            web_username="setseeker",
            web_password="web-pass",
            api_key="api-key-123",
        )

        self.assertIn('downloads: "/tmp/downloads"', yaml_text)
        self.assertIn('username: "alice"', yaml_text)
        self.assertIn('password: "secret"', yaml_text)
        self.assertIn('key: "api-key-123"', yaml_text)
        self.assertIn('port: 5030', yaml_text)
        self.assertIn('listen_port: 50300', yaml_text)


if __name__ == "__main__":
    unittest.main()
