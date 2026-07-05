import os
import re
import json
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from sclib import Playlist, SoundcloudAPI, Track

soundcloud_url = ""
SETS_DIR = Path("sets")


def normalize_soundcloud_url(url):
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("Empty SoundCloud URL")

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urllib.parse.urlsplit(cleaned)
    if not parsed.netloc:
        raise ValueError(f"Invalid SoundCloud URL: {url}")

    path = parsed.path.strip("/").lower()
    if path.startswith("discover/sets/") or "track-stations:" in path:
        raise ValueError(
            "That SoundCloud link is a generated station, not a set. "
            "Paste a direct track, user playlist/set, or local file/folder path."
        )

    # Shared URLs often include tracking params (`si`, `utm_*`) that can break resolve.
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    keep = [(k, v) for k, v in query_pairs if k == "secret_token"]
    query = urllib.parse.urlencode(keep, doseq=True)

    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def sanitize_filename(name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe or "untitled"


def unique_output_path(path):
    if not path.exists():
        return path

    for index in range(1, 10000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not find a unique filename for {path}")


@contextmanager
def download_spinner(message):
    if not sys.stdout.isatty():
        print(f"{message}...")
        yield
        return

    stop_event = threading.Event()
    frames = "|/-\\"
    started_at = time.monotonic()

    def animate():
        index = 0
        while not stop_event.wait(0.12):
            elapsed = int(time.monotonic() - started_at)
            sys.stdout.write(f"\r{frames[index % len(frames)]} {message} ({elapsed}s)")
            sys.stdout.flush()
            index += 1

    thread = threading.Thread(target=animate, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join()
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def scrape_client_ids(seed_url):
    candidates = []

    try:
        html = fetch_text(seed_url)
    except Exception:
        return candidates

    script_urls = re.findall(r'<script[^>]+src="([^"]+)"', html)
    for script_url in script_urls[:40]:
        full_url = urllib.parse.urljoin(seed_url, script_url)
        try:
            js_text = fetch_text(full_url)
        except Exception:
            continue

        for client_id in re.findall(r'client_id[:=]"?([a-zA-Z0-9]{32})', js_text):
            if client_id not in candidates:
                candidates.append(client_id)

    return candidates


def resolve_with_client_id(url, client_id):
    params = urllib.parse.urlencode({"url": url, "client_id": client_id})
    endpoint = f"https://api-v2.soundcloud.com/resolve?{params}"

    try:
        payload = fetch_text(endpoint)
        obj = json.loads(payload)
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None

    client = SoundcloudAPI(client_id=client_id)
    kind = obj.get("kind")
    if kind == "track":
        return Track(obj=obj, client=client)
    if kind == "playlist":
        playlist = Playlist(obj=obj, client=client)
        playlist.clean_attributes()
        return playlist
    if kind == "system-playlist":
        raise ValueError(
            "That SoundCloud link is a generated station or chart, not a set. "
            "Paste a direct track, user playlist/set, or local file/folder path."
        )
    return None


def resolve_with_fallback(url):
    # Fallback: refresh credentials from multiple pages and retry resolve.
    seed_pages = [
        url,
        "https://soundcloud.com/discover",
        "https://soundcloud.com/charts/top",
    ]
    tested = set()
    for seed in seed_pages:
        for client_id in scrape_client_ids(seed):
            if client_id in tested:
                continue
            tested.add(client_id)
            resolved = resolve_with_client_id(url, client_id)
            if isinstance(resolved, (Track, Playlist)):
                return resolved

    return None


def download_track(track):
    filename = f"{sanitize_filename(track.artist)} - {sanitize_filename(track.title)}.mp3"
    destination = unique_output_path(SETS_DIR / filename)
    partial = destination.with_name(f".{destination.name}.part")
    if partial.exists():
        partial.unlink()

    try:
        with download_spinner(f"Downloading {destination.name}"):
            with open(partial, "wb") as file:
                track.write_mp3_to(file)
            partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    print(f"Downloaded: {destination}")


def main(soundcloud_url):
    os.makedirs(SETS_DIR, exist_ok=True)
    normalized_url = normalize_soundcloud_url(soundcloud_url)

    resolved = resolve_with_fallback(normalized_url)
    if not resolved:
        raise RuntimeError(
            "Could not resolve the SoundCloud URL. Try opening the link in a browser first, "
            "then rerun with the canonical track URL without tracking params."
        )

    if isinstance(resolved, Track):
        print(f"Attempting to download: {resolved.title}, Artist: {resolved.artist}")
        download_track(resolved)
        return

    if isinstance(resolved, Playlist):
        resolved.clean_attributes()
        print(f"Attempting to download playlist: {resolved.title} ({len(resolved)} tracks)")
        for index, track in enumerate(resolved, start=1):
            print(f"[{index}/{len(resolved)}] {track.artist} - {track.title}")
            download_track(track)
        return

    raise RuntimeError(f"Unsupported SoundCloud object type: {type(resolved)!r}")


if __name__ == "__main__":
    main(soundcloud_url)
