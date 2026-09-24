// =============================================================================
// content.js  —  THE "PLUMBING" (ChatGPT / Claude.ai / Gemini web versions)
// -----------------------------------------------------------------------------
// This is the part that's specific to running inside a web AI chat site (see
// manifest.json's content_scripts.matches for the current site list). Its
// jobs:
//   1. Find the prompt text box on the page.
//   2. Watch what you type.
//   3. Quietly run the "brain" (window.PromptCoach.analyze) to feed the local
//      skill history — its findings are not shown on the page.
//   4. Optionally ask background.js for an AI-powered rewrite, using the
//      user's OWN Anthropic API key (set in Settings) — see background.js.
//   5. Show a small, always-visible, draggable card (collapsible to an icon)
//      with the AI's suggested rewrite and a "Use this" button.
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
  var customPos = null;    // {left, top} once the user has dragged the card
  var collapsed = false;   // true = shrunk to the small icon
  var mode = "improve";    // "improve" (AI rewrites) or "teach" (AI coaches, you edit)

  // --- Auto AI-critique (live, cost-guarded) ----------------------------------
  // See docs/PromptCoach_Direction_and_Roadmap.pdf: the paid rewrite can fire
  // automatically after a pause, not just on click — but real money is on the
  // line, so it stays guarded: on by default (switchable off in Settings), a
  // much longer pause than the free rules' 400ms, and a hard cooldown so
  // someone drafting a long prompt with several pauses can't trigger a burst
  // of calls.
  var autoTimer = null;
  var lastAutoFireAt = 0;
  var lastAutoText = "";
  var AUTO_PAUSE_MS = 3000;
  var AUTO_COOLDOWN_MS = 15000;
  var AUTO_MIN_WORDS = 3;

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

  // --- The widget: always on screen, either expanded or collapsed to an icon --
  // It never hides itself (not on blur, not on clicks elsewhere). The user can
  // collapse it to a small icon, drag either form anywhere, and click the icon
  // to reopen it. Both the position and collapsed state are remembered
  // (chrome.storage.local, shared across the supported sites). Only the
  // position is remembered: every page load starts open, in Improve mode.
  var CARD_W = 320, ICON_SIZE = 40;
  var HINT = "Start typing and a suggestion will appear here.";

  var REFRESH_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 3 21 9 15 9"/></svg>';
  var MIN_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>';

  function ensureCard() {
    if (card) return card;
    card = document.createElement("div");
    card.className = "pc-card";
    card.style.display = "none";
    card.innerHTML =
      '<div class="pc-panel">' +
        '<div class="pc-head">' +
          '<span class="pc-title">Prompt Coach</span>' +
          '<span class="pc-actions">' +
            '<button class="pc-ai" title="Get a new suggestion" aria-label="Get a new suggestion">' + REFRESH_SVG + '</button>' +
            '<button class="pc-min" title="Collapse to icon" aria-label="Collapse to icon">' + MIN_SVG + '</button>' +
          '</span>' +
        '</div>' +
        '<div class="pc-modes" role="tablist">' +
          '<button class="pc-mode" data-mode="improve" title="The AI rewrites your prompt for you">Improve</button>' +
          '<button class="pc-mode" data-mode="teach" title="The AI explains what to strengthen; you make the edits">Teach</button>' +
        '</div>' +
        '<div class="pc-ai-out"><div class="pc-ai-note">' + HINT + '</div></div>' +
      '</div>' +
      '<button class="pc-icon" title="Open Prompt Coach" aria-label="Open Prompt Coach">PC</button>';
    document.body.appendChild(card);

    card.querySelector(".pc-ai").addEventListener("click", function () {
      runAiImprove(currentBox || findPromptBox());
    });
    Array.prototype.forEach.call(card.querySelectorAll(".pc-mode"), function (b) {
      b.addEventListener("click", function () {
        var next = b.getAttribute("data-mode");
        if (next === mode) return;
        setMode(next);
        // Re-run right away if there is something to work on.
        var box = currentBox || findPromptBox();
        if (box && readText(box).trim()) runAiImprove(box);
      });
    });
    card.querySelector(".pc-min").addEventListener("click", function () { setCollapsed(true); });
    enableDrag(card);
    return card;
  }

  function setMode(next) {
    mode = next === "teach" ? "teach" : "improve";
    if (card) {
      Array.prototype.forEach.call(card.querySelectorAll(".pc-mode"), function (b) {
        var on = b.getAttribute("data-mode") === mode;
        b.classList.toggle("pc-mode-on", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
    }
  }

  function setCollapsed(value) {
    collapsed = !!value;
    if (card) card.classList.toggle("pc-collapsed", collapsed);
    positionCard();
  }

  // Drag the expanded card by its header, or the collapsed icon by itself.
  // Listeners live on the card because the contents change; a press on the
  // icon that barely moves counts as a click (reopens the card).
  function enableDrag(el) {
    function handle(e) {
      if (e.button !== 0) return false;
      if (collapsed) return !!e.target.closest(".pc-icon");
      return !!e.target.closest(".pc-head") && !e.target.closest("button");
    }

    // Keep focus in the prompt box while grabbing (no focus steal).
    el.addEventListener("mousedown", function (e) { if (handle(e)) e.preventDefault(); });

    // Double-click the header to snap back to the automatic placement.
    el.addEventListener("dblclick", function (e) {
      if (collapsed || !e.target.closest(".pc-head") || e.target.closest("button")) return;
      customPos = null;
      try { chrome.storage.local.remove("promptCoachCardPos"); } catch (err) {}
      positionCard();
    });

    el.addEventListener("pointerdown", function (e) {
      if (!handle(e)) return;
      var r = el.getBoundingClientRect();
      var dx = e.clientX - r.left, dy = e.clientY - r.top;
      var sx = e.clientX, sy = e.clientY, moved = false;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
      el.style.userSelect = "none";

      function move(ev) {
        if (!moved && Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) < 4) return;
        moved = true;
        customPos = { left: ev.clientX - dx, top: ev.clientY - dy };
        positionCard();
      }
      function up() {
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        el.removeEventListener("pointercancel", up);
        el.style.userSelect = "";
        if (moved) {
          var rr = el.getBoundingClientRect(); // save the clamped, on-screen spot
          customPos = { left: rr.left, top: rr.top };
          try { chrome.storage.local.set({ promptCoachCardPos: customPos }); } catch (err) {}
        } else if (collapsed) {
          setCollapsed(false);
        }
      }
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
    });
  }

  // Default placement (until the user drags it): docked to the right edge,
  // near the top. That keeps it clear of the prompt box (bottom centre) and of
  // the conversation (centre), and the collapsed icon sits in the same spot so
  // collapsing/reopening doesn't make it jump.
  function positionCard() {
    if (!card) return;
    var W = window.innerWidth, H = window.innerHeight;
    var w = collapsed ? ICON_SIZE : Math.min(CARD_W, W - 32);
    card.style.top = card.style.bottom = card.style.left = card.style.right = "auto";
    card.style.width = w + "px";

    if (customPos) {
      card.style.left = Math.max(0, Math.min(customPos.left, W - w)) + "px";
      card.style.top = Math.max(0, Math.min(customPos.top, H - (collapsed ? ICON_SIZE : 48))) + "px";
      return;
    }
    card.style.right = "16px";
    card.style.top = Math.min(80, Math.max(8, H - 120)) + "px";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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

  // --- "Improve with AI" — asks background.js, which uses the user's OWN key
  // A newer request supersedes an older one (requestId), so a slow reply can't
  // overwrite a fresher suggestion.
  var requestId = 0;
  function runAiImprove(box) {
    ensureCard();
    var out = card.querySelector(".pc-ai-out");
    var text = box ? readText(box) : "";
    if (!text.trim()) {
      out.innerHTML = '<div class="pc-ai-note">Type a prompt first, then refresh.</div>';
      return;
    }
    var myId = ++requestId;
    var reqMode = mode;
    out.innerHTML = '<div class="pc-ai-note">Thinking…</div>';

    chrome.runtime.sendMessage({ type: "PROMPT_COACH_IMPROVE", prompt: text, mode: mode }, function (result) {
      if (myId !== requestId) return;
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
        out.innerHTML = '<div class="pc-ai-err">' + escapeHtml(result.message || "Request failed.") + '</div>';
        return;
      }

      if (reqMode === "teach") {
        var sug = (result.suggestions || []).map(function (x) {
          return '<div class="pc-sug">' +
            '<div class="pc-sug-title">' + escapeHtml(x.title) + '</div>' +
            '<div class="pc-why">' + escapeHtml(x.why) + '</div>' +
            '<div class="pc-try">' + escapeHtml(x.try) + '</div></div>';
        }).join("");
        out.innerHTML =
          (result.strength ? '<div class="pc-strength">' + escapeHtml(result.strength) + '</div>' : '') +
          (sug || '<div class="pc-ai-note">Nothing major to add. This prompt is in good shape.</div>');
        return;
      }

      var tipsHtml = (result.tips || []).map(function (t) {
        return '<div class="pc-why">• ' + escapeHtml(t) + '</div>';
      }).join("");
      out.innerHTML =
        '<div class="pc-ai-card">' +
        '<div class="pc-ai-head"><span>Suggested prompt</span>' +
        '<button class="pc-ai-use">Use this</button></div>' +
        '<div class="pc-ai-text">' + escapeHtml(result.improved) + '</div>' +
        tipsHtml + '</div>';

      out.querySelector(".pc-ai-use").addEventListener("click", function () {
        usedSuggestionSinceLastSubmit = true;
        writeText(box, result.improved);
        out.innerHTML = '<div class="pc-ai-note">' + HINT + '</div>';
      });
    });
  }

  // Auto-fire the paid AI critique after a pause — on unless the user turned
  // it off in Settings or collapsed the widget, the prompt is at least a few
  // words, it has changed since the last auto-fire, and the cooldown has
  // elapsed. See the guardrail constants declared above.
  function maybeAutoCritique() {
    var LOG = "[Prompt Coach Auto]";
    if (!currentBox) { console.log(LOG, "skipped: no prompt box attached"); return; }
    if (collapsed) { console.log(LOG, "skipped: widget is collapsed"); return; }
    var text = readText(currentBox);
    var trimmed = text.trim();
    var wc = trimmed ? trimmed.split(/\s+/).length : 0;
    if (wc < AUTO_MIN_WORDS) { console.log(LOG, "skipped: too few words (" + wc + " < " + AUTO_MIN_WORDS + ")"); return; }
    if (text === lastAutoText) { console.log(LOG, "skipped: text unchanged since last auto-fire"); return; }
    var sinceLastFire = Date.now() - lastAutoFireAt;
    if (sinceLastFire < AUTO_COOLDOWN_MS) {
      // Don't drop the request — try again once the cooldown has passed.
      console.log(LOG, "cooldown (" + sinceLastFire + "ms < " + AUTO_COOLDOWN_MS + "ms), retrying when it ends");
      if (autoTimer) clearTimeout(autoTimer);
      autoTimer = setTimeout(maybeAutoCritique, AUTO_COOLDOWN_MS - sinceLastFire + 50);
      return;
    }
    if (typeof chrome === "undefined" || !chrome.storage) { console.log(LOG, "skipped: no chrome.storage available"); return; }

    chrome.storage.local.get("promptCoachAutoCritique", function (r) {
      if (r.promptCoachAutoCritique === false) { console.log(LOG, "skipped: toggle is off in Settings"); return; }
      console.log(LOG, "firing now");
      lastAutoFireAt = Date.now();
      lastAutoText = text;
      runAiImprove(currentBox);
    });
  }

  // --- The main loop: react to typing (debounced so it's not jumpy) ---------
  // The free rule-based analysis still runs (it feeds the local skill history
  // in recordSubmit), but only the AI critique is shown on the page.
  function onInput() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      if (!currentBox) return;
      lastAnalysis = window.PromptCoach.analyze(readText(currentBox));
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
    positionCard();
    console.log("[Prompt Coach] attached to prompt box");
  }

  // Show the widget right away (restoring saved position/collapsed state),
  // then keep it alive: these sites re-render, so re-attach it if the page
  // drops it, and keep looking for the prompt box (ChatGPT loads slowly).
  function start() {
    ensureCard();
    function show() { setMode(mode); setCollapsed(collapsed); card.style.display = "block"; }
    try {
      chrome.storage.local.get("promptCoachCardPos", function (r) {
        if (r && r.promptCoachCardPos) customPos = r.promptCoachCardPos;
        show();
      });
    } catch (e) { show(); }

    setInterval(function () {
      if (!document.body.contains(card)) document.body.appendChild(card);
      var box = findPromptBox();
      if (box && box !== currentBox) attach(box);
      positionCard();
    }, 1000);
  }

  start();
})();
