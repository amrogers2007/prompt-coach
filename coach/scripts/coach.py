#!/usr/bin/env python3
"""Prompt Coach command-line entry point.

Hook subcommands (read Claude Code's hook JSON on stdin, print hook JSON):
    session | prompt | tool
User subcommands:
    score [--json]      the scoreboard (also writes summary.md + badge.svg)
    settings ...        pause / resume / intensity / status / reset / export
    doctor              check that everything works on this machine
    library             check the recommendation library file and summarize it
    eval [corpus]       measure trigger-detector accuracy on the labeled prompt corpus
    insights [--json]   is the coaching working? acceptance, misfits, and habit change
    dashboard [--demo]  your AI habits over time, as a page in your browser (--no-open, --out PATH)
    demo                write a sample profile (into PROMPT_COACH_HOME) for screenshots

Hook subcommands ALWAYS exit 0 and stay quiet on any error: a coaching tool
must never break someone's AI session.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcoach import hooks, report, scoring, store  # noqa: E402


def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def run_hook(name):
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        handler = {"session": hooks.handle_session, "prompt": hooks.handle_prompt,
                   "tool": hooks.handle_tool}[name]
        with store.lock():
            out = handler(payload)
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception as exc:  # noqa: BLE001  (deliberate: never break the session)
        store.log_error("hook:" + name, exc)
    return 0


def cmd_score(args):
    r = report.build()
    report.write_shareables(r)
    if "--json" in args:
        print(report.export_json(r))
    else:
        print(report.render_text(r))
        print("\n(Saved: %s and %s)" % (os.path.join(store.home(), "summary.md"),
                                       os.path.join(store.home(), "badge.svg")))
    return 0


def _parse_duration(text):
    """'2h', '30m', '1d', '3' (hours) -> seconds."""
    text = text.strip().lower()
    unit = 3600
    if text.endswith("m"):
        unit, text = 60, text[:-1]
    elif text.endswith("h"):
        text = text[:-1]
    elif text.endswith("d"):
        unit, text = 86400, text[:-1]
    return float(text) * unit


def cmd_settings(args):
    state = store.load_state()
    s = state["settings"]
    action = args[0].lower() if args else "status"

    if action == "pause":
        secs = _parse_duration(args[1]) if len(args) > 1 else 3600
        s["paused_until"] = time.time() + secs
        msg = "Coaching paused for %s." % (args[1] if len(args) > 1 else "1 hour")
    elif action == "resume":
        s["paused_until"] = 0
        s["enabled"] = True
        msg = "Coaching resumed."
    elif action == "off":
        s["enabled"] = False
        msg = "Coaching is off. Use 'resume' to turn it back on."
    elif action == "intensity":
        level = (args[1].lower() if len(args) > 1 else "")
        if level not in ("light", "normal", "frequent"):
            print("Usage: intensity light|normal|frequent")
            return 1
        s["intensity"] = level
        msg = "Coaching intensity set to %s." % level
    elif action == "toasts":
        how = (args[1].lower() if len(args) > 1 else "")
        if how not in ("auto", "chat", "system"):
            print("Usage: toasts auto|chat|system   (chat = Claude says status notes in its reply; system = shown by the app)")
            return 1
        s["toasts"] = how
        msg = "Status notes will be delivered via: %s." % how
    elif action == "experiment":
        # Pilot mode: hold back coaching on a random share of spotted moments, for comparison.
        try:
            pct = float((args[1] if len(args) > 1 else "").rstrip("%"))
        except ValueError:
            print("Usage: experiment <percent held back, 0-50>   e.g. experiment 20   (experiment 0 turns it off)")
            return 1
        if not 0 <= pct <= 50:
            print("Pick a share between 0 and 50 percent.")
            return 1
        s["holdout"] = pct / 100.0
        state["coach"]["arms"] = {}      # a new experiment starts with fresh random groups
        msg = ("Experiment on: %g%% of spotted coaching moments will be held back for comparison. "
               "See the results with: coach.py insights" % pct) if pct else "Experiment off."
    elif action in ("why", "mute", "unmute"):
        from pcoach import controls
        target = args[1] if len(args) > 1 else ""
        msg, changed = (controls.why(state) if action == "why" else
                        controls.mute(state, target) if action == "mute" else controls.unmute(state, target))
        if not changed:
            print(msg)
            return 0 if action == "why" else 1
    elif action == "reset":
        if "--yes" not in args:
            print("This deletes your score, streak, and history. Re-run with: reset --yes")
            return 1
        store.reset()
        print("Your Prompt Coach data was deleted.")
        return 0
    elif action == "export":
        r = report.build()
        print(report.export_json(r))
        return 0
    elif action == "status":
        paused = s.get("paused_until", 0) > time.time()
        print("Coaching: %s | intensity: %s | data: %s" % (
            "off" if not s.get("enabled", True) else ("paused" if paused else "on"),
            s.get("intensity", "normal"), store.home()))
        return 0
    else:
        print("Unknown setting. Try: status | pause [2h] | resume | off | intensity light|normal|frequent | toasts auto|chat|system | why | mute <id> | unmute <id|all> | experiment <percent> | export | reset --yes")
        return 1

    store.save_state(state)
    print(msg)
    return 0


def cmd_doctor(_args):
    ok = True
    print("Python: %s" % sys.version.split()[0])
    try:
        os.makedirs(store.home(), exist_ok=True)
        probe = os.path.join(store.home(), ".probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.unlink(probe)
        print("Data folder writable: %s" % store.home())
    except OSError as exc:
        ok = False
        print("Data folder NOT writable: %s (%s)" % (store.home(), exc))
    st = store.load_state()
    print("Saved profile: level %d, %d prompts recorded" % (st["level"], st["totals"]["prompts"]))
    err = os.path.join(store.home(), "errors.log")
    if os.path.exists(err):
        print("Recent hook errors (see %s):" % err)
        with open(err, encoding="utf-8") as f:
            for line in f.readlines()[-3:]:
                print("  " + line.rstrip())
        ok = False
    else:
        print("No hook errors logged.")
    print("Result: %s" % ("everything looks good" if ok else "needs attention"))
    return 0 if ok else 1


def cmd_library(_args):
    from pcoach import library, signals
    entries, problems = library.check(detectors=signals.DETECTORS)
    print("Recommendation library: %s" % library.default_path())
    print("%d recommendations" % len(entries))
    by_detect = {"ai": 0, "general": 0, "detector": 0}
    for e in entries:
        by_detect["ai" if "ai" in e["detect"] else "general" if "general" in e["detect"] else "detector"] += 1
    print("  %d spotted automatically, %d judged by the AI, %d everyday habits" % (
        by_detect["detector"], by_detect["ai"], by_detect["general"]))
    stages = []
    for e in entries:
        if e["stage"] not in stages:
            stages.append(e["stage"])
    for st in stages:
        print("  %-12s %d" % (st, sum(1 for e in entries if e["stage"] == st)))
    used = {d for e in entries for d in e["detect"]}
    print("Detectors you can use in 'detect:': %s" % ", ".join(sorted(signals.DETECTORS)))
    unused = sorted(set(signals.DETECTORS) - used)
    if unused:
        print("  (not used by any entry yet: %s)" % ", ".join(unused))
    if problems:
        print("\nProblems:")
        for p in problems:
            print("  - " + p)
        return 1
    print("\nNo problems found.")
    return 0


def cmd_dashboard(args):
    """Your AI habits over time, as a page in your browser (made on this computer)."""
    from pcoach import dashboard
    out = args[args.index("--out") + 1] if "--out" in args and args.index("--out") + 1 < len(args) else None
    open_it = "--no-open" not in args
    if "--demo" in args:
        import tempfile
        from pcoach import demo
        home = tempfile.mkdtemp(prefix="prompt-coach-demo-")
        old = os.environ.get("PROMPT_COACH_HOME")
        os.environ["PROMPT_COACH_HOME"] = home
        try:
            demo.seed_history()
            data = dashboard.build()
        finally:
            if old is None:
                os.environ.pop("PROMPT_COACH_HOME", None)
            else:
                os.environ["PROMPT_COACH_HOME"] = old
        path = dashboard.write(out or os.path.join(home, "dashboard.html"), data=data, open_browser=open_it)
        print("Sample dashboard with made-up data: %s" % path)
        return 0
    path = dashboard.write(out, open_browser=open_it)
    print("Your dashboard: %s" % path)
    return 0


def cmd_insights(args):
    from pcoach import insights
    r = insights.build()
    if "--json" in args:
        print(json.dumps(r, indent=2, default=str))
    else:
        print(insights.render(r))
    return 0


def cmd_eval(args):
    from pcoach import evaluate
    rows = evaluate.load_corpus(args[0] if args else None)
    result = evaluate.run(rows)
    print(evaluate.render(result))
    return 0


def cmd_demo(_args):
    from pcoach import demo
    demo.seed()
    print("Demo profile written to %s" % store.home())
    return 0


def main(argv):
    _utf8_stdout()
    if len(argv) < 2:
        print(__doc__)
        return 0
    cmd, args = argv[1], argv[2:]
    if cmd in ("session", "prompt", "tool"):
        return run_hook(cmd)
    table = {"score": cmd_score, "settings": cmd_settings, "doctor": cmd_doctor, "demo": cmd_demo,
             "library": cmd_library, "eval": cmd_eval,
             "insights": cmd_insights, "dashboard": cmd_dashboard}
    if cmd not in table:
        print(__doc__)
        return 1
    return table[cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
