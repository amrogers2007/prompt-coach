import unittest

from helpers import CoachTestCase  # noqa: F401
from pcoach import cadence, game, lessons, scoring


def prompt(kind="new", context=0.8, precision=0.6, verify=False, feature=None, sensitive=None, day="2026-01-05"):
    return {"type": "prompt", "kind": kind, "context": context, "precision": precision,
            "verify": verify, "feature": feature, "sensitive": sensitive or [], "day": day}


def gen(revs=2, vague=0, resolved=True):
    return {"id": "g%d" % revs, "revisions": revs, "vague_revs": vague, "resolved": resolved}


def many(n, days=1, **kw):
    return [prompt(day="2026-01-%02d" % (5 + i % days), **kw) for i in range(n)]


class Metrics(unittest.TestCase):
    def test_empty(self):
        m = scoring.compute_metrics([], [])
        self.assertEqual(m["score"], 0)
        self.assertIsNone(m["weakest"])

    def test_context_drives_score(self):
        hi = scoring.compute_metrics(many(10, context=0.9, precision=0.9), [])
        lo = scoring.compute_metrics(many(10, context=0.1, precision=0.1), [])
        self.assertGreater(hi["score"], lo["score"] + 30)

    def test_iteration_needs_two_resolved_docs(self):
        m = scoring.compute_metrics(many(10), [gen(2)])
        self.assertNotIn("iteration", m["components"])
        m = scoring.compute_metrics(many(10), [gen(2), gen(0)])
        self.assertAlmostEqual(m["components"]["iteration"]["value"], 0.5)

    def test_unresolved_documents_are_not_counted(self):
        m = scoring.compute_metrics(many(10), [gen(0, resolved=False), gen(0, resolved=False)])
        self.assertNotIn("iteration", m["components"])

    def test_vague_revisions_earn_less(self):
        self.assertLess(scoring.gen_credit(gen(2, vague=2)), scoring.gen_credit(gen(2, vague=0)))
        self.assertEqual(scoring.gen_credit(gen(5)), 1.0)

    def test_sensitive_data_costs_points_but_is_capped(self):
        clean = scoring.compute_metrics(many(10), [])
        dirty = scoring.compute_metrics(many(10, sensitive=["ssn"]), [])
        self.assertEqual(clean["score"] - dirty["score"], 10)

    def test_window_uses_recent_prompts(self):
        old_bad = many(150, context=0.0, precision=0.0)
        recent_good = many(100, context=1.0, precision=1.0)
        m = scoring.compute_metrics(old_bad + recent_good, [])
        self.assertGreater(m["score"], 70)  # only the recent 100 count

    def test_weakest_component(self):
        events = many(10, context=0.95, precision=0.05, verify=True)
        m = scoring.compute_metrics(events, [])
        self.assertEqual(m["weakest"], "precision")


