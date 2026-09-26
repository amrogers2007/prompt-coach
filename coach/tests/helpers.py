import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from pcoach import store  # noqa: E402


class CoachTestCase(unittest.TestCase):
    """Gives each test a private data folder and a controllable clock."""

    START = 1_750_000_000  # a fixed Tuesday-ish timestamp; day math uses local time

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pcoach-test-")
        self._old_home = os.environ.get("PROMPT_COACH_HOME")
        os.environ["PROMPT_COACH_HOME"] = self.tmp
        self._old_entry = os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)   # tests must not depend on where they run
        self._old_now = store.now
        self.t = float(self.START)
        store.now = lambda: self.t

    def tearDown(self):
        if self._old_entry is not None:
            os.environ["CLAUDE_CODE_ENTRYPOINT"] = self._old_entry
        store.now = self._old_now
        if self._old_home is None:
            os.environ.pop("PROMPT_COACH_HOME", None)
        else:
            os.environ["PROMPT_COACH_HOME"] = self._old_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def advance(self, seconds):
        self.t += seconds


RICH = ("I'm preparing a board update for our investors. The goal is to persuade them to approve "
        "a hiring plan because growth is stalling. Keep it to 5 bullets in a formal tone, and cite sources.")
BARE = "write me a poem"
