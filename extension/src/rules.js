// =============================================================================
// rules.js  —  THE "BRAIN"
// -----------------------------------------------------------------------------
// Pure logic. Give it a prompt string, get back { issues, improvedPrompt }.
// Friendly + SHORT on purpose. Shows at most the 3 highest-priority issues so
// it never overwhelms. v1 = hard-coded rules (no AI model).
//
// evaluateAll() vs analyze(): evaluateAll() runs every rule and returns all
// matches (used by tests, and by telemetry.js's future caller — see
// docs/PRIVACY-DESIGN.md — which needs to count every rule that fired, not
// just the 3 shown). analyze() is the one the extension UI actually uses: it
// calls evaluateAll() and keeps only the top 3, plus the rewritten prompt.
// =============================================================================

(function () {
  function evaluateAll(rawText) {
    var text = (rawText || "").trim();
    var wc = text ? text.split(/\s+/).length : 0;
    function has(ws) { var l = text.toLowerCase(); return ws.some(function (w) { return l.indexOf(w) >= 0; }); }

    if (wc < 2) return [];

    var isQ = text.indexOf("?") >= 0 ||
      /^(what|who|when|where|which|why|how|is|are|does|do|can|should)\b/i.test(text);
    var isTask = /^(write|create|make|solve|do|build|generate|draft|help me|email|plan)\b/i.test(text);

    var all = [];

    // 9 — Sensitive data (safety first)
    var sensitive =
      /[\w.+-]+@[\w-]+\.[\w.-]+/.test(text) ||          // email
      /\b\d{3}-\d{2}-\d{4}\b/.test(text) ||             // SSN-like
      /\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b/.test(text) ||   // phone-like
      /\b\d{13,16}\b/.test(text) ||                     // card-like
      has(["confidential", "social security", "ssn", "credit card", "password", "account number"]);
    if (sensitive) all.push({ prio: 1, id: "sensitive",
      title: "⚠️ Looks like private info", why: "Avoid pasting personal or confidential data into AI." });

    // 2 — Accuracy safeguard
    if (isQ && !has(["source", "cite", "citation", "reference", "according to"]))
      all.push({ prio: 2, id: "grounding",
        title: "No accuracy check", why: "AI can make things up — ask for sources.",
        eg: "Cite sources; say if you're unsure.",
        add: "Cite your sources, and say if you're unsure instead of guessing." });

    // 12 — Missing technical constraints (coding tasks)
    var codeWords = ["code", "function", " script", "program", "algorithm",
      "class ", " api", "bug", "debug", "regex", "sql query", "endpoint", "unit test"];
    var stackWords = ["python", "javascript", "typescript", "java ", "c++", "c#",
      "ruby", "golang", " go ", "rust", "php", "swift", "kotlin", "html", "css",
      "sql", "bash", "node", "react", "vue", "angular", "version", "framework", "library"];
    if (has(codeWords) && !has(stackWords))
      all.push({ prio: 3.5, id: "techConstraints",
        title: "No language or stack given", why: "Say the language, framework, and version — otherwise it guesses.",
        eg: "In Python 3.11, no external libraries.",
        add: "Language/framework/version: [fill in]." });

    // 2.5 — Edit in the AI, not Word
    // Detects "revise/edit/polish this document" style requests and coaches
    // people to keep iterating inside the chat (ChatGPT Canvas / Claude
    // Artifacts) instead of the old habit of copy-pasting into Word between
    // every round of edits.
    var editVerbs = ["edit this", "edit the", "revise this", "revise the",
      "make edits", "make changes", "proofread", "polish this", "polish the",
      "clean up this", "clean up the", "rewrite this", "rewrite the",
      "redline", "track changes", "tighten this", "tighten the", "reword"];
    var docWords = ["document", "draft", "essay", "report", "paper", "section",
      "paragraph", "memo", "letter", "cover letter", "resume", "manuscript"];
    var wordAppWords = ["word doc", "word document", ".docx", "google doc", "in word", "microsoft word"];
    var isEditTask = has(editVerbs) && (has(docWords) || has(wordAppWords) || wc > 40);
    if (isEditTask)
      all.push({ prio: 2.5, id: "editInAI",
        title: "Edit it here, not in Word", why: "Keep revising in this chat — the AI can edit the text " +
          "directly and you just say what's next, instead of pasting into Word every round.",
        eg: "Make the edit right here; I'll tell you what to change next instead of copying into Word.",
        add: "Make the edit directly here (not just describe it) so we can keep iterating without me copy-pasting into Word." });

    // 5 — Let it ask first
    if (isTask || wc < 8)
      all.push({ prio: 3, id: "clarify",
        title: "Let it ask first", why: "Have the AI ask questions if anything's unclear.",
        eg: "Ask me anything unclear before answering.",
        add: "If anything is unclear, ask me before you answer." });

    // 3 — Context
    if (wc < 6)
      all.push({ prio: 4, id: "context",
        title: "Too little context", why: "Add your goal, who it's for, and key details.",
        eg: "(Goal: ___. For: ___. Details: ___)",
        add: "Context — goal: [fill in]. For: [fill in]. Key details: [fill in]." });

    // 13 — Missing planning constraints (budget/timeline/resources)
    var planWords = ["plan", "strategy", "roadmap", "proposal", "budget", "itinerary"];
    var constraintWords = ["budget of", "deadline", "timeline", "by next", "days",
      "weeks", "months", "$", "resources available", "team of"];
    if (isTask && has(planWords) && !has(constraintWords))
      all.push({ prio: 4.5, id: "planConstraints",
        title: "No budget, timeline, or resources", why: "Real-world limits shape a plan — without them it's generic.",
        eg: "Budget: $___. Timeline: ___. Team/resources: ___.",
        add: "Constraints — budget: [fill in]. Timeline: [fill in]. Resources: [fill in]." });

    // 1 — Format / length
    if (!has(["bullet", "concise", "short", "brief", "one sentence", "paragraph",
      "word", "words", "list", "step", "table", "tl;dr", "summary", "summarize"]))
      all.push({ prio: 5, id: "format",
        title: "No length or format", why: "Say the shape you want, or it may overshoot.",
        eg: "Answer in 3 short bullets.",
        add: "Answer concisely in 3 short bullets." });

    // 14 — Comparison without a structured output ask
    var comparisonWords = ["compare", " vs ", " vs.", "versus", "pros and cons",
      "difference between", "which is better", "options for", "alternatives to"];
    var structureWords = ["table", "side by side", "side-by-side", "columns",
      "bullet", "list", "pros and cons"];
    if (has(comparisonWords) && !has(structureWords))
      all.push({ prio: 5.5, id: "structure",
        title: "No structured output ask", why: "Comparisons read easier as a table or side-by-side list.",
        eg: "Put it in a table with one row per option.",
        add: "Put the comparison in a table (one row per option)." });

    // 6 — Audience / tone
    if (isTask && !has(["for ", "audience", "tone", "formal", "casual", "professional",
      "beginner", "expert", "5th", "executive", "exec", "kids", "children", "simple terms"]))
      all.push({ prio: 6, id: "audience",
        title: "No audience or tone", why: "Say who it's for and the tone to use.",
        eg: "Write for execs, professional tone.",
        add: "Write it for [audience], in a [tone] tone." });

    // 15 — No role/persona for expert-level tasks
    var expertWords = ["legal", "medical", "financial advice", "contract",
      "diagnos", "tax ", "investment", "clinical", "compliance", "security audit",
      "code review"];
    var personaWords = ["act as", "you are a", "as a doctor", "as a lawyer",
      "as an expert", "as a senior", "persona"];
    if (has(expertWords) && !has(personaWords))
      all.push({ prio: 6.5, id: "persona",
        title: "No role assigned", why: "Assigning an expert persona sharpens specialist answers.",
        eg: "Act as a [specialist] with 10+ years of experience.",
        add: "Act as an experienced [specialist] for this." });

    // 11 — Success criteria
    if (isTask && has(["good", "great", "best", "nice", "better", "perfect"]))
      all.push({ prio: 7, id: "criteria",
        title: "Vague quality bar", why: "Say what 'good' means here.",
        eg: "It's good if it [your criteria]." });

    // 16 — No negative constraints
    var negWords = ["don't", "do not", "avoid", "without", "skip", "exclude",
      "no jargon", "not including"];
    if (isTask && wc >= 10 && !has(negWords))
      all.push({ prio: 7.5, id: "negative",
        title: "No negative constraints", why: "Saying what to avoid is as useful as saying what you want.",
        eg: "Avoid jargon; don't include an intro paragraph.",
        add: "Avoid: [things to skip or exclude]." });

    // 8 — Give an example
    if (isTask && wc < 25 && !has(["example", "e.g", "for instance", "such as", "like this"]))
      all.push({ prio: 8, id: "example",
        title: "No example", why: "Show a sample of what you want.",
        eg: "Here's an example of the style I want: ___" });

    // 17 — Accepting the first draft
    var optionWords = ["options", "alternatives", "variations", "different versions",
      "few different", "couple of options", "2 options", "3 options", "multiple"];
    if (isTask && wc >= 8 && wc < 40 && !has(optionWords))
      all.push({ prio: 8.5, id: "options",
        title: "Only asking for one version", why: "Ask for 2-3 options so you can compare instead of taking the first draft.",
        eg: "Give me 2-3 different versions to choose from.",
        add: "Give me 2-3 different options to choose from." });

    // 10 — Recency
    if (has(["latest", "recent", "current", "today", "this year", "newest", "right now", "2024", "2025", "2026"]))
      all.push({ prio: 9, id: "recency",
        title: "Asking about current info", why: "AI may be out of date — ask it to flag uncertainty.",
        eg: "Note if this might be outdated." });

    // 18 — No step-by-step reasoning for math/logic tasks
    var reasoningWords = ["calculate", "solve", "prove", "derive", "logic puzzle",
      "math problem", "equation", "optimi", "probability", "proof"];
    var showWorkWords = ["step by step", "step-by-step", "show your work",
      "show your reasoning", "walk me through", "walk through"];
    if (has(reasoningWords) && !has(showWorkWords))
      all.push({ prio: 9.5, id: "stepByStep",
        title: "No step-by-step ask", why: "Reasoning aloud, step by step, makes math/logic answers more accurate.",
        eg: "Show your work, step by step.",
        add: "Show your work step by step." });

    // 7 — Compound
    if ((text.match(/\?/g) || []).length >= 2)
      all.push({ prio: 10, id: "compound",
        title: "Several questions at once", why: "Ask one thing at a time for deeper answers.",
        eg: "Split this into separate questions." });

    // 4 — Tutor mode
    if (isTask)
      all.push({ prio: 11, id: "tutor",
        title: "Learn it, not just get it?", why: "Ask it to guide you, not do your thinking.",
        eg: "Guide me step by step instead of giving the answer." });

    // 19 — No self-check ask
    var selfCheckWords = ["double check", "double-check", "check your work",
      "review your answer", "verify your answer", "sanity check", "self-check"];
    if (isTask && wc >= 15 && !has(selfCheckWords))
      all.push({ prio: 10.5, id: "selfCheck",
        title: "No ask to double-check itself", why: "Asking it to review its own answer catches mistakes before you do.",
        eg: "Double-check your answer for mistakes before giving it to me.",
        add: "Double-check your answer for mistakes before giving it to me." });

    all.sort(function (a, b) { return a.prio - b.prio; });
    return all;
  }

  // Keep it short: highest-priority 3 only.
  function analyze(rawText) {
    var text = (rawText || "").trim();
    var all = evaluateAll(text);
    var shown = all.slice(0, 3);
    var adds = shown.filter(function (i) { return i.add; }).map(function (i) { return i.add; });
    var improved = adds.length
      ? text + "\n\n" + adds.map(function (a) { return "- " + a; }).join("\n")
      : text;

    return { issues: shown, improvedPrompt: improved };
  }

  var api = { analyze: analyze, evaluateAll: evaluateAll };
  if (typeof window !== "undefined") window.PromptCoach = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
