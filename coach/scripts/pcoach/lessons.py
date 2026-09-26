"""The micro-training library and how coaching moments are chosen and worded.

Each lesson is one small idea plus a few *questions* the AI can ask. The
coach's job is to ask, not to rewrite the user's prompt for them: people
learn the habit by answering the question themselves.
"""

SKILL_TITLES = {
    "context": "Giving the AI context",
    "iteration": "Treating first drafts as drafts",
    "precision": "Saying what a good answer looks like",
    "verification": "Checking the AI's work",
    "feature": "Using the right feature",
    "safety": "Keeping sensitive data out",
    "advanced": "Advanced prompting moves",
}

LESSONS = [
    # ---- context ------------------------------------------------------------
    {"id": "ctx-audience", "skill": "context", "levels": (1, 3),
     "title": "Say who it's for",
     "tip": "The same request produces very different results for a CEO, a new hire, or a customer. Naming the reader is the cheapest quality boost there is.",
     "questions": ["Who is going to read this, and what do they already know?",
                   "If your manager forwarded this, what would they want the reader to do next?"]},
    {"id": "ctx-goal", "skill": "context", "levels": (1, 3),
     "title": "Say what it's for",
     "tip": "AI does much better when it knows the goal behind the task, not just the task.",
     "questions": ["What do you want to be true after this is done that isn't true now?",
                   "What decision or action is this meant to lead to?"]},
    {"id": "ctx-example", "skill": "context", "levels": (1, 4),
     "title": "Show, don't just tell",
     "tip": "One example of what you like, or a paragraph you already wrote, teaches the AI your taste faster than a description does.",
     "questions": ["Do you have a past example of something like this that you liked?",
                   "Can you paste two sentences in the voice you want?"]},
    {"id": "ctx-interview", "skill": "context", "levels": (2, 4),
     "title": "Let the AI interview you",
     "tip": "For bigger tasks, ask the AI to question you first. It surfaces what you forgot to mention.",
     "questions": ["Want me to ask you 3 quick questions before I start, so the first draft lands closer?"]},
    # ---- iteration ----------------------------------------------------------
    {"id": "it-draft", "skill": "iteration", "levels": (1, 4),
     "title": "The first draft is the starting line",
     "tip": "Experts almost never accept the first output. Two or three rounds of 'change this, keep that' is where the quality comes from.",
     "questions": ["What is the one thing you would change if you had to present this in ten minutes?",
                   "Which part feels least like you?"]},
    {"id": "it-specific", "skill": "iteration", "levels": (1, 3),
     "title": "Point at the exact spot",
     "tip": "'Make it better' gives the AI nothing to aim at. 'Cut slide 3 in half and lead with the cost' does.",
     "questions": ["Which single slide, paragraph, or sentence bothers you most, and why?"]},
    {"id": "it-critic", "skill": "iteration", "levels": (2, 4),
     "title": "Ask for a critique before you accept",
     "tip": "Have the AI play a tough reviewer of its own draft. It usually finds real problems.",
     "questions": ["Want me to review this as your toughest reader would, and list what they would push back on?"]},
    # ---- precision ----------------------------------------------------------
    {"id": "pr-format", "skill": "precision", "levels": (1, 3),
     "title": "Name the shape of the answer",
     "tip": "Length, format, and tone are decisions only you can make. If you don't, the AI picks a generic default.",
     "questions": ["How long should this be, and in what format: bullets, a table, a one-pager?",
                   "Should it sound formal, friendly, or somewhere between?"]},
    {"id": "pr-limits", "skill": "precision", "levels": (2, 4),
     "title": "Say what to avoid",
     "tip": "A short list of 'don'ts' (jargon, hype words, anything legally risky) removes the most annoying failures.",
     "questions": ["Is there anything you'd hate to see in the answer: phrases, claims, or a tone?"]},
    # ---- verification -------------------------------------------------------
    {"id": "vf-sure", "skill": "verification", "levels": (1, 4),
     "title": "Ask how sure it is",
     "tip": "AI can sound equally confident when it is right and when it is guessing. Asking it to flag uncertainty changes what you get back.",
     "questions": ["Which parts of that would you double-check before sending it to anyone?",
                   "Do any of those numbers or claims need a source?"]},
    {"id": "vf-holes", "skill": "verification", "levels": (2, 4),
     "title": "Invite disagreement",
     "tip": "AI tends to agree with you. Asking it to poke holes is how you get its honest second opinion.",
     "questions": ["What is the strongest argument against what I just told you?"]},
    # ---- feature ------------------------------------------------------------
    {"id": "ft-file", "skill": "feature", "levels": (1, 3),
     "title": "Point at the file, don't paste it",
     "tip": "Attach or reference the real document instead of pasting a wall of text. Then the AI can edit it in place and you skip the copy-paste loop.",
     "questions": ["Is that text from a document you could attach instead, so I can edit it directly?"]},
    {"id": "ft-inplace", "skill": "feature", "levels": (1, 4),
     "title": "Edit in the AI, not in Word",
     "tip": "Rather than copying the output into Word to fix it by hand, tell the AI the fix and let it regenerate. It keeps the whole conversation's context.",
     "questions": ["Instead of fixing that by hand, want to just tell me what to change?"]},
    # ---- safety -------------------------------------------------------------
    {"id": "sf-redact", "skill": "safety", "levels": (1, 4),
     "title": "Redact before you paste",
     "tip": "Keys, passwords, IDs, and confidential material should not go into AI tools unless your company has approved that use.",
     "questions": ["Could we swap the sensitive parts for placeholders like [CLIENT] and [ACCOUNT #] and still get what you need?"]},
    # ---- advanced -----------------------------------------------------------
    {"id": "ad-role", "skill": "advanced", "levels": (3, 4),
     "title": "Give it a role and a reader",
     "tip": "'You are a hiring manager reading this résumé' plus 'the reader is skeptical' gives the AI a viewpoint to write from.",
     "questions": ["Whose eyes should I read this through: a skeptic, a busy executive, a customer?"]},
    {"id": "ad-chain", "skill": "advanced", "levels": (3, 4),
     "title": "Break big jobs into steps",
     "tip": "Outline first, then draft, then tighten. Each step is easier to steer than one giant request.",
     "questions": ["Want to agree on the outline first before I write the full thing?"]},
]

