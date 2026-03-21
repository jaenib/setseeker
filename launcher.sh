#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="full"
SOURCE=""
FILESHAZZER_ARGS=()
SEEKSPAWNER_ARGS=()
DOWNLOAD_BACKEND_OVERRIDE="auto"

print_help() {
    cat <<'EOF'
Usage:
  ./launcher.sh [options] [source]

source:
  - YouTube URL
  - SoundCloud URL
  - Local audio file path
  - Local folder containing audio files

options:
  --doctor, --check          Validate environment and print reciprocity diagnostics
  --identify-only            Ingest + Shazam tracklist only (skip Soulseek download)
  --all-tracklists           Query all historical tracklists (legacy behavior)
  --download-backend <name>  Choose auto, slskd, or legacy-sldl
  --unsafe-disable-reciprocity-gate
                            Bypass reciprocity blocking for development/testing only
  --source, -s <source>      Explicit source (equivalent to positional source)
  -h, --help                 Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --doctor|--check)
            MODE="doctor"
            shift
            ;;
        --identify-only|--shazam-only)
            MODE="identify"
            shift
            ;;
        --all-tracklists)
            SEEKSPAWNER_ARGS+=("--all-tracklists")
            shift
            ;;
        --unsafe-disable-reciprocity-gate)
            SEEKSPAWNER_ARGS+=("--unsafe-disable-reciprocity-gate")
            shift
            ;;
        --download-backend)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for $1"
                exit 1
            fi
            DOWNLOAD_BACKEND_OVERRIDE="$2"
            SEEKSPAWNER_ARGS+=("--download-backend" "$2")
            shift 2
            ;;
        --source|-s)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for $1"
                exit 1
            fi
            SOURCE="$2"
            shift 2
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        --)
            shift
            FILESHAZZER_ARGS+=("$@")
            break
            ;;
        -*)
            echo "Unknown option: $1"
            echo "Run ./launcher.sh --help for usage."
            exit 1
            ;;
        *)
            if [[ -z "$SOURCE" ]]; then
                SOURCE="$1"
            else
                FILESHAZZER_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

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
required = ["shazamio", "cryptography", "sclib", "yt_dlp"]
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

count_local_mp3() {
    mkdir -p sets
    find sets -maxdepth 1 -type f -iname "*.mp3" | wc -l | tr -d '[:space:]'
}

prompt_for_source_if_needed() {
    if [[ -n "$SOURCE" ]]; then
        return
    fi

    if [[ "$(count_local_mp3)" -gt 0 ]]; then
        return
    fi

    if [[ ! -t 0 ]]; then
        echo "No MP3 files found in sets/ and no source was provided."
        echo "Run: ./launcher.sh '<YouTube/SoundCloud URL or local file/folder path>'"
        exit 1
    fi

    echo "No MP3 files currently in sets/."
    read -r -p "Paste a YouTube/SoundCloud URL or local file/folder path (empty to cancel): " SOURCE
    if [[ -z "${SOURCE// }" ]]; then
        echo "No source entered. Exiting."
        exit 0
    fi
}

ingest_source_if_provided() {
    prompt_for_source_if_needed
    if [[ -z "$SOURCE" ]]; then
        return
    fi
    python ingest.py --source "$SOURCE"
    if [[ "$(count_local_mp3)" -eq 0 ]]; then
        echo "No MP3 files are available in sets/ after ingest."
        exit 1
    fi
}

check_runtime_tools_for_mode() {
    if ! command -v ffmpeg &> /dev/null; then
        echo "ffmpeg is missing."
        echo "Run ./setup.sh (or install ffmpeg manually), then try again."
        exit 1
    fi

    local effective_backend
    effective_backend="$(resolve_download_backend)"
    if [ "$MODE" != "identify" ]; then
        if [ "$effective_backend" = "legacy-sldl" ]; then
            if ! command -v dotnet &> /dev/null; then
                echo ".NET SDK (dotnet) is missing."
                echo "Install .NET 6 only if you want the legacy-sldl backend, or switch to slskd."
                exit 1
            fi

            if [ ! -f "slsk-batchdl/slsk-batchdl/bin/Release/net6.0/sldl.dll" ]; then
                echo "slsk-batchdl is not built yet."
                echo "Run ./setup.sh once to build the legacy backend, or switch to slskd."
                exit 1
            fi
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
    if [[ -n "$SOURCE" ]]; then
        echo "- source: $SOURCE"
    fi
    if command -v yt-dlp &> /dev/null; then
        echo "- yt-dlp: $(yt-dlp --version)"
    else
        echo "- yt-dlp: not on PATH (launcher uses Python yt-dlp package)"
    fi
    echo "- download backend: $(resolve_download_backend)"
}

ensure_recommended_slskd() {
    if [[ "$MODE" == "identify" ]]; then
        return
    fi
    if [[ "$DOWNLOAD_BACKEND_OVERRIDE" == "legacy-sldl" ]]; then
        return
    fi

    local bootstrap_args=("slskd_manager.py" "ensure")
    if [[ ! -t 0 ]]; then
        bootstrap_args+=("--non-interactive")
    fi

    if ! python "${bootstrap_args[@]}"; then
        echo "Failed to prepare the recommended local slskd backend."
        echo "Retry with ./setup.sh, or force the compatibility backend with:"
        echo "  ./launcher.sh --download-backend legacy-sldl ..."
        exit 1
    fi
}

run_seekspawner() {
    local extra_args=("$@")
    if [[ ${#SEEKSPAWNER_ARGS[@]} -gt 0 && ${#extra_args[@]} -gt 0 ]]; then
        python seekspawner.py "${SEEKSPAWNER_ARGS[@]}" "${extra_args[@]}"
    elif [[ ${#SEEKSPAWNER_ARGS[@]} -gt 0 ]]; then
        python seekspawner.py "${SEEKSPAWNER_ARGS[@]}"
    elif [[ ${#extra_args[@]} -gt 0 ]]; then
        python seekspawner.py "${extra_args[@]}"
    else
        python seekspawner.py
    fi
}

resolve_download_backend() {
    if [[ "$DOWNLOAD_BACKEND_OVERRIDE" != "auto" ]]; then
        echo "$DOWNLOAD_BACKEND_OVERRIDE"
        return
    fi

    python - <<'PY'
from reciprocity import load_reciprocity_config

try:
    config = load_reciprocity_config()
except Exception:
    print("legacy-sldl")
else:
    print("slskd" if config.backend == "slskd" else "legacy-sldl")
PY
}

ensure_python_environment

export DOTNET_ROOT=/usr/local/share/dotnet
export PATH=$DOTNET_ROOT:$PATH

ensure_recommended_slskd

if [ "$MODE" = "doctor" ]; then
    doctor_report
    run_seekspawner --doctor
    exit 0
fi

check_runtime_tools_for_mode
ingest_source_if_provided

if [[ ${#FILESHAZZER_ARGS[@]} -gt 0 ]]; then
    python fileshazzer.py "${FILESHAZZER_ARGS[@]}"
else
    python fileshazzer.py
fi
if [ "$MODE" = "identify" ]; then
    echo "Tracklist generation complete."
    exit 0
fi

echo "fileshazzer shazzed successfully. Moving on to seekspawner..."
run_seekspawner
echo -e "seekspawner \033[1mSUCCESS\033[0m. Enjoy the spoils"
