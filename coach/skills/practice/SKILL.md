---
name: practice
description: Run a short, low-stakes practice round where the user writes a prompt for a realistic work scenario and gets coached on it. Use when the user asks to practice, train, or take a quick lesson on prompting.
argument-hint: "[topic, e.g. context | iteration | verification]"
disable-model-invocation: true
---

Run a 3-minute practice round. Practice never affects the user's score; it is a safe place to try things.

1. Ask ONE short question about their job (role and one recurring task) unless you already know it from the conversation.
2. Invent a realistic scenario from their world in 2-3 sentences (a task where a first-try prompt would be mediocre).
   If `$ARGUMENTS` names a habit (context, iteration, shape, verification), design the scenario so that habit matters.
3. Ask them to write the prompt they would type. Stop and wait.
4. When they answer, respond in this order, briefly:
   - one specific thing they did well;
   - what a reader with no context would still be missing (as a question, not a rewrite);
   - offer to run the prompt for real so they can see the difference, then let them improve it and compare.
5. Finish with a one-line takeaway they can reuse, and offer another round.

Keep it playful and encouraging, and never longer than needed.
