import argparse
import glob
import json
import os
import re
import shutil
import sys
from getpass import getpass
from pathlib import Path

from download_backends import SlskdDownloadBackend, TrackQuery
from reciprocity import ReciprocityAuditError, ReciprocityConfig, config_error_status, evaluate_reciprocity_status, format_reciprocity_doctor, load_reciprocity_config

try:
    from cryptography.fernet import Fernet
except ModuleNotFoundError:
    print("Missing Python package 'cryptography'.")
    print("Run './setup.sh' once, or './launcher.sh --doctor' to auto-fix the environment.")
    sys.exit(1)


# ---------- SETTINGS -----------------------------
TRACKLIST_DIR = "tracklists"
SKIPPED_PATH = "logs/skipped_queries.log"
TRACKLIST_MANIFEST_PATH = Path("tmp/queries/tracklists_last_run.txt")

CREDENTIAL_DIR = Path("user")
LEGACY_CREDENTIAL_DIRS = [Path("../user")]
DOWNLOAD_DIR = Path("spoils")

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav", ".aac", ".alac"}

SLSK_USER = ""  # Fill in manually to skip loading
SLSK_PW = ""  # Fill in manually to skip loading
# --------------------------------------------------


def cred_paths(cred_dir):
    return cred_dir / "slsk_cred.json", cred_dir / "slsk.key"


def cred_pair_exists(cred_dir):
    cred_path, key_path = cred_paths(cred_dir)
    return cred_path.is_file() and key_path.is_file()


