#!/usr/bin/env bash
# Sets up a local development environment for CampPhoto AI.
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data logs output models

echo ""
echo "Environment ready. Activate it with: source .venv/bin/activate"
echo "Then try:  python -m app.cli --help"
