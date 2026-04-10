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

echo "Checking BlackHole virtual audio driver..."
if ! ls -d /Library/Audio/Plug-Ins/HAL/BlackHole*.driver >/dev/null 2>&1; then
    echo "⚠️ BlackHole audio driver not detected (or incomplete). Preparing to install..."
    echo "👉 [Password Required] The following requires system privileges to write the driver. Please enter your Mac login password:"
    brew reinstall --cask blackhole-2ch
    echo "🔄 Restarting Mac core audio service (coreaudiod) to load the new driver..."
    sudo killall coreaudiod
else
    echo "✅ BlackHole virtual audio driver is securely installed."
fi

echo "Checking Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed."
    exit 1
fi

echo "Checking virtual environment (.venv) state..."
if [ -d ".venv" ]; then
    # Test if the existing python inside .venv works on this specific Mac
    if .venv/bin/python -c "import sys" >/dev/null 2>&1; then
        echo "✅ Existing .venv is compatible with the current Mac. Retaining."
    else
        echo "⚠️ Existing .venv is broken (likely due to Mac path changes). Rebuilding..."
        rm -rf .venv
        python3 -m venv .venv
    fi
else
    echo "Creating a fresh isolated virtual environment (.venv)..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Ensuring cache directories exist (for models & packages)..."
mkdir -p .hf_cache
mkdir -p .pip_cache

echo "Loading environment variables..."
export HF_HOME="$PROJECT_DIR/.hf_cache"
export PIP_CACHE_DIR="$PROJECT_DIR/.pip_cache"

echo "Upgrading pip and installing project dependencies..."
python3 -m pip install --upgrade pip
pip install -r requirements.txt

echo "=========================================="
echo "✅ [Aegis Prompter] Deployment Complete!"
echo "👉 Environment is ready. To begin, type 'source .venv/bin/activate' in this terminal."
echo "👉 Host OS remains clean. GBs of ML weights are safely cached within the project folder."
echo "=========================================="
