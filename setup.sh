#!/bin/bash

echo "🔧 Setting up your Soulseek track downloader..."

# 1. Create Python virtual environment
if [ ! -d "setseek_venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv setseek_venv
else
    echo "Python virtual environment already exists."
fi

echo "Activating venv and installing Python dependencies..."
source setseek_venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. Install .NET 6 SDK if missing
if ! command -v dotnet &> /dev/null; then
    echo ".NET 6 SDK not found. Installing..."
    # macOS with Homebrew
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install --cask dotnet-sdk
    else
        echo "Please install .NET 6 SDK manually: https://dotnet.microsoft.com/en-us/download"
        exit 1
    fi
else
    echo ".NET SDK found"
fi

# 3. Clone slsk-batchdl if not present
if [ ! -d "slsk-batchdl" ]; then
    echo "Cloning slsk-batchdl..."
    git clone https://github.com/fiso64/slsk-batchdl.git
else
    echo "slsk-batchdl already cloned."
fi

# 4. Build slsk-batchdl
echo "🔨 Building slsk-batchdl..."
cd slsk-batchdl/slsk-batchdl
dotnet build -c Release
cd ../..

# 5. Setup default folders
mkdir -p  sets tracklists spoils user logs temp/segments temp/queries

# 6. Prompt to create Soulseek credentials file

if [ ! -f "user/slsk_cred.json" ]; then
    echo "Enter Soulseek credentials now to be stored at user/slsk_cred.json"
    echo "OR"
    echo "Manually provide during each run of seekspawner."

    read -p "Enter and store now? (Y/n) " answer
    answer=${answer:-Y}  # default to 'Y' if empty

    if [[ "$answer" =~ ^[Yy]$ ]]; then
        read -p "Enter your Soulseek username: " username
        read -s -p "Enter your Soulseek password: " password
        echo ""
        source setseek_venv/bin/activate
        python3 crencrypt.py "$username" "$password" "user"
    else
        echo "Ok Schwurbli, You'll be prompted to enter credentials every time when running seekspawner."
    fi
else
    echo "Soulseek credentials exist, change then? (Y/n)"
    read -p "Change credentials? (Y/n) " change_answer
    change_answer=${change_answer:-N}  # default to 'N' if empty

    if [[ "$change_answer" =~ ^[Yy]$ ]]; then
        read -p "Enter your Soulseek username: " username
        read -s -p "Enter your Soulseek password: " password
        echo ""
        source setseek_venv/bin/activate
        python3 crencrypt.py "$username" "$password" "user"
    else
        echo "Keeping existing credentials."
    fi
fi


echo "setseek setup success"
#echo "Always activate the virtual environment with:"
#echo "   source setseek_venv/bin/activate"
