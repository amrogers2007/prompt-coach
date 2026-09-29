# Coach: design notes

The pivot: from a browser extension that rewrites prompts to a **coach embedded in the AI itself**. This
document records why it is built the way it is, and what is still open.

## The idea in one paragraph

Give people who never learned to use AI a coach that is *in the room*: it sees the conversation, asks questions
instead of doing the thinking, notices when the AI has produced a deck or PDF and pushes the user to iterate on it, remembers
how the user has done over time, and converts that into a level a manager can understand.

## Decisions and why

| Decision | Reasoning |
|---|---|
| **Claude plugin first** (skills + hooks + agent) | It's the one surface where a coach can genuinely be inside the loop: hooks can observe each prompt and each file the AI writes, and inject a coaching instruction into the AI's context. The same plugin folder also loads (with a subset) in the Claude desktop app's Cowork. |
| **Coach asks, doesn't rewrite** | People learn habits by producing the missing piece themselves. It also fits the user-research finding (a skeptical physics professor) that people want to build their own judgment rather than outsource it. |
| **Coaching delivered by the main AI, via hook-injected instructions** | Simple, and the coach automatically has the full conversation as memory. Cost: the AI might occasionally not comply. The alternative (a separate coach process) can't see the chat. |
| **Adaptive cadence** | Beginners about every 2 prompts, experts about every 8, never twice in a row, always on generated files and sensitive data, with `pause` and `intensity` controls. The goal is "constant but not nagging". |
| **Behavior-based, hard, reversible levels** | Requested: 4 levels, "a bit hard", can drop. Computed from a rolling window with a small buffer, so it is fair rather than jumpy, and vacation-proof (window counts prompts, not days). |
| **Iteration is 30% of the score** | The research behind the project says the single biggest gap for novices is accepting the first draft. So a generated document is tracked as a "draft" and scored by how many revisions follow. |
| **No prompt text stored, ever** | Enterprise trust. Signals are reduced to small numbers immediately; only those persist. |
| **Python, standard library only** | Testable here, no install step, works on macOS/Linux/Windows. Cost: users need Python 3.9+ (checked by the installer and `doctor`). Node would allow reusing `extension/src/rules.js`, but Python wasn't a blocker and Node isn't installed on most non-coder machines either. |
| **Hooks fail silent** | A coach must never break someone's AI session: every hook exits 0 and logs errors to `~/.prompt-coach/errors.log`. |

## How a turn flows

```
SessionStart hook ── welcome line + "coach is active" context
UserPromptSubmit ──► signals.analyze_prompt (context, precision, verify, feature, sensitive, kind)
                     ├─ was a draft pending? refine => revision credit; anything else => draft accepted
                     ├─ store event (numbers only), XP, streak, achievements
                     ├─ scoring.compute_metrics + resolve_level (may level up or down)
                     ├─ was the coach's last offer answered? yes => follow-up action; "doesn't fit" => mute tip
                     ├─ signals.detect_triggers ── named teachable moments (no_audience, calculations...)
                     ├─ cadence.decide (urgent triggers skip the schedule) ── choose_skill ── lessons.choose
                     │     (triggered recommendation > everyday habit; muted/recent skipped; pilot holdout)
                     │     ── coach_instruction (offer + follow-up action + AI-judged alternatives) ──► AI context
                     └─ toast (systemMessage) for level-ups, streaks, achievements
PostToolUse (Write/Edit/Bash) ─► document generated? new "draft" + first-draft nudge ──► AI context
                                  (a revised version of a pending draft => "second pass" nudge)
```

## The score

`score = 100 * weighted mean of available habits - sensitive-data penalty`, weights renormalized over the habits that
have enough data (so a new user isn't scored 0 for lacking document history, but can't reach Advanced without it:
levels have activity gates as well as score gates). See `coach/README.md` for weights and gates and
`coach/scripts/pcoach/scoring.py` for the implementation (tested in `coach/tests/test_scoring.py`).

## Desktop chat and Cowork (v0.2)

Anthropic's docs say chat loads skills only (hooks, agents and local MCP servers in plugins are ignored) and
Cowork runs in a Linux sandbox whose plugin data folder is reportedly not persistent between conversations. So hooks alone
cannot cover "all of desktop Claude". The answer is a local MCP server (`pcoach/mcp_server.py`, packaged as a
`.mcpb` desktop extension) that reuses the same engine as the hooks:

- `coach_start` / `coach_turn` / `coach_document` / `coach_score` / `coach_settings`, with server-level instructions plus a small
  skill telling Claude to call them each turn. Status notes (welcome, level-ups) are delivered as instructions for Claude to say,
  because the app doesn't show hook `systemMessage`s.
