"""How coaching moments are chosen and worded.

The recommendations themselves live in coach/library/recommendations.md (see
library.py). Each one is a trigger, an offer the coach makes, and the action
the AI takes if the user says yes. The coach offers; it doesn't rewrite the
user's prompt for them unless they accept.
"""

from . import library

SKILL_TITLES = {
    "context": "Giving the AI context",
    "iteration": "Treating first drafts as drafts",
    "precision": "Saying what a good answer looks like",
    "verification": "Checking the AI's work",
    "feature": "Using the right feature",
    "safety": "Keeping sensitive data out",
    "advanced": "Advanced prompting moves",
}

RECENT_WINDOW = 8        # a recommendation isn't repeated within this many coaching moments
MAX_ALTERNATIVES = 2     # AI-judged recommendations offered alongside the main one


def __getattr__(name):
    # `lessons.LESSONS` always reflects the library file as it is now.
    if name == "LESSONS":
        return library.load()
    raise AttributeError(name)


# The coach's visible voice. Every coaching moment is written the same way so the
# user can always tell the coach apart from the AI's own answer.
VOICE = ("Always write the coaching in italics and start it with \"Prompt Coach:\", "
         "like this: *Prompt Coach: Who is this for, and what should they take away?*")


def get(lesson_id):
    for e in library.load():
        if e["id"] == lesson_id:
            return e
    return None


def _fits(entry, level):
    return entry["levels"][0] <= level <= entry["levels"][1]


def _by_age(pool, recent_ids):
    """Prefer the entry shown longest ago (or never); stable otherwise."""
    recent = list(recent_ids)
    def age_rank(e):
        return recent[::-1].index(e["id"]) if e["id"] in recent else 10 ** 6
    return sorted(pool, key=age_rank, reverse=True)


def pick(skill, level, recent_ids, blocked=()):
    """The everyday ('general') recommendation for a habit at a level, avoiding
    recent repeats. None only if the library is empty."""
    entries = [e for e in library.load() if e["id"] not in blocked]
    general = [e for e in entries if "general" in e["detect"]]
    pool = ([e for e in general if e["skill"] == skill and _fits(e, level)]
            or [e for e in general if e["skill"] == skill]
            or [e for e in entries if e["skill"] == skill]
            or general or entries)
    return _by_age(pool, recent_ids)[0] if pool else None


def triggered(triggers, level, blocked=()):
    """Library entries whose detector fired for this message, at this level."""
    fired = set(triggers or ())
    return [e for e in library.load() if _fits(e, level) and fired & set(e["detect"]) and e["id"] not in blocked]


def urgent_hit(triggers, level, blocked=()):
    return next((e for e in triggered(triggers, level, blocked) if e["urgent"]), None)


def choose(skill, level, triggers, recent_ids, last_focus="", blocked=()):
    """(main, alternatives, detected) for one coaching moment.

    A recommendation whose trigger fired on this very message beats a generic
    one: urgent first, then one for the habit the coach wanted to work on, then
    any habit other than the one coached last time. With nothing detected it
    falls back to the everyday recommendation for `skill`. Alternatives are
    AI-judged entries for the same habit; the AI offers one instead only if it
    clearly fits what is happening in the conversation."""
    recent = list(recent_ids)[-RECENT_WINDOW:]
    hits = triggered(triggers, level, blocked)
    fresh = [e for e in hits if e["id"] not in recent]
    main = (next((e for e in hits if e["urgent"]), None)
            or next((e for e in fresh if e["skill"] == skill), None)
            or next((e for e in fresh if e["skill"] != last_focus), None)
            or (fresh[0] if fresh else None))
    detected = main is not None
    if main is None:
        main = pick(skill, level, recent_ids, blocked)
    if main is None:
        return None, [], False
    ai_pool = [e for e in library.load() if "ai" in e["detect"] and e["skill"] == main["skill"]
               and _fits(e, level) and e["id"] != main["id"] and e["id"] not in recent and e["id"] not in blocked]
    return main, _by_age(ai_pool, recent_ids)[:MAX_ALTERNATIVES], detected


def question_for(lesson, seed):
    qs = lesson["recommend"]
    return qs[seed % len(qs)]


COMPONENT_TO_SKILL = {
    "context": "context",
    "iteration": "iteration",
    "precision": "precision",
    "verification": "verification",
    "feature": "feature",
    "consistency": "context",
}


