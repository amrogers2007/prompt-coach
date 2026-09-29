"""Seed a realistic sample profile: for screenshots, demos, and tests.

Deterministic (fixed seed) and writes only into PROMPT_COACH_HOME, so point that
at a scratch folder before running it:  PROMPT_COACH_HOME=/tmp/demo coach.py demo
"""

import random
import time

from . import game, library, scoring, store

# For the history demo: how often each habit gap shows up in a new request at the
# start (first number) and by the end (second) as the sample person improves.
GAP_TREND = {
    "no_audience": (0.55, 0.12), "no_purpose": (0.50, 0.16), "no_format": (0.45, 0.20),
    "vague_goal": (0.22, 0.05), "subjective": (0.25, 0.12), "factual_question": (0.18, 0.08),
    "calculations": (0.07, 0.05), "single_option": (0.10, 0.03), "multi_task": (0.08, 0.10),
}


def _clamp(v):
    return round(min(1.0, max(0.0, v)), 3)


def seed_history(weeks=10, seed_value=11, now=None):
    """A richer sample for the dashboard: about `weeks` weeks of someone who
    improves, with issue labels, coaching moments, offers and documents, all in the
    same event format the real coach writes."""
    rnd = random.Random(seed_value)
    store.reset()
    state = store.default_state()
    now = now or time.time()
    lesson_for = {}
    for e in library.load():
        for d in e["detect"]:
            lesson_for.setdefault(d, e)
    events, gens = [], []
    days = weeks * 7
    for d in range(days, 0, -1):
        day_ts = now - d * 86400
        if time.localtime(day_ts).tm_wday >= 5 or rnd.random() < 0.12:     # weekends and a few days off
            continue
        progress = 1 - d / float(days)
        for i in range(rnd.randint(2, 5) + (1 if progress > 0.5 else 0)):
            ts = day_ts + 9 * 3600 + i * 1800 + rnd.randint(0, 600)
            new = i % 2 == 0 or rnd.random() < 0.3
            triggers = sorted(t for t, (a, b) in GAP_TREND.items() if new and rnd.random() < a + (b - a) * progress)
            sensitive = ["confidential_marker"] if rnd.random() < 0.015 else []
            if sensitive:
                triggers.append("sensitive")
            events.append({
                "type": "prompt", "ts": ts, "day": store.day_of(ts), "session": "demo",
                "kind": "new" if new else "followup", "words": rnd.randint(8, 80),
                "context": _clamp(rnd.gauss(0.22 + 0.5 * progress, 0.12)) if new else 0.2,
                "precision": _clamp(rnd.gauss(0.18 + 0.45 * progress, 0.15)),
                "verify": rnd.random() < 0.05 + 0.3 * progress,
                "feature": 1.0 if rnd.random() < 0.10 + 0.35 * progress else (0.0 if rnd.random() < 0.08 else None),
                "sensitive": sensitive, "triggers": triggers,
            })
            entry = lesson_for.get(triggers[0]) if triggers else None
            if entry and rnd.random() < 0.45:
                events.append({"type": "coach", "ts": ts + 1, "reason": "cadence", "lesson": entry["id"],
                               "skill": entry["skill"], "detected": True, "triggers": [triggers[0]]})
                roll, take = rnd.random(), 0.25 + 0.35 * progress
                kind = ("offer_accepted" if roll < take else "offer_declined" if roll < take + 0.2
                        else "offer_misfit" if roll < take + 0.24 else None)
                if kind:
                    events.append({"type": kind, "lesson": entry["id"], "skill": entry["skill"], "ts": ts + 60})
        if rnd.random() < 0.5:
            gid, gts = "hist%d" % d, day_ts + 13 * 3600
            revs = 0 if rnd.random() > 0.2 + 0.6 * progress else rnd.choice([1, 2, 2])
            events.append({"type": "gen", "gen": gid, "kind": rnd.choice(["deck", "document", "PDF"]), "ts": gts})
            for k in range(revs):
                events.append({"type": "revision", "gen": gid, "ts": gts + 300 * (k + 1), "vague": False})
            events.append({"type": "gen_resolved", "gen": gid, "revisions": revs, "accepted_first_draft": revs == 0,
                           "ts": gts + 3600})
            gens.append({"id": gid, "key": gid, "kind": "document", "ts": gts, "revisions": revs, "vague_revs": 0,
                         "resolved": True, "resolved_ts": gts + 3600, "session": "demo"})

    events.sort(key=lambda e: e["ts"])
    for e in events:
        store.append_event(e)
    prompts = [e for e in events if e["type"] == "prompt"]
    state["gens"] = gens[-store.MAX_GENS:]
    state["totals"].update({
        "prompts": len(prompts),
        "revisions": sum(1 for e in events if e["type"] == "revision"),
        "rich_prompts": sum(1 for p in prompts if p["kind"] == "new" and p["context"] >= 0.7),
        "verifies": sum(1 for p in prompts if p["verify"]),
        "docs": len(gens),
        "coached": sum(1 for e in events if e["type"] == "coach"),
        "offers_accepted": sum(1 for e in events if e["type"] == "offer_accepted"),
    })
    state["xp"] = sum(game.xp_for_prompt(p) for p in prompts)
    state["streak"] = {"count": 4, "best": 11, "last_day": store.day_of(now - 86400)}
    level = 1
    for _ in range(4):      # climb through the levels the way the real coach would
        level = scoring.resolve_level(scoring.compute_metrics(events, gens), level)
    state["level"] = level
    for n in range(2, level + 1):
        state["achievements"]["level_%d" % n] = now - (level + 1 - n) * 14 * 86400
    game.check_achievements(state, now - 3 * 86400)
    store.save_state(state)
    return state


