# Prompt Coach: the coach that lives inside Claude

A plugin that gives your AI a built-in **coach**. It doesn't rewrite your prompts. It asks
the right question at the right moment so you learn to use AI well, nudges you to **revise the
decks, PDFs and documents the AI makes for you**, remembers how you've been doing, and turns that
into an **AI Fluency level** (Beginner, Practitioner, Advanced, Expert) you can show a manager.

Built for people who are **not coders and never learned how to use AI**, at work.

```
You:    write me a poem about the sea
Claude: (writes the poem)
        ...
        Coach: Who is this poem for, and what should they feel when they read it?
```

```
Claude: I've put together Board Update.pptx (8 slides) ...
        Coach: Treat that as a first draft. What would your CFO push back on first?
You:    cut the market slide and lead with the hiring cost
        Prompt Coach: Achievement unlocked: Second draft.
```

## Install

**Claude Code (terminal, VS Code, desktop Code tab):**

```bash
claude plugin marketplace add amrogers2007/prompt-coach
claude plugin install prompt-coach@prompt-coach
```

Or run the guided installer, which also checks your setup: `sh install/install.sh`
(macOS/Linux/Git Bash) or `powershell -ExecutionPolicy Bypass -File install\install.ps1` (Windows).

**Claude desktop app (Cowork):** run `python coach/scripts/build_zip.py`, then in the app open
*Customize > Plugins > Add > Upload plugin* and choose `dist/prompt-coach-plugin.zip`. Hooks,
agents and skills load in Cowork; see "Where it runs" below for the caveats.

**Try it without installing:** `claude --plugin-dir ./coach`

Requires Python 3.8+ on the machine (standard library only, nothing to `pip install`).
Then just work as usual. The coach starts on its own.

## What you'll see

| Moment | What happens |
|---|---|
| Session start | One-line welcome ("Beginner, 3-day streak"). |
| Every few prompts | Your AI ends a reply with **one** short coaching question. Beginners hear from it about every 2 prompts, experts about every 8. |
| A bare request | A prompt with no context from a newer user gets coached right away. |
| A file is generated | The AI treats it as a first draft and asks how to improve it. After you revise it, it asks whether it's closer. |
| Sensitive data pasted | A gentle heads-up (keys, SSNs, cards, passwords, "confidential"). |
| Something good happens | A small toast: level-up, streak, achievement. |

Commands (all optional):

| Command | What it does |
|---|---|
| `/prompt-coach:score` | Your scoreboard, what's between you and the next level, and a **shareable summary** + badge for your manager. |
| `/prompt-coach:coach` | Ask for coaching on demand. |
| `/prompt-coach:practice` | A 3-minute practice round. Never affects your score. |
| `/prompt-coach:settings` | Pause (`pause 2h`), `resume`, `off`, `intensity light\|normal\|frequent`, `export`, `reset`, `doctor`. |
| The `coach` agent | Ask "how am I doing overall?" for a fuller check-up and a 3-step plan. |

## How your level works

It's **behavior-based**: computed from what you actually do, not a quiz, over your most recent 60
prompts and 12 generated documents. Six habits, weighted:

| Habit | Weight | Earned by |
|---|---|---|
| Context up front | 30% | Saying who it's for, what it's for, your situation, background |
| Revising drafts | 30% | Revising AI-made documents instead of accepting the first draft (a specific revision counts more than "make it better") |
| Specific asks | 15% | Naming format, length, tone, limits |
| Checking the AI | 10% | Asking for sources, confidence, or a critique |
| Right feature | 10% | Referencing files / editing in place instead of pasting walls of text |
| Showing up | 5% | Using it on more than one day |

Sensitive data in prompts costs points (up to 10).

Levels are deliberately hard and **can go down** if habits slip:

| Level | Needs |
|---|---|
| 1 Beginner | Everyone starts here |
| 2 Practitioner | Score 30+, 8+ prompts |
| 3 Advanced | Score 55+, 25+ prompts on 4+ days, 3+ documents revised |
| 4 Expert | Score 78+, 60+ prompts on 10+ days, 8+ documents with at least 70% revised, no sensitive-data flags |

A level is only lost when you fall about 6 points **below** its gate, so one off day doesn't flip it.
The window counts prompts, not calendar days, so a vacation doesn't cost you a level.

Streaks count working days (weekends don't break one) with at least one good-habit moment: a
context-rich request or a revision.

## Privacy

- **Local only.** Everything lives in `~/.prompt-coach` (override with `PROMPT_COACH_HOME`). Nothing is sent anywhere by this plugin.
- **No prompt text is ever stored.** Only small numbers ("context score 0.7"), counts, the *kind* of document generated ("deck"), and a hash used to recognize the same file.
- The shareable summary and `export` contain aggregate numbers only.
- `settings reset --yes` deletes everything.
- Honest limit: the score is measured on your own device, so today it's self-reported, not tamper-proof. A verified team version is future work (see `docs/COACH-DESIGN.md`).

## Where it runs

| Surface | Status |
|---|---|
| Claude Code (terminal, IDE, desktop Code tab) | Full: hooks, coaching, file detection, score. Tested. |
| Claude desktop app, Cowork | Hooks, agents and skills load there too per Anthropic's plugin docs. Not yet tested by hand; confirm the machine/sandbox has Python 3.8+ (run `/prompt-coach:settings doctor`). |
| claude.ai chat | Skills only (`/score`, `/coach`, `/practice`); hooks aren't loaded in chat, so no automatic coaching there. |
| ChatGPT, Copilot, Gemini | Not supported by this plugin. The browser extension in `../extension` covers those websites. |

## Limits worth knowing

- Scoring is heuristic (keyword and structure signals), tuned to be fair on average, not perfect on any one prompt.
- The coach can only see what hooks can: it can't read the AI's reply to judge it, so "did you accept the draft?" is inferred from your next prompt.
- The coaching question is delivered *by the AI following an instruction*, so it can occasionally skip or word it differently.
- Document detection covers Office files and PDFs (and larger Markdown/HTML written directly). Files made by unusual tools may be missed.

## Develop

```bash
python -m unittest discover -s coach/tests -v     # 96 tests, standard library only
claude plugin validate ./coach                    # manifest + skills check
claude --plugin-dir ./coach                       # run it live
PROMPT_COACH_HOME=/tmp/demo python coach/scripts/coach.py demo    # sample profile
PROMPT_COACH_HOME=/tmp/demo python coach/scripts/coach.py score   # see the scoreboard
python coach/scripts/build_zip.py                 # package for Claude desktop upload
```

Layout: `scripts/pcoach/signals.py` (what a prompt reveals), `scoring.py` (score + levels),
`cadence.py` (when to speak), `lessons.py` (micro-training + instructions), `game.py` (XP/streaks/achievements),
`hooks.py` (the three hook handlers), `report.py` (scoreboard, badge, export), `store.py` (local storage).
