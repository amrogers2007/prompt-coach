# Approaches — the full menu of ways to build this

Two independent choices: **(A) where the coaching lives** and **(B) how it
intervenes.** Mix and match to get a product concept.

---

## Axis A — WHERE it lives (form factor)

| # | Form factor | What it is | Buildable by you now? | Enterprise-friendly? |
|---|---|---|---|---|
| A1 | **Browser extension on AI sites** | Overlay on chatgpt.com, claude.ai, Copilot/Gemini web. Watches the prompt box, nudges. | ✅ Very (best first prototype) | Medium (IT must allow the extension) |
| A2 | **Grammarly-style universal extension** | Coaches *any* text box that looks like an AI prompt, across the whole web. | ✅ Yes, bit harder | Medium |
| A3 | **Prompt "linter" / spell-check** | Before you hit send, it flags anti-patterns ("no format specified", "no sources requested") and offers a one-click fix. | ✅ Yes (great wedge) | Medium |
| A4 | **Your own wrapper chat app** | You build a chat UI that proxies to real models; coaching is baked into the interface. Company deploys *your* chat. | ✅ Yes | ✅ High (you control everything) but competes w/ ChatGPT |
| A5 | **Teams / Slack bot** | Coaching where enterprises already live. "Ask me how to prompt X," or reviews prompts you paste. | ✅ Yes | ✅ High (rides existing IT approval) |
| A6 | **Native app plugin** (Word/Excel/Copilot) | Embed like Copilot does. | ❌ Hard — needs vendor extensibility/partnership | ✅ High |
| A7 | **Manager analytics dashboard** | Doesn't touch the AI tool. Shows leaders how their team uses AI + where coaching is needed. | ✅ Yes | ✅ High (this is what the *buyer* wants) |
| A8 | **Desktop overlay** (floating helper) | Sits on top of any app via OS. | ⚠️ Medium-hard, permissions | Low-Medium |

## Axis B — HOW it intervenes (coaching style)

| # | Style | Example | Intrusive? |
|---|---|---|---|
| B1 | **Passive nudge** | Occasionally shows a relevant tip card. | Low |
| B2 | **Active rewrite** | "Improve this prompt? → [better version]" one-click. | Medium |
| B3 | **On-demand** | User clicks "coach me" / "why did this go wrong?" only when they want. | Lowest |
| B4 | **Diagnostic** | Detects a bad outcome (huge answer, likely-hallucination question) → offers the exact fix in context. | Medium |
| B5 | **Templates/scaffolds** | One-click reusable prompt patterns for common tasks. | Low |

---

## Promising combined concepts

- **"Spell-check for prompts" (A3 + B4 + B2).** Underlines/flags weak prompts
  before send, explains why, offers a one-click better version. Teaches *by
  doing*, in the flow, zero course. **← strong candidate; matches your interview data.**
- **"The fix-it button" (A1 + B3).** After a bad response, a small button:
  "Too long? Made stuff up? Did your thinking? → fix it." Only appears when the
  user is already frustrated = perfectly timed teaching moment.
- **"Coached company chat" (A4 + B1/B2).** Your own enterprise chat where good
  prompting is built into the UI. Most control, but you're now competing with
  the AI vendors' own chat apps.
- **"Adoption cockpit" (A7).** Sell the *manager* a dashboard of team AI usage +
  coaching recommendations. This is what the *buyer* actually wants to buy, even
  though the employee-facing coach is what changes behavior. (Often you need both.)

## Things you may not have considered
- The **buyer wants measurement**, not just coaching. A manager dashboard (A7)
  might be *easier to sell* than the coach itself — the coach makes employees
  better; the dashboard proves it to the person with the budget.
- A **prompt linter (A3)** may be a stronger wedge than open-ended "tips" because
  it's concrete, obviously useful, and demoable in 10 seconds.
- **On-demand (B3)** sidesteps the biggest risk: being annoying. People hate
  interruptions; they love help *when they ask*.
- You don't have to pick one forever. **Start with the cheapest demoable wedge**
  (almost certainly a browser extension), learn, then expand.

## Leaning recommendation (to debate, not obey)
Prototype **A1/A3 + B3/B4**: a browser extension that (1) offers help on-demand
and (2) catches the specific anti-patterns your users named, with one-click
fixes. Cheapest to build, directly targets real pain, demoable, sidesteps
native-app integration entirely.
