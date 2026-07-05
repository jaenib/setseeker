import io
import tempfile
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

fake_sclib = types.ModuleType("sclib")
fake_sclib.Playlist = type("Playlist", (), {})
fake_sclib.SoundcloudAPI = type("SoundcloudAPI", (), {})
fake_sclib.Track = type("Track", (), {})
sys.modules.setdefault("sclib", fake_sclib)

import ingest
import scdl
import seekspawner


class SoundCloudIngestTests(unittest.TestCase):
    def test_generated_station_url_is_rejected_before_download(self):
        with self.assertRaisesRegex(ValueError, "generated station"):
            scdl.normalize_soundcloud_url(
                "https://soundcloud.com/discover/sets/track-stations:2350338077"
            )

    def test_failed_soundcloud_ingest_cleans_created_mp3s(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sets_dir = Path(tmpdir) / "sets"
            sets_dir.mkdir()
            existing = sets_dir / "existing.mp3"
            existing.write_bytes(b"keep")

            def fake_scdl_main(source):
                del source
                (sets_dir / "partial.mp3").write_bytes(b"delete")
                raise RuntimeError("download failed")

            with mock.patch.object(ingest, "SETS_DIR", sets_dir):
                with mock.patch.object(ingest.scdl, "main", side_effect=fake_scdl_main):
                    with self.assertRaisesRegex(RuntimeError, "download failed"):
                        with redirect_stdout(io.StringIO()):
                            ingest.ingest_soundcloud("https://soundcloud.com/example/set")

            self.assertTrue(existing.exists())
            self.assertFalse((sets_dir / "partial.mp3").exists())


class TracklistParsingTests(unittest.TestCase):
    def test_ranged_timestamp_prefix_is_removed_from_download_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracklist_dir = Path(tmpdir)
            tracklist = tracklist_dir / "set_tracklist.txt"
            tracklist.write_text(
                "[00:00:30-00:03:30] Moby - Porcelain\n",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                queries = seekspawner.build_track_queries(
                    str(tracklist_dir),
                    use_last_run_only=False,
                )

        self.assertEqual(len(queries), 2)
        self.assertEqual(queries[0].artist, "Moby")
        self.assertEqual(queries[0].title, "Porcelain")
        self.assertEqual(queries[0].format, "mp3")


if __name__ == "__main__":
    unittest.main()
