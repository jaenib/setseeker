import sys
import os
import subprocess
import asyncio
from pathlib import Path

try:
    from shazamio import Shazam
except ModuleNotFoundError:
    print("Missing Python package 'shazamio'.")
    print("Run './setup.sh' once, or './launcher.sh --doctor' to auto-fix the environment.")
    sys.exit(1)

# Segment length in seconds
segment_length = 60  # Default 30s go up if your set consists of longer tracks
recognition_retries = 4
recognition_retry_delay = 1.5
recognition_request_spacing = 0.35

# Directories
INPUT_DIR = "sets"  # MP3 files
SEGMENTS_DIR = "tmp/segments"
OUT_DIR = "tracklists"
RUN_TRACKLIST_MANIFEST = Path("tmp/queries/tracklists_last_run.txt")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
RUN_TRACKLIST_MANIFEST.parent.mkdir(parents=True, exist_ok=True)


def write_last_run_manifest(tracklist_paths):
    with open(RUN_TRACKLIST_MANIFEST, "w", encoding="utf-8") as f:
        for tracklist_path in tracklist_paths:
            f.write(str(tracklist_path) + "\n")

async def recognize_segment(shazam, file_path):
    # Support both recent and older shazamio APIs.
    if hasattr(shazam, "recognize"):
        return await shazam.recognize(file_path)
    if hasattr(shazam, "recognize_song"):
        return await shazam.recognize_song(file_path)
    raise AttributeError("Unsupported shazamio version: missing recognize methods")

def is_retryable_shazam_error(error):
    message = str(error)
    retryable_snippets = (
        "URL is invalid",
        "Cannot connect to host",
        "Server disconnected",
        "Timeout",
        "429",
    )
    return any(snippet in message for snippet in retryable_snippets)

async def recognize_segment_with_retry(file_path, max_attempts, base_delay, label=None):
    last_error = None
    endpoint_countries = ("US", "GB")
    for attempt in range(1, max_attempts + 1):
        endpoint_country = endpoint_countries[(attempt - 1) % len(endpoint_countries)]
        shazam = Shazam(language="en-US", endpoint_country=endpoint_country)
        try:
            return await recognize_segment(shazam, file_path)
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts or not is_retryable_shazam_error(exc):
                raise
            wait_seconds = base_delay * attempt
            if attempt == 1:
                prefix = f"[{label}] " if label else ""
                print(f"{prefix}Shazam fail; retrying...")
            await asyncio.sleep(wait_seconds)
    raise last_error


def format_timestamp(seconds):
    return f"{seconds // 3600:02}:{(seconds % 3600) // 60:02}:{seconds % 60:02}"


def same_detection(left, artist, title):
    return (
        left["artist"].casefold() == artist.casefold()
        and left["title"].casefold() == title.casefold()
    )


def append_detection(track_entries, timestamp_seconds, segment_length, artist, title):
    if (
        track_entries
        and track_entries[-1]["end_seconds"] == timestamp_seconds
        and same_detection(track_entries[-1], artist, title)
    ):
        track_entries[-1]["end_seconds"] = timestamp_seconds + segment_length
        track_entries[-1]["is_range"] = True
        return False

    track_entries.append(
        {
            "start_seconds": timestamp_seconds,
            "end_seconds": timestamp_seconds + segment_length,
            "artist": artist,
            "title": title,
            "is_range": False,
        }
    )
    return True


def format_track_entry(entry):
    start = format_timestamp(entry["start_seconds"])
    if entry["is_range"]:
        end = format_timestamp(entry["end_seconds"])
        timestamp = f"{start}-{end}"
    else:
        timestamp = start
    return f"[{timestamp}] {entry['artist']} - {entry['title']}"

def build_split_command(input_file, segment_pattern, segment_length, reencode):
    # Keep ffmpeg output clean and exclude attached picture streams from source MP3s.
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-y",
        "-i",
        input_file,
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-f",
        "segment",
        "-segment_time",
        str(segment_length),
        "-segment_format",
        "mp3",
    ]
    if reencode:
        command += ["-ar", "44100", "-ac", "2", "-b:a", "192k"]
    else:
        # Stream copy splits in seconds instead of re-encoding the whole set.
        # Worst case is a <100ms bit-reservoir glitch at each segment start,
        # which Shazam recognition tolerates.
        command += ["-c:a", "copy"]
    command.append(segment_pattern)
    return command


