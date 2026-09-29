"""The streak, tested end to end: how it is counted, and that every place that
shows it (welcome note, scoreboard, dashboard, toasts) agrees with the others.

Dates used: Mon 2026-01-05 ... Fri 2026-01-09, weekend 10/11, Mon 2026-01-12 ...
"""

import datetime
import json
import os
import random
import subprocess
import sys
import unittest

from helpers import BARE, RICH, SCRIPTS, CoachTestCase

from pcoach import dashboard, game, hooks, mcp_server, report, store

COACH = os.path.join(SCRIPTS, "coach.py")


def at(day, hour=12, minute=0):
    """Local-time timestamp for 'YYYY-MM-DD'."""
    d = datetime.date.fromisoformat(day)
    return datetime.datetime(d.year, d.month, d.day, hour, minute).timestamp()


def plus(day, n):
    return (datetime.date.fromisoformat(day) + datetime.timedelta(days=n)).isoformat()


def context_of(out):
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")


def said(out):
    """Everything the user would be shown from a hook result."""
    return ((out or {}).get("systemMessage") or "") + context_of(out)


def reference_streak(good_days, today):
    """An independent, deliberately plain re-count from a list of good-habit days."""
    count, best, prev = 0, 0, None
    for day in sorted(set(good_days)):
        d = datetime.date.fromisoformat(day)
        if prev is None:
            count = 1
        else:
            missed, x = 0, prev + datetime.timedelta(days=1)
            while x < d:
                missed += 1 if x.weekday() < 5 else 0
                x += datetime.timedelta(days=1)
            count = count + 1 if missed == 0 else 1
        best, prev = max(best, count), d
    if prev is not None:
        missed, x = 0, prev + datetime.timedelta(days=1)
        end = datetime.date.fromisoformat(today)
        while x < end:
            missed += 1 if x.weekday() < 5 else 0
            x += datetime.timedelta(days=1)
        if missed:
            count = 0
    return count, best


class Counting(CoachTestCase):
    def touch(self, day, hour=12, minute=0):
        return game.touch_streak(self.state, at(day, hour, minute))

    def setUp(self):
        super().setUp()
        self.state = store.default_state()

    def test_a_full_working_week(self):
        grew = [self.touch("2026-01-0%d" % d) for d in (5, 6, 7, 8, 9)]
        self.assertEqual(grew, [1, 2, 3, 4, 5])
        self.assertEqual(self.state["streak"], {"count": 5, "best": 5, "last_day": "2026-01-09"})

    def test_same_day_counts_once(self):
        self.assertEqual(self.touch("2026-01-05", 9), 1)
        for hour in (10, 13, 23):
            self.assertIsNone(self.touch("2026-01-05", hour))
        self.assertEqual(self.state["streak"]["count"], 1)

    def test_midnight_starts_a_new_day(self):
        self.assertEqual(self.touch("2026-01-05", 23, 59), 1)
        self.assertEqual(self.touch("2026-01-06", 0, 1), 2)

    def test_weekend_off_does_not_break_it(self):
        self.touch("2026-01-09")                                   # Friday
        self.assertEqual(self.touch("2026-01-12"), 2)              # Monday

    def test_weekend_days_count_when_used(self):
        self.touch("2026-01-09")
        self.assertEqual(self.touch("2026-01-10"), 2)              # Saturday
        self.assertEqual(self.touch("2026-01-11"), 3)              # Sunday
        self.assertEqual(self.touch("2026-01-12"), 4)              # Monday

    def test_a_missed_working_day_resets(self):
        self.touch("2026-01-05")
        self.touch("2026-01-06")
        self.assertEqual(self.touch("2026-01-08"), 1)              # skipped Wednesday
        self.assertEqual(self.state["streak"]["best"], 2)

    def test_missing_friday_breaks_it_even_across_a_weekend(self):
        self.touch("2026-01-08")                                   # Thursday
        self.assertEqual(self.touch("2026-01-12"), 1)              # Monday, Friday was missed

    def test_missing_friday_is_not_forgiven_by_weekend_use(self):
        self.touch("2026-01-07")
        self.touch("2026-01-08")                                   # Thursday: 2
        self.assertEqual(self.touch("2026-01-10"), 1)              # Saturday, Friday was missed
        self.state["streak"] = {"count": 2, "best": 2, "last_day": "2026-01-08"}
        self.assertEqual(self.touch("2026-01-11"), 1)              # same on Sunday

    def test_a_clock_that_goes_backwards_never_adds_a_day(self):
        self.touch("2026-01-05")
        self.touch("2026-01-06")
        self.assertIsNone(self.touch("2026-01-02"))
        self.assertEqual(self.state["streak"], {"count": 2, "best": 2, "last_day": "2026-01-06"})

    def test_a_damaged_date_does_not_freeze_the_streak(self):
        for bad in ("not-a-date", "2026-13-45", 20260105, None):
            self.state["streak"] = {"count": 4, "best": 4, "last_day": bad}
            self.assertEqual(game.current_streak(self.state, at("2026-01-05")), 0, bad)
            self.assertEqual(self.touch("2026-01-05"), 1, bad)
            self.assertEqual(self.state["streak"]["best"], 4)

    def test_missing_fields_are_tolerated(self):
        self.state["streak"] = {}
        self.assertEqual(game.current_streak(self.state, at("2026-01-05")), 0)
        self.assertEqual(self.touch("2026-01-05"), 1)
        self.assertEqual(self.state["streak"]["best"], 1)

    def test_thirty_working_days(self):
        day, n = "2026-01-05", 0
        while n < 30:
            if datetime.date.fromisoformat(day).weekday() < 5:
                n += 1
                self.assertEqual(self.touch(day), n)
            day = plus(day, 1)
        self.assertEqual(self.state["streak"]["best"], 30)