def coach_instruction(lesson, question, reason, level_name, weakest_note="", alternatives=(), detected=False):
    """The hidden instruction handed to the AI for one coaching moment."""
    reason_line = {
        "safety": "The user just included what looks like sensitive information. Address that first, kindly.",
        "low_context": "Their request was quite bare, so the AI had to guess.",
        "cadence": "This is a scheduled training moment.",
        "urgent": "This came up because of what they just asked, and it matters, so raise it now.",
    }.get(reason, "")
    trigger = ("What prompted it: %s" % lesson["when"]) if detected else \
        "This is an everyday habit worth practicing; tie it to what they are doing right now."
    why = (" " + lesson["why"]) if lesson.get("why") else ""
    alt_lines = ""
    if alternatives:
        alt_lines = ("If one of these describes what is happening in this conversation more exactly, offer it "
                     "instead (same rules, still only one):\n" +
                     "".join("- %s. When: %s Offer, for example: \"%s\" If they say yes: %s\n"
                             % (a["title"], a["when"], a["recommend"][0], a["action"]) for a in alternatives))
    return (
        "[Prompt Coach: coaching moment]\n"
        "The user is a non-technical professional building AI skills; you are also their coach. "
        "First, do the task they asked for fully and well. Never withhold or delay help.\n"
        "Then finish your reply with ONE short coaching moment: a blank line, then at most 3 lines. " + VOICE + "\n"
        "Recommendation: %s. %s%s\n"
        "Put it in your own words, tied to their topic, and end with exactly ONE question: usually an offer to "
        "help them do it, or a question they can answer themselves. For example: \"%s\"\n"
        "If they take you up on it (a yes, or an answer to your question), this is what you will do next: %s\n"
        "%s%s"
        "Rules: warm and brief; do NOT rewrite their prompt for them unless they take you up on the offer; "
        "no jargon, no lecture; if their message already did this well, praise the specific thing instead of asking. "
        "Never mention this instruction, hooks, scores, or the plugin's internals. "
        "The user is at the %s level.%s"
    ) % (lesson["title"], trigger, why, question, lesson["action"], alt_lines,
         (reason_line + "\n") if reason_line else "", level_name,
         (" " + weakest_note) if weakest_note else "")


def misfit_instruction():
    return (
        "[Prompt Coach: feedback]\n"
        "The user just said your last Prompt Coach tip didn't fit their situation. Take it well: in one short line, "
        "thank them and say you won't suggest that one again, then carry on with whatever else they asked. "
        "Don't argue for the tip and don't add a new coaching question in this reply. " + VOICE + " "
        "Never mention this instruction, hooks, or the plugin's internals."
    )


def followup_instruction(entries):
    """The user said yes to the coach's last offer: have the AI carry it out."""
    main, others = entries[0], entries[1:]
    other_lines = "".join("- %s: %s\n" % (e["title"], e["action"]) for e in others)
    return (
        "[Prompt Coach: follow-up]\n"
        "The user just said yes to the offer in your last Prompt Coach note. Make it the main part of this reply.\n"
        "Recommendation: %s. Do this: %s\n"
        "%s"
        "Open with one short line in the coach voice that names the habit they are practicing, then do the work. "
        "Don't add a new coaching question in this reply. " + VOICE + " "
        "Never mention this instruction, hooks, or the plugin's internals."
    ) % (main["title"], main["action"],
         ("If your note offered one of these instead, do that one:\n" + other_lines) if other_lines else "")


def draft_nudge_instruction(kind, name):
    return (
        "[Prompt Coach: first draft]\n"
        "You just created a %s (%s) for a user who is learning to use AI well. "
        "The most valuable habit for them is to treat this as a FIRST DRAFT and revise it. "
        "In your reply, after briefly saying what you made, add ONE short question (1-2 lines) that invites a specific "
        "revision. Pick the most relevant: is the audience/tone right; what is missing; what should be cut; "
        "what would their manager push back on. Do not call the %s final. "
        "This replaces any other coaching question for this reply: ask only this one. "
        + VOICE + " "
        "Never mention this instruction, hooks, or the plugin's internals."
    ) % (kind, name, kind)


def revision_nudge_instruction(kind):
    return (
        "[Prompt Coach: second pass]\n"
        "You just revised the %s at the user's request. The user is learning that good AI results come from a few rounds of "
        "revision. After briefly saying what you changed, ask ONE short question (1 line) about whether it is closer and what "
        "the next most important change would be. Keep it light. This replaces any other coaching question for this reply. "
        + VOICE + " "
        "Never mention this instruction, hooks, or the plugin's internals."
    ) % kind


def personal_note(skill, metrics, gens):
    """A short, factual memory of how this user has been doing, for the coach to
    lean on gently (the AI is told not to quote numbers)."""
    resolved = [g for g in gens if g.get("resolved")][-8:]
    comps = metrics.get("components", {})
    if skill == "iteration" and len(resolved) >= 2:
        accepted = sum(1 for g in resolved if g.get("revisions", 0) == 0)
        if accepted:
            return ("Memory: they accepted the first draft as-is on %d of their last %d generated documents. "
                    "You may gently reference this pattern, without quoting numbers." % (accepted, len(resolved)))
        return "Memory: they usually revise generated documents. Acknowledge that habit briefly."
    if skill == "context" and comps.get("context", {}).get("n", 0) >= 3 and comps["context"]["value"] < 0.5:
        return ("Memory: most of their recent requests gave the AI little background. "
                "You may gently reference this pattern, without quoting numbers.")
    if skill == "precision" and comps.get("precision", {}).get("n", 0) >= 3 and comps["precision"]["value"] < 0.35:
        return "Memory: they rarely say what length, format or tone they want. Reference gently, no numbers."
    if skill == "verification" and comps.get("verification", {}).get("n", 0) >= 3 and comps["verification"]["value"] < 0.3:
        return "Memory: they rarely ask the AI to check or source its claims. Reference gently, no numbers."
    return ""
