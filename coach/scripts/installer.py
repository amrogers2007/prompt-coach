#!/usr/bin/env python3
"""What the Prompt Coach setup program does, as plain steps with no windows, so
each one can be tested against scratch folders.

The setup program (setup_app.py, built into PromptCoachSetup.exe) calls run();
the installed program's "uninstall" calls uninstall(). Nothing here needs Python
on the user's computer: the coach is installed as coach.exe.

What gets installed (Windows, for the current user only, no administrator rights):

    <install dir>\\coach.exe, coachw.exe, _internal\\    the coach itself
    <install dir>\\library\\recommendations.md          what the coach can recommend
    <install dir>\\marketplace\\                         the Claude Code plugin, calling coach.exe
    Claude desktop config: mcpServers["prompt-coach"]   -> chat and Cowork
    Claude Code: plugin prompt-coach@prompt-coach       -> the Code tab
    Start menu shortcuts and an entry in "Installed apps"

The user's scores live in ~/.prompt-coach and are never touched by setup.
"""

import ctypes
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

import setup_desktop

APP_NAME = "Prompt Coach"
APP_KEY = "PromptCoach"
SERVER_NAME = setup_desktop.SERVER_NAME
MARKETPLACE = "prompt-coach"
PLUGIN = "prompt-coach"
PLUGIN_ID = "%s@%s" % (PLUGIN, MARKETPLACE)
EXE_TOKEN = "__COACH_EXE__"
RUN_SH = 'sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"'
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\%s" % APP_KEY

# The one thing setup cannot do for the user: Claude's own instructions live in their account.
PREFERENCE_LINE = ("In every conversation, use my Prompt Coach tools without being asked: call coach_turn with my "
                   "message before you reply to each message I send, starting with the very first one, and follow "
                   "what it returns.")

OK, SKIPPED, FAILED = "ok", "skipped", "failed"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class Options:
    def __init__(self, **kw):
        self.payload = None            # folder or .zip holding the runtime (coach.exe ...) and plugin-template/
        self.install_dir = default_install_dir()
        self.claude_config = None      # claude_desktop_config.json; None = Claude's own
        self.claude_home = None        # Claude Code's settings folder (CLAUDE_CONFIG_DIR); None = its default
        self.claude_cli = None         # claude.exe; None = look for it
        self.chat = True               # connect the desktop app's chat and Cowork
        self.code = True               # install the Claude Code plugin (Code tab)
        self.shortcuts = True
        self.registry = True
        self.reopen = True             # open Claude again afterwards and confirm the helper started
        self.confirm_timeout = 120
        for k, v in kw.items():
            if not hasattr(self, k):
                raise TypeError("unknown option: %s" % k)
            setattr(self, k, v)

    @property
    def real_claude(self):
        """True when setup is changing the config Claude itself reads (not a test copy)."""
        return self.claude_config is None

    def config_path(self):
        return self.claude_config or os.path.join(setup_desktop.claude_dir(), "claude_desktop_config.json")


