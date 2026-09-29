# The Prompt Coach loop

**Prompt Coach teaches people to use AI well while they're using it, not in a course beforehand.**
This page is a short public summary of the project's business case.

## The problem: having AI isn't the same as using it well

- **Few use it often.** 52% of U.S. employees use AI at work at least a few times a year, but only 30% use it a
  few times a week or more, and 15% daily. ([Gallup, May 2026][gallup])
- **Most use is basic.** 88% of employees use AI in their daily work, mostly for search and summaries. Only 5%
  use it in advanced ways, and 12% get enough training. ([EY, 15,000 employees][ey])
- **Training is rare.** 39% of workers used AI at work in the past year, but only 15.9% say their employer offers
  AI training. 19% of users say tasks take longer while they're still learning. ([New York Fed, 2026][nyfed])
- **Access doesn't become habit.** In a trial with 7,137 workers at 66 large firms, over 90% of those given
  Microsoft 365 Copilot tried it, but the average person used it in only 41% of weeks. ([Dillon et al.,
  2025][copilot])
- **Short lessons in the moment help.** A review of 40 studies found that short, focused, personalized lessons
  improve knowledge, behavior and motivation. ([Monib et al., 2024][micro])

So Prompt Coach coaches inside the conversation with the AI, at the moment a good habit matters.

## How it works

![The Prompt Coach loop: Detect, Coach, Act, Verify, Improve](img/coaching-loop.svg)

| Step | What Prompt Coach does |
|---|---|
| **1. Detect** | 27 checks spot moments like a missing audience or an unchecked number. Only labels are stored. |
| **2. Coach** | Offers one short tip, after the answer, from a [library of 76 best practices](../coach/library/recommendations.md). |
| **3. Act** | If you say "yes", the AI does the better step with you, such as asking who your reader is. |
| **4. Verify** | Tracks whether tips are taken and whether the issue comes back less often. |
| **5. Improve** | Pauses tips people keep turning down. Re-tests the checks on every change. |

## Principles

- **Fewer, better tips.** A wrong tip costs trust, so success is never measured by how many tips appear.
- **Private.** The coach runs on your computer and never stores what you type.
- **Your choice.** Every tip is an offer. You can decline it, mute it, or ask why it appeared.
- **Safety first.** Sensitive data and high-stakes decisions are flagged right away.

## Does it work?

- **Spotting the right moments.** On prompts it had never seen, 93% of the moments it flagged were real, and it
  caught 88% of them. A second blind test scored 80% on both. After fixes, it scores about 98% on the test sets;
  real prompts from a pilot are the next test.
- **Changing habits.** A pilot mode holds back coaching on some issues so they can be compared with coached ones.
  In simulated pilots, coached issues came back 7% of the time against 18% for uncoached ones.
- **Still unknown:** whether it changes real behavior at work. That needs a pilot with real people.

**Not built yet:** coaching in other work tools, insights for managers, and levels others can verify.

## Sources

- Gallup, [AI indicator][gallup], May 2026 data.
- EY, [press release on its survey of 15,000 employees and 1,500 employers][ey], November 2025.
- Federal Reserve Bank of New York, [Liberty Street Economics post on AI at work and training][nyfed], April 2026.
- Dillon, Jaffe, Immorlica and Stanton, [*Shifting Work Patterns with Generative AI*][copilot], NBER Working Paper
  33795, 2025.
- Monib, Qazi and Apong, [*Microlearning beyond boundaries: A systematic review and a novel framework for
  improving learning outcomes*][micro], *Heliyon*, 2024.

Many of the library's best practices began as a research table contributed to the project
([`BEST-PRACTICES-SOURCE.md`](BEST-PRACTICES-SOURCE.md)).

[gallup]: https://www.gallup.com/699797/indicator-artificial-intelligence.aspx
[ey]: https://www.ey.com/en_gl/newsroom/2025/11/ey-survey-reveals-companies-are-missing-out-on-up-to-40-percent-of-ai-productivity-gains-due-to-gaps-in-talent-strategy
[nyfed]: https://libertystreeteconomics.newyorkfed.org/2026/04/use-of-gen-ai-in-the-workplace-and-the-value-of-access-to-training/
[copilot]: https://www.hbs.edu/ris/Publication%20Files/w33795_dd1e2857-d195-4333-86ba-6a8953119ed4.pdf
[micro]: https://pmc.ncbi.nlm.nih.gov/articles/PMC11774797/
