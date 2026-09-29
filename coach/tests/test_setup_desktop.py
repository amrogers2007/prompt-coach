"""The desktop-chat setup script, run against a scratch config (never the real one)."""

import glob
import io
import json
import os
import sys
import tempfile
import unittest

from helpers import SCRIPTS

sys.path.insert(0, SCRIPTS)
import setup_desktop  # noqa: E402


class SetupDesktop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="claude-cfg-")
        self.config = os.path.join(self.dir, "claude_desktop_config.json")
        self.existing = {"preferences": {"sidebarMode": "epitaxy", "chicagoEnabled": True},
                         "mcpServers": {"other-tool": {"command": "node", "args": ["x.js"]}}}
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(self.existing, f)
        ext = os.path.join(self.dir, "Claude Extensions Settings")
        os.makedirs(ext)
        self.ext_settings = os.path.join(ext, "local.mcpb.amanda-rogers.prompt-coach.json")
        with open(self.ext_settings, "w", encoding="utf-8") as f:
            json.dump({"isEnabled": True}, f)
        self.out = io.StringIO()

    def say(self, *a):
        print(*a, file=self.out)

    def config_now(self):
        with open(self.config, encoding="utf-8") as f:
            return json.load(f)

    def install(self, **kw):
        return setup_desktop.install(self.config, self.dir, out=self.say, python=sys.executable, **kw)

    def test_connects_keeps_other_settings_and_backs_up(self):
        self.assertEqual(self.install(), 0, self.out.getvalue())
        data = self.config_now()
        self.assertEqual(data["preferences"], self.existing["preferences"])
        self.assertEqual(data["mcpServers"]["other-tool"], self.existing["mcpServers"]["other-tool"])
        entry = data["mcpServers"]["prompt-coach"]
        self.assertEqual(entry["command"], sys.executable)
        self.assertTrue(entry["args"][0].endswith("coach_mcp.py") and os.path.isabs(entry["args"][0]))
        self.assertEqual(len(glob.glob(self.config + ".bak-prompt-coach-*")), 1)
        self.assertIn("helper answered with 5 tools", self.out.getvalue())

    def test_running_twice_changes_nothing_the_second_time(self):
        self.install()
        before = self.config_now()
        self.install()
        self.assertEqual(self.config_now(), before)
        self.assertEqual(len(glob.glob(self.config + ".bak-prompt-coach-*")), 1)
        self.assertIn("already connected", self.out.getvalue())

    def test_switches_off_the_old_extension_unless_asked_not_to(self):
        self.install(keep_extension=True)
        with open(self.ext_settings, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["isEnabled"])
        self.install()
        with open(self.ext_settings, encoding="utf-8") as f:
            self.assertFalse(json.load(f)["isEnabled"])

    def test_missing_config_is_created(self):
        os.remove(self.config)
        self.assertEqual(self.install(), 0)
        self.assertIn("prompt-coach", self.config_now()["mcpServers"])

    def test_remove_undoes_it(self):
        self.install()
        self.assertEqual(setup_desktop.remove(self.config, out=self.say), 0)
        data = self.config_now()
        self.assertNotIn("prompt-coach", data["mcpServers"])
        self.assertIn("other-tool", data["mcpServers"])

    def test_check_reports_and_test_launches(self):
        self.assertEqual(setup_desktop.check(self.config, self.dir, out=self.say), 1)   # not connected yet
        self.install()
        self.assertEqual(setup_desktop.check(self.config, self.dir, out=self.say), 0)
        self.assertIn("Test launch: OK", self.out.getvalue())

    def test_store_python_is_never_used(self):
        self.assertTrue(setup_desktop.is_store_python(
            r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python3.exe"))
        self.assertFalse(setup_desktop.is_store_python(r"C:\Python313\python.exe"))
        found = setup_desktop.find_python()
        self.assertTrue(found is None or not setup_desktop.is_store_python(found))

    # --- --wait: the change must land while Claude is closed --------------------------------------

    GOOD_LOG = ("2026-09-29 [prompt-coach] [info] Initializing server...\n"
                "[prompt-coach] [info] Server started and connected successfully\n"
                "[prompt-coach] [info] Message from client: method=\"tools/list\" id=1\n")

    def wait(self, running_seq, reopen=None, log=GOOD_LOG, timeout=60):
        seen_while_running = []
        states = list(running_seq)

        def running():
            state = states.pop(0) if states else False
            if state:   # the entry must never be written while Claude is still running
                seen_while_running.append("prompt-coach" in self.config_now().get("mcpServers", {}))
            return state
        rc = setup_desktop.wait_and_apply(
            self.config, self.dir, out=self.say, running=running, reopen=reopen or (lambda: True),
            sleep=lambda s: None, poll=1, timeout=timeout, confirm_timeout=5, read_log=lambda: log)
        return rc, seen_while_running

    def test_wait_applies_only_after_claude_has_closed_then_confirms(self):
        rc, seen = self.wait([True, True, True, False, False])
        self.assertEqual(rc, 0, self.out.getvalue())
        self.assertEqual(seen, [False, False, False])     # never written while Claude was still running
        self.assertIn("prompt-coach", self.config_now()["mcpServers"])
        self.assertIn("Success: Claude started the Prompt Coach helper", self.out.getvalue())

    def test_wait_gives_up_if_claude_never_closes(self):
        before = self.config_now()
        rc, _ = self.wait([True] * 200, timeout=10)
        self.assertEqual(rc, 1)
        self.assertEqual(self.config_now(), before)
        self.assertIn("Nothing was changed", self.out.getvalue())

    def test_wait_reports_a_helper_that_crashes_on_start(self):
        crash = self.GOOD_LOG.split("Server started")[0] + "python3: can't open file 'x': [Errno 2] No such file"
        rc, _ = self.wait([False, False], log=crash)
        self.assertEqual(rc, 1)
        self.assertIn("it failed", self.out.getvalue())

    def test_wait_notices_if_claude_strips_the_entry(self):
        def reopen_and_strip():
            data = self.config_now()
            del data["mcpServers"]["prompt-coach"]
            setup_desktop.write_json(self.config, data)
            return True
        rc, _ = self.wait([False, False], reopen=reopen_and_strip)
        self.assertEqual(rc, 1)
        self.assertIn("removed the Prompt Coach entry", self.out.getvalue())

    def test_desktop_app_is_told_apart_from_the_claude_code_cli(self):
        self.assertTrue(setup_desktop._is_desktop_path(
            r"C:\Program Files\WindowsApps\Claude_2.9939.4.0_x64__pzs8sxrjxfjjc\app\Claude.exe"))
        self.assertTrue(setup_desktop._is_desktop_path(r"C:\Users\a\AppData\Local\AnthropicClaude\app-1.0\claude.exe"))
        self.assertFalse(setup_desktop._is_desktop_path(r"C:\Users\a\AppData\Roaming\Claude\claude-code\2.1.284\claude.exe"))

    def test_startup_verdict(self):
        self.assertEqual(setup_desktop.startup_verdict(self.GOOD_LOG), "ok")
        self.assertIsNone(setup_desktop.startup_verdict(""))
        old_fail_then_ok = "Initializing server...\nclosed unexpectedly\n" + self.GOOD_LOG
        self.assertEqual(setup_desktop.startup_verdict(old_fail_then_ok), "ok")     # only the latest start counts

    def test_a_helper_that_fails_to_start_changes_nothing(self):
        before = self.config_now()
        rc = setup_desktop.install(self.config, self.dir, out=self.say,
                                   python=os.path.join(self.dir, "no-such-python.exe"))
        self.assertEqual(rc, 1)
        self.assertEqual(self.config_now(), before)
        self.assertIn("Nothing was changed", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
