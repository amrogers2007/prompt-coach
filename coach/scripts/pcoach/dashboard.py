"""Your AI habits over time: a personal dashboard built from the local event log.

`build()` turns the stored signals (numbers and issue labels, never message text)
into one row per calendar day: how much you used AI, your habit scores, the
issues the coach spotted, coaching taken, drafts revised, whether the day had a
good-habit moment, and your AI Fluency score as it stood at the end of that day.
It also packs what the page needs to explain and motivate: each habit gap's
meaning and fix, badge progress, and what the next level still needs.

`write()` renders that into a single self-contained HTML file
(dashboard_page.html + the data) that loads nothing from the internet, so it
works offline and nothing about you leaves this computer.
"""

import datetime
import json
import os
import pathlib
import time
import webbrowser

from . import game, library, scoring, store

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_page.html")
DAY = 86400

# Issues that are gaps in a habit, in plain words. The other detectors describe
# situations (a legal topic, a handoff) rather than something to do less of.
HABIT_GAPS = {
    "no_audience": "Audience not named",
    "no_purpose": "Purpose not stated",
    "no_format": "Format or length not given",
    "vague_goal": "Vague goal",
    "subjective": "Vague quality words (“professional”, “brief”)",
    "jargon": "Unexplained shorthand",
    "style_no_example": "Style asked for without an example",
    "multi_task": "Several tasks in one request",
    "competing_goals": "Competing priorities",
    "long_prompt": "Very long pasted request",
    "factual_question": "Fact question without a source",
    "calculations": "Numbers left unchecked",
    "single_option": "Asked for just one option",
    "long_document": "Long document without an outline",
    "structured_output": "Data format not defined",
    "missed_requirement": "Repeating a missed requirement",
    "manual_edits": "Fixing AI output by hand",
    "sensitive": "Sensitive details shared",
}

# A before/after example for each gap: the everyday version of the fix.
GAP_EXAMPLES = {
    "no_audience": ("Write an email about the office move.",
                    "Write an email to the sales team about the office move; they haven't seen the new building yet."),
    "no_purpose": ("Draft a memo on the parking changes.",
                   "Draft a memo on the parking changes so staff stop using visitor spots from Monday."),
    "no_format": ("Write a welcome note for new hires.",
                  "Write a welcome note for new hires: three short paragraphs, warm, under 150 words."),
    "vague_goal": ("Help me with my presentation.",
                   "Cut my 20-slide presentation to 10 slides for a 15-minute pitch to investors."),
    "subjective": ("Make this bio more professional.",
                   "Rewrite this bio in the third person, no exclamation marks, under 80 words."),
    "jargon": ("Update the OKRs with the NPS numbers.",
               "Update our quarterly goals with the customer satisfaction score, which is now 42 out of 100."),
    "style_no_example": ("Write it in the same style as our newsletter.",
                         "Write it in the same style as our newsletter. Here's last month's opening paragraph: …"),
    "multi_task": ("Summarize this article, compare it to the other one, and draft a reply.",
                   "First, summarize this article in five bullets. We'll compare and draft the reply after."),
    "competing_goals": ("Write a quick, comprehensive, creative plan that's also cheap.",
                        "Write the plan for the lowest cost first. Being fast comes second, and two pages is fine."),
    "long_prompt": ("(Three pages of pasted notes) … can you write the summary?",
                    "Here are the five key points from my notes. Write a one-paragraph summary from them."),
    "factual_question": ("How many people live in Ohio?",
                         "How many people live in Ohio? Cite the source and its date."),
    "calculations": ("Total it up: 1,200 units at $45 with a 15% discount.",
                     "Total it up: 1,200 units at $45 with a 15% discount. Show the formula so I can check it."),
    "single_option": ("Give me a name for my bakery.",
                      "Give me five names for my bakery, each with a one-line reason, then recommend one."),
    "long_document": ("Write a 20-page business plan for a coffee shop.",
                      "Start with an outline for a 20-page coffee-shop business plan. I'll approve it before you write."),
    "structured_output": ("Turn this list into a CSV for our CRM.",
                          "Turn this list into a CSV with these columns: name, email, company, stage."),
    "missed_requirement": ("You forgot the pricing section again.",
                           "Before you answer, check this list: pricing section, under 500 words, no jargon."),
    "manual_edits": ("I fixed the greeting myself in Word.",
                     "Always open with “Hi team” and skip the closing line. Please remember that from now on."),
    "sensitive": ("My SSN is 123-45-6789, fill in this form.",
                  "My SSN is [SSN], fill in this form. I'll add the number myself."),
}

