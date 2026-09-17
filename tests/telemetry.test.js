// Tests for extension/src/telemetry.js — the (not-yet-wired-in) client-side
// telemetry aggregation sketch. See docs/PRIVACY-DESIGN.md for why this
// exists and what it deliberately does NOT do.

const test = require("node:test");
const assert = require("node:assert/strict");
const telemetry = require("../extension/src/telemetry.js");

test("_recordInto accumulates counts per rule per day", () => {
  let buf = {};
  buf = telemetry._recordInto(buf, "grounding", "2026-01-01");
  buf = telemetry._recordInto(buf, "grounding", "2026-01-01");
  buf = telemetry._recordInto(buf, "format", "2026-01-01");
  assert.deepEqual(buf, { "2026-01-01": { grounding: 2, format: 1 } });
});

test("_recordInto does not mutate the buffer it was given", () => {
  const original = { "2026-01-01": { x: 1 } };
  const next = telemetry._recordInto(original, "x", "2026-01-01");
  assert.equal(original["2026-01-01"].x, 1);
  assert.equal(next["2026-01-01"].x, 2);
});

test("_recordInto keeps separate days separate", () => {
  let buf = {};
  buf = telemetry._recordInto(buf, "grounding", "2026-01-01");
  buf = telemetry._recordInto(buf, "grounding", "2026-01-02");
  assert.deepEqual(buf, {
    "2026-01-01": { grounding: 1 },
    "2026-01-02": { grounding: 1 },
  });
});

test("_toAggregatedEvent contains only team, date, and counts — never raw text", () => {
  const buf = { "2026-01-01": { grounding: 3, sensitive: 1 } };
  const event = telemetry._toAggregatedEvent(buf, "2026-01-01", "sales-west");
  assert.deepEqual(event, {
    team: "sales-west",
    date: "2026-01-01",
    counts: { grounding: 3, sensitive: 1 },
  });
  assert.deepEqual(Object.keys(event).sort(), ["counts", "date", "team"]);
});

test("_toAggregatedEvent defaults team to null and counts to {} for an unknown day", () => {
  const event = telemetry._toAggregatedEvent({}, "2026-01-01");
  assert.deepEqual(event, { team: null, date: "2026-01-01", counts: {} });
});

test("_pruneOlderThan drops days older than the cutoff and keeps recent ones", () => {
  const buf = { "2020-01-01": { x: 1 }, "2099-01-01": { y: 1 } };
  const pruned = telemetry._pruneOlderThan(buf, 30);
  assert.deepEqual(pruned, { "2099-01-01": { y: 1 } });
});

test("_pruneOlderThan does not mutate the input buffer", () => {
  const buf = { "2020-01-01": { x: 1 } };
  telemetry._pruneOlderThan(buf, 30);
  assert.deepEqual(buf, { "2020-01-01": { x: 1 } });
});

// --- Behavior outside an extension context (no `chrome` global) ------------
// These exercise the real code paths telemetry.js takes when required from
// Node (as these tests do) or loaded on a page with no extension APIs —
// they must fail safe (no-op), never throw.
test("isEnabled() resolves false when there is no chrome.storage", async () => {
  assert.equal(await telemetry.isEnabled(), false);
});

test("record() is a no-op (does not throw) with no chrome.storage", async () => {
  await assert.doesNotReject(() => telemetry.record("grounding"));
});

test("flush() resolves null with no chrome.storage", async () => {
  assert.equal(await telemetry.flush("sales-west"), null);
});
