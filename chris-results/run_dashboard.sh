#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8766}"
echo "TerraGuard evidence explorer: http://127.0.0.1:${PORT}/app/"
echo "Press Ctrl+C to stop."
python3 -m http.server "$PORT" --directory .
