"""User controls shared by the command line (coach.py settings ...) and the chat
helper (coach_settings): explain the last tip, and mute or unmute a tip.

Each function takes the loaded state, changes it if needed, and returns
(message, changed). The caller saves the state when `changed` is true.
"""

import time

from . import lessons

FOREVER_SECONDS = 10 * 365 * 86400


def why(state):
    last = state["coach"].get("last_moment") or {}
    entry = lessons.get(last.get("id", "")) if last else None
    if not entry:
        return "No coaching tip has been shown yet.", False
    lines = ["Last tip: %s" % entry["title"]]
    if last.get("triggers"):
        lines.append("Why: %s" % entry["when"])
        lines.append("Spotted by: %s (only these labels were stored, never your words)" % ", ".join(last["triggers"]))
    else:
        lines.append("Why: it was time for a regular practice moment on this habit (%s)." % entry["skill"])
    lines.append("Don't want it again? Mute it: %s" % entry["id"])
    return "\n".join(lines), False


def mute(state, tip_id, now=None):
    tip_id = (tip_id or "").strip()
    if not tip_id or tip_id == "last":
        tip_id = (state["coach"].get("last_moment") or {}).get("id", "")
    entry = lessons.get(tip_id)
    if not entry:
        return "Unknown tip '%s'. Ask 'why' to see the last tip's id." % tip_id, False
    state["coach"].setdefault("muted", {})[tip_id] = (now or time.time()) + FOREVER_SECONDS
    return "You won't see '%s' again (undo by unmuting %s)." % (entry["title"], tip_id), True


def unmute(state, tip_id):
    tip_id = (tip_id or "").strip()
    muted = state["coach"].setdefault("muted", {})
    if tip_id == "all":
        muted.clear()
        return "All tips can come up again.", True
    entry = lessons.get(tip_id)
    if not entry:
        return "Unknown tip '%s'." % tip_id, False
    muted.pop(tip_id, None)
    return "'%s' can come up again." % entry["title"], True