def default_install_dir():
    """The usual per-user place. Hooks need a path without spaces (see command_path): a
    user name with a space is fine when Windows has a short name for it; on the
    rare drive without short names, the shared ProgramData folder is used instead."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    usual = os.path.join(base, "Programs", APP_KEY)
    if " " in usual and " " in short_path(base):
        shared = os.environ.get("PROGRAMDATA")
        if shared and " " not in shared:
            return os.path.join(shared, APP_KEY)
    return usual


class Result:
    """What happened, step by step: [(step, status, detail)]."""

    def __init__(self, out=None):
        self.steps = []
        self.out = out or (lambda text: None)

    def add(self, step, status, detail=""):
        self.steps.append((step, status, detail))
        self.out("%s: %s%s" % (step, status, (" (%s)" % detail) if detail else ""))
        return status

    def status(self, step):
        for name, status, _detail in self.steps:
            if name == step:
                return status
        return None

    @property
    def ok(self):
        return not any(status == FAILED for _s, status, _d in self.steps)


# --- files -----------------------------------------------------------------------------------

def _rmtree(path, tries=6):
    for attempt in range(tries):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.unlink(path)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.3 * (attempt + 1))


def copy_runtime(payload, install_dir):
    """Put the coach's files in install_dir, replacing an older version."""
    if not payload or not os.path.exists(payload):
        raise FileNotFoundError("The setup files are missing (%s)." % payload)
    os.makedirs(install_dir, exist_ok=True)
    staging = os.path.join(install_dir, ".new")
    _rmtree(staging)
    try:
        if os.path.isdir(payload):
            shutil.copytree(payload, staging)
        else:
            with zipfile.ZipFile(payload) as z:
                z.extractall(staging)
    except (zipfile.BadZipFile, OSError) as exc:
        _rmtree(staging)
        if not os.listdir(install_dir):
            os.rmdir(install_dir)                       # nothing was installed: leave no empty folder behind
        if isinstance(exc, zipfile.BadZipFile):
            raise OSError("The setup file is damaged. Please download it again.")
        raise
    if not os.path.isfile(os.path.join(staging, "coach.exe")) and sys.platform == "win32":
        _rmtree(staging)
        raise FileNotFoundError("The setup files are incomplete: coach.exe is missing.")
    for name in os.listdir(install_dir):                 # the old version goes, the user's nothing (none lives here)
        if name != ".new":
            _rmtree(os.path.join(install_dir, name))
    for name in os.listdir(staging):
        os.replace(os.path.join(staging, name), os.path.join(install_dir, name))
    _rmtree(staging)
    return install_dir


def short_path(path):
    """Windows' short form of a path (no spaces), when the drive has one."""
    if sys.platform != "win32":
        return path
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)
        return buf.value if 0 < n < 1024 else path
    except (AttributeError, OSError):
        return path


def command_path(exe):
    """How hooks and skills name the program. Claude runs hook commands through a
    shell (Git Bash where it exists, PowerShell otherwise), and the only spelling
    both accept is a bare path with forward slashes and no spaces."""
    path = exe
    if " " in path:
        path = short_path(path)
    path = path.replace("\\", "/")
    return '"%s"' % path if " " in path else path


def make_plugin(install_dir, exe=None):
    """Write the Claude Code plugin (as a one-plugin marketplace folder) whose hooks
    and skills call the installed program instead of Python."""
    template = os.path.join(install_dir, "plugin-template")
    if not os.path.isdir(template):
        raise FileNotFoundError("The setup files are incomplete: the plugin is missing.")
    market = os.path.join(install_dir, "marketplace")
    _rmtree(market)
    plugin = os.path.join(market, "plugin")
    shutil.copytree(template, plugin)
    command = command_path(exe or os.path.join(install_dir, "coach.exe"))
    for root, _dirs, files in os.walk(plugin):
        for name in files:
            if not name.endswith((".md", ".json")):
                continue
            full = os.path.join(root, name)
            with open(full, encoding="utf-8") as f:
                text = f.read()
            if EXE_TOKEN in text:
                # Inside JSON the path sits in a string: quotes (spaces in the path) must be escaped.
                value = command.replace('"', '\\"') if name.endswith(".json") else command
                with open(full, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text.replace(EXE_TOKEN, value))
    os.makedirs(os.path.join(market, ".claude-plugin"), exist_ok=True)
    with open(os.path.join(market, ".claude-plugin", "marketplace.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"name": MARKETPLACE,
                   "description": "Prompt Coach: a coach that teaches people to use AI well.",
                   "owner": {"name": "Amanda Rogers"},
                   "plugins": [{"name": PLUGIN, "source": "./plugin",
                                "description": "An AI coach inside Claude: adaptive coaching questions, "
                                               "draft-revision nudges, and a local AI Fluency level."}]}, f, indent=2)
    return market


def template_text(text):
    """Turn a plugin file written for Python (sh run.sh ...) into its installed form."""
    return (text.replace(RUN_SH, EXE_TOKEN)
                .replace('sh \\"${CLAUDE_PLUGIN_ROOT}/scripts/run.sh\\"', EXE_TOKEN)
                .replace("Bash(sh *scripts/run.sh *)", "Bash(%s *)" % EXE_TOKEN)
                .replace("(most often: Python 3.9+ is not installed)", "(most often: Prompt Coach needs reinstalling)"))


# --- the Claude desktop app: chat and Cowork ---------------------------------------------------

def chat_entry(exe):
    return {"command": exe, "args": ["mcp"]}


