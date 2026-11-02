# Changelog

Versions of the Prompt Coach plugin (`coach/`). Dates are commit dates.

## 0.5.5 (2026-11-02)

- Memory comes first in Chat and Cowork. Claude refuses to update its memory once a connected tool has run in the
  conversation (its own explanation; the rule isn't documented), and the coach's helper is one, so "save this to
  memory" used to end in "nothing has been saved". Now the helper's instructions put a memory update before any
  coach call (so a save asked for in a conversation's first message should go through), a "save to memory"
  message is neither scored nor coached, and when a save is refused the coach has Claude say why in one line,
  hand over the note as a block to paste as the first message of a new conversation, and offer a file instead.
  To get this in Chat and Cowork: with the Windows setup program, install the new `PromptCoachSetup.exe`; from a
  clone connected with `setup_desktop.py`, `git pull`, then quit and reopen Claude (the helper hands Claude its
  instructions when it starts). Everyone: upload the new `prompt-coach-chat-skill.zip` under *Customize >
  Skills* in place of the old one, and if you pasted the one-liner into *Settings > Account*, add its new
  sentence: "If I ask you to save something to memory, do that first."
- `setup_desktop.py` finds Claude's settings where current versions keep them (`%LOCALAPPDATA%\Claude-Data`);
  before, `--check` reported the coach as not connected on such a machine, and a connect would have written to
  the old folder.

## 0.5.4 (2026-10-31)

- The dashboard has an Auto / Light / Dark switch, remembered per browser; before, it only followed the system.
- Docs reconciled after a full read-through: chat and Cowork are recorded as confirmed by hand on Windows
  everywhere; the Mac instructions say `python3` and how to quit Claude on a Mac; the simulated-pilot numbers,
  the level gates, the two-week rule for losing a level, and the test counts match the code; the install fallbacks
  point at the GitHub release instead of a build step; the plugin zip no longer carries the build scripts.

## 0.5.3 (2026-10-28)

- The dashboard page is made when the coach is installed (Windows setup, the chat setup, the guided installers)
  or at the first session, so the Start menu shortcut and a bookmark work from the first day. The first welcome
  note and the scoreboard show where it is.
- A sample dashboard, built from made-up history, is published to GitHub Pages on every push so people can see
  it without installing anything; the sample says it is one.
- Releases: pushing a version tag builds the Windows setup program and the zips and attaches them to a GitHub
  Release, which the README's download link points at.
- Docs: the README leads with the problem and what is and isn't proven; the startup glossary and early interview
  notes moved to `docs/history/`; this changelog.

## 0.5.2 (2026-10-16)

- A background-task notice or system reminder that Claude Code hands to the prompt hook is no longer scored
  as if the user typed it.

## 0.5.1 (2026-10-16)

- A question is never counted as an answer to a tip ("so now do I have to reinstall" no longer earns a cheer).

## 0.5.0 (2026-10-16)

- Every tip ends in exactly one of five outcomes: said yes, answered in your own words (by replying, or by rewriting
  the request to include what it asked for), declined, didn't fit, or passed over. The first two count as taken.
- Tips come half as often: every 4th prompt for Beginners, 6th for Practitioners, 10th for Advanced, 16th for
  Experts. Safety warnings and the bare-request tip are still immediate.
- Every line the coach says is italic, marked with the light-bulb emoji and a bold "Prompt Coach:" label.

## 0.4.2 (2026-09-29)

- The streak reads the same everywhere (welcome note, scoreboard, dashboard) and as it stands today; a lapsed
  streak reads 0. A missed working day always breaks it. Growth is announced the day it happens.
- The saved dashboard and summary files are kept current once they exist.
- Claude desktop chat starts the coach by itself (one line in Claude's instructions).

## 0.4.1 (2026-09-29)

- The browser extension and its era are gone; the project is the Claude plugin only. The packaged `.mcpb`
  installer is removed: `setup_desktop.py` is the one way to connect Claude desktop chat.

## 0.4.0 (2026-09-28)

- A personal dashboard of your AI habits over time (`/prompt-coach:dashboard`): score ring, what changed
  between earlier and recent messages, weekly recap, score over time with a goal line, habit gaps with
  before/after examples, usage by week or day, streak calendar and badges. One local file, no network.
- Public one-pager on the coaching loop (`docs/COACHING-LOOP.md`).

## 0.3.1 (2026-09-28)

- Claude's own scratch notes (a drafted commit message in a temp folder) no longer trigger the first-draft nudge.

## 0.3.0 (2026-09-28)

- All 76 recommendations live in `coach/library/recommendations.md` (when / recommend / action), validated by
  `coach.py library`.
- 27 named trigger detectors, measured against 220 labeled prompts (`coach.py eval`). Blind-set results are
  recorded in the docs.
- A "yes" to a tip makes the AI carry out the recommendation. Declining twice mutes a tip for two weeks;
  "doesn't fit" mutes it for a month and counts as a false positive.
- Pilot mode (`settings experiment 20`) and `coach.py insights` to measure whether coaching changes behavior.
- Desktop chat setup applies its change while Claude is closed (`setup_desktop.py --wait`).

## 0.2.0 (2026-09-25)

- Claude desktop chat and Cowork: a local helper (MCP server, standard library only) that reuses the hook engine,
  with a shared profile and cross-channel de-duplication.

## 0.1.0 (2026-09-25)

- First release of the plugin: hooks, skills and a coach agent; coaching by asking; generated-document
  detection and revision nudges; local, behavior-based AI Fluency levels with streaks, achievements, a
  shareable summary and a badge. Python standard library only.
