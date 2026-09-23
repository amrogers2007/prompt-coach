// Tests for extension/src/profile.js — the local-only per-user skill history
// backing the toolbar popup (profile.html). Unlike telemetry.js, this is NOT
// opt-in gated: nothing here ever leaves the browser, so there's no consent
// gate to test around — see the file's own header comment for why.

const test = require("node:test");
const assert = require("node:assert/strict");
const profile = require("../extension/src/profile.js");

test("_recordInto accumulates shown/accepted counts per category per day", () => {
  let buf = {};
  buf = profile._recordInto(buf, "missingContext", false, "2026-09-01");
  buf = profile._recordInto(buf, "missingContext", true, "2026-09-01");
  buf = profile._recordInto(buf, "outputFormat", false, "2026-09-01");
  assert.deepEqual(buf, {
    "2026-09-01": {
      missingContext: { shown: 2, accepted: 1 },
      outputFormat: { shown: 1, accepted: 0 },
    },
  });
});

test("_recordInto does not mutate the buffer it was given", () => {
  const original = { "2026-09-01": { x: { shown: 1, accepted: 0 } } };
  const next = profile._recordInto(original, "x", true, "2026-09-01");
  assert.deepEqual(original["2026-09-01"].x, { shown: 1, accepted: 0 });
  assert.deepEqual(next["2026-09-01"].x, { shown: 2, accepted: 1 });
});

test("_recordInto keeps separate days separate", () => {
  let buf = {};
  buf = profile._recordInto(buf, "missingContext", false, "2026-09-01");
  buf = profile._recordInto(buf, "missingContext", false, "2026-09-02");
  assert.deepEqual(buf, {
    "2026-09-01": { missingContext: { shown: 1, accepted: 0 } },
    "2026-09-02": { missingContext: { shown: 1, accepted: 0 } },
  });
});

test("_pruneOlderThan drops days older than the cutoff and keeps recent ones", () => {
  const buf = {
    "2020-01-01": { a: { shown: 1, accepted: 0 } },
    "2099-01-01": { b: { shown: 1, accepted: 0 } },
  };
  const pruned = profile._pruneOlderThan(buf, 30);
  assert.deepEqual(pruned, { "2099-01-01": { b: { shown: 1, accepted: 0 } } });
});

test("_pruneOlderThan does not mutate the input buffer", () => {
  const buf = { "2020-01-01": { a: { shown: 1, accepted: 0 } } };
  profile._pruneOlderThan(buf, 30);
  assert.deepEqual(buf, { "2020-01-01": { a: { shown: 1, accepted: 0 } } });
});

test("_skillSnapshot totals categories within the window and excludes what's outside it", () => {
  const buf = {
    "2020-01-01": { old: { shown: 100, accepted: 0 } },
    "2099-01-01": {
      missingContext: { shown: 5, accepted: 2 },
      outputFormat: { shown: 3, accepted: 3 },
    },
  };
  const snap = profile._skillSnapshot(buf, 30);
  assert.equal(snap.old, undefined);
  assert.deepEqual(snap.missingContext, { shown: 5, accepted: 2 });
  assert.deepEqual(snap.outputFormat, { shown: 3, accepted: 3 });
});

test("_skillSnapshot sums a category across multiple days in the window", () => {
  const buf = {
    "2099-01-01": { missingContext: { shown: 2, accepted: 0 } },
    "2099-01-02": { missingContext: { shown: 3, accepted: 1 } },
  };
  const snap = profile._skillSnapshot(buf, 30);
  assert.deepEqual(snap.missingContext, { shown: 5, accepted: 1 });
});

test("_categoryTrends: fewer triggers this week than last is 'improving'", () => {
  const d1 = new Date(); d1.setDate(d1.getDate() - 14);
  const d2 = new Date();
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const buf = {
    [fmt(d1)]: { missingContext: { shown: 10, accepted: 0 } },
    [fmt(d2)]: { missingContext: { shown: 3, accepted: 0 } },
  };
  const trends = profile._categoryTrends(buf);
  assert.equal(trends.missingContext.trend, "improving");
  assert.equal(trends.missingContext.lastWeek, 10);
  assert.equal(trends.missingContext.thisWeek, 3);
});

test("_categoryTrends: more triggers this week than last is 'slipping'", () => {
  const d1 = new Date(); d1.setDate(d1.getDate() - 14);
  const d2 = new Date();
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const buf = {
    [fmt(d1)]: { outputFormat: { shown: 2, accepted: 0 } },
    [fmt(d2)]: { outputFormat: { shown: 6, accepted: 0 } },
  };
  const trends = profile._categoryTrends(buf);
  assert.equal(trends.outputFormat.trend, "slipping");
});

test("_categoryTrends: only one week of data is 'insufficient-data'", () => {
  const trends = profile._categoryTrends({ "2099-01-01": { missingContext: { shown: 4, accepted: 0 } } });
  assert.equal(trends.missingContext.trend, "insufficient-data");
  assert.equal(trends.missingContext.lastWeek, null);
});

test("_categoryTrends returns {} for an empty buffer", () => {
  assert.deepEqual(profile._categoryTrends({}), {});
  assert.deepEqual(profile._categoryTrends(undefined), {});
});

// --- Behavior outside an extension context (no `chrome` global) ------------
// These exercise the real code paths profile.js takes when required from
// Node (as these tests do) — they must fail safe (no-op), never throw.
test("record() is a no-op (does not throw) with no chrome.storage", async () => {
  await assert.doesNotReject(() => profile.record("missingContext", false));
});

test("getSnapshot() resolves {} with no chrome.storage", async () => {
  assert.deepEqual(await profile.getSnapshot(), {});
});

test("getTrends() resolves {} with no chrome.storage", async () => {
  assert.deepEqual(await profile.getTrends(), {});
});

test("clearAll() is a no-op (does not throw) with no chrome.storage", async () => {
  await assert.doesNotReject(() => profile.clearAll());
});