class CurrentStreak(CoachTestCase):
    """What is shown must be the streak as it stands *now*, not as it stood on the last good day."""

    def state_with(self, count, last_day, best=None):
        st = store.default_state()
        st["streak"] = {"count": count, "best": best or count, "last_day": last_day}
        return st

    def test_alive_today_and_the_next_working_day(self):
        st = self.state_with(3, "2026-01-07")                      # Wednesday
        self.assertEqual(game.current_streak(st, at("2026-01-07")), 3)
        self.assertEqual(game.current_streak(st, at("2026-01-08", 23, 59)), 3)

    def test_gone_after_a_missed_working_day(self):
        st = self.state_with(3, "2026-01-07")
        self.assertEqual(game.current_streak(st, at("2026-01-09", 0, 1)), 0)
        self.assertEqual(game.current_streak(st, at("2026-03-01")), 0)

    def test_friday_streak_lasts_through_monday(self):
        st = self.state_with(5, "2026-01-09")
        for day in ("2026-01-10", "2026-01-11", "2026-01-12"):
            self.assertEqual(game.current_streak(st, at(day)), 5, day)
        self.assertEqual(game.current_streak(st, at("2026-01-13")), 0)

    def test_thursday_streak_is_gone_by_the_weekend(self):
        st = self.state_with(2, "2026-01-08")
        self.assertEqual(game.current_streak(st, at("2026-01-09")), 2)     # Friday: still time
        self.assertEqual(game.current_streak(st, at("2026-01-10")), 0)     # Saturday: Friday was missed

    def test_status_says_whether_today_is_counted(self):
        st = self.state_with(2, "2026-01-06", best=6)
        self.assertEqual(game.streak_status(st, at("2026-01-06")),
                         {"count": 2, "best": 6, "today": True, "alive": True})
        self.assertEqual(game.streak_status(st, at("2026-01-07")),
                         {"count": 2, "best": 6, "today": False, "alive": True})
        self.assertEqual(game.streak_status(st, at("2026-01-08")),
                         {"count": 0, "best": 6, "today": False, "alive": False})

    def test_never_started(self):
        self.assertEqual(game.current_streak(store.default_state(), at("2026-01-05")), 0)


class Toasts(unittest.TestCase):
    def test_every_new_streak_day_is_announced_from_day_two(self):
        self.assertEqual(game.toast_lines(0, 1, [], 1), [])
        for n in (2, 4, 6, 8, 9, 11):
            self.assertEqual(game.toast_lines(0, n, [], 1), ["Streak: %d days in a row." % n])

    def test_milestones_get_the_bigger_line(self):
        for n in (3, 5, 7, 10, 14, 20, 30):
            self.assertEqual(game.toast_lines(0, n, [], 1), ["%d-day streak of good AI habits." % n])

    def test_no_growth_no_line(self):
        self.assertEqual(game.toast_lines(0, None, [], 1), [])

    def test_still_at_most_two_lines(self):
        self.assertEqual(len(game.toast_lines(1, 4, ["Second draft", "Fact checker"], 2)), 2)


