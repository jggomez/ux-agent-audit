#!/bin/bash
# Shell script to build the UX Audit Agent standalone bundle and generate the native macOS .pkg installer.

set -e

# Resolve directory of this script to run correctly from any CWD
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "Initializing build environment..."

if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment (.venv) not found at $PROJECT_DIR/.venv" >&2
    echo "Please set up the virtualenv first by running: uv venv && source .venv/bin/activate && uv pip install -e ." >&2
    exit 1
fi

echo "Running packaging and installer generator script..."
"$PROJECT_DIR"/.venv/bin/python package_app.py

echo "Build process completed successfully."
exit 0
