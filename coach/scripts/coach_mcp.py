#!/usr/bin/env python3
"""Entry point for the Prompt Coach MCP server (Claude chat / Cowork). See pcoach/mcp_server.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcoach import mcp_server  # noqa: E402


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    mcp_server.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
