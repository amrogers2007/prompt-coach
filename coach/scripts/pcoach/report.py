"""The scoreboard, the shareable summary, and the SVG badge.

The summary and the JSON export contain only aggregate numbers (level, score,
counts, streak). They never contain prompt text, document names, or anything
from the conversations.
"""

import json
import time

from . import game, scoring, store

COMPONENT_LABELS = {
    "context": "Context up front",
    "iteration": "Revising drafts",
    "precision": "Specific asks",
    "verification": "Checking the AI",
    "feature": "Right feature",
    "consistency": "Showing up",
}
LEVEL_COLORS = {1: "#6b7280", 2: "#2b59c3", 3: "#1f7a4d", 4: "#b7791f"}
BLOCKS = " ▁▂▃▄▅▆▇█"


def bar(value, width=12):
    filled = int(round(max(0.0, min(1.0, value)) * width))
    return "█" * filled + "░" * (width - filled)


def sparkline(counts):
    top = max(counts) if counts else 0
    if top == 0:
        return BLOCKS[1] * len(counts)
    return "".join(BLOCKS[max(1, int(round(c / top * 8)))] if c else BLOCKS[1] for c in counts)


def daily_counts(events, days=14):
    today = time.time()
    labels = [store.day_of(today - i * 86400) for i in range(days - 1, -1, -1)]
    counts = {d: 0 for d in labels}
    for e in events:
        if e.get("type") == "prompt" and e.get("day") in counts:
            counts[e["day"]] += 1
    return [counts[d] for d in labels]


def build(state=None, events=None):
    state = state or store.load_state()
    events = events if events is not None else store.read_events(tail_bytes=store.RECENT_BYTES)
    m = scoring.compute_metrics(events, state["gens"])
    level = scoring.resolve_level(m, state["level"])
    return {
        "generated_at": int(time.time()),
        "level": level,
        "level_name": scoring.LEVELS[level],
        "score": m["score"],
        "components": m["components"],
        "weakest": m["weakest"],
        "stats": m["stats"],
        "needs": scoring.next_level_needs(m, level),
        "streak": {"current": state["streak"]["count"], "best": state["streak"]["best"]},
        "xp": state["xp"],
        "achievements": sorted(state["achievements"], key=lambda k: state["achievements"][k]),
        "totals": state["totals"],
        "documents": {"generated": len(state["gens"]), "revised": sum(1 for g in state["gens"] if g.get("revisions", 0) > 0)},
        "daily": daily_counts(events),
        "paused": state["settings"].get("paused_until", 0) > time.time() or not state["settings"].get("enabled", True),
        "intensity": state["settings"].get("intensity", "normal"),
    }


def summary_sentence(r):
    bits = ["AI Fluency: %s (Level %d of 4), score %d/100" % (r["level_name"], r["level"], r["score"])]
    if r["streak"]["current"] >= 2:
        bits.append("%d-day streak" % r["streak"]["current"])
    it = r["components"].get("iteration")
    if it and r["stats"]["gens"] >= 2:
        bits.append("revises %d%% of the documents it generates" % int(round(it["value"] * 100)))
    return ", ".join(bits) + "."


def render_text(r):
    lines = []
    lines.append("# Your AI Fluency Score")
    lines.append("")
    lines.append("**%s** (Level %d of 4) · Score **%d / 100**" % (r["level_name"], r["level"], r["score"]))
    if r["stats"]["scored"] < 8:
        lines.append("")
        lines.append("_Provisional: your score firms up after about 8 prompts (%d so far)._" % r["stats"]["scored"])
    lines.append("")
    if r["level"] < 4:
        lines.append("To reach **%s**:" % scoring.LEVELS[r["level"] + 1])
        if r["needs"]:
            for n in r["needs"]:
                lines.append("- " + n)
        else:
            lines.append("- You meet every requirement. Keep it up and it will unlock on your next prompt.")
    else:
        lines.append("You're at the top level. Keep the habits going to hold it.")
    lines.append("")
    lines.append("## Your habits")
    lines.append("```")
    for key in ("context", "iteration", "precision", "verification", "feature", "consistency"):
        comp = r["components"].get(key)
        label = COMPONENT_LABELS[key].ljust(18)
        if comp is None:
            lines.append("%s %s  not enough data yet" % (label, "░" * 12))
        else:
            lines.append("%s %s  %3d%%" % (label, bar(comp["value"]), int(round(comp["value"] * 100))))
    lines.append("```")
    if r["weakest"]:
        lines.append("")
        lines.append("Best next step: **%s**." % COMPONENT_LABELS[r["weakest"]].lower())
    lines.append("")
    lines.append("## Progress")
    lines.append("- Streak: **%d** working day%s (best %d)" % (
        r["streak"]["current"], "" if r["streak"]["current"] == 1 else "s", r["streak"]["best"]))
    lines.append("- XP: **%d**" % r["xp"])
    lines.append("- Last 14 days: `%s`" % sparkline(r["daily"]))
    lines.append("- Documents generated: %d, revised at least once: %d" % (
        r["documents"]["generated"], r["documents"]["revised"]))
    if r["achievements"]:
        titles = []
        for a in r["achievements"]:
            if a.startswith("level_"):
                titles.append("Reached %s" % scoring.LEVELS[int(a.split("_")[1])])
            else:
                titles.append(game._TITLES.get(a, a))
        lines.append("- Achievements: " + ", ".join(titles))
    if r["paused"]:
        lines.append("- Coaching is currently **paused**.")
    lines.append("")
    lines.append("## Shareable summary")
    lines.append("> " + summary_sentence(r))
    lines.append(">")
    lines.append("> Based on %d prompts. Measured on this device by Prompt Coach; no prompt content is shared." % r["stats"]["scored"])
    return "\n".join(lines)


def badge_svg(r):
    color = LEVEL_COLORS.get(r["level"], "#2b59c3")
    right = "%s %d/4" % (r["level_name"], r["level"])
    lw, rw = 92, 24 + 7 * len(right)
    w = lw + rw
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="28" role="img" aria-label="AI Fluency: %s">'
        '<rect width="%d" height="28" rx="5" fill="#1f2430"/>'
        '<rect x="%d" width="%d" height="28" rx="5" fill="%s"/>'
        '<rect x="%d" width="8" height="28" fill="%s"/>'
        '<g fill="#ffffff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="12" text-anchor="middle">'
        '<text x="%d" y="18">AI Fluency</text><text x="%d" y="18" font-weight="bold">%s</text></g></svg>'
    ) % (w, right, w, lw, rw, color, lw, color, lw // 2, lw + rw // 2, right)


def write_shareables(r):
    home = store.home()
    import os
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "summary.md"), "w", encoding="utf-8") as f:
        f.write(render_text(r) + "\n")
    with open(os.path.join(home, "badge.svg"), "w", encoding="utf-8") as f:
        f.write(badge_svg(r))
    return os.path.join(home, "summary.md"), os.path.join(home, "badge.svg")


def export_json(r):
    """Aggregate-only export, suitable for a future team dashboard."""
    keep = ("generated_at", "level", "level_name", "score", "components", "stats", "streak",
            "xp", "achievements", "documents", "daily")
    return json.dumps({k: r[k] for k in keep}, indent=1)