HABITS = [
    ("context", "Giving context", "How much background your new requests give: who it's for, why, your situation."),
    ("precision", "Saying what good looks like", "Whether you name length, format, tone or limits."),
    ("verification", "Checking the AI", "Share of new requests that ask for sources, confidence or a critique."),
    ("iteration", "Revising drafts", "Share of AI-made documents you revised instead of accepting as-is."),
    ("feature", "Working from files", "Share of requests that point at a file instead of pasting text."),
]


def _day(ts):
    return store.day_of(ts)


def _day_end(day):
    d = datetime.datetime.strptime(day, "%Y-%m-%d") + datetime.timedelta(days=1)
    return time.mktime(d.timetuple())


def _days_between(first, last):
    d = datetime.date.fromisoformat(first)
    end = datetime.date.fromisoformat(last)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def _gens(events, state_gens):
    """Generated documents, rebuilt from the event log and merged with the saved
    list (older profiles only have the latter)."""
    gens = {}
    for e in events:
        t, gid = e.get("type"), e.get("gen")
        if t == "gen":
            gens[gid] = {"id": gid, "ts": e["ts"], "kind": e.get("kind"), "revisions": 0, "vague_revs": 0,
                         "resolved": False, "resolved_ts": None}
        elif t == "revision" and gid in gens:
            gens[gid]["revisions"] += 1
            if e.get("vague"):
                gens[gid]["vague_revs"] += 1
        elif t == "gen_resolved" and gid in gens:
            gens[gid]["resolved"] = True
            gens[gid]["resolved_ts"] = e["ts"]
            gens[gid]["revisions"] = max(gens[gid]["revisions"], e.get("revisions", 0))
    for g in state_gens or ():
        merged = dict(gens.get(g["id"], {}))
        merged.update({k: v for k, v in g.items() if v is not None})
        if merged.get("resolved") and not merged.get("resolved_ts"):
            merged["resolved_ts"] = g.get("ts")
        gens[g["id"]] = merged
    return sorted(gens.values(), key=lambda g: g.get("ts", 0))


def _empty_row(day):
    return {"day": day, "prompts": 0, "new": 0, "ctx_sum": 0.0, "ctx_n": 0, "prec_sum": 0.0, "prec_n": 0,
            "verify": 0, "feat_yes": 0, "feat_n": 0, "coached": 0, "taken": 0, "declined": 0, "misfit": 0,
            "docs": 0, "docs_done": 0, "docs_revised": 0, "issues": {}, "good_day": False,
            "score": None, "level": None}


def gap_info():
    """Each habit gap explained: its name, when it happens, the coach's
    suggestion, and a before/after example."""
    by_detector = {}
    for e in library.load():
        for d in e["detect"]:
            by_detector.setdefault(d, e)
    out = {}
    for key, name in HABIT_GAPS.items():
        e = by_detector.get(key)
        before, after = GAP_EXAMPLES.get(key, ("", ""))
        out[key] = {
            "name": name,
            "title": e["title"] if e else name,
            "when": e["when"] if e else "",
            "recommend": e["recommend"][0] if e else "",
            "action": e["action"] if e else "",
            "before": before,
            "after": after,
        }
    return out


def achievements(state, level, score):
    """Badges: earned (with a date) or in progress (have / need)."""
    earned = state.get("achievements", {})
    out = []
    for aid, title, desc, _test in game.ACHIEVEMENTS:
        have, need = game.ACHIEVEMENT_PROGRESS.get(aid, lambda s: (0, 1))(state)
        out.append({"id": aid, "title": title, "desc": desc, "earned": earned.get(aid),
                    "done": aid in earned or have >= need, "have": max(0, min(have, need)), "need": need})
    for lvl in (2, 3, 4):
        aid, name, gate = "level_%d" % lvl, scoring.LEVELS[lvl], scoring.GATES[lvl]["score"]
        done = aid in earned or level >= lvl
        out.append({"id": aid, "title": "Reached %s" % name, "desc": "Your AI Fluency level went up to %s." % name,
                    "earned": earned.get(aid), "done": done,
                    "have": gate if done else max(0, min(score or 0, gate)), "need": gate})
    return out


