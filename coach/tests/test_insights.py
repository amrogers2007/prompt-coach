"""The effectiveness measures: can they see a real learning effect, and do they
stay flat when there isn't one? Two simulated users go through the real prompt
hook with a randomized holdout; one learns from coaching, one never changes."""

import random
import unittest

from helpers import CoachTestCase
from pcoach import hooks, insights, store

SID = "session-insights-01"

# Each issue has a prompt that triggers it and a version where the habit is fixed.
ISSUES = {
    "no_audience": ("write an email about the office move",
                    "write an email to my team about the office move, 5 bullets, so they know where to park"),
    "factual_question": ("how many people live in Ohio?",
                         "how many people live in Ohio? cite the census source"),
    "subjective": ("make the proposal more compelling and polished",
                   "cut the proposal to 300 words and lead with the cost savings"),
    "calculations": ("calculate the total if we sell 1200 units at $45 with a 15% discount",
                     "check my math: 1200 units at $45 with a 15% discount is $45,900"),
}
NEUTRAL = "explain how compound interest works like I'm 12"


class Simulation(CoachTestCase):
    def run_user(self, learns, seed, prompts=110):
        """One simulated person, in a fresh data folder. A learner fixes an issue
        most of the time once they've been coached on that exact issue."""
        store.reset()
        hooks._rng = random.Random(seed)
        rng = random.Random(seed + 1000)
        state = store.load_state()
        state["settings"]["holdout"] = 0.4
        store.save_state(state)
        coached = set()
        for i in range(prompts):
            self.advance(20 * 60 if i % 15 else 16 * 3600)   # a few sessions a day, many days
            issue = rng.choice(list(ISSUES) + [None])
            if issue is None:
                text = NEUTRAL
            else:
                bad, good = ISSUES[issue]
                text = good if (learns and issue in coached and rng.random() < 0.85) else bad
            out = hooks.handle_prompt({"session_id": SID, "prompt": text})
            ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
            if "coaching moment" in ctx:
                coached.update(store.load_state()["coach"]["last_moment"].get("triggers", []))
        return insights.build()

    def pilot(self, learns, people=6):
        return [self.run_user(learns, seed=100 + p) for p in range(people)]

    def test_pilot_detects_a_real_learning_effect(self):
        reports = self.pilot(learns=True)
        pooled = insights.pool(reports)
        self.assertGreaterEqual(pooled["coached"]["issues"], 5)
        self.assertGreaterEqual(pooled["holdout"]["issues"], 3)
        self.assertLess(pooled["effect"], -0.08)      # coached issues fell well below held-back ones
        self.assertIn("Did it stick?", insights.render(reports[0]))

    def test_pilot_shows_no_effect_when_nobody_changes(self):
        pooled = insights.pool(self.pilot(learns=False))
        self.assertIsNotNone(pooled["effect"])
        self.assertLess(abs(pooled["effect"]), 0.06)

    def test_an_issue_keeps_its_group(self):
        self.run_user(learns=False, seed=3, prompts=60)
        arms = store.load_state()["coach"]["arms"]
        by_issue = {}
        for e in store.read_events():
            if e["type"] in ("coach", "coach_holdout"):
                for t in e.get("triggers", []):
                    if t in arms:
                        by_issue.setdefault(t, set()).add(e["type"])
        for t, kinds in by_issue.items():
            self.assertEqual(len(kinds), 1, t)

    def test_holdout_never_withholds_safety(self):
        hooks._rng = random.Random(1)
        state = store.load_state()
        state["settings"]["holdout"] = 0.5
        store.save_state(state)
        for i in range(12):
            self.advance(120)
            out = hooks.handle_prompt({"session_id": SID, "prompt": "Help me write a termination letter "
                                       "for an employee on my team, formal, 1 page, so HR can file it %d" % i})
            state = store.load_state()
            state["coach"]["prompts_since"] = 3
            store.save_state(state)
        kinds = [e["type"] for e in store.read_events() if e["type"] in ("coach", "coach_holdout")]
        self.assertNotIn("coach_holdout", kinds)
        self.assertIn("coach", kinds)


class FeedbackControls(CoachTestCase):
    def send(self, text, gap=60):
        self.advance(gap)
        return hooks.handle_prompt({"session_id": SID, "prompt": text})

    def offer(self):
        self.send("explain how compound interest works like I'm 12")
        state = store.load_state()
        state["coach"]["prompts_since"] = 5
        store.save_state(state)
        out = self.send("write an email about the office move")
        self.assertIn("coaching moment", (out or {}).get("hookSpecificOutput", {}).get("additionalContext", ""))
        return store.load_state()["coach"]["last_moment"]["id"]

    def test_misfit_mutes_the_tip_and_is_acknowledged(self):
        tip = self.offer()
        out = self.send("that doesn't apply here")
        self.assertIn("didn't fit", out["hookSpecificOutput"]["additionalContext"])
        state = store.load_state()
        self.assertIn(tip, state["coach"]["muted"])
        self.assertEqual(insights.build()["misfit"], 1)

    def test_two_declines_mute_a_tip_for_a_while(self):
        first = self.offer()
        self.send("no thanks")
        state = store.load_state()
        state["coach"]["lessons"] = []            # let it come round again
        store.save_state(state)
        again = self.offer()
        self.assertEqual(first, again)
        self.send("not now")
        self.assertIn(first, store.load_state()["coach"]["muted"])
        state = store.load_state()
        state["coach"]["lessons"] = []
        store.save_state(state)
        self.assertNotEqual(self.offer(), first)  # muted tips are skipped

    def test_muted_safety_tip_is_never_silenced(self):
        self.send("explain how compound interest works like I'm 12")
        self.send("My SSN is 123-45-6789, fill in this form please")
        self.send("that's not relevant")
        self.assertEqual(store.load_state()["coach"]["muted"], {})


if __name__ == "__main__":
    unittest.main()
