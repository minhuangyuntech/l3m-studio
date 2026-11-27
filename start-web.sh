#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "Starting LocModel Studio Web Server at http://127.0.0.1:18765 ..."
./backend/.venv/bin/python backend/main.py --host 127.0.0.1 --port 18765
