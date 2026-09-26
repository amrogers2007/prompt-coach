#!/bin/sh
# Launcher: find a working Python 3 and run coach.py with the given arguments.
# Hooks call this so the plugin works on macOS, Linux, and Windows (Git Bash)
# regardless of whether Python is named python3, python, or py. If Python is
# missing we exit 0 silently: coaching must never break the user's session.
dir=$(dirname "$0")
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    exec "$py" "$dir/coach.py" "$@"
  fi
done
exit 0