def seed(days=21, seed_value=7):
    rnd = random.Random(seed_value)
    store.reset()
    state = store.default_state()
    events = []
    now = time.time()
    gens = []

    for d in range(days, 0, -1):
        day_ts = now - d * 86400
        if time.localtime(day_ts).tm_wday >= 5:      # weekends off
            continue
        progress = 1 - d / float(days)                # improving over time
        for i in range(rnd.randint(2, 4)):
            ts = day_ts + 9 * 3600 + i * 2400
            new = i % 2 == 0
            ctx = min(1.0, max(0.0, rnd.gauss(0.25 + 0.55 * progress, 0.12))) if new else 0.2
            events.append({
                "type": "prompt", "ts": ts, "day": store.day_of(ts), "session": "demo",
                "kind": "new" if new else "followup", "words": rnd.randint(8, 60),
                "context": round(ctx, 3), "precision": round(min(1, max(0, rnd.gauss(0.2 + 0.5 * progress, 0.15))), 3),
                "verify": rnd.random() < 0.1 + 0.3 * progress,
                "feature": 1.0 if rnd.random() < 0.15 + 0.3 * progress else None, "sensitive": [],
            })
        if rnd.random() < 0.6:
            revs = 0 if rnd.random() > 0.25 + 0.6 * progress else rnd.choice([1, 2, 2])
            gid = "demo%d" % d
            gens.append({"id": gid, "key": gid, "kind": rnd.choice(["deck", "document", "PDF"]),
                         "ts": day_ts + 11 * 3600, "revisions": revs, "vague_revs": 0,
                         "resolved": True, "session": "demo"})
            for _ in range(revs):
                events.append({"type": "revision", "gen": gid, "ts": day_ts + 11 * 3600 + 300})

    for e in events:
        store_event = dict(e)
        store.append_event(store_event)

    state["gens"] = gens
    prompts = [e for e in events if e["type"] == "prompt"]
    state["totals"].update({
        "prompts": len(prompts),
        "revisions": sum(1 for e in events if e["type"] == "revision"),
        "rich_prompts": sum(1 for p in prompts if p["kind"] == "new" and p["context"] >= 0.7),
        "verifies": sum(1 for p in prompts if p["verify"]),
        "docs": len(gens),
    })
    state["xp"] = sum(game.xp_for_prompt(p) for p in prompts)
    state["streak"] = {"count": 6, "best": 9, "last_day": store.day_of(now - 86400)}
    m = scoring.compute_metrics(store.read_events(), gens)
    state["level"] = scoring.earned_level(m)
    for n in range(2, state["level"] + 1):
        state["achievements"]["level_%d" % n] = now
    game.check_achievements(state, now)
    store.save_state(state)
    return state
