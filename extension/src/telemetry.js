// =============================================================================
// telemetry.js  —  DESIGN SKETCH, NOT WIRED IN
// -----------------------------------------------------------------------------
// See docs/PRIVACY-DESIGN.md for the full reasoning. Short version:
//
//   - Prompt text NEVER enters this file. It only ever sees rule IDs (the
//     same ids rules.js already assigns, e.g. "grounding", "sensitive") —
//     never the text that triggered them.
//   - It aggregates locally into day-bucketed counts per rule and holds them
//     until flush() is called — it never sends anything itself. There is no
//     backend to send it to yet; wiring this up is a future, separate change
//     that also needs a real consent UI (options.html) and a server that
//     enforces k-anonymity before a manager ever sees a number. Doing that
//     enforcement here, client-side, would be a lie: a single browser can't
//     see other employees' counts, so it can't know if a group is big enough
//     to be anonymous. See docs/PRIVACY-DESIGN.md §3.
//   - Everything is off by default. record() is a no-op until a caller
//     confirms opt-in via isEnabled().
//
// This file is intentionally NOT referenced by manifest.json, content.js, or
// background.js. It exists so the aggregation logic can be written, tested,
// and reviewed before any product/legal decision to turn telemetry on.
// =============================================================================

(function () {
  var STORAGE_KEY = "promptCoachTelemetryOptIn";
  var BUFFER_KEY = "promptCoachTelemetryBuffer";

  function todayBucket() {
    // Day-level only — never a precise timestamp. See docs/PRIVACY-DESIGN.md.
    return new Date().toISOString().slice(0, 10); // "YYYY-MM-DD"
  }

  // Pure function: given the current buffer and a rule id, return the next
  // buffer. Kept pure and separate from chrome.storage so it's trivially
  // unit-testable without a browser or extension APIs.
  function recordInto(buffer, ruleId, date) {
    date = date || todayBucket();
    var next = JSON.parse(JSON.stringify(buffer || {}));
    if (!next[date]) next[date] = {};
    next[date][ruleId] = (next[date][ruleId] || 0) + 1;
    return next;
  }

  // Turn a day's counts into the exact shape docs/PRIVACY-DESIGN.md §6
  // describes — the only thing that would ever be sent, and only once a
  // real opt-in + backend exist.
  function toAggregatedEvent(buffer, date, team) {
    date = date || todayBucket();
    return {
      team: team || null,      // employer-provided label, never inferred from identity
      date: date,
      counts: (buffer && buffer[date]) || {},
    };
  }

  // Drop any day older than `days` (default 30) — don't hold data forever
  // just because it hasn't been flushed.
  function pruneOlderThan(buffer, days) {
    days = days || 30;
    var cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    var cutoffStr = cutoff.toISOString().slice(0, 10);
    var next = {};
    Object.keys(buffer || {}).forEach(function (date) {
      if (date >= cutoffStr) next[date] = buffer[date];
    });
    return next;
  }

  // --- chrome.storage-backed wrapper (thin; the logic above is what matters) --
  function isEnabled() {
    if (typeof chrome === "undefined" || !chrome.storage) return Promise.resolve(false);
    return chrome.storage.local.get(STORAGE_KEY).then(function (r) {
      return !!r[STORAGE_KEY];
    });
  }

  function setEnabled(enabled) {
    if (typeof chrome === "undefined" || !chrome.storage) return Promise.resolve();
    var toSet = {};
    toSet[STORAGE_KEY] = !!enabled;
    var clear = enabled ? Promise.resolve() : chrome.storage.local.remove(BUFFER_KEY);
    return clear.then(function () { return chrome.storage.local.set(toSet); });
  }

  // Call this with a rule id from rules.js's analyze() output — never the
  // prompt text. No-ops silently if telemetry isn't opted in.
  function record(ruleId) {
    return isEnabled().then(function (enabled) {
      if (!enabled) return;
      return chrome.storage.local.get(BUFFER_KEY).then(function (r) {
        var buffer = pruneOlderThan(recordInto(r[BUFFER_KEY], ruleId));
        var toSet = {};
        toSet[BUFFER_KEY] = buffer;
        return chrome.storage.local.set(toSet);
      });
    });
  }

  // Returns the aggregated event for today, or null if there's nothing to
  // send / telemetry is off. Does NOT send it anywhere — see file header.
  function flush(team) {
    return isEnabled().then(function (enabled) {
      if (!enabled) return null;
      return chrome.storage.local.get(BUFFER_KEY).then(function (r) {
        var event = toAggregatedEvent(r[BUFFER_KEY], todayBucket(), team);
        return Object.keys(event.counts).length ? event : null;
      });
    });
  }

  var api = {
    isEnabled: isEnabled,
    setEnabled: setEnabled,
    record: record,
    flush: flush,
    // Exposed for unit testing without chrome.storage:
    _recordInto: recordInto,
    _toAggregatedEvent: toAggregatedEvent,
    _pruneOlderThan: pruneOlderThan,
  };

  if (typeof window !== "undefined") window.PromptCoachTelemetry = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