def build(events=None, state=None, now=None):
    """Everything the dashboard page shows, as plain data."""
    state = state or store.load_state()
    now = now or store.now()
    events = sorted(events if events is not None else store.read_events(), key=lambda e: e.get("ts", 0))
    prompts = [e for e in events if e.get("type") == "prompt"]
    gens = _gens(events, state.get("gens"))
    level = state.get("level", 1)
    streak = game.streak_status(state, now)

    data = {
        "generated": int(now),
        "generated_label": time.strftime("%b %d, %Y at %H:%M", time.localtime(now)).replace(" 0", " "),
        "current": {
            "level": level,
            "level_name": scoring.LEVELS.get(level, "Beginner"),
            "streak": streak["count"],
            "best_streak": streak["best"],
            "streak_today": streak["today"],
            "score": None,
        },
        "gates": {scoring.LEVELS[lvl]: g["score"] for lvl, g in sorted(scoring.GATES.items())},
        "gates_full": {str(lvl): dict(g, name=scoring.LEVELS[lvl]) for lvl, g in scoring.GATES.items()},
        "habits": [{"key": k, "name": n, "help": h} for k, n, h in HABITS],
        "issue_names": HABIT_GAPS,
        "gap_info": gap_info(),
        "achievements": achievements(state, level, None),
        "needs": [],
        "rows": [],
    }
    if not prompts:
        data["empty"] = True
        return data

    days = _days_between(_day(prompts[0]["ts"]), max(_day(now), _day(events[-1]["ts"])))
    rows = {d: _empty_row(d) for d in days}

    for e in events:
        row = rows.get(_day(e.get("ts", 0)))
        if row is None:
            continue
        t = e.get("type")
        if t == "prompt":
            row["prompts"] += 1
            if e.get("kind") == "new":
                row["new"] += 1
                row["ctx_sum"] += e.get("context", 0.0)
                row["ctx_n"] += 1
                row["prec_sum"] += e.get("precision", 0.0)
                row["prec_n"] += 1
                row["verify"] += 1 if e.get("verify") else 0
            if e.get("feature") is not None:
                row["feat_n"] += 1
                row["feat_yes"] += 1 if e.get("feature") == 1.0 else 0
            if game.is_good_habit({"kind": e.get("kind"), "context": e.get("context", 0.0)}):
                row["good_day"] = True
            for trig in e.get("triggers") or ():
                if trig in HABIT_GAPS:
                    row["issues"][trig] = row["issues"].get(trig, 0) + 1
        elif t == "coach":
            row["coached"] += 1
        elif t == "offer_accepted":
            row["taken"] += 1
        elif t == "offer_declined":
            row["declined"] += 1
        elif t == "offer_misfit":
            row["misfit"] += 1
        elif t == "gen":
            row["docs"] += 1
    for g in gens:
        if g.get("resolved") and g.get("resolved_ts"):
            row = rows.get(_day(g["resolved_ts"]))
            if row is not None:
                row["docs_done"] += 1
                row["docs_revised"] += 1 if g.get("revisions", 0) > 0 else 0

    # The AI Fluency score as it stood at the end of each day (same rules as /score).
    replay_level, i = 1, 0
    upto, last_m = [], None
    for day in days:
        end = _day_end(day)
        while i < len(events) and events[i].get("ts", 0) < end:
            upto.append(events[i])
            i += 1
        done = [dict(g, resolved=True) for g in gens if g.get("resolved") and (g.get("resolved_ts") or 0) < end]
        last_m = scoring.compute_metrics(upto, done)
        replay_level = scoring.resolve_level(last_m, replay_level)
        rows[day]["score"] = last_m["score"]
        rows[day]["level"] = replay_level

    data["rows"] = [rows[d] for d in days]
    score = data["rows"][-1]["score"]
    data["current"]["score"] = score
    data["needs"] = scoring.next_level_needs(last_m, level)
    data["achievements"] = achievements(state, level, score)
    data["first_day"], data["last_day"] = days[0], days[-1]
    return data


def render(data):
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return page.replace("/*__DATA__*/null", payload, 1)


def default_path():
    return os.path.join(store.home(), "dashboard.html")


def write(path=None, data=None, open_browser=True):
    """Write the dashboard file and (optionally) open it in the default browser."""
    path = path or default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    html = render(data if data is not None else build())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    os.replace(tmp, path)
    if open_browser:
        try:
            webbrowser.open(pathlib.Path(path).resolve().as_uri())
        except Exception:  # noqa: BLE001  (opening a browser is a convenience, never a failure)
            pass
    return path