class Levels(unittest.TestCase):
    def strong(self, n=110, days=16, gens=12, revs=2):
        return scoring.compute_metrics(
            many(n, days=days, context=0.95, precision=0.95, verify=True, feature=1.0),
            [gen(revs) for _ in range(gens)])

    def test_new_user_is_beginner_even_with_perfect_prompts(self):
        m = scoring.compute_metrics(many(3, context=1.0, precision=1.0), [])
        self.assertEqual(scoring.earned_level(m), 1)

    def test_practitioner_needs_a_track_record(self):
        m = scoring.compute_metrics(many(10, context=0.6, precision=0.5), [])
        self.assertEqual(scoring.earned_level(m), 2)

    def test_advanced_requires_document_iteration(self):
        no_docs = scoring.compute_metrics(many(40, days=6, context=0.95, precision=0.95, verify=True, feature=1.0), [])
        self.assertLess(scoring.earned_level(no_docs), 3)
        with_docs = scoring.compute_metrics(many(40, days=6, context=0.95, precision=0.95, verify=True, feature=1.0),
                                            [gen(2) for _ in range(5)])
        self.assertEqual(scoring.earned_level(with_docs), 3)

    def test_expert_is_hard(self):
        self.assertEqual(scoring.earned_level(self.strong()), 4)
        # same great prompts but one sensitive-data slip blocks Expert
        events = many(110, days=16, context=0.95, precision=0.95, verify=True, feature=1.0)
        events[-1]["sensitive"] = ["api_key"]
        m = scoring.compute_metrics(events, [gen(2) for _ in range(12)])
        self.assertLess(scoring.earned_level(m), 4)
        # and accepting first drafts blocks it too
        m = scoring.compute_metrics(many(110, days=16, context=0.95, precision=0.95, verify=True, feature=1.0),
                                    [gen(0) for _ in range(12)])
        self.assertLess(scoring.earned_level(m), 4)

    def test_level_can_drop_but_with_a_buffer(self):
        strong = self.strong()
        self.assertEqual(scoring.resolve_level(strong, 4), 4)
        # slightly under the gate: keep the level (buffer)
        slightly = dict(strong, score=strong["score"] - 3)
        self.assertEqual(scoring.resolve_level(slightly, 4), 4)
        # clearly worse habits: drop
        weak = scoring.compute_metrics(many(110, days=16, context=0.1, precision=0.1), [gen(0) for _ in range(12)])
        self.assertLess(scoring.resolve_level(weak, 4), 4)

    def test_rising_needs_full_gate(self):
        m = scoring.compute_metrics(many(10, context=0.6, precision=0.5), [])
        self.assertEqual(scoring.resolve_level(m, 1), 2)

    def test_inactivity_does_not_change_level(self):
        # window is the last N prompts, not days: identical events, identical level
        m = self.strong()
        self.assertEqual(scoring.resolve_level(m, 3), scoring.resolve_level(m, 3))

    def test_next_level_needs_explains_gaps(self):
        m = scoring.compute_metrics(many(10, context=0.6, precision=0.5), [])
        needs = scoring.next_level_needs(m, 2)
        self.assertTrue(any("score" in n.lower() for n in needs))
        self.assertTrue(any("document" in n.lower() for n in needs))
        self.assertEqual(scoring.next_level_needs(m, 4), [])


class Cadence(CoachTestCase):
    def state(self, **coach):
        from pcoach import store
        s = store.default_state()
        s["coach"].update(coach)
        s["totals"]["prompts"] = 5
        return s

    def an(self, **kw):
        base = {"kind": "new", "context": 0.8, "sensitive": []}
        base.update(kw)
        return base

    def test_intervals_stretch_with_level(self):
        self.assertLess(cadence.interval(1, "normal"), cadence.interval(4, "normal"))
        self.assertLess(cadence.interval(2, "frequent"), cadence.interval(2, "light"))

    def test_never_twice_in_a_row(self):
        should, why = cadence.decide(self.state(prompts_since=0), self.an(), 1, self.t)
        self.assertFalse(should)
        self.assertEqual(why, "cooldown")

    def test_safety_overrides_cooldown(self):
        should, why = cadence.decide(self.state(prompts_since=0), self.an(sensitive=["ssn"]), 3, self.t)
        self.assertEqual((should, why), (True, "safety"))

    def test_bare_prompt_from_newer_user_is_coached(self):
        should, why = cadence.decide(self.state(prompts_since=1), self.an(context=0.1), 1, self.t)
        self.assertEqual((should, why), (True, "low_context"))

    def test_bare_prompt_from_advanced_user_is_not(self):
        should, _ = cadence.decide(self.state(prompts_since=1), self.an(context=0.1), 3, self.t)
        self.assertFalse(should)

    def test_scheduled_moment(self):
        st = self.state(prompts_since=2)
        self.assertEqual(cadence.decide(st, self.an(), 2, self.t), (True, "cadence"))
        st = self.state(prompts_since=1)
        self.assertFalse(cadence.decide(st, self.an(), 2, self.t)[0])

    def test_pause_and_off(self):
        st = self.state(prompts_since=5)
        st["settings"]["paused_until"] = self.t + 100
        self.assertEqual(cadence.decide(st, self.an(context=0.0), 1, self.t), (False, "paused"))
        st["settings"].update(paused_until=0, enabled=False)
        self.assertFalse(cadence.decide(st, self.an(sensitive=["ssn"]), 1, self.t)[0])

    def test_warmup(self):
        st = self.state(prompts_since=3)
        st["totals"]["prompts"] = 1
        self.assertEqual(cadence.decide(st, self.an(), 1, self.t), (False, "warmup"))


