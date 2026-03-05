import os
import re
import json
import urllib.error
import urllib.parse
import urllib.request

from sclib import Playlist, SoundcloudAPI, Track

soundcloud_url = ""


def normalize_soundcloud_url(url):
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("Empty SoundCloud URL")

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urllib.parse.urlsplit(cleaned)
    if not parsed.netloc:
        raise ValueError(f"Invalid SoundCloud URL: {url}")

    # Shared URLs often include tracking params (`si`, `utm_*`) that can break resolve.
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    keep = [(k, v) for k, v in query_pairs if k == "secret_token"]
    query = urllib.parse.urlencode(keep, doseq=True)

    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def sanitize_filename(name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe or "untitled"


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
    if kind in ("playlist", "system-playlist"):
        playlist = Playlist(obj=obj, client=client)
        playlist.clean_attributes()
        return playlist
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
    filename = f"sets/{sanitize_filename(track.artist)} - {sanitize_filename(track.title)}.mp3"
    with open(filename, "wb+") as file:
        track.write_mp3_to(file)
    print(f"Downloaded: {filename}")


def main(soundcloud_url):
    os.makedirs("sets", exist_ok=True)
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
