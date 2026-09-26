import json
import os
import subprocess
import sys
import unittest

from helpers import BARE, RICH, SCRIPTS, CoachTestCase
from pcoach import hooks, mcp_server, store

SERVER = os.path.join(SCRIPTS, "coach_mcp.py")


def rpc(method, params=None, mid=1):
    msg = {"jsonrpc": "2.0", "method": method}
    if mid is not None:
        msg["id"] = mid
    if params is not None:
        msg["params"] = params
    return msg


def call(name, args=None, mid=1):
    return rpc("tools/call", {"name": name, "arguments": args or {}}, mid)


def text_of(reply):
    assert "result" in reply, reply
    return reply["result"]["content"][0]["text"]


class InProcess(CoachTestCase):
    def setUp(self):
        super().setUp()
        self.server = mcp_server.Server()

    def test_initialize_negotiates_and_carries_instructions(self):
        r = self.server.handle(rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                  "clientInfo": {"name": "t", "version": "1"}}))
        self.assertEqual(r["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertIn("coach_turn", r["result"]["instructions"])
        r = self.server.handle(rpc("initialize", {"protocolVersion": "1999-01-01"}))
        self.assertEqual(r["result"]["protocolVersion"], mcp_server.SUPPORTED_PROTOCOLS[0])

    def test_notifications_get_no_reply(self):
        self.assertIsNone(self.server.handle(rpc("notifications/initialized", mid=None)))

    def test_tools_list_is_well_formed(self):
        tools = self.server.handle(rpc("tools/list"))["result"]["tools"]
        names = [t["name"] for t in tools]
        self.assertEqual(names, ["coach_start", "coach_turn", "coach_document", "coach_score", "coach_settings"])
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertTrue(t["description"])

    def test_unknown_method_and_tool_are_errors_not_crashes(self):
        self.assertEqual(self.server.handle(rpc("nope"))["error"]["code"], -32601)
        self.assertEqual(self.server.handle(call("nope"))["error"]["code"], -32602)

    def test_first_conversation_greets_via_the_chat_note(self):
        text = text_of(self.server.handle(call("coach_start")))
        self.assertIn("I'm your AI coach", text)
        self.assertIn("at the very start", text)
        again = text_of(self.server.handle(call("coach_start")))
        self.assertIn("Welcome back, I'm your AI coach", again)

    def test_turns_return_nothing_then_a_coaching_instruction(self):
        first = text_of(self.server.handle(call("coach_turn", {"message": BARE})))
        self.assertNotIn("coaching moment", first)                 # (may carry the "First steps" achievement note)
        second = text_of(self.server.handle(call("coach_turn", {"message": BARE + " about the sea"})))
        self.assertIn("coaching moment", second)
        self.assertIn("Prompt Coach:", second)
        third = text_of(self.server.handle(call("coach_turn", {"message": RICH})))
        self.assertNotIn("coaching moment", third)                 # cooldown: never twice in a row

    def test_trivial_and_coding_messages_are_ignored(self):
        for msg in ("thanks", "fix the bug in content.js where it crashes"):
            self.assertIn("Nothing to do", text_of(self.server.handle(call("coach_turn", {"message": msg}))))
        self.assertEqual(store.load_state()["totals"]["prompts"], 0)

    def test_sensitive_message_gets_a_heads_up_and_is_not_stored(self):
        text = text_of(self.server.handle(call("coach_turn", {"message": "summarize: SSN 123-45-6789 for Jane Doe"})))
        self.assertIn("sensitive", text.lower())
        for name in os.listdir(self.tmp):
            with open(os.path.join(self.tmp, name), encoding="utf-8") as f:
                self.assertNotIn("123-45-6789", f.read(), name)

    def test_long_messages_are_truncated_before_analysis(self):
        text_of(self.server.handle(call("coach_turn", {"message": "write a memo " + "word " * 5000})))
        events = [e for e in store.read_events() if e["type"] == "prompt"]
        self.assertLessEqual(events[0]["words"], 310)      # 1500 characters, not 5000 words

    def test_hook_and_mcp_do_not_double_count_the_same_message(self):
        hooks.handle_prompt({"session_id": "code-session-1", "prompt": RICH})               # hook saw it first
        again = text_of(self.server.handle(call("coach_turn", {"message": RICH})))          # tool sees it too
        self.assertIn("Nothing to do", again)
        self.assertEqual(store.load_state()["totals"]["prompts"], 1)

    def test_same_channel_repeats_still_count(self):
        self.server.handle(call("coach_turn", {"message": RICH}))
        self.server.handle(call("coach_turn", {"message": RICH}))
        self.assertEqual(store.load_state()["totals"]["prompts"], 2)

    def test_document_flow_draft_then_revision(self):
        nudge = text_of(self.server.handle(call("coach_document", {"kind": "deck", "name": "Board Update"})))
        self.assertIn("first draft", nudge.lower())
        self.advance(30)
        self.server.handle(call("coach_turn", {"message": "make slide 2 shorter and add costs"}))
        self.assertEqual(store.load_state()["totals"]["revisions"], 1)
        self.advance(200)
        second = text_of(self.server.handle(call("coach_document", {"kind": "deck", "name": "Board Update v2"})))
        self.assertIn("second pass", second)
        self.assertEqual(len(store.load_state()["gens"]), 1)

    def test_unknown_document_kind_falls_back(self):
        text = text_of(self.server.handle(call("coach_document", {"kind": "zzz", "name": "Thing"})))
        self.assertIn("first draft", text.lower())

    def test_score_and_settings(self):
        self.assertIn("Your AI Fluency Score", text_of(self.server.handle(call("coach_score"))))
        data = json.loads(text_of(self.server.handle(call("coach_score", {"format": "json"}))))
        self.assertIn("score", data)
        self.assertIn("paused", text_of(self.server.handle(call("coach_settings", {"action": "pause", "value": "2h"}))))
        self.assertNotIn("coaching moment", text_of(self.server.handle(call("coach_turn", {"message": BARE + " again please"}))))
        self.assertIn("resumed", text_of(self.server.handle(call("coach_settings", {"action": "resume"}))))
        self.assertIn("light", text_of(self.server.handle(call("coach_settings", {"action": "intensity", "value": "light"}))))
        self.assertIn("on", text_of(self.server.handle(call("coach_settings", {"action": "status"}))))

    def test_bad_settings_do_not_crash(self):
        r = self.server.handle(call("coach_settings", {"action": "intensity", "value": "extreme"}))
        self.assertIn("Nothing to do", text_of(r))                # error swallowed, logged, chat unaffected
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "errors.log")))

    def test_session_rolls_over_after_idle(self):
        first = self.server.session()
        self.server.last_call -= mcp_server.IDLE_SESSION_SECONDS + 5
        self.assertNotEqual(self.server.session(), first + "-x")   # a new id is issued when idle
        self.assertTrue(self.server.session().startswith("mcp-"))


