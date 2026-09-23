// =============================================================================
// profile.js  —  YOUR OWN LOCAL SKILL HISTORY
// -----------------------------------------------------------------------------
// Unlike telemetry.js (see docs/PRIVACY-DESIGN.md), this is NOT gated behind
// an opt-in: nothing here ever leaves the browser. It's the same local-storage
// aggregation pattern (day-bucketed counts, pruned after a window) applied to
// a single purpose — showing you your own trend, in the popup (profile.html).
//
// One record per coaching event: { category, accepted }. "accepted" means a
// suggestion was actually used (a "Use..." button clicked), not just shown.
// =============================================================================

(function () {
  var BUFFER_KEY = "promptCoachProfileBuffer";

  // Local calendar date (not UTC) — this is a personal trend view, so it
  // should match the day the user actually experienced, unlike telemetry.js's
  // UTC choice (which exists there for cross-timezone server aggregation).
  function todayBucket(d) {
    d = d || new Date();
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function recordInto(buffer, category, accepted, date) {
    date = date || todayBucket();
    var next = JSON.parse(JSON.stringify(buffer || {}));
    if (!next[date]) next[date] = {};
    if (!next[date][category]) next[date][category] = { shown: 0, accepted: 0 };
    next[date][category].shown += 1;
    if (accepted) next[date][category].accepted += 1;
    return next;
  }

  function pruneOlderThan(buffer, days) {
    days = days || 90;
    var cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    var cutoffStr = todayBucket(cutoff);
    var next = {};
    Object.keys(buffer || {}).forEach(function (date) {
      if (date >= cutoffStr) next[date] = buffer[date];
    });
    return next;
  }

  // Totals per category over the last `days` (default 30) — the "skill snapshot".
  function skillSnapshot(buffer, days) {
    days = days || 30;
    var cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    var cutoffStr = todayBucket(cutoff);
    var totals = {};
    Object.keys(buffer || {}).forEach(function (date) {
      if (date < cutoffStr) return;
      var day = buffer[date];
      Object.keys(day).forEach(function (cat) {
        if (!totals[cat]) totals[cat] = { shown: 0, accepted: 0 };
        totals[cat].shown += day[cat].shown;
        totals[cat].accepted += day[cat].accepted;
      });
    });
    return totals;
  }

  // Coarse week index (days-since-epoch / 7) — good enough for a lightweight
  // personal week-over-week trend; doesn't need to align to real ISO weeks.
  function weekKey(dateStr) {
    var d = new Date(dateStr + "T00:00:00");
    var epochDays = Math.floor(d.getTime() / 86400000);
    return Math.floor(epochDays / 7);
  }

  // Per-category week-over-week trend: "improving" means the category fired
  // LESS this week than last (fewer weaknesses flagged = better prompts),
  // "slipping" means more, "plateauing" means the same.
  function categoryTrends(buffer) {
    var weeks = {};
    Object.keys(buffer || {}).forEach(function (date) {
      var wk = weekKey(date);
      if (!weeks[wk]) weeks[wk] = {};
      Object.keys(buffer[date]).forEach(function (cat) {
        weeks[wk][cat] = (weeks[wk][cat] || 0) + buffer[date][cat].shown;
      });
    });
    var weekIdxs = Object.keys(weeks).map(Number).sort(function (a, b) { return a - b; });
    if (weekIdxs.length === 0) return {};

    var thisWk = weekIdxs[weekIdxs.length - 1];
    var lastWk = weekIdxs.length >= 2 ? weekIdxs[weekIdxs.length - 2] : null;
    var allCats = {};
    weekIdxs.forEach(function (w) { Object.keys(weeks[w]).forEach(function (c) { allCats[c] = true; }); });

    var result = {};
    Object.keys(allCats).forEach(function (cat) {
      var thisCount = (weeks[thisWk] && weeks[thisWk][cat]) || 0;
      var lastCount = lastWk !== null ? ((weeks[lastWk] && weeks[lastWk][cat]) || 0) : null;
      var trend = "insufficient-data";
      if (lastCount !== null) {
        if (thisCount < lastCount) trend = "improving";
        else if (thisCount > lastCount) trend = "slipping";
        else trend = "plateauing";
      }
      result[cat] = { thisWeek: thisCount, lastWeek: lastCount, trend: trend };
    });
    return result;
  }

  // --- chrome.storage-backed wrapper ------------------------------------------
  function record(category, accepted) {
    if (typeof chrome === "undefined" || !chrome.storage) return Promise.resolve();
    return chrome.storage.local.get(BUFFER_KEY).then(function (r) {
      var buffer = pruneOlderThan(recordInto(r[BUFFER_KEY], category, accepted));
      var toSet = {};
      toSet[BUFFER_KEY] = buffer;
      return chrome.storage.local.set(toSet);
    });
  }

  function getSnapshot(days) {
    if (typeof chrome === "undefined" || !chrome.storage) return Promise.resolve({});
    return chrome.storage.local.get(BUFFER_KEY).then(function (r) {
      return skillSnapshot(r[BUFFER_KEY], days);
    });
  }

  function getTrends() {
    if (typeof chrome === "undefined" || !chrome.storage) return Promise.resolve({});
    return chrome.storage.local.get(BUFFER_KEY).then(function (r) {
      return categoryTrends(r[BUFFER_KEY]);
    });
  }

  function clearAll() {
    if (typeof chrome === "undefined" || !chrome.storage) return Promise.resolve();
    return chrome.storage.local.remove(BUFFER_KEY);
  }

  var api = {
    record: record,
    getSnapshot: getSnapshot,
    getTrends: getTrends,
    clearAll: clearAll,
    // Exposed for unit testing without chrome.storage:
    _recordInto: recordInto,
    _pruneOlderThan: pruneOlderThan,
    _skillSnapshot: skillSnapshot,
    _categoryTrends: categoryTrends,
  };

  if (typeof window !== "undefined") window.PromptCoachProfile = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