def connect_chat(config_path, exe):
    """Register the helper in Claude desktop's config. Returns (changed, detail)."""
    entry = chat_entry(exe)
    ok, detail = setup_desktop.test_launch(entry)
    if not ok:
        raise RuntimeError("The coach didn't start: %s" % detail)
    data = setup_desktop.read_json(config_path)
    servers = data.setdefault("mcpServers", {})
    if servers.get(SERVER_NAME) == entry:
        return False, "already connected"
    saved = setup_desktop.backup(config_path)
    servers[SERVER_NAME] = entry
    setup_desktop.write_json(config_path, data)
    return True, ("settings backed up to %s" % os.path.basename(saved)) if saved else "connected"


def disconnect_chat(config_path, install_dir=None):
    """Remove the helper from Claude's config. With install_dir, only if it is ours."""
    try:
        data = setup_desktop.read_json(config_path)
    except (OSError, ValueError):
        return False
    entry = data.get("mcpServers", {}).get(SERVER_NAME)
    if not entry:
        return False
    if install_dir and not _inside(entry.get("command", ""), install_dir):
        return False                       # someone's own (developer) setup: leave it
    setup_desktop.backup(config_path)
    del data["mcpServers"][SERVER_NAME]
    if not data["mcpServers"]:
        del data["mcpServers"]
    setup_desktop.write_json(config_path, data)
    return True


def _inside(path, folder):
    try:
        a = os.path.normcase(os.path.abspath(path))
        b = os.path.normcase(os.path.abspath(folder))
        return os.path.commonpath([a, b]) == b
    except ValueError:
        return False


def claude_running():
    return setup_desktop.desktop_running()


def _stop_claude():
    """Really end the Claude desktop app's processes. Only ever reached from a
    setup or uninstall the user started; tests must pass their own `stop`."""
    if sys.platform != "win32":
        return
    ps = ("Get-Process -Name claude -ErrorAction SilentlyContinue | Where-Object { $_.Path -and "
          "($_.Path -like '*\\WindowsApps\\Claude_*' -or $_.Path -like '*\\AnthropicClaude\\*') } | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                       creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        pass


def close_claude(wait=30, running=None, sleep=time.sleep, stop=None):
    """Quit the Claude desktop app (the user agreed to this in the setup window)."""
    running = running or claude_running
    (stop or _stop_claude)()
    waited, quiet = 0.0, 0
    while waited <= wait:
        if running():
            quiet = 0
        else:
            quiet += 1
            if quiet >= 2:
                return True
        sleep(1.0)
        waited += 1.0
    return False


def confirm_started(config_path, started_at, timeout=120, sleep=time.sleep, read_log=None, poll=2.0):
    """After Claude reopens: did it start our helper? 'ok', 'failed', 'removed' or 'unknown'."""
    log = os.path.join(setup_desktop.log_dir(), "mcp-server-%s.log" % SERVER_NAME)
    read_log = read_log or (lambda: setup_desktop._read_text(log, started_at))
    waited = 0.0
    while waited < timeout:
        sleep(poll)
        waited += poll
        try:
            if SERVER_NAME not in setup_desktop.read_json(config_path).get("mcpServers", {}):
                return "removed"
        except (OSError, ValueError):
            pass
        verdict = setup_desktop.startup_verdict(read_log() or "")
        if verdict:
            return verdict
    return "unknown"


# --- Claude Code: the Code tab -------------------------------------------------------------------

def _version_of(path):
    """The version folder a bundled claude.exe sits under: claude-code/2.1.281/claude.exe,
    or, since Claude 2.1.29x, claude-code/2.1.299/<build id>/claude.exe."""
    folder = os.path.dirname(path)
    for _ in range(3):
        name = os.path.basename(folder)
        parts = name.split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts):
            return tuple(int(p) for p in parts)
        folder = os.path.dirname(folder)
    return ()


