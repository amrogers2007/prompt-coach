---
name: dashboard
description: "Show the user's AI habits over time as a page in their browser: how much they use AI, their AI Fluency score, their habits, the habit gaps the coach spotted, and how all of it changed. Use when the user asks for their dashboard, trends, history, or how their AI use has changed over time."
argument-hint: "[demo]"
allowed-tools: Bash(sh *scripts/run.sh *)
---

Build the user's dashboard and open it in their browser:

- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" dashboard`
- If they asked for a sample or demo (for example to show someone what it looks like), add `--demo`: that builds it
  from made-up data and never touches theirs.

The command prints where the page was saved. Then tell the user, in two or three plain sentences, that it opened in
their browser (and the file path in case it didn't), and what they can see there: their score over time, how much they
use AI, their habits, and the habit gaps that are fading or sticking. Mention that the page was made on their computer
and nothing in it was sent anywhere.

Requested: $ARGUMENTS
