---
name: score
description: Show the user's AI Fluency level, score, streak and a shareable summary. Use when the user asks about their AI score, level, progress, streak, or wants something to show a manager.
argument-hint: "[json]"
allowed-tools: Bash
---

Show the user their Prompt Coach scoreboard.

1. Run this command with the Bash tool (add `--json` only if the user asked for JSON/export data):

   `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" score $ARGUMENTS`

2. Show the command's output to the user exactly as printed (it is already formatted Markdown). Do not reword the numbers or invent any.
3. Then add at most two sentences: celebrate one genuine strength from their habits, and name the single most useful next step (the "Best next step" line).
4. If the command prints nothing or errors, run `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" doctor` and explain the problem in plain language (most often: Python 3.8+ is not installed).

If they want to share it, point them to the two files the command saved (`summary.md` and `badge.svg` in their `.prompt-coach` folder). Mention that the summary contains only aggregate numbers, never prompts or document names, and that it is measured on their own device.