class ThroughTheHooks(CoachTestCase):
    def send(self, text, day, hour=12, sid="sess-streak-0001", variation=None):
        self.t = at(day, hour)
        if variation is not None:
            text = "%s (version %s)" % (text, variation)
        return hooks.handle_prompt({"session_id": sid, "prompt": text})

    def streak(self):
        return store.load_state()["streak"]

    def test_rich_request_is_a_good_habit_and_a_bare_one_is_not(self):
        self.send(BARE, "2026-01-05")
        self.assertEqual(self.streak()["count"], 0)
        self.send(RICH, "2026-01-05", 13)
        self.assertEqual(self.streak()["count"], 1)

    def test_four_days_in_a_row(self):
        for i, day in enumerate(("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08")):
            self.send(BARE, day, 9, variation=i)
            self.send(RICH, day, 10, variation=i)
            self.send(RICH, day, 15, variation="again %d" % i)
            self.assertEqual(self.streak()["count"], i + 1)
        self.assertEqual(self.streak(), {"count": 4, "best": 4, "last_day": "2026-01-08"})

    def test_a_day_of_only_bare_requests_breaks_it(self):
        self.send(RICH, "2026-01-05")
        self.send(RICH, "2026-01-06", variation=1)
        self.send(BARE, "2026-01-07")
        self.assertEqual(game.current_streak(store.load_state(), at("2026-01-07")), 2)   # still alive that day
        self.send(RICH, "2026-01-08", variation=2)
        self.assertEqual(self.streak()["count"], 1)

    def test_growth_is_announced_the_moment_it_happens(self):
        self.send(RICH, "2026-01-05")
        self.assertIn("Streak: 2 days in a row.", said(self.send(RICH, "2026-01-06", variation=1)))
        self.assertIn("3-day streak of good AI habits.", said(self.send(RICH, "2026-01-07", variation=2)))
        self.assertNotIn("treak", said(self.send(RICH, "2026-01-07", 15, variation=3)))   # once a day

    def test_streak_badge_is_earned_on_day_three(self):
        for i, day in enumerate(("2026-01-05", "2026-01-06", "2026-01-07")):
            self.assertNotIn("streak_3", store.load_state()["achievements"])
            self.send(RICH, day, variation=i)
        self.assertIn("streak_3", store.load_state()["achievements"])

    def test_hook_and_chat_helper_share_one_streak(self):
        server = mcp_server.Server(open_browser=False)
        self.send(RICH, "2026-01-05")
        self.t = at("2026-01-05", 12)
        server.call_tool("coach_turn", {"message": RICH})                      # same message, other channel
        self.assertEqual(store.load_state()["totals"]["prompts"], 1)
        self.t = at("2026-01-06")
        server.call_tool("coach_turn", {"message": RICH + " (tuesday)"})
        self.assertEqual(self.streak()["count"], 2)
        self.send(RICH, "2026-01-07", variation="wednesday")
        self.assertEqual(self.streak()["count"], 3)
        self.t = at("2026-01-08")
        server.call_tool("coach_turn", {"message": RICH + " (thursday)"})
        self.assertEqual(self.streak(), {"count": 4, "best": 4, "last_day": "2026-01-08"})

    def test_coach_switched_off_changes_nothing(self):
        self.send(RICH, "2026-01-05")
        st = store.load_state()
        st["settings"]["enabled"] = False
        store.save_state(st)
        self.send(RICH, "2026-01-06", variation=1)
        self.assertEqual(self.streak()["count"], 1)


class WelcomeNote(CoachTestCase):
    def seed(self, count, last_day, best=None):
        st = store.load_state()
        st["welcomed"] = True
        st["streak"] = {"count": count, "best": best or count, "last_day": last_day}
        store.save_state(st)

    def welcome(self, day, hour=9):
        self.t = at(day, hour)
        return said(hooks.handle_session({"session_id": "welcome-%s-%d" % (day, hour)}))

    def test_today_already_counted(self):
        self.seed(3, "2026-01-07")
        text = self.welcome("2026-01-07", 16)
        self.assertIn("3-day streak", text)
        self.assertNotIn("makes it", text)

    def test_today_not_counted_yet_says_what_will_move_it(self):
        self.seed(2, "2026-01-06")
        text = self.welcome("2026-01-07")
        self.assertIn("2-day streak", text)
        self.assertIn("makes it 3", text)

    def test_one_day_streak_waiting_for_day_two(self):
        self.seed(1, "2026-01-06")
        self.assertIn("makes it 2", self.welcome("2026-01-07"))

    def test_a_broken_streak_is_not_shown_as_if_it_were_alive(self):
        self.seed(2, "2026-01-05")
        text = self.welcome("2026-01-08")
        self.assertNotIn("2-day streak", text)
        self.assertNotIn("makes it", text)
        self.assertIn("Welcome back", text)

    def test_monday_morning_after_a_friday_streak(self):
        self.seed(4, "2026-01-09")
        text = self.welcome("2026-01-12")
        self.assertIn("4-day streak", text)
        self.assertIn("makes it 5", text)

    def test_the_note_stays_one_line(self):
        self.seed(2, "2026-01-06")
        self.t = at("2026-01-07")
        st = store.load_state()
        st["settings"]["toasts"] = "chat"
        store.save_state(st)
        note = context_of(hooks.handle_session({"session_id": "one-line-note-1"}))
        starred = [l for l in note.splitlines() if l.startswith("*Prompt Coach:")]
        self.assertEqual(len(starred), 1)
        self.assertTrue(starred[0].endswith("*"))


