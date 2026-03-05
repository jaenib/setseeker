import os
import json
import subprocess
import glob
import re
import shutil
import sys
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

SLSKDL_EXECUTABLE = "slsk-batchdl/slsk-batchdl/bin/Release/net6.0/sldl.dll"
CREDENTIAL_DIR = Path("user")
LEGACY_CREDENTIAL_DIRS = [Path("../user")]

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

def is_queryfied(artist, title):
    return artist != "" and title != "" and "-" not in artist and '"' not in title


def querify_tracklists(tracklist_dir, output_query_file=QUERYFILE_PATH):
    seen = set()
    queries = []
    skipped = []

    txt_files = glob.glob(os.path.join(tracklist_dir, "**", "*.txt"), recursive=True)
    print(f"Found {len(txt_files)} .txt files in '{tracklist_dir}'")
    
    for file_path in txt_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for lineno, line in enumerate(lines, 1):
            original = line.strip()
            cleaned = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', original)

            if not cleaned or cleaned.lower().startswith("final tracklist"):
                skipped.append(f"[{file_path}:{lineno}] HEADER OR EMPTY -> {cleaned}")
                continue
    
            if '-' in cleaned:
                parts = cleaned.split('-', maxsplit=1)
    
                if len(parts) < 2:
                    skipped.append(f"[{file_path}:{lineno}] TOO FEW PARTS -> {cleaned}")
                    continue
    
                artist = parts[0].strip()
                title = parts[1].strip()
                title = re.sub(r'\s+(320|FLAC)$', '', title, flags=re.IGNORECASE)
    
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

    with open(output_query_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(queries))

    if skipped:
        with open(SKIPPED_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(skipped))
        print(f"Skipped {len(skipped)} problematic lines. See {SKIPPED_PATH} for details.")

    print(f"{len(queries)} filtered queries (list mode) ready at {output_query_file}")


def sendseek():
    print("Seeking souls...")

    global SLSK_USER, SLSK_PW
    SLSK_USER, SLSK_PW, cred_source = resolve_credentials()
    print(f"Accessing Soulseek as {SLSK_USER} ({cred_source})")

    env = os.environ.copy()
    env["DOTNET_ROOT"] = "/usr/local/share/dotnet"
    env["PATH"] = f'{env["DOTNET_ROOT"]}:{env["PATH"]}'

    '''
    command = ["dotnet", "--list-sdks",
               "DOTNET_ROOT=usr/local/share/dotnet",
               "PATH=$DOTNET_ROOT:$PATH",
               "dotnet", "--list-sdks"]
    '''
    #subprocess.run(command, env=env, check=True)

    command = [
        "dotnet",
        SLSKDL_EXECUTABLE,
        QUERYFILE_PATH,
        "--user", SLSK_USER,
        "--pass", SLSK_PW,
        "--input-type=list",
        "--path", "spoils",
    ]

    try:
        subprocess.run(command, env=env, check=True)
        print("Seek concluded")
    except subprocess.CalledProcessError as e:
        print(f"Seek collapsed under {e}")


if __name__ == "__main__":
    # Friendly warning instead of hard-failing for users who run it directly.
    expected_venv = os.path.abspath(".venv")
    actual_venv = os.environ.get("VIRTUAL_ENV", "")

    if not actual_venv or not actual_venv.startswith(expected_venv):
        print("Warning: .venv is not active. If dependencies fail, run: source .venv/bin/activate")

    print("Seeker spawned")

    # GO
    querify_tracklists(TRACKLIST_DIR, QUERYFILE_PATH)
    sendseek()
