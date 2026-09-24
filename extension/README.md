# Prompt Coach — Chrome Extension

Coaches you to write better AI prompts, right as you type, on chatgpt.com,
claude.ai, and gemini.google.com.

## The three-part design (remember this!)
- **`src/rules.js` = the BRAIN.** Pure logic: given a prompt, what could be
  better + a rewritten version. Knows nothing about browsers. *Reusable* in a
  future desktop app, Slack bot, etc.
- **`src/content.js` = the PLUMBING.** The web-chat-specific part: find the
  text box, watch typing, draw the suggestion card. `findPromptBox()` tries a
  few site-specific selectors, then falls back to "the first contenteditable
  or textarea on the page" — that's what makes adding a new site usually just
  a `manifest.json` match, not new code. The brain (`rules.js`) never changes.
- **`src/background.js` = the AI CONNECTION.** A service worker that calls
  Claude directly from the browser using **your own** Anthropic API key
  (stored in `chrome.storage.local` via the Settings page, `src/options.html`).
  Nothing about this extension routes your prompts or your key through any
  server the developer runs — the request goes straight from your browser to
  Anthropic, and you're billed directly for whatever you use.
- **`src/profile.js` + `src/profile.html` = YOUR PROGRESS.** A toolbar popup
  showing your own skill trend over time (which coaching categories fire
  most, and whether that's improving), backed by local-only
  `chrome.storage.local` — nothing here ever leaves the browser, so unlike
  `telemetry.js` (below) it isn't opt-in gated.

## Try the logic WITHOUT Chrome (fastest)
Open `../playground/index.html` in any browser. It runs the same `rules.js`
logic against a plain text box, with example buttons, and has its own
"bring your own key" field for the AI-rewrite feature. Great for tuning the
rules without reloading the extension.

## Run the tests
`rules.js`, `telemetry.js`, and `profile.js` are pure logic with no
browser/extension dependency, so they're tested directly with Node — no
build step, no test framework dependency (uses `node:test`, built into
Node 18+):
```
npm test
```
`playground/index.html` keeps its own copy of the same rules (documented at
its top) so it can run with zero build step; if you add or change a rule in
`rules.js`, update both, then run the tests above.

## Load the real extension in Chrome
1. Open Chrome → go to `chrome://extensions`
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked**.
4. Select this `extension/` folder.
5. Go to https://chatgpt.com, https://claude.ai, or https://gemini.google.com
   and start typing a prompt — a card should appear.
6. (Optional, for AI rewrites) Right-click the extension in
   `chrome://extensions` → **Options**, and paste in your own Anthropic API
   key from https://console.anthropic.com/settings/keys.

If nothing shows: open the page, right-click → Inspect → Console, and look for
`[Prompt Coach] attached to prompt box`. These sites change their HTML often,
so if it can't find the box we may need to update the selectors in
`content.js` (`findPromptBox`).

**Confirmed hands-on (2026-09-17):** the coaching card and "Use improved
prompt" button both work live on chatgpt.com, claude.ai, and
gemini.google.com.

**Found and fixed via real-world testing (2026-09-18):** clicking "✨ Improve
with AI" blurs the prompt box (focus moves to the button), and a blur
handler used to unconditionally hide the whole card 200ms later — so on a
real network request (which takes longer than 200ms), the card was already
hidden by the time the AI response arrived. It looked like nothing happened.
Fixed in `content.js`: the blur handler now checks whether focus moved
*inside* the card (i.e. you clicked one of its own buttons) before hiding —
if so, it leaves the card open so the AI result is actually visible when it
arrives. Verified with a simulated 800ms response delay and a real mouse
click (not a synthetic one) to faithfully reproduce the original bug.

**"✨ Improve with AI" confirmed fully working end-to-end (2026-09-18)**
with a real Anthropic API key on a live site, after fixing both of the
above and one more real bug the same testing surfaced: the request set
`output_config.effort = "low"`, which `claude-haiku-4-5` doesn't support
and rejected outright. Removed (it was an optional tuning hint, not
required for the feature). All three sites, both buttons, real network
calls — this is now a fully working v1.

**v2 direction implemented (2026-09-23)**, from
`docs/PromptCoach_Direction_and_Roadmap.pdf`: category tagging + a task
classifier, an auto-triggered "live" AI critique with real cost guardrails,
a lightweight "doesn't refine" proxy, and the new local skill-progress
popup — see "What v1 does" below for specifics. **Unlike the fixes above,
this round was verified with mocked `chrome.*`/network calls in a browser
(timing, cooldowns, category mapping, popup rendering all checked), but
not yet hands-on on a real site with a real key** — that's the next thing
worth doing by hand.

## The on-page widget (v0.4)
A small, minimal card that is **always on screen** — it opens docked to the
top-right of the page on load, in **Improve** mode, and never hides itself.
- **Improve | Teach toggle:** *Improve* has the AI rewrite your prompt
  (with a **Use this** button and short tips; missing details become
  `[placeholders]`, never invented facts). *Teach* doesn't rewrite — it names
  one thing you did well and up to three improvements, each with a nudge, so
  you make the edits yourself.
- **Automatic:** a suggestion appears ~3 seconds after you stop typing (needs
  your API key; turn off in Settings). The refresh arrow re-runs it on demand.
- **Drag and collapse:** drag it by its title bar anywhere (position is
  remembered); the minus button shrinks it to a small draggable "PC" icon, and
  a click on the icon reopens it. While collapsed, no automatic calls are made.
  Double-click the title bar to snap back to the default spot.
- The free rule-based analysis still runs quietly to build your local
  progress popup; it is no longer shown on the page.

## What v1 does
Detects common prompt problems (from real user interviews), organized into
8 categories (see `rules.js`'s header comment for the full mapping), and
offers a one-click improved prompt, entirely for free and offline:
- No format/length → answers come back too long
- Fact question with no accuracy safeguard → risk of made-up info
- Too little context → the AI has to guess
- **Editing a document but describing changes instead of asking the AI to make
  them directly** → coaches iterative in-AI editing (ChatGPT Canvas / Claude
  Artifacts) instead of the old copy-paste-into-Word loop
- "Do it for me" → optional "tutor me instead" nudge

`classify()` tells generative/analytical prompts ("write me...", "explain...")
apart from discrete factual ones ("what's 7\*8") — refinement-style coaching
and the auto-critique below only apply to the former.

Optionally, with your own API key set in Settings:
- **✨ Improve with AI** button sends the prompt to Claude for a smarter,
  context-aware rewrite plus 1–3 plain-English tips.
- **Auto-run AI critique while typing** (Settings toggle, **on by default**):
  fires the same rewrite automatically ~3 seconds after you stop typing, for
  generative prompts only, with a hard 15-second cooldown between auto-calls
  so it can't run away with your API credit.
- A lightweight **"doesn't refine"** signal: sending a new prompt soon after
  the last one, with no suggestion ever used, gets tagged as a moment worth
  coaching iteration on — a proxy, not a read of the AI's actual reply (that
  would mean parsing each site's response DOM, which is deferred — see below).
- The toolbar popup (**`src/profile.html`**) shows your own 30-day skill
  snapshot and week-over-week trend per category, entirely local.

## What v1 does NOT do yet (future)
- Work on Copilot web (Copilot's chat surface and auth are more different from
  the others; hasn't been attempted)
- Reading the AI's actual response off the page to know for certain whether
  you refined it (the "doesn't refine" signal above is a proxy, by design —
  see `docs/PromptCoach_Direction_and_Roadmap.pdf`'s "Open / Deferred" section)
- Any real, working team / manager dashboard (see `../dashboard/` for the mockup,
  `../docs/OPEN-QUESTIONS.md` for the privacy questions that gate a real one, and
  `../docs/PRIVACY-DESIGN.md` for the answer plus `src/telemetry.js`, a client-side
  aggregation sketch that's deliberately **not wired in yet** — no consent UI or
  backend exists to send it to). The new `src/profile.js`/`profile.html` is a
  separate, simpler thing: your own local history, not the enterprise layer.

## Privacy / security notes
- Your Anthropic API key lives only in this browser's extension storage. It is
  never sent anywhere except `api.anthropic.com`.
- The rule-based coaching (no key required) runs 100% locally — nothing you
  type is ever sent anywhere unless you click "Improve with AI" (or leave the
  auto-critique toggle on, which it is by default — turn it off in Settings if you would rather only send a prompt on request).
- Your skill-progress popup (`profile.js`/`profile.html`) stores only
  category names and counts — never prompt text — and never leaves this
  browser either way. "Clear my data" in the popup wipes it on demand.
