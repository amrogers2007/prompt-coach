// =============================================================================
// server.js  —  THE "AI BRAIN" (a tiny local server)
// -----------------------------------------------------------------------------
// Why this exists: the API key must NEVER go in the browser. This little server
// runs on YOUR computer, holds the key, and is the only thing that talks to
// Claude. The playground/extension sends a prompt here; this sends back an
// improved version + tips.
//
// Run it with:   ANTHROPIC_API_KEY=sk-ant-... node server.js
// (see README.md in this folder for the full setup)
// =============================================================================

import http from "node:http";
import Anthropic from "@anthropic-ai/sdk";

const PORT = 8787;

// The model. Default is Claude Opus 5 (most capable). For a fast, cheaper
// prompt-rewriter you can switch this to "claude-haiku-4-5" — see README.
const MODEL = "claude-opus-5";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY from the environment

const SYSTEM_PROMPT = `You are Prompt Coach. Rewrite the user's AI prompt so it
gets a better result, then explain what you improved in 1-3 short, friendly tips.

Rules:
- Keep the rewrite faithful to what the user actually wants.
- Improve clarity, add missing context/format/goal, and guard against made-up info.
- Be concise and encouraging. Tips are one short sentence each, no jargon.`;

// Force the model to return exactly this JSON shape, so we can trust it.
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

async function improveWithClaude(prompt) {
  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 2048,
    system: SYSTEM_PROMPT,
    output_config: {
      format: { type: "json_schema", schema: SCHEMA },
      effort: "low", // this is a small, fast task — low effort keeps it quick + cheap
    },
    messages: [{ role: "user", content: `Improve this prompt:\n\n${prompt}` }],
  });

  // With output_config.format, the first text block is guaranteed valid JSON.
  const textBlock = response.content.find((b) => b.type === "text");
  return JSON.parse(textBlock.text);
}

// --- Minimal HTTP server with CORS (so the browser page can call it) --------
const server = http.createServer(async (req, res) => {
  // CORS headers — let the local playground page talk to us.
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }

  if (req.method === "POST" && req.url === "/improve") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", async () => {
      try {
        const { prompt } = JSON.parse(body || "{}");
        if (!prompt || !prompt.trim()) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Please include a non-empty 'prompt'." }));
          return;
        }
        const result = await improveWithClaude(prompt);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(result));
      } catch (err) {
        console.error("[Prompt Coach] error:", err.message);
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }

  res.writeHead(404).end("Not found");
});

server.listen(PORT, () => {
  console.log(`[Prompt Coach] AI brain running at http://localhost:${PORT}`);
  console.log(`[Prompt Coach] model: ${MODEL}`);
});