def find_claude_cli(roots=None):
    """The Claude Code program. The desktop app ships its own copy (not on PATH), one or
    two folders under claude-code/; the newest version wins."""
    found = shutil.which("claude")
    if found and not setup_desktop._is_desktop_path(found):
        return found
    if roots is None:
        roots = [setup_desktop.claude_dir(), os.path.join(os.environ.get("APPDATA", ""), "Claude")]
    copies = []
    for root in roots:
        for depth in ("*", os.path.join("*", "*")):
            copies += glob.glob(os.path.join(root, "claude-code", depth, "claude.exe"))
            copies += glob.glob(os.path.join(root, "claude-code", depth, "claude"))
    copies = [c for c in copies if _version_of(c)]
    return max(copies, key=_version_of) if copies else None


def code_home(claude_home=None):
    return claude_home or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def known_marketplace(claude_home=None):
    """How Claude Code knows our marketplace name, if at all: its 'source' dict."""
    path = os.path.join(code_home(claude_home), "plugins", "known_marketplaces.json")
    try:
        return (setup_desktop.read_json(path).get(MARKETPLACE) or {}).get("source")
    except (OSError, ValueError):
        return None


def plugin_installed(claude_home=None):
    path = os.path.join(code_home(claude_home), "plugins", "installed_plugins.json")
    try:
        entries = setup_desktop.read_json(path).get("plugins", {}).get(PLUGIN_ID) or []
    except (OSError, ValueError):
        return None
    return entries[0].get("version", "?") if entries else None


def _is_ours(source, install_dir):
    where = (source or {}).get("path") or (source or {}).get("directory") or ""
    return bool(where) and _inside(where, install_dir)


def _cli(cli, args, claude_home, timeout=180):
    env = dict(os.environ)
    if claude_home:
        env["CLAUDE_CONFIG_DIR"] = claude_home
    p = subprocess.run([cli] + args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=timeout, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def install_code_plugin(cli, market_dir, install_dir, claude_home=None):
    """Install (or update) the plugin through Claude Code's own commands.
    Returns (status, detail)."""
    source = known_marketplace(claude_home)
    if source and not _is_ours(source, install_dir):
        if plugin_installed(claude_home):
            return SKIPPED, "already installed another way (%s); left as it is" % (
                source.get("repo") or source.get("source") or "custom")
        _cli(cli, ["plugin", "marketplace", "remove", MARKETPLACE], claude_home)
    elif source:
        # Ours, from an earlier setup: start clean so the new version is the one that runs.
        _cli(cli, ["plugin", "uninstall", PLUGIN_ID], claude_home)
        _cli(cli, ["plugin", "marketplace", "remove", MARKETPLACE], claude_home)
    rc, text = _cli(cli, ["plugin", "marketplace", "add", market_dir], claude_home)
    if rc:
        return FAILED, _last_line(text)
    rc, text = _cli(cli, ["plugin", "install", PLUGIN_ID], claude_home)
    if rc:
        return FAILED, _last_line(text)
    version = plugin_installed(claude_home)
    if not version:
        return FAILED, "Claude Code did not record the plugin"
    return OK, "version %s" % version


def remove_code_plugin(cli, install_dir, claude_home=None):
    source = known_marketplace(claude_home)
    if not source or not _is_ours(source, install_dir):
        return False
    _cli(cli, ["plugin", "uninstall", PLUGIN_ID], claude_home)
    _cli(cli, ["plugin", "marketplace", "remove", MARKETPLACE], claude_home)
    return True


def _last_line(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return lines[-1][:300] if lines else "no details"


# --- Windows: shortcuts and "Installed apps" -----------------------------------------------------

def start_menu_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)


def make_shortcuts(install_dir, folder=None):
    folder = folder or start_menu_dir()
    os.makedirs(folder, exist_ok=True)
    exe = os.path.join(install_dir, "coachw.exe")
    links = [("My AI habits dashboard", "dashboard", "See how your AI habits are changing"),
             ("Uninstall Prompt Coach", "uninstall", "Remove Prompt Coach from this computer")]
    lines = ["$s = New-Object -ComObject WScript.Shell"]
    for name, arg, tip in links:
        lines += ["$l = $s.CreateShortcut('%s')" % os.path.join(folder, name + ".lnk").replace("'", "''"),
                  "$l.TargetPath = '%s'" % exe.replace("'", "''"),
                  "$l.Arguments = '%s'" % arg,
                  "$l.WorkingDirectory = '%s'" % install_dir.replace("'", "''"),
                  "$l.Description = '%s'" % tip,
                  "$l.Save()"]
    p = subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(lines)], capture_output=True, text=True,
                       timeout=60, creationflags=NO_WINDOW)
    made = [n for n, _a, _t in links if os.path.exists(os.path.join(folder, n + ".lnk"))]
    if len(made) != len(links):
        raise RuntimeError("shortcuts were not created: %s" % _last_line(p.stderr))
    return folder


