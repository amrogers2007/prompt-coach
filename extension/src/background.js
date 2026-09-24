// =============================================================================
// background.js  —  the ONLY place that talks to the Anthropic API
// -----------------------------------------------------------------------------
// This is a Manifest V3 service worker. It holds no secrets of its own — it
// reads the user's OWN API key out of chrome.storage.local (set on the
// options page) and calls Claude directly from their browser.
//
// Why this exists instead of content.js calling fetch() directly:
//   - Service workers have the extension's full host_permissions and are not
//     subject to the page's Content-Security-Policy, so this is the reliable
//     place to make a cross-origin request to api.anthropic.com.
//   - It keeps "talks to the network" in one small, auditable file.
//
// Why this design instead of the old local Node server:
//   - No server to install or keep running. The user's own key, in their own
//     browser, pays for their own usage — nothing routes through us.
// =============================================================================

const MODEL = "claude-haiku-4-5"; // fast + cheap, good fit for a prompt rewrite

// Two modes (chosen by the toggle on the on-page card):
//   improve — rewrite the prompt for the user (with a short "what changed").
//   teach   — don't rewrite; tell the user what to strengthen and why, so
//             they make the edits themselves (the "AI teaching you to use AI"
//             idea — and it keeps the user doing the thinking).
const IMPROVE_SYSTEM = `You are Prompt Coach. Rewrite the user's AI prompt so it gets a
noticeably better result, then explain what you changed in 1-3 short tips.

Rules:
- Stay faithful to what the user actually wants. Keep their voice and intent; do
  not add requirements, tone, or constraints they didn't imply.
- Add what is genuinely missing: goal, audience, relevant context, output format,
  length, and (for factual asks) a request to say when unsure instead of guessing.
- NEVER invent facts about the user. Where a key detail is missing, put a short
  [bracketed placeholder] for them to fill in, e.g. [your grade level].
- Keep the rewrite about as short as it can be while still being clear. If the
  prompt is already strong, change little and say so in the tips.
- Tips: one short, plain sentence each, naming the change and why it helps.
- Output only the rewritten prompt in "improved" (no preamble, no quotes).`;

const TEACH_SYSTEM = `You are Prompt Coach in teaching mode. The user wants to learn to write
better AI prompts by making the edits THEMSELVES. Do NOT rewrite their prompt and do
not include a full replacement prompt.

Give a strength and the 2-3 highest-impact ways to improve, most important first.
- "strength": one specific thing the prompt already does well (never generic praise).
- Each suggestion has:
  - "title": 2-5 words naming the gap (e.g. "Say who it's for").
  - "why": one plain sentence on how it changes the AI's answer.
  - "try": a concrete nudge in the form of a question or a short fragment they could
    add (e.g. "Who will read this, and what do they already know?"), tied to THEIR
    topic. Not a finished prompt.
- Only raise things that matter for THIS prompt. If it is already strong, return one
  suggestion at most.
- Friendly, brief, no jargon.`;

const IMPROVE_SCHEMA = {
  type: "object",
  properties: {
    improved: { type: "string", description: "The improved version of the prompt." },
    tips: {
      type: "array",
      items: { type: "string" },
      description: "1-3 short, friendly explanations of what changed and why.",
    },
  },
  required: ["improved", "tips"],
  additionalProperties: false,
};

const TEACH_SCHEMA = {
  type: "object",
  properties: {
    strength: { type: "string", description: "One specific thing the prompt does well." },
    suggestions: {
      type: "array",
      items: {
        type: "object",
        properties: {
          title: { type: "string" },
          why: { type: "string" },
          try: { type: "string" },
        },
        required: ["title", "why", "try"],
        additionalProperties: false,
      },
      description: "0-3 highest-impact improvements, most important first.",
    },
  },
  required: ["strength", "suggestions"],
  additionalProperties: false,
};

async function getApiKey() {
  const { anthropicApiKey } = await chrome.storage.local.get("anthropicApiKey");
  return anthropicApiKey || "";
}

async function improveWithClaude(prompt, mode) {
  const teach = mode === "teach";
  const apiKey = await getApiKey();
  if (!apiKey) {
    return { error: "no_key" };
  }

  // Don't let a stalled request leave the card spinning forever.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  let res;
  try {
    res = await fetch("https://api.anthropic.com/v1/messages", {
    signal: controller.signal,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      // Required for calling the API directly from a browser context instead
      // of a server. This is what lets the request run with the USER's key,
      // billed to the USER's Anthropic account — not ours.
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 1024,
      system: teach ? TEACH_SYSTEM : IMPROVE_SYSTEM,
      output_config: {
        format: { type: "json_schema", schema: teach ? TEACH_SCHEMA : IMPROVE_SCHEMA },
      },
      messages: [{ role: "user", content: `${teach ? "Coach me on this prompt" : "Improve this prompt"}:\n\n${prompt}` }],
    }),
    });
  } catch (e) {
    return { error: "api_error", message: e && e.name === "AbortError" ? "Timed out waiting for Claude. Try again." : "Could not reach Anthropic. Check your connection." };
  } finally {
    clearTimeout(timeout);
  }

  const data = await res.json();

  if (!res.ok) {
    // Surface Anthropic's own error message (e.g. bad key, no credit) as-is.
    const message = (data && data.error && data.error.message) || `Request failed (${res.status})`;
    return { error: "api_error", message };
  }

  const textBlock = (data.content || []).find((b) => b.type === "text");
  if (!textBlock) return { error: "api_error", message: "No response from model." };

  try {
    const parsed = JSON.parse(textBlock.text);
    if (teach) return { mode: "teach", strength: parsed.strength || "", suggestions: parsed.suggestions || [] };
    return { mode: "improve", improved: parsed.improved, tips: parsed.tips || [] };
  } catch (e) {
    return { error: "api_error", message: "Could not parse the model's response." };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "PROMPT_COACH_IMPROVE") {
    improveWithClaude(message.prompt, message.mode).then(sendResponse);
    return true; // keep the message channel open for the async response
  }
  if (message && message.type === "PROMPT_COACH_OPEN_OPTIONS") {
    chrome.runtime.openOptionsPage();
  }
  if (message && message.type === "PROMPT_COACH_HAS_KEY") {
    getApiKey().then((key) => sendResponse({ hasKey: !!key }));
    return true;
  }
});
