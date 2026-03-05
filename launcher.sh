#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="full"
case "${1:-}" in
    --doctor|--check)
        MODE="doctor"
        shift
        ;;
    --identify-only|--shazam-only)
        MODE="identify"
        shift
        ;;
esac

choose_python() {
    local candidate
    for candidate in python3.11 python3.10 python3.9 python3; do
        if command -v "$candidate" &> /dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

venv_is_compatible() {
    if [ ! -x ".venv/bin/python" ]; then
        return 1
    fi
    .venv/bin/python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
}

ensure_python_environment() {
    local pybin
    pybin="$(choose_python)" || {
        echo "No supported python3 interpreter found."
        echo "Install Python 3.11 and rerun ./launcher.sh."
        exit 1
    }

    if ! venv_is_compatible; then
        echo "Preparing a compatible .venv using ${pybin}..."
        rm -rf .venv
        "${pybin}" -m venv .venv
    fi

    # shellcheck disable=SC1091
    source .venv/bin/activate

    python -m pip install --upgrade pip > /dev/null

if ! python - <<'PY' > /tmp/setseek_missing_python_deps.txt 2>&1
import importlib.util
required = ["shazamio", "cryptography", "sclib"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(",".join(missing))
    raise SystemExit(1)
PY
    then
        echo "Missing Python packages in .venv. Installing requirements..."
        if ! python -m pip install -r requirements.txt; then
            echo "Failed to install Python dependencies."
            echo "Check internet/DNS, then run ./setup.sh."
            exit 1
        fi
    fi
}

check_runtime_tools() {
    if ! command -v ffmpeg &> /dev/null; then
        echo "ffmpeg is missing."
        echo "Run ./setup.sh (or install ffmpeg manually), then try again."
        exit 1
    fi

    if [ "$MODE" != "identify" ]; then
        if ! command -v dotnet &> /dev/null; then
            echo ".NET SDK (dotnet) is missing."
            echo "Run ./setup.sh to install/build slsk-batchdl."
            exit 1
        fi

        if [ ! -f "slsk-batchdl/slsk-batchdl/bin/Release/net6.0/sldl.dll" ]; then
            echo "slsk-batchdl is not built yet."
            echo "Run ./setup.sh once, then rerun ./launcher.sh."
            exit 1
        fi
    fi
}

doctor_report() {
    echo "Environment looks good:"
    echo "- python: $(python --version 2>&1)"
    echo "- pip: $(python -m pip --version)"
    echo "- ffmpeg: $(command -v ffmpeg)"
    if command -v dotnet &> /dev/null; then
        echo "- dotnet: $(dotnet --version)"
    else
        echo "- dotnet: not found"
    fi
    echo "- mode: $MODE"
}

ensure_python_environment
check_runtime_tools

export DOTNET_ROOT=/usr/local/share/dotnet
export PATH=$DOTNET_ROOT:$PATH

if [ "$MODE" = "doctor" ]; then
    doctor_report
    exit 0
fi

python fileshazzer.py "$@"
if [ "$MODE" = "identify" ]; then
    echo "Tracklist generation complete."
    exit 0
fi

echo "fileshazzer shazzed successfully. Moving on to seekspawner..."
python seekspawner.py "$@"
echo -e "seekspawner \033[1mSUCCESS\033[0m. Enjoy the spoils"
