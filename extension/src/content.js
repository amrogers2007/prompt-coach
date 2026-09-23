// =============================================================================
// content.js  —  THE "PLUMBING" (ChatGPT / Claude.ai / Gemini web versions)
// -----------------------------------------------------------------------------
// This is the part that's specific to running inside a web AI chat site (see
// manifest.json's content_scripts.matches for the current site list). Its
// jobs:
//   1. Find the prompt text box on the page.
//   2. Watch what you type.
//   3. Ask the "brain" (window.PromptCoach.analyze) what could be better
//      (instant, free, rule-based).
//   4. Optionally ask background.js for an AI-powered rewrite, using the
//      user's OWN Anthropic API key (set in Settings) — see background.js.
//   5. Show a little suggestion card, with "Use this" buttons.
//
// findPromptBox() tries site-specific selectors first (they're the most
// reliable when they match), then falls back to "the first contenteditable
// or textarea on the page" — every text-box-based AI chat site has one of
// those, even ones we haven't added a specific selector for yet. This is
// also why adding a new site is usually just a manifest.json match, not new
// selector code: see extension/README.md.
//
// If we later build a desktop version, THIS file gets rewritten, but rules.js
// (the brain) stays exactly the same.
// =============================================================================

(function () {
  var card = null;         // the suggestion card element (created once)
  var currentBox = null;   // the prompt box we're watching
  var debounceTimer = null;
  var lastAnalysis = null;

  // --- Auto AI-critique (live, cost-guarded) ----------------------------------
  // See docs/PromptCoach_Direction_and_Roadmap.pdf: the paid rewrite can fire
  // automatically after a pause, not just on click — but real money is on the
  // line, so this is deliberately conservative: off by default (Settings
  // toggle), a much longer pause than the free rules' 400ms, and a hard
  // cooldown so someone drafting a long prompt with several pauses can't
  // trigger a burst of calls.
  var autoTimer = null;
  var lastAutoFireAt = 0;
  var lastAutoText = "";
  var AUTO_PAUSE_MS = 3000;
  var AUTO_COOLDOWN_MS = 15000;
  var AUTO_MIN_WORDS = 6;

  // --- "Doesn't refine" proxy + per-prompt profile recording ------------------
  // Lightweight heuristic (see docs/PromptCoach_Direction_and_Roadmap.pdf):
  // rather than reading the AI's reply off the page (fragile, site-specific,
  // deferred), we just watch submissions: did you send a new prompt soon
  // after the last one without ever using a suggestion?
  var lastSubmitTime = 0;
  var lastSubmitText = "";
  var hasPriorSubmit = false;
  var usedSuggestionSinceLastSubmit = false;
  var REFINE_WINDOW_MS = 120000; // 2 minutes

  // --- Find the prompt box ---------------------------------------------------
  // These sites change their HTML often, so we try known selectors first
  // (most specific/reliable), then fall back to "the first contenteditable
  // or textarea on the page." If Prompt Coach stops attaching on a site,
  // check the console for "[Prompt Coach] attached to prompt box" — if it's
  // missing, that site likely needs a new selector added here.
  function findPromptBox() {
    var candidates = [
      document.querySelector("#prompt-textarea"),                 // chatgpt.com
      document.querySelector('div.ProseMirror[contenteditable="true"]'), // claude.ai
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

  // Small, non-blocking celebration when a suggestion is actually used — see
  // docs/PromptCoach_Direction_and_Roadmap.pdf's "minimal aesthetic, small
  // celebrations" direction. Web Animations API only — no library, no new
  // CSS keyframes to maintain.
  function celebrate() {
    if (!card) return;
    var colors = ["#2b59c3", "#5b7fd6", "#8aa6e6", "#3a4a7a", "#6f8fe0"];
    for (var i = 0; i < 6; i++) {
      var dot = document.createElement("div");
      dot.style.cssText = "position:absolute;top:6px;left:50%;width:6px;height:6px;" +
        "border-radius:1px;background:" + colors[i % colors.length] + ";pointer-events:none;";
      card.appendChild(dot);
      var dx = (Math.random() - 0.5) * 60;
      var dy = -20 - Math.random() * 30;
      var rot = (Math.random() - 0.5) * 180;
      dot.animate(
        [
          { transform: "translate(0,0) rotate(0deg)", opacity: 1 },
          { transform: "translate(" + dx + "px," + dy + "px) rotate(" + rot + "deg)", opacity: 0 }
        ],
        { duration: 600 + Math.random() * 200, easing: "ease-out" }
      );
      (function (d) { setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); }, 900); })(dot);
    }
  }

  // Record this prompt's detected issues (if any) into the local skill
  // history, then reset submit-tracking for the next prompt. Called right
  // before a submit is allowed to go through.
  function recordSubmit(text) {
    if (!window.PromptCoachProfile) return;

    var now = Date.now();
    if (hasPriorSubmit && (now - lastSubmitTime) < REFINE_WINDOW_MS &&
        !usedSuggestionSinceLastSubmit &&
        window.PromptCoach.classify(lastSubmitText) === "generative") {
      // Sent a new prompt soon after the last one, never used a suggestion,
      // and the prior prompt was the kind that benefits from iterating.
      window.PromptCoachProfile.record("iterationMindset", false);
    }

    if (lastAnalysis && lastAnalysis.issues) {
      lastAnalysis.issues.forEach(function (issue) {
        if (issue.category) window.PromptCoachProfile.record(issue.category, usedSuggestionSinceLastSubmit);
      });
    }

    lastSubmitTime = now;
    lastSubmitText = text;
    hasPriorSubmit = true;
    usedSuggestionSinceLastSubmit = false;
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
        usedSuggestionSinceLastSubmit = true;
        celebrate();
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
        usedSuggestionSinceLastSubmit = true;
        celebrate();
        writeText(box, result.improved);
        hideCard();
      });
    });
  }

  // Auto-fire the paid AI critique after a long pause — only if the user
  // opted in (Settings toggle, off by default), the prompt is the kind that
  // benefits (classify() === "generative"), it's actually changed since the
  // last auto-fire, and the cooldown has elapsed. See the guardrail constants
  // declared above.
  function maybeAutoCritique() {
    if (!currentBox) return;
    var text = readText(currentBox);
    var trimmed = text.trim();
    var wc = trimmed ? trimmed.split(/\s+/).length : 0;
    if (wc < AUTO_MIN_WORDS) return;
    if (text === lastAutoText) return;
    if (window.PromptCoach.classify(text) !== "generative") return;
    if (Date.now() - lastAutoFireAt < AUTO_COOLDOWN_MS) return;
    if (typeof chrome === "undefined" || !chrome.storage) return;

    chrome.storage.local.get("promptCoachAutoCritique", function (r) {
      if (!r.promptCoachAutoCritique) return;
      lastAutoFireAt = Date.now();
      lastAutoText = text;
      runAiImprove(currentBox);
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

    if (autoTimer) clearTimeout(autoTimer);
    autoTimer = setTimeout(maybeAutoCritique, AUTO_PAUSE_MS);
  }

  // Enter (without Shift) is the near-universal "send" gesture across these
  // sites' prompt boxes — used only to observe a submission, never to block
  // or alter it. Text is captured here, before the site's own handler runs,
  // since some sites clear the box immediately after Enter.
  function onKeydown(e) {
    if (e.key !== "Enter" || e.shiftKey) return;
    var text = readText(currentBox).trim();
    if (text) recordSubmit(text);
  }

  // Attach our listener to the prompt box once we find it.
  function attach(box) {
    if (box === currentBox) return;
    currentBox = box;
    box.addEventListener("input", onInput);
    box.addEventListener("keydown", onKeydown);
    // Clicking a button inside the card (e.g. "Improve with AI") blurs the
    // prompt box too, since focus moves to that button. Only auto-hide if
    // focus actually left the card — otherwise a slow AI response (network
    // latency > this 200ms delay) finishes updating a card that's already
    // hidden, which looks like nothing happened. Explicit actions (dismiss,
    // "Use improved prompt") still hide the card themselves either way.
    box.addEventListener("blur", function () {
      setTimeout(function () {
        if (card && card.contains(document.activeElement)) return;
        hideCard();
      }, 200);
    });
    console.log("[Prompt Coach] attached to prompt box");
  }

  // ChatGPT loads slowly and re-renders, so keep checking for the box.
  setInterval(function () {
    var box = findPromptBox();
    if (box && box !== currentBox) attach(box);
    if (card && card.style.display === "block" && currentBox) positionCard(currentBox);
  }, 1000);
})();
