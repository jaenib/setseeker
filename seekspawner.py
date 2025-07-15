import os
import json
import subprocess

# ---------- SETTINGS -----------------------------
TRACKLIST_DIR = "tracklists_test"
QUERYFILE_PATH = "queries.txt"
SKIPPED_PATH = "skipped_queries.log"

SLSKDL_EXECUTABLE = "slsk-batchdl-master/slsk-batchdl/bin/Release/net6.0/sldl.dll"
SLSK_CRED = ""

SLSK_USER = ""  # Fill in manually to skip loading
SLSK_PW = ""  # Fill in manually to skip loading
# --------------------------------------------------


def load_cred(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data["username"], data["password"]

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

            if cleaned and '-' in cleaned:
                parts = cleaned.rsplit('-', maxsplit=1)
                artist = parts[0].strip()
                title = re.sub(r'\s+(320|FLAC)$', '', parts[1].strip(), flags=re.IGNORECASE)

                if not is_queryfied(artist, title):
                    skipped.append(f"[{file_path}:{lineno}] BAD FORMAT -> {cleaned}")
                    continue

                for format_type in ["mp3", "flac"]:
                    key = (artist.lower(), title.lower(), format_type)
                    if key not in seen:
                        seen.add(key)

                        if format_type == "mp3":
                            query_line = f"\"artist={artist},title={title}\"  \"format=mp3\"  \"br >= 320\""
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

    global SLSK_USER, SLSK_PASS

    if not SLSK_USER or not SLSK_PASS:
        print("Soulseek credentials missing. Attempting to load from file...")
        try:
            SLSK_USER, SLSK_PASS = load_cred(SLSK_CRED)
            print(f"Loaded credentials from {SLSK_CRED}")
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return
        else:
          if SLSK_USER == "":
            SLSK_USER = input("Soulseek username: ")
          if SLSK_PW == "":
            SLSK_PW = input("Soulseek password: ")

    else:
        print(f"Using provided Soulseek credentials: {SLSK_USER}")

    command = [
        "dotnet",
        SLSKDL_EXECUTABLE,
        QUERYFILE_PATH,
        "--user", SLSK_USER,
        "--pass", SLSK_PW,
        "--input-type=list"
    ]

    try:
        subprocess.run(command, check=True)
        print("Seek concluded")
    except subprocess.CalledProcessError as e:
        print(f"Seek collapsed under {e}")

if __name__ == "__main__":
    querify_tracklists(TRACKLIST_PATH, QUERYFILE_PATH)
    sendseek()


