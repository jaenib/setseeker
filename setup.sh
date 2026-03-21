#!/bin/bash
set -euo pipefail

echo "Setting up setseeker..."

# 1. Select Python and create virtual environment
PYTHON_BIN=""
for candidate in python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" &> /dev/null; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "No python3 interpreter found. Install Python 3.11+ and rerun setup."
    exit 1
fi

echo "Using $PYTHON_BIN for virtual environment creation."

# Recreate incompatible old envs (for example python 3.8 envs from conda shim)
if [ -x ".venv/bin/python" ]; then
    if ! .venv/bin/python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"; then
        echo "Existing .venv uses unsupported Python. Recreating .venv with $PYTHON_BIN..."
        rm -rf .venv
    fi
fi

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    "$PYTHON_BIN" -m venv .venv
else
    echo "Python virtual environment already exists."
fi

echo "Activating venv and installing Python dependencies..."
source .venv/bin/activate
echo "Activated venv, Python is:"
which python
python -c "import sys; print(sys.version)"
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 2. Ensure ffmpeg is available
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg not found. Attempting to install..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ffmpeg
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    else
        echo "Please install ffmpeg manually: https://ffmpeg.org/download.html"
    fi
else
    echo "ffmpeg found"
fi

# 3. Setup default folders
mkdir -p sets tracklists spoils user logs tmp/segments tmp/queries

# Credential paths (single canonical location inside this repo)
CRED_DIR="user"
CRED_FILE="$CRED_DIR/slsk_cred.json"
KEY_FILE="$CRED_DIR/slsk.key"
LEGACY_CRED_FILE="../user/slsk_cred.json"
LEGACY_KEY_FILE="../user/slsk.key"

# Offer to import credentials from legacy sibling folders to avoid duplicate stores.
if [ ! -f "$CRED_FILE" ] && [ ! -f "$KEY_FILE" ] && [ -f "$LEGACY_CRED_FILE" ] && [ -f "$LEGACY_KEY_FILE" ]; then
    echo "Found encrypted Soulseek credentials in ../user (legacy location)."
    read -p "Import those into this repo's user/ folder now? (Y/n) " import_answer
    import_answer=${import_answer:-Y}
    if [[ "$import_answer" =~ ^[Yy]$ ]]; then
        cp "$LEGACY_CRED_FILE" "$CRED_FILE"
        cp "$LEGACY_KEY_FILE" "$KEY_FILE"
        echo "Imported credentials into $CRED_DIR/"
    fi
fi

# 4. Prompt to create Soulseek credentials file
if [ -f "$CRED_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "Encrypted Soulseek credentials already exist at $CRED_FILE"
    read -p "Change credentials now? (y/N) " change_answer
    change_answer=${change_answer:-N}

    if [[ "$change_answer" =~ ^[Yy]$ ]]; then
        read -p "Enter your Soulseek username: " username
        read -s -p "Enter your Soulseek password: " password
        echo ""
        source .venv/bin/activate
        python3 crencrypt.py "$username" "$password" "$CRED_DIR"
    else
        echo "Keeping existing encrypted credentials."
    fi
else
    if [ -f "$CRED_FILE" ] || [ -f "$KEY_FILE" ]; then
        echo "Found incomplete credential files in $CRED_DIR. They will be recreated."
        rm -f "$CRED_FILE" "$KEY_FILE"
    fi

    echo "Soulseek credentials are stored encrypted at $CRED_FILE"
    echo "Choose N if you'd rather enter credentials at runtime."

    if [[ -n "$SLSK_USERNAME" && -n "$SLSK_PASSWORD" ]]; then
        python3 crencrypt.py "$SLSK_USERNAME" "$SLSK_PASSWORD" "$CRED_DIR"
        echo "Credentials stored from environment variables."
    else
        read -p "Store credentials now? (Y/n) " answer
        answer=${answer:-Y}  # default to 'Y' if empty

        if [[ "$answer" =~ ^[Yy]$ ]]; then
            read -p "Enter your Soulseek username: " username
            read -s -p "Enter your Soulseek password: " password
            echo ""
            python3 crencrypt.py "$username" "$password" "$CRED_DIR"
        else
            echo "Skipping storage. seekspawner.py will prompt at runtime."
        fi
    fi
fi

echo "Preparing a local slskd backend for the recommended reciprocity-backed mode..."
if python slskd_manager.py ensure; then
    echo "Local slskd is ready."
else
    echo "Automatic slskd setup did not complete."
    echo "You can rerun ./setup.sh after fixing network or permissions."
fi

echo "setseek setup success"
echo "next steps:"
echo "  1. run ./launcher.sh --doctor"
echo "  2. then run ./launcher.sh '<youtube/soundcloud url or local file>'"
#echo "Always activate the virtual environment with:"
#echo "   source setseek_venv/bin/activate"
