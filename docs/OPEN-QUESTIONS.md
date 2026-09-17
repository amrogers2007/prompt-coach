# Open Questions

Things we don't know yet. Answer them over time — mostly by talking to people
and doing a little research. Move answered ones to IDEA.md.

## About the customer / problem
- [ ] Which employees feel this pain *most*? (role, industry?)
- [ ] Is the stronger buyer HR/L&D, IT, or an individual department head?
- [ ] Do companies already have a budget line for "AI training/adoption"? Who owns it?
- [ ] Is low AI adoption actually a problem companies feel *urgently*, or nice-to-have?

## About the product
- [x] Which form factor first: browser extension, desktop integration, or app?
      → **Answered: browser extension** (chatgpt.com), BYOK for the AI-powered
      rewrite. Moved to IDEA.md / PROTOTYPE-SPEC.md.
- [ ] What are the 20 best "micro-tips"? (You could start listing these now — it's
      basically your content/curriculum, and it's fun. `rules.js` has ~12 so far —
      see `dashboard/`'s "what to train on next" chart for how you'd prioritize
      the next ones once you have real trigger-frequency data.)
- [ ] How do you make coaching feel helpful, not annoying? (Timing, frequency, tone.)
- [ ] How would a skeptic's experience differ from an enthusiast's?
- [ ] Which manager-dashboard metrics actually matter?
      → **Partially answered, unblocked from real data.** `dashboard/` mocks up
      a prioritized set — adoption, top coaching categories triggered (the
      curriculum, ranked by real need), a trend line proving issues-per-prompt
      is falling over time, sensitive-data flags (a distinct compliance metric,
      not just a coaching one), a team leaderboard, and a skeptic-conversion
      rate. This ordering is a guess worth testing on real managers — it isn't
      wired to real usage data, which is gated on the privacy questions below.

## About feasibility (the technical reality)
- [x] Can you technically "sit next to" ChatGPT/Copilot? (Browser extensions: yes,
      for web versions. Injecting into their native apps: much harder / not really.)
      → Confirmed and built (`extension/`).
- [x] Can a browser call Claude directly, with the user's own key, with no
      backend? → **Yes.** Anthropic's API supports CORS for direct browser
      calls via the `anthropic-dangerous-direct-browser-access` header. This is
      what makes the BYOK design in `extension/src/background.js` possible —
      confirmed before relying on it, not assumed.
- [ ] Does Microsoft 365 Copilot have an extensibility/plugin model you could use?
- [ ] Do enterprise AI tools expose usage data an admin could feed you? (Privacy!)
- [ ] Privacy/security: enterprises are strict (you saw this at State Farm). What
      can you see vs. not see about what employees are typing? This is a big deal.
      **This is exactly why `dashboard/` is a mockup with sample data, not wired
      to anything real** — a real version needs a real answer here first
      (aggregation? anonymization? opt-in? what never leaves the browser?).

## About the market / competition
- [ ] Who are the top 5 companies already doing "AI enablement"? What do they charge?
- [ ] What's the honest answer to "why won't Microsoft/OpenAI just build this"?
- [ ] Is there a version that's cross-tool (works with any AI) that vendors won't build?

## About you / the path
- [ ] How many hours/week can you realistically give this during the school year?
- [ ] Do you want a co-founder eventually (e.g. a Harvey Mudd friend)?
- [ ] What does Harvey Mudd / the Claremont Colleges offer for student founders?