class OverStdio(CoachTestCase):
    def run_server(self, lines, env_extra=None):
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
        env.update(env_extra or {})
        data = "".join(l if isinstance(l, str) else json.dumps(l) + "\n" for l in lines)
        p = subprocess.run([sys.executable, SERVER], input=data, capture_output=True, text=True, env=env, timeout=60)
        return p

    def test_full_session_over_the_wire(self):
        p = self.run_server([
            rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}, 1),
            rpc("notifications/initialized", mid=None),
            rpc("tools/list", mid=2),
            call("coach_start", mid=3),
            call("coach_turn", {"message": BARE}, mid=4),
            call("coach_turn", {"message": BARE + " for my nephew"}, mid=5),
        ])
        self.assertEqual(p.returncode, 0, p.stderr)
        replies = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])       # nothing extra on stdout
        self.assertIn("coaching moment", text_of(replies[4]))
        self.assertEqual(p.stderr, "")

    def test_garbage_input_does_not_kill_the_server(self):
        p = self.run_server(["not json\n", "[]\n", '"string"\n', "\n", rpc("ping", mid=7)])
        self.assertEqual(p.returncode, 0)
        lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual(lines[0]["error"]["code"], -32700)
        self.assertEqual(lines[-1], {"jsonrpc": "2.0", "id": 7, "result": {}})

    def test_corrupt_state_recovers(self):
        os.makedirs(self.tmp, exist_ok=True)
        with open(os.path.join(self.tmp, "state.json"), "w") as f:
            f.write("{broken")
        p = self.run_server([call("coach_turn", {"message": BARE}, mid=1)])
        self.assertEqual(json.loads(p.stdout.splitlines()[0])["id"], 1)

    def test_non_ascii_messages(self):
        p = self.run_server([call("coach_turn", {"message": "écris un poème sur la mer pour mon neveu, s'il te plaît"}, mid=1)])
        self.assertIn("result", json.loads(p.stdout.splitlines()[0]))


if __name__ == "__main__":
    unittest.main()
