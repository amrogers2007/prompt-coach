"""Measure how accurately the trigger detectors spot teachable moments.

A labeled corpus (coach/evals/detector_corpus.jsonl) lists realistic prompts
and the triggers a careful human would expect. For every detector we count
true positives, false positives (coaching that wouldn't fit) and misses.
Precision matters most: a wrong coaching moment costs the user's trust, a
missed one costs nothing.
"""

import json
import os

from . import signals


def default_corpus():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "evals", "detector_corpus.jsonl")


def load_corpus(path=None):
    rows = []
    with open(path or default_corpus(), encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith("//"):
                row = json.loads(line)
                row["line"] = n
                rows.append(row)
    return rows


def run(rows):
    """{'detectors': {name: {tp, fp, fn, precision, recall}}, 'overall': {...},
    'errors': [(line, prompt, false_positives, misses)]}"""
    stats = {name: {"tp": 0, "fp": 0, "fn": 0} for name in signals.DETECTORS}
    errors = []
    for row in rows:
        got = set(signals.analyze_prompt(row["prompt"])["triggers"])
        want = set(row["expect"])
        for name in stats:
            if name in got and name in want:
                stats[name]["tp"] += 1
            elif name in got:
                stats[name]["fp"] += 1
            elif name in want:
                stats[name]["fn"] += 1
        if got != want:
            errors.append((row["line"], row["prompt"], sorted(got - want), sorted(want - got)))
    for s in stats.values():
        s["precision"] = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else None
        s["recall"] = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else None
    tp = sum(s["tp"] for s in stats.values())
    fp = sum(s["fp"] for s in stats.values())
    fn = sum(s["fn"] for s in stats.values())
    overall = {"tp": tp, "fp": fp, "fn": fn, "prompts": len(rows),
               "precision": tp / (tp + fp) if tp + fp else None,
               "recall": tp / (tp + fn) if tp + fn else None,
               "exact": sum(1 for _ in rows) - len(errors)}
    return {"detectors": stats, "overall": overall, "errors": errors}


def _pct(x):
    return "  -  " if x is None else "%4.0f%%" % (100 * x)


def render(result):
    o = result["overall"]
    lines = ["Detector accuracy on %d labeled prompts" % o["prompts"],
             "Overall precision %s, recall %s; %d of %d prompts exactly right" % (
                 _pct(o["precision"]).strip(), _pct(o["recall"]).strip(), o["exact"], o["prompts"]),
             "", "%-20s %5s %5s %4s %4s %4s" % ("detector", "prec", "recall", "tp", "fp", "miss")]
    for name, s in sorted(result["detectors"].items()):
        lines.append("%-20s %5s %5s %4d %4d %4d" % (name, _pct(s["precision"]), _pct(s["recall"]),
                                                   s["tp"], s["fp"], s["fn"]))
    if result["errors"]:
        lines += ["", "Disagreements (line: prompt -> wrongly fired / missed):"]
        for line, prompt, extra, missed in result["errors"]:
            lines.append("  %d: %s" % (line, prompt[:90]))
            if extra:
                lines.append("      fired but shouldn't: %s" % ", ".join(extra))
            if missed:
                lines.append("      missed: %s" % ", ".join(missed))
    return "\n".join(lines)
