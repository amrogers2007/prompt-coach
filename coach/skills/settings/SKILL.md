---
name: settings
description: "Change Prompt Coach settings: pause or resume coaching, turn it off, make coaching lighter or more frequent, explain why a tip appeared, mute a tip, see whether the coaching is working, export or delete the user's data, or check that the coach is working."
argument-hint: "[status | pause 2h | resume | off | intensity light|normal|frequent | why | mute <tip> | unmute <tip|all> | insights | experiment <percent> | toasts chat|system|auto | export | reset | doctor]"
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
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings toasts chat` (or `system`, `auto`): how short status notes such as the welcome and level-ups are delivered. `chat` = Claude says them in its reply; `system` = shown by the app. Default `auto` uses `chat` in the Claude desktop app.
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings why`: explains the last coaching tip (what spotted it) and its id.
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings mute <tip-id>` / `settings unmute <tip-id>` / `settings unmute all`:
  stop (or restart) one particular tip. Run `settings why` first to get the id if they mean "that last tip".
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" insights`: is the coaching working? Tips shown, taken, declined, "didn't
  fit", and whether issues came up less after being coached. Summarize it in two or three plain sentences.
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings experiment 20` (or `0` to stop): pilot mode for teams measuring the
  coach. A random 20% of issues get no coaching so they can be compared with coached ones. Only use when the user
  explicitly asks to run an experiment or pilot; explain that some tips will be held back.
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings export` (aggregate numbers only, as JSON)
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" doctor` (health check)
- `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" settings reset` deletes ALL their scores, streaks and history.
  This is destructive: first ask the user to confirm in plain words, and only then add `--yes`.

Requested: $ARGUMENTS

After running, confirm in one friendly sentence what changed. Requests like "I'm in a hurry" or
"stop the questions for today" mean `pause` (suggest `pause 1d`); "less often" means `intensity light`;
"why did you say that?" about a tip means `why`; "stop telling me that" means `why` then `mute` with its id.
