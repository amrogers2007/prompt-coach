"""The two files people upload to the Claude desktop app must build and be complete:
the chat skill (tells Claude to use the coach's tools) and the plugin zip."""

import json
import os
import tempfile
import unittest
import zipfile

from helpers import SCRIPTS  # noqa: F401  (also puts scripts/ on sys.path)
import build_chat_skill
import build_zip
from pcoach import __version__, mcp_server


class ChatSkill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="pcoach-dist-")
        cls.old_out = build_chat_skill.OUT_DIR
        build_chat_skill.OUT_DIR = cls.out
        build_chat_skill.main()
        cls.skill = os.path.join(cls.out, "prompt-coach-chat-skill.zip")

    @classmethod
    def tearDownClass(cls):
        build_chat_skill.OUT_DIR = cls.old_out

    def parts(self):
        text = zipfile.ZipFile(self.skill).read("prompt-coach/SKILL.md").decode("utf-8")
        head, body = text.split("---\n", 2)[1:]
        return head, body

    def test_front_matter_is_valid(self):
        head, _body = self.parts()
        self.assertIn("name: prompt-coach", head)
        desc = [l for l in head.splitlines() if l.startswith("description:")][0]
        self.assertTrue(desc.split(": ", 1)[1].startswith('"') and desc.endswith('"'))      # quoted YAML

    def test_it_carries_the_helpers_own_instructions(self):
        _head, body = self.parts()
        self.assertIn(mcp_server.INSTRUCTIONS, body)
        for tool in mcp_server.TOOLS:
            self.assertIn(tool["name"], body)
        self.assertIn("ignore this skill completely", body)          # safe when the helper isn't connected

    def test_the_zip_holds_only_the_skill(self):
        self.assertEqual(zipfile.ZipFile(self.skill).namelist(), ["prompt-coach/SKILL.md"])


class PluginZip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="pcoach-dist-")
        cls.old_out = build_zip.OUT_DIR
        build_zip.OUT_DIR = cls.out
        build_zip.main()
        cls.names = zipfile.ZipFile(os.path.join(cls.out, "prompt-coach-plugin.zip")).namelist()
        cls.zip = zipfile.ZipFile(os.path.join(cls.out, "prompt-coach-plugin.zip"))

    @classmethod
    def tearDownClass(cls):
        cls.zip.close()
        build_zip.OUT_DIR = cls.old_out

    def test_everything_the_coach_needs_travels_with_it(self):
        for needed in (".claude-plugin/plugin.json", "hooks/hooks.json", "scripts/run.sh", "scripts/coach.py",
                       "scripts/coach_mcp.py", "scripts/pcoach/hooks.py", "scripts/pcoach/dashboard_page.html",
                       "library/recommendations.md", "skills/coach/SKILL.md", "skills/dashboard/SKILL.md",
                       "agents/coach.md"):
            self.assertIn(needed, self.names, needed)

    def test_no_tests_or_caches_are_shipped(self):
        self.assertFalse([n for n in self.names if n.startswith("tests/") or "__pycache__" in n or n.endswith(".pyc")])

    def test_version_matches_the_code(self):
        manifest = json.loads(self.zip.read(".claude-plugin/plugin.json"))
        self.assertEqual(manifest["version"], __version__)


if __name__ == "__main__":
    unittest.main()
