import unittest

from helpers import BARE, RICH, CoachTestCase  # noqa: F401
from pcoach import signals


class ContextScore(unittest.TestCase):
    def test_bare_prompt_scores_low(self):
        self.assertLess(signals.context_score(BARE), 0.2)

    def test_rich_prompt_scores_high(self):
        self.assertGreaterEqual(signals.context_score(RICH), 0.7)

    def test_length_alone_is_not_enough(self):
        filler = "please " * 60
        self.assertLess(signals.context_score(filler), 0.5)

    def test_empty(self):
        self.assertEqual(signals.context_score(""), 0.0)

    def test_variety_beats_repetition(self):
        varied = "I'm a nurse manager writing for my staff because we need a new shift policy so that handoffs improve."
        repeated = "policy policy policy policy policy policy policy policy policy policy policy policy"
        self.assertGreater(signals.context_score(varied), signals.context_score(repeated))


class PrecisionAndVerification(unittest.TestCase):
    def test_format_tone_and_numbers(self):
        self.assertGreaterEqual(signals.precision_score("5 bullets, formal tone, under 100 words"), 0.7)

    def test_no_spec(self):
        self.assertEqual(signals.precision_score("tell me about dogs"), 0.0)

    def test_verification_cues(self):
        for t in ["please cite sources", "double-check the numbers", "how sure are you?",
                  "what am I missing", "play devil's advocate"]:
            self.assertTrue(signals.has_verification(t), t)
        self.assertFalse(signals.has_verification("write a summary of the meeting"))


class Refinement(unittest.TestCase):
    def test_refinements(self):
        for t in ["make it shorter", "change the title on slide 3", "add a section about costs",
                  "too formal, soften the tone", "can you also remove the last bullet"]:
            self.assertTrue(signals.is_refinement(t), t)

    def test_new_tasks_are_not_refinements(self):
        for t in ["write a poem about autumn", "Create a budget spreadsheet for my club",
                  "help me draft an email to my landlord"]:
            self.assertFalse(signals.is_refinement(t), t)

    def test_new_task_that_refers_back_is_refinement(self):
        self.assertTrue(signals.is_refinement("write it again but shorter, make the deck more visual"))

    def test_long_messages_are_not_refinements(self):
        self.assertFalse(signals.is_refinement("change " + "word " * 200))

    def test_vague(self):
        self.assertTrue(signals.is_vague_refinement("make it better"))
        self.assertFalse(signals.is_vague_refinement("cut slide 3 in half and lead with the cost"))

    def test_kind_classification(self):
        self.assertEqual(signals.classify_kind("anything", 0, False), "new")
        self.assertEqual(signals.classify_kind("make it shorter", 3, True), "refine")
        self.assertEqual(signals.classify_kind("make it shorter", 3, False), "followup")
        self.assertEqual(signals.classify_kind("thanks, that helps", 2, False), "followup")
        self.assertEqual(signals.classify_kind(RICH, 4, False), "new")


class Triviality(unittest.TestCase):
    def test_trivial(self):
        for t in ["", "ok", "thanks", "/help", "yes please"]:
            self.assertTrue(signals.is_trivial(t), t)

    def test_not_trivial(self):
        self.assertFalse(signals.is_trivial("write a poem"))
        self.assertFalse(signals.is_trivial("shorter please"))


class CodingPrompts(unittest.TestCase):
    def test_coding_prompts_are_recognised(self):
        for t in ["fix the bug in content.js where the card disappears",
                  "why does this throw?\n```python\nprint(x)\n```",
                  "refactor this function and add unit tests",
                  "run npm install and then git commit the changes"]:
            self.assertTrue(signals.is_coding_prompt(t), t)

    def test_everyday_prompts_are_not(self):
        for t in [RICH, BARE, "write an email about the bug in our billing process to my customer",
                  "summarize the python course syllabus for my manager"]:
            self.assertFalse(signals.is_coding_prompt(t), t)


class Features(unittest.TestCase):
    def test_file_reference_is_good(self):
        self.assertEqual(signals.feature_signal("Summarize @reports/q3.docx for me"), 1.0)
        self.assertEqual(signals.feature_signal("update the deck to use our new logo"), 1.0)

    def test_giant_paste_is_bad(self):
        pasted = "rewrite this: " + "lorem ipsum dolor sit amet " * 90
        self.assertEqual(signals.feature_signal(pasted), 0.0)

    def test_not_applicable(self):
        self.assertIsNone(signals.feature_signal("what is a good name for a bakery"))


class Sensitive(unittest.TestCase):
    def test_detects_categories_without_returning_values(self):
        text = "my key is sk-abcdefghijklmnopqrstuvwx and ssn 123-45-6789 password: hunter2"
        found = signals.find_sensitive(text)
        self.assertEqual(found, ["api_key", "password", "ssn"])
        self.assertNotIn("hunter2", "".join(found))

    def test_card_numbers_need_a_valid_luhn(self):
        self.assertIn("card_number", signals.find_sensitive("card 4111 1111 1111 1111"))
        self.assertNotIn("card_number", signals.find_sensitive("order 1234 5678 9012 3456"))

    def test_private_key_and_confidential(self):
        self.assertIn("private_key", signals.find_sensitive("-----BEGIN RSA PRIVATE KEY-----"))
        self.assertIn("confidential_marker", signals.find_sensitive("this is CONFIDENTIAL do not share"))

    def test_clean_text(self):
        self.assertEqual(signals.find_sensitive(RICH), [])


class Documents(unittest.TestCase):
    def test_doc_kinds(self):
        self.assertEqual(signals.doc_kind_for_path("/x/Plan.PPTX"), "deck")
        self.assertEqual(signals.doc_kind_for_path("r.pdf"), "PDF")
        self.assertIsNone(signals.doc_kind_for_path("app.py"))

    def test_soft_docs_need_size(self):
        self.assertIsNone(signals.doc_kind_for_path("notes.md", soft_min_chars=1500, content_len=100))
        self.assertEqual(signals.doc_kind_for_path("notes.md", soft_min_chars=1500, content_len=4000), "document")

    def test_paths_in_command(self):
        cmd = 'python make_deck.py && cp out.pptx "C:/Users/me/Reports/Q3 plan.pdf"'
        paths = signals.doc_paths_in_command(cmd)
        self.assertIn("out.pptx", paths)
        self.assertTrue(any(p.endswith(".pdf") for p in paths))


if __name__ == "__main__":
    unittest.main()
