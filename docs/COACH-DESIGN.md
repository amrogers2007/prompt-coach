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
                     ├─ cadence.decide ── choose_skill ── lessons.pick ── coach_instruction ──► AI context
                     └─ toast (systemMessage) for level-ups, streaks, achievements
PostToolUse (Write/Edit/Bash) ─► document generated? new "draft" + first-draft nudge ──► AI context
                                  (a revised version of a pending draft => "second pass" nudge)
```

## The score

`score = 100 * weighted mean of available habits - sensitive-data penalty`, weights renormalized over the habits that
have enough data (so a new user isn't scored 0 for lacking document history, but can't reach Advanced without it:
levels have activity gates as well as score gates). See `coach/README.md` for weights and gates and
`coach/scripts/pcoach/scoring.py` for the implementation (tested in `coach/tests/test_scoring.py`).

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
6. **Coaching content.** 16 lessons today. Needs review by someone who trains people for a living.
7. **Team features.** Leaderboards are tempting and risky (they reward gaming the heuristics); prefer team-level trends.
