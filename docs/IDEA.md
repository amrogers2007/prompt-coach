# The Idea (living document)

> Update this as your thinking sharpens. Nothing here is final.

---

## 1. One-liner
An **in-the-flow AI coach for enterprise employees**: it rides alongside the AI
tools people already use for work and nudges them, in the moment, on how to use
AI better — without adding another task or another course to complete.

Analogy: **"Grammarly, but for how you use AI"** — or "a coach for the co-pilot."

---

## 2. The problem (why this matters)
Companies are spending real money giving employees AI tools (ChatGPT Enterprise,
Microsoft 365 Copilot, etc.). But:
- Most employees **don't know how to use them well**, or at all.
- Many are **forced** to use AI and feel resentful or lost.
- Some **dislike AI** — not because it's bad, but because they don't know how to
  make it work *the way they want* (e.g. "it does too much of my thinking" →
  they just never learned to tell it to explain instead of answer).
- Traditional training = **courses nobody finishes.** Watching a 40-min video
  doesn't change behavior at your desk on Tuesday.

**The gap:** learning happens *away* from the work. The best time to teach
someone is *while they're doing the thing.*

---

## 3. Who it's for (the customer)

There are two different "customers" in enterprise, and it's important not to
confuse them:

- **The buyer** (who pays): a company — likely an HR / L&D (Learning &
  Development) leader, a "Head of AI Enablement," or a department head with a
  budget to make their team more productive with AI.
- **The user** (who uses it): a regular employee — e.g. a marketer, analyst,
  claims adjuster, HR generalist — who's been handed AI tools and told "use
  these," and doesn't know how.

> The person we design *for* is the user. The person we *sell to* is the buyer.
> Both have to be happy.

**Ideal early customer profile (ICP) — a guess to test:**
Mid-to-large companies (a few thousand+ employees) that recently rolled out
Copilot or ChatGPT Enterprise and are frustrated that adoption is low.

---

## 4. The product — what it actually is

**Core behavior:** in-the-moment micro-coaching. As someone works with AI, the
tool occasionally surfaces a tiny, relevant tip ("Try asking it to *explain its
reasoning* instead of just giving the answer" / "You can paste the whole doc and
ask for a summary first"). Short. Contextual. Skippable. Never a homework
assignment.

**Possible form factors (each has real trade-offs — see ACTION-PLAN):**
1. **Browser extension** that rides on top of web-based AI tools (chat.openai.com,
   claude.ai, Copilot web). — *Easiest to actually build as a prototype.*
2. **Integration into desktop/enterprise AI** (like how Copilot embeds in Word,
   Excel, Teams). — *Most powerful, but requires partnerships/APIs you don't
   control yet.*
3. **A lightweight companion app** the company deploys. — *Middle ground.*

**Design principles (from your own words):**
- Coaching *in the moment*, during real work — not a separate practice course.
- Encourage efficiency; **don't add another task.**
- Help people bend AI to *their* preferences (e.g. "don't do my thinking for me")
  so even skeptics find it useful.

---

## 5. Why now
- Enterprises just bought AI licenses and are measured on adoption.
- "AI enablement / adoption" is a brand-new budget line in 2025–2026.
- Behavior-change-at-the-desk is an unsolved piece — courses aren't working.

---

## 6. How it could make money (business model)
Enterprise software is usually **SaaS**: companies pay a recurring fee, often
**per employee per month (per-seat)**. Example rough shape (illustrative only):
$3–$10 / employee / month. A 2,000-person company at $5/seat = $120k/year from
one customer. You need very few customers to reach real revenue — but each one
is hard to win.

**Cost-structure note (added after the BYOK decision, see PROTOTYPE-SPEC.md):**
the individual/free tier now costs *you* nothing to run — each person's own
Anthropic API key pays for their own AI usage, not you. That's what makes
"free extension individuals install and love" (the bottom-up plan below)
actually sustainable at zero marginal cost. It also means the eventual
per-seat SaaS fee for an *enterprise* tier would need to be justified by
something beyond "AI access" — most plausibly the manager dashboard, org-wide
policy/rules, and centralized billing (so IT doesn't need 2,000 individual
API keys) — not by the coaching itself.

---

## 7. Competition / who else is here
(Worth researching properly — see OPEN-QUESTIONS.) Broad categories:
- AI-training companies & courses (Section, Sana, BCG-style consulting, LinkedIn Learning).
- The platform vendors themselves (Microsoft & OpenAI publish their own adoption tooling).
- Grammarly-style "assistant that rides on top of your work" products.

**Your potential wedge (what makes you different):** *in-the-flow, cross-tool,
behavior-changing* coaching — not another course, not locked to one vendor.

**The scary question to answer honestly:** what stops Microsoft/OpenAI from just
building this themselves? (Partial answer: they benefit from adoption, and a
neutral, cross-tool, enterprise-customizable coach is a gap — but this needs a
real answer.)

---

## 8. Your unfair advantages
- **Enterprise access:** you just interned at State Farm — you personally know
  real enterprise employees and managers who live this problem. That is gold for
  customer interviews. Most founders would kill for that access.
- **Technical ability:** CS + Physics at Harvey Mudd — you can build a prototype
  yourself, which most idea-havers cannot.
- **Time & low stakes:** you're a sophomore. You can treat this as a paid-in-
  experience learning project with massive upside and near-zero downside.

---

## 9. Honest read on the goal
- **Dream outcome:** a real company, 6-figure income. Possible, but it's a
  multi-year, probably multi-person journey with enterprise sales — realistic to
  aim at, not realistic to expect fast.
- **Realistic near-term win (and a great one):** go through the full motion of
  finding a real problem, talking to real users, building a small real thing,
  and maybe getting your first person to say "I'd pay for this." That experience
  is worth more than the idea itself and compounds into everything you do next.
- **Stated near-term goal (current focus):** a complete, individual, portfolio-
  quality project to point to when applying to competitive roles — real
  customer discovery, a real product decision log, a working extension, an
  honest architecture pivot (shared-key server → BYOK) with a documented
  reason, and a public repo someone can actually read. This is compatible with
  both goals above, not a downgrade of them — a startup that never gets built
  teaches a recruiter nothing; a small thing built all the way through does.

All three goals point to the **same first steps** — so there's no conflict. Start.
