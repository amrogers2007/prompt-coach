// =============================================================================
// content.js  —  THE "PLUMBING" (ChatGPT web version)
// -----------------------------------------------------------------------------
// This is the part that's specific to running inside the ChatGPT website.
// Its jobs:
//   1. Find the prompt text box on the page.
//   2. Watch what you type.
//   3. Ask the "brain" (window.PromptCoach.analyze) what could be better
//      (instant, free, rule-based).
//   4. Optionally ask background.js for an AI-powered rewrite, using the
//      user's OWN Anthropic API key (set in Settings) — see background.js.
//   5. Show a little suggestion card, with "Use this" buttons.
//
// If we later build a desktop version, THIS file gets rewritten, but rules.js
// (the brain) stays exactly the same.
// =============================================================================

(function () {
  var card = null;         // the suggestion card element (created once)
  var currentBox = null;   // the prompt box we're watching
  var debounceTimer = null;
  var lastAnalysis = null;

  // --- Find the prompt box ---------------------------------------------------
  // ChatGPT changes its HTML often, so we try several selectors and fall back
  // to "the biggest text box on the page."
  function findPromptBox() {
    var candidates = [
      document.querySelector("#prompt-textarea"),
      document.querySelector("main form textarea"),
      document.querySelector("form textarea"),
      document.querySelector('div[contenteditable="true"]'),
      document.querySelector("textarea")
    ];
    for (var i = 0; i < candidates.length; i++) {
      if (candidates[i]) return candidates[i];
    }
    return null;
  }

  // Read the text out of the box (works for <textarea> and contenteditable div).
  function readText(box) {
    if (!box) return "";
    if (box.tagName === "TEXTAREA") return box.value;
    return box.innerText || "";
  }

  // Write text INTO the box (so "Use this" actually replaces the prompt).
  function writeText(box, text) {
    box.focus();
    if (box.tagName === "TEXTAREA") {
      box.value = text;
      box.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      // contenteditable: select everything, then insert (keeps the site happy).
      var sel = window.getSelection();
      var range = document.createRange();
      range.selectNodeContents(box);
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand("insertText", false, text);
    }
  }

  // --- Build the suggestion card (once) -------------------------------------
  function ensureCard() {
    if (card) return card;
    card = document.createElement("div");
    card.className = "pc-card";
    card.style.display = "none";
    document.body.appendChild(card);
    return card;
  }

  function hideCard() {
    if (card) card.style.display = "none";
  }

  // Put the card just above the prompt box.
  function positionCard(box) {
    var rect = box.getBoundingClientRect();
    card.style.left = rect.left + "px";
    card.style.width = Math.min(rect.width, 520) + "px";
    card.style.bottom = (window.innerHeight - rect.top + 8) + "px";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // --- Render the analysis into the card ------------------------------------
  function render(box, analysis) {
    ensureCard();
    lastAnalysis = analysis;

    var wc = readText(box).trim() ? readText(box).trim().split(/\s+/).length : 0;
    if (wc < 2) { hideCard(); return; }

    var html = '<div class="pc-head">' +
      '<span class="pc-title">✨ Prompt Coach</span>' +
      '<button class="pc-x" title="Dismiss">×</button>' +
      '</div>';

    if (analysis.issues.length) {
      html += '<ul class="pc-list">';
      analysis.issues.forEach(function (issue) {
        html += '<li class="pc-item">' +
          '<div class="pc-item-title">' + escapeHtml(issue.title) + '</div>' +
          '<div class="pc-why">' + escapeHtml(issue.why) + '</div>' +
          (issue.eg ? '<div class="pc-eg">Try: “' + escapeHtml(issue.eg) + '”</div>' : '') +
          '</li>';
      });
      html += '</ul>';

      var improvedDiffers = analysis.improvedPrompt && analysis.improvedPrompt !== readText(box);
      if (improvedDiffers) {
        html += '<button class="pc-use">Use improved prompt</button>';
      }
    } else {
      html += '<div class="pc-solid">✅ Looks solid.</div>';
    }

    // Optional AI-powered rewrite, using the user's own key (background.js).
    html += '<button class="pc-ai">✨ Improve with AI</button>';
    html += '<div class="pc-ai-out"></div>';

    card.innerHTML = html;

    card.querySelector(".pc-x").addEventListener("click", hideCard);
    var useBtn = card.querySelector(".pc-use");
    if (useBtn) {
      useBtn.addEventListener("click", function () {
        writeText(box, analysis.improvedPrompt);
        hideCard();
      });
    }
    card.querySelector(".pc-ai").addEventListener("click", function () {
      runAiImprove(box);
    });

    positionCard(box);
    card.style.display = "block";
  }

  // --- "Improve with AI" — asks background.js, which uses the user's OWN key
  function runAiImprove(box) {
    var out = card.querySelector(".pc-ai-out");
    var text = readText(box);
    out.innerHTML = '<div class="pc-ai-note">🤔 Asking Claude…</div>';

    chrome.runtime.sendMessage({ type: "PROMPT_COACH_IMPROVE", prompt: text }, function (result) {
      if (chrome.runtime.lastError) {
        out.innerHTML = '<div class="pc-ai-err">Something went wrong reaching the extension. Try reloading the page.</div>';
        return;
      }
      if (!result) return;

      if (result.error === "no_key") {
        out.innerHTML = '<div class="pc-ai-note">No API key set yet. ' +
          '<button class="pc-ai-settings">Add your key</button> to turn this on ' +
          '(uses your own Anthropic account — you pay only for what you use).</div>';
        out.querySelector(".pc-ai-settings").addEventListener("click", function () {
          chrome.runtime.sendMessage({ type: "PROMPT_COACH_OPEN_OPTIONS" });
        });
        return;
      }
      if (result.error) {
        out.innerHTML = '<div class="pc-ai-err">⚠️ ' + escapeHtml(result.message || "Request failed.") + '</div>';
        return;
      }

      var tipsHtml = (result.tips || []).map(function (t) {
        return '<div class="pc-why">• ' + escapeHtml(t) + '</div>';
      }).join("");
      out.innerHTML =
        '<div class="pc-ai-card">' +
        '<div class="pc-ai-head"><span>🤖 AI-improved prompt</span>' +
        '<button class="pc-ai-use">Use this</button></div>' +
        '<div class="pc-ai-text">' + escapeHtml(result.improved) + '</div>' +
        tipsHtml + '</div>';

      out.querySelector(".pc-ai-use").addEventListener("click", function () {
        writeText(box, result.improved);
        hideCard();
      });
    });
  }

  // --- The main loop: react to typing (debounced so it's not jumpy) ---------
  function onInput() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      if (!currentBox) return;
      var text = readText(currentBox);
      var analysis = window.PromptCoach.analyze(text);
      render(currentBox, analysis);
    }, 400);
  }

  // Attach our listener to the prompt box once we find it.
  function attach(box) {
    if (box === currentBox) return;
    currentBox = box;
    box.addEventListener("input", onInput);
    box.addEventListener("blur", function () { setTimeout(hideCard, 200); });
    console.log("[Prompt Coach] attached to prompt box");
  }

  // ChatGPT loads slowly and re-renders, so keep checking for the box.
  setInterval(function () {
    var box = findPromptBox();
    if (box && box !== currentBox) attach(box);
    if (card && card.style.display === "block" && currentBox) positionCard(currentBox);
  }, 1000);
})();
