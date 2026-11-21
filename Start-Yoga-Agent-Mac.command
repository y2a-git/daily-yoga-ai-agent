#!/bin/bash
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 app.py
else
    echo "============================================================"
    echo " Python 3 was not found on this Mac."
    echo " Opening python.org so you can install it in 1 click..."
    echo "============================================================"
    open "https://www.python.org/downloads/macos/"
    read -p "Press Enter to close..."
fi