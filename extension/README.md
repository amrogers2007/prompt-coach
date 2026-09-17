# Prompt Coach — Chrome Extension

Coaches you to write better AI prompts, right as you type, on ChatGPT web.

## The three-part design (remember this!)
- **`src/rules.js` = the BRAIN.** Pure logic: given a prompt, what could be
  better + a rewritten version. Knows nothing about browsers. *Reusable* in a
  future desktop app, Slack bot, etc.
- **`src/content.js` = the PLUMBING.** The ChatGPT-web-specific part: find the
  text box, watch typing, draw the suggestion card. This gets rewritten per
  platform; the brain does not.
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

## Load the real extension in Chrome
1. Open Chrome → go to `chrome://extensions`
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked**.
4. Select this `extension/` folder.
5. Go to https://chatgpt.com and start typing a prompt — a card should appear.
6. (Optional, for AI rewrites) Right-click the extension in
   `chrome://extensions` → **Options**, and paste in your own Anthropic API
   key from https://console.anthropic.com/settings/keys.

If nothing shows: open the page, right-click → Inspect → Console, and look for
`[Prompt Coach] attached to prompt box`. ChatGPT changes its HTML often, so if
it can't find the box we may need to update the selectors in `content.js`
(`findPromptBox`).

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
- Work on Claude / Gemini / Copilot web (easy to add: extend the selectors + matches)
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
