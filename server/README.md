# Prompt Coach — AI Brain (local server) — LEGACY, replaced by BYOK

> **Superseded.** The extension and playground no longer use this server. Each
> user now adds their **own** Anthropic API key directly in the extension's
> Settings (or the playground's key field), and the browser calls Claude
> directly — see `extension/src/background.js`. That's possible because
> Anthropic's API supports CORS for direct browser calls via the
> `anthropic-dangerous-direct-browser-access` header, which didn't feel worth
> relying on until it was double-checked.
>
> **Why the change:** this server design meant *the developer's* key paid for
> *everyone's* usage — fine for a demo, not viable for something other people
> actually install. Moving the key into each user's own browser means each
> person pays for their own usage, with no server to install or keep running.
> This file is kept for the history of that decision, and because "why did we
> build it this way, then change it" is exactly the kind of judgment call a
> resume reader might ask about.

This tiny server is what let the coach use a **real Claude model** instead of
hard-coded rules, back when the design assumed one shared key. It exists for
one reason: **the API key must never go in the browser** — under this design.
This server held the key and was the only thing that called Claude.

```
browser (playground)  ──prompt──►  this server  ──key──►  Claude API
                      ◄─improved──               ◄────────
```

## One-time setup

### 1. Get an Anthropic API key
- Go to https://console.anthropic.com → sign up → **API Keys** → create a key.
- You'll need to add a payment method and a little credit (this is pay-per-use;
  a prompt rewrite costs a fraction of a cent, but it's not free).
- Copy the key — it looks like `sk-ant-...`. **Never commit it or paste it into
  the extension.**

### 2. Install the one dependency
From this `server/` folder:
```bash
npm install
```

## Run it
```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here npm start
```
You should see: `AI brain running at http://localhost:8787`.
Leave it running, then use the **"✨ Improve with AI"** button in the playground.

## Which model?
Defaults to **Claude Opus 5** (most capable). For a prompt-rewriter you may
prefer something faster and cheaper — edit `MODEL` in `server.js`:
- `"claude-opus-5"` — best quality (default)
- `"claude-haiku-4-5"` — fastest + cheapest, great for this simple task
- `"claude-sonnet-5"` — middle ground

## What it does
`POST /improve` with `{ "prompt": "..." }` → returns
`{ "improved": "...", "tips": ["...", "..."] }`.
The model is forced to return that exact JSON shape (structured outputs), so the
result is always parseable.

## Rules vs AI (why we kept both)
- **Rules** (`extension/src/rules.js`): instant, free, offline, predictable. Runs
  as you type.
- **AI** (this server): smarter, understands any prompt, but costs a call and
  adds a second of latency. Runs when you click the button.
This is a real product decision you'll face: cheap-and-instant vs smart-but-costly.
