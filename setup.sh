#!/bin/bash

echo "Setting up your Soulseek track downloader..."

# 1. Create Python virtual environment
if [ ! -d "setseek_venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "Python virtual environment already exists."
fi

echo "Activating venv and installing Python dependencies..."
source .venv/bin/activate
echo "Acitvated venv, Python is:"
which python
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

# 4. Install .NET 6 SDK if missing
dotnet_missing=false
if ! command -v dotnet &> /dev/null; then
    echo ".NET 6 SDK not found. Attempting to install..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install --cask dotnet-sdk
    elif command -v apt-get &> /dev/null; then
        wget https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
        sudo dpkg -i packages-microsoft-prod.deb
        rm packages-microsoft-prod.deb
        sudo apt-get update
        sudo apt-get install -y dotnet-sdk-6.0
    else
        echo "Please install .NET 6 SDK manually: https://dotnet.microsoft.com/en-us/download"
    fi
    if ! command -v dotnet &> /dev/null; then
        echo ".NET 6 SDK still missing. Install it manually and re-run setup.sh."
        dotnet_missing=true
    fi
else
    echo ".NET SDK found"
fi

if [ "$dotnet_missing" = false ]; then
    export DOTNET_ROOT=/usr/local/share/dotnet
    export PATH=$DOTNET_ROOT:$PATH
    echo "Setting up .NET environment variables DOTNET_ROOT and PATH..."

    # Clone slsk-batchdl if not present
    if [ ! -d "slsk-batchdl" ]; then
        echo "Cloning slsk-batchdl..."
        git clone https://github.com/fiso64/slsk-batchdl.git
    else
        echo "slsk-batchdl already cloned."
    fi
    # Build slsk-batchdl
    echo "🔨 Building slsk-batchdl..."
    (cd slsk-batchdl/slsk-batchdl && dotnet build -c Release)
else
    echo "Skipping slsk-batchdl build due to missing .NET."
fi

# 5. Prompt to create Soulseek credentials file
if [ ! -f "user/slsk_cred.json" ]; then
    echo "Soulseek credentials are stored encrypted at user/slsk_cred.json"
    echo "You can remove this file to reset them later."
    if [[ -n "$SLSK_USERNAME" && -n "$SLSK_PASSWORD" ]]; then
        python3 crencrypt.py "$SLSK_USERNAME" "$SLSK_PASSWORD" "user"
        echo "Credentials stored from environment variables."
    else
        echo "Enter Soulseek credentials now to store them (or skip to provide at runtime)."
        read -p "Enter and store now? (Y/n) " answer
        answer=${answer:-Y}  # default to 'Y' if empty

        if [[ "$answer" =~ ^[Yy]$ ]]; then
            read -p "Enter your Soulseek username: " username
            read -s -p "Enter your Soulseek password: " password
            echo ""
            python3 crencrypt.py "$username" "$password" "user"
        else
            echo "You'll be prompted to enter credentials every time when running seekspawner."
        fi
    fi
else
    echo "Soulseek credentials exist, change then? (Y/n)"
    read -p "Change credentials? (Y/n) " change_answer
    change_answer=${change_answer:-N}  # default to 'N' if empty

    if [[ "$change_answer" =~ ^[Yy]$ ]]; then
        read -p "Enter your Soulseek username: " username
        read -s -p "Enter your Soulseek password: " password
        echo ""
        source .venv/bin/activate
        python3 crencrypt.py "$username" "$password" "user"
    else
        echo "Keeping existing credentials."
    fi
fi

if [ "$dotnet_missing" = true ]; then
    echo "!! slsk-batchdl not built. Install .NET 6 SDK and re-run setup.sh. !!"
fi

echo "setseek setup success"
echo "continue by adding mp3 to folder: sets, or add soundcloud-urls to fileshazzer.py"
#echo "Always activate the virtual environment with:"
#echo "   source setseek_venv/bin/activate"
