"""The game layer: XP, streaks, achievements, and the short toast messages.

XP is lifetime flavor (it only goes up). The *level* comes from scoring.py and
can go down. Streaks count working days with a good-habit moment, and skip
weekends so a Friday-to-Monday gap doesn't break one.
"""

import datetime

from . import scoring, store

ACHIEVEMENTS = [
    ("first_steps", "First steps", "Sent your first coached prompt.",
     lambda s: s["totals"]["prompts"] >= 1),
    ("second_draft", "Second draft", "Revised an AI-made document instead of accepting the first draft.",
     lambda s: s["totals"]["revisions"] >= 1),
    ("draft_habit", "Draft habit", "Revised AI-made documents 5 times.",
     lambda s: s["totals"]["revisions"] >= 5),
    ("context_setter", "Context setter", "Gave rich context up front in 5 requests.",
     lambda s: s["totals"]["rich_prompts"] >= 5),
    ("fact_checker", "Fact checker", "Asked the AI to check or source its work 3 times.",
     lambda s: s["totals"]["verifies"] >= 3),
    ("streak_3", "3-day streak", "Three working days in a row of good AI habits.",
     lambda s: s["streak"]["best"] >= 3),
    ("streak_7", "7-day streak", "Seven working days in a row of good AI habits.",
     lambda s: s["streak"]["best"] >= 7),
    ("streak_14", "14-day streak", "Fourteen working days in a row of good AI habits.",
     lambda s: s["streak"]["best"] >= 14),
    ("clean_hands", "Clean hands", "50 prompts with no sensitive data flagged.",
     lambda s: s["totals"]["prompts"] >= 50 and s["totals"]["sensitive"] == 0),
]
_TITLES = {a[0]: a[1] for a in ACHIEVEMENTS}


def _to_date(day):
    return datetime.date.fromisoformat(day)


def _workdays_between(a, b):
    """Working days strictly after date a up to and including date b."""
    n, d = 0, a
    while d < b:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def touch_streak(state, ts):
    """Record a good-habit moment at time ts. Returns new streak count if it grew."""
    today = store.day_of(ts)
    streak = state["streak"]
    last = streak.get("last_day") or ""
    if last == today:
        return None
    if last:
        gap = _workdays_between(_to_date(last), _to_date(today))
        streak["count"] = streak["count"] + 1 if gap <= 1 else 1
    else:
        streak["count"] = 1
    streak["last_day"] = today
    streak["best"] = max(streak.get("best", 0), streak["count"])
    return streak["count"]


def xp_for_prompt(analysis):
    xp = 5
    if analysis["kind"] == "new":
        xp += int(round(10 * analysis["context"]))
        xp += int(round(5 * analysis["precision"]))
    if analysis.get("verify"):
        xp += 5
    if analysis.get("feature") == 1.0:
        xp += 5
    return xp


def is_good_habit(analysis):
    if analysis["kind"] == "refine":
        return True
    return analysis["kind"] == "new" and analysis["context"] >= 0.6


def check_achievements(state, ts):
    """Unlock any newly-earned achievements. Returns their titles."""
    unlocked = []
    for aid, title, _desc, test in ACHIEVEMENTS:
        if aid in state["achievements"]:
            continue
        try:
            ok = test(state)
        except (KeyError, TypeError):
            ok = False
        if ok:
            state["achievements"][aid] = ts
            unlocked.append(title)
    return unlocked


def level_up_achievement(state, level, ts):
    aid = "level_%d" % level
    if aid not in state["achievements"]:
        state["achievements"][aid] = ts
        return True
    return False


def level_name(level):
    return scoring.LEVELS.get(level, "Beginner")


def toast_lines(level_change, streak_grew, new_achievements, level):
    """At most two short lines so the user is celebrated, not nagged."""
    lines = []
    if level_change > 0:
        lines.append("Level up! You're now %s (Level %d of 4)." % (level_name(level), level))
    elif level_change < 0:
        lines.append("Level slipped to %s. A few more context-rich requests and revisions will win it back." % level_name(level))
    if streak_grew and streak_grew in (3, 5, 7, 10, 14, 20, 30):
        lines.append("%d-day streak of good AI habits." % streak_grew)
    for title in new_achievements[:2]:
        if len(lines) >= 2:
            break
        lines.append("Achievement unlocked: %s." % title)
    return lines[:2]