- One shared profile in `~/.prompt-coach`, so the Code tab, chat and Cowork add up to one level. A message seen by both channels is
  deduplicated (first channel wins, 120 s window).
- Cost of the design: reliability depends on Claude deciding to call the tools (hooks are guaranteed), and there is one extra tool call per message.
- Runtime: Claude Desktop ships Node.js but not Python, so the helper uses the user's Python 3.9+. A Node port (or the MCPB `uv` runtime) would remove that requirement.
- v0.3: the `.mcpb` never worked on the author's Windows PC. Claude launched it with `python3`, which resolved to the
  Microsoft Store Python. Both that Python and Claude (an MSIX app) get private, virtualized copies of AppData, so the
  helper's files, installed into Claude's copy, didn't exist for it. `coach/scripts/setup_desktop.py` now registers
  the helper in `claude_desktop_config.json` with an absolute path to a regular Python and the repo's own
  `coach_mcp.py`. It writes the config inside the MSIX package folder when there is one, and test-launches the helper
  before touching anything. As a side effect, chat runs the latest code in the repo with no reinstall.

## Recommendation library and the evidence loop (v0.3)

A collaborator's proposal (trigger, recommendation, agent action) and the project's business case (kept outside the
public repo) shaped v0.3:

- **One editable library.** `coach/library/recommendations.md` holds all 76 recommendations (the collaborator's 60 plus the 16
  original lessons). Each has *when / recommend / action*, a habit, a level range and a detector. Adding one is a
  Markdown edit; `coach.py library` validates the file. Source research: `BEST-PRACTICES-SOURCE.md`.
- **Recognition to action.** The coach offers; a "yes" on the next message injects that recommendation's action, so
  the user does the better behavior immediately (the business case's recognition, relevance, action, reinforcement).
- **Precision first.** The case's first "must be true" is high-precision detection. Detectors are regexes measured
  against labeled prompts (`coach/evals/`). Two blind sets, each scored once before tuning: 93% precision / 88% recall,
  then 80% / 80%. The drop is the honest lesson: keyword rules generalize only as far as their vocabulary. After
  fixing the gaps, all sets score 98%, but that is in-sample. The next credible number needs real anonymized prompts,
  or an LLM-judge detector for the fuzzy triggers (no audience, no purpose) with regexes kept for the crisp ones. Specific triggers supersede generic ones (a PTO-policy question
  is about the internal source, not facts in general).
- **Don't optimize for nudges.** Tips the user declines twice are muted for two weeks; "that doesn't apply" mutes one
  for a month and counts as a false positive. `settings why` explains any tip.
- **Measure behavior, with a control group.** `insights` reports acceptance, misfits and whether each issue came up
  less after coaching. Pilot mode randomizes per user and issue (not per moment, which would contaminate the
  control), and `insights.pool()` combines participants. Only "after" rates are compared: an issue's first moment is
  when it first appears, so a before/after change is biased. Simulated pilots confirm the analysis finds a real effect
  (-11 pts) and shows none when behavior doesn't change (-2 pts).

## Open questions / next steps

1. **Cowork/Desktop in practice.** Anthropic's docs say hooks/agents/skills load in Cowork. Untested by hand here.
   Need to confirm where hook scripts execute (host vs sandbox) and that Python is available there. If not, port the
   handlers to a runtime that is guaranteed (or an MCP server bundled as `.mcpb`).
2. **Real-model validation.** Hook I/O was verified against the real Claude Code binary (hooks fire, JSON accepted,
   context injected). What is not yet measured is how reliably models follow the coaching instruction and how the
   questions *feel*. Suggested next step: `claude plugin eval` cases (the docs describe an eval harness) plus a week of dogfooding.
3. **Verified levels.** Today the score is local and self-reported. A manager-grade credential needs a signed export
   and a team backend, reusing the k-anonymity design in `PRIVACY-DESIGN.md`. The `export` command already emits an aggregate-only payload.
4. **Better signals.** Reading the AI's reply (to see whether the user acted on a suggestion) and using a small LLM judge for
   prompt quality would beat keyword heuristics, at a cost in privacy and money. Kept out of v1 on purpose.
5. **Onboarding.** A one-time "what do you do?" question would let lessons use the user's real work as examples (the `practice` skill
   already does this ad hoc).
6. **Coaching content.** 76 recommendations in the library. Needs review by someone who trains people for a living,
   and a fresh blind prompt set (ideally real, anonymized prompts from a pilot) to re-measure detector precision.
8. **A real pilot.** The measurement is built; the evidence isn't. Next: a few colleagues with `experiment 20` for
   three to four weeks, then pool their `insights --json`.
7. **Team features.** Leaderboards are tempting and risky (they reward gaming the heuristics); prefer team-level trends.
