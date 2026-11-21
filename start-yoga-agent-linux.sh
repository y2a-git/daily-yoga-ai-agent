#!/usr/bin/env bash
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 app.py
else
    echo "Python 3 is required. Install it with: sudo apt install python3"
    read -p "Press Enter to close..."
fi