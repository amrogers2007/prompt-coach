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
        *Prompt Coach: Who is this poem for, and what should they feel when they read it?*
```

```
Claude: I've put together Board Update.pptx (8 slides) ...
        *Prompt Coach: Treat that as a first draft. What would your CFO push back on first?*
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

**Claude desktop app, Chat and Cowork:** chat can't run hooks, so there the coach is a small local
helper that Claude calls each turn.
1. `python coach/scripts/build_mcpb.py` builds `dist/prompt-coach.mcpb` and `dist/prompt-coach-chat-skill.zip`.
2. Double-click `prompt-coach.mcpb` (or Settings > Extensions > Advanced > Install Extension) and choose **Install**.
   In each tool's permission prompt pick **Always allow** so it doesn't ask every message.
3. Upload `prompt-coach-chat-skill.zip` under *Customize > Skills*: it tells Claude to use the coach in every conversation.
4. Start a new chat. Claude should open with an italic *Prompt Coach:* greeting.

Your score is shared with the Code tab (same `~/.prompt-coach` folder), and a message that reaches both channels is
only counted once. In Cowork you can also upload `dist/prompt-coach-plugin.zip` (*Customize > Plugins > Add >
Upload plugin*); see "Where it runs".

**Try it without installing:** `claude --plugin-dir ./coach`

Requires Python 3.9+ on the machine (standard library only, nothing to `pip install`).
Then just work as usual. The coach starts on its own.

## What you'll see

| Moment | What happens |
|---|---|
| Session start | One-line welcome ("Beginner, 3-day streak"). |
| Every few prompts | Your AI ends a reply with **one** short coaching question, always in italics and starting with "Prompt Coach:". Beginners hear from it about every 2 prompts, experts about every 8. |
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

It's **behavior-based**: computed from what you actually do, not a quiz, over your most recent 100
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
| 3 Advanced | Score 55+, 30+ prompts on 5+ days, 4+ documents revised |
| 4 Expert | Score 78+, 100 prompts on 15+ days, 10+ documents with at least 70% revised, no sensitive-data flags (about 3+ working weeks of consistently strong habits) |

A level is only lost when you fall about 6 points **below** its gate, so one off day doesn't flip it.
The window counts prompts, not calendar days, so a vacation doesn't cost you a level.

Streaks count working days (weekends don't break one) with at least one good-habit moment: a
context-rich request or a revision.

## What `/prompt-coach:score` shows

(Sample data from `coach.py demo`.)

```
# Your AI Fluency Score

**Advanced** (Level 3 of 4) · Score **62 / 100**

To reach **Expert**:
- Raise your AI Fluency score from 62 to 78
- Build a longer track record (43 of 100 scored prompts)
- Revise at least 70% of documents you generate (now 44%)

Context up front   ██████░░░░░░   54%
Revising drafts    █████░░░░░░░   44%
Specific asks      ██████░░░░░░   49%
Checking the AI    ████████████  100%
Right feature      ████████████  100%
Showing up         ████████████  100%

Best next step: revising drafts.
Streak: 6 working days (best 9) · Last 14 days: ▆▁▁▄██▄▆▁▁██▄▆

> AI Fluency: Advanced (Level 3 of 4), score 62/100, 6-day streak,
> revises 44% of the documents it generates.
> Based on 43 prompts. Measured on this device by Prompt Coach; no prompt content is shared.
```

It also writes `summary.md` and a small `badge.svg` (Level and score) you can paste into a profile or send to a manager.

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
| Claude desktop, Chat | Through the desktop extension + skill: Claude calls the coach's tools each turn (greeting, coaching, document nudges, score). Less reliable than hooks because Claude has to choose to call them, and it adds a small tool call per message. The helper is tested with an MCP client; the in-app behavior is not yet tested by hand. |
| Claude desktop, Cowork | Same extension works there if the session runs on your computer. The plugin zip's hooks may also load, but Cowork runs in a sandbox whose home folder is reportedly not kept between conversations, so prefer the extension (it keeps your data on your computer). Not yet tested by hand. |
| claude.ai in a browser | Skills only; no local helper, so no tracking. |
| ChatGPT, Copilot, Gemini | Not supported by this plugin. The browser extension in `../extension` covers those websites. |

## Limits worth knowing

- Coding prompts (code fences, source files, stack traces, dev jargon) are deliberately ignored: this coach is for everyday work, and rules built for prose would judge them unfairly.
- Scoring is heuristic (keyword and structure signals), tuned to be fair on average, not perfect on any one prompt.
- The coach can only see what hooks can: it can't read the AI's reply to judge it, so "did you accept the draft?" is inferred from your next prompt.
- The coaching question is delivered *by the AI following an instruction*, so it can occasionally skip or word it differently.
- Document detection covers Office files and PDFs (and larger Markdown/HTML written directly). Files made by unusual tools may be missed.

## Develop

```bash
python -m unittest discover -s coach/tests -v     # 108 tests, standard library only
claude plugin validate ./coach                    # manifest + skills check
claude --plugin-dir ./coach                       # run it live
PROMPT_COACH_HOME=/tmp/demo python coach/scripts/coach.py demo    # sample profile
PROMPT_COACH_HOME=/tmp/demo python coach/scripts/coach.py score   # see the scoreboard
python coach/scripts/build_zip.py                 # package for Claude desktop upload
```

Layout: `scripts/pcoach/signals.py` (what a prompt reveals), `scoring.py` (score + levels),
`cadence.py` (when to speak), `lessons.py` (micro-training + instructions), `game.py` (XP/streaks/achievements),
`hooks.py` (the three hook handlers), `report.py` (scoreboard, badge, export), `store.py` (local storage).