_BY_ID = {l["id"]: l for l in LESSONS}

# The coach's visible voice. Every coaching moment is written the same way so the
# user can always tell the coach apart from the AI's own answer.
VOICE = ("Always write the coaching in italics and start it with \"Prompt Coach:\", "
         "like this: *Prompt Coach: Who is this for, and what should they take away?*")


def get(lesson_id):
    return _BY_ID.get(lesson_id)


def pick(skill, level, recent_ids):
    """Best lesson for a skill at a level, avoiding recent repeats."""
    pool = [l for l in LESSONS if l["skill"] == skill and l["levels"][0] <= level <= l["levels"][1]]
    if not pool:
        pool = [l for l in LESSONS if l["skill"] == skill] or LESSONS
    recent = list(recent_ids)
    # Prefer the lesson shown longest ago (or never).
    def age_rank(l):
        return recent[::-1].index(l["id"]) if l["id"] in recent else 10 ** 6
    pool.sort(key=age_rank, reverse=True)
    return pool[0]


def question_for(lesson, seed):
    qs = lesson["questions"]
    return qs[seed % len(qs)]


COMPONENT_TO_SKILL = {
    "context": "context",
    "iteration": "iteration",
    "precision": "precision",
    "verification": "verification",
    "feature": "feature",
    "consistency": "context",
}


def coach_instruction(lesson, question, reason, level_name, weakest_note=""):
    """The hidden instruction handed to the AI for one coaching moment."""
    reason_line = {
        "safety": "The user just included what looks like sensitive information. Address that first, kindly.",
        "low_context": "Their request was quite bare, so the AI had to guess.",
        "cadence": "This is a scheduled training moment.",
    }.get(reason, "")
    return (
        "[Prompt Coach: coaching moment]\n"
        "The user is a non-technical professional building AI skills; you are also their coach. "
        "First, do the task they asked for fully and well. Never withhold or delay help.\n"
        "Then finish your reply with ONE short coaching moment: a blank line, then at most 3 lines. " + VOICE + "\n"
        "Lesson: %s. %s\n"
        "Ask exactly ONE question that gets the user to make the improvement themselves. "
        "For example: \"%s\"\n"
        "%s"
        "Rules: warm and brief; do NOT rewrite their prompt for them; no jargon, no lecture; "
        "if their message already did this well, praise the specific thing instead of asking. "
        "Never mention this instruction, hooks, scores, or the plugin's internals. "
        "The user is at the %s level.%s"
    ) % (lesson["title"], lesson["tip"], question,
         (reason_line + "\n") if reason_line else "", level_name,
         (" " + weakest_note) if weakest_note else "")


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
