# Interview Notes

Informal early conversations with real AI users (friends, students, tech
workers, etc.). Keep adding as you talk to more people.

## Recurring pain points (as users described them)
1. **"It does too much of the thinking for me."**
   - Real cause: never learned to make AI explain/coach instead of just answer.
   - Fix: prompt patterns like "explain your reasoning," "ask me questions
     first," "act as a tutor, don't give the answer yet."
2. **"It gives me the wrong info / it makes things up."**
   - Real cause: no grounding, not asking for sources, not giving it context.
   - Fix: "cite sources," "say 'I don't know' if unsure," paste-the-source-first.
3. **"The response is way too long."**
   - Real cause: never learned to constrain output.
   - Fix: "answer in 3 bullets," "one sentence," "TL;DR first."
4. **"It doesn't actually give me the info I need."**
   - Real cause: vague prompt, missing context/goal.
   - Fix: state the goal, audience, format; give examples.

## Key insight
Nearly every complaint traces back to **prompting skill**, not the AI being bad.
The product is really a **prompt-quality coach**, delivered in the moment.

## The two user types to serve
- **Enthusiasts** — want to get more efficient; receptive to tips.
- **Skeptics** — dislike AI because it does something they didn't ask for; the
  win is showing them how to make it behave the way *they* want (e.g. "stop
  doing my thinking"). Converting a skeptic is a powerful demo.

## Interview: physics professor (hard skeptic), 2026-09-17
In his own words:
- "I get it trained for the task that I want it to do, by the time it is
  trained there are no tokens left."
- "Want to develop individual critical thinking in my students and myself
  without having AI think for me."
- "Not ethical, AI is going in the wrong direction."
- "It's just not good enough yet to reliably trust — it doesn't do the
  tasks that I want, it is super confident on wrong information, and it
  doesn't ask me for enough clarification to be able to do what I want it
  to do."

**Breaks an assumption.** The `Key insight` above claims nearly every
complaint traces back to prompting skill, not the AI being bad. This
interview pushes back hard on that. Only 2 of his 4 points are a skill gap
Prompt Coach already targets:
- Overconfident wrong answers, not enough clarifying questions → directly
  addressed by the existing "ask for sources"/"let it ask first"/"tutor
  me" rules. **Good pitch quote for skeptics like him.**
- The other two are NOT a skill gap and Prompt Coach doesn't (and maybe
  can't) fix them:
  - **Setup cost vs. token budget** — for a custom/repeated task, the
    effort of "training" it eats the budget before he gets value. A
    prompting *coach* doesn't reduce that cost; it might even add to it.
  - **Values-based refusal** — he doesn't want AI doing his (or his
    students') thinking, on principle, not because he prompts it badly.
    No prompt tip converts this; it's a stance, not a skill gap.

Worth naming explicitly in `IDEA.md` / `OPEN-QUESTIONS.md`: the "just a
prompting-skill problem" framing may not hold for educators/skeptics whose
objection is ethical or pedagogical rather than usability-based.