def remove_segments_for(base_name):
    for file in os.listdir(SEGMENTS_DIR):
        if file.startswith(f"{base_name}_") and file.endswith(".mp3"):
            os.remove(os.path.join(SEGMENTS_DIR, file))


def reencode_forced():
    return os.environ.get("SETSEEK_SEGMENT_REENCODE", "").strip().lower() in {"1", "true", "yes"}


# Split set audio into segments
def split_audio(input_file, segment_length):
    print(f"Splitting {input_file} into {segment_length}-second chunks...")
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    segment_pattern = os.path.join(SEGMENTS_DIR, f"{base_name}_%03d.mp3")

    if reencode_forced():
        subprocess.run(build_split_command(input_file, segment_pattern, segment_length, reencode=True), check=True)
        return

    try:
        subprocess.run(build_split_command(input_file, segment_pattern, segment_length, reencode=False), check=True)
    except subprocess.CalledProcessError:
        print("Stream-copy split failed; retrying with re-encoding...")
        remove_segments_for(base_name)
        subprocess.run(build_split_command(input_file, segment_pattern, segment_length, reencode=True), check=True)

# Recognize tracks with ShazamIO
async def recognize_tracks(segment_length):
    print("Recognizing tracks with Shazam...")
    track_entries = []

    for file in sorted(os.listdir(SEGMENTS_DIR)):
        if file.endswith(".mp3"):
            file_path = os.path.join(SEGMENTS_DIR, file)

            # Assuming _XXX.mp3 format
            segment_index = int(file.split("_")[-1].split(".")[0])
            timestamp_seconds = segment_index * segment_length
            timestamp = format_timestamp(timestamp_seconds)

            try:
                result = await recognize_segment_with_retry(
                    file_path=file_path,
                    max_attempts=recognition_retries,
                    base_delay=recognition_retry_delay,
                    label=timestamp,
                )
                if "track" in result:
                    title = result["track"]["title"]
                    artist = result["track"]["subtitle"]
                    is_new_entry = append_detection(
                        track_entries=track_entries,
                        timestamp_seconds=timestamp_seconds,
                        segment_length=segment_length,
                        artist=artist,
                        title=title,
                    )
                    if is_new_entry:
                        print(f"Recognized: [{timestamp}] {artist} - {title}")
                else:
                    print(f"[{timestamp}] No match.")
            except Exception as e:
                if is_retryable_shazam_error(e):
                    print(f"[{timestamp}] Shazam fail; skip.")
                else:
                    compact_error = str(e).splitlines()[0]
                    print(f"[{timestamp}] Shazam error: {type(e).__name__}: {compact_error}")
            finally:
                # Small pacing helps reduce transient API failures from bursty requests.
                await asyncio.sleep(recognition_request_spacing)

    return [format_track_entry(entry) for entry in track_entries]

# ID all sets in "sets"
async def main(segment_length):
    sets = [f for f in os.listdir(INPUT_DIR) if f.endswith(".mp3")]
    generated_tracklists = []

    if not sets:
        print("No MP3 files found in 'sets/' folder.")
        print("Use './launcher.sh <YouTube/SoundCloud URL or local file/folder path>' to ingest audio.")
        write_last_run_manifest([])
        return

    for set_file in sets:
        for file in os.listdir(SEGMENTS_DIR):
            if file.endswith(".mp3"):
                os.remove(os.path.join(SEGMENTS_DIR, file))

        input_path = os.path.join(INPUT_DIR, set_file)
        split_audio(input_path, segment_length)

        tracks = await recognize_tracks(segment_length)

        base_name = os.path.splitext(set_file)[0]
        output_dir = os.path.join(OUT_DIR, base_name)
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{base_name}_tracklist_{segment_length}s.txt")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("Final Tracklist:\n")
            for track in tracks:
                f.write(track + "\n")
        generated_tracklists.append(Path(output_file))

        # Move set to outdir
        os.rename(os.path.join(INPUT_DIR, set_file), os.path.join(output_dir, set_file))

    write_last_run_manifest(generated_tracklists)

    print("\nFinal Tracklist:")
    for track in tracks:
        print(track)
    print(f"\nfileshazzer completed. Generated {len(generated_tracklists)} tracklist file(s).")

# Run
if __name__ == "__main__":
    expected_venv = os.path.abspath(".venv")
    actual_venv = os.environ.get("VIRTUAL_ENV", "")
    if not actual_venv or not actual_venv.startswith(expected_venv):
        print("Warning: .venv is not active. If dependencies fail, run: source .venv/bin/activate")

    asyncio.run(main(segment_length))
