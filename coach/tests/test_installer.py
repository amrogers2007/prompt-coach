"""The setup program's steps, run against scratch folders (never the real Claude
settings, never the real install folder).

Two layers:
  * Steps: every step with a stand-in for coach.exe and for Claude Code, on any computer.
  * RealBuild: the actual built program (build_installer.py) installed, driven through
    Claude Code, PowerShell and the chat protocol with no Python on the PATH, then removed.
    Skipped when the build or Claude Code isn't on this computer.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from helpers import RICH, SCRIPTS  # noqa: F401  (also puts scripts/ on sys.path)

import build_installer
import installer
import setup_app
import setup_desktop
from pcoach import __version__

WINDOWS = sys.platform == "win32"
BUILD = os.path.join(os.path.expanduser("~"), ".prompt-coach-build", "dist")
RUNTIME = os.path.join(BUILD, "runtime")
SETUP_EXE = os.path.join(BUILD, "PromptCoachSetup.exe")


def clipboard_text():
    """What is on the Windows clipboard right now, read by a different program (PowerShell)."""
    p = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True,
                       text=True, encoding="utf-8", timeout=30)
    return p.stdout.rstrip("\r\n")


def built_version():
    try:
        with open(os.path.join(RUNTIME, "plugin-template", ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return None


class FakeClaudeCode:
    """Stands in for `claude plugin ...`: keeps the same two files Claude Code keeps."""

    def __init__(self, home):
        self.home, self.calls, self.fail_on = home, [], None
        os.makedirs(os.path.join(home, "plugins"), exist_ok=True)

    def _file(self, name):
        return os.path.join(self.home, "plugins", name)

    def _load(self, name, default):
        try:
            with open(self._file(name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save(self, name, data):
        with open(self._file(name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def seed_github(self):
        self._save("known_marketplaces.json", {"prompt-coach": {"source": {"source": "github",
                                                                           "repo": "amrogers2007/prompt-coach"}}})
        self._save("installed_plugins.json", {"version": 2, "plugins": {
            installer.PLUGIN_ID: [{"scope": "user", "version": "0.4.1"}]}})

    def __call__(self, cli, args, claude_home, timeout=180):
        self.calls.append(" ".join(args))
        if self.fail_on and self.fail_on in " ".join(args):
            return 1, "Error: something went wrong\nfailed to do it"
        markets = self._load("known_marketplaces.json", {})
        plugins = self._load("installed_plugins.json", {"version": 2, "plugins": {}})
        if args[:3] == ["plugin", "marketplace", "add"]:
            with open(os.path.join(args[3], ".claude-plugin", "marketplace.json"), encoding="utf-8") as f:
                name = json.load(f)["name"]
            markets[name] = {"source": {"source": "directory", "path": args[3]}}
        elif args[:3] == ["plugin", "marketplace", "remove"]:
            markets.pop(args[3], None)
        elif args[:2] == ["plugin", "install"]:
            market = markets[args[2].split("@")[1]]["source"]["path"]
            with open(os.path.join(market, "plugin", ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
                version = json.load(f)["version"]
            plugins["plugins"][args[2]] = [{"scope": "user", "version": version}]
        elif args[:2] == ["plugin", "uninstall"]:
            plugins["plugins"].pop(args[2], None)
        self._save("known_marketplaces.json", markets)
        self._save("installed_plugins.json", plugins)
        return 0, "ok"


class StepsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pcoach-setup-")
        self.payload = os.path.join(self.tmp, "payload")
        os.makedirs(self.payload)
        for name in ("coach.exe", "coachw.exe"):
            with open(os.path.join(self.payload, name), "w") as f:
                f.write("stand-in")
        os.makedirs(os.path.join(self.payload, "_internal"))
        build_installer.write_template(os.path.join(self.payload, "plugin-template"))
        self.home = os.path.join(self.tmp, "claude-home")
        self.claude = FakeClaudeCode(self.home)
        self.config = os.path.join(self.tmp, "cfg", "claude_desktop_config.json")
        # A space in the path is the hard case on Windows (it has short names to fall back on).
        self.install_dir = os.path.join(self.tmp, "Install Dir" if WINDOWS else "install-dir")
        self._old = (installer._cli, setup_desktop.test_launch)
        self._old_stop = installer._stop_claude
        installer._stop_claude = self._never_stop       # a test must never close the real Claude app
        installer._cli = self.claude
        setup_desktop.test_launch = lambda entry, timeout=60: (True, "stand-in")
        self.said = []

    def tearDown(self):
        installer._cli, setup_desktop.test_launch = self._old
        installer._stop_claude = self._old_stop
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _never_stop():
        raise AssertionError("a test tried to close the real Claude app")

    def opts(self, **kw):
        base = dict(payload=self.payload, install_dir=self.install_dir, claude_config=self.config,
                    claude_home=self.home, claude_cli="claude-stand-in", shortcuts=False, registry=False)
        base.update(kw)
        return installer.Options(**base)

    def run_setup(self, **kw):
        return installer.run(self.opts(**kw), out=self.said.append)

    def config_data(self):
        with open(self.config, encoding="utf-8") as f:
            return json.load(f)


class Install(StepsCase):
    def test_a_fresh_install_does_every_step(self):
        r = self.run_setup()
        self.assertTrue(r.ok, r.steps)
        self.assertEqual([(s, st) for s, st, _d in r.steps],
                         [("Install the coach", "ok"), ("Connect Claude chat and Cowork", "ok"),
                          ("Add to the Code tab", "ok")])
        for name in ("coach.exe", "coachw.exe", "_internal", "marketplace", "plugin-template"):
            self.assertTrue(os.path.exists(os.path.join(self.install_dir, name)), name)
        self.assertEqual(self.config_data()["mcpServers"]["prompt-coach"],
                         {"command": os.path.join(self.install_dir, "coach.exe"), "args": ["mcp"]})
        self.assertEqual(installer.plugin_installed(self.home), __version__)

    def test_other_claude_settings_are_kept_and_backed_up(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump({"preferences": {"theme": "dark"}, "mcpServers": {"other": {"command": "x"}}}, f)
        self.run_setup()
        data = self.config_data()
        self.assertEqual(data["preferences"], {"theme": "dark"})
        self.assertEqual(data["mcpServers"]["other"], {"command": "x"})
        self.assertIn("prompt-coach", data["mcpServers"])
        backups = [n for n in os.listdir(os.path.dirname(self.config)) if ".bak-prompt-coach-" in n]
        self.assertEqual(len(backups), 1)

    def test_an_older_python_based_connection_is_replaced(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"prompt-coach": {"command": "python.exe", "args": ["coach_mcp.py"]}}}, f)
        self.run_setup()
        self.assertEqual(self.config_data()["mcpServers"]["prompt-coach"]["args"], ["mcp"])

    def test_running_it_again_is_an_upgrade_not_a_mess(self):
        self.run_setup()
        with open(os.path.join(self.install_dir, "old-file.txt"), "w") as f:
            f.write("from the previous version")
        r = self.run_setup()
        self.assertTrue(r.ok, r.steps)
        self.assertFalse(os.path.exists(os.path.join(self.install_dir, "old-file.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.install_dir, ".new")))
        self.assertEqual(list(self.config_data()["mcpServers"]), ["prompt-coach"])
        self.assertIn("plugin uninstall prompt-coach@prompt-coach", self.claude.calls)     # clean reinstall
        self.assertEqual(installer.plugin_installed(self.home), __version__)

    def test_the_payload_can_be_a_zip(self):
        packed = build_installer.zip_folder(self.payload, os.path.join(self.tmp, "payload.zip"))
        r = self.run_setup(payload=packed)
        self.assertTrue(r.ok, r.steps)
        self.assertTrue(os.path.exists(os.path.join(self.install_dir, "coach.exe")))

    def test_a_damaged_download_changes_nothing(self):
        bad = os.path.join(self.tmp, "bad.zip")
        with open(bad, "w") as f:
            f.write("not a zip")
        r = self.run_setup(payload=bad)
        self.assertFalse(r.ok)
        self.assertIn("download it again", r.steps[0][2])
        self.assertFalse(os.path.exists(self.install_dir))
        self.assertFalse(os.path.exists(self.config))
        self.assertEqual(self.claude.calls, [])

    def test_missing_setup_files_are_reported(self):
        r = self.run_setup(payload=os.path.join(self.tmp, "nope.zip"))
        self.assertFalse(r.ok)
        self.assertIn("missing", r.steps[0][2])

    def test_a_coach_that_does_not_start_is_never_connected(self):
        setup_desktop.test_launch = lambda entry, timeout=60: (False, "it crashed")
        r = self.run_setup()
        self.assertEqual(r.status("Connect Claude chat and Cowork"), "failed")
        self.assertFalse(os.path.exists(self.config))
        self.assertEqual(r.status("Add to the Code tab"), "ok")            # the rest still happens

    def test_no_claude_code_on_the_computer_is_not_a_failure(self):
        old = installer.find_claude_cli
        installer.find_claude_cli = lambda: None
        try:
            r = self.run_setup(claude_cli=None)
        finally:
            installer.find_claude_cli = old
        self.assertTrue(r.ok)
        self.assertEqual(r.status("Add to the Code tab"), "skipped")
        self.assertEqual(r.status("Connect Claude chat and Cowork"), "ok")

    def test_a_plugin_installed_from_github_is_left_alone(self):
        self.claude.seed_github()
        r = self.run_setup()
        self.assertTrue(r.ok)
        self.assertEqual(r.status("Add to the Code tab"), "skipped")
        self.assertEqual(self.claude.calls, [])
        self.assertEqual(installer.known_marketplace(self.home)["source"], "github")

    def test_claude_code_refusing_is_reported_in_plain_words(self):
        self.claude.fail_on = "plugin install"
        r = self.run_setup()
        self.assertFalse(r.ok)
        self.assertEqual([d for s, _st, d in r.steps if s == "Add to the Code tab"], ["failed to do it"])

    def test_chat_only_and_code_only(self):
        r = self.run_setup(code=False)
        self.assertEqual([s for s, _st, _d in r.steps], ["Install the coach", "Connect Claude chat and Cowork"])
        self.assertEqual(self.claude.calls, [])
        shutil.rmtree(self.install_dir)
        os.unlink(self.config)
        r = self.run_setup(chat=False)
        self.assertFalse(os.path.exists(self.config))
        self.assertEqual(r.status("Add to the Code tab"), "ok")

    def test_unknown_option_is_a_programming_error(self):
        with self.assertRaises(TypeError):
            installer.Options(instal_dir="typo")


class Plugin(StepsCase):
    def files(self):
        self.run_setup()
        out = {}
        plugin = os.path.join(self.install_dir, "marketplace", "plugin")
        for root, _dirs, names in os.walk(plugin):
            for name in names:
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    out[os.path.relpath(os.path.join(root, name), plugin).replace(os.sep, "/")] = f.read()
        return out

    def test_nothing_in_the_installed_plugin_needs_python_or_a_shell_script(self):
        files = self.files()
        self.assertIn(".claude-plugin/plugin.json", files)
        self.assertFalse([n for n in files if n.startswith(("scripts/", "tests/"))])
        for name, text in files.items():
            for word in ("run.sh", "__COACH_EXE__", "python", "CLAUDE_PLUGIN_ROOT"):
                self.assertNotIn(word, text, "%s mentions %s" % (name, word))

    def test_hooks_call_the_program_in_a_form_every_shell_accepts(self):
        hooks = json.loads(self.files()["hooks/hooks.json"])["hooks"]
        commands = [h["command"] for event in hooks.values() for group in event for h in group["hooks"]]
        self.assertEqual(len(commands), 3)
        for command, arg in zip(commands, ("session", "prompt", "tool")):
            path, last = command.rsplit(" ", 1)
            self.assertEqual(last, arg)
            self.assertNotIn("\\", path)               # Git Bash would eat backslashes
            if WINDOWS:
                self.assertNotIn(" ", path)            # "Install Dir" became its short name
                self.assertNotIn('"', path)            # PowerShell can't run a quoted string as a command
                self.assertTrue(os.path.exists(path), path)

    def test_every_skill_and_the_agent_were_carried_over(self):
        files = self.files()
        for name in ("skills/score/SKILL.md", "skills/dashboard/SKILL.md", "skills/settings/SKILL.md",
                     "skills/coach/SKILL.md", "skills/practice/SKILL.md", "agents/coach.md"):
            self.assertIn(name, files)
        self.assertIn("coach.exe dashboard", files["skills/dashboard/SKILL.md"])
        self.assertIn("coach.exe score", files["skills/score/SKILL.md"])
        self.assertRegex(files["skills/score/SKILL.md"], r"allowed-tools: Bash\(\S+coach\.exe \*\)")

    def test_marketplace_names_the_plugin(self):
        self.run_setup()
        with open(os.path.join(self.install_dir, "marketplace", ".claude-plugin", "marketplace.json"),
                  encoding="utf-8") as f:
            market = json.load(f)
        self.assertEqual(market["name"], "prompt-coach")
        self.assertEqual(market["plugins"][0]["source"], "./plugin")

    def test_command_path_spellings(self):
        self.assertEqual(installer.command_path(r"C:\Apps\PromptCoach\coach.exe"), "C:/Apps/PromptCoach/coach.exe")
        # No short name available (the file doesn't exist): quoted, which Git Bash accepts.
        self.assertEqual(installer.command_path(r"Q:\No Such Dir\coach.exe"), '"Q:/No Such Dir/coach.exe"')

    def test_template_text_rewrites_every_python_call(self):
        text = installer.template_text('run `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" score --json` now\n'
                                       "allowed-tools: Bash(sh *scripts/run.sh *)\n"
                                       '"command": "sh \\"${CLAUDE_PLUGIN_ROOT}/scripts/run.sh\\" prompt"')
        self.assertNotIn("run.sh", text)
        self.assertEqual(text.count("__COACH_EXE__"), 3)


class Uninstall(StepsCase):
    def test_everything_setup_did_is_undone(self):
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump({"preferences": {"theme": "dark"}, "mcpServers": {"other": {"command": "x"}}}, f)
        self.run_setup()
        r = installer.uninstall(self.opts(), out=self.said.append)
        self.assertTrue(r.ok, r.steps)
        self.assertEqual(self.config_data(), {"preferences": {"theme": "dark"}, "mcpServers": {"other": {"command": "x"}}})
        self.assertIsNone(installer.plugin_installed(self.home))
        self.assertIsNone(installer.known_marketplace(self.home))
        self.assertFalse(os.path.exists(self.install_dir))

    def test_scores_are_kept_unless_asked(self):
        data = os.path.join(self.tmp, "data")
        os.makedirs(data)
        with open(os.path.join(data, "state.json"), "w") as f:
            f.write("{}")
        old = os.environ.get("PROMPT_COACH_HOME")
        os.environ["PROMPT_COACH_HOME"] = data
        try:
            self.run_setup()
            installer.uninstall(self.opts())
            self.assertTrue(os.path.exists(os.path.join(data, "state.json")))
            self.run_setup()
            installer.uninstall(self.opts(), delete_data=True)
            self.assertFalse(os.path.exists(data))
        finally:
            if old is None:
                os.environ.pop("PROMPT_COACH_HOME", None)
            else:
                os.environ["PROMPT_COACH_HOME"] = old

    def test_a_developers_own_setup_is_not_removed(self):
        self.claude.seed_github()
        os.makedirs(os.path.dirname(self.config))
        mine = {"command": "python.exe", "args": ["C:/repo/coach_mcp.py"]}
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"prompt-coach": mine}}, f)
        os.makedirs(self.install_dir)
        r = installer.uninstall(self.opts())
        self.assertTrue(r.ok)
        self.assertEqual(self.config_data()["mcpServers"]["prompt-coach"], mine)
        self.assertEqual(installer.plugin_installed(self.home), "0.4.1")

    def test_uninstalling_twice_is_harmless(self):
        self.run_setup()
        installer.uninstall(self.opts())
        r = installer.uninstall(self.opts())
        self.assertTrue(r.ok, r.steps)


class ClaudeOpenOrClosed(StepsCase):
    """With the real config, Claude must be closed first (it rewrites its settings while open)."""

    def setUp(self):
        super().setUp()
        self._more = (installer.claude_running, setup_desktop.claude_dir, setup_desktop.relaunch,
                      installer.confirm_started)
        self.running = True
        self.reopened = []
        installer.claude_running = lambda: self.running
        setup_desktop.claude_dir = lambda: os.path.dirname(self.config)
        installer.confirm_started = lambda *a, **k: "ok"

    def tearDown(self):
        (installer.claude_running, setup_desktop.claude_dir, setup_desktop.relaunch,
         installer.confirm_started) = self._more
        super().tearDown()

    def real(self, **kw):
        return self.opts(claude_config=None, **kw)

    def reopen(self):
        self.reopened.append(True)
        return True

    def test_setup_stops_if_claude_stays_open(self):
        r = installer.run(self.real(), close=lambda: False)
        self.assertFalse(r.ok)
        self.assertEqual(r.steps[0][0], "Close Claude")
        self.assertFalse(os.path.exists(self.install_dir))
        self.assertFalse(os.path.exists(self.config))

    def test_setup_without_permission_to_close_changes_nothing(self):
        r = installer.run(self.real())
        self.assertFalse(r.ok)
        self.assertFalse(os.path.exists(self.config))

    def test_closes_installs_reopens_and_confirms(self):
        def close():
            self.running = False
            return True
        r = installer.run(self.real(), close=close, relaunch=self.reopen)
        self.assertTrue(r.ok, r.steps)
        self.assertEqual([s for s, _st, _d in r.steps][0], "Close Claude")
        self.assertEqual(r.status("Check that Claude started the coach"), "ok")
        self.assertEqual(self.reopened, [True])
        self.assertIn("prompt-coach", self.config_data()["mcpServers"])

    def test_claude_dropping_the_coach_is_reported(self):
        self.running = False
        installer.confirm_started = lambda *a, **k: "removed"
        r = installer.run(self.real(), relaunch=self.reopen)
        self.assertFalse(r.ok)
        self.assertIn("removed the coach", r.steps[-1][2])

    def test_no_confirmation_yet_is_not_a_failure(self):
        self.running = False
        installer.confirm_started = lambda *a, **k: "unknown"
        r = installer.run(self.real(), relaunch=self.reopen)
        self.assertTrue(r.ok)
        self.assertEqual(r.status("Check that Claude started the coach"), "skipped")

    def test_confirm_started_reads_claudes_log(self):
        installer.confirm_started = self._more[3]
        os.makedirs(os.path.dirname(self.config))
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"prompt-coach": {}}}, f)
        good = "Initializing server\nServer started and connected successfully\ntools/list\n"
        bad = "Initializing server\nServer transport closed unexpectedly\n"
        nap = lambda s: None  # noqa: E731
        self.assertEqual(installer.confirm_started(self.config, 0, 10, sleep=nap, read_log=lambda: good), "ok")
        self.assertEqual(installer.confirm_started(self.config, 0, 10, sleep=nap, read_log=lambda: bad), "failed")
        self.assertEqual(installer.confirm_started(self.config, 0, 10, sleep=nap, read_log=lambda: ""), "unknown")
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump({}, f)
        self.assertEqual(installer.confirm_started(self.config, 0, 10, sleep=nap, read_log=lambda: good), "removed")

    def test_close_claude_waits_until_it_is_really_gone(self):
        # `stop` is a stand-in: a test must never close the real Claude app.
        asked = []
        stop = lambda: asked.append(True)  # noqa: E731
        states = iter([True, True, False, False])
        self.assertTrue(installer.close_claude(wait=10, running=lambda: next(states), sleep=lambda s: None, stop=stop))
        self.assertFalse(installer.close_claude(wait=3, running=lambda: True, sleep=lambda s: None, stop=stop))
        self.assertEqual(asked, [True, True])


class SetupProgram(StepsCase):
    def test_silent_run_writes_a_log_and_returns_zero(self):
        log = os.path.join(self.tmp, "setup.log")
        rc = setup_app.main(["--silent", "--payload", self.payload, "--install-dir", self.install_dir,
                             "--claude-config", self.config, "--claude-home", self.home, "--claude-cli", "stand-in",
                             "--no-shortcuts", "--no-registry", "--log", log])
        self.assertEqual(rc, 0)
        with open(log, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Prompt Coach is installed", text)
        self.assertIn("Add to the Code tab: ok", text)

    def test_silent_failure_returns_one(self):
        rc = setup_app.main(["--silent", "--payload", os.path.join(self.tmp, "none.zip"), "--install-dir",
                             self.install_dir, "--claude-config", self.config, "--claude-home", self.home,
                             "--no-shortcuts", "--no-registry", "--log", os.path.join(self.tmp, "s.log")])
        self.assertEqual(rc, 1)

    def test_silent_uninstall(self):
        args = ["--silent", "--payload", self.payload, "--install-dir", self.install_dir, "--claude-config",
                self.config, "--claude-home", self.home, "--claude-cli", "stand-in", "--no-shortcuts",
                "--no-registry", "--log", os.path.join(self.tmp, "s.log")]
        self.assertEqual(setup_app.main(args), 0)
        self.assertEqual(setup_app.main(args + ["--uninstall"]), 0)
        self.assertFalse(os.path.exists(self.install_dir))

    def test_summary_is_plain_language(self):
        r = self.run_setup()
        head, lines = setup_app.summary(r)
        self.assertEqual(head, "Prompt Coach is installed")
        self.assertEqual(len(lines), 2)
        bad = installer.Result()
        bad.add("Install the coach", installer.FAILED, "files are in use")
        self.assertEqual(setup_app.summary(bad), ("Setup didn't finish", ["Install the coach: files are in use"]))

    def test_the_last_step_line_names_the_tool_claude_must_call(self):
        self.assertIn("coach_turn", installer.PREFERENCE_LINE)
        self.assertIn("very first", installer.PREFERENCE_LINE)

    @unittest.skipUnless(WINDOWS, "the window is a Windows program")
    def test_every_page_of_the_window_can_be_built(self):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "setup_app.py"), "--selftest-gui",
                            "--install-dir", self.install_dir, "--claude-config", self.config,
                            "--log", os.path.join(self.tmp, "gui.log")], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        # The window has closed. The line it copied must still be there to paste into Claude.
        self.assertEqual(clipboard_text(), installer.PREFERENCE_LINE)


@unittest.skipUnless(WINDOWS, "Windows only")
class WindowsBits(StepsCase):
    def test_start_menu_shortcuts(self):
        self.run_setup()
        folder = installer.make_shortcuts(self.install_dir, folder=os.path.join(self.tmp, "Start Menu"))
        self.assertEqual(sorted(os.listdir(folder)), ["My AI habits dashboard.lnk", "Uninstall Prompt Coach.lnk"])

    def test_installed_apps_entry_is_written_and_removed(self):
        import winreg
        old = installer.UNINSTALL_KEY
        installer.UNINSTALL_KEY = old + "SelfTest"
        try:
            self.run_setup()
            installer.register_app(self.install_dir, "9.9.9")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_KEY) as key:
                self.assertEqual(winreg.QueryValueEx(key, "DisplayName")[0], "Prompt Coach")
                self.assertEqual(winreg.QueryValueEx(key, "DisplayVersion")[0], "9.9.9")
                self.assertIn("coachw.exe", winreg.QueryValueEx(key, "UninstallString")[0])
            installer.unregister_app()
            with self.assertRaises(OSError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_KEY)
        finally:
            installer.unregister_app()
            installer.UNINSTALL_KEY = old

    def test_claude_code_is_found_one_or_two_folders_under_claude_code(self):
        # Claude 2.1.28x shipped claude-code/<version>/claude.exe; 2.1.29x adds a build-id folder.
        root = os.path.join(self.tmp, "Claude")
        for rel in (("claude-code", "2.1.281", "claude.exe"), ("claude-code", "2.1.299", "f0584be0fbaf", "claude.exe"),
                    ("claude-code", "notes.txt")):
            p = os.path.join(root, *rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write("x")
        with mock.patch.object(installer.shutil, "which", return_value=None):
            found = installer.find_claude_cli(roots=[root])
        self.assertEqual(found, os.path.join(root, "claude-code", "2.1.299", "f0584be0fbaf", "claude.exe"))
        self.assertIsNone(installer.find_claude_cli(roots=[os.path.join(self.tmp, "nowhere")]))

    def test_short_path_removes_spaces(self):
        self.run_setup()
        short = installer.short_path(os.path.join(self.install_dir, "coach.exe"))
        self.assertTrue(os.path.exists(short))
        self.assertTrue(os.path.samefile(short, os.path.join(self.install_dir, "coach.exe")))


@unittest.skipUnless(WINDOWS and os.path.isfile(SETUP_EXE) and built_version() == __version__,
                     "build it first: python coach/scripts/build_installer.py")
class RealBuild(unittest.TestCase):
    """The real setup program, installed into scratch folders and used for real."""

    NO_PYTHON = r"C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pcoach-real-")
        cls.install_dir = os.path.join(cls.tmp, "My Apps", "Prompt Coach")
        cls.config = os.path.join(cls.tmp, "cfg", "claude_desktop_config.json")
        cls.home = os.path.join(cls.tmp, "claude-home")
        cls.data = os.path.join(cls.tmp, "data")
        cls.cli = installer.find_claude_cli()
        cls.setup = os.path.join(cls.tmp, "PromptCoachSetup.exe")     # as downloaded: a lone file
        shutil.copy2(SETUP_EXE, cls.setup)
        cls.common = ["--silent", "--install-dir", cls.install_dir, "--claude-config", cls.config,
                      "--claude-home", cls.home, "--no-shortcuts", "--no-registry"]
        cls.installed = cls.run_setup(["--log", os.path.join(cls.tmp, "install.log")])
        cls.exe = os.path.join(cls.install_dir, "coach.exe")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run_setup(cls, extra):
        env = dict(os.environ, PATH=cls.NO_PYTHON)
        if not cls.cli:
            extra = extra + ["--no-code"]
        return subprocess.run([cls.setup] + cls.common + extra, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=600)

    def env(self, **more):
        env = dict(os.environ, PATH=self.NO_PYTHON, PROMPT_COACH_HOME=self.data)
        env.update(more)
        return env

    def coach(self, args, stdin="", **env):
        return subprocess.run([self.exe] + args, input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=self.env(**env), timeout=120)

    def test_1_setup_succeeded(self):
        self.assertEqual(self.installed.returncode, 0, self.installed.stdout + self.installed.stderr)
        with open(os.path.join(self.tmp, "install.log"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("Install the coach: ok", log)
        self.assertIn("Connect Claude chat and Cowork: ok", log)
        if self.cli:
            self.assertIn("Add to the Code tab: ok", log)

    def test_2_the_program_runs_with_no_python_on_the_computer(self):
        p = self.coach(["doctor"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("everything looks good", p.stdout)
        self.assertEqual(shutil.which("python", path=self.NO_PYTHON), None)

    def test_3_hooks_coach_and_count(self):
        p = self.coach(["session"], json.dumps({"session_id": "real-1"}), CLAUDE_CODE_ENTRYPOINT="claude-desktop")
        self.assertIn("I'm your AI coach", p.stdout)
        p = self.coach(["prompt"], json.dumps({"session_id": "real-1", "prompt": RICH}))
        self.assertEqual(p.returncode, 0, p.stderr)
        state = json.load(open(os.path.join(self.data, "state.json"), encoding="utf-8"))
        self.assertEqual(state["totals"]["prompts"], 1)
        self.assertEqual(state["streak"]["count"], 1)
        self.assertFalse(os.path.exists(os.path.join(self.data, "errors.log")))

    def test_4_the_recommendation_library_travelled_with_it(self):
        p = self.coach(["library"])
        self.assertIn("No problems found", p.stdout)

    def test_5_dashboard_and_score(self):
        p = self.coach(["dashboard", "--no-open"])
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(self.data, "dashboard.html"), encoding="utf-8") as f:
            self.assertIn("Streak and badges", f.read())
        self.assertIn("AI Fluency", self.coach(["score"]).stdout)

    def test_6_chat_helper_speaks_the_protocol(self):
        with open(self.config, encoding="utf-8") as f:
            entry = json.load(f)["mcpServers"]["prompt-coach"]
        self.assertEqual(entry, {"command": self.exe, "args": ["mcp"]})
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "coach_turn", "arguments": {"message": "write a thank-you note to my team"}}}]
        p = subprocess.run([entry["command"]] + entry["args"], input="".join(json.dumps(m) + "\n" for m in msgs),
                           capture_output=True, text=True, encoding="utf-8", timeout=120,
                           env=self.env(PROMPT_COACH_HOME=os.path.join(self.tmp, "chat-data")))
        replies = {r["id"]: r for r in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
        self.assertEqual(replies[1]["result"]["serverInfo"]["version"], __version__)
        self.assertEqual(len(replies[2]["result"]["tools"]), 5)
        self.assertIn("I'm your AI coach", replies[3]["result"]["content"][0]["text"])     # starts by itself

    def test_7_the_hook_command_works_in_powershell_and_cmd(self):
        with open(os.path.join(self.install_dir, "marketplace", "plugin", "hooks", "hooks.json"),
                  encoding="utf-8") as f:
            command = json.load(f)["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertNotIn(" ", command.rsplit(" ", 1)[0])
        payload = os.path.join(self.tmp, "in.json")
        with open(payload, "w", encoding="utf-8") as f:
            json.dump({"session_id": "real-ps", "prompt": "write me a poem about the sea for my nephew"}, f)
        # (cmd gets its line as one string: Python's list quoting would mangle the quotes for it.)
        for name, shell in (("powershell", ["powershell", "-NoProfile", "-Command",
                                            "Get-Content '%s' | %s" % (payload, command)]),
                            ("cmd", 'cmd /c type "%s" | %s' % (payload, command.replace("/", "\\")))):
            before = self.prompts()
            p = subprocess.run(shell, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=self.env(), timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(self.prompts(), before + 1, name)

    def prompts(self):
        try:
            with open(os.path.join(self.data, "state.json"), encoding="utf-8") as f:
                return json.load(f)["totals"]["prompts"]
        except OSError:
            return 0

    def test_8_claude_code_runs_the_installed_plugin(self):
        if not self.cli:
            self.skipTest("Claude Code isn't on this computer")
        self.assertEqual(installer.plugin_installed(self.home), __version__)
        data = os.path.join(self.tmp, "claude-data")
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.home, PROMPT_COACH_HOME=data,
                   CLAUDE_CODE_ENTRYPOINT="claude-desktop")
        p = subprocess.run([self.cli, "-p", RICH, "--output-format", "stream-json", "--verbose",
                            "--include-hook-events"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=300, stdin=subprocess.DEVNULL)
        events = []
        for line in p.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        hooks = {e.get("hook_event"): e for e in events if e.get("subtype") == "hook_response"}
        self.assertIn("SessionStart", hooks, p.stdout[-600:])
        self.assertIn("UserPromptSubmit", hooks)
        for e in hooks.values():
            self.assertEqual(e.get("exit_code"), 0, e)
        self.assertIn("I'm your AI coach", hooks["SessionStart"].get("stdout", ""))
        with open(os.path.join(data, "state.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["totals"]["prompts"], 1)

    def test_8b_the_installed_program_can_remove_itself(self):
        """What 'Uninstall' in Installed apps runs: coachw.exe uninstall, from inside the folder it deletes."""
        import time
        spot = os.path.join(self.tmp, "second")
        args = ["--silent", "--install-dir", os.path.join(spot, "app"), "--claude-config",
                os.path.join(spot, "cfg.json"), "--claude-home", os.path.join(spot, "home"), "--no-code",
                "--no-shortcuts", "--no-registry", "--log", os.path.join(spot, "i.log")]
        os.makedirs(spot)
        p = subprocess.run([self.setup] + args, capture_output=True, text=True, timeout=600,
                           env=dict(os.environ, PATH=self.NO_PYTHON))
        self.assertEqual(p.returncode, 0, p.stdout)
        exe = os.path.join(spot, "app", "coachw.exe")
        self.assertTrue(os.path.exists(exe))
        p = subprocess.run([exe, "uninstall", "--silent", "--claude-config", os.path.join(spot, "cfg.json"),
                            "--claude-home", os.path.join(spot, "home"), "--no-shortcuts", "--no-registry"],
                           capture_output=True, text=True, timeout=120, env=dict(os.environ, PATH=self.NO_PYTHON))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(spot, "cfg.json"), encoding="utf-8") as f:
            self.assertNotIn("prompt-coach", f.read())
        for _ in range(40):                                # the folder goes a few seconds after the program ends
            if not os.path.exists(os.path.join(spot, "app")):
                break
            time.sleep(0.5)
        self.assertFalse(os.path.exists(os.path.join(spot, "app")))

    def test_9_upgrade_then_uninstall_leaves_nothing_but_the_scores(self):
        p = self.run_setup(["--log", os.path.join(self.tmp, "upgrade.log")])
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(self.coach(["doctor"]).returncode, 0)
        p = self.run_setup(["--uninstall", "--log", os.path.join(self.tmp, "uninstall.log")])
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertFalse(os.path.exists(self.install_dir))
        with open(self.config, encoding="utf-8") as f:
            self.assertNotIn("prompt-coach", f.read())
        if self.cli:
            self.assertIsNone(installer.plugin_installed(self.home))
        self.assertTrue(os.path.exists(os.path.join(self.data, "state.json")))


if __name__ == "__main__":
    unittest.main()
