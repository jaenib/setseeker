import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from getpass import getpass
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ModuleNotFoundError:
    print("Missing Python package 'cryptography'.")
    print("Run './setup.sh' once, or './launcher.sh --doctor' to auto-fix the environment.")
    sys.exit(1)


# ---------- SETTINGS -----------------------------
TRACKLIST_DIR = "tracklists"
QUERYFILE_PATH = "tmp/queries/queries.txt"
SKIPPED_PATH = "logs/skipped_queries.log"
TRACKLIST_MANIFEST_PATH = Path("tmp/queries/tracklists_last_run.txt")

SLSKDL_EXECUTABLE = "slsk-batchdl/slsk-batchdl/bin/Release/net6.0/sldl.dll"
CREDENTIAL_DIR = Path("user")
LEGACY_CREDENTIAL_DIRS = [Path("../user")]

COMMUNITY_STATE_PATH = CREDENTIAL_DIR / "community_state.json"
DEFAULT_SHARE_DIR = "spoils"

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav", ".aac", ".alac"}

SLSK_USER = ""  # Fill in manually to skip loading
SLSK_PW = ""  # Fill in manually to skip loading
# --------------------------------------------------


def default_community_state():
    return {
        "share_dir": DEFAULT_SHARE_DIR,  # Default behavior: downloaded files live in shared folder.
        "suppress_no_share_reminder": False,
        "stats": {
            "runs": 0,
            "downloaded_tracks_total": 0,
            "downloaded_bytes_total": 0,
            "shared_files_last": 0,
            "shared_bytes_last": 0,
            "shared_files_peak": 0,
            "shared_bytes_peak": 0,
        },
    }


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


def resolve_credentials():
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

    print("No usable saved Soulseek credentials found.")
    return prompt_for_credentials()