class EveryPlaceAgrees(CoachTestCase):
    """The scoreboard, the export, the dashboard and the welcome note all show the same number."""

    def shown_everywhere(self, day, hour=12):
        self.t = at(day, hour)
        state = store.load_state()
        r = report.build()
        d = dashboard.build()
        exported = json.loads(report.export_json(r))
        return {
            "game": game.current_streak(state, self.t),
            "score": r["streak"]["current"],
            "export": exported["streak"]["current"],
            "dashboard": d["current"]["streak"],
        }, r, d

    def assert_all(self, day, expected, hour=12):
        shown, r, d = self.shown_everywhere(day, hour)
        self.assertEqual(set(shown.values()), {expected}, "%s: %r" % (day, shown))
        return r, d

    def send(self, text, day, hour=12, variation=""):
        self.t = at(day, hour)
        hooks.handle_prompt({"session_id": "agree-sess-0001", "prompt": "%s %s" % (text, variation)})

    def test_while_it_grows_and_after_it_lapses(self):
        for i, day in enumerate(("2026-01-05", "2026-01-06", "2026-01-07")):
            self.send(RICH, day, 10, i)
            self.assert_all(day, i + 1, 11)
        self.assert_all("2026-01-08", 3)                 # next working day, nothing yet: still alive
        r, d = self.assert_all("2026-01-09", 0)          # Thursday was missed
        self.assertEqual(r["streak"]["best"], 3)
        self.assertEqual(d["current"]["best_streak"], 3)
        self.assertIn("Streak: **0** days in a row (best 3)", report.render_text(r))
        self.assertNotIn("-day streak", report.summary_sentence(r))

    def test_scoreboard_text_and_summary_use_the_live_number(self):
        self.send(RICH, "2026-01-05")
        self.send(RICH, "2026-01-06", variation=1)
        self.t = at("2026-01-06", 13)
        r = report.build()
        self.assertIn("Streak: **2** days in a row (best 2)", report.render_text(r))
        self.assertIn("2-day streak", report.summary_sentence(r))

    def test_dashboard_says_whether_today_counts(self):
        self.send(RICH, "2026-01-05")
        self.t = at("2026-01-05", 13)
        self.assertTrue(dashboard.build()["current"]["streak_today"])
        self.t = at("2026-01-06", 9)
        self.assertFalse(dashboard.build()["current"]["streak_today"])

    def test_dashboard_calendar_matches_the_streak(self):
        days = ("2026-01-05", "2026-01-06", "2026-01-07")
        for i, day in enumerate(days):
            self.send(BARE, day, 9, i)
            self.send(RICH, day, 10, i)
        self.send(BARE, "2026-01-08", 9, "thursday")
        self.t = at("2026-01-08", 10)
        rows = {r["day"]: r for r in dashboard.build()["rows"]}
        self.assertEqual([d for d in sorted(rows) if rows[d]["good_day"]], list(days))
        self.assertFalse(rows["2026-01-08"]["good_day"])

    def test_sixty_random_days_match_an_independent_count(self):
        rnd = random.Random(2026)
        for trial in range(6):
            store.reset()
            day, good = "2026-02-02", []
            for n in range(60):
                weekday = datetime.date.fromisoformat(day).weekday()
                roll = rnd.random()
                used = roll < (0.35 if weekday >= 5 else 0.9)
                if used:
                    self.send(BARE, day, 9, "%d-%d" % (trial, n))
                    if rnd.random() < 0.75:
                        self.send(RICH, day, 10 + rnd.randrange(8), "%d-%d" % (trial, n))
                        good.append(day)
                        if rnd.random() < 0.4:
                            self.send(RICH, day, 20, "%d-%d-late" % (trial, n))
                want, best = reference_streak(good, day)
                shown, r, d = self.shown_everywhere(day, 23)
                self.assertEqual(set(shown.values()), {want}, "trial %d, %s: %r" % (trial, day, shown))
                self.assertEqual(r["streak"]["best"], best, "trial %d, %s" % (trial, day))
                self.assertEqual(d["current"]["best_streak"], best)
                logged = sorted(row["day"] for row in d["rows"] if row["good_day"])
                self.assertEqual(logged, sorted(set(good)))
                day = plus(day, 1)


