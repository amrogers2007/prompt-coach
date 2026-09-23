// Settings page logic: save/clear the user's own Anthropic API key in
// chrome.storage.local. Nothing here ever sends the key anywhere — that
// only happens in background.js, directly to api.anthropic.com.

const keyInput = document.getElementById("key");
const status = document.getElementById("status");

function showStatus(text, kind) {
  status.textContent = text;
  status.className = kind || "";
}

// Pre-fill with a masked placeholder if a key is already saved, so the user
// can tell at a glance whether one is set without ever re-displaying it.
chrome.storage.local.get("anthropicApiKey", ({ anthropicApiKey }) => {
  if (anthropicApiKey) {
    keyInput.placeholder = "sk-ant-•••• (saved — enter a new key to replace it)";
  }
});

document.getElementById("save").addEventListener("click", () => {
  const value = keyInput.value.trim();
  if (!value) {
    showStatus("Enter a key first.", "err");
    return;
  }
  if (!value.startsWith("sk-ant-")) {
    showStatus("That doesn't look like an Anthropic key (should start with sk-ant-).", "err");
    return;
  }
  chrome.storage.local.set({ anthropicApiKey: value }, () => {
    keyInput.value = "";
    keyInput.placeholder = "sk-ant-•••• (saved — enter a new key to replace it)";
    showStatus("Saved. \"Improve with AI\" is now on.", "ok");
  });
});

document.getElementById("clear").addEventListener("click", () => {
  chrome.storage.local.remove("anthropicApiKey", () => {
    keyInput.value = "";
    keyInput.placeholder = "sk-ant-...";
    showStatus("Key removed. Rule-based coaching still works; AI rewrite is off.", "ok");
  });
});

// Auto-critique toggle: off by default (see content.js's maybeAutoCritique
// and its cost-guardrail constants). Reflect/persist it here, nothing more —
// content.js reads this same key straight from chrome.storage.local itself.
const autoCritiqueInput = document.getElementById("auto-critique");

chrome.storage.local.get("promptCoachAutoCritique", ({ promptCoachAutoCritique }) => {
  autoCritiqueInput.checked = !!promptCoachAutoCritique;
});

autoCritiqueInput.addEventListener("change", () => {
  chrome.storage.local.set({ promptCoachAutoCritique: autoCritiqueInput.checked });
});
