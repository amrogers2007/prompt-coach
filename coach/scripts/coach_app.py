#!/usr/bin/env python3
"""The one program the installer puts on a computer (coach.exe / coachw.exe).

Everything Prompt Coach does goes through it, so the computer needs no Python:

    coach.exe session | prompt | tool      the plugin's hooks (Claude Code, Code tab)
    coach.exe mcp                          the helper Claude chat and Cowork talk to
    coach.exe score | dashboard | ...      the same commands as coach.py
    coachw.exe uninstall                   remove Prompt Coach (asks first)

coachw.exe is the same program built without a console window, for shortcuts.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "mcp":
        import coach_mcp
        return coach_mcp.main()
    if cmd == "uninstall":
        import installer
        return installer.uninstall_interactive(argv[2:])
    if not cmd and getattr(sys, "frozen", False) and sys.stdout is None:
        argv = argv + ["dashboard"]          # coachw.exe double-clicked: show the dashboard
    import coach
    return coach.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
