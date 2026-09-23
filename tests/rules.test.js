// Tests for extension/src/rules.js — the rule-based coaching "brain".
//
// Uses Node's built-in test runner (node:test) so this stays true to the
// project's zero-dependency ethos: `node --test tests/` needs nothing from
// npm. Run with `npm test`.
//
// Each case was verified against the actual browser behavior in
// playground/index.html before being written here (see the commit that
// added this file), not guessed from reading the source.

const test = require("node:test");
const assert = require("node:assert/strict");
const { analyze, evaluateAll, classify } = require("../extension/src/rules.js");

function ids(text) {
  return evaluateAll(text).map((i) => i.id);
}

function categoryOf(text, id) {
  const match = evaluateAll(text).find((i) => i.id === id);
  return match ? match.category : undefined;
}

test("empty or single-word input produces no issues", () => {
  assert.deepEqual(ids(""), []);
  assert.deepEqual(ids("hi"), []);
});

test("every issue has a unique id and a title", () => {
  const seen = new Set();
  for (const issue of evaluateAll("write a detailed step by step tutorial for beginners on how to change a car tire safely at home, double check")) {
    assert.ok(issue.id, "issue is missing an id");
    assert.ok(!seen.has(issue.id), `duplicate id ${issue.id} in a single evaluateAll() call`);
    seen.add(issue.id);
    assert.ok(issue.title, `issue ${issue.id} is missing a title`);
  }
});

test("analyze() shows at most 3 issues, highest priority first", () => {
  const r = analyze("write a detailed step by step tutorial for beginners on how to change a car tire safely at home");
  assert.ok(r.issues.length <= 3);
  const prios = evaluateAll("write a detailed step by step tutorial for beginners on how to change a car tire safely at home").map((i) => i.prio);
  assert.deepEqual(r.issues.map((i) => i.prio), prios.slice(0, 3));
});

test("analyze() appends improvement bullets only for shown issues that have one", () => {
  const text = "write a python function to sort a list";
  const r = analyze(text);
  if (r.issues.some((i) => i.add)) {
    assert.ok(r.improvedPrompt.startsWith(text));
    assert.ok(r.improvedPrompt.length > text.length);
  } else {
    assert.equal(r.improvedPrompt, text);
  }
});

// --- sensitive ---------------------------------------------------------
test("sensitive: flags an email address", () => {
  assert.ok(ids("please help me write to foo@bar.com about the invoice").includes("sensitive"));
});
test("sensitive: a plain message with no personal info is not flagged", () => {
  assert.ok(!ids("please help me write a short note to my friend").includes("sensitive"));
});

// --- grounding -----------------------------------------------------------
test("grounding: a factual question with no source ask is flagged", () => {
  assert.ok(ids("what is the capital of france").includes("grounding"));
});
test("grounding: asking it to cite sources suppresses the flag", () => {
  assert.ok(!ids("what is the capital of france? cite your sources").includes("grounding"));
});

// --- techConstraints -------------------------------------------------------
test("techConstraints: a coding task with no language/stack is flagged", () => {
  assert.ok(ids("write a script to parse csv files and print a summary table").includes("techConstraints"));
});
test("techConstraints: naming the language suppresses the flag", () => {
  assert.ok(!ids("write a python script to parse csv files").includes("techConstraints"));
});
test("techConstraints: does not false-positive on 'capital' (contains 'api') or 'description' (contains 'script')", () => {
  assert.ok(!ids("what is the capital of france").includes("techConstraints"));
  assert.ok(!ids("write a description of the product for our new website").includes("techConstraints"));
  assert.ok(!ids("clean up this transcript from the meeting").includes("techConstraints"));
});

// --- editInAI --------------------------------------------------------------
test("editInAI: editing a document in place is flagged", () => {
  assert.ok(ids("please revise this document and clean it up").includes("editInAI"));
});

// --- clarify -----------------------------------------------------------
test("clarify: a task prompt is flagged", () => {
  assert.ok(ids("write a poem about the ocean for me right now").includes("clarify"));
});

// --- context -------------------------------------------------------------
test("context: a very short prompt is flagged", () => {
  assert.ok(ids("help me plan trip").includes("context"));
});
test("context: enough words suppresses the flag", () => {
  assert.ok(!ids("help me plan an amazing weekend trip itinerary").includes("context"));
});

