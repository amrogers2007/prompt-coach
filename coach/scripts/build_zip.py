#!/usr/bin/env python3
"""Build dist/prompt-coach-plugin.zip: the file you upload in Claude Desktop under
Customize > Plugins > Add > Upload plugin (works for Cowork and Chat-side skills).

The zip's root is the plugin root (.claude-plugin/plugin.json at the top level).
Tests and caches are left out.
"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(os.path.dirname(PLUGIN_ROOT), "dist")
SKIP_DIRS = {"tests", "__pycache__", ".git", "dist"}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "prompt-coach-plugin.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(PLUGIN_ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(root, name)
                arc = os.path.relpath(full, PLUGIN_ROOT).replace(os.sep, "/")
                z.write(full, arc)
                count += 1
    print("Wrote %s (%d files)" % (out, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
