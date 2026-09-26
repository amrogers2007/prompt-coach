#!/bin/sh
# Install Prompt Coach for Claude Code (macOS / Linux / Git Bash on Windows).
# Usage: sh install/install.sh
set -e
REPO="amrogers2007/prompt-coach"

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code ('claude') was not found on your PATH."
  echo "Using the Claude desktop app instead? Open Customize > Plugins and upload dist/prompt-coach-plugin.zip"
  echo "(build it with: python coach/scripts/build_zip.py)."
  exit 1
fi

PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Prompt Coach needs Python 3.8 or newer (https://www.python.org/downloads/). Install it, then re-run this script."
  exit 1
fi

echo "Adding the Prompt Coach marketplace..."
claude plugin marketplace add "$REPO"
echo "Installing the plugin..."
claude plugin install prompt-coach@prompt-coach
echo
echo "Health check:"
"$PY" "$(dirname "$0")/../coach/scripts/coach.py" doctor || true
echo
echo "Done. Start a new Claude Code session and just work as usual; the coach starts automatically."
echo "Type /prompt-coach:score any time to see your level."
