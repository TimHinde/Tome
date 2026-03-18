#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Init git submodules (SRD reference data)
if git rev-parse --git-dir > /dev/null 2>&1; then
    git submodule update --init --recursive --quiet
fi

# Run the MCP server
echo "Starting Tome MCP server..."
exec python server.py
