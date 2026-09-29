"""Guards the trigger detectors' accuracy on the labeled prompt sets in coach/evals/.

The business case's first "must be true" is that teachable moments can be
detected with high precision, so a change that makes coaching fire where it
doesn't fit should fail the build. Run `coach.py eval` to see the details.
"""

import os
import unittest

from helpers import SCRIPTS  # noqa: F401  (puts pcoach on the path)
from pcoach import evaluate, signals

EVALS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals")
MIN_PRECISION = 0.92
MIN_RECALL = 0.85
MIN_DETECTOR_PRECISION = 0.75   # no single detector may be much worse than the rest


class DetectorAccuracy(unittest.TestCase):
    def check(self, name):
        result = evaluate.run(evaluate.load_corpus(os.path.join(EVALS, name)))
        o = result["overall"]
        report = evaluate.render(result)
        self.assertGreaterEqual(o["precision"], MIN_PRECISION, report)
        self.assertGreaterEqual(o["recall"], MIN_RECALL, report)
        for det, s in result["detectors"].items():
            if s["precision"] is not None and s["tp"] + s["fp"] >= 3:
                self.assertGreaterEqual(s["precision"], MIN_DETECTOR_PRECISION, "%s\n%s" % (det, report))
        return result

    def test_tuning_set(self):
        self.check("detector_corpus.jsonl")

    def test_holdout_set(self):
        self.check("detector_holdout.jsonl")

    def test_second_blind_set(self):
        self.check("detector_blind2.jsonl")

    def test_corpus_labels_name_real_detectors(self):
        for name in ("detector_corpus.jsonl", "detector_holdout.jsonl", "detector_blind2.jsonl"):
            for row in evaluate.load_corpus(os.path.join(EVALS, name)):
                for label in row["expect"]:
                    self.assertIn(label, signals.DETECTORS, "%s line %d" % (name, row["line"]))


if __name__ == "__main__":
    unittest.main()
