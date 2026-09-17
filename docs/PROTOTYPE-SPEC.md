# Prototype Spec — v1

Decisions locked in (revise freely as you learn).

## Go-to-market decision: BOTTOM-UP
Build for **individuals first**, keep the **enterprise** vision for later. Get
users before buyers. (Same playbook as Grammarly, Slack, Notion, Zoom.)
- Now: free extension individuals install and love.
- Later: team features → manager dashboard → sell to companies.
This is NOT switching to consumer — it's the standard modern path *into* enterprise.

## What we're building
A **browser extension** that coaches people to write better AI prompts, in the
flow, teaching *by doing*.

### Core value (primary goal)
Help an individual employee **learn to use AI well and appreciate its value.**

### Features
- **v1 (build first): "before you send" nudge (Grammarly-style).**
  As the user types a prompt, detect weak patterns and offer improvement +
  explanation. Rewrite the prompt AND show what improved (learn-by-doing).
  Targets the exact interview complaints:
  - no output format/length → suggest "answer in 3 bullets / one paragraph"
  - fact question, no grounding → suggest "ask for sources / say if unsure"
  - vague goal/no context → suggest stating goal, audience, format
  - wants understanding → suggest "explain your reasoning / tutor me, don't just answer"
- **v2 (later): "fix it — idk why it's not working" helper.**
  After a bad response, a button diagnoses (too long? made up? did your
  thinking?) and offers the fix. Post-send counterpart to v1.
- **v3+ (much later): team view → manager dashboard** (usage improving over time).

### Scope guardrails (avoid biting off too much)
- **Target ONE site first: ChatGPT web (chatgpt.com).** Architect for multi-site
  so adding claude.ai / Gemini / Copilot web later is a small config, not a rewrite.
- **NOT the native desktop apps** (a browser extension can't reach those).
- **v1 "intelligence" = hard-coded rules first** (a "prompt linter"). Fast, free,
  no API key, works offline, easy to demo. Wire in a real LLM later if wanted.
- On-demand + gentle: never block sending; suggestions are dismissible.

## Tech (as built)
- Chrome extension, Manifest V3.
- Plain JavaScript + a content script that watches the prompt box.
- No backend for the rule-based coaching (runs entirely in the browser).
- **AI rewrite = bring-your-own-key (BYOK).** No server, no shared key. Each
  user adds their own Anthropic API key in the extension's Settings page; a
  background service worker calls `api.anthropic.com` directly from the
  browser using that key (`anthropic-dangerous-direct-browser-access`), billed
  to the user's own account. (An earlier version routed this through a local
  Node server holding one shared key — see `server/README.md` for why that
  was replaced.)

## Definition of "v1 done"
On chatgpt.com, when I type a weak prompt, a small helper appears suggesting a
concrete improvement with a one-click "use this" and a one-line "why." I can
show it to a friend and they immediately get it. ✅ Done.

## v1.5 — added since v1
- **New coaching category: edit in the AI, not Word.** Detects document-editing
  requests ("revise this report," "make edits to my cover letter") and coaches
  the habit of iterating directly in the AI (ChatGPT Canvas / Claude Artifacts)
  instead of the old copy-into-Word-and-back loop. This is a real, distinct
  skill gap separate from prompting — most people don't know these editing
  surfaces exist.
- **BYOK AI rewrite**, replacing the shared-key local server (see Tech above).
- **Manager dashboard mockup** (`dashboard/`), sample data only. See
  `OPEN-QUESTIONS.md` for what would need to be true before this could run on
  real, privacy-safe usage data.

## Project framing update
This project is now explicitly also a **portfolio piece** — something to point
to when applying to competitive roles, not only a path to a company. That
doesn't change the product decisions above, but it does change priorities:
polish and a clean, public, well-documented repo matter as much as the
original startup thesis. See root `README.md`.
