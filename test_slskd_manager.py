import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import reciprocity
import slskd_manager
from cryptography.fernet import Fernet


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
            jwt_key="jwt-key-456",
        )

        self.assertIn('downloads: "/tmp/downloads"', yaml_text)
        self.assertIn('username: "alice"', yaml_text)
        self.assertIn('password: "secret"', yaml_text)
        self.assertIn('api_key: "api-key-123"', yaml_text)
        self.assertIn('key: "api-key-123"', yaml_text)
        self.assertIn('key: "jwt-key-456"', yaml_text)
        self.assertIn("ttl: 604800000", yaml_text)
        self.assertIn('port: 5030', yaml_text)
        self.assertIn('listen_port: 50300', yaml_text)

    def test_configured_api_health_distinguishes_auth_failure_from_unreachable(self):
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "reciprocity_config.json"
            config_path.write_text('{"slskd":{"url":"http://127.0.0.1:5030","api_key":"bad-key"}}', encoding="utf-8")

            client = mock.Mock()
            client.get_application.side_effect = Exception("slskd authentication failed; check API key or web credentials")

            with mock.patch.object(slskd_manager, "RECIPROCITY_CONFIG_PATH", config_path), mock.patch.object(
                slskd_manager, "SlskdApiClient", return_value=client
            ), mock.patch.object(slskd_manager, "_probe_slskd_web_service", return_value=True):
                health = slskd_manager.configured_api_health()

        self.assertTrue(health.configured)
        self.assertFalse(health.authenticated)
        self.assertTrue(health.service_up)
        self.assertIn("authentication failed", health.detail)

    def test_configured_api_health_decrypts_stored_api_key(self):
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            key_path = tmp_path / "slskd.key"
            config_path = tmp_path / "reciprocity_config.json"
            key = Fernet.generate_key()
            fernet = Fernet(key)
            encrypted_api_key = fernet.encrypt(b"real-api-key").decode("utf-8")
            key_path.write_bytes(key)
            config_path.write_text(
                (
                    '{"slskd":{'
                    '"url":"http://127.0.0.1:5030",'
                    f'"api_key":"{encrypted_api_key}",'
                    '"api_key_encrypted":true'
                    "}}"
                ),
                encoding="utf-8",
            )

            captured_configs = []

            def build_client(config):
                captured_configs.append(config)
                client = mock.Mock()
                client.get_application.return_value = {"version": "test"}
                return client

            with mock.patch.object(slskd_manager, "RECIPROCITY_CONFIG_PATH", config_path), mock.patch.object(
                reciprocity, "BOOTSTRAP_ENCRYPTION_KEY_PATH", key_path
            ), mock.patch.object(slskd_manager, "SlskdApiClient", side_effect=build_client):
                health = slskd_manager.configured_api_health()

        self.assertTrue(health.authenticated)
        self.assertEqual(captured_configs[0].api_key, "real-api-key")

    def test_refresh_local_slskd_config_credentials_rewrites_generated_config(self):
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app_dir = tmp_path / "slskd" / "app"
            app_dir.mkdir(parents=True)
            config_path = app_dir / "slskd.yml"
            bootstrap_path = tmp_path / "slskd" / "bootstrap.json"
            reciprocity_path = tmp_path / "reciprocity_config.json"
            bootstrap_key_path = tmp_path / "slskd.key"
            share_dir = tmp_path / "share"
            downloads_dir = tmp_path / "downloads"
            incomplete_dir = tmp_path / "incomplete"

            metadata = {
                "web_url": "http://127.0.0.1:5030",
                "web_port": 5030,
                "listen_port": 50300,
                "api_key": "api-key",
                "jwt_key": "jwt-key",
                "web_username": "setseeker",
                "web_password": "web-pass",
                "share_dir": str(share_dir),
                "downloads_dir": str(downloads_dir),
                "incomplete_dir": str(incomplete_dir),
                "soulseek_username": "old-user",
            }
            config_path.write_text("old config", encoding="utf-8")

            with mock.patch.object(slskd_manager, "LOCAL_SLSKD_CONFIG_PATH", config_path), mock.patch.object(
                slskd_manager, "LOCAL_SLSKD_BOOTSTRAP_PATH", bootstrap_path
            ), mock.patch.object(slskd_manager, "BOOTSTRAP_ENCRYPTION_KEY_PATH", bootstrap_key_path), mock.patch.object(
                slskd_manager, "RECIPROCITY_CONFIG_PATH", reciprocity_path
            ):
                slskd_manager.save_bootstrap_metadata(metadata)
                with mock.patch.object(
                    slskd_manager,
                    "resolve_credentials",
                    return_value=slskd_manager.SoulseekCredentials("new-user", "new-pass", "test"),
                ):
                    refreshed = slskd_manager.refresh_local_slskd_config_credentials(non_interactive=True)

            yaml_text = config_path.read_text(encoding="utf-8")
            self.assertIn('username: "new-user"', yaml_text)
            self.assertIn('password: "new-pass"', yaml_text)
            self.assertIn('api_key: "api-key"', yaml_text)
            self.assertEqual(refreshed["soulseek_username"], "new-user")
            self.assertTrue(reciprocity_path.is_file())


if __name__ == "__main__":
    unittest.main()