def register_app(install_dir, version):
    import winreg
    exe = os.path.join(install_dir, "coachw.exe")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in (("DisplayName", APP_NAME), ("DisplayVersion", version), ("Publisher", "Amanda Rogers"),
                            ("InstallLocation", install_dir), ("DisplayIcon", exe),
                            ("UninstallString", '"%s" uninstall' % exe),
                            ("URLInfoAbout", "https://github.com/amrogers2007/prompt-coach")):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", _size_kb(install_dir))):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def unregister_app():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def _size_kb(folder):
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total // 1024


# --- the whole thing -------------------------------------------------------------------------------

def version_of(install_dir):
    try:
        with open(os.path.join(install_dir, "marketplace", "plugin", ".claude-plugin", "plugin.json"),
                  encoding="utf-8") as f:
            return json.load(f).get("version", "?")
    except (OSError, ValueError):
        return "?"


def run(opts, out=None, close=None, relaunch=None):
    """Install everything. `close()` is asked to get Claude closed when it is
    running (returns True once it is); without it, a running Claude stops setup."""
    r = Result(out)
    exe = os.path.join(opts.install_dir, "coach.exe")

    if opts.real_claude and opts.chat and claude_running():
        if not (close and close()):
            r.add("Close Claude", FAILED, "Claude is still running. Quit it from the tray icon and run setup again")
            return r
        r.add("Close Claude", OK)

    try:
        copy_runtime(opts.payload, opts.install_dir)
        market = make_plugin(opts.install_dir, exe)
        r.add("Install the coach", OK, opts.install_dir)
    except PermissionError:
        r.add("Install the coach", FAILED, "files are in use. Close Claude completely and run setup again")
        return r
    except (OSError, zipfile.BadZipFile) as exc:
        r.add("Install the coach", FAILED, str(exc))
        return r

    if opts.chat:
        try:
            _changed, detail = connect_chat(opts.config_path(), exe)
            r.add("Connect Claude chat and Cowork", OK, detail)
        except (OSError, ValueError, RuntimeError) as exc:
            r.add("Connect Claude chat and Cowork", FAILED, str(exc))

    if opts.code:
        cli = opts.claude_cli or find_claude_cli()
        if not cli:
            r.add("Add to the Code tab", SKIPPED, "Claude Code isn't on this computer yet; chat and Cowork still work")
        else:
            try:
                status, detail = install_code_plugin(cli, market, opts.install_dir, opts.claude_home)
            except (OSError, subprocess.SubprocessError) as exc:
                status, detail = FAILED, str(exc)
            r.add("Add to the Code tab", status, detail)

    if opts.shortcuts:
        try:
            make_shortcuts(opts.install_dir)
            r.add("Start menu shortcuts", OK)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            r.add("Start menu shortcuts", SKIPPED, str(exc))       # a convenience, not a failure
    if opts.registry and sys.platform == "win32":
        try:
            register_app(opts.install_dir, version_of(opts.install_dir))
            r.add("Add to Installed apps", OK)
        except OSError as exc:
            r.add("Add to Installed apps", SKIPPED, str(exc))

    if opts.real_claude and opts.chat and opts.reopen and r.status("Connect Claude chat and Cowork") == OK:
        started = time.time()
        if (relaunch or setup_desktop.relaunch)():
            verdict = confirm_started(opts.config_path(), started, opts.confirm_timeout)
            if verdict == "ok":
                r.add("Check that Claude started the coach", OK)
            elif verdict == "unknown":
                r.add("Check that Claude started the coach", SKIPPED,
                      "Claude reopened; start a new chat and look for the Prompt Coach greeting")
            else:
                r.add("Check that Claude started the coach", FAILED,
                      "Claude removed the coach from its settings" if verdict == "removed"
                      else "Claude could not start the coach")
        else:
            r.add("Reopen Claude", SKIPPED, "please open Claude yourself")
    return r