class SavedPagesStayFresh(CoachTestCase):
    """The dashboard and summary are files. Once made, they are kept up to date so
    an open tab or a bookmark never shows an old streak."""

    def send(self, text, day, hour=12, variation=""):
        self.t = at(day, hour)
        return hooks.handle_prompt({"session_id": "fresh-sess-0001", "prompt": "%s %s" % (text, variation)})

    def page_streak(self):
        with open(dashboard.default_path(), encoding="utf-8") as f:
            page = f.read()
        start = page.index('"current": {')
        return json.loads(page[start + len('"current": '):page.index("}", start) + 1])["streak"]

    def test_nothing_is_written_until_the_user_has_made_them(self):
        self.send(RICH, "2026-01-05")
        hooks.handle_session({"session_id": "fresh-sess-0002"})
        self.assertFalse(os.path.exists(dashboard.default_path()))
        self.assertFalse(os.path.exists(os.path.join(store.home(), "summary.md")))

    def test_dashboard_file_follows_the_streak(self):
        self.send(RICH, "2026-01-05")
        dashboard.write(open_browser=False)
        self.assertEqual(self.page_streak(), 1)
        self.send(RICH, "2026-01-06", variation=1)
        self.assertEqual(self.page_streak(), 2)

    def test_dashboard_file_is_refreshed_when_a_session_starts(self):
        self.send(RICH, "2026-01-05")
        self.send(RICH, "2026-01-06", variation=1)
        dashboard.write(open_browser=False)
        self.t = at("2026-01-09")                          # streak has lapsed since
        hooks.handle_session({"session_id": "fresh-sess-0003"})
        self.assertEqual(self.page_streak(), 0)

    def test_summary_file_follows_the_streak(self):
        self.send(RICH, "2026-01-05")
        report.write_shareables(report.build())
        self.send(RICH, "2026-01-06", variation=1)
        with open(os.path.join(store.home(), "summary.md"), encoding="utf-8") as f:
            self.assertIn("Streak: **2** days in a row", f.read())

    def test_a_refresh_that_fails_never_breaks_the_session(self):
        self.send(RICH, "2026-01-05")
        dashboard.write(open_browser=False)
        old = dashboard.build
        dashboard.build = lambda *a, **k: 1 / 0
        try:
            out = self.send(RICH, "2026-01-06", variation=1)
        finally:
            dashboard.build = old
        self.assertIn("Streak: 2 days in a row.", said(out))
        self.assertEqual(store.load_state()["streak"]["count"], 2)