def load_cred(cred_dir):
    cred_path, key_path = cred_paths(cred_dir)
    with open(cred_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(key_path, "rb") as f:
        key = f.read()

    fernet = Fernet(key)
    username = data["username"]
    password = fernet.decrypt(data["password_encrypted"].encode()).decode()
    return username, password


def save_cred(username, password, cred_dir=CREDENTIAL_DIR):
    cred_dir.mkdir(parents=True, exist_ok=True)
    cred_path, key_path = cred_paths(cred_dir)
    key = Fernet.generate_key()
    encrypted_password = Fernet(key).encrypt(password.encode()).decode()

    with open(cred_path, "w", encoding="utf-8") as f:
        json.dump(
            {"username": username, "password_encrypted": encrypted_password},
            f,
            indent=4,
        )

    with open(key_path, "wb") as f:
        f.write(key)


def migrate_cred_pair(source_dir, target_dir=CREDENTIAL_DIR):
    target_dir.mkdir(parents=True, exist_ok=True)
    source_cred_path, source_key_path = cred_paths(source_dir)
    target_cred_path, target_key_path = cred_paths(target_dir)
    shutil.copy2(source_cred_path, target_cred_path)
    shutil.copy2(source_key_path, target_key_path)


def prompt_for_credentials():
    username = ""
    while not username:
        username = input("Soulseek username: ").strip()

    password = ""
    while not password:
        password = getpass("Soulseek password: ").strip()

    save_answer = input("Save encrypted credentials in user/ for next runs? (Y/n) ").strip().lower()
    if save_answer in ("", "y", "yes"):
        try:
            save_cred(username, password)
            print("Saved encrypted credentials to user/slsk_cred.json and user/slsk.key")
        except Exception as e:
            print(f"Could not save encrypted credentials: {e}")

    return username, password, "interactive prompt"


def resolve_credentials(allow_prompt=True):
    if SLSK_USER and SLSK_PW:
        return SLSK_USER, SLSK_PW, "script settings"

    env_user = os.environ.get("SLSK_USERNAME", "").strip()
    env_pw = os.environ.get("SLSK_PASSWORD", "").strip()
    if env_user and env_pw:
        return env_user, env_pw, "environment variables"

    candidate_dirs = [CREDENTIAL_DIR, *LEGACY_CREDENTIAL_DIRS]
    for candidate_dir in candidate_dirs:
        if not cred_pair_exists(candidate_dir):
            continue

        try:
            username, password = load_cred(candidate_dir)
            if candidate_dir != CREDENTIAL_DIR and not cred_pair_exists(CREDENTIAL_DIR):
                migrate_cred_pair(candidate_dir, CREDENTIAL_DIR)
                return username, password, f"{candidate_dir} (imported to user/)"
            return username, password, f"{candidate_dir}"
        except Exception as e:
            print(f"Couldn't decrypt credentials from {candidate_dir}: {e}")

    if not allow_prompt:
        return "", "", ""
    print("No usable saved Soulseek credentials found.")
    return prompt_for_credentials()


def count_files_and_size(folder, audio_only=False):
    if not folder.exists() or not folder.is_dir():
        return 0, 0

    count = 0
    size_bytes = 0

    for item in folder.rglob("*"):
        if not item.is_file():
            continue
        if audio_only and item.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        count += 1
        try:
            size_bytes += item.stat().st_size
        except OSError:
            pass

    return count, size_bytes


def format_megabytes(size_bytes):
    return f"{size_bytes / (1024.0 * 1024.0):.1f}"


def print_download_summary(spoils_before, spoils_after):
    before_tracks, before_bytes = spoils_before
    after_tracks, after_bytes = spoils_after

    downloaded_tracks = max(after_tracks - before_tracks, 0)
    downloaded_bytes = max(after_bytes - before_bytes, 0)
    print(f"Downloaded {downloaded_tracks} tracks ({format_megabytes(downloaded_bytes)} MB).")


def get_expected_username_for_reciprocity():
    username, _, _ = resolve_credentials(allow_prompt=False)
    return username or None


def print_reciprocity_pass(status):
    listen_state = "reachable locally" if status.listening_port_ok else "reachability unverified"
    print(
        "Reciprocity gate passed: "
        f"{status.shared_directory_roots} share roots, "
        f"{status.shared_folder_count} folders, "
        f"{status.shared_file_count} files, "
        f"listen port {status.listening_port or 'unknown'} {listen_state}."
    )


def load_reciprocity_status(expected_username):
    try:
        config = load_reciprocity_config()
        status = evaluate_reciprocity_status(config, expected_username=expected_username)
    except ReciprocityAuditError as exc:
        config = ReciprocityConfig()
        status = config_error_status(str(exc), expected_username=expected_username)
    return config, status


def run_reciprocity_doctor(expected_username):
    _, status = load_reciprocity_status(expected_username)
    print(format_reciprocity_doctor(status))
    return status


def is_queryfied(artist, title):
    return artist != "" and title != "" and "-" not in artist and '"' not in title


def list_tracklist_files(tracklist_dir, use_last_run_only=True):
    if use_last_run_only and TRACKLIST_MANIFEST_PATH.is_file():
        manifest_paths = []
        with open(TRACKLIST_MANIFEST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                candidate = line.strip()
                if not candidate:
                    continue
                candidate_path = Path(candidate)
                if candidate_path.is_file():
                    manifest_paths.append(str(candidate_path))
        if manifest_paths:
            print(
                f"Using {len(manifest_paths)} tracklist file(s) from latest fileshazzer run "
                f"({TRACKLIST_MANIFEST_PATH})."
            )
            return manifest_paths

    txt_files = glob.glob(os.path.join(tracklist_dir, "**", "*.txt"), recursive=True)
    print(f"Using all tracklists: found {len(txt_files)} .txt file(s) in '{tracklist_dir}'")
    return txt_files


def build_track_queries(tracklist_dir, use_last_run_only=True):
    seen = set()
    track_queries = []
    skipped = []

    txt_files = list_tracklist_files(tracklist_dir, use_last_run_only=use_last_run_only)

    for file_path in txt_files:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for lineno, line in enumerate(lines, 1):
            original = line.strip()
            cleaned = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*", "", original)

            if not cleaned or cleaned.lower().startswith("final tracklist"):
                skipped.append(f"[{file_path}:{lineno}] HEADER OR EMPTY -> {cleaned}")
                continue

            if "-" in cleaned:
                parts = cleaned.split("-", maxsplit=1)

                if len(parts) < 2:
                    skipped.append(f"[{file_path}:{lineno}] TOO FEW PARTS -> {cleaned}")
                    continue

                artist = parts[0].strip()
                title = parts[1].strip()
                title = re.sub(r"\s+(320|FLAC)$", "", title, flags=re.IGNORECASE)

                if not is_queryfied(artist, title):
                    skipped.append(f"[{file_path}:{lineno}] BAD FORMAT -> {cleaned}")
                    continue

                for format_type in ["mp3", "flac"]:
                    key = (artist.lower(), title.lower(), format_type)
                    if key not in seen:
                        seen.add(key)
                        track_queries.append(
                            TrackQuery(
                                artist=artist,
                                title=title,
                                format=format_type,
                                min_bitrate=320 if format_type == "mp3" else 0,
                                source_file=file_path,
                                source_line=lineno,
                                raw_line=original,
                            )
                        )

            else:
                skipped.append(f"[{file_path}:{lineno}] NO HYPHEN or EMPTY -> {cleaned}")

    if skipped:
        with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(skipped))
        print(f"Skipped {len(skipped)} problematic lines. See {SKIPPED_PATH} for details.")

    print(f"{len(track_queries)} filtered track queries ready.")
    if not use_last_run_only:
        print("Note: --all-tracklists includes historical sets; 'already exist' messages are expected.")
    else:
        print("Only latest-run tracklists were queried to reduce duplicate re-checks.")
    return track_queries


def print_backend_summary(summary):
    print(
        f"slskd backend summary: requested {summary.requested_count}, "
        f"downloaded {summary.succeeded_count}, missed {summary.missed_count}, failed {summary.failed_count}."
    )
    if summary.mirrored_count:
        print(f"Mirrored {summary.mirrored_count} completed file(s) into spoils/.")
    if summary.mirror_failures:
        print(
            f"{summary.mirror_failures} completed file(s) stayed only in the slskd downloads directory. "
            "Check slskd's configured downloads path if you expected them in spoils/."
        )


def sendseek(args, track_queries):
    print("Seeking souls...")

    if not track_queries:
        print("No valid track queries were produced from the current tracklists. Nothing to download.")
        return

    global SLSK_USER, SLSK_PW
    SLSK_USER, SLSK_PW, cred_source = resolve_credentials()
    print(f"Accessing Soulseek as {SLSK_USER} ({cred_source})")

    reciprocity_config, reciprocity_status = load_reciprocity_status(expected_username=SLSK_USER)
    print(format_reciprocity_doctor(reciprocity_status))
    if not reciprocity_status.overall_ok:
        if args.unsafe_disable_reciprocity_gate:
            print("UNSAFE MODE: reciprocity gate disabled by --unsafe-disable-reciprocity-gate")
        else:
            print("Download blocked by reciprocity gate.")
            raise SystemExit(2)
    else:
        print_reciprocity_pass(reciprocity_status)

    print("Download backend: slskd")
    backend = SlskdDownloadBackend(reciprocity_config, output_dir=DOWNLOAD_DIR)

    spoils_before = count_files_and_size(DOWNLOAD_DIR, audio_only=True)
    try:
        summary = backend.download_queries(track_queries)
        print("Seek concluded")
        print_backend_summary(summary)
    except Exception as e:
        print(f"Seek collapsed under {e}")
    finally:
        spoils_after = count_files_and_size(DOWNLOAD_DIR, audio_only=True)
        print_download_summary(spoils_before, spoils_after)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert tracklists into download queries and fetch them through slskd.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Print reciprocity audit results and exit.",
    )
    parser.add_argument(
        "--unsafe-disable-reciprocity-gate",
        action="store_true",
        help="Bypass the reciprocity gate for development/testing only.",
    )
    parser.add_argument(
        "--all-tracklists",
        action="store_true",
        help="Query every tracklist under tracklists/ (legacy behavior).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.doctor:
        run_reciprocity_doctor(expected_username=get_expected_username_for_reciprocity())
        sys.exit(0)

    expected_venv = os.path.abspath(".venv")
    actual_venv = os.environ.get("VIRTUAL_ENV", "")

    if not actual_venv or not actual_venv.startswith(expected_venv):
        print("Warning: .venv is not active. If dependencies fail, run: source .venv/bin/activate")

    print("Seeker spawned")

    track_queries = build_track_queries(
        TRACKLIST_DIR,
        use_last_run_only=not args.all_tracklists,
    )
    sendseek(args, track_queries)
