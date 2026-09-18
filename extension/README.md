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

## Try the logic WITHOUT Chrome (fastest)
Open `../playground/index.html` in any browser. It runs the same `rules.js`
logic against a plain text box, with example buttons, and has its own
"bring your own key" field for the AI-rewrite feature. Great for tuning the
rules without reloading the extension.

## Run the tests
`rules.js` and `telemetry.js` are pure logic with no browser/extension
dependency, so they're tested directly with Node — no build step, no test
framework dependency (uses `node:test`, built into Node 18+):
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

## What v1 does
Detects common prompt problems (from real user interviews) and offers a
one-click improved prompt, entirely for free and offline:
- No format/length → answers come back too long
- Fact question with no accuracy safeguard → risk of made-up info
- Too little context → the AI has to guess
- **Editing a document but describing changes instead of asking the AI to make
  them directly** → coaches iterative in-AI editing (ChatGPT Canvas / Claude
  Artifacts) instead of the old copy-paste-into-Word loop
- "Do it for me" → optional "tutor me instead" nudge

Optionally, with your own API key set in Settings, a **✨ Improve with AI**
button sends the prompt to Claude for a smarter, context-aware rewrite plus
1–3 plain-English tips.

## What v1 does NOT do yet (future)
- Work on Copilot web (Copilot's chat surface and auth are more different from
  the others; hasn't been attempted)
- The "fix it after a bad response" helper (v2)
- Any real, working team / manager dashboard (see `../dashboard/` for the mockup,
  `../docs/OPEN-QUESTIONS.md` for the privacy questions that gate a real one, and
  `../docs/PRIVACY-DESIGN.md` for the answer plus `src/telemetry.js`, a client-side
  aggregation sketch that's deliberately **not wired in yet** — no consent UI or
  backend exists to send it to)

## Privacy / security notes
- Your Anthropic API key lives only in this browser's extension storage. It is
  never sent anywhere except `api.anthropic.com`.
- The rule-based coaching (no key required) runs 100% locally — nothing you
  type is ever sent anywhere unless you click "Improve with AI."