def load_community_state():
    state = default_community_state()

    if not COMMUNITY_STATE_PATH.is_file():
        return state

    try:
        with open(COMMUNITY_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            share_dir = data.get("share_dir", DEFAULT_SHARE_DIR)
            normalized = resolve_share_dir(share_dir)
            state["share_dir"] = "" if normalized is None else str(normalized)
            if not state["share_dir"] and "share_dir" not in data:
                state["share_dir"] = DEFAULT_SHARE_DIR

            state["suppress_no_share_reminder"] = bool(
                data.get("suppress_no_share_reminder", False)
            )

            stats = data.get("stats", {})
            if isinstance(stats, dict):
                default_stats = state["stats"]
                for key in default_stats.keys():
                    try:
                        default_stats[key] = int(stats.get(key, default_stats[key]))
                    except (TypeError, ValueError):
                        pass
    except Exception as e:
        print(f"Could not read {COMMUNITY_STATE_PATH}: {e}")

    return state


def save_community_state(state):
    CREDENTIAL_DIR.mkdir(parents=True, exist_ok=True)
    default_state = default_community_state()
    raw_share_dir = state.get("share_dir", default_state["share_dir"])
    normalized_share_dir = ""
    if raw_share_dir is not None:
        normalized_share_dir = str(raw_share_dir).strip()
        if normalized_share_dir.lower() in {"none", "off", "disable", "disabled"}:
            normalized_share_dir = ""

    payload = {
        "share_dir": normalized_share_dir,
        "suppress_no_share_reminder": bool(
            state.get(
                "suppress_no_share_reminder",
                default_state["suppress_no_share_reminder"],
            )
        ),
        "stats": {},
    }

    stats = state.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}

    for key, value in default_state["stats"].items():
        try:
            payload["stats"][key] = int(stats.get(key, value))
        except (TypeError, ValueError):
            payload["stats"][key] = value

    with open(COMMUNITY_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def resolve_share_dir(raw_path):
    if raw_path is None:
        return None

    path_str = str(raw_path).strip()
    if path_str.lower() in {"", "none", "off", "disable", "disabled"}:
        return None

    expanded = os.path.expandvars(os.path.expanduser(path_str))
    return Path(expanded)


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


def format_gigabytes(size_bytes):
    return f"{size_bytes / (1024.0 * 1024.0 * 1024.0):.2f}"


def maybe_print_no_share_reminder(state, share_dir, skip_share_check=False):
    if share_dir is not None:
        return
    if skip_share_check:
        print("Skipping sharing reminder for this run (--skip-share-check).")
        return
    if state.get("suppress_no_share_reminder", False):
        return

    print("\nCommunity reminder: sharing is cool and keeps Soulseek healthy.")
    print("No local share folder is configured for setseeker right now.")
    print("Set one with: --share-dir <path>")
    print("If you already share elsewhere (Nicotine+/slskd), silence this with: --disable-share-reminder")
    for seconds in range(10, 0, -1):
        print(f"Continuing in {seconds}s... (or rerun with --skip-share-check)")
        time.sleep(1)


def update_and_save_stats(state, downloaded_tracks, downloaded_bytes, shared_files, shared_bytes):
    stats = state.setdefault("stats", {})

    stats["runs"] = int(stats.get("runs", 0)) + 1
    stats["downloaded_tracks_total"] = int(stats.get("downloaded_tracks_total", 0)) + int(downloaded_tracks)
    stats["downloaded_bytes_total"] = int(stats.get("downloaded_bytes_total", 0)) + int(downloaded_bytes)

    stats["shared_files_last"] = int(shared_files)
    stats["shared_bytes_last"] = int(shared_bytes)
    stats["shared_files_peak"] = max(int(stats.get("shared_files_peak", 0)), int(shared_files))
    stats["shared_bytes_peak"] = max(int(stats.get("shared_bytes_peak", 0)), int(shared_bytes))

    save_community_state(state)


def print_stats_snapshot(state):
    stats = state.get("stats", {})
    runs = int(stats.get("runs", 0))
    d_tracks = int(stats.get("downloaded_tracks_total", 0))
    d_bytes = int(stats.get("downloaded_bytes_total", 0))
    s_files_last = int(stats.get("shared_files_last", 0))
    s_bytes_last = int(stats.get("shared_bytes_last", 0))
    s_files_peak = int(stats.get("shared_files_peak", 0))
    s_bytes_peak = int(stats.get("shared_bytes_peak", 0))

    print(
        f"Stats: {runs} runs, downloaded {d_tracks} tracks "
        f"({format_gigabytes(d_bytes)} GB total)."
    )
    print(
        f"Last configured share snapshot: {s_files_last} files "
        f"({format_gigabytes(s_bytes_last)} GB)."
    )
    print(
        f"Peak configured share snapshot: {s_files_peak} files "
        f"({format_gigabytes(s_bytes_peak)} GB)."
    )
    if d_bytes > 0:
        ratio = s_bytes_last / d_bytes
        print(f"Current share-vs-downloaded bytes ratio: {ratio:.2f}x.")


def print_session_summary(state, spoils_before, spoils_after, share_dir):
    before_tracks, before_bytes = spoils_before
    after_tracks, after_bytes = spoils_after

    downloaded_tracks = max(after_tracks - before_tracks, 0)
    downloaded_bytes = max(after_bytes - before_bytes, 0)
    shared_files, shared_bytes = (
        count_files_and_size(share_dir, audio_only=False) if share_dir is not None else (0, 0)
    )

    update_and_save_stats(state, downloaded_tracks, downloaded_bytes, shared_files, shared_bytes)
    stats = state.get("stats", {})
    downloaded_bytes_total = int(stats.get("downloaded_bytes_total", 0))

    if share_dir is not None:
        summary = (
            f"Downloaded {downloaded_tracks} tracks ({format_megabytes(downloaded_bytes)} MB). "
            f"Configured share folder has {shared_files} files ({format_gigabytes(shared_bytes)} GB)."
        )
    else:
        summary = (
            f"Downloaded {downloaded_tracks} tracks ({format_megabytes(downloaded_bytes)} MB). "
            "No local share folder configured."
        )

    if downloaded_bytes_total > 0:
        ratio = shared_bytes / downloaded_bytes_total
        summary += f" Share/download ratio (current-vs-total bytes): {ratio:.2f}x."

    print(summary)
    print_stats_snapshot(state)


def print_share_help():
    print(
        "Sharing & community (setseeker wrapper)\n"
        "- This flow lives in seekspawner.py, without modifying slsk-batchdl.\n"
        "- Default share folder is 'spoils' (the download folder).\n"
        "- Change it with --share-dir <path>, or disable local sharing with --no-share-dir.\n"
        "- If no share folder is configured, a reminder is shown at run start.\n"
        "- If you already share elsewhere, persistently silence that reminder with --disable-share-reminder.\n"
        "- Use --skip-share-check for a one-run bypass."
    )


def apply_community_arg_overrides(state, args):
    changed = False

    if args.share_dir is not None:
        normalized = resolve_share_dir(args.share_dir)
        state["share_dir"] = str(normalized) if normalized is not None else ""
        changed = True
    if args.no_share_dir:
        state["share_dir"] = ""
        changed = True
    if args.disable_share_reminder:
        state["suppress_no_share_reminder"] = True
        changed = True
    if args.enable_share_reminder:
        state["suppress_no_share_reminder"] = False
        changed = True

    return changed


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


def querify_tracklists(tracklist_dir, output_query_file=QUERYFILE_PATH, use_last_run_only=True):
    seen = set()
    queries = []
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

                        if format_type == "mp3":
                            query_line = f"\"artist={artist},title={title}\"  \"format=mp3\"  \"br >= 320\""
                            queries.append(query_line)

                        if format_type == "flac":
                            query_line = f"\"artist={artist},title={title}\"  \"format=flac\""
                            queries.append(query_line)

            else:
                skipped.append(f"[{file_path}:{lineno}] NO HYPHEN or EMPTY -> {cleaned}")

    with open(output_query_file, "w", encoding="utf-8") as f:
        f.write("\n".join(queries))

    if skipped:
        with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(skipped))
        print(f"Skipped {len(skipped)} problematic lines. See {SKIPPED_PATH} for details.")

    print(f"{len(queries)} filtered queries (list mode) ready at {output_query_file}")
    if not use_last_run_only:
        print("Note: --all-tracklists includes historical sets; 'already exist' messages are expected.")
    else:
        print("Only latest-run tracklists were queried to reduce duplicate re-checks.")


