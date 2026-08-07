#!/bin/bash
# 🛡️ Aegis Prompter - Automated Testing Engine

# 1. Get project absolute path
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "🚀 [Aegis Prompter] Booting up testing engine in: $PROJECT_ROOT"

# 2. Locate isolated Python engine
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "⚠️ ERROR: Python binary not found in .venv. Ensure the environment is set up by running 'bash setup_mac.sh' first."
    exit 1
fi

# 3. Ensure testing utilities are available
echo "📦 [1/3] Checking and installing unit testing dependencies..."
"$PYTHON_BIN" -m pip install pytest pytest-mock -q

# 4. Keep the generated file map in sync with the code (stdlib only, never hand-edited)
echo "🗺️ [2/3] Regenerating FILEMAP.md from the current source tree..."
"$PYTHON_BIN" "$PROJECT_ROOT/tools/gen_filemap.py"

# 5. Ignite green light tests (filtering environmental warnings like EOL, SSL, Deprecation)
echo "🏗️ [3/3] Initiating Unit Tests and Mock Verifications..."
export PYTHONPATH="$PROJECT_ROOT"
"$PYTHON_BIN" -m pytest "$PROJECT_ROOT/tests/unit" -v \
    -W ignore::DeprecationWarning \
    -W ignore::FutureWarning \
    -W ignore:"urllib3 v2 only supports OpenSSL"

echo "✅ [COMPLETE] Testing suite finished execution. Environmental warnings were filtered out. Please review the logical green lights."