def uninstall(opts, out=None, close=None, delete_data=False):
    """Undo run(). The user's scores stay unless delete_data."""
    r = Result(out)
    if opts.real_claude and claude_running():
        if not (close and close()):
            r.add("Close Claude", FAILED, "Claude is still running. Quit it from the tray icon and try again")
            return r
        r.add("Close Claude", OK)
    try:
        gone = disconnect_chat(opts.config_path(), opts.install_dir)
        r.add("Disconnect Claude chat and Cowork", OK if gone else SKIPPED, "" if gone else "was not connected")
    except (OSError, ValueError) as exc:
        r.add("Disconnect Claude chat and Cowork", FAILED, str(exc))
    cli = opts.claude_cli or find_claude_cli()
    try:
        gone = bool(cli) and remove_code_plugin(cli, opts.install_dir, opts.claude_home)
        r.add("Remove from the Code tab", OK if gone else SKIPPED, "" if gone else "was not installed by setup")
    except (OSError, subprocess.SubprocessError) as exc:
        r.add("Remove from the Code tab", FAILED, str(exc))
    if opts.shortcuts:
        _rmtree_quiet(start_menu_dir())
    if opts.registry and sys.platform == "win32":
        unregister_app()
    if delete_data:
        from pcoach import store
        _rmtree_quiet(store.home())
        r.add("Delete scores and history", OK)
    r.add("Remove the coach's files", *remove_files(opts.install_dir))
    return r


def _rmtree_quiet(path):
    try:
        _rmtree(path, tries=2)
    except OSError:
        pass


def remove_files(install_dir):
    """Delete the install folder. The program doing the deleting may live in it
    (Windows won't delete a running program), so what is left is removed by a
    short command that runs after this program has ended."""
    if not os.path.isdir(install_dir):
        return SKIPPED, "already gone"
    running_here = getattr(sys, "frozen", False) and _inside(sys.executable, install_dir)
    if not running_here:
        try:
            _rmtree(install_dir, tries=3)
            return OK, ""
        except OSError as exc:
            return FAILED, str(exc)
    # One string, not a list: Python's list quoting would mangle the quotes cmd needs around the path.
    # (/s makes cmd strip only the outer pair.) The wait lets this program end first.
    command = 'cmd /s /c "ping -n 4 127.0.0.1 >nul & rmdir /s /q "%s""' % install_dir
    subprocess.Popen(command, cwd=os.path.expanduser("~"), close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=NO_WINDOW | 0x00000200)          # own process group: outlives this program
    return OK, "finishing in a few seconds"


# --- the installed program's own "uninstall" (message boxes; no window toolkit needed) ------------------

def _box(text, title=APP_NAME, flags=0):
    try:
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x00010000)     # foreground
    except (AttributeError, OSError):
        print(text)
        return 0


def uninstall_interactive(argv=()):
    YESNO, QUESTION, INFO, WARNING, YES = 0x04, 0x20, 0x40, 0x30, 6
    install_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) \
        else default_install_dir()
    opts = Options(install_dir=install_dir)
    argv = list(argv)
    for flag, name in (("--claude-config", "claude_config"), ("--claude-home", "claude_home")):   # for tests
        if flag in argv and argv.index(flag) + 1 < len(argv):
            setattr(opts, name, os.path.abspath(argv[argv.index(flag) + 1]))
    opts.shortcuts = "--no-shortcuts" not in argv
    opts.registry = "--no-registry" not in argv
    silent = "--silent" in argv
    if not silent and _box("Remove Prompt Coach from this computer?\n\nYour scores and history are kept, so you "
                           "can pick up where you left off if you install it again.", flags=YESNO | QUESTION) != YES:
        return 0

    def close():
        if not silent and _box("Claude needs to be closed to finish.\n\nClose Claude now? Your chats are saved.",
                               flags=YESNO | QUESTION) != YES:
            return False
        return close_claude()

    r = uninstall(opts, close=close)
    if not silent:
        if r.ok:
            _box("Prompt Coach was removed. You can open Claude again.", flags=INFO)
        else:
            _box("Prompt Coach could not be removed completely:\n\n%s"
                 % "\n".join("%s: %s" % (s, d) for s, st, d in r.steps if st == FAILED), flags=WARNING)
    return 0 if r.ok else 1
