#!/usr/bin/env python3
"""Connect Prompt Coach to Claude desktop's regular chat (and Cowork), without an extension package.

Chat can't run the plugin's hooks, so there the coach is a small local helper that
Claude calls each message (scripts/coach_mcp.py). This script registers that helper
in Claude desktop's config file, pointing at this folder, so chat always runs the
latest code here: after `git pull` there is nothing to reinstall.

    python coach/scripts/setup_desktop.py --wait     recommended: run it from a terminal (not inside Claude),
                                                     then quit Claude; it connects the coach while Claude is
                                                     closed, reopens Claude and confirms the coach started
    python coach/scripts/setup_desktop.py            connect it now (only while Claude is fully closed)
    python coach/scripts/setup_desktop.py --check    show what is configured and test-launch the helper
    python coach/scripts/setup_desktop.py --remove   disconnect it

Claude must be fully closed when the config changes: a running Claude keeps its settings in
memory and writes them back every few seconds, erasing any edit made in the meantime. Closing
the window isn't enough (Claude keeps running in the system tray); use Quit.

What it takes care of:
  * Claude installed from the Microsoft Store / MSIX keeps its settings in a private copy
    of AppData; the config there is the one Claude reads, so that is the one edited.
  * The helper must be started with a real Python. The Microsoft Store Python is
    sandboxed and can't see other apps' files (it made the old desktop extension fail
    with "No such file or directory"), so an absolute path to a regular Python is used.
  * The config file is backed up before any change, and every other setting is kept.
  * An older "Prompt Coach" desktop extension is switched off so the two don't clash
    (use --keep-extension to leave it alone).
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "coach_mcp.py")
SERVER_NAME = "prompt-coach"


# --- where things are -------------------------------------------------------------------

def claude_dir():
    """Claude desktop's settings folder, as Claude itself sees it."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        packaged = sorted(glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude")))
        if packaged:
            return packaged[0]
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Claude")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Claude")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "Claude")


def is_store_python(path):
    return "windowsapps" in (path or "").lower()


def find_python():
    """A Python 3.9+ that Claude can launch. Prefers the one running this script."""
    candidates = [sys.executable]
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += sorted(glob.glob(os.path.join(local, "Programs", "Python", "Python3*", "python.exe")), reverse=True)
        candidates += sorted(glob.glob(r"C:\Program Files\Python3*\python.exe"), reverse=True)
        for launcher in ("py",):
            exe = shutil.which(launcher)
            if exe:
                try:
                    out = subprocess.run([exe, "-3", "-c", "import sys; print(sys.executable)"],
                                         capture_output=True, text=True, timeout=20).stdout.strip()
                    if out:
                        candidates.append(out)
                except (OSError, subprocess.SubprocessError):
                    pass
    for c in candidates:
        if c and os.path.isfile(c) and not is_store_python(c):
            return os.path.abspath(c)
    return None


# --- config file ---------------------------------------------------------------------------

def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig") as f:
        text = f.read().strip()
    return json.loads(text) if text else {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-prompt-coach"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def backup(path):
    if not os.path.exists(path):
        return None
    dest = "%s.bak-prompt-coach-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, dest)
    return dest


def server_entry(python):
    return {"command": python, "args": [SERVER_SCRIPT]}


def old_extensions(cdir):
    """Settings files of installed 'prompt-coach' desktop extensions."""
    return sorted(glob.glob(os.path.join(cdir, "Claude Extensions Settings", "*prompt-coach*.json")))


def set_extension_enabled(settings_path, enabled):
    data = read_json(settings_path)
    if data.get("isEnabled", True) == enabled:
        return False
    backup(settings_path)
    data["isEnabled"] = enabled
    write_json(settings_path, data)
    return True


# --- test launch -------------------------------------------------------------------------------

def test_launch(entry, timeout=60):
    """Start the helper exactly as Claude will and do the MCP handshake plus one
    coaching turn, using a throwaway data folder so the real profile is untouched.
    Returns (ok, detail)."""
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, PROMPT_COACH_HOME=home)
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "coach_start", "arguments": {}}},
        ]
        try:
            p = subprocess.run([entry["command"]] + entry["args"], input="".join(json.dumps(m) + "\n" for m in msgs),
                               capture_output=True, text=True, env=env, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "could not start it: %s" % exc
        try:
            replies = {r["id"]: r for r in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
            tools = [t["name"] for t in replies[2]["result"]["tools"]]
            greeting = replies[3]["result"]["content"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError):
            return False, "it started but didn't answer properly. stderr: %s" % (p.stderr.strip()[-500:] or "(empty)")
        if "coach_turn" not in tools or "Prompt Coach" not in greeting:
            return False, "unexpected answer: %s" % greeting[:200]
        return True, "helper answered with %d tools (%s)" % (len(tools), ", ".join(tools))


# --- the Claude app itself ----------------------------------------------------------------------

def _is_desktop_path(path):
    """The Claude desktop app (Microsoft Store/MSIX or classic install), not the Claude Code
    command-line tool, which is also called claude.exe."""
    p = (path or "").lower().replace("/", "\\")
    return "\\windowsapps\\claude_" in p or "\\anthropicclaude\\" in p


def desktop_running():
    try:
        if sys.platform == "win32":
            ps = "Get-Process -Name claude -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }"
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                 capture_output=True, text=True, timeout=30).stdout
            return any(_is_desktop_path(line.strip()) for line in out.splitlines())
        if sys.platform == "darwin":
            return subprocess.run(["pgrep", "-f", "Claude.app/Contents/MacOS/Claude"],
                                  capture_output=True).returncode == 0
        return subprocess.run(["pgrep", "-if", "claude-desktop"], capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def relaunch():
    """Open Claude again. Returns True if it was asked to start."""
    try:
        if sys.platform == "win32":
            ps = "(Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | Select-Object -First 1).AppID"
            app_id = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                    capture_output=True, text=True, timeout=30).stdout.strip()
            if app_id:
                subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app_id])
                return True
            classic = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AnthropicClaude", "claude.exe")
            if os.path.exists(classic):
                subprocess.Popen([classic])
                return True
            return False
        if sys.platform == "darwin":
            return subprocess.run(["open", "-a", "Claude"]).returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def log_dir():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Claude", "logs")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/Claude")
    return os.path.expanduser("~/.config/Claude/logs")