def sendseek(args, state):
    print("Seeking souls...")

    share_dir = resolve_share_dir(state.get("share_dir", DEFAULT_SHARE_DIR))
    if share_dir is not None:
        print(f"Community share folder: {share_dir}")

    maybe_print_no_share_reminder(state, share_dir, skip_share_check=args.skip_share_check)

    global SLSK_USER, SLSK_PW
    SLSK_USER, SLSK_PW, cred_source = resolve_credentials()
    print(f"Accessing Soulseek as {SLSK_USER} ({cred_source})")

    env = os.environ.copy()
    env["DOTNET_ROOT"] = "/usr/local/share/dotnet"
    env["PATH"] = f'{env["DOTNET_ROOT"]}:{env["PATH"]}'

    command = [
        "dotnet",
        SLSKDL_EXECUTABLE,
        QUERYFILE_PATH,
        "--user",
        SLSK_USER,
        "--pass",
        SLSK_PW,
        "--input-type=list",
        "--path",
        "spoils",
    ]

    spoils_before = count_files_and_size(Path("spoils"), audio_only=True)
    try:
        subprocess.run(command, env=env, check=True)
        print("Seek concluded")
    except subprocess.CalledProcessError as e:
        print(f"Seek collapsed under {e}")
    finally:
        spoils_after = count_files_and_size(Path("spoils"), audio_only=True)
        print_session_summary(state, spoils_before, spoils_after, share_dir)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert tracklists into sldl queries and download from Soulseek.",
    )
    parser.add_argument(
        "--share-dir",
        help="Set local share folder (default: spoils). Set to 'none' to disable local share folder.",
    )
    parser.add_argument(
        "--no-share-dir",
        action="store_true",
        help="Disable local share folder (opt out).",
    )
    parser.add_argument(
        "--skip-share-check",
        action="store_true",
        help="Skip sharing reminder for this run only.",
    )
    parser.add_argument(
        "--disable-share-reminder",
        action="store_true",
        help="Persistently silence reminder when no local share folder is configured.",
    )
    parser.add_argument(
        "--enable-share-reminder",
        action="store_true",
        help="Re-enable reminder when no local share folder is configured.",
    )
    parser.add_argument(
        "--show-share-stats",
        action="store_true",
        help="Print stored share/download stats and exit.",
    )
    parser.add_argument(
        "--help-share",
        action="store_true",
        help="Print community sharing help and exit.",
    )
    parser.add_argument(
        "--all-tracklists",
        action="store_true",
        help="Query every tracklist under tracklists/ (legacy behavior).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.help_share:
        print_share_help()
        sys.exit(0)

    community_state = load_community_state()
    if apply_community_arg_overrides(community_state, args):
        save_community_state(community_state)

    if args.show_share_stats:
        print_stats_snapshot(community_state)
        sys.exit(0)

    expected_venv = os.path.abspath(".venv")
    actual_venv = os.environ.get("VIRTUAL_ENV", "")

    if not actual_venv or not actual_venv.startswith(expected_venv):
        print("Warning: .venv is not active. If dependencies fail, run: source .venv/bin/activate")

    print("Seeker spawned")

    querify_tracklists(
        TRACKLIST_DIR,
        QUERYFILE_PATH,
        use_last_run_only=not args.all_tracklists,
    )
    sendseek(args, community_state)
