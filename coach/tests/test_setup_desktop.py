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

    def test_a_helper_that_fails_to_start_changes_nothing(self):
        before = self.config_now()
        rc = setup_desktop.install(self.config, self.dir, out=self.say,
                                   python=os.path.join(self.dir, "no-such-python.exe"))
        self.assertEqual(rc, 1)
        self.assertEqual(self.config_now(), before)
        self.assertIn("Nothing was changed", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
