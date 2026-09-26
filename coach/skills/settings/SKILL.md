---
name: settings
description: Change Prompt Coach settings: pause or resume coaching, turn it off, make coaching lighter or more frequent, export or delete the user's data, or check that the coach is working.
argument-hint: "[status | pause 2h | resume | off | intensity light|normal|frequent | export | reset | doctor]"
allowed-tools: Bash(sh *scripts/run.sh *)
---

Manage Prompt Coach for the user.

Map what they asked to one of these commands and run it with the Bash tool
(default to `status` if they gave no instruction):

- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings status`
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings pause 2h` (accepts minutes `30m`, hours `2h`, days `1d`)
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings resume`
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings off`
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings intensity light` (or `normal`, `frequent`)
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings export` (aggregate numbers only, as JSON)
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" doctor` (health check)
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings reset` deletes ALL their scores, streaks and history.
  This is destructive: first ask the user to confirm in plain words, and only then add `--yes`.

Requested: $ARGUMENTS

After running, confirm in one friendly sentence what changed. Requests like "I'm in a hurry" or
"stop the questions for today" mean `pause` (suggest `pause 1d`); "less often" means `intensity light`.
