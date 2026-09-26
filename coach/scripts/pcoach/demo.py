"""Seed a realistic sample profile: for screenshots, demos, and tests.

Deterministic (fixed seed) and writes only into PROMPT_COACH_HOME, so point that
at a scratch folder before running it:  PROMPT_COACH_HOME=/tmp/demo coach.py demo
"""

import random
import time

from . import game, scoring, store


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
