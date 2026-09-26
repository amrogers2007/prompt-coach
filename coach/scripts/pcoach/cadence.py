"""When should the coach speak up? Adaptive: often for beginners, rarely for experts.

Rules, in priority order:
  1. Never if disabled or paused.
  2. Sensitive data always gets a nudge, even right after another one.
  3. Never on two consecutive prompts (that's nagging).
  4. Not before the user has sent a couple of prompts (let them settle in).
  5. A bare, context-free request from a newer user gets coached promptly.
  6. Otherwise on a schedule that stretches as the level rises.
"""

INTERVAL_BY_LEVEL = {1: 2, 2: 3, 3: 5, 4: 8}
INTENSITY_FACTOR = {"light": 1.6, "normal": 1.0, "frequent": 0.6}
MIN_PROMPTS_BEFORE_COACHING = 2
LOW_CONTEXT = 0.35


def interval(level, intensity):
    base = INTERVAL_BY_LEVEL.get(level, 3)
    factor = INTENSITY_FACTOR.get(intensity, 1.0)
    return max(2, int(round(base * factor)))


def is_paused(settings, now_ts):
    if not settings.get("enabled", True):
        return True
    return settings.get("paused_until", 0) > now_ts


def decide(state, analysis, level, now_ts):
    """Return (should_coach, reason). `prompts_since` counts scored prompts
    since the last coaching moment, *not* including the current one."""
    settings = state["settings"]
    if is_paused(settings, now_ts):
        return False, "paused"

    if analysis.get("sensitive"):
        return True, "safety"

    coach = state["coach"]
    since = coach["prompts_since"]
    total = state["totals"]["prompts"]

    if since < 1:
        return False, "cooldown"
    if total < MIN_PROMPTS_BEFORE_COACHING:
        return False, "warmup"

    if analysis["kind"] == "new" and analysis["context"] < LOW_CONTEXT and level <= 2:
        return True, "low_context"

    if since >= interval(level, settings.get("intensity", "normal")) - 1:
        return True, "cadence"
    return False, "not_due"
