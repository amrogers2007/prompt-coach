#!/usr/bin/env python3
"""Build dist/prompt-coach-chat-skill.zip: the small skill you upload once in the
Claude desktop app (Customize > Skills) so that regular chat uses the coach.

Chat can't run the plugin's hooks, so there Claude calls the coach's local helper
each message (connect it with setup_desktop.py). This skill is what tells Claude
to do that in every conversation. Its wording comes from the helper itself, so
the two can't drift apart.
"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pcoach.mcp_server import INSTRUCTIONS  # noqa: E402

PLUGIN_ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(os.path.dirname(PLUGIN_ROOT), "dist")


def chat_skill_md():
    return (
        "---\n"
        "name: prompt-coach\n"
        'description: "Use in every conversation. Prompt Coach is this user\'s AI-skills coach: call its tools '
        '(coach_start, coach_turn, coach_document, coach_score, coach_settings) as described, and deliver its '
        'coaching in italics starting with Prompt Coach:."\n'
        "---\n\n"
        "This user has the Prompt Coach helper connected to Claude on their computer. Use its tools in every "
        "conversation.\n\n"
        + INSTRUCTIONS +
        "\n\nIf the Prompt Coach tools are not available in this conversation, ignore this skill completely and tell "
        "the user only if they ask why coaching is missing (the helper may not be connected: see the Prompt Coach "
        "README, 'Claude desktop app, Chat and Cowork').\n"
    )


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    skill = os.path.join(OUT_DIR, "prompt-coach-chat-skill.zip")
    with zipfile.ZipFile(skill, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("prompt-coach/SKILL.md", chat_skill_md())
    print("Wrote %s" % skill)
    return 0


if __name__ == "__main__":
    sys.exit(main())