// --- planConstraints ---------------------------------------------------
test("planConstraints: a plan with no budget/timeline is flagged", () => {
  assert.ok(ids("write a marketing plan for a new coffee shop").includes("planConstraints"));
});
test("planConstraints: giving a budget and timeline suppresses the flag", () => {
  assert.ok(!ids("write a marketing plan for a coffee shop with a budget of $5000 and a 3 month timeline").includes("planConstraints"));
});

// --- format ----------------------------------------------------------------
test("format: no length/shape given is flagged", () => {
  assert.ok(ids("tell me about dogs").includes("format"));
});
test("format: asking for bullets suppresses the flag", () => {
  assert.ok(!ids("tell me about dogs in 3 short bullets").includes("format"));
});

// --- structure ---------------------------------------------------------
test("structure: a comparison with no table/list ask is flagged", () => {
  assert.ok(ids("Compare AWS Lambda and Google Cloud Functions briefly for cost and cold start time so I can decide which to use for my new startup").includes("structure"));
});
test("structure: asking for a table suppresses the flag", () => {
  assert.ok(!ids("Compare cats and dogs briefly and put it in a table for shedding and cost so I can decide which to adopt").includes("structure"));
});

// --- audience ------------------------------------------------------------
test("audience: a task with no audience/tone is flagged", () => {
  assert.ok(ids("write a blog post about hiking").includes("audience"));
});
test("audience: naming the audience suppresses the flag", () => {
  assert.ok(!ids("write a blog post about hiking for beginners").includes("audience"));
});

// --- persona -------------------------------------------------------------
test("persona: an expert-domain task with no role assigned is flagged", () => {
  assert.ok(ids("please review this contract for potential legal issues").includes("persona"));
});
test("persona: assigning a role suppresses the flag", () => {
  assert.ok(!ids("act as a lawyer and review this contract for potential legal issues").includes("persona"));
});

// --- criteria ------------------------------------------------------------
test("criteria: a vague quality bar ('best') is flagged", () => {
  assert.ok(ids("write the best email possible for this situation").includes("criteria"));
});

// --- negative ------------------------------------------------------------
test("negative: a long task with no negative constraints is flagged", () => {
  assert.ok(ids("write a detailed 20 word summary of this quarterly report for executives, be thorough and accurate").includes("negative"));
});
test("negative: giving a negative constraint suppresses the flag", () => {
  assert.ok(!ids("write an email to my team without using jargon and don't mention layoffs at all this week").includes("negative"));
});

// --- example -------------------------------------------------------------
test("example: a short task with no example is flagged", () => {
  assert.ok(ids("write a short poem").includes("example"));
});

// --- options ---------------------------------------------------------------
test("options: a task asking for only one version is flagged", () => {
  assert.ok(ids("write a tagline for my bakery that specializes in sourdough bread and pastries for the downtown farmers market").includes("options"));
});
test("options: asking for multiple options suppresses the flag", () => {
  assert.ok(!ids("write a tagline for my bakery, give me 2-3 different options to choose from").includes("options"));
});

// --- recency -------------------------------------------------------------
test("recency: asking about 'latest' info is flagged", () => {
  assert.ok(ids("what's the latest news on this topic").includes("recency"));
});

// --- stepByStep ----------------------------------------------------------
test("stepByStep: a calculation with no show-your-work ask is flagged", () => {
  assert.ok(ids("calculate the compound interest on $5000 at 4% over 10 years").includes("stepByStep"));
});
test("stepByStep: asking to show work suppresses the flag", () => {
  assert.ok(!ids("calculate the compound interest on $5000 at 4% over 10 years, show your work step by step").includes("stepByStep"));
});

// --- compound ------------------------------------------------------------
test("compound: two questions in one prompt is flagged", () => {
  assert.ok(ids("what is the capital of france? and what is the population?").includes("compound"));
});

// --- tutor -----------------------------------------------------------------
test("tutor: a task prompt gets the 'learn it' nudge", () => {
  assert.ok(ids("write a summary of this book").includes("tutor"));
});

