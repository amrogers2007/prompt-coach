"""Sanity-check the score and levels against realistic user archetypes.

These aren't unit tests of one function: they replay believable behavior through
the real hook handlers (with a fake clock) and check the *outcomes* we designed
for: bad habits stay Beginner, real improvement climbs, Expert is reachable but
hard, and slipping habits lose a level.
"""

import random
import unittest

from helpers import CoachTestCase
from pcoach import hooks, report, store

LAZY = ["write me a poem", "summarize this", "make a presentation", "email for my boss", "explain taxes",
        "write a report", "fix this", "help with my resume", "make it better", "write a speech"]

MEDIUM = [
    "Write an email to my landlord about the broken heater, keep it polite and short.",
    "Summarize this article for me in 5 bullets, focus on the risks.",
    "Help me draft a status update for my team about the delayed launch, formal tone.",
    "Explain how compound interest works in simple terms, with one example.",
    "Create an agenda for a 45 minute team meeting about Q3 planning, use a table.",
]

RICH = [
    "I'm a project manager preparing a status update for our executive team because the launch slipped two weeks. "
    "The goal is to reassure them and ask for one extra contractor. Keep it to 5 bullets in a confident, formal tone "
    "and cite the numbers I give you.",
    "I'm applying for a marketing analyst role at a healthcare company and my background is in retail. Draft a cover "
    "letter that connects my experience so that the hiring manager sees the fit. Keep it under 250 words, warm but "
    "professional, and don't use clichés. Tell me if you're unsure about anything.",
    "We are a nonprofit preparing a grant proposal for the city board, who care mostly about measurable impact. "
    "Outline the proposal as a table with sections, and flag any claims that need a source before we submit.",
    "I'm a teacher writing a parent newsletter about the new reading program because parents keep asking questions. "
    "For a non-technical audience, use 3 short paragraphs and a friendly tone, and avoid jargon.",
]

FOLLOWUP = ["make slide 2 shorter", "add a section about costs", "too formal, soften the tone",
            "cut the last paragraph and lead with the result", "change the title to something punchier"]


class Persona:
    def __init__(self, test, name, new_pool, revise_prob, verify_prob=0.0):
        self.test, self.name = test, name
        self.new_pool, self.revise_prob = new_pool, revise_prob
        self.rnd = random.Random(hash(name) % 1000)
        self.sid_n = 0

    def workday(self, prompts=3):
        t = self.test
        self.sid_n += 1
        sid = "%s-%d-abcdef" % (self.name, self.sid_n)
        hooks.handle_session({"session_id": sid})
        for _ in range(prompts):
            t.advance(600)
            text = self.rnd.choice(self.new_pool)
            hooks.handle_prompt({"session_id": sid, "prompt": text})
            t.advance(60)
            hooks.handle_tool({"session_id": sid, "tool_name": "Write", "cwd": "/tmp",
                               "tool_input": {"file_path": "/tmp/%s-%d-%d.docx" % (self.name, self.sid_n, self.rnd.random() * 1e6),
                                              "content": "x"}})
            if self.rnd.random() < self.revise_prob:
                for _ in range(self.rnd.choice([1, 2, 2])):
                    t.advance(120)
                    hooks.handle_prompt({"session_id": sid, "prompt": self.rnd.choice(FOLLOWUP)})
                    t.advance(120)
                    hooks.handle_tool({"session_id": sid, "tool_name": "Write", "cwd": "/tmp",
                                       "tool_input": {"file_path": "/tmp/rev.docx", "content": "x"}})
        self.test.advance(86400)     # next day

    def level(self):
        return report.build()["level"]


class Archetypes(CoachTestCase):
    def run_days(self, persona, days):
        out = []
        for d in range(days):
            if self.t and store.day_of(self.t) and __import__("time").localtime(self.t).tm_wday >= 5:
                self.advance(86400)
            persona.workday()
            out.append(persona.level())
        return out

    def test_lazy_user_stays_a_beginner(self):
        levels = self.run_days(Persona(self, "lazy", LAZY, revise_prob=0.0), 20)
        self.assertEqual(max(levels), 1, levels)

    def test_average_user_reaches_practitioner_not_advanced(self):
        levels = self.run_days(Persona(self, "avg", MEDIUM, revise_prob=0.3), 25)
        self.assertGreaterEqual(max(levels), 2, levels)
        self.assertLessEqual(max(levels), 3, levels)

    def test_power_user_gets_to_advanced_and_can_reach_expert_but_not_instantly(self):
        levels = self.run_days(Persona(self, "power", RICH, revise_prob=0.9), 30)
        first_advanced = next((i for i, l in enumerate(levels) if l >= 3), None)
        self.assertIsNotNone(first_advanced, levels)
        self.assertGreaterEqual(first_advanced, 3, "Advanced should take more than a couple of days: %s" % levels)
        self.assertEqual(levels[-1], 4, "a consistently strong user should be able to reach Expert: %s" % levels)
        first_expert = next(i for i, l in enumerate(levels) if l == 4)
        self.assertGreaterEqual(first_expert, 10, "Expert must be hard: %s" % levels)

    def test_good_user_who_slips_loses_a_level(self):
        good = Persona(self, "slip", RICH, revise_prob=0.95)
        self.run_days(good, 25)
        peak = good.level()
        self.assertGreaterEqual(peak, 3)
        bad = Persona(self, "slip", LAZY, revise_prob=0.0)
        bad.sid_n = 1000
        levels = self.run_days(bad, 25)
        self.assertLess(levels[-1], peak, (peak, levels))


if __name__ == "__main__":
    unittest.main()
