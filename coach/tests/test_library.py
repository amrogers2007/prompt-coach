"""The recommendation library (coach/library/recommendations.md), its trigger
detectors, and the offer -> "yes" -> follow-up flow."""

import os
import tempfile
import unittest

from helpers import BARE, RICH, CoachTestCase
from pcoach import hooks, lessons, library, signals, store

SID = "session-library-0001"


def prompt(text, sid=SID):
    return {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": text}


def context_of(out):
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


class LibraryFile(unittest.TestCase):
    def test_shipped_library_has_no_problems(self):
        entries, problems = library.check(detectors=signals.DETECTORS)
        self.assertEqual(problems, [])
        self.assertGreaterEqual(len(entries), 70)

    def test_every_entry_has_the_three_parts(self):
        for e in library.load():
            self.assertTrue(e["when"] and e["recommend"] and e["action"], e["id"])
            self.assertIn(e["skill"], lessons.SKILL_TITLES, e["id"])

    def test_every_detector_is_used_and_every_skill_has_an_everyday_entry(self):
        entries = library.load()
        used = {d for e in entries for d in e["detect"]}
        self.assertEqual(set(signals.DETECTORS) - used, set())
        for skill in lessons.SKILL_TITLES:
            self.assertTrue(any(e["skill"] == skill and "general" in e["detect"] for e in entries), skill)

    def test_parser_defaults_and_problems(self):
        text = (
            "# Library\n\n## How to add\nSome notes, no fields.\n\n# Define\n\n"
            "## my-new-one\n- title: T\n- skill: context\n- when: W\n- recommend: R1\n- recommend: R2\n- action: A\n\n"
            "## broken\n- title: T\n- skill: nonsense\n- when: W\n- recommend: R\n- action: A\n\n"
            "## Bad Id\n- title: T\n- skill: safety\n- levels: 9\n- when: W\n- recommend: R\n- action: A\n"
            "- colour: blue\n"
        )
        entries, problems = library.parse(text)
        ids = [e["id"] for e in entries]
        self.assertEqual(ids, ["my-new-one", "Bad Id"])
        first = entries[0]
        self.assertEqual(first["stage"], "Define")
        self.assertEqual(first["levels"], (1, 4))
        self.assertEqual(first["detect"], ["ai"])
        self.assertEqual(first["recommend"], ["R1", "R2"])
        joined = " | ".join(problems)
        self.assertIn("broken: skill 'nonsense'", joined)
        self.assertIn("lowercase words", joined)
        self.assertIn("unknown field 'colour'", joined)
        self.assertIn("levels '9'", joined)

    def test_edits_to_the_file_are_picked_up_without_restarting(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "r.md")
        entry = "# Define\n## a\n- title: T\n- skill: context\n- when: W\n- recommend: R\n- action: A\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(entry)
        self.assertEqual(len(library.load(path)), 1)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n" + entry.replace("## a", "## b").replace("# Define\n", "") + "extra\n")
        os.utime(path, (1, 2))    # make sure the change is visible even on coarse clocks
        self.assertEqual([e["id"] for e in library.load(path)], ["a", "b"])

    def test_files_saved_by_windows_editors_still_load(self):
        with open(library.default_path(), encoding="utf-8") as f:
            src = f.read()
        d = tempfile.mkdtemp()
        variants = {
            "bom.md": b"\xef\xbb\xbf" + src.encode("utf-8"),
            "crlf.md": src.replace("\n", "\r\n").encode("utf-8"),
            "ansi.md": src.encode("cp1252", errors="replace"),   # Notepad "ANSI"
        }
        for name, data in variants.items():
            path = os.path.join(d, name)
            with open(path, "wb") as f:
                f.write(data)
            self.assertEqual(len(library.load(path)), len(library.load()), name)
        _entries, problems = library.check(os.path.join(d, "ansi.md"), signals.DETECTORS)
        self.assertIn("UTF-8", problems[0])

    def test_missing_file_means_an_empty_library_not_a_crash(self):
        self.assertEqual(library.load(os.path.join(tempfile.gettempdir(), "no-such-library.md")), [])


class Detectors(unittest.TestCase):
    CASES = {
        "help me with my presentation": "vague_goal",
        "write an email about the office move": "no_audience",
        "Draft the SOW for the PMO using the RACI from the QBR": "jargon",
        "Can you write a brief, professional bio for my website": "subjective",
        "What percentage of US adults use AI at work?": "factual_question",
        "what is our PTO policy for new hires": "internal_policy",
        "what are the latest interest rate changes": "current_info",
        "calculate the total if we sell 1200 units at $45 with a 15% discount": "calculations",
        "Help me write a termination letter for an employee": "consequential",
        "this is too formal, doesn't sound like me": "tone_feedback",
        "give me a name for my bakery": "single_option",
        "write a 20 page business plan for a coffee shop": "long_document",
        "turn this list into a CSV I can import into our CRM": "structured_output",
        "you forgot the pricing section again": "missed_requirement",
        "send it to the whole team": "external_action",
        "delete all the old drafts permanently": "irreversible",
        "from now on always use British spelling": "remember_pref",
        "every monday I write a status update for my boss": "repeated_task",
        "I'm going on leave next week, help me hand this off to my colleague": "handoff",
        "summarize this article, then compare it with the other one, and draft a response": "multi_task",
        "write a quick, comprehensive and creative plan that's also cheap": "competing_goals",
        "write it in the same style as our last newsletter": "style_no_example",
        "My SSN is 123-45-6789, fill in this form": "sensitive",
    }

    def test_each_detector_fires_on_its_example(self):
        for text, name in self.CASES.items():
            self.assertIn(name, signals.analyze_prompt(text)["triggers"], text)

    def test_quiet_on_ordinary_rich_requests(self):
        self.assertEqual(signals.analyze_prompt(RICH)["triggers"], [])
        self.assertEqual(signals.analyze_prompt("explain how compound interest works like I'm 12")["triggers"], [])

    def test_acceptance_and_decline(self):
        for yes in ("yes", "Yes please", "sure, go ahead", "ok do it", "let's do that"):
            self.assertTrue(signals.is_acceptance(yes), yes)
        for no in ("no thanks", "not now", "nope"):
            self.assertFalse(signals.is_acceptance(no), no)
            self.assertTrue(signals.is_decline(no), no)
        self.assertFalse(signals.is_acceptance("yes " + "word " * 20))


class Choosing(unittest.TestCase):
    def test_detected_trigger_beats_the_everyday_pool(self):
        main, alts, detected = lessons.choose("context", 1, ["no_audience"], [])
        self.assertEqual(main["id"], "define-audience")
        self.assertTrue(detected)

    def test_urgent_trigger_wins_even_for_another_habit(self):
        main, _alts, _ = lessons.choose("context", 1, ["no_audience", "consequential"], [])
        self.assertEqual(main["id"], "validate-human")

    def test_recently_shown_recommendation_is_not_repeated(self):
        main, _alts, detected = lessons.choose("context", 1, ["no_audience"], ["define-audience"])
        self.assertNotEqual(main["id"], "define-audience")

    def test_nothing_detected_falls_back_to_an_everyday_habit(self):
        main, alts, detected = lessons.choose("precision", 1, [], [])
        self.assertIn("general", main["detect"])
        self.assertFalse(detected)
        for a in alts:
            self.assertIn("ai", a["detect"])
            self.assertEqual(a["skill"], main["skill"])

    def test_level_range_is_respected(self):
        main, alts, _ = lessons.choose("advanced", 1, ["repeated_task"], [])   # automate-candidate is 2-4
        self.assertNotEqual(main["id"], "automate-candidate")
        for a in alts:
            self.assertLessEqual(a["levels"][0], 1)

    def test_instruction_carries_offer_and_action(self):
        main, alts, _ = lessons.choose("context", 1, ["no_audience"], [])
        text = lessons.coach_instruction(main, main["recommend"][0], "cadence", "Beginner", "", alts, True)
        self.assertIn(main["action"], text)
        self.assertIn("What prompted it", text)
        self.assertIn(lessons.VOICE, text)


class OfferFlow(CoachTestCase):
    def send(self, text, gap=60):
        self.advance(gap)
        return hooks.handle_prompt(prompt(text))

    def coached_offer(self):
        self.send(RICH)
        out = self.send("write an email about the office move")
        self.assertIn("coaching moment", context_of(out))
        return store.load_state()["sessions"][SID]["offer"]

    def test_yes_to_the_offer_gets_the_follow_up_action(self):
        offer = self.coached_offer()
        out = self.send("yes please")
        ctx = context_of(out)
        self.assertIn("[Prompt Coach: follow-up]", ctx)
        self.assertIn(lessons.get(offer["ids"][0])["action"], ctx)
        state = store.load_state()
        self.assertEqual(state["totals"]["offers_accepted"], 1)
        self.assertNotIn("offer", state["sessions"][SID])

    def test_longer_yes_is_scored_and_not_coached_on_top(self):
        self.coached_offer()
        for _ in range(3):
            self.send(BARE + " about trees")    # make a new coaching moment due
        state = store.load_state()
        state["sessions"][SID]["offer"] = {"ids": ["define-audience"], "ts": self.t}
        state["coach"]["prompts_since"] = 5
        store.save_state(state)
        out = self.send("yes, go ahead and do that for the email")
        ctx = context_of(out)
        self.assertIn("follow-up", ctx)
        self.assertNotIn("coaching moment", ctx)

    def test_taking_three_offers_unlocks_coachable(self):
        out = None
        for i in range(3):
            state = store.load_state()
            state["sessions"].setdefault(SID, {"prompts": 1, "pending_gen": None, "last_ts": self.t,
                                               "coached_this_turn": False, "last_nudge_ts": 0})
            state["sessions"][SID]["offer"] = {"ids": ["define-audience"], "ts": self.t}
            store.save_state(state)
            out = self.send("yes please")
        self.assertIn("coachable", store.load_state()["achievements"])
        self.assertIn("Coachable", out.get("systemMessage", ""))

    def test_no_thanks_or_moving_on_lets_the_offer_lapse(self):
        self.coached_offer()
        self.assertIsNone(self.send("no thanks"))
        self.assertNotIn("offer", store.load_state()["sessions"][SID])
        events = [e["type"] for e in store.read_events()]
        self.assertIn("offer_declined", events)

    def test_a_stale_yes_does_nothing(self):
        self.coached_offer()
        out = self.send("yes", gap=hooks.OFFER_TTL_SECONDS + 5)
        self.assertIsNone(out)

    def test_plain_yes_with_no_offer_is_still_ignored(self):
        self.assertIsNone(self.send("yes"))
        self.assertEqual(store.load_state()["totals"]["prompts"], 0)

    def test_urgent_trigger_skips_the_schedule_but_not_the_cooldown(self):
        self.send(RICH)
        self.send(RICH)   # second prompt: past warm-up; RICH is well specified
        state = store.load_state()
        state["coach"]["prompts_since"] = 1
        store.save_state(state)
        out = self.send("Help me write a termination letter for an employee on my team, formal, 1 page, "
                        "so HR can file it")
        self.assertIn("qualified human", context_of(out).lower())


class ConversationRegressions(CoachTestCase):
    """Bugs found by replaying a realistic 12-message conversation (2026-09-28)."""

    def send(self, text, gap=90, sid=SID):
        self.advance(gap)
        out = hooks.handle_prompt(prompt(text, sid))
        return context_of(out)

    def test_urgent_tip_is_said_once_per_conversation(self):
        self.send(RICH)
        msgs = ["Help me write a termination letter for an employee who missed deadlines",
                "add the date of the performance review", "the termination is effective Friday",
                "is it legal to terminate someone in California without notice",
                "draft the email to HR about the termination", "mention the final paycheck for the termination"]
        shown = sum("qualified human review" in self.send(m) for m in msgs)
        self.assertEqual(shown, 1)
        # A new conversation may raise it again.
        hooks.handle_session({"session_id": "other"})
        self.assertIn("qualified human review", self.send(msgs[0], sid="other") or
                      self.send(msgs[3], sid="other"))

    def test_ok_plus_a_new_instruction_is_not_a_yes(self):
        for text in ("ok make the tone warmer", "please shorten it", "great, now add a chart"):
            self.assertFalse(signals.is_acceptance(text), text)
        for text in ("ok", "ok thanks", "okay go ahead", "perfect thanks", "yes, it's for the board"):
            self.assertTrue(signals.is_acceptance(text), text)

    def test_small_edits_are_not_interrupted_by_generic_tips(self):
        self.send(RICH)
        self.send("Help me write a termination letter for an employee who missed deadlines")
        for edit in ("make it more formal", "add the date of the performance review",
                     "shorten the second paragraph", "add a line about returning the laptop"):
            self.assertNotIn("everyday habit", self.send(edit), edit)

    def test_draft_question_replaces_the_offer(self):
        import tempfile
        self.send(RICH)
        self.assertIn("coaching moment", self.send("create a presentation about customer churn"))
        path = os.path.join(tempfile.mkdtemp(), "Churn.pptx")
        with open(path, "w") as f:
            f.write("x")
        self.advance(20)
        out = hooks.handle_tool({"session_id": SID, "tool_name": "Write",
                                 "tool_input": {"file_path": path, "content": "x"}})
        self.assertIn("first draft", context_of(out))
        # "yes" now answers the draft question, not the hidden offer.
        self.assertNotIn("follow-up", self.send("yes"))

    def test_claudes_own_scratch_notes_are_not_user_documents(self):
        import tempfile
        long_text = "notes " * 400
        scratch = os.path.join(tempfile.mkdtemp(), "scratchpad", "commit-msg.txt")
        in_temp = os.path.join(tempfile.mkdtemp(), "plan.md")
        memory = os.path.join(os.path.expanduser("~"), ".claude", "projects", "p", "memory", "note.md")
        for path in (scratch, in_temp, memory):
            out = hooks.handle_tool({"session_id": SID, "tool_name": "Write",
                                     "tool_input": {"file_path": path, "content": long_text}})
            self.assertIsNone(out, path)
        # A real document the user asked for, even in a temp folder, still counts.
        deck = os.path.join(tempfile.mkdtemp(), "Plan.pptx")
        out = hooks.handle_tool({"session_id": SID, "tool_name": "Write",
                                 "tool_input": {"file_path": deck, "content": "x"}})
        self.assertIn("first draft", context_of(out))
        # And a long Markdown report in the user's own folder does too.
        self.assertFalse(hooks._is_scratch_text(os.path.join(os.path.expanduser("~"), "Documents", "report.md")))

    def test_short_new_request_is_new_work(self):
        self.assertEqual(signals.classify_kind("write me a poem about autumn", 3, False), "new")
        self.assertEqual(signals.classify_kind("write it shorter", 3, False), "followup")
        self.assertEqual(signals.classify_kind("draft the memo again", 3, False), "followup")


if __name__ == "__main__":
    unittest.main()