// --- selfCheck -----------------------------------------------------------
test("selfCheck: a long task with no self-check ask is flagged", () => {
  assert.ok(ids("write a detailed step by step tutorial for beginners on how to change a car tire safely at home").includes("selfCheck"));
});
test("selfCheck: asking it to double-check suppresses the flag", () => {
  assert.ok(!ids("write a detailed step by step tutorial for beginners on how to change a car tire safely at home, double check your answer for mistakes").includes("selfCheck"));
});

// --- category tagging -----------------------------------------------------
// Every rule maps into one of 8 broader buckets used by the per-user skill
// dashboard (profile.js) — see docs/PromptCoach_Direction_and_Roadmap.pdf.
// One test per rule, using the same prompts already verified above, so this
// only checks the NEW thing (category) rather than re-deriving whether the
// rule fires at all.
test("every rule has exactly one of the 8 known categories", () => {
  const known = new Set([
    "safety", "accuracyGrounding", "missingConstraints", "iterationMindset",
    "vagueAsk", "missingContext", "outputFormat", "tooBroad",
  ]);
  const seenIds = new Set();
  // A battery of prompts broad enough to trigger all 20 rules at least once.
  const prompts = [
    "please help me write to foo@bar.com about the invoice",
    "what is the capital of france",
    "write a script to parse csv files and print a summary table",
    "please revise this document and clean it up",
    "write a poem about the ocean for me right now",
    "help me plan trip",
    "write a marketing plan for a new coffee shop",
    "tell me about dogs",
    "Compare AWS Lambda and Google Cloud Functions briefly for cost and cold start time so I can decide which to use for my new startup",
    "write a blog post about hiking",
    "please review this contract for potential legal issues",
    "write the best email possible for this situation",
    "write a detailed 20 word summary of this quarterly report for executives, be thorough and accurate",
    "write a short poem",
    "write a tagline for my bakery that specializes in sourdough bread and pastries for the downtown farmers market",
    "what's the latest news on this topic",
    "calculate the compound interest on $5000 at 4% over 10 years",
    "what is the capital of france? and what is the population?",
    "write a summary of this book",
    "write a detailed step by step tutorial for beginners on how to change a car tire safely at home",
  ];
  for (const p of prompts) {
    for (const issue of evaluateAll(p)) {
      seenIds.add(issue.id);
      assert.ok(issue.category, `rule ${issue.id} is missing a category`);
      assert.ok(known.has(issue.category), `rule ${issue.id} has unknown category ${issue.category}`);
    }
  }
  // Sanity check the battery actually exercised all 20 rules, not a subset.
  assert.equal(seenIds.size, 20, `expected all 20 rules to fire across the battery, saw ${seenIds.size}: ${[...seenIds].sort()}`);
});

test("category mapping matches the documented taxonomy for representative rules", () => {
  assert.equal(categoryOf("please help me write to foo@bar.com about the invoice", "sensitive"), "safety");
  assert.equal(categoryOf("what is the capital of france", "grounding"), "accuracyGrounding");
  assert.equal(categoryOf("write a script to parse csv files and print a summary table", "techConstraints"), "missingConstraints");
  assert.equal(categoryOf("please revise this document and clean it up", "editInAI"), "iterationMindset");
  assert.equal(categoryOf("write a poem about the ocean for me right now", "clarify"), "vagueAsk");
  assert.equal(categoryOf("help me plan trip", "context"), "missingContext");
  assert.equal(categoryOf("tell me about dogs", "format"), "outputFormat");
  assert.equal(categoryOf("what is the capital of france? and what is the population?", "compound"), "tooBroad");
});

// --- classify() ------------------------------------------------------------
// Gates whether refinement-style coaching (iteration nudges, auto AI
// critique) applies at all — see docs/PromptCoach_Direction_and_Roadmap.pdf.
test("classify: discrete factual questions are 'factual'", () => {
  assert.equal(classify("what's 7*8"), "factual");
  assert.equal(classify("what year did the Roman Empire fall?"), "factual");
  assert.equal(classify("is the sky blue"), "factual");
});
test("classify: open-ended / generative asks are 'generative'", () => {
  assert.equal(classify("write a poem about the ocean"), "generative");
  assert.equal(classify("explain photosynthesis"), "generative");
  assert.equal(classify("compare react and vue"), "generative");
});
test("classify: empty or whitespace-only input is 'factual' (nothing to coach)", () => {
  assert.equal(classify(""), "factual");
  assert.equal(classify("   "), "factual");
});
