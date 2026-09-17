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

const SYSTEM_PROMPT = `You are Prompt Coach. Rewrite the user's AI prompt so it
gets a better result, then explain what you improved in 1-3 short, friendly tips.

Rules:
- Keep the rewrite faithful to what the user actually wants.
- Improve clarity, add missing context/format/goal, and guard against made-up info.
- Be concise and encouraging. Tips are one short sentence each, no jargon.`;

const SCHEMA = {
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

async function getApiKey() {
  const { anthropicApiKey } = await chrome.storage.local.get("anthropicApiKey");
  return anthropicApiKey || "";
}

async function improveWithClaude(prompt) {
  const apiKey = await getApiKey();
  if (!apiKey) {
    return { error: "no_key" };
  }

  const res = await fetch("https://api.anthropic.com/v1/messages", {
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
      system: SYSTEM_PROMPT,
      output_config: {
        format: { type: "json_schema", schema: SCHEMA },
        effort: "low",
      },
      messages: [{ role: "user", content: `Improve this prompt:\n\n${prompt}` }],
    }),
  });

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
    return { improved: parsed.improved, tips: parsed.tips || [] };
  } catch (e) {
    return { error: "api_error", message: "Could not parse the model's response." };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "PROMPT_COACH_IMPROVE") {
    improveWithClaude(message.prompt).then(sendResponse);
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
