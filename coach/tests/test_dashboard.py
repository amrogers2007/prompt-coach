"""The personal dashboard: the numbers behind it, the page it writes, and privacy."""

import json
import os
import re

from helpers import RICH, CoachTestCase
from pcoach import dashboard, demo, game, hooks, library, mcp_server, scoring, signals, store


def data_of(html):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


class DashboardData(CoachTestCase):
    def test_empty_profile(self):
        d = dashboard.build()
        self.assertTrue(d["empty"])
        self.assertEqual(d["rows"], [])
        self.assertEqual(len(d["gap_info"]), len(dashboard.HABIT_GAPS))     # explanations ship even with no data

    def test_history_rows_add_up(self):
        demo.seed_history(weeks=6, now=self.t)
        events = store.read_events()
        d = dashboard.build(now=self.t)
        rows = d["rows"]
        # one row per calendar day, no gaps, ending today
        self.assertEqual(rows[-1]["day"], store.day_of(self.t))
        self.assertEqual(len({r["day"] for r in rows}), len(rows))
        # totals match the raw log
        self.assertEqual(sum(r["prompts"] for r in rows), sum(1 for e in events if e["type"] == "prompt"))
        self.assertEqual(sum(r["coached"] for r in rows), sum(1 for e in events if e["type"] == "coach"))
        self.assertEqual(sum(r["taken"] for r in rows), sum(1 for e in events if e["type"] == "offer_accepted"))
        self.assertEqual(sum(r["docs"] for r in rows), sum(1 for e in events if e["type"] == "gen"))
        self.assertEqual(sum(r["docs_done"] for r in rows), sum(1 for e in events if e["type"] == "gen_resolved"))
        gaps = sum(sum(r["issues"].values()) for r in rows)
        self.assertEqual(gaps, sum(len([t for t in e.get("triggers", []) if t in dashboard.HABIT_GAPS])
                                   for e in events if e["type"] == "prompt"))
        for r in rows:
            self.assertTrue(0 <= r["score"] <= 100)

    def test_good_habit_days_follow_the_streak_rule(self):
        demo.seed_history(weeks=3, now=self.t)
        events = store.read_events()
        good = set()
        for e in events:
            if e["type"] == "prompt" and game.is_good_habit({"kind": e["kind"], "context": e["context"]}):
                good.add(e["day"])
        rows = dashboard.build(now=self.t)["rows"]
        self.assertEqual({r["day"] for r in rows if r["good_day"]}, good)

    def test_the_sample_person_improves(self):
        demo.seed_history(weeks=8, now=self.t)
        rows = dashboard.build(now=self.t)["rows"]
        active = [r for r in rows if r["prompts"]]
        early, late = active[:10], active[-10:]
        rate = lambda rs: sum(r["issues"].get("no_audience", 0) for r in rs) / float(sum(r["prompts"] for r in rs))
        self.assertLess(rate(late), rate(early))
        self.assertGreater(late[-1]["score"], early[0]["score"])

    def test_each_days_score_uses_only_what_had_happened_by_then(self):
        demo.seed_history(weeks=3, now=self.t)
        events = store.read_events()
        rows = dashboard.build(now=self.t)["rows"]
        mid = rows[len(rows) // 2]
        end = dashboard._day_end(mid["day"])
        gens = [dict(g, resolved=True) for g in dashboard._gens(events, store.load_state()["gens"])
                if g.get("resolved") and g["resolved_ts"] < end]
        expected = scoring.compute_metrics([e for e in events if e["ts"] < end], gens)["score"]
        self.assertEqual(mid["score"], expected)

    def test_final_score_and_needs_match_the_scoreboard(self):
        demo.seed_history(weeks=4, now=self.t)
        d = dashboard.build(now=self.t)
        gens = [dict(g, resolved=True) for g in dashboard._gens(store.read_events(), store.load_state()["gens"]) if g.get("resolved")]
        m = scoring.compute_metrics(store.read_events(), gens)
        self.assertEqual(d["current"]["score"], m["score"])
        self.assertEqual(d["needs"], scoring.next_level_needs(m, d["current"]["level"]))

    def test_older_profiles_without_issue_labels_still_work(self):
        demo.seed()             # the 0.2-era sample: no issue labels, documents only in the saved state
        d = dashboard.build()
        self.assertFalse(d.get("empty"))
        self.assertGreater(sum(r["docs_done"] for r in d["rows"]), 0)
        self.assertEqual(sum(sum(r["issues"].values()) for r in d["rows"]), 0)


class GapExplanations(CoachTestCase):
    def test_every_gap_has_a_detector_a_library_entry_and_an_example(self):
        detectors = {d for e in library.load() for d in e["detect"]}
        info = dashboard.gap_info()
        for key in dashboard.HABIT_GAPS:
            self.assertIn(key, signals.DETECTORS, key)
            self.assertIn(key, detectors, key)
            self.assertIn(key, dashboard.GAP_EXAMPLES, key)
            g = info[key]
            for field in ("title", "when", "recommend", "action", "before", "after"):
                self.assertTrue(g[field], "%s.%s" % (key, field))

    def test_the_better_example_no_longer_triggers_the_gap(self):
        """The 'try' version of each example must not itself set off the same detector
        (other than sensitive, whose example keeps a placeholder on purpose)."""
        for key, (before, after) in dashboard.GAP_EXAMPLES.items():
            if key == "sensitive":
                continue
            self.assertNotIn(key, signals.analyze_prompt(after)["triggers"], "%s: %r" % (key, after))


class Badges(CoachTestCase):
    def test_every_badge_has_progress_that_agrees_with_its_test(self):
        for aid, _title, _desc, test in game.ACHIEVEMENTS:
            self.assertIn(aid, game.ACHIEVEMENT_PROGRESS, aid)
        state = store.load_state()
        state["totals"].update({"prompts": 60, "revisions": 5, "rich_prompts": 5, "verifies": 3, "sensitive": 0, "offers_accepted": 3})
        state["streak"]["best"] = 14
        for aid, _title, _desc, test in game.ACHIEVEMENTS:
            have, need = game.ACHIEVEMENT_PROGRESS[aid](state)
            self.assertTrue(test(state), aid)
            self.assertGreaterEqual(have, need, aid)
        state["totals"]["sensitive"] = 1
        self.assertEqual(game.ACHIEVEMENT_PROGRESS["clean_hands"](state)[0], 0)

    def test_dashboard_lists_earned_and_in_progress_badges(self):
        demo.seed_history(weeks=6, now=self.t)
        d = dashboard.build(now=self.t)
        ids = {a["id"] for a in d["achievements"]}
        self.assertTrue({"first_steps", "level_2", "level_4"} <= ids)
        for a in d["achievements"]:
            self.assertTrue(0 <= a["have"] <= a["need"], a)
            if a["done"]:
                self.assertEqual(a["have"], a["need"], a)
        self.assertTrue(any(a["done"] for a in d["achievements"]))
        self.assertTrue(any(not a["done"] for a in d["achievements"]))


class DashboardPage(CoachTestCase):
    def test_page_is_self_contained_and_carries_the_data(self):
        demo.seed_history(weeks=2, now=self.t)
        html = dashboard.render(dashboard.build(now=self.t))
        # nothing is loaded from anywhere: no external scripts, styles, images or fonts
        urls = set(re.findall(r"https?://[^\s\"'<>)]+", html))
        self.assertEqual(urls, {"http://www.w3.org/2000/svg"})       # an SVG namespace name, not a request
        self.assertNotRegex(html, r"<(script|link|img)[^>]+(src|href)=")
        self.assertGreater(len(data_of(html)["rows"]), 5)

    def test_data_cannot_break_out_of_its_script_tag(self):
        d = dashboard.build()
        d["issue_names"] = {"x": "</script><script>alert(1)</script>"}
        html = dashboard.render(d)
        self.assertEqual(html.count("</script>"), 2)                  # only the page's own two script tags
        self.assertEqual(data_of(html)["issue_names"]["x"], "</script><script>alert(1)</script>")

    def test_write_saves_next_to_the_profile_without_opening_a_browser(self):
        path = dashboard.write(open_browser=False)
        self.assertEqual(path, os.path.join(self.tmp, "dashboard.html"))
        self.assertTrue(os.path.getsize(path) > 1000)

    def test_message_text_never_reaches_the_page(self):
        secret = "our secret merger with Zorblax Industries " + RICH
        hooks.handle_prompt({"session_id": "s", "prompt": secret})
        self.advance(60)
        hooks.handle_prompt({"session_id": "s", "prompt": "write an email about the Zorblax deal"})
        html = dashboard.render(dashboard.build())
        self.assertNotIn("Zorblax", html)
        self.assertNotIn("merger", html)

    def test_nothing_on_the_page_reads_like_monitoring(self):
        d = dashboard.build()
        blob = json.dumps(d).lower()
        for word in ("hour", "session_id", "ip address", "timestamp"):
            self.assertNotIn(word, blob, word)


class DashboardEntryPoints(CoachTestCase):
    def test_cli_writes_the_demo_and_leaves_real_data_alone(self):
        import coach
        hooks.handle_prompt({"session_id": "s", "prompt": RICH})
        before = store.read_events()
        out = os.path.join(self.tmp, "demo.html")
        self.assertEqual(coach.main(["coach.py", "dashboard", "--demo", "--no-open", "--out", out]), 0)
        with open(out, encoding="utf-8") as f:
            self.assertGreater(len(data_of(f.read())["rows"]), 30)
        self.assertEqual(store.read_events(), before)
        self.assertEqual(os.environ.get("PROMPT_COACH_HOME"), self.tmp)

    def test_chat_tool_opens_the_dashboard(self):
        demo.seed_history(weeks=2, now=self.t)
        server = mcp_server.Server(open_browser=False)
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "coach_score", "arguments": {"format": "dashboard"}}})
        text = reply["result"]["content"][0]["text"]
        self.assertIn("dashboard is open", text)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "dashboard.html")))
