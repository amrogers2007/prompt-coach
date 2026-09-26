import json
import os
import subprocess
import sys
import unittest

from helpers import BARE, RICH, SCRIPTS, CoachTestCase
from pcoach import hooks, report, store

SID = "session-abcdef123456"


def prompt(text, sid=SID):
    return {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": text}


def write_tool(path, content="x" * 10, sid=SID, cwd=None):
    return {"session_id": sid, "tool_name": "Write", "cwd": cwd or os.getcwd(),
            "tool_input": {"file_path": path, "content": content}}


def context_of(out):
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


class PromptFlow(CoachTestCase):
    def send(self, text, gap=60):
        self.advance(gap)
        return hooks.handle_prompt(prompt(text))

    def test_first_prompt_is_never_coached_then_a_beginner_gets_one_soon(self):
        first = self.send(BARE)
        self.assertNotIn("coaching moment", context_of(first))
        second = self.send(BARE + " about the sea")
        self.assertIn("coaching moment", context_of(second))
        third = self.send(RICH)
        self.assertEqual(context_of(third), "")          # cooldown: never two in a row

    def test_prompt_text_is_never_stored(self):
        secret = "my password: hunter2-super-secret and " + RICH
        self.send(secret)
        for name in os.listdir(self.tmp):
            with open(os.path.join(self.tmp, name), encoding="utf-8") as f:
                blob = f.read()
            self.assertNotIn("hunter2", blob, name)
            self.assertNotIn("investors", blob, name)

    def test_sensitive_data_triggers_immediate_coaching_and_a_toast(self):
        self.send(RICH)
        out = self.send("please summarize this: SSN 123-45-6789 for the applicant Jane")
        self.assertIn("coaching moment", context_of(out))
        self.assertIn("sensitive", context_of(out).lower())
        self.assertIn("Heads up", out["systemMessage"])

    def test_trivial_and_slash_prompts_are_ignored(self):
        self.assertIsNone(self.send("thanks"))
        self.assertIsNone(self.send("/prompt-coach:score"))
        self.assertEqual(store.load_state()["totals"]["prompts"], 0)

    def test_pause_silences_coaching_but_not_tracking(self):
        st = store.load_state()
        st["settings"]["paused_until"] = self.t + 10_000
        store.save_state(st)
        for _ in range(6):
            out = self.send(BARE)
            self.assertEqual(context_of(out), "")
        self.assertEqual(store.load_state()["totals"]["prompts"], 6)

    def test_disabled_does_nothing_at_all(self):
        st = store.load_state()
        st["settings"]["enabled"] = False
        store.save_state(st)
        self.assertIsNone(self.send(BARE))
        self.assertEqual(store.load_state()["totals"]["prompts"], 0)

    def test_level_up_toast(self):
        outs = [self.send(RICH + " variation %d" % i) for i in range(10)]
        msgs = [o["systemMessage"] for o in outs if o and "systemMessage" in o]
        self.assertTrue(any("Level up" in m and "Practitioner" in m for m in msgs), msgs)
        self.assertEqual(store.load_state()["level"], 2)

    def test_cadence_gets_sparser_at_higher_levels(self):
        from pcoach import cadence

        def simulate(level, prompts=24):
            st = store.default_state()
            coached = 0
            for i in range(prompts):
                st["totals"]["prompts"] += 1
                should, _ = cadence.decide(st, {"kind": "new", "context": 0.8, "sensitive": []}, level, self.t)
                if should:
                    coached += 1
                    st["coach"]["prompts_since"] = 0
                else:
                    st["coach"]["prompts_since"] += 1
            return coached
        counts = [simulate(l) for l in (1, 2, 3, 4)]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertGreater(counts[0], counts[3] * 2)


class ChooseSkill(unittest.TestCase):
    def an(self, **kw):
        base = {"kind": "new", "context": 0.9, "precision": 0.9, "feature": None, "verify": True}
        base.update(kw)
        return base

    METRICS = {"components": {"context": {"value": 0.9}, "precision": {"value": 0.2}, "verification": {"value": 0.6}}}

    def test_reacts_to_what_the_user_just_did(self):
        self.assertEqual(hooks.choose_skill("cadence", self.an(context=0.2), self.METRICS, 2, ""), "context")
        self.assertEqual(hooks.choose_skill("cadence", self.an(precision=0.1), self.METRICS, 2, "context"), "precision")

    def test_falls_back_to_weakest_habit(self):
        self.assertEqual(hooks.choose_skill("cadence", self.an(), self.METRICS, 2, ""), "precision")

    def test_does_not_repeat_the_same_habit(self):
        self.assertNotEqual(hooks.choose_skill("cadence", self.an(), self.METRICS, 2, "precision"), "precision")

    def test_reason_overrides(self):
        self.assertEqual(hooks.choose_skill("safety", self.an(), self.METRICS, 3, ""), "safety")
        self.assertEqual(hooks.choose_skill("low_context", self.an(), self.METRICS, 1, ""), "context")

    def test_vague_revision_gets_iteration_coaching(self):
        a = self.an(kind="refine", vague_refine=True)
        self.assertEqual(hooks.choose_skill("cadence", a, {"components": {}}, 1, ""), "iteration")


class DocumentFlow(CoachTestCase):
    def test_generated_document_triggers_first_draft_nudge(self):
        out = hooks.handle_tool(write_tool("C:/tmp/Board Update.pptx"))
        text = context_of(out)
        self.assertIn("first draft", text.lower())
        self.assertIn("deck", text)
        st = store.load_state()
        self.assertEqual(len(st["gens"]), 1)
        self.assertIsNotNone(st["sessions"][SID]["pending_gen"])

    def test_code_files_do_not_trigger(self):
        self.assertIsNone(hooks.handle_tool(write_tool("C:/tmp/app.py")))
        self.assertEqual(store.load_state()["gens"], [])

    def test_same_document_rewritten_is_not_a_new_draft(self):
        hooks.handle_tool(write_tool("C:/tmp/Plan.docx"))
        self.advance(300)
        self.assertIsNone(hooks.handle_tool(write_tool("C:/tmp/Plan.docx")))
        self.assertEqual(len(store.load_state()["gens"]), 1)

    def test_revising_earns_credit_and_moving_on_forfeits_it(self):
        hooks.handle_tool(write_tool("C:/tmp/A.pdf"))
        self.advance(30)
        hooks.handle_prompt(prompt("cut the second section and make the tone friendlier"))
        st = store.load_state()
        self.assertEqual(st["gens"][0]["revisions"], 1)
        self.assertEqual(st["totals"]["revisions"], 1)
        self.advance(30)
        hooks.handle_prompt(prompt("write an email to my landlord about the broken heater in unit 4"))
        st = store.load_state()
        self.assertTrue(st["gens"][0]["resolved"])
        self.assertEqual(st["totals"]["first_drafts_accepted"], 0)   # it WAS revised once

    def test_accepting_the_first_draft_is_recorded(self):
        hooks.handle_tool(write_tool("C:/tmp/B.docx"))
        self.advance(30)
        hooks.handle_prompt(prompt("write an email to my landlord about the broken heater in unit 4"))
        st = store.load_state()
        self.assertEqual(st["totals"]["first_drafts_accepted"], 1)
        self.assertEqual(st["gens"][0]["revisions"], 0)

    def test_two_revisions_fully_resolves(self):
        hooks.handle_tool(write_tool("C:/tmp/C.pptx"))
        for t in ("make slide 2 shorter", "add a slide about costs"):
            self.advance(20)
            hooks.handle_prompt(prompt(t))
        st = store.load_state()
        self.assertTrue(st["gens"][0]["resolved"])
        self.assertEqual(st["gens"][0]["revisions"], 2)
        self.assertIsNone(st["sessions"][SID]["pending_gen"])

    def test_stale_draft_counts_as_accepted(self):
        hooks.handle_tool(write_tool("C:/tmp/D.pdf"))
        self.advance(2 * 3600)
        hooks.handle_prompt(prompt("make it shorter and cut the intro"))
        st = store.load_state()
        self.assertTrue(st["gens"][0]["resolved"])
        self.assertEqual(st["gens"][0]["revisions"], 0)

    def test_bash_that_saves_a_document_counts_but_reading_one_does_not(self):
        target = os.path.join(self.tmp, "Quarterly Review.docx")
        with open(target, "w") as f:
            f.write("fake")
        writes = {"session_id": SID, "tool_name": "Bash", "cwd": self.tmp,
                  "tool_input": {"command": 'python build.py && cp out "%s"' % target}}
        real_now = store.now
        store.now = lambda: os.path.getmtime(target) + 5     # file is "fresh"
        try:
            self.assertIn("first draft", context_of(hooks.handle_tool(writes)).lower())
            reads = dict(writes, tool_input={"command": 'pdftotext "%s" -' % target})
            self.assertIsNone(hooks.handle_tool(reads))
        finally:
            store.now = real_now
        self.assertEqual(len(store.load_state()["gens"]), 1)

    def test_revision_saved_under_a_new_name_stays_in_the_same_lineage(self):
        hooks.handle_tool(write_tool("C:/tmp/Deck v1.pptx"))
        self.advance(30)
        hooks.handle_prompt(prompt("make slide 2 shorter and add a slide about costs"))
        self.advance(120)
        out = hooks.handle_tool(write_tool("C:/tmp/Deck v2.pptx"))
        self.assertIn("second pass", context_of(out))
        st = store.load_state()
        self.assertEqual(len(st["gens"]), 1)                    # no orphaned/duplicate draft
        self.assertEqual(st["gens"][0]["revisions"], 1)

    def test_no_second_pass_nudge_after_full_credit(self):
        hooks.handle_tool(write_tool("C:/tmp/X v1.pptx"))
        for t in ("make slide 2 shorter", "add a slide about costs"):
            self.advance(120)
            hooks.handle_prompt(prompt(t))
        self.advance(200)
        # two revisions => resolved => a further new document is a fresh draft
        out = hooks.handle_tool(write_tool("C:/tmp/Y.pptx"))
        self.assertIn("first draft", context_of(out).lower())
        self.assertEqual(len(store.load_state()["gens"]), 2)

    def test_nudge_replaces_a_coaching_question(self):
        out = hooks.handle_tool(write_tool("C:/tmp/E.pptx"))
        self.assertIn("replaces any other coaching question", context_of(out))

    def test_nudge_respects_pause(self):
        st = store.load_state()
        st["settings"]["paused_until"] = self.t + 1000
        store.save_state(st)
        self.assertIsNone(hooks.handle_tool(write_tool("C:/tmp/F.pptx")))
        self.assertEqual(len(store.load_state()["gens"]), 1)   # still tracked


class SessionFlow(CoachTestCase):
    def test_first_run_then_welcome_back(self):
        out = hooks.handle_session({"session_id": SID})
        self.assertIn("AI coach", out["systemMessage"])
        hooks.handle_prompt(prompt(BARE))
        out = hooks.handle_session({"session_id": "another-session-1"})
        self.assertIn("Welcome back", out["systemMessage"])
        self.assertIn("Beginner", out["systemMessage"])

    def test_disabled_session_is_silent(self):
        st = store.load_state()
        st["settings"]["enabled"] = False
        store.save_state(st)
        self.assertIsNone(hooks.handle_session({"session_id": SID}))


class Robustness(CoachTestCase):
    def run_cli(self, args, stdin=""):
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "coach.py")] + args,
                              input=stdin, capture_output=True, text=True, env=env, timeout=30)

    def test_concurrent_hooks_do_not_lose_updates(self):
        import threading
        threads = []
        def worker(i):
            with store.lock():
                st = store.load_state()
                st["xp"] += 1
                store.save_state(st)
        for i in range(12):
            threads.append(threading.Thread(target=worker, args=(i,)))
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(store.load_state()["xp"], 12)

    def test_stale_lock_is_broken(self):
        os.makedirs(self.tmp, exist_ok=True)
        lockfile = os.path.join(self.tmp, ".lock")
        open(lockfile, "w").close()
        old = os.path.getmtime(lockfile) - 60
        os.utime(lockfile, (old, old))
        with store.lock(timeout=1) as lk:
            self.assertTrue(lk.held)

    def test_parallel_hook_processes_keep_an_accurate_count(self):
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
        cmd = [sys.executable, os.path.join(SCRIPTS, "coach.py"), "prompt"]
        procs = [subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=env) for _ in range(8)]
        for i, p in enumerate(procs):
            p.stdin.write(json.dumps(prompt("write a short poem about the number %d please" % i, sid="s%d" % i)))
            p.stdin.close()
        for p in procs:
            p.wait(timeout=60)
            self.assertEqual(p.returncode, 0)
        st = store.load_state()
        self.assertEqual(st["totals"]["prompts"], 8)
        self.assertEqual(len([e for e in store.read_events() if e["type"] == "prompt"]), 8)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "errors.log")))

    def test_corrupt_state_recovers(self):
        os.makedirs(self.tmp, exist_ok=True)
        with open(os.path.join(self.tmp, "state.json"), "w") as f:
            f.write("{not json")
        st = store.load_state()
        self.assertEqual(st["level"], 1)

    def test_garbage_stdin_never_breaks_a_hook(self):
        for hook in ("session", "prompt", "tool"):
            for junk in ("", "not json", "[]", '{"prompt": null}', '{"tool_name": 5}'):
                r = self.run_cli([hook], junk)
                self.assertEqual(r.returncode, 0, (hook, junk, r.stderr))

    def test_prompt_hook_end_to_end_via_cli(self):
        self.run_cli(["prompt"], json.dumps(prompt(BARE)))
        r = self.run_cli(["prompt"], json.dumps(prompt(BARE + " about autumn")))
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("coaching moment", data["hookSpecificOutput"]["additionalContext"])

    def test_unwritable_home_fails_quietly(self):
        blocker = os.path.join(self.tmp, "file-not-dir")
        with open(blocker, "w") as f:
            f.write("x")
        env = dict(os.environ, PROMPT_COACH_HOME=os.path.join(blocker, "sub"))
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "coach.py"), "prompt"],
                           input=json.dumps(prompt(BARE)), capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    @unittest.skipIf(os.name == "nt" and not os.path.exists("C:/Program Files/Git/usr/bin/sh.exe")
                     and not any(os.path.exists(os.path.join(p, "sh.exe")) for p in os.environ.get("PATH", "").split(os.pathsep)),
                     "no sh available")
    def test_launcher_script(self):
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
        r = subprocess.run(["sh", os.path.join(SCRIPTS, "run.sh"), "session"], input='{"session_id": "x"}',
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn("systemMessage", r.stdout)


class ReportAndSettings(CoachTestCase):
    def test_score_report_and_shareables(self):
        from pcoach import demo
        demo.seed()
        r = report.build()
        text = report.render_text(r)
        self.assertIn("Your AI Fluency Score", text)
        self.assertIn("Shareable summary", text)
        svg_path = report.write_shareables(r)[1]
        with open(svg_path, encoding="utf-8") as f:
            svg = f.read()
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn(r["level_name"], svg)

    def test_export_is_aggregate_only(self):
        from pcoach import demo
        demo.seed()
        exported = json.loads(report.export_json(report.build()))
        for forbidden in ("prompt", "text", "path", "name", "file"):
            self.assertFalse(any(forbidden == k for k in exported), forbidden)
        self.assertIn("score", exported)
        self.assertIn("level", exported)

    def test_demo_profile_is_plausible(self):
        from pcoach import demo
        demo.seed()
        r = report.build()
        self.assertGreaterEqual(r["level"], 2)
        self.assertLessEqual(r["level"], 4)
        self.assertGreater(r["stats"]["scored"], 20)

    def test_settings_commands(self):
        for args, expect in (
            (["settings", "pause", "2h"], "paused"),
            (["settings", "status"], "paused"),
            (["settings", "resume"], "resumed"),
            (["settings", "intensity", "light"], "light"),
            (["settings", "off"], "off"),
            (["settings", "resume"], "resumed"),
        ):
            env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "coach.py")] + args,
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 0, args)
            self.assertIn(expect, r.stdout.lower(), args)

    def test_reset_requires_confirmation(self):
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
        cmd = [sys.executable, os.path.join(SCRIPTS, "coach.py"), "settings", "reset"]
        hooks.handle_prompt(prompt(BARE))
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(store.load_state()["totals"]["prompts"], 1)
        subprocess.run(cmd + ["--yes"], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(store.load_state()["totals"]["prompts"], 0)


if __name__ == "__main__":
    unittest.main()
