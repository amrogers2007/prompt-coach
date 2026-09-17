// =============================================================================
// rules.js  —  THE "BRAIN"
// -----------------------------------------------------------------------------
// Pure logic. Give it a prompt string, get back { issues, improvedPrompt }.
// Friendly + SHORT on purpose. Shows at most the 3 highest-priority issues so
// it never overwhelms. v1 = hard-coded rules (no AI model).
// =============================================================================

(function () {
  function analyze(rawText) {
    var text = (rawText || "").trim();
    var wc = text ? text.split(/\s+/).length : 0;
    function has(ws) { var l = text.toLowerCase(); return ws.some(function (w) { return l.indexOf(w) >= 0; }); }

    if (wc < 2) return { issues: [], improvedPrompt: text };

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

    // 1 — Format / length
    if (!has(["bullet", "concise", "short", "brief", "one sentence", "paragraph",
      "word", "words", "list", "step", "table", "tl;dr", "summary", "summarize"]))
      all.push({ prio: 5, id: "format",
        title: "No length or format", why: "Say the shape you want, or it may overshoot.",
        eg: "Answer in 3 short bullets.",
        add: "Answer concisely in 3 short bullets." });

    // 6 — Audience / tone
    if (isTask && !has(["for ", "audience", "tone", "formal", "casual", "professional",
      "beginner", "expert", "5th", "executive", "exec", "kids", "children", "simple terms"]))
      all.push({ prio: 6, id: "audience",
        title: "No audience or tone", why: "Say who it's for and the tone to use.",
        eg: "Write for execs, professional tone.",
        add: "Write it for [audience], in a [tone] tone." });

    // 11 — Success criteria
    if (isTask && has(["good", "great", "best", "nice", "better", "perfect"]))
      all.push({ prio: 7, id: "criteria",
        title: "Vague quality bar", why: "Say what 'good' means here.",
        eg: "It's good if it [your criteria]." });

    // 8 — Give an example
    if (isTask && wc < 25 && !has(["example", "e.g", "for instance", "such as", "like this"]))
      all.push({ prio: 8, id: "example",
        title: "No example", why: "Show a sample of what you want.",
        eg: "Here's an example of the style I want: ___" });

    // 10 — Recency
    if (has(["latest", "recent", "current", "today", "this year", "newest", "right now", "2024", "2025", "2026"]))
      all.push({ prio: 9, id: "recency",
        title: "Asking about current info", why: "AI may be out of date — ask it to flag uncertainty.",
        eg: "Note if this might be outdated." });

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

    // Keep it short: highest-priority 3 only.
    all.sort(function (a, b) { return a.prio - b.prio; });
    var shown = all.slice(0, 3);
    var adds = shown.filter(function (i) { return i.add; }).map(function (i) { return i.add; });
    var improved = adds.length
      ? text + "\n\n" + adds.map(function (a) { return "- " + a; }).join("\n")
      : text;

    return { issues: shown, improvedPrompt: improved };
  }

  window.PromptCoach = { analyze: analyze };
})();
