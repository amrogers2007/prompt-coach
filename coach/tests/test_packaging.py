"""The desktop pieces (extension + chat skill) must build, be self-contained, and run
from the unpacked bundle exactly as Claude Desktop would run them."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

from helpers import SCRIPTS  # noqa: F401  (also puts scripts/ on sys.path)
import build_mcpb
from pcoach import mcp_server


class Packaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="pcoach-dist-")
        cls.old_out = build_mcpb.OUT_DIR
        build_mcpb.OUT_DIR = cls.out
        build_mcpb.main()
        cls.mcpb = os.path.join(cls.out, "prompt-coach.mcpb")
        cls.skill = os.path.join(cls.out, "prompt-coach-chat-skill.zip")

    @classmethod
    def tearDownClass(cls):
        build_mcpb.OUT_DIR = cls.old_out

    def test_manifest_has_what_the_spec_requires(self):
        m = json.loads(zipfile.ZipFile(self.mcpb).read("manifest.json"))
        for key in ("manifest_version", "name", "version", "description", "author", "server"):
            self.assertIn(key, m)
        self.assertEqual(m["author"]["name"], "Amanda Rogers")
        self.assertEqual(m["server"]["type"], "python")
        self.assertIn("${__dirname}", m["server"]["mcp_config"]["args"][0])
        self.assertEqual(m["server"]["mcp_config"]["platform_overrides"]["win32"]["command"], "python")
        self.assertEqual([t["name"] for t in m["tools"]], [t["name"] for t in mcp_server.TOOLS])
        self.assertIn(">=3.9", m["compatibility"]["runtimes"]["python"])
        names = zipfile.ZipFile(self.mcpb).namelist()
        self.assertIn(m["server"]["entry_point"], names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])

    def test_version_matches_the_plugin(self):
        m = json.loads(zipfile.ZipFile(self.mcpb).read("manifest.json"))
        with open(os.path.join(os.path.dirname(SCRIPTS), ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            plugin = json.load(f)
        self.assertEqual(m["version"], plugin["version"])

    def test_bundle_runs_on_its_own(self):
        with tempfile.TemporaryDirectory() as unpacked, tempfile.TemporaryDirectory() as home:
            zipfile.ZipFile(self.mcpb).extractall(unpacked)
            server = os.path.join(unpacked, "server", "coach_mcp.py")
            env = dict(os.environ, PROMPT_COACH_HOME=home)
            env.pop("PYTHONPATH", None)
            data = "".join(json.dumps(m) + "\n" for m in (
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "coach_start", "arguments": {}}}))
            p = subprocess.run([sys.executable, server], input=data, capture_output=True, text=True, env=env,
                               timeout=60, cwd=unpacked)
            self.assertEqual(p.returncode, 0, p.stderr)
            replies = [json.loads(l) for l in p.stdout.splitlines()]
            self.assertEqual(len(replies[1]["result"]["tools"]), 5)
            self.assertIn("I'm your AI coach", replies[2]["result"]["content"][0]["text"])

    def test_chat_skill_is_valid_and_carries_the_instructions(self):
        text = zipfile.ZipFile(self.skill).read("prompt-coach/SKILL.md").decode("utf-8")
        head, body = text.split("---\n", 2)[1:]
        self.assertIn("name: prompt-coach", head)
        desc = [l for l in head.splitlines() if l.startswith("description:")][0]
        self.assertTrue(desc.split(": ", 1)[1].startswith('"') and desc.endswith('"'))      # quoted YAML
        for tool in ("coach_start", "coach_turn", "coach_document", "coach_score"):
            self.assertIn(tool, body)
        self.assertIn("ignore this skill completely", body)          # safe when the extension is absent


if __name__ == "__main__":
    unittest.main()