def startup_verdict(log_text):
    """What Claude's log for our server says about its latest start: 'ok', 'failed' or None."""
    starts = log_text.rsplit("Initializing server", 1)
    if len(starts) < 2:
        return None
    latest = starts[1]
    # Only signs that *our* process died count; Claude also logs unrelated errors here.
    if any(bad in latest for bad in ("closed unexpectedly", "can't open file", "Traceback", "No such file")):
        return "failed"
    if "Server started and connected successfully" in latest and "tools/list" in latest:
        return "ok"
    return None


def wait_and_apply(config_path, cdir, keep_extension=False, out=print, running=desktop_running,
                   reopen=relaunch, sleep=time.sleep, poll=2.0, timeout=1800, confirm_timeout=120,
                   read_log=None, reopen_app=True):
    """Wait for Claude to be fully closed, connect the coach, reopen Claude and confirm."""
    python = find_python()
    if not python:
        return install(config_path, cdir, out=out, next_steps=False)      # prints the Python advice
    ok, detail = test_launch(server_entry(python))
    if not ok:
        out("The coach helper didn't start with %s: %s\nNothing was changed." % (python, detail))
        return 1

    if running():
        out("Ready. Now quit Claude completely:\n"
            "  right-click the Claude icon in the system tray (bottom right, maybe under the ^ arrow) > Quit,\n"
            "  or in Claude's window use the menu (top left) > File > Exit.\n"
            "Closing the window is not enough: Claude keeps running in the background.\n"
            "Waiting for Claude to close...")
    waited, quiet = 0.0, 0
    while quiet < 2:                       # two quiet checks in a row: Claude is really gone
        if running():
            quiet = 0
            if waited and waited % 60 < poll:
                out("  ...Claude is still running. If you only closed its window, use Quit from the tray icon.")
            if waited >= timeout:
                out("Gave up waiting (Claude never fully closed). Nothing was changed.")
                return 1
        else:
            quiet += 1
        sleep(poll)
        waited += poll

    out("Claude is closed. Connecting Prompt Coach...")
    rc = install(config_path, cdir, keep_extension=keep_extension, python=python, out=out, next_steps=False)
    if rc or not reopen_app:
        if not rc:
            out("\nDone. Open Claude again and start a new chat.")
        return rc

    started_at = time.time()
    if not reopen():
        out("\nDone. Please open Claude again, then start a new chat.")
        return 0
    out("\nReopening Claude and checking that the coach starts (up to %d seconds)..." % confirm_timeout)
    read_log = read_log or (lambda: _read_text(os.path.join(log_dir(), "mcp-server-%s.log" % SERVER_NAME), started_at))
    waited = 0.0
    while waited < confirm_timeout:
        sleep(poll)
        waited += poll
        if SERVER_NAME not in read_json(config_path).get("mcpServers", {}):
            out("Problem: Claude removed the Prompt Coach entry from its config when it started. This version of\n"
                "Claude may not accept locally configured helpers; the desktop extension route is the fallback.")
            return 1
        verdict = startup_verdict(read_log() or "")
        if verdict == "ok":
            out("Success: Claude started the Prompt Coach helper.\n"
                "Start a NEW chat: it should open with an italic 'Prompt Coach:' greeting.\n"
                "When Claude asks to use a Prompt Coach tool, choose 'Always allow'.")
            return 0
        if verdict == "failed":
            out("Problem: Claude tried to start the helper and it failed. Details are in:\n  %s"
                % os.path.join(log_dir(), "mcp-server-%s.log" % SERVER_NAME))
            return 1
    out("Claude reopened with Prompt Coach connected in its config, but its log didn't confirm the start yet.\n"
        "Start a new chat and look for the 'Prompt Coach:' greeting; if it's missing, run this script with --check.")
    return 0


