"""The game layer: XP, streaks, achievements, and the short toast messages.

XP is lifetime flavor (it only goes up). The *level* comes from scoring.py and
can go down. Streaks count days in a row with a good-habit moment; weekends off
do not break one, a missed working day does.
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
    ("streak_3", "3-day streak", "Three days in a row of good AI habits.",
     lambda s: s["streak"]["best"] >= 3),
    ("streak_7", "7-day streak", "Seven days in a row of good AI habits.",
     lambda s: s["streak"]["best"] >= 7),
    ("streak_14", "14-day streak", "Fourteen days in a row of good AI habits.",
     lambda s: s["streak"]["best"] >= 14),
    ("coachable", "Coachable", "Took the coach up on 3 of its offers.",
     lambda s: s["totals"].get("offers_accepted", 0) >= 3),
    ("clean_hands", "Clean hands", "50 prompts with no sensitive data flagged.",
     lambda s: s["totals"]["prompts"] >= 50 and s["totals"]["sensitive"] == 0),
]
_TITLES = {a[0]: a[1] for a in ACHIEVEMENTS}

# How close the user is to each badge, for the dashboard: id -> (have, need).
# Keep in step with the tests in ACHIEVEMENTS above (test_dashboard checks they agree).
ACHIEVEMENT_PROGRESS = {
    "first_steps": lambda s: (s["totals"]["prompts"], 1),
    "second_draft": lambda s: (s["totals"]["revisions"], 1),
    "draft_habit": lambda s: (s["totals"]["revisions"], 5),
    "context_setter": lambda s: (s["totals"]["rich_prompts"], 5),
    "fact_checker": lambda s: (s["totals"]["verifies"], 3),
    "streak_3": lambda s: (s["streak"]["best"], 3),
    "streak_7": lambda s: (s["streak"]["best"], 7),
    "streak_14": lambda s: (s["streak"]["best"], 14),
    "coachable": lambda s: (s["totals"].get("offers_accepted", 0), 3),
    "clean_hands": lambda s: (s["totals"]["prompts"] if s["totals"]["sensitive"] == 0 else 0, 50),
}


def _to_date(day):
    return datetime.date.fromisoformat(day)


def _missed_workdays(a, b):
    """Working days strictly between date a and date b: the ones that went by
    without a good-habit moment. (Counting b itself would let a Thursday streak
    carry on over a missed Friday when the next use is on the weekend.)"""
    n, d = 0, a + datetime.timedelta(days=1)
    while d < b:
        if d.weekday() < 5:
            n += 1
        d += datetime.timedelta(days=1)
    return n


def _last_day(streak):
    """The saved last good-habit day as a date, or None if there is none (or it is unreadable)."""
    try:
        return _to_date(streak.get("last_day") or "")
    except (TypeError, ValueError):
        return None


def touch_streak(state, ts):
    """Record a good-habit moment at time ts. Returns new streak count if it grew."""
    today = store.day_of(ts)
    streak = state["streak"]
    last = _last_day(streak)
    if last is not None and last >= _to_date(today):
        return None                      # already counted today (or the clock went backwards)
    if last is not None and _missed_workdays(last, _to_date(today)) == 0:
        streak["count"] = streak.get("count", 0) + 1
    else:
        streak["count"] = 1
    streak["last_day"] = today
    streak["best"] = max(streak.get("best", 0), streak["count"])
    return streak["count"]


def streak_status(state, now=None):
    """The streak as it stands right now, for anything that shows it.

    The saved count is only true as of the last good-habit day. It is still alive
    today and through the next working day; after a missed working day it is 0,
    even though nothing has been saved since. 'today' says whether today already
    counts, so a note can say what would move the number."""
    streak = state.get("streak") or {}
    best = streak.get("best", 0)
    last = _last_day(streak)
    if last is None:
        return {"count": 0, "best": best, "today": False, "alive": False}
    today = _to_date(store.day_of(store.now() if now is None else now))
    alive = _missed_workdays(last, today) == 0
    return {"count": streak.get("count", 0) if alive else 0, "best": best,
            "today": alive and last >= today, "alive": alive}


def current_streak(state, now=None):
    return streak_status(state, now)["count"]


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
    elif streak_grew and streak_grew >= 2:
        # Said once a day, the moment the number moves, so it never looks stuck.
        lines.append("Streak: %d days in a row." % streak_grew)
    for title in new_achievements[:2]:
        if len(lines) >= 2:
            break
        lines.append("Achievement unlocked: %s." % title)
    return lines[:2]
