import io
import subprocess
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

import fileshazzer
import ingest
import scdl
import seekspawner


class SoundCloudIngestTests(unittest.TestCase):
    def test_generated_station_url_is_rejected_before_download(self):
        with self.assertRaisesRegex(ValueError, "generated station"):
            scdl.normalize_soundcloud_url(
                "https://soundcloud.com/discover/sets/track-stations:2350338077"
            )

    def test_download_track_gives_sclib_a_readable_file_handle(self):
        # sclib's write_mp3_to seeks back and re-reads the stream to embed
        # ID3 metadata, so download_track must not open the file write-only.
        class FakeTrack:
            artist = "Mementomor"
            title = "Radio Ozora"

            def write_mp3_to(self, file):
                file.write(b"mp3-bytes")
                file.seek(0)
                assert file.read() == b"mp3-bytes"

        with tempfile.TemporaryDirectory() as tmpdir:
            sets_dir = Path(tmpdir) / "sets"
            sets_dir.mkdir()
            with mock.patch.object(scdl, "SETS_DIR", sets_dir):
                with redirect_stdout(io.StringIO()):
                    scdl.download_track(FakeTrack())

            destination = sets_dir / "Mementomor - Radio Ozora.mp3"
            self.assertEqual(destination.read_bytes(), b"mp3-bytes")
            self.assertEqual(list(sets_dir.iterdir()), [destination])

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


class SegmentSplitTests(unittest.TestCase):
    def test_copy_command_streams_without_reencoding(self):
        command = fileshazzer.build_split_command("in.mp3", "out_%03d.mp3", 60, reencode=False)
        self.assertIn("copy", command)
        self.assertNotIn("192k", command)
        self.assertEqual(command[-1], "out_%03d.mp3")

    def test_reencode_command_normalizes_audio(self):
        command = fileshazzer.build_split_command("in.mp3", "out_%03d.mp3", 60, reencode=True)
        self.assertIn("192k", command)
        self.assertNotIn("copy", command)

    def test_split_audio_falls_back_to_reencode_when_copy_fails(self):
        calls = []

        def fake_run(command, check=False):
            calls.append(command)
            if "copy" in command:
                raise subprocess.CalledProcessError(1, command)

        with mock.patch.object(fileshazzer.subprocess, "run", side_effect=fake_run), mock.patch.object(
            fileshazzer, "remove_segments_for"
        ) as cleanup, mock.patch.dict("os.environ", {"SETSEEK_SEGMENT_REENCODE": ""}), redirect_stdout(io.StringIO()):
            fileshazzer.split_audio("sets/x.mp3", 60)

        self.assertEqual(len(calls), 2)
        self.assertIn("copy", calls[0])
        self.assertIn("192k", calls[1])
        cleanup.assert_called_once_with("x")

    def test_split_audio_honors_forced_reencode_env(self):
        calls = []

        def fake_run(command, check=False):
            calls.append(command)

        with mock.patch.object(fileshazzer.subprocess, "run", side_effect=fake_run), mock.patch.dict(
            "os.environ", {"SETSEEK_SEGMENT_REENCODE": "1"}
        ), redirect_stdout(io.StringIO()):
            fileshazzer.split_audio("sets/x.mp3", 60)

        self.assertEqual(len(calls), 1)
        self.assertIn("192k", calls[0])
        self.assertNotIn("copy", calls[0])


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
