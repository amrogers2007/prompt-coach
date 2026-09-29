"""Is the coaching working? Leading and behavioral measures from the local event log.

Follows the business case's KPI hierarchy: count teachable moments, acceptance,
dismissals and misfits (a proxy for detection precision), then the behavioral
question that matters: after a trigger is coached, does it come back less
often? Randomized holdout moments (settings: experiment) give the comparison
group, so the difference isn't just people improving anyway.

Everything is computed from the signals already stored (trigger names, never
prompt text).
"""

from . import lessons, store

BEFORE = 20         # prompts before an issue's first moment
AFTER = 40          # prompts after it that are compared
MIN_AFTER = 10      # an issue counts as "measured" once this many prompts follow its first moment


def _prompts(events):
    return sorted((e for e in events if e.get("type") == "prompt" and "triggers" in e), key=lambda e: e["ts"])


def _rate(window, trigger):
    if not window:
        return None
    return sum(1 for p in window if trigger in p["triggers"]) / float(len(window))


def habit_change(events):
    """Per issue (trigger): how often it came up before its first coaching moment
    and in the AFTER prompts that followed, and which group it was in: 'coached',
    or 'holdout' when a pilot experiment held its coaching back. An issue keeps
    its group for good (see hooks._in_holdout), so the groups stay clean."""
    prompts = _prompts(events)
    first = {}
    for ev in sorted((e for e in events if e.get("type") in ("coach", "coach_holdout")), key=lambda e: e["ts"]):
        for t in ev.get("triggers") or ():
            first.setdefault(t, ev)
    out = {}
    for t, ev in first.items():
        before = [p for p in prompts if p["ts"] < ev["ts"]][-BEFORE:]
        after = [p for p in prompts if p["ts"] > ev["ts"]][:AFTER]
        if len(after) < MIN_AFTER:
            continue
        b, a = _rate(before, t), _rate(after, t)
        out[t] = {"group": "coached" if ev["type"] == "coach" else "holdout",
                  "before": b, "after": a, "change": (a - b) if b is not None else None,
                  "prompts_after": len(after)}
    return out


def compare(habit_rows):
    """How often issues came up after their first moment, coached vs held back.
    Takes the habit rows of one user or, for a pilot, of many users pooled.
    Negative 'effect' means coached issues came back less than uncoached ones.

    'After' rates are compared rather than before/after changes: an issue's first
    moment is, by construction, when it first shows up, so its 'before' rate is
    biased low (the per-issue change is shown for context only)."""
    groups = {"coached": [], "holdout": []}
    for row in habit_rows:
        if row.get("after") is not None:
            groups[row["group"]].append(row["after"])
    out = {g: {"issues": len(v), "mean_after": (sum(v) / len(v)) if v else None} for g, v in groups.items()}
    c, h = out["coached"]["mean_after"], out["holdout"]["mean_after"]
    out["effect"] = (c - h) if c is not None and h is not None else None
    return out


def pool(reports):
    """Combine the `insights --json` output of several pilot participants."""
    return compare([row for r in reports for row in r["habits"].values()])


def build(events=None):
    events = store.read_events() if events is None else events
    prompts = _prompts(events)
    counts = {k: 0 for k in ("coach", "coach_holdout", "offer_accepted", "offer_declined", "offer_misfit")}
    per_rec = {}
    for ev in events:
        typ = ev.get("type")
        if typ in counts:
            counts[typ] += 1
        lid = ev.get("lesson")
        if lid and typ in counts:
            per_rec.setdefault(lid, {k: 0 for k in counts})[typ] += 1
    shown = counts["coach"]
    habits = habit_change(events)
    detected_moments = sum(1 for p in prompts if p["triggers"])
    return {
        "prompts": sum(1 for e in events if e.get("type") == "prompt"),
        "teachable_moments": detected_moments,
        "shown": shown,
        "held_out": counts["coach_holdout"],
        "accepted": counts["offer_accepted"],
        "declined": counts["offer_declined"],
        "misfit": counts["offer_misfit"],
        "acceptance_rate": counts["offer_accepted"] / float(shown) if shown else None,
        "misfit_rate": counts["offer_misfit"] / float(shown) if shown else None,
        "recommendations": per_rec,
        "habits": habits,
        "comparison": compare(habits.values()),
    }


def _pct(x):
    return "-" if x is None else "%d%%" % round(100 * x)


def render(r):
    lines = ["# Is the coaching working?", ""]
    if not r["prompts"]:
        return "\n".join(lines + ["No prompts recorded yet."])
    lines += [
        "- Prompts scored: %d, with a teachable moment spotted in %d" % (r["prompts"], r["teachable_moments"]),
        "- Coaching shown: %d (plus %d held back for comparison)" % (r["shown"], r["held_out"]),
        "- Offers taken: %d (%s); declined: %d; 'didn't fit': %d (%s)" % (
            r["accepted"], _pct(r["acceptance_rate"]), r["declined"], r["misfit"], _pct(r["misfit_rate"])),
    ]
    if r["habits"]:
        lines += ["", "## Did it stick?",
                  "How often each issue came up in the %d prompts after it was first spotted. Lower is better." % AFTER,
                  "", "| Issue | Group | Came up afterwards |", "|---|---|---|"]
        for t, s in sorted(r["habits"].items()):
            lines.append("| %s | %s | %s |" % (
                t.replace("_", " "), "held back" if s["group"] == "holdout" else "coached", _pct(s["after"])))
        cmp_ = r["comparison"]
        if cmp_["effect"] is not None:
            lines += ["", "Coached issues came up %s of the time afterwards, held-back issues %s: a difference "
                      "of %+d pts. One person's numbers are noisy; pool several people's `insights --json` for a "
                      "pilot." % (_pct(cmp_["coached"]["mean_after"]), _pct(cmp_["holdout"]["mean_after"]),
                                  round(100 * cmp_["effect"]))]
    if r["recommendations"]:
        lines += ["", "## By recommendation", "", "| Recommendation | Shown | Taken | Declined | Didn't fit |",
                  "|---|---|---|---|---|"]
        for lid, c in sorted(r["recommendations"].items(), key=lambda kv: -kv[1]["coach"]):
            e = lessons.get(lid)
            lines.append("| %s | %d | %d | %d | %d |" % (e["title"] if e else lid, c["coach"], c["offer_accepted"],
                                                         c["offer_declined"], c["offer_misfit"]))
    return "\n".join(lines)
