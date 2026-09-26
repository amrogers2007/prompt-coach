"""Static checks on the plugin's own files, so a broken manifest, hook config or
skill front matter is caught in CI rather than silently at runtime (a skill whose
YAML doesn't parse loads with all its metadata dropped)."""

import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    assert m, "%s has no front matter" % path
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


class PluginFiles(unittest.TestCase):
    def markdown_files(self):
        return (glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) +
                glob.glob(os.path.join(ROOT, "agents", "*.md")))

    def test_manifest_and_marketplace(self):
        manifest = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        self.assertEqual(manifest["name"], "prompt-coach")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        market = json.load(open(os.path.join(REPO, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
        entry = market["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])          # entry name must equal manifest name
        self.assertTrue(os.path.isdir(os.path.join(REPO, entry["source"])))

    def test_skill_and_agent_front_matter_is_valid_yaml_shaped(self):
        files = self.markdown_files()
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            fm = frontmatter(path)
            self.assertIn("description", fm, path)
            desc = fm["description"]
            if desc.startswith('"'):
                self.assertTrue(desc.endswith('"') and not desc.endswith('\\"'), path)
            else:
                # An unquoted YAML value can't contain ': ' or ' #' (the skill would lose its metadata).
                self.assertNotIn(": ", desc, path)
                self.assertNotIn(" #", desc, path)

    def test_hooks_config_points_at_real_scripts(self):
        hooks = json.load(open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8"))["hooks"]
        for event in ("SessionStart", "UserPromptSubmit", "PostToolUse"):
            self.assertIn(event, hooks)
        for groups in hooks.values():
            for group in groups:
                for h in group["hooks"]:
                    self.assertEqual(h["type"], "command")
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/run.sh", h["command"])
                    self.assertLessEqual(h.get("timeout", 30), 30)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "scripts", "run.sh")))
        self.assertTrue(os.path.exists(os.path.join(ROOT, "scripts", "coach.py")))

    def test_launcher_has_lf_endings_and_python_floor_matches_docs(self):
        data = open(os.path.join(ROOT, "scripts", "run.sh"), "rb").read()
        self.assertNotIn(b"\r", data)
        readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        self.assertIn("Python 3.9+", readme)
        self.assertIn(b"(3, 9)", data)

    def test_skills_only_preapprove_the_launcher(self):
        for path in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")):
            fm = frontmatter(path)
            allowed = fm.get("allowed-tools")
            if allowed:
                self.assertEqual(allowed, "Bash(sh *scripts/run.sh *)", path)


if __name__ == "__main__":
    unittest.main()
