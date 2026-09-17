# Privacy Design — Real Manager-Dashboard Telemetry

`dashboard/` is currently a mockup with hard-coded sample data (see its
footer: *"Illustrative sample data"*). `OPEN-QUESTIONS.md` flags exactly why:
**enterprises are strict about what a browser extension can see and report
about what employees type, and we hadn't answered that before building
anything real.** This doc answers it — a design a company could actually
trust, before a single line of production telemetry code exists.

This is a design doc, not a shipped feature. `extension/src/telemetry.js`
is a working sketch of the client-side half (aggregation + opt-in gate),
deliberately **not wired into `content.js`/`manifest.json`** — there's no
backend to send it to yet, and turning it on is a product/legal decision,
not just an engineering one.

## 1. The hard constraint

The thing being coached is **the literal text someone typed to an AI** —
often before they've decided whether it's sensitive. That text can contain
anything: trade secrets, a draft layoff email, a customer's SSN, health
information. So the first design rule is not "anonymize the prompt" — it's:

> **Prompt text never leaves the browser. Full stop. Not encrypted, not
> hashed, not truncated. It is used locally to run `rules.js` and then
> discarded.**

Everything below is about the *next* layer down: is it even safe to report
*"this employee's rules-engine flagged the 'no accuracy check' rule 4 times
today"* — a fact about behavior, not content?

## 2. Data classification

| Data | Ever leaves the browser? |
|---|---|
| Raw prompt text | **Never.** |
| Which rule IDs fired (e.g. `grounding`, `format`) | Only as an aggregated count (see §3) |
| Timestamp | Only bucketed to a day, never exact time |
| Individual identity (name, email, browser/user ID) | **Never sent to the aggregation step.** Only a team/org label the user's employer already assigned (see §4) |
| Whether the AI-rewrite feature was used | Same treatment as a rule ID — a count, nothing else |
| The `sensitive` rule firing specifically | Counted like any other rule — **never** with the text that triggered it |

The dashboard's "sensitive-data flags" metric (in `dashboard/`) is a count
of *how often* the `sensitive` rule fired — never what was flagged. That
distinction matters enough to call out on the dashboard UI itself, not just
in this doc.

## 3. Why aggregation has to happen in two places, not one

A single browser only ever sees one person's usage. If a client sends
*"user X triggered `sensitive` 3 times today"* directly, the aggregation
step receives individually-identifiable behavior even if no name is
attached — a manager who knows only one person on a team used the tool
that day can de-anonymize it trivially. This is the mistake a naive design
makes: doing k-anonymity thresholds *client-side* doesn't work, because
one client can't see the other N-1 employees' counts to know if the group
is big enough to hide in.

So the design splits the work:

- **Client (`telemetry.js`, in this repo today):** turn rule triggers into
  small, day-bucketed, per-team counts. No raw text, no per-message
  granularity, no precise timestamps. This is the part that can be open,
  audited, and shipped without a backend existing yet.
- **Aggregation server (not built — future work):** the only place that
  ever sees a batch from an individual browser. Its one job is to hold
  counts in a buffer **per (team, day, rule)** and refuse to release any
  number to a manager's dashboard until at least **k=5** distinct browser
  installs have contributed to it that day. Below that threshold, the
  dashboard shows "not enough data yet" instead of a number. This is the
  actual privacy boundary — it cannot be done correctly on the client,
  and no client-side design should claim otherwise.

This repo does not implement the aggregation server — that's real
backend/infra work with its own security review, and pretending to solve
it with a client-only trick would be worse than admitting it's unsolved.

## 4. Opt-in, not opt-out

- Telemetry defaults to **off** (`chrome.storage.local` flag,
  `telemetryOptIn: false`). Nothing is measured, batched, or queued unless
  a user (or their admin, via managed policy — a real MV3 mechanism) turns
  it on.
- The team/org label is something the *employer* provides at deploy time
  (e.g. via Chrome managed storage), never something inferred from the
  user's email or account — no employer-run backend needs to know who a
  specific employee is to show "Team: Sales West" trends.
- Turning it off deletes the local aggregation buffer immediately.

## 5. What ships in this repo today vs. later

| Piece | Status |
|---|---|
| `rules.js` — the coaching logic | Shipped, runs 100% locally |
| `telemetry.js` — local aggregation + opt-in gate | **New in this change.** Pure logic, unit-testable, not wired into the extension's message flow |
| Consent UI in `options.html` | Not built — needs real product copy, not a placeholder checkbox |
| Aggregation server enforcing k-anonymity | Not built — the actual blocking piece before `dashboard/` can show real data |
| `dashboard/` reading real data | Blocked on the above |

## 6. Example of what an aggregated event looks like

```json
{
  "team": "sales-west",
  "date": "2026-09-16",
  "counts": { "grounding": 3, "format": 5, "sensitive": 1 }
}
```

No user ID. No prompt text. No exact time. One row per browser, per day —
and even this row is only useful to an employer once a server has merged
at least 5 of them together for the same team/day.
