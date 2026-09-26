#!/usr/bin/env python3
"""Build the Claude desktop pieces for chat and Cowork:

    dist/prompt-coach.mcpb            the desktop extension (the local coach helper)
    dist/prompt-coach-chat-skill.zip  a skill that tells Claude when to use it

A .mcpb is just a zip with a manifest.json and the server files. Claude Desktop
does not ship Python, so the helper uses the Python already on the computer
(3.9+, standard library only: nothing to install).
"""

import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pcoach import __version__  # noqa: E402
from pcoach.mcp_server import INSTRUCTIONS, TOOLS  # noqa: E402

PLUGIN_ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(os.path.dirname(PLUGIN_ROOT), "dist")


def manifest():
    return {
        "manifest_version": "0.3",
        "name": "prompt-coach",
        "display_name": "Prompt Coach",
        "version": __version__,
        "description": "An AI coach inside Claude: coaching questions, draft-revision nudges, and a local AI Fluency level.",
        "long_description": (
            "Prompt Coach helps people who never learned to use AI get much more out of it. Instead of rewriting your "
            "prompts it asks the right question at the right moment, nudges you to revise the decks, PDFs and documents "
            "Claude makes for you, and tracks a local AI Fluency level (Beginner to Expert) you can share with a manager.\n\n"
            "Everything runs on this computer. Your messages are analysed locally and reduced to small numbers; the text "
            "itself is never stored and nothing is sent anywhere. Requires Python 3.9 or newer."),
        "author": {"name": "Amanda Rogers", "url": "https://github.com/amrogers2007"},
        "homepage": "https://github.com/amrogers2007/prompt-coach",
        "repository": {"type": "git", "url": "https://github.com/amrogers2007/prompt-coach.git"},
        "license": "MIT",
        "keywords": ["coaching", "prompting", "training", "skills"],
        "server": {
            "type": "python",
            "entry_point": "server/coach_mcp.py",
            "mcp_config": {
                "command": "python3",
                "args": ["${__dirname}/server/coach_mcp.py"],
                "platform_overrides": {"win32": {"command": "python", "args": ["${__dirname}/server/coach_mcp.py"]}},
            },
        },
        "tools": [{"name": t["name"], "description": t["description"]} for t in TOOLS],
        "compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"python": ">=3.9"}},
    }


def chat_skill_md():
    return (
        "---\n"
        "name: prompt-coach\n"
        'description: "Use in every conversation. Prompt Coach is this user\'s AI-skills coach: call its tools '
        '(coach_start, coach_turn, coach_document, coach_score, coach_settings) as described, and deliver its '
        'coaching in italics starting with Prompt Coach:."\n'
        "---\n\n"
        "This user has the Prompt Coach desktop extension installed. Use its tools in every conversation.\n\n"
        + INSTRUCTIONS.replace("\n", "\n\n", 0) +
        "\n\nIf the Prompt Coach tools are not available in this conversation, ignore this skill completely and tell "
        "the user only if they ask why coaching is missing (the extension may need to be enabled in Settings > Extensions).\n"
    )


def _add_tree(z, src_dir, arc_prefix):
    count = 0
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(root, name)
            arc = arc_prefix + "/" + os.path.relpath(full, src_dir).replace(os.sep, "/")
            z.write(full, arc)
            count += 1
    return count


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    mcpb = os.path.join(OUT_DIR, "prompt-coach.mcpb")
    with zipfile.ZipFile(mcpb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(), indent=2))
        z.write(os.path.join(HERE, "coach_mcp.py"), "server/coach_mcp.py")
        n = _add_tree(z, os.path.join(HERE, "pcoach"), "server/pcoach")
    print("Wrote %s (manifest + server + %d module files)" % (mcpb, n))

    skill = os.path.join(OUT_DIR, "prompt-coach-chat-skill.zip")
    with zipfile.ZipFile(skill, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("prompt-coach/SKILL.md", chat_skill_md())
    print("Wrote %s" % skill)
    return 0


if __name__ == "__main__":
    sys.exit(main())
