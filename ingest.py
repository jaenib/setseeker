import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import scdl

try:
    import yt_dlp
except ModuleNotFoundError:
    yt_dlp = None


SETS_DIR = Path("sets")
LOCAL_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".aif",
    ".aiff",
    ".webm",
    ".mp4",
    ".mkv",
    ".mov",
}


def is_url(value):
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def classify_source(source):
    cleaned = source.strip()
    if is_url(cleaned):
        parsed = urlparse(cleaned)
        # Remove port from netloc to get domain
        domain = parsed.netloc.lower().split(":")[0] if parsed.netloc else ""

        # Use exact domain matching to prevent spoofing
        if domain == "soundcloud.com" or domain == "www.soundcloud.com":
            return "soundcloud"
        if domain in {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be"}:
            return "youtube"
        raise ValueError("Unsupported URL source. Use YouTube or SoundCloud links.")
    return "local"


def ensure_sets_dir():
    SETS_DIR.mkdir(parents=True, exist_ok=True)


def current_mp3_set():
    return {p.resolve() for p in SETS_DIR.glob("*.mp3")}


def new_mp3_files(before):
    after = current_mp3_set()
    return sorted(str(p) for p in after - before)


def ensure_unique_destination(path):
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def copy_or_convert_local_file(source_file):
    source_file = source_file.resolve()
    if source_file.suffix.lower() == ".mp3":
        destination = ensure_unique_destination(SETS_DIR / source_file.name)
        shutil.copy2(source_file, destination)
        return str(destination)

    destination = ensure_unique_destination(SETS_DIR / f"{source_file.stem}.mp3")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-y",
        "-i",
        str(source_file),
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "192k",
        str(destination),
    ]
    subprocess.run(command, check=True)
    return str(destination)


def iter_local_audio_files(path):
    if path.is_file():
        if path.suffix.lower() in LOCAL_AUDIO_EXTENSIONS:
            yield path
        return

    for file_path in path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in LOCAL_AUDIO_EXTENSIONS:
            yield file_path


def ingest_local(source):
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Local path not found: {source}")

    imported = []
    for file_path in iter_local_audio_files(source_path):
        imported.append(copy_or_convert_local_file(file_path))

    if not imported:
        raise RuntimeError(
            "No supported audio files found in local source. "
            "Supported formats include mp3, wav, flac, m4a, aac, ogg, opus."
        )

    return imported


def ingest_soundcloud(source):
    before = current_mp3_set()
    scdl.main(source)
    imported = new_mp3_files(before)
    if not imported:
        print("SoundCloud download completed but no new MP3 files were detected in sets/.")
    return imported


def ingest_youtube(source):
    if yt_dlp is None:
        raise RuntimeError(
            "Missing Python package 'yt-dlp'. Run './setup.sh' or './launcher.sh --doctor'."
        )

    before = current_mp3_set()
    output_template = str(SETS_DIR / "%(uploader|unknown)s - %(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": False,
        "quiet": False,
        "no_warnings": True,
        "ignoreerrors": False,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result_code = ydl.download([source])
        if result_code != 0:
            raise RuntimeError("yt-dlp failed to download source.")

    imported = new_mp3_files(before)
    if not imported:
        print("YouTube download completed but no new MP3 files were detected in sets/.")
    return imported


def ingest_source(source):
    ensure_sets_dir()
    source_type = classify_source(source)

    if source_type == "local":
        print(f"Importing local audio from: {source}")
        imported = ingest_local(source)
    elif source_type == "soundcloud":
        print(f"Downloading from SoundCloud: {source}")
        imported = ingest_soundcloud(source)
    elif source_type == "youtube":
        print(f"Downloading from YouTube: {source}")
        imported = ingest_youtube(source)
    else:
        raise RuntimeError(f"Unsupported source type: {source_type}")

    return source_type, imported


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Ingest audio into sets/ from a YouTube link, SoundCloud link, or local file/folder."
        )
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="YouTube URL, SoundCloud URL, or local file/folder path",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    source_type, imported = ingest_source(args.source)
    print(f"Source type: {source_type}")
    print(f"Imported files: {len(imported)}")
    for path in imported:
        print(f"- {path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Ingest failed: {exc}")
        sys.exit(1)
