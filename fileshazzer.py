import sys
import os
import subprocess
import asyncio

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

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

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

async def recognize_segment_with_retry(file_path, max_attempts, base_delay):
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
                print(
                    f"Transient Shazam response issue for {os.path.basename(file_path)}; "
                    f"retrying up to {max_attempts} attempts..."
                )
            await asyncio.sleep(wait_seconds)
    raise last_error

# Split set audio into segments
def split_audio(input_file, segment_length):
    print(f"Splitting {input_file} into {segment_length}-second chunks...")
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    segment_pattern = os.path.join(SEGMENTS_DIR, f"{base_name}_%03d.mp3")

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
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "192k",
        segment_pattern,
    ]

    subprocess.run(command, check=True)

# Recognize tracks with ShazamIO
async def recognize_tracks(segment_length):
    print("Recognizing tracks with Shazam...")
    track_list = []

    for file in sorted(os.listdir(SEGMENTS_DIR)):
        if file.endswith(".mp3"):
            file_path = os.path.join(SEGMENTS_DIR, file)

            # Assuming _XXX.mp3 format
            segment_index = int(file.split("_")[-1].split(".")[0])
            timestamp_seconds = segment_index * segment_length
            timestamp = f"{timestamp_seconds // 3600:02}:{(timestamp_seconds % 3600) // 60:02}:{timestamp_seconds % 60:02}"

            try:
                result = await recognize_segment_with_retry(
                    file_path=file_path,
                    max_attempts=recognition_retries,
                    base_delay=recognition_retry_delay,
                )
                if "track" in result:
                    title = result["track"]["title"]
                    artist = result["track"]["subtitle"]
                    track_list.append(f"[{timestamp}] {artist} - {title}")
                    print(f"Recognized: [{timestamp}] {artist} - {title}")
                else:
                    print(f"[{timestamp}] No match found for {file}")
            except Exception as e:
                if is_retryable_shazam_error(e):
                    print(f"[{timestamp}] Shazam temporary response issue for {file}; skipped after retries.")
                else:
                    compact_error = str(e).splitlines()[0]
                    print(f"Error processing {file}: {type(e).__name__}: {compact_error}")
            finally:
                # Small pacing helps reduce transient API failures from bursty requests.
                await asyncio.sleep(recognition_request_spacing)

    return track_list

# ID all sets in "sets"
async def main(segment_length):
    sets = [f for f in os.listdir(INPUT_DIR) if f.endswith(".mp3")]

    if not sets:
        print("No MP3 files found in 'sets/' folder.")
        print("Use './launcher.sh <YouTube/SoundCloud URL or local file/folder path>' to ingest audio.")
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

        with open(output_file, "w") as f:
            f.write("Final Tracklist:\n")
            for track in tracks:
                f.write(track + "\n")

        # Move set to outdir
        os.rename(os.path.join(INPUT_DIR, set_file), os.path.join(output_dir, set_file))

    print("\nFinal Tracklist:")
    for track in tracks:
        print(track)

# Run
if __name__ == "__main__":
    expected_venv = os.path.abspath(".venv")
    actual_venv = os.environ.get("VIRTUAL_ENV", "")
    if not actual_venv or not actual_venv.startswith(expected_venv):
        print("Warning: .venv is not active. If dependencies fail, run: source .venv/bin/activate")

    asyncio.run(main(segment_length))