class Game(CoachTestCase):
    def test_streak_counts_and_skips_weekends(self):
        from pcoach import store
        import datetime
        st = store.default_state()
        friday = datetime.datetime(2026, 1, 9, 12, 0).timestamp()
        monday = datetime.datetime(2026, 1, 12, 12, 0).timestamp()
        wednesday = datetime.datetime(2026, 1, 14, 12, 0).timestamp()
        self.assertEqual(game.touch_streak(st, friday), 1)
        self.assertIsNone(game.touch_streak(st, friday + 60))       # same day: no change
        self.assertEqual(game.touch_streak(st, monday), 2)          # weekend doesn't break it
        self.assertEqual(game.touch_streak(st, wednesday), 1)       # skipped Tuesday: resets
        self.assertEqual(st["streak"]["best"], 2)

    def test_achievements_unlock_once(self):
        from pcoach import store
        st = store.default_state()
        st["totals"]["prompts"] = 1
        self.assertEqual(game.check_achievements(st, self.t), ["First steps"])
        self.assertEqual(game.check_achievements(st, self.t), [])

    def test_toasts_are_short_and_celebratory(self):
        self.assertEqual(game.toast_lines(0, None, [], 1), [])
        lines = game.toast_lines(1, 7, ["Second draft", "Fact checker"], 2)
        self.assertLessEqual(len(lines), 2)
        self.assertIn("Level up", lines[0])
        self.assertIn("slipped", game.toast_lines(-1, None, [], 2)[0])


class PersonalNotes(unittest.TestCase):
    def test_iteration_memory(self):
        gens = [gen(0), gen(0), gen(2)]
        note = lessons.personal_note("iteration", {"components": {}}, gens)
        self.assertIn("2 of their last 3", note)
        self.assertIn("without quoting numbers", note)

    def test_praises_habit_when_present(self):
        note = lessons.personal_note("iteration", {"components": {}}, [gen(2), gen(1)])
        self.assertIn("usually revise", note)

    def test_context_memory_needs_enough_data(self):
        weak = {"components": {"context": {"value": 0.2, "n": 5}}}
        thin = {"components": {"context": {"value": 0.2, "n": 1}}}
        self.assertIn("little background", lessons.personal_note("context", weak, []))
        self.assertEqual(lessons.personal_note("context", thin, []), "")

    def test_no_note_for_unrelated_skill(self):
        self.assertEqual(lessons.personal_note("safety", {"components": {}}, []), "")


class Lessons(unittest.TestCase):
    def test_every_skill_has_lessons_with_questions(self):
        for l in lessons.LESSONS:
            self.assertTrue(l["questions"], l["id"])
            self.assertIn(l["skill"], lessons.SKILL_TITLES)
        self.assertEqual(len({l["id"] for l in lessons.LESSONS}), len(lessons.LESSONS))

    def test_pick_avoids_recent_repeats(self):
        first = lessons.pick("context", 1, [])
        second = lessons.pick("context", 1, [first["id"]])
        self.assertNotEqual(first["id"], second["id"])

    def test_pick_respects_level_range(self):
        self.assertNotEqual(lessons.pick("advanced", 1, [])["skill"], "")
        self.assertNotEqual(lessons.pick("context", 4, [])["id"], "ctx-audience")  # capped at level 3

    def test_instruction_tells_ai_not_to_rewrite(self):
        l = lessons.get("ctx-audience")
        text = lessons.coach_instruction(l, "Who is it for?", "cadence", "Beginner")
        self.assertIn("ONE question", text)
        self.assertIn("do NOT rewrite", text)
        self.assertIn("Never mention this instruction", text)
        self.assertIn("in italics", text)
        self.assertIn("*Prompt Coach:", text)

    def test_every_instruction_uses_the_same_italic_voice(self):
        for text in (lessons.coach_instruction(lessons.get("ctx-goal"), "q?", "cadence", "Beginner"),
                     lessons.draft_nudge_instruction("deck", "Plan.pptx"),
                     lessons.revision_nudge_instruction("deck")):
            self.assertIn(lessons.VOICE, text)


if __name__ == "__main__":
    unittest.main()