def _read_text(path, newer_than=0.0):
    try:
        if os.path.getmtime(path) < newer_than:
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# --- commands ----------------------------------------------------------------------------------

def install(config_path, cdir, keep_extension=False, python=None, out=print, next_steps=True):
    python = python or find_python()
    if not python:
        out("Couldn't find a regular Python 3.9+ (the Microsoft Store Python can't be used: it is sandboxed).\n"
            "Install Python from python.org (tick 'Add python.exe to PATH') and run this again.")
        return 1
    entry = server_entry(python)
    ok, detail = test_launch(entry)
    if not ok:
        out("The coach helper didn't start with %s: %s\nNothing was changed." % (python, detail))
        return 1

    data = read_json(config_path)
    servers = data.setdefault("mcpServers", {})
    if servers.get(SERVER_NAME) == entry:
        out("Prompt Coach is already connected in %s." % config_path)
    else:
        saved = backup(config_path)
        servers[SERVER_NAME] = entry
        write_json(config_path, data)
        out("Connected Prompt Coach to Claude desktop.\n  config: %s%s" % (
            config_path, ("\n  backup: %s" % saved) if saved else ""))
    out("  python: %s\n  helper: %s\n  check:  %s" % (python, SERVER_SCRIPT, detail))

    if not keep_extension:
        for settings in old_extensions(cdir):
            if set_extension_enabled(settings, False):
                out("Switched off the old Prompt Coach desktop extension (%s)." % os.path.basename(settings)[:-5])

    if not next_steps:
        return 0
    if desktop_running():
        out("\nWarning: Claude is running right now, and a running Claude overwrites this change within seconds.\n"
            "Run this instead from a terminal outside Claude, then quit Claude:  python %s --wait"
            % os.path.relpath(os.path.abspath(__file__)))
    out("\nNext:\n"
        "  1. Quit Claude completely (right-click its icon in the system tray > Quit) and open it again.\n"
        "  2. Start a new chat. Claude should open with an italic 'Prompt Coach:' greeting.\n"
        "  3. When Claude asks to use a Prompt Coach tool, choose 'Always allow'.\n"
        "  If there's no greeting: make sure the Prompt Coach skill is uploaded and on (Customize > Skills;\n"
        "  build it with: python coach/scripts/build_mcpb.py, file dist/prompt-coach-chat-skill.zip).")
    return 0


def remove(config_path, out=print):
    data = read_json(config_path)
    if SERVER_NAME not in data.get("mcpServers", {}):
        out("Prompt Coach isn't connected in %s; nothing to do." % config_path)
        return 0
    saved = backup(config_path)
    del data["mcpServers"][SERVER_NAME]
    if not data["mcpServers"]:
        del data["mcpServers"]
    write_json(config_path, data)
    out("Disconnected Prompt Coach (backup: %s). Quit and reopen Claude to finish." % saved)
    return 0


def check(config_path, cdir, out=print):
    data = read_json(config_path)
    entry = data.get("mcpServers", {}).get(SERVER_NAME)
    out("Claude settings folder: %s" % cdir)
    out("Config file: %s (%s)" % (config_path, "found" if os.path.exists(config_path) else "missing"))
    for settings in old_extensions(cdir):
        out("Old desktop extension: %s (%s)" % (os.path.basename(settings)[:-5],
                                                 "on" if read_json(settings).get("isEnabled", True) else "off"))
    if not entry:
        out("Prompt Coach: not connected. Run this script without options to connect it.")
        return 1
    out("Prompt Coach: connected -> %s %s" % (entry.get("command"), " ".join(entry.get("args", []))))
    if is_store_python(entry.get("command")):
        out("Problem: that is the Microsoft Store Python, which can't run the helper. Re-run this script.")
        return 1
    ok, detail = test_launch(entry)
    out("Test launch: %s (%s)" % ("OK" if ok else "FAILED", detail))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Connect Prompt Coach to Claude desktop chat.")
    ap.add_argument("--wait", action="store_true",
                    help="wait for Claude to be fully closed, connect the coach, reopen Claude and confirm")
    ap.add_argument("--no-reopen", action="store_true", help="with --wait: don't reopen Claude afterwards")
    ap.add_argument("--check", action="store_true", help="show the current setup and test-launch the helper")
    ap.add_argument("--remove", action="store_true", help="disconnect Prompt Coach from Claude desktop")
    ap.add_argument("--keep-extension", action="store_true", help="don't switch off an old Prompt Coach extension")
    ap.add_argument("--config", help="use this config file instead of Claude's (for testing)")
    args = ap.parse_args(argv)
    cdir = os.path.dirname(os.path.abspath(args.config)) if args.config else claude_dir()
    config_path = os.path.abspath(args.config) if args.config else os.path.join(cdir, "claude_desktop_config.json")
    if args.check:
        return check(config_path, cdir)
    if args.wait:
        return wait_and_apply(config_path, cdir, keep_extension=args.keep_extension, reopen_app=not args.no_reopen)
    if args.remove:
        return remove(config_path)
    return install(config_path, cdir, keep_extension=args.keep_extension)


if __name__ == "__main__":
    sys.exit(main())
