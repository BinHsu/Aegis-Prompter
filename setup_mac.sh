#!/bin/bash

# Aegis Prompter - Cross-Mac Deployment Script
# Ensures an isolated environment that doesn't pollute the host macOS.

set -e

echo "🚀 [Aegis Prompter] Starting automated Mac environment deployment..."
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "Checking Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew is not installed. Please install Homebrew first and try again."
    exit 1
fi

echo "Checking and installing system dependencies (portaudio)..."
brew list portaudio &> /dev/null || brew install portaudio

# BlackHole is the FALLBACK capture path, not the default one (R6), so this script no longer
# installs it. It used to run `brew reinstall --cask blackhole-2ch` plus `sudo killall coreaudiod`
# unconditionally, which demanded a login password during every normal setup — for a component the
# product exists to stop needing, and which the process tap replaced (V61, V62, V65, V69). Killing
# coreaudiod also interrupts audio for every other application on the machine. Detect, report, and
# leave the decision to the operator; the tap needs no driver and no password.
echo "Checking system-audio capture options..."
if ls -d /Library/Audio/Plug-Ins/HAL/BlackHole*.driver >/dev/null 2>&1; then
    echo "✅ BlackHole is installed — available as the fallback path if the tap cannot run."
else
    echo "ℹ️  BlackHole is not installed, and that is the normal case now."
    echo "    System audio is captured by the Core Audio process tap built below — no driver,"
    echo "    no password, and your output device is left alone."
    echo "    You only need BlackHole on macOS older than 14.2 (V6) or if the tap fails to build."
    echo "    If you do: brew install --cask blackhole-2ch   (it will ask for your password,"
    echo "    and a reboot or 'sudo killall coreaudiod' is required to load the driver)."
fi

# Pick an interpreter the dependencies actually support. macOS still ships 3.9, which reached
# end of life in October 2025, and `mlx` requires >= 3.10 — a .venv built on the system python
# silently pins an older mlx whose inference is measurably slower (V51) and whose ASR output
# differs (V53). Prefer the newest supported interpreter present; never fall back to 3.9.
echo "Selecting a Python interpreter (>= 3.10 required)..."
PYTHON_BIN=""
for CANDIDATE in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$CANDIDATE" &> /dev/null; then
        if "$CANDIDATE" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
            PYTHON_BIN="$(command -v "$CANDIDATE")"
            break
        fi
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ No Python >= 3.10 found. Install one, e.g. 'brew install python@3.12', then re-run."
    exit 1
fi
echo "✅ Using $PYTHON_BIN ($("$PYTHON_BIN" -V))"

echo "Checking virtual environment (.venv) state..."
# An existing .venv is kept only if it both works AND is >= 3.10. A venv built by an older run
# of this script on the system 3.9 would otherwise survive forever and quietly cap mlx.
if [ -d ".venv" ] && .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    echo "✅ Existing .venv is usable ($(.venv/bin/python -V)). Retaining."
else
    if [ -d ".venv" ]; then
        echo "⚠️ Existing .venv is broken or older than 3.10. Rebuilding (the old one is moved aside)..."
        rm -rf .venv.old && mv .venv .venv.old
    else
        echo "Creating a fresh isolated virtual environment (.venv)..."
    fi
    "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate

# Model weights are NOT cached in the project. Where they land is the operator's choice, made
# in the web UI, and HF_HOME is derived from it at runtime by src/bootstrap.py. Exporting a
# project-local HF_HOME here only ever affected this script's own shell anyway.
echo "Ensuring the pip cache directory exists..."
mkdir -p .pip_cache
export PIP_CACHE_DIR="$PROJECT_DIR/.pip_cache"

echo "Upgrading pip and installing project dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

# The system-audio tap helper. Command Line Tools are enough -- no Xcode (V6) -- and the binary is
# gitignored because it is a build artefact of a source file that is not. A machine that cannot
# build it is not broken: BlackHole remains the fallback capture path (R6), so this warns rather
# than aborts a setup that is otherwise complete.
echo "Building the system-audio tap helper..."
if xcrun --find clang >/dev/null 2>&1; then
    if clang -fobjc-arc -framework Foundation -framework CoreAudio \
             -o "$PROJECT_DIR/src/native/aegis_tap" "$PROJECT_DIR/src/native/aegis_tap.m"; then
        echo "   built: src/native/aegis_tap"
    else
        echo "   ⚠️  compile failed. System audio will fall back to BlackHole."
    fi
else
    echo "   ⚠️  no clang found (xcode-select --install). Falling back to BlackHole for system audio."
fi

echo "Regenerating the agent-facing file map (FILEMAP.md)..."
python "$PROJECT_DIR/tools/gen_filemap.py"

echo "=========================================="
echo "✅ [Aegis Prompter] Deployment Complete!"
echo "👉 Environment is ready. To begin:"
echo "     source .venv/bin/activate"
echo "     streamlit run src/app.py"
echo "👉 No model weights were downloaded. Open the page on THIS Mac, choose a storage root,"
echo "   and the app fetches them there with a progress bar."
echo "=========================================="
