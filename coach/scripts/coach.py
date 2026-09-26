#!/usr/bin/env python3
"""Prompt Coach command-line entry point.

Hook subcommands (read Claude Code's hook JSON on stdin, print hook JSON):
    session | prompt | tool
User subcommands:
    score [--json]      the scoreboard (also writes summary.md + badge.svg)
    settings ...        pause / resume / intensity / status / reset / export
    doctor              check that everything works on this machine
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
        print("Unknown setting. Try: status | pause [2h] | resume | off | intensity light|normal|frequent | export | reset --yes")
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
    table = {"score": cmd_score, "settings": cmd_settings, "doctor": cmd_doctor, "demo": cmd_demo}
    if cmd not in table:
        print(__doc__)
        return 1
    return table[cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