class ChatStartsOnItsOwn(CoachTestCase):
    """In chat, Claude has to call the coach. If it skips coach_start, the first
    coach_turn of the conversation carries the greeting, so the coach still opens by itself."""

    def setUp(self):
        super().setUp()
        self.server = mcp_server.Server(open_browser=False)

    def test_first_turn_greets_when_start_was_skipped(self):
        text = self.server.call_tool("coach_turn", {"message": RICH})
        self.assertIn("I'm your AI coach", text)
        self.assertIn("at the very start", text)
        again = self.server.call_tool("coach_turn", {"message": RICH + " second"})
        self.assertNotIn("I'm your AI coach", again)

    def test_no_double_greeting_when_start_was_called(self):
        self.assertIn("I'm your AI coach", self.server.call_tool("coach_start", {}))
        self.assertNotIn("I'm your AI coach", self.server.call_tool("coach_turn", {"message": RICH}))

    def test_the_greeted_first_turn_still_counts_and_coaches(self):
        text = self.server.call_tool("coach_turn", {"message": BARE})
        self.assertIn("I'm your AI coach", text)
        st = store.load_state()
        self.assertEqual(st["totals"]["prompts"], 1)

    def test_a_trivial_first_message_still_greets(self):
        text = self.server.call_tool("coach_turn", {"message": "hi"})
        self.assertIn("I'm your AI coach", text)

    def test_a_draft_made_before_the_first_turn_is_kept(self):
        self.server.call_tool("coach_document", {"kind": "deck", "name": "Board Update"})
        self.advance(30)
        text = self.server.call_tool("coach_turn", {"message": "make slide 2 shorter and add costs"})
        self.assertNotIn("I'm your AI coach", text)
        self.assertEqual(store.load_state()["totals"]["revisions"], 1)

    def test_no_second_greeting_when_the_plugin_already_handled_the_message(self):
        hooks.handle_session({"session_id": "code-session-1"})
        hooks.handle_prompt({"session_id": "code-session-1", "prompt": RICH})
        text = self.server.call_tool("coach_turn", {"message": RICH})
        self.assertNotIn("AI coach", text)
        self.assertEqual(store.load_state()["totals"]["prompts"], 1)

    def test_greeting_carries_the_streak(self):
        st = store.load_state()
        st["welcomed"] = True
        st["streak"] = {"count": 2, "best": 2, "last_day": "2026-01-06"}
        store.save_state(st)
        self.t = at("2026-01-07")
        text = self.server.call_tool("coach_turn", {"message": BARE})
        self.assertIn("2-day streak", text)
        self.assertIn("makes it 3", text)

    def test_switched_off_stays_silent(self):
        st = store.load_state()
        st["settings"]["enabled"] = False
        store.save_state(st)
        text = self.server.call_tool("coach_turn", {"message": RICH})
        self.assertNotIn("AI coach", text)


class RealProcesses(CoachTestCase):
    """The real entry point, as Claude runs it: separate processes, real clock."""

    def run_hook(self, name, payload):
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp, CLAUDE_CODE_ENTRYPOINT="claude-desktop")
        return subprocess.run([sys.executable, COACH, name], input=json.dumps(payload), env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=60)

    def seed(self, count, days_ago):
        store.now = self._old_now
        today = datetime.date.today()
        last, left = today, days_ago
        while left:                                        # step back over working days only
            last -= datetime.timedelta(days=1)
            left -= 1 if last.weekday() < 5 else 0
        st = store.default_state()
        st["welcomed"] = True
        st["streak"] = {"count": count, "best": count, "last_day": last.isoformat()}
        store.save_state(st)

    def test_yesterdays_streak_grows_today_and_says_so(self):
        self.seed(2, 1)
        p = self.run_hook("session", {"session_id": "real-0001"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("makes it 3", p.stdout)
        p = self.run_hook("prompt", {"session_id": "real-0001", "prompt": RICH})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("3-day streak of good AI habits.", p.stdout)
        self.assertEqual(store.load_state()["streak"]["count"], 3)
        p = self.run_hook("session", {"session_id": "real-0002"})
        self.assertIn("3-day streak", p.stdout)
        self.assertNotIn("makes it", p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "errors.log")))

    def test_a_lapsed_streak_restarts_at_one(self):
        self.seed(6, 3)
        p = self.run_hook("session", {"session_id": "real-0003"})
        self.assertNotIn("6-day streak", p.stdout)
        self.run_hook("prompt", {"session_id": "real-0003", "prompt": RICH})
        st = store.load_state()["streak"]
        self.assertEqual((st["count"], st["best"]), (1, 6))

    def test_many_sessions_at_once_count_the_day_once(self):
        self.seed(2, 1)
        env = dict(os.environ, PROMPT_COACH_HOME=self.tmp)
        procs = []
        for i in range(8):
            p = subprocess.Popen([sys.executable, COACH, "prompt"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8")
            p.stdin.write(json.dumps({"session_id": "race-%04d" % i, "prompt": "%s (window %d)" % (RICH, i)}))
            p.stdin.close()
            procs.append(p)
        for p in procs:
            p.wait(timeout=60)
            p.stdout.close()
            p.stderr.close()
        st = store.load_state()
        self.assertEqual(st["streak"], {"count": 3, "best": 3, "last_day": datetime.date.today().isoformat()})
        # (On a very busy machine a process may give up waiting for the lock, so the
        # message total is checked loosely here; test_hooks covers the lock itself.)
        self.assertTrue(1 <= st["totals"]["prompts"] <= 8, st["totals"]["prompts"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "errors.log")))


if __name__ == "__main__":
    unittest.main()
