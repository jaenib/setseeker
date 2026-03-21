import tempfile
import unittest
from pathlib import Path
from unittest import mock

import download_backends
from reciprocity import ReciprocityConfig, SlskdConfig


class FakeSlskdApiClient:
    def __init__(self, config):
        self.config = config
        self.options = {}
        self.responses = []
        self.transfer = {}
        self.application = {"server": {"isLoggedIn": True}}
        self.create_search_errors = []

    def get_options(self):
        return self.options

    def get_application(self):
        return self.application

    def create_search(self, search_id, search_text, search_timeout, response_limit, file_limit):
        if self.create_search_errors:
            raise self.create_search_errors.pop(0)
        return {"id": str(search_id), "searchText": search_text}

    def get_search(self, search_id, include_responses=False):
        del search_id, include_responses
        return {"id": "search-1", "isComplete": True, "state": "Completed"}

    def get_search_responses(self, search_id):
        del search_id
        return self.responses

    def delete_search(self, search_id):
        del search_id
        return None

    def enqueue_download(self, username, files):
        del username, files
        return {"enqueued": [self.transfer]}

    def list_downloads(self, include_removed=False, username=None):
        del include_removed, username
        return [self.transfer]


class DownloadBackendTests(unittest.TestCase):
    def test_remote_to_local_relative_filename_uses_parent_dir_and_file(self):
        relative = download_backends.remote_to_local_relative_filename(r"Artist\Album\Track.mp3")
        self.assertEqual(relative, Path("Album") / "Track.mp3")

    def test_slskd_backend_downloads_and_mirrors_to_spoils(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            slskd_downloads = tmp_path / "slskd-downloads"
            slskd_downloads.mkdir()

            remote_filename = r"Artist\Album\Track.mp3"
            downloaded_file = slskd_downloads / "Album" / "Track.mp3"
            downloaded_file.parent.mkdir(parents=True, exist_ok=True)
            downloaded_file.write_bytes(b"test-audio")

            fake_client = FakeSlskdApiClient(None)
            fake_client.options = {"directories": {"downloads": str(slskd_downloads)}}
            fake_client.responses = [
                {
                    "username": "sharer",
                    "hasFreeUploadSlot": True,
                    "queueLength": 0,
                    "uploadSpeed": 1000000,
                    "files": [
                        {
                            "filename": remote_filename,
                            "extension": "mp3",
                            "size": downloaded_file.stat().st_size,
                            "bitRate": 320,
                            "isVariableBitRate": False,
                        }
                    ],
                }
            ]
            fake_client.transfer = {
                "id": "transfer-1",
                "filename": remote_filename,
                "size": downloaded_file.stat().st_size,
                "state": "Completed, Succeeded",
            }

            config = ReciprocityConfig(
                slskd=SlskdConfig(url="http://127.0.0.1:5030"),
            )

            with mock.patch.object(download_backends, "SlskdApiClient", return_value=fake_client):
                backend = download_backends.SlskdDownloadBackend(
                    config=config,
                    output_dir=tmp_path / "spoils",
                    echo=lambda message: None,
                    sleep=lambda seconds: None,
                )
                summary = backend.download_queries(
                    [
                        download_backends.TrackQuery(
                            artist="Artist",
                            title="Track",
                            format="mp3",
                            min_bitrate=320,
                        )
                    ]
                )
                mirrored_exists = (tmp_path / "spoils" / "Album" / "Track.mp3").is_file()

            self.assertEqual(summary.succeeded_count, 1)
            self.assertEqual(summary.mirrored_count, 1)
            self.assertTrue(mirrored_exists)

    def test_slskd_backend_reports_miss_when_no_candidate_matches(self):
        fake_client = FakeSlskdApiClient(None)
        fake_client.options = {"directories": {"downloads": "/tmp/does-not-matter"}}
        fake_client.responses = [
            {
                "username": "sharer",
                "hasFreeUploadSlot": True,
                "queueLength": 0,
                "uploadSpeed": 1000000,
                "files": [{"filename": r"Wrong\Song.flac", "extension": "flac", "size": 12}],
            }
        ]

        config = ReciprocityConfig(
            slskd=SlskdConfig(url="http://127.0.0.1:5030"),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(download_backends, "SlskdApiClient", return_value=fake_client):
                backend = download_backends.SlskdDownloadBackend(
                    config=config,
                    output_dir=Path(tmpdir) / "spoils",
                    echo=lambda message: None,
                    sleep=lambda seconds: None,
                )
                summary = backend.download_queries(
                    [download_backends.TrackQuery(artist="Artist", title="Track", format="mp3", min_bitrate=320)]
                )

        self.assertEqual(summary.missed_count, 1)
        self.assertEqual(summary.failed_count, 0)

    def test_slskd_backend_retries_when_backend_is_logging_in(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            slskd_downloads = tmp_path / "slskd-downloads"
            slskd_downloads.mkdir()

            remote_filename = r"Artist\Album\Track.mp3"
            downloaded_file = slskd_downloads / "Album" / "Track.mp3"
            downloaded_file.parent.mkdir(parents=True, exist_ok=True)
            downloaded_file.write_bytes(b"test-audio")

            fake_client = FakeSlskdApiClient(None)
            fake_client.options = {"directories": {"downloads": str(slskd_downloads)}}
            fake_client.application = {"server": {"isLoggedIn": False}}
            fake_client.create_search_errors = [
                download_backends.ReciprocityAuditError(
                    "slskd API returned HTTP 409 for /api/v0/searches: The server connection must be connected and logged in to perform a search (currently: Connected, LoggingIn)"
                )
            ]
            fake_client.responses = [
                {
                    "username": "sharer",
                    "hasFreeUploadSlot": True,
                    "queueLength": 0,
                    "uploadSpeed": 1000000,
                    "files": [
                        {
                            "filename": remote_filename,
                            "extension": "mp3",
                            "size": downloaded_file.stat().st_size,
                            "bitRate": 320,
                            "isVariableBitRate": False,
                        }
                    ],
                }
            ]
            fake_client.transfer = {
                "id": "transfer-1",
                "filename": remote_filename,
                "size": downloaded_file.stat().st_size,
                "state": "Completed, Succeeded",
            }

            config = ReciprocityConfig(
                slskd=SlskdConfig(url="http://127.0.0.1:5030"),
            )

            def fake_sleep(seconds):
                del seconds
                fake_client.application = {"server": {"isLoggedIn": True}}

            with mock.patch.object(download_backends, "SlskdApiClient", return_value=fake_client):
                backend = download_backends.SlskdDownloadBackend(
                    config=config,
                    output_dir=tmp_path / "spoils",
                    echo=lambda message: None,
                    sleep=fake_sleep,
                )
                summary = backend.download_queries(
                    [download_backends.TrackQuery(artist="Artist", title="Track", format="mp3", min_bitrate=320)]
                )

            self.assertEqual(summary.succeeded_count, 1)


if __name__ == "__main__":
    unittest.main()
