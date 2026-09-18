# Prompt Coach

[![Test](https://github.com/amrogers2007/prompt-coach/actions/workflows/test.yml/badge.svg)](https://github.com/amrogers2007/prompt-coach/actions/workflows/test.yml)

**An in-the-flow AI coach that watches how you write prompts and teaches you to
get more out of AI — right as you type, with zero setup cost to you.**

Built by Amanda Rogers (CS + Physics, Harvey Mudd) as a self-directed project:
take a real idea from a napkin sketch to a working prototype, the way a real
product gets built — talk to users first, then prototype, then build. The
`docs/` folder is the actual paper trail of that process, kept intentionally
rough and unedited.

> This started as a startup idea (see `docs/`). It's now primarily a portfolio
> project — a complete, working example of product thinking + full-stack build,
> from customer interviews through a shipped Chrome extension.

## Try it in 60 seconds (no install)

Open [`playground/index.html`](playground/index.html) in any browser. Type a
prompt and watch the coaching appear live — no Chrome extension, no server,
no signup.

## What's in this repo

| Folder | What it is |
|---|---|
| [`extension/`](extension/) | The real Chrome extension (Manifest V3). Coaches you live on chatgpt.com, claude.ai, and gemini.google.com. |
| [`playground/`](playground/) | A standalone page that runs the same coaching logic — the fastest way to try it or tune the rules. |
| [`dashboard/`](dashboard/) | A manager-facing dashboard **mockup** (sample data) showing what a company buying this would want to see. |
| [`server/`](server/) | *(legacy)* An earlier design where a server held the API key. Kept for the history — see its README for why it was replaced. |
| [`docs/`](docs/) | The idea, the customer interviews, the business thinking, and the open questions — the "why" behind every decision above. |
| [`tests/`](tests/) | Automated tests for the rules engine and telemetry sketch (Node's built-in test runner, zero dependencies). Runs in CI on every push — see the badge above. |

## How it works

1. **The rules engine** (`extension/src/rules.js`) is the "brain": pure,
   dependency-free JavaScript that reads a prompt and flags concrete,
   research-backed weaknesses (no source-checking, no format specified, too
   little context, missing technical/planning constraints, no structured
   output ask, no persona for expert tasks, editing habits that belong in the
   AI instead of Word, and more — 20 rules total) — instantly, for free,
   fully offline.
2. **Bring-your-own-key AI rewrite.** Click "✨ Improve with AI" and, if you've
   added your own Anthropic API key in the extension's Settings, it calls
   Claude *directly from your browser* to produce a smarter rewrite. Your key
   never leaves your machine except to talk to Anthropic — nothing routes
   through a server anyone else runs, and usage is billed to **your** account,
   not the developer's. See [`extension/src/background.js`](extension/src/background.js).
3. **The manager dashboard** (mockup) shows the metrics a company would
   actually want if they rolled this out org-wide: adoption, which coaching
   categories fire most (i.e. what to train on next), whether prompt quality
   is trending up over time, and a couple of high-signal outliers (sensitive
   data flags, skeptic conversion). See `docs/` for the reasoning behind why
   these and not others.

## Documents
- [IDEA.md](docs/IDEA.md) — the living idea document (vision, customer, product, business, risks)
- [APPROACHES.md](docs/APPROACHES.md) — the full menu of product directions considered
- [PROTOTYPE-SPEC.md](docs/PROTOTYPE-SPEC.md) — what v1 actually is and isn't
- [INTERVIEW-NOTES.md](docs/INTERVIEW-NOTES.md) — real early user interviews and the pain points they surfaced
- [GLOSSARY.md](docs/GLOSSARY.md) — plain-English definitions of startup/business terms
- [ACTION-PLAN.md](docs/ACTION-PLAN.md) — concrete next steps, cheapest-first
- [OPEN-QUESTIONS.md](docs/OPEN-QUESTIONS.md) — things still unresolved, on purpose

## Status

Working prototype, confirmed hands-on end-to-end. Rule-based coaching runs
live on chatgpt.com, claude.ai, and gemini.google.com; the AI-powered
rewrite works with your own API key on all three; the manager dashboard is
a mockup pending real (privacy-safe) telemetry — see `docs/OPEN-QUESTIONS.md`.
