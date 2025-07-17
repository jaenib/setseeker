import sys
import os
import json
import subprocess
import glob
import re
from shazamio import Shazam
from cryptography.fernet import Fernet


# ---------- SETTINGS -----------------------------
TRACKLIST_DIR = "tracklists"
QUERYFILE_PATH = "tmp/queries/queries.txt"
SKIPPED_PATH = "logsskipped_queries.log"

SLSKDL_EXECUTABLE = "slsk-batchdl/slsk-batchdl/bin/Release/net6.0/sldl.dll"
SLSK_CRED = "user"  # Path to your Soulseek credentials file

SLSK_USER = ""  # Fill in manually to skip loading
SLSK_PW = ""  # Fill in manually to skip loading
# --------------------------------------------------


def load_cred(path):
    cred_path=f"{path}/slsk_cred.json"
    with open(cred_path, "r") as f:
        data = json.load(f)
    key_path = f"{path}/slsk.key"
    with open(key_path, "rb") as f:
        key = f.read()

    fernet = Fernet(key)
    username = data["username"]
    password = fernet.decrypt(data["password_encrypted"].encode()).decode()
    return username, password

def is_queryfied(artist, title):
    return artist != "" and title != "" and "-" not in artist and '"' not in title

def querify_tracklists(tracklist_dir, output_query_file):
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

    if not SLSK_USER or not SLSK_PW:
        print("Soulseek credentials missing. Attempting to load from file...")
        try:
            SLSK_USER, SLSK_PW = load_cred(SLSK_CRED)
            print(f"Loaded credentials from {SLSK_USER}")
        except Exception as e:
            print(f"Error loading credentials: {e}")
        if SLSK_USER == "":
            SLSK_USER = input("Soulseek username: ")
        if SLSK_PW == "":
            SLSK_PW = input("Soulseek password: ")

    else:
        print(f"Accessing Soulseek as {SLSK_USER}")

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

    command = [#"source", "~/.zshrc","export", "DOTNET_ROOT=usr/local/share/dotnet", "&&", "export", "PATH=$DOTNET_ROOT:$PATH", "&&",
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
    # Check venv
    expected_venv = os.path.abspath("setseek_venv")
    actual_venv = os.environ.get("VIRTUAL_ENV", "")
    
    if not actual_venv or not actual_venv.startswith(expected_venv):
        print("(I told you they'd forget..): Please activate the virtual environment with 'source setseek_venv/bin/activate' before running this script.")
        sys.exit(1)

    print("Virtual environment good. Seeker spawned")

    # GO
    querify_tracklists(TRACKLIST_DIR, QUERYFILE_PATH)
    sendseek()
