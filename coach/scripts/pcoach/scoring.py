"""The AI Fluency score and the four levels.

Design goals (from the product brief):
  * behavior-based: computed from what people actually do, not a quiz;
  * hard: the top levels need sustained habits, not one good day;
  * reversible: level is derived from a rolling window, so bad habits can
    lower it (with a small buffer so a single off day doesn't flip it);
  * vacation-proof: the window is the last N prompts, not the last N days.
"""

WINDOW_PROMPTS = 100
WINDOW_GENS = 12

WEIGHTS = {
    "context": 0.30,       # gave the AI something to work with
    "iteration": 0.30,     # treated generated documents as drafts and revised them
    "precision": 0.15,     # said what a good answer looks like
    "verification": 0.10,  # asked the AI to show its work / check itself
    "feature": 0.10,       # used files and edit-in-place instead of copy-paste
    "consistency": 0.05,   # showed up on multiple days
}

LEVELS = {1: "Beginner", 2: "Practitioner", 3: "Advanced", 4: "Expert"}

GATES = {
    2: {"score": 30, "scored": 8},
    3: {"score": 55, "scored": 30, "days": 5, "gens": 4},
    4: {"score": 78, "scored": 100, "days": 15, "gens": 10, "iter": 0.7, "clean": True},
}

SLACK_SCORE = 6      # points below a gate before a level is actually lost
SLACK_COUNT = 0.6    # fraction of activity gates that must still hold
SLACK_ITER = 0.15


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def gen_credit(gen):
    """How well was one generated document iterated on? 0..1.

    Two solid revisions = full credit. A vague revision ("make it better")
    counts for less than a specific one ("cut slide 3, lead with cost").
    """
    revs = gen.get("revisions", 0)
    vague = min(gen.get("vague_revs", 0), revs)
    return max(0.0, min(1.0, (revs - 0.4 * vague) / 2.0))


def compute_metrics(events, gens):
    prompts = [e for e in events if e.get("type") == "prompt"][-WINDOW_PROMPTS:]
    new = [p for p in prompts if p.get("kind") == "new"]

    comps = {}

    if len(new) >= 2:
        comps["context"] = (_mean(p["context"] for p in new), len(new))
        comps["precision"] = (_mean(p["precision"] for p in new), len(new))
        verify_rate = sum(1 for p in new if p.get("verify")) / float(len(new))
        comps["verification"] = (min(1.0, verify_rate / 0.3), len(new))

    feats = [p["feature"] for p in prompts if p.get("feature") is not None]
    if len(feats) >= 2:
        comps["feature"] = (_mean(feats), len(feats))

    resolved = [g for g in gens if g.get("resolved")][-WINDOW_GENS:]
    iter_rate = None
    if len(resolved) >= 2:
        iter_rate = _mean(gen_credit(g) for g in resolved)
        comps["iteration"] = (iter_rate, len(resolved))

    days = len({p.get("day") for p in prompts if p.get("day")})
    if prompts:
        comps["consistency"] = (min(1.0, days / 7.0), days)

    total_w = sum(WEIGHTS[k] for k in comps)
    if total_w > 0:
        raw = sum(WEIGHTS[k] * v for k, (v, _) in comps.items()) / total_w
    else:
        raw = 0.0

    recent = prompts[-20:]
    sensitive_recent = sum(1 for p in recent if p.get("sensitive"))
    penalty = min(10, 4 * sensitive_recent)
    score = max(0, min(100, int(round(raw * 100 - penalty))))

    scored_comps = {k: v for k, (v, n) in comps.items() if k != "consistency"}
    weakest = min(scored_comps, key=lambda k: (scored_comps[k], -WEIGHTS[k])) if scored_comps else None

    return {
        "score": score,
        "raw": round(raw * 100, 1),
        "penalty": penalty,
        "components": {k: {"value": round(v, 3), "n": n, "weight": WEIGHTS[k]} for k, (v, n) in comps.items()},
        "weakest": weakest,
        "stats": {
            "scored": len(prompts),
            "days": days,
            "gens": len(resolved),
            "iter": round(iter_rate, 3) if iter_rate is not None else None,
            "sensitive_recent": sensitive_recent,
        },
    }


def meets(level, m, slack=False):
    gate = GATES.get(level)
    if gate is None:
        return True
    s = m["stats"]
    need_score = gate["score"] - (SLACK_SCORE if slack else 0)
    if m["score"] < need_score:
        return False

    def count_ok(key, have):
        if key not in gate:
            return True
        need = gate[key] * (SLACK_COUNT if slack else 1)
        return have >= need

    if not count_ok("scored", s["scored"]):
        return False
    if not count_ok("days", s["days"]):
        return False
    if not count_ok("gens", s["gens"]):
        return False
    if "iter" in gate:
        need = gate["iter"] - (SLACK_ITER if slack else 0)
        if s["iter"] is None or s["iter"] < need:
            return False
    if gate.get("clean") and not slack and s["sensitive_recent"] > 0:
        return False
    return True


def earned_level(m):
    level = 1
    for n in (2, 3, 4):
        if meets(n, m):
            level = n
        else:
            break
    return level


def resolve_level(m, stored):
    """New level given metrics and the previously stored level.

    Rising needs the full gate. Falling needs to miss the gate by a margin
    (see SLACK_*), which is what makes it feel fair rather than jumpy.
    """
    earned = earned_level(m)
    if earned >= stored:
        return earned
    level = stored
    while level > earned and not meets(level, m, slack=True):
        level -= 1
    return max(level, earned)


def next_level_needs(m, level):
    """Plain-English list of what stands between the user and the next level."""
    nxt = level + 1
    gate = GATES.get(nxt)
    if gate is None:
        return []
    s = m["stats"]
    needs = []
    if m["score"] < gate["score"]:
        needs.append("Raise your AI Fluency score from %d to %d" % (m["score"], gate["score"]))
    if s["scored"] < gate.get("scored", 0):
        needs.append("Build a longer track record (%d of %d scored prompts)" % (s["scored"], gate["scored"]))
    if s["days"] < gate.get("days", 0):
        needs.append("Use it on more days (%d of %d)" % (s["days"], gate["days"]))
    if s["gens"] < gate.get("gens", 0):
        needs.append("Revise more AI-made documents (%d of %d)" % (s["gens"], gate["gens"]))
    if "iter" in gate and (s["iter"] is None or s["iter"] < gate["iter"]):
        have = 0 if s["iter"] is None else int(round(s["iter"] * 100))
        needs.append("Revise at least %d%% of documents you generate (now %d%%)" % (int(gate["iter"] * 100), have))
    if gate.get("clean") and s["sensitive_recent"] > 0:
        needs.append("Keep sensitive data out of prompts (%d recent flag%s)" % (
            s["sensitive_recent"], "" if s["sensitive_recent"] == 1 else "s"))
    return needs
