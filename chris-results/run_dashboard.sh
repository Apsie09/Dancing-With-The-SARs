#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8766}"
echo "TerraGuard dashboard: http://127.0.0.1:${PORT}/terraguard_dashboard.html"
echo "Press Ctrl+C to stop."
python3 -m http.server "$PORT" --directory .
