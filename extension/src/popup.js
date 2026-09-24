// Popup logic for profile.html — extension pages enforce a strict CSP that
// blocks inline <script> blocks entirely (no exceptions, unlike a regular
// web page), so this has to live in its own file and be loaded via
// <script src="popup.js">, same as options.html/options.js already do.

var CATEGORY_LABELS = {
  missingContext: "Missing Context",
  vagueAsk: "Vague / Ambiguous Ask",
  outputFormat: "No Output Format",
  tooBroad: "Too Broad in Scope",
  missingConstraints: "Missing Constraints",
  iterationMindset: "Doesn't Refine / Iterate",
  accuracyGrounding: "Accuracy / Grounding",
};

function render() {
  Promise.all([
    window.PromptCoachProfile.getSnapshot(30),
    window.PromptCoachProfile.getTrends(),
  ]).then(function (results) {
    var snapshot = results[0];
    var trends = results[1];
    var container = document.getElementById("snapshot");
    var safetyNote = document.getElementById("safety-note");

    var rows = Object.keys(CATEGORY_LABELS)
      .map(function (cat) { return { cat: cat, shown: (snapshot[cat] && snapshot[cat].shown) || 0 }; })
      .filter(function (r) { return r.shown > 0; })
      .sort(function (a, b) { return b.shown - a.shown; });

    if (rows.length === 0) {
      container.innerHTML = '<div class="empty">No coaching yet in the last 30 days — start typing a prompt on chatgpt.com, claude.ai, or gemini.google.com.</div>';
    } else {
      var max = rows[0].shown;
      container.innerHTML = rows.map(function (r) {
        var pct = Math.max(6, Math.round((r.shown / max) * 100));
        var trendInfo = trends[r.cat];
        var trendSymbol = "";
        var trendClass = "";
        if (trendInfo && trendInfo.trend !== "insufficient-data") {
          trendClass = trendInfo.trend;
          trendSymbol = trendInfo.trend === "improving" ? "▼" : trendInfo.trend === "slipping" ? "▲" : "▬";
        }
        return '<div class="row">' +
          '<div class="row-label">' + CATEGORY_LABELS[r.cat] + '</div>' +
          '<div class="row-bar-track"><div class="row-bar-fill" style="width:' + pct + '%"></div></div>' +
          '<div class="row-count">' + r.shown + '</div>' +
          '<div class="trend ' + trendClass + '" title="' + (trendInfo ? trendInfo.trend : "") + '">' + trendSymbol + '</div>' +
          '</div>';
      }).join("");
    }

    var safetyShown = (snapshot.safety && snapshot.safety.shown) || 0;
    if (safetyShown > 0) {
      safetyNote.style.display = "block";
      safetyNote.textContent = "⚠️ Sensitive-data pattern flagged " + safetyShown + " time" + (safetyShown === 1 ? "" : "s") + " in the last 30 days.";
    } else {
      safetyNote.style.display = "none";
    }
  });
}

document.getElementById("clear").addEventListener("click", function () {
  window.PromptCoachProfile.clearAll().then(render);
});

render();
